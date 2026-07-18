from __future__ import annotations

import base64
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

REMOTE_POWERSHELL_CONTRACT_VERSION = 1
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
