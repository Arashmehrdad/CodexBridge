from __future__ import annotations

import base64
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from .remote_controller_state import build_remote_controller_state_contract

REMOTE_POWERSHELL_CONTRACT_VERSION = 1
REMOTE_POWERSHELL_ARTIFACT_MANIFEST_VERSION = 1
_ALLOWED_EXECUTABLE_NAMES = {"pwsh", "pwsh.exe", "powershell", "powershell.exe"}


def build_remote_powershell_request(
    *,
    host_id: str,
    executable_path: str,
    argv: list[str],
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_bytes: bytes | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Build the deterministic, byte-safe X4 remote PowerShell request envelope."""
    normalized_host = str(host_id).strip()
    if not normalized_host:
        raise ValueError("Remote PowerShell requires host_id")

    executable = str(executable_path).strip()
    path = PurePosixPath(executable)
    if not executable.startswith("/") or path.name.lower() not in _ALLOWED_EXECUTABLE_NAMES:
        raise ValueError("Remote PowerShell requires an absolute pwsh or powershell path")

    exact_argv = [str(value) for value in argv]
    exact_environment = {
        str(name): str(value) for name, value in (environment or {}).items()
    }
    if any(not name for name in exact_environment):
        raise ValueError("Remote PowerShell environment names cannot be empty")
    if timeout_seconds is not None and int(timeout_seconds) < 1:
        raise ValueError("Remote PowerShell timeout_seconds must be positive or null")

    payload: dict[str, Any] = {
        "version": REMOTE_POWERSHELL_CONTRACT_VERSION,
        "host_id": normalized_host,
        "executable_path": executable,
        "argv": exact_argv,
        "working_directory": str(working_directory),
        "environment": exact_environment,
        "stdin_base64": base64.b64encode(stdin_bytes or b"").decode("ascii"),
        "stdin_size_bytes": len(stdin_bytes or b""),
        "timeout_seconds": None if timeout_seconds is None else int(timeout_seconds),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["request_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def decode_remote_powershell_stdin(request: dict[str, Any]) -> bytes:
    """Decode and verify the binary stdin carried by a request envelope."""
    try:
        decoded = base64.b64decode(str(request["stdin_base64"]), validate=True)
    except (KeyError, ValueError) as exc:
        raise ValueError("Remote PowerShell stdin_base64 is invalid") from exc
    if len(decoded) != int(request.get("stdin_size_bytes", -1)):
        raise ValueError("Remote PowerShell stdin size does not match the envelope")
    return decoded


def validate_remote_powershell_request(request: dict[str, Any]) -> dict[str, Any]:
    """Rebuild an accepted X4 envelope and reject any persisted-field drift."""
    if not isinstance(request, dict):
        raise ValueError("Persisted remote PowerShell request is invalid")
    required = {
        "version",
        "host_id",
        "executable_path",
        "argv",
        "working_directory",
        "environment",
        "stdin_base64",
        "stdin_size_bytes",
        "timeout_seconds",
        "request_fingerprint",
    }
    if set(request) != required:
        raise ValueError("Persisted remote PowerShell request fields are invalid")
    if request.get("version") != REMOTE_POWERSHELL_CONTRACT_VERSION:
        raise ValueError("Persisted remote PowerShell request version is invalid")
    argv = request.get("argv")
    environment = request.get("environment")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise ValueError("Persisted remote PowerShell argv must be a list of strings")
    if not isinstance(environment, dict) or any(
        not isinstance(name, str) or not isinstance(value, str)
        for name, value in environment.items()
    ):
        raise ValueError("Persisted remote PowerShell environment must contain string pairs")
    stdin_bytes = decode_remote_powershell_stdin(request)
    expected = build_remote_powershell_request(
        host_id=str(request["host_id"]),
        executable_path=str(request["executable_path"]),
        argv=list(argv),
        working_directory=str(request["working_directory"]),
        environment=dict(environment),
        stdin_bytes=stdin_bytes,
        timeout_seconds=request["timeout_seconds"],
    )
    if request != expected:
        raise ValueError("Remote PowerShell request changed after acceptance")
    return expected


def build_remote_powershell_artifact_manifest(
    *,
    run_id: str,
    lease_generation: int,
    controller_state: dict[str, Any],
) -> dict[str, Any]:
    """Declare protected remote and local binary output evidence for X4."""
    remote = dict(controller_state.get("remote") or {})
    streams = []
    for stream in ("stdout", "stderr"):
        remote_path = str(remote.get(f"{stream}_path") or "")
        if not remote_path:
            raise ValueError(f"Remote PowerShell controller is missing {stream}_path")
        streams.append(
            {
                "stream": stream,
                "remote_path": remote_path,
                "local_relative_path": f"artifacts/remote-{stream}.bin",
                "classification": "protected_evidence",
                "transfer_encoding": "binary",
                "publication_state": "pending",
            }
        )
    return {
        "version": REMOTE_POWERSHELL_ARTIFACT_MANIFEST_VERSION,
        "tool": "remote_powershell",
        "invoking_run_id": run_id,
        "lease_generation": int(lease_generation),
        "execution_id": str(controller_state.get("execution_id") or ""),
        "streams": streams,
    }


def validate_remote_powershell_artifact_manifest(
    manifest: dict[str, Any],
    *,
    run_id: str,
    lease_generation: int,
    controller_state: dict[str, Any],
) -> dict[str, Any]:
    """Reject artifact path, identity, classification, or encoding drift."""
    expected = build_remote_powershell_artifact_manifest(
        run_id=run_id,
        lease_generation=lease_generation,
        controller_state=controller_state,
    )
    if manifest != expected:
        raise ValueError("Remote PowerShell artifact manifest changed after acceptance")
    return expected


def build_remote_powershell_durable_input(
    request: dict[str, Any],
    *,
    run_id: str,
    lease_generation: int,
) -> dict[str, Any]:
    """Build the exact durable pre-launch payload for one X4 request."""
    validated = validate_remote_powershell_request(request)
    binding = bind_remote_powershell_controller_request(
        validated,
        run_id=run_id,
        lease_generation=lease_generation,
    )
    controller_state = build_remote_controller_state_contract(
        run_id=run_id,
        host_id=validated["host_id"],
        command_id=binding["command_id"],
        lease_generation=lease_generation,
        remote_argv=list(binding["remote_argv"]),
        timeout_seconds=binding["timeout_seconds"],
    )
    artifact_manifest = build_remote_powershell_artifact_manifest(
        run_id=run_id,
        lease_generation=lease_generation,
        controller_state=controller_state,
    )
    return {
        "host_id": validated["host_id"],
        "command_id": binding["command_id"],
        "remote_powershell_request": validated,
        "remote_powershell_binding": binding,
        "remote_controller_state": controller_state,
        "remote_powershell_artifact_manifest": artifact_manifest,
    }


def validate_remote_powershell_durable_input(
    input_data: dict[str, Any],
    *,
    run_id: str,
    lease_generation: int,
) -> dict[str, Any]:
    """Reject any durable X4 request, binding, or controller drift before launch."""
    if not isinstance(input_data, dict):
        raise ValueError("Persisted remote PowerShell durable input is invalid")
    request = input_data.get("remote_powershell_request")
    if not isinstance(request, dict):
        raise ValueError("Persisted remote PowerShell request is missing")
    expected = build_remote_powershell_durable_input(
        request,
        run_id=run_id,
        lease_generation=lease_generation,
    )
    if input_data != expected:
        raise ValueError("Remote PowerShell durable input changed after acceptance")
    return expected


def bind_remote_powershell_controller_request(
    request: dict[str, Any],
    *,
    run_id: str,
    lease_generation: int,
) -> dict[str, Any]:
    """Create the exact R4 controller input identity for one accepted X4 request."""
    validated = validate_remote_powershell_request(request)
    timeout = validated["timeout_seconds"]
    return {
        "command_id": "remote_powershell",
        "remote_argv": [validated["executable_path"], *validated["argv"]],
        "timeout_seconds": timeout,
        "request_fingerprint": validated["request_fingerprint"],
        "request_id": run_id,
        "lease_generation": int(lease_generation),
    }
