from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .return_loop.atomic_writer import atomic_write_json
from .ssh_probes import SSHProbeSpec

SSH_CAPABILITY_SCHEMA_VERSION = "ssh-capability-snapshot.v1"
SSH_CAPABILITIES_DIR = "ssh_capabilities"

_HOST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_SNAPSHOT_ID_RE = re.compile(
    r"^\d{8}T\d{6}Z_sshcap_[0-9a-f]{8}$"
)
_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]+={0,2}$")
_OS_RELEASE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_CAPABILITY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_TOOL_PROBES: dict[str, tuple[str, ...]] = {
    "systemd": ("systemctl", "--version"),
    "docker": ("docker", "--version"),
    "docker_compose": ("docker", "compose", "version"),
    "supervisor": ("supervisorctl", "version"),
    "kubectl": ("kubectl", "version", "--client", "--output=yaml"),
    "nginx": ("nginx", "-v"),
    "git": ("git", "--version"),
    "python": ("python3", "--version"),
    "node": ("node", "--version"),
    "npm": ("npm", "--version"),
    "curl": ("curl", "--version"),
    "sha256sum": ("sha256sum", "--version"),
    "tar": ("tar", "--version"),
    "scp": ("scp", "-V"),
    "rsync": ("rsync", "--version"),
    "setsid": ("setsid", "--version"),
}

