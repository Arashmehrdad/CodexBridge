from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, TextIO

from .hermes_companion_protocol import (
    DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
    HermesCompanionProtocolError,
    build_handshake,
    effective_schema_hash,
    tool_call,
    tool_describe,
    tool_search,
)

MAX_REQUEST_BYTES = 64 * 1024


@dataclass(frozen=True)
class HermesRegistrySnapshot:
    generation: int
    definitions: tuple[dict[str, Any], ...]
    active_toolsets: tuple[str, ...]
    executor: Any | None = None
    initialization_warnings: tuple[str, ...] = ()


class HermesCompanionRuntimeError(RuntimeError):
    """Fail-closed companion startup or adapter failure."""


def _canonical_error(operation: str, exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "operation": operation,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _git_revision(checkout: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    revision = result.stdout.strip().lower()
    if result.returncode != 0 or len(revision) != 40:
        raise HermesCompanionRuntimeError(
            "unable to verify the Hermes checkout revision"
        )
    if revision != PINNED_HERMES_REVISION:
        raise HermesCompanionRuntimeError(
            f"Hermes checkout revision drift: expected {PINNED_HERMES_REVISION}, observed {revision}"
        )
    return revision


def _registry_generation(registry: Any) -> int:
    for name in ("generation", "_generation", "registry_generation"):
        value = getattr(registry, name, None)
        if isinstance(value, int) and value >= 0:
            return value
    raise HermesCompanionRuntimeError(
        "unsupported Hermes ToolRegistry interface: generation is unavailable"
    )


def _registry_definitions(registry: Any) -> list[dict[str, Any]]:
    names_getter = getattr(registry, "get_all_tool_names", None)
    if not callable(names_getter):
        raise HermesCompanionRuntimeError(
            "unsupported Hermes ToolRegistry interface: get_all_tool_names is unavailable"
        )
    tool_names = names_getter()
    if not isinstance(tool_names, (list, tuple, set, frozenset)) or any(
        not isinstance(name, str) or not name for name in tool_names
    ):
        raise HermesCompanionRuntimeError(
            "unsupported Hermes ToolRegistry interface: tool names are invalid"
        )
    normalized_names = set(tool_names)
    if not normalized_names:
        raise HermesCompanionRuntimeError(
            "Hermes registry contains no tools after built-in discovery"
        )

    entries = getattr(registry, "_tools", None)
    if not isinstance(entries, Mapping):
        raise HermesCompanionRuntimeError(
            "unsupported Hermes ToolRegistry interface: raw tool entries are unavailable"
        )
    if set(entries) != normalized_names:
        raise HermesCompanionRuntimeError(
            "unsupported Hermes ToolRegistry interface: catalog identity is inconsistent"
        )

    definitions: list[dict[str, Any]] = []
    for name in sorted(normalized_names):
        entry = entries[name]
        schema = getattr(entry, "schema", None)
        if not isinstance(schema, Mapping):
            raise HermesCompanionRuntimeError(
                f"unsupported Hermes ToolRegistry interface: schema is invalid for {name}"
            )
        definition = dict(schema)
        if definition.get("name") != name:
            raise HermesCompanionRuntimeError(
                f"unsupported Hermes ToolRegistry interface: schema identity drift for {name}"
            )
        toolset = getattr(entry, "toolset", "")
        if toolset:
            definition.setdefault("toolset", str(toolset))
        definitions.append(definition)
    return definitions


def _active_toolsets(registry: Any) -> tuple[str, ...]:
    for name in ("active_toolsets", "enabled_toolsets", "toolsets"):
        value = getattr(registry, name, None)
        if isinstance(value, Mapping):
            return tuple(sorted(str(item) for item in value))
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted(str(item) for item in value))
    return ()


def _resolve_registry(module: Any) -> Any:
    for name in ("registry", "tool_registry", "TOOL_REGISTRY"):
        candidate = getattr(module, name, None)
        if candidate is not None:
            return candidate
    getter = getattr(module, "get_registry", None)
    if callable(getter):
        return getter()
    raise HermesCompanionRuntimeError(
        "unsupported Hermes registry module: no registry singleton is exposed"
    )


def load_pinned_registry(checkout: Path) -> HermesRegistrySnapshot:
    checkout = checkout.resolve()
    if not checkout.is_dir():
        raise HermesCompanionRuntimeError("Hermes checkout does not exist")
    _git_revision(checkout)
    checkout_text = str(checkout)
    if checkout_text not in sys.path:
        sys.path.insert(0, checkout_text)
    before = set(sys.modules)
    module = importlib.import_module("tools.registry")
    discover_builtin_tools = getattr(module, "discover_builtin_tools", None)
    if not callable(discover_builtin_tools):
        raise HermesCompanionRuntimeError(
            "unsupported Hermes registry module: discover_builtin_tools is unavailable"
        )
    discovered_modules = discover_builtin_tools()
    if not isinstance(discovered_modules, list) or any(
        not isinstance(name, str) or not name for name in discovered_modules
    ):
        raise HermesCompanionRuntimeError(
            "unsupported Hermes registry module: built-in discovery result is invalid"
        )
    registry = _resolve_registry(module)
    definitions = _registry_definitions(registry)
    imported = sorted(set(sys.modules) - before)
    handshake = build_handshake(
        registry_generation=_registry_generation(registry),
        tool_definitions=definitions,
        active_toolsets=_active_toolsets(registry),
        python_identity={"executable": sys.executable, "version": sys.version.split()[0]},
        imported_modules=imported,
    )
    model_tools = importlib.import_module("model_tools")
    handle_function_call = getattr(model_tools, "handle_function_call", None)
    if not callable(handle_function_call):
        raise HermesCompanionRuntimeError(
            "unsupported Hermes model_tools interface: handle_function_call is unavailable"
        )
    imported = sorted(set(sys.modules) - before)
    build_handshake(
        registry_generation=_registry_generation(registry),
        tool_definitions=definitions,
        active_toolsets=_active_toolsets(registry),
        python_identity={"executable": sys.executable, "version": sys.version.split()[0]},
        imported_modules=imported,
    )

    def execute_bound_tool(name: str, arguments: Mapping[str, Any]) -> str:
        return handle_function_call(
            function_name=name,
            function_args=dict(arguments),
            enabled_toolsets=list(handshake["active_toolsets"]),
            disabled_toolsets=[],
        )

    return HermesRegistrySnapshot(
        generation=int(handshake["registry_generation"]),
        definitions=tuple(definitions),
        active_toolsets=tuple(handshake["active_toolsets"]),
        executor=execute_bound_tool,
    )


class HermesCompanion:
    def __init__(
        self,
        snapshot: HermesRegistrySnapshot,
        *,
        max_output_bytes: int = DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
    ) -> None:
        self.snapshot = snapshot
        self.max_output_bytes = max_output_bytes
        self.schema_hash = effective_schema_hash(snapshot.definitions)
        self.handshake = build_handshake(
            registry_generation=snapshot.generation,
            tool_definitions=snapshot.definitions,
            active_toolsets=snapshot.active_toolsets,
            python_identity={"executable": sys.executable, "version": sys.version.split()[0]},
            imported_modules=(),
            initialization_warnings=snapshot.initialization_warnings,
            max_bytes=max_output_bytes,
        )

    def dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        operation = str(request.get("operation", "")).strip()
        if operation == "handshake":
            return dict(self.handshake)
        if request.get("protocol_version") != HERMES_COMPANION_PROTOCOL_VERSION:
            raise HermesCompanionProtocolError("companion protocol version drift")
        expected_generation = request.get("registry_generation")
        expected_schema_hash = request.get("effective_schema_hash")
        if not isinstance(expected_generation, int):
            raise HermesCompanionProtocolError("registry_generation is required")
        if not isinstance(expected_schema_hash, str):
            raise HermesCompanionProtocolError("effective_schema_hash is required")
        if operation == "tool_search":
            return tool_search(
                query=str(request.get("query", "")),
                limit=int(request.get("limit", 20)),
                tool_definitions=self.snapshot.definitions,
                handshake=self.handshake,
                expected_registry_generation=expected_generation,
                expected_schema_hash=expected_schema_hash,
                max_bytes=self.max_output_bytes,
            )
        if operation == "tool_call":
            if self.snapshot.executor is None:
                raise HermesCompanionProtocolError("Hermes tool execution is unavailable")
            return tool_call(
                tool_name=str(request.get("tool_name", "")),
                arguments=request.get("arguments", {}),
                tool_definitions=self.snapshot.definitions,
                handshake=self.handshake,
                expected_registry_generation=expected_generation,
                expected_schema_hash=expected_schema_hash,
                executor=self.snapshot.executor,
                max_bytes=self.max_output_bytes,
            )
        if operation == "tool_describe":
            return tool_describe(
                tool_name=str(request.get("tool_name", "")),
                tool_definitions=self.snapshot.definitions,
                handshake=self.handshake,
                expected_registry_generation=expected_generation,
                expected_schema_hash=expected_schema_hash,
                max_bytes=self.max_output_bytes,
            )
        raise HermesCompanionProtocolError(
            f"unsupported companion operation: {operation or '<empty>'}"
        )


def serve_stdio(companion: HermesCompanion, stdin: TextIO, stdout: TextIO) -> int:
    for raw_line in stdin:
        if len(raw_line.encode("utf-8")) > MAX_REQUEST_BYTES:
            response = _canonical_error("unknown", HermesCompanionProtocolError("request exceeds maximum size"))
        else:
            operation = "unknown"
            try:
                request = json.loads(raw_line)
                if not isinstance(request, Mapping):
                    raise HermesCompanionProtocolError("request must be a JSON object")
                operation = str(request.get("operation", "unknown"))
                response = companion.dispatch(request)
            except Exception as exc:
                response = _canonical_error(operation, exc)
        stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pinned Hermes registry companion over stdio")
    parser.add_argument(
        "--hermes-checkout",
        default=os.environ.get("CODEXBRIDGE_HERMES_CHECKOUT", ""),
    )
    parser.add_argument(
        "--max-output-bytes",
        type=int,
        default=DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.hermes_checkout:
        raise SystemExit("--hermes-checkout or CODEXBRIDGE_HERMES_CHECKOUT is required")
    snapshot = load_pinned_registry(Path(args.hermes_checkout))
    companion = HermesCompanion(snapshot, max_output_bytes=args.max_output_bytes)
    raise SystemExit(serve_stdio(companion, sys.stdin, sys.stdout))


if __name__ == "__main__":
    main()
