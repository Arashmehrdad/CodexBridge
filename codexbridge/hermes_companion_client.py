from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .hermes_companion_protocol import (
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
    HermesCompanionProtocolError,
    verify_handshake_identity,
)

MAX_COMPANION_REQUEST_BYTES = 64 * 1024
DEFAULT_COMPANION_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class HermesCompanionLaunch:
    profile_id: str
    checkout: str
    argv: tuple[str, ...]
    stdin_text: str
    timeout_seconds: int
    expected_registry_generation: int | None
    expected_schema_hash: str
    operation: str


def _canonical_line(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n"
    if len(encoded.encode("utf-8")) > MAX_COMPANION_REQUEST_BYTES:
        raise HermesCompanionProtocolError("companion request exceeds maximum size")
    return encoded


def build_companion_launch(
    *,
    profile_id: str,
    checkout: str | Path,
    operation: str,
    payload: Mapping[str, Any] | None = None,
    expected_registry_generation: int | None = None,
    expected_schema_hash: str = "",
    timeout_seconds: int = DEFAULT_COMPANION_TIMEOUT_SECONDS,
) -> HermesCompanionLaunch:
    normalized_profile = str(profile_id).strip()
    if not normalized_profile:
        raise HermesCompanionProtocolError("companion profile_id must not be empty")
    checkout_path = Path(checkout).resolve()
    if not checkout_path.is_dir() or checkout_path.is_symlink():
        raise HermesCompanionProtocolError(
            "Hermes checkout must be an existing non-symlink directory"
        )
    normalized_operation = str(operation).strip()
    if normalized_operation not in {"handshake", "tool_search", "tool_describe", "tool_call"}:
        raise HermesCompanionProtocolError(
            f"unsupported companion client operation: {normalized_operation or '<empty>'}"
        )
    if timeout_seconds < 1 or timeout_seconds > 600:
        raise HermesCompanionProtocolError(
            "companion timeout_seconds must be between 1 and 600"
        )

    request = {"operation": normalized_operation, **dict(payload or {})}
    if normalized_operation != "handshake":
        if not isinstance(expected_registry_generation, int) or expected_registry_generation < 0:
            raise HermesCompanionProtocolError(
                "expected_registry_generation is required for bound requests"
            )
        if len(expected_schema_hash) != 64:
            raise HermesCompanionProtocolError(
                "expected_schema_hash must be a 64-character SHA-256 value"
            )
        request.update(
            {
                "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
                "registry_generation": expected_registry_generation,
                "effective_schema_hash": expected_schema_hash,
            }
        )

    return HermesCompanionLaunch(
        profile_id=normalized_profile,
        checkout=str(checkout_path),
        argv=(
            "-m",
            "codexbridge.hermes_companion",
            "--hermes-checkout",
            str(checkout_path),
        ),
        stdin_text=_canonical_line(request),
        timeout_seconds=int(timeout_seconds),
        expected_registry_generation=expected_registry_generation,
        expected_schema_hash=expected_schema_hash,
        operation=normalized_operation,
    )


def start_companion_request(manager: Any, repo_name: str, launch: HermesCompanionLaunch) -> dict:
    companion_metadata = {
        "operation": launch.operation,
        "hermes_revision": PINNED_HERMES_REVISION,
        "checkout": launch.checkout,
        "expected_registry_generation": launch.expected_registry_generation,
        "expected_schema_hash": launch.expected_schema_hash,
        "one_request": True,
    }
    response = manager.start_executable_profile(
        repo_name,
        launch.profile_id,
        list(launch.argv),
        working_directory=str(Path.cwd().resolve()),
        stdin_text=launch.stdin_text,
        timeout_seconds=launch.timeout_seconds,
        hermes_companion=companion_metadata,
    )
    result = dict(response)
    result["hermes_companion"] = {
        "operation": launch.operation,
        "hermes_revision": PINNED_HERMES_REVISION,
        "checkout": launch.checkout,
        "expected_registry_generation": launch.expected_registry_generation,
        "expected_schema_hash": launch.expected_schema_hash,
        "one_request": True,
    }
    return result


def parse_companion_result(
    stdout: str,
    *,
    expected_operation: str,
    expected_registry_generation: int | None = None,
    expected_schema_hash: str = "",
) -> dict[str, Any]:
    lines = [line for line in str(stdout).splitlines() if line.strip()]
    if len(lines) != 1:
        raise HermesCompanionProtocolError(
            "companion must emit exactly one response for one-request execution"
        )
    try:
        response = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise HermesCompanionProtocolError("companion response is not valid JSON") from exc
    if not isinstance(response, dict):
        raise HermesCompanionProtocolError("companion response must be a JSON object")
    if response.get("ok") is not True:
        raise HermesCompanionProtocolError(
            f"companion request failed: {response.get('error', 'unknown error')}"
        )
    if response.get("operation") != expected_operation:
        raise HermesCompanionProtocolError("companion response operation drift")
    if expected_operation == "handshake":
        generation = response.get("registry_generation")
        schema_hash = response.get("effective_schema_hash")
        if not isinstance(generation, int) or generation < 0 or not isinstance(schema_hash, str):
            raise HermesCompanionProtocolError("companion handshake identity is incomplete")
        verify_handshake_identity(
            response,
            expected_registry_generation=generation,
            expected_schema_hash=schema_hash,
        )
    else:
        if expected_registry_generation is None:
            raise HermesCompanionProtocolError("expected registry identity is required")
        if response.get("registry_generation") != expected_registry_generation:
            raise HermesCompanionProtocolError("Hermes registry generation drift")
        if response.get("effective_schema_hash") != expected_schema_hash:
            raise HermesCompanionProtocolError("Hermes effective schema drift")
    return response