_PACKAGE_MANAGER_COMMAND = (
    "for command_name in apt-get dnf yum apk pacman zypper; do "
    "if command -v \"$command_name\" >/dev/null 2>&1; then "
    "printf '%s\\n' \"$command_name\"; exit 0; fi; done; exit 1"
)
_SHELL_FACTS_COMMAND = (
    "printf 'shell=%s\\n' \"${SHELL:-}\"; "
    "printf 'sh=%s\\n' \"$(command -v sh 2>/dev/null || true)\"; "
    "printf 'bash=%s\\n' \"$(command -v bash 2>/dev/null || true)\"; "
    "printf 'pwsh=%s\\n' \"$(command -v pwsh 2>/dev/null || true)\""
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_snapshot_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_sshcap_{uuid4().hex[:8]}"


def _normalize_host_id(host_id: str) -> str:
    value = str(host_id or "").strip()
    if not _HOST_ID_RE.fullmatch(value):
        raise ValueError("SSH capability host_id must use letters, numbers, _ or -")
    return value


def _normalize_fingerprint(value: str) -> str:
    fingerprint = str(value or "").strip().rstrip("=")
    if fingerprint and not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("SSH capability host-key fingerprint is invalid")
    return fingerprint


def _normalize_required(values: Sequence[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        name = str(value or "").strip().lower()
        if not _CAPABILITY_NAME_RE.fullmatch(name):
            raise ValueError(f"Invalid required SSH capability: {value!r}")
        normalized.add(name)
    return tuple(sorted(normalized))


def capability_probe_specs() -> tuple[SSHProbeSpec, ...]:
    specs: list[SSHProbeSpec] = [
        SSHProbeSpec("os_release", ("cat", "/etc/os-release"), timeout_seconds=15),
        SSHProbeSpec("architecture", ("uname", "-m"), timeout_seconds=15, required=True),
        SSHProbeSpec("kernel", ("uname", "-sr"), timeout_seconds=15, required=True),
        SSHProbeSpec("effective_uid", ("id", "-u"), timeout_seconds=15, required=True),
        SSHProbeSpec("sudo_noninteractive", ("sudo", "-n", "true"), timeout_seconds=15),
        SSHProbeSpec("timezone", ("date", "+%Z%z"), timeout_seconds=15),
        SSHProbeSpec("locale", ("locale",), timeout_seconds=15),
        SSHProbeSpec(
            "package_manager",
            ("sh", "-lc", _PACKAGE_MANAGER_COMMAND),
            timeout_seconds=15,
        ),
        SSHProbeSpec(
            "shells",
            ("sh", "-lc", _SHELL_FACTS_COMMAND),
            timeout_seconds=15,
        ),
    ]
    specs.extend(
        SSHProbeSpec(name, argv, timeout_seconds=20)
        for name, argv in sorted(_TOOL_PROBES.items())
    )
    return tuple(specs)


def _probe_ok(result: Mapping[str, Any] | None) -> bool:
    return bool(result and result.get("ok"))


def _probe_output(result: Mapping[str, Any] | None) -> str:
    if not result:
        return ""
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    return stdout or stderr


def _first_line(value: str, *, max_chars: int = 512) -> str:
    line = next((item.strip() for item in str(value or "").splitlines() if item.strip()), "")
    return line[:max_chars]


def _parse_os_release(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _OS_RELEASE_NAME_RE.fullmatch(name):
            continue
        item = raw_value.strip()
        if len(item) >= 2 and item[0] == item[-1] and item[0] in {"'", '"'}:
            item = item[1:-1]
        if any(ord(char) < 32 or ord(char) == 127 for char in item):
            continue
        parsed[name] = item[:1024]
    return {
        "id": parsed.get("ID", ""),
        "name": parsed.get("NAME", ""),
        "version_id": parsed.get("VERSION_ID", ""),
        "version": parsed.get("VERSION", ""),
        "pretty_name": parsed.get("PRETTY_NAME", ""),
    }


def _parse_shells(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in str(value or "").splitlines():
        if "=" not in line:
            continue
        key, item = line.split("=", 1)
        key = key.strip().lower()
        if key in {"shell", "sh", "bash", "pwsh"}:
            parsed[key] = item.strip()[:1024]
    return parsed


def _summarize_checks(
    probe_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    for name, result in sorted(probe_results.items()):
        checks[name] = {
            "ok": bool(result.get("ok")),
            "exit_code": int(result.get("exit_code", 1)),
            "timed_out": bool(result.get("timed_out")),
            "duration_seconds": float(result.get("duration_seconds", 0.0)),
            "output_truncated": bool(result.get("output_truncated")),
            "error": str(result.get("error") or "")[:1024],
        }
    return checks


def build_capability_snapshot_payload(
    *,
    host_id: str,
    host_key_fingerprint: str,
    endpoint_route: str,
    environment_probe: Mapping[str, Any],
    capability_probe_results: Mapping[str, Mapping[str, Any]],
    required_capabilities: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_host_id = _normalize_host_id(host_id)
    normalized_fingerprint = _normalize_fingerprint(host_key_fingerprint)
    required = _normalize_required(required_capabilities)
    environment = dict(environment_probe.get("environment") or {})
    gpu = dict(environment_probe.get("gpu") or {})

    tools: dict[str, dict[str, Any]] = {}
    for name in sorted(_TOOL_PROBES):
        result = capability_probe_results.get(name) or {}
        tools[name] = {
            "available": _probe_ok(result),
            "version": _first_line(_probe_output(result)),
        }

    effective_uid_output = _first_line(
        _probe_output(capability_probe_results.get("effective_uid")), max_chars=32
    )
    root = effective_uid_output == "0"
    sudo_noninteractive = _probe_ok(
        capability_probe_results.get("sudo_noninteractive")
    )
    systemd = bool(tools.get("systemd", {}).get("available"))
    docker = bool(tools.get("docker", {}).get("available"))
    docker_compose = bool(tools.get("docker_compose", {}).get("available"))

    available_capabilities: dict[str, bool] = {
        "root": root,
        "passwordless_sudo": sudo_noninteractive,
        "systemd": systemd,
        "docker": docker,
        "docker_compose": docker_compose,
        "process_group_controls": bool(tools.get("setsid", {}).get("available")),
    }
    available_capabilities.update(
        {name: bool(item.get("available")) for name, item in tools.items()}
    )
    unknown_required = sorted(
        name for name in required if name not in available_capabilities
    )
    missing_required = sorted(
        name
        for name in required
        if name in available_capabilities and not available_capabilities[name]
    )
    required_ok = not unknown_required and not missing_required

    os_release = _parse_os_release(
        _probe_output(capability_probe_results.get("os_release"))
    )
    operating_system = {
        **os_release,
        "kernel": _first_line(
            _probe_output(capability_probe_results.get("kernel"))
        ),
        "architecture": _first_line(
            _probe_output(capability_probe_results.get("architecture"))
        ),
        "environment_summary": str(environment.get("os") or "")[:1024],
    }
    package_manager = _first_line(
        _probe_output(capability_probe_results.get("package_manager")),
        max_chars=128,
    )
    timezone = _first_line(
        _probe_output(capability_probe_results.get("timezone")), max_chars=128
    )
    locale_output = _probe_output(capability_probe_results.get("locale"))
    locale_first = _first_line(locale_output, max_chars=256)

    environment_ok = bool(environment_probe.get("ok"))
    status = "ok"
    if not environment_ok:
        status = "unavailable"
    elif not required_ok or str(environment_probe.get("status")) == "partial":
        status = "partial"

    return {
        "schema_version": SSH_CAPABILITY_SCHEMA_VERSION,
        "host_id": normalized_host_id,
        "host_key_fingerprint": normalized_fingerprint,
        "endpoint_route": str(endpoint_route or "").strip()[:128],
        "collected_at": _utc_now(),
        "status": status,
        "operating_system": operating_system,
        "identity": {
            "effective_uid": int(effective_uid_output)
            if effective_uid_output.isdigit()
            else None,
            "root": root,
            "passwordless_sudo": sudo_noninteractive,
        },
        "shells": _parse_shells(
            _probe_output(capability_probe_results.get("shells"))
        ),
        "package_manager": package_manager,
        "service_management": {
            "systemd": systemd,
            "supervisor": bool(tools.get("supervisor", {}).get("available")),
            "kubernetes_client": bool(tools.get("kubectl", {}).get("available")),
        },
        "tools": tools,
        "resources": {
            "system_memory": dict(environment.get("system_memory") or {}),
            "root_disk": dict(environment.get("root_disk") or {}),
            "gpu_available": bool(gpu.get("available")),
            "gpu_device_count": int(gpu.get("device_count") or 0),
            "gpu_devices": list(gpu.get("devices") or []),
        },
        "runtime": {
            "python": dict(environment.get("python") or {}),
            "torch": dict(environment.get("torch") or {}),
            "cuda_compiler": str(environment.get("cuda_compiler") or "")[:2048],
        },
        "environment": {
            "working_directory": str(environment.get("working_directory") or "")[:2048],
            "timezone": timezone,
            "locale": locale_first,
        },
        "process_group_controls": available_capabilities[
            "process_group_controls"
        ],
        "required_capabilities": list(required),
        "required_capabilities_ok": required_ok,
        "missing_required_capabilities": missing_required,
        "unknown_required_capabilities": unknown_required,
        "checks": _summarize_checks(capability_probe_results),
        "environment_probe_status": str(environment_probe.get("status") or ""),
        "error": ""
        if environment_ok and required_ok
        else "Capability discovery or required-capability validation was incomplete",
    }


def _canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _snapshot_directory(runs_dir: Path, host_id: str) -> Path:
    normalized_host_id = _normalize_host_id(host_id)
    return (
        Path(runs_dir).resolve()
        / SSH_CAPABILITIES_DIR
        / normalized_host_id
    ).resolve()


def persist_capability_snapshot(
    runs_dir: Path,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    host_id = _normalize_host_id(str(payload.get("host_id") or ""))
    if payload.get("schema_version") != SSH_CAPABILITY_SCHEMA_VERSION:
        raise ValueError("SSH capability payload schema version is invalid")
    snapshot_id = _make_snapshot_id()
    snapshot_hash = _canonical_payload_hash(payload)
    record = {
        **dict(payload),
        "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot_hash,
    }
    path = _snapshot_directory(Path(runs_dir), host_id) / f"{snapshot_id}.json"
    atomic_write_json(path, record)
    return capability_snapshot_projection(record)


def _snapshot_path(runs_dir: Path, host_id: str, snapshot_id: str) -> Path:
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError("Invalid SSH capability snapshot_id")
    root = _snapshot_directory(Path(runs_dir), host_id)
    path = (root / f"{snapshot_id}.json").resolve()
    path.relative_to(root)
    return path


def read_capability_snapshot(
    runs_dir: Path,
    *,
    host_id: str,
    snapshot_id: str,
) -> dict[str, Any]:
    path = _snapshot_path(Path(runs_dir), host_id, snapshot_id)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Unknown SSH capability snapshot_id")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("SSH capability snapshot is invalid") from exc
    if record.get("snapshot_id") != snapshot_id:
        raise ValueError("SSH capability snapshot ID mismatch")
    expected = str(record.get("snapshot_sha256") or "")
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"snapshot_id", "snapshot_sha256"}
    }
    if _canonical_payload_hash(payload) != expected:
        raise ValueError("SSH capability snapshot hash mismatch")
    return record


def capability_snapshot_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    tools = dict(record.get("tools") or {})
    available_tools = sorted(
        name for name, item in tools.items() if bool(dict(item).get("available"))
    )
    resources = dict(record.get("resources") or {})
    operating_system = dict(record.get("operating_system") or {})
    identity = dict(record.get("identity") or {})
    return {
        "ok": bool(record.get("required_capabilities_ok"))
        and str(record.get("status")) != "unavailable",
        "snapshot_id": str(record.get("snapshot_id") or ""),
        "snapshot_sha256": str(record.get("snapshot_sha256") or ""),
        "schema_version": str(record.get("schema_version") or ""),
        "host_id": str(record.get("host_id") or ""),
        "host_key_fingerprint": str(record.get("host_key_fingerprint") or ""),
        "endpoint_route": str(record.get("endpoint_route") or ""),
        "collected_at": str(record.get("collected_at") or ""),
        "status": str(record.get("status") or ""),
        "operating_system": {
            "pretty_name": str(operating_system.get("pretty_name") or ""),
            "kernel": str(operating_system.get("kernel") or ""),
            "architecture": str(operating_system.get("architecture") or ""),
        },
        "identity": {
            "root": bool(identity.get("root")),
            "passwordless_sudo": bool(identity.get("passwordless_sudo")),
        },
        "package_manager": str(record.get("package_manager") or ""),
        "available_tools": available_tools,
        "memory_total_bytes": int(
            dict(resources.get("system_memory") or {}).get("total_bytes") or 0
        ),
        "root_disk_free_bytes": int(
            dict(resources.get("root_disk") or {}).get("free_bytes") or 0
        ),
        "gpu_available": bool(resources.get("gpu_available")),
        "gpu_device_count": int(resources.get("gpu_device_count") or 0),
        "required_capabilities": list(record.get("required_capabilities") or []),
        "required_capabilities_ok": bool(
            record.get("required_capabilities_ok")
        ),
        "missing_required_capabilities": list(
            record.get("missing_required_capabilities") or []
        ),
        "unknown_required_capabilities": list(
            record.get("unknown_required_capabilities") or []
        ),
        "error": str(record.get("error") or ""),
    }
