from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence

HERMES_COMPANION_PROTOCOL_VERSION = "1.0"
PINNED_HERMES_REVISION = "862b1b37bf0aadba3a98b3756c7d71779379b53b"
DEFAULT_PUBLIC_OUTPUT_MAX_BYTES = 64 * 1024
MAX_SEARCH_LIMIT = 100

_FORBIDDEN_MODEL_MODULE_PREFIXES = (
    "hermes_agent",
    "model_client",
    "model_provider",
    "agent_loop",
    "inference",
)


class HermesCompanionProtocolError(ValueError):
    """Deterministic companion-contract failure."""


class HermesInterfaceDriftError(HermesCompanionProtocolError):
    """Raised when the caller and companion no longer share one catalog identity."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bounded_envelope(payload: Mapping[str, Any], max_bytes: int) -> dict[str, Any]:
    if max_bytes < 256:
        raise HermesCompanionProtocolError("max_bytes must be at least 256")
    result = dict(payload)
    encoded = _canonical_json(result).encode("utf-8")
    if len(encoded) > max_bytes:
        raise HermesCompanionProtocolError(
            f"companion response exceeds the public output bound of {max_bytes} bytes"
        )
    result["encoded_bytes"] = len(encoded)
    return result


def effective_schema_hash(tool_definitions: Sequence[Mapping[str, Any]]) -> str:
    normalized = sorted(
        (dict(definition) for definition in tool_definitions),
        key=lambda item: str(item.get("name", "")),
    )
    names = [str(item.get("name", "")) for item in normalized]
    if any(not name for name in names):
        raise HermesCompanionProtocolError("every tool definition must have a name")
    if len(names) != len(set(names)):
        raise HermesCompanionProtocolError("tool definition names must be unique")
    return sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()


def assert_no_model_runtime_initialized(imported_modules: Iterable[str]) -> None:
    observed = sorted({str(name).strip() for name in imported_modules if str(name).strip()})
    forbidden = [
        name
        for name in observed
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in _FORBIDDEN_MODEL_MODULE_PREFIXES
        )
    ]
    if forbidden:
        raise HermesCompanionProtocolError(
            "Hermes model runtime initialization is forbidden: " + ", ".join(forbidden)
        )


def build_handshake(
    *,
    registry_generation: int,
    tool_definitions: Sequence[Mapping[str, Any]],
    active_toolsets: Sequence[str],
    python_identity: Mapping[str, Any],
    imported_modules: Iterable[str] = (),
    initialization_warnings: Sequence[str] = (),
    hermes_revision: str = PINNED_HERMES_REVISION,
    protocol_version: str = HERMES_COMPANION_PROTOCOL_VERSION,
    max_bytes: int = DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
) -> dict[str, Any]:
    if hermes_revision != PINNED_HERMES_REVISION:
        raise HermesInterfaceDriftError(
            f"unsupported Hermes revision: {hermes_revision}"
        )
    if protocol_version != HERMES_COMPANION_PROTOCOL_VERSION:
        raise HermesInterfaceDriftError(
            f"unsupported companion protocol: {protocol_version}"
        )
    if not isinstance(registry_generation, int) or registry_generation < 0:
        raise HermesCompanionProtocolError("registry_generation must be non-negative")
    assert_no_model_runtime_initialized(imported_modules)
    payload = {
        "ok": True,
        "operation": "handshake",
        "protocol_version": protocol_version,
        "hermes_revision": hermes_revision,
        "registry_generation": registry_generation,
        "effective_schema_hash": effective_schema_hash(tool_definitions),
        "active_toolsets": sorted({str(value) for value in active_toolsets}),
        "python_identity": dict(python_identity),
        "model_runtime_initialized": False,
        "initialization_warnings": [str(value) for value in initialization_warnings],
    }
    return _bounded_envelope(payload, max_bytes)


def verify_handshake_identity(
    handshake: Mapping[str, Any],
    *,
    expected_registry_generation: int,
    expected_schema_hash: str,
) -> None:
    if handshake.get("protocol_version") != HERMES_COMPANION_PROTOCOL_VERSION:
        raise HermesInterfaceDriftError("companion protocol version drift")
    if handshake.get("hermes_revision") != PINNED_HERMES_REVISION:
        raise HermesInterfaceDriftError("Hermes revision drift")
    if handshake.get("model_runtime_initialized") is not False:
        raise HermesCompanionProtocolError("model runtime initialization evidence is invalid")
    if handshake.get("registry_generation") != expected_registry_generation:
        raise HermesInterfaceDriftError("Hermes registry generation drift")
    if handshake.get("effective_schema_hash") != expected_schema_hash:
        raise HermesInterfaceDriftError("Hermes effective schema drift")


def tool_search(
    *,
    query: str,
    tool_definitions: Sequence[Mapping[str, Any]],
    handshake: Mapping[str, Any],
    expected_registry_generation: int,
    expected_schema_hash: str,
    limit: int = 20,
    max_bytes: int = DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
) -> dict[str, Any]:
    verify_handshake_identity(
        handshake,
        expected_registry_generation=expected_registry_generation,
        expected_schema_hash=expected_schema_hash,
    )
    normalized_query = str(query).strip().casefold()
    if not normalized_query:
        raise HermesCompanionProtocolError("tool_search query must not be empty")
    if limit < 1 or limit > MAX_SEARCH_LIMIT:
        raise HermesCompanionProtocolError(
            f"tool_search limit must be between 1 and {MAX_SEARCH_LIMIT}"
        )
    matches: list[dict[str, Any]] = []
    for definition in sorted(tool_definitions, key=lambda item: str(item.get("name", ""))):
        name = str(definition.get("name", ""))
        description = str(definition.get("description", ""))
        toolset = str(definition.get("toolset", ""))
        haystack = "\n".join((name, description, toolset)).casefold()
        if normalized_query not in haystack:
            continue
        matches.append(
            {
                "name": name,
                "description": description,
                "toolset": toolset,
                "schema_hash": sha256(_canonical_json(dict(definition)).encode("utf-8")).hexdigest(),
            }
        )
        if len(matches) >= limit:
            break
    return _bounded_envelope(
        {
            "ok": True,
            "operation": "tool_search",
            "registry_generation": expected_registry_generation,
            "effective_schema_hash": expected_schema_hash,
            "query": str(query),
            "results": matches,
            "result_count": len(matches),
        },
        max_bytes,
    )


def tool_call(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    tool_definitions: Sequence[Mapping[str, Any]],
    handshake: Mapping[str, Any],
    expected_registry_generation: int,
    expected_schema_hash: str,
    executor: Any,
    max_bytes: int = DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
) -> dict[str, Any]:
    verify_handshake_identity(
        handshake,
        expected_registry_generation=expected_registry_generation,
        expected_schema_hash=expected_schema_hash,
    )
    exact_name = str(tool_name).strip()
    if not exact_name:
        raise HermesCompanionProtocolError("tool_call name must not be empty")
    matches = [dict(item) for item in tool_definitions if str(item.get("name", "")) == exact_name]
    if len(matches) != 1:
        raise HermesCompanionProtocolError(f"Hermes tool is unavailable or ambiguous: {exact_name}")
    if not isinstance(arguments, Mapping):
        raise HermesCompanionProtocolError("tool_call arguments must be an object")
    definition = matches[0]
    result = executor(exact_name, dict(arguments))
    if not isinstance(result, (str, dict)):
        raise HermesCompanionProtocolError("Hermes tool result has an unsupported type")
    return _bounded_envelope(
        {
            "ok": True,
            "operation": "tool_call",
            "registry_generation": expected_registry_generation,
            "effective_schema_hash": expected_schema_hash,
            "tool_name": exact_name,
            "tool_schema_hash": sha256(_canonical_json(definition).encode("utf-8")).hexdigest(),
            "arguments": dict(arguments),
            "result": result,
        },
        max_bytes,
    )


def tool_describe(
    *,
    tool_name: str,
    tool_definitions: Sequence[Mapping[str, Any]],
    handshake: Mapping[str, Any],
    expected_registry_generation: int,
    expected_schema_hash: str,
    max_bytes: int = DEFAULT_PUBLIC_OUTPUT_MAX_BYTES,
) -> dict[str, Any]:
    verify_handshake_identity(
        handshake,
        expected_registry_generation=expected_registry_generation,
        expected_schema_hash=expected_schema_hash,
    )
    exact_name = str(tool_name).strip()
    if not exact_name:
        raise HermesCompanionProtocolError("tool_describe name must not be empty")
    matches = [dict(item) for item in tool_definitions if str(item.get("name", "")) == exact_name]
    if not matches:
        raise HermesCompanionProtocolError(f"Hermes tool is unavailable: {exact_name}")
    if len(matches) != 1:
        raise HermesCompanionProtocolError(f"Hermes tool identity is ambiguous: {exact_name}")
    definition = matches[0]
    return _bounded_envelope(
        {
            "ok": True,
            "operation": "tool_describe",
            "registry_generation": expected_registry_generation,
            "effective_schema_hash": expected_schema_hash,
            "tool_name": exact_name,
            "tool_schema_hash": sha256(_canonical_json(definition).encode("utf-8")).hexdigest(),
            "definition": definition,
        },
        max_bytes,
    )
