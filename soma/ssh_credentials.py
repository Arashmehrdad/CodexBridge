from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping
from uuid import uuid4

from .config import SSHHostConfig
from .dotenv import ENV_NAME_RE, read_dotenv_file
from .return_loop.atomic_writer import atomic_write_json
from .ssh_commands import resolve_ssh_connection

SSH_CREDENTIAL_SOURCE_TYPES = frozenset(
    {
        "auto",
        "env_file",
        "process_environment",
        "openssh_config",
        "connection_file",
        "key_file",
    }
)
SSH_CREDENTIAL_FIELDS = (
    "hostname",
    "user",
    "port",
    "identity_file",
    "expected_host_key",
)
SSH_REQUIRED_CREDENTIAL_FIELDS = frozenset({"hostname", "user", "identity_file"})
SSH_CREDENTIAL_PROBES_DIR = "ssh_credential_sources"
MAX_SSH_CREDENTIAL_SOURCE_BYTES = 65_536
MAX_SSH_PRIVATE_KEY_BYTES = 1_048_576

_PROBE_ID_RE = re.compile(r"^\d{8}T\d{6}Z_sshcred_[0-9a-f]{8}$")
_SAFE_HINT_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_USER_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/=]+$")
_PRIVATE_KEY_HEADER_RE = re.compile(
    rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"
)
_OPENSSH_HOST_RE = re.compile(r"^\s*Host\s+(?P<aliases>.+?)\s*$", re.IGNORECASE)

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "hostname": ("SSH_HOST", "SSH_HOSTNAME", "HOST", "HOSTNAME"),
    "user": ("SSH_USER", "SSH_USERNAME", "USER", "USERNAME"),
    "port": ("SSH_PORT", "PORT"),
    "identity_file": (
        "SSH_KEY_PATH",
        "SSH_IDENTITY_FILE",
        "SSH_PRIVATE_KEY_PATH",
        "IDENTITY_FILE",
        "PRIVATE_KEY_PATH",
        "KEY_PATH",
    ),
    "expected_host_key": (
        "SSH_HOST_KEY",
        "SSH_HOST_FINGERPRINT",
        "EXPECTED_HOST_KEY",
        "HOST_KEY",
        "HOST_FINGERPRINT",
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_probe_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_sshcred_{uuid4().hex[:8]}"


def _probe_manifest_path(runs_dir: Path, probe_id: str) -> Path:
    if not _PROBE_ID_RE.fullmatch(probe_id):
        raise ValueError(f"Invalid SSH credential probe_id: {probe_id!r}")
    root = (Path(runs_dir) / SSH_CREDENTIAL_PROBES_DIR).resolve()
    path = (root / probe_id / "manifest.json").resolve()
    path.relative_to(root)
    return path


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _normalize_source_type(source_type: str) -> str:
    normalized = str(source_type or "auto").strip().lower()
    if normalized not in SSH_CREDENTIAL_SOURCE_TYPES:
        raise ValueError(
            f"Unsupported SSH credential source_type: {source_type!r}. "
            f"Allowed: {sorted(SSH_CREDENTIAL_SOURCE_TYPES)}"
        )
    return normalized


def _normalize_hint(host_hint: str) -> str:
    hint = str(host_hint or "").strip()
    if hint and not _SAFE_HINT_RE.fullmatch(hint):
        raise ValueError("SSH credential host_hint contains unsupported characters")
    return hint.upper().replace("-", "_")


def _normalize_field_overrides(
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_field, raw_name in dict(overrides or {}).items():
        field = str(raw_field or "").strip()
        name = str(raw_name or "").strip()
        if field not in SSH_CREDENTIAL_FIELDS:
            raise ValueError(f"Unsupported SSH credential field override: {field!r}")
        if not ENV_NAME_RE.fullmatch(name):
            raise ValueError(
                f"SSH credential override for {field!r} must name one environment variable"
            )
        normalized[field] = name
    return normalized


def _normalize_absolute_path(value: str, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw or len(raw) > 2048 or _has_control_characters(raw):
        raise ValueError(f"{label} must be a bounded absolute path")
    candidate = Path(raw).expanduser()
    if not (candidate.is_absolute() or PureWindowsPath(raw).is_absolute()):
        raise ValueError(f"{label} must be an absolute path")
    return candidate


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _read_regular_file(path_value: str, *, label: str, max_bytes: int) -> tuple[Path, bytes]:
    candidate = _normalize_absolute_path(path_value, label)
    if candidate.is_symlink() or _is_reparse_point(candidate) or not candidate.is_file():
        raise ValueError(f"{label} is missing or not a regular non-link file")
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        raise ValueError(f"{label} metadata could not be read") from exc
    if size > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} bytes")
    try:
        data = candidate.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} could not be read") from exc
    return candidate.resolve(strict=True), data


def _find_git_root(path: Path) -> Path | None:
    for parent in (path.parent, *path.parents):
        if (parent / ".git").exists():
            return parent
    return None


def _git_hygiene(path: Path) -> dict[str, Any]:
    root = _find_git_root(path)
    if root is None:
        return {
            "inside_git_repository": False,
            "tracked": False,
            "ignored": False,
            "ok": True,
            "reason": "outside_git_repository",
        }
    executable = shutil.which("git")
    if not executable:
        return {
            "inside_git_repository": True,
            "tracked": False,
            "ignored": False,
            "ok": False,
            "reason": "git_hygiene_could_not_be_verified",
        }
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return {
            "inside_git_repository": True,
            "tracked": False,
            "ignored": False,
            "ok": False,
            "reason": "git_path_identity_mismatch",
        }
    tracked = subprocess.run(
        [executable, "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).returncode == 0
    ignored = subprocess.run(
        [executable, "-C", str(root), "check-ignore", "-q", "--", relative],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).returncode == 0
    if tracked:
        reason = "secret_source_is_git_tracked"
    elif not ignored:
        reason = "secret_source_inside_git_is_not_ignored"
    else:
        reason = "secret_source_is_git_ignored"
    return {
        "inside_git_repository": True,
        "tracked": tracked,
        "ignored": ignored,
        "ok": not tracked and ignored,
        "reason": reason,
    }


def _windows_acl_posture(path: Path) -> dict[str, Any]:
    if os.name != "nt":
        mode = path.stat().st_mode
        broad_write = bool(mode & 0o022)
        broad_read = bool(mode & 0o004)
        return {
            "checked": True,
            "broad_write": broad_write,
            "broad_read": broad_read,
            "ok": not broad_write,
            "reason": "broad_write_access" if broad_write else "ok",
        }
    executable = shutil.which("icacls")
    if not executable:
        return {
            "checked": False,
            "broad_write": False,
            "broad_read": False,
            "ok": True,
            "reason": "acl_tool_unavailable",
        }
    try:
        result = subprocess.run(
            [executable, str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "checked": False,
            "broad_write": False,
            "broad_read": False,
            "ok": True,
            "reason": "acl_check_failed",
        }
    text = result.stdout.lower()
    broad_principals = ("everyone:", "builtin\\users:", "authenticated users:")
    broad_lines = [line for line in text.splitlines() if any(item in line for item in broad_principals)]
    broad_write = any(any(marker in line for marker in ("(f)", "(m)", "(w)")) for line in broad_lines)
    broad_read = bool(broad_lines)
    return {
        "checked": result.returncode == 0,
        "broad_write": broad_write,
        "broad_read": broad_read,
        "ok": not broad_write,
        "reason": "broad_write_access" if broad_write else "ok",
    }


def _file_security(path: Path) -> dict[str, Any]:
    git = _git_hygiene(path)
    acl = _windows_acl_posture(path)
    refusals: list[str] = []
    warnings: list[str] = []
    if not git["ok"]:
        refusals.append(str(git["reason"]))
    if not acl["ok"]:
        refusals.append(str(acl["reason"]))
    elif acl["broad_read"]:
        warnings.append("broad_read_access_detected")
    if not acl["checked"]:
        warnings.append(str(acl["reason"]))
    return {
        "ok": not refusals,
        "git": git,
        "acl": acl,
        "refusals": sorted(set(refusals)),
        "warnings": sorted(set(warnings)),
    }


def _opaque_path_identity(path: Path) -> str:
    normalized = os.path.normcase(os.path.normpath(str(path)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _file_version_identity(path: Path, data: bytes) -> str:
    stat_result = path.stat()
    digest = hashlib.sha256()
    digest.update(data)
    digest.update(str(stat_result.st_size).encode("ascii"))
    digest.update(str(stat_result.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _key_fingerprint(path: Path) -> tuple[str, str]:
    executable = shutil.which("ssh-keygen")
    if not executable:
        return "", "ssh_keygen_unavailable"
    try:
        result = subprocess.run(
            [executable, "-lf", str(path), "-E", "sha256"],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", "ssh_keygen_failed"
    if result.returncode != 0:
        return "", "key_fingerprint_unavailable"
    tokens = result.stdout.strip().split()
    fingerprint = next((token for token in tokens if token.startswith("SHA256:")), "")
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        return "", "key_fingerprint_unavailable"
    return fingerprint, ""


def _inspect_key_path(path_value: str) -> dict[str, Any]:
    path, data = _read_regular_file(
        path_value,
        label="SSH private-key path",
        max_bytes=MAX_SSH_PRIVATE_KEY_BYTES,
    )
    security = _file_security(path)
    fingerprint, fingerprint_error = _key_fingerprint(path)
    refusals = list(security["refusals"])
    warnings = list(security["warnings"])
    if fingerprint_error:
        refusals.append(fingerprint_error)
    return {
        "ok": not refusals,
        "basename": path.name,
        "size_bytes": len(data),
        "path_identity_sha256": _opaque_path_identity(path),
        "file_version_sha256": _file_version_identity(path, data),
        "public_key_fingerprint": fingerprint,
        "security": security,
        "refusals": sorted(set(refusals)),
        "warnings": sorted(set(warnings)),
    }


def _candidate_score(variable: str, field: str, hint: str) -> int:
    upper = variable.upper()
    stripped = upper
    score = 0
    if hint and upper.startswith(hint + "_"):
        stripped = upper[len(hint) + 1 :]
        score += 1000
    aliases = _FIELD_ALIASES[field]
    if stripped in aliases:
        score += 500 - aliases.index(stripped)
    elif upper in aliases:
        score += 250 - aliases.index(upper)
    else:
        suffixes = tuple("_" + alias for alias in aliases)
        if any(upper.endswith(suffix) for suffix in suffixes):
            score += 100
    return score


def _map_environment_fields(
    names: list[str],
    *,
    hint: str,
    overrides: dict[str, str],
) -> tuple[dict[str, str], dict[str, list[str]], list[str], dict[str, list[str]]]:
    available = set(names)
    mapping: dict[str, str] = {}
    candidates: dict[str, list[str]] = {}
    ambiguous: dict[str, list[str]] = {}
    for field in SSH_CREDENTIAL_FIELDS:
        override = overrides.get(field)
        if override:
            if override not in available:
                raise ValueError(
                    f"SSH credential override for {field!r} names an unavailable variable"
                )
            mapping[field] = override
            candidates[field] = [override]
            continue
        scored = sorted(
            (
                (_candidate_score(name, field, hint), name)
                for name in names
                if _candidate_score(name, field, hint) > 0
            ),
            key=lambda item: (-item[0], item[1]),
        )
        candidates[field] = [name for _score, name in scored]
        if not scored:
            continue
        best_score = scored[0][0]
        best = [name for score, name in scored if score == best_score]
        if len(best) == 1:
            mapping[field] = best[0]
        else:
            ambiguous[field] = best
    missing = sorted(SSH_REQUIRED_CREDENTIAL_FIELDS - set(mapping) - set(ambiguous))
    return mapping, candidates, missing, ambiguous


def _validate_resolved_values(
    values: Mapping[str, str], mapping: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    endpoint = {
        "hostname_valid": False,
        "user_valid": False,
        "port_valid": True,
        "expected_host_key_valid": True,
    }
    key_result: dict[str, Any] = {}
    hostname_name = mapping.get("hostname", "")
    user_name = mapping.get("user", "")
    port_name = mapping.get("port", "")
    key_name = mapping.get("identity_file", "")
    fingerprint_name = mapping.get("expected_host_key", "")

    if hostname_name:
        endpoint["hostname_valid"] = bool(
            _HOSTNAME_RE.fullmatch(str(values.get(hostname_name, "")).strip())
        )
    if user_name:
        endpoint["user_valid"] = bool(
            _USER_RE.fullmatch(str(values.get(user_name, "")).strip())
        )
    if port_name:
        raw_port = str(values.get(port_name, "")).strip()
        endpoint["port_valid"] = raw_port.isdigit() and 1 <= int(raw_port) <= 65535
    if fingerprint_name:
        endpoint["expected_host_key_valid"] = bool(
            _FINGERPRINT_RE.fullmatch(str(values.get(fingerprint_name, "")).strip())
        )
    if key_name:
        try:
            key_result = _inspect_key_path(str(values.get(key_name, "")))
        except ValueError as exc:
            key_result = {
                "ok": False,
                "basename": "",
                "size_bytes": 0,
                "path_identity_sha256": "",
                "file_version_sha256": "",
                "public_key_fingerprint": "",
                "security": {},
                "refusals": [str(exc)],
                "warnings": [],
            }
    return endpoint, key_result


def _detect_source_type(path: Path, data: bytes) -> str:
    lowered_name = path.name.lower()
    if lowered_name.endswith((".env", ".dotenv")) or ".env." in lowered_name:
        return "env_file"
    if _PRIVATE_KEY_HEADER_RE.search(data[:4096]):
        return "key_file"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("SSH credential source type could not be detected") from exc
    logical = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if logical and logical[0].startswith("ssh "):
        return "connection_file"
    if any(_OPENSSH_HOST_RE.match(line) for line in logical):
        return "openssh_config"
    if logical and all("=" in line.removeprefix("export ") for line in logical):
        return "env_file"
    if lowered_name.endswith((".pem", ".key")) or lowered_name.startswith("id_"):
        return "key_file"
    raise ValueError("SSH credential source type could not be detected")


def _parse_openssh_config(text: str, alias_hint: str) -> dict[str, str]:
    blocks: dict[str, dict[str, str]] = {}
    current: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        host_match = _OPENSSH_HOST_RE.match(raw_line)
        if host_match:
            aliases = [item for item in host_match.group("aliases").split() if item]
            current = [item for item in aliases if not any(char in item for char in "*?!")]
            for alias in current:
                blocks.setdefault(alias, {})
            continue
        if not current:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].lower(), parts[1].strip()
        if key not in {"hostname", "user", "port", "identityfile"}:
            continue
        for alias in current:
            blocks[alias].setdefault(key, value)

    selected = alias_hint
    if selected:
        exact = next((alias for alias in blocks if alias.lower() == selected.lower()), "")
        if not exact:
            raise ValueError("OpenSSH source does not contain the requested alias")
        selected = exact
    elif len(blocks) == 1:
        selected = next(iter(blocks))
    else:
        raise ValueError("OpenSSH source requires an unambiguous host_hint alias")
    values = blocks[selected]
    return {
        "alias": selected,
        "hostname": values.get("hostname", selected),
        "user": values.get("user", ""),
        "port": values.get("port", "22"),
        "identity_file": values.get("identityfile", ""),
    }


def _probe_env_values(
    values: Mapping[str, str],
    *,
    source_type: str,
    hint: str,
    overrides: dict[str, str],
) -> dict[str, Any]:
    names = sorted(values)
    mapping, candidates, missing, ambiguous = _map_environment_fields(
        names,
        hint=hint,
        overrides=overrides,
    )
    endpoint, key_result = _validate_resolved_values(values, mapping)
    refusals: list[str] = []
    if mapping.get("hostname") and not endpoint["hostname_valid"]:
        refusals.append("hostname_value_invalid")
    if mapping.get("user") and not endpoint["user_valid"]:
        refusals.append("user_value_invalid")
    if not endpoint["port_valid"]:
        refusals.append("port_value_invalid")
    if not endpoint["expected_host_key_valid"]:
        refusals.append("expected_host_key_invalid")
    refusals.extend(key_result.get("refusals") or [])
    return {
        "source_type": source_type,
        "discovered_names": names,
        "field_mapping": mapping,
        "field_candidates": candidates,
        "missing_fields": missing,
        "ambiguous_fields": ambiguous,
        "endpoint_validation": endpoint,
        "key_file": key_result,
        "refusals": sorted(set(refusals)),
        "warnings": sorted(set(key_result.get("warnings") or [])),
    }


def probe_ssh_credential_source(
    runs_dir: Path,
    *,
    source_path: str = "",
    source_type: str = "auto",
    host_hint: str = "",
    field_overrides: Mapping[str, str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect one local credential source and return only sanitized metadata."""

    normalized_type = _normalize_source_type(source_type)
    hint = _normalize_hint(host_hint)
    overrides = _normalize_field_overrides(field_overrides)
    probe_id = _make_probe_id()
    source_reference = ""
    source_basename = ""
    source_path_identity = ""
    source_version_identity = ""
    source_security: dict[str, Any] = {}
    details: dict[str, Any]

    if normalized_type == "process_environment":
        if source_path:
            raise ValueError("process_environment credential sources do not accept source_path")
        all_values = dict(os.environ if environment is None else environment)
        allowed_names = set(overrides.values())
        if hint:
            allowed_names.update(name for name in all_values if name.upper().startswith(hint + "_"))
        for aliases in _FIELD_ALIASES.values():
            allowed_names.update(name for name in aliases if name in all_values)
        selected_values = {name: all_values[name] for name in sorted(allowed_names) if name in all_values}
        if not selected_values:
            raise ValueError("No scoped SSH credential variables were found in the process environment")
        source_version_identity = hashlib.sha256(
            json.dumps(selected_values, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        details = _probe_env_values(
            selected_values,
            source_type=normalized_type,
            hint=hint,
            overrides=overrides,
        )
    else:
        path, data = _read_regular_file(
            source_path,
            label="SSH credential source",
            max_bytes=(
                MAX_SSH_PRIVATE_KEY_BYTES
                if normalized_type == "key_file"
                else MAX_SSH_CREDENTIAL_SOURCE_BYTES
            ),
        )
        source_reference = str(path)
        source_basename = path.name
        source_path_identity = _opaque_path_identity(path)
        source_version_identity = _file_version_identity(path, data)
        source_security = _file_security(path)
        if normalized_type == "auto":
            normalized_type = _detect_source_type(path, data)

        if normalized_type == "env_file":
            values = read_dotenv_file(
                path,
                label="SSH credential env_file",
                max_bytes=MAX_SSH_CREDENTIAL_SOURCE_BYTES,
            )
            details = _probe_env_values(
                values,
                source_type=normalized_type,
                hint=hint,
                overrides=overrides,
            )
        elif normalized_type == "connection_file":
            connection = resolve_ssh_connection(SSHHostConfig(connection_file=str(path)))
            user, hostname = connection.destination.split("@", 1)
            key_result = _inspect_key_path(connection.identity_file)
            details = {
                "source_type": normalized_type,
                "discovered_names": [],
                "field_mapping": {
                    "hostname": "connection_file:hostname",
                    "user": "connection_file:user",
                    "port": "connection_file:port",
                    "identity_file": "connection_file:identity_file",
                },
                "field_candidates": {},
                "missing_fields": [],
                "ambiguous_fields": {},
                "endpoint_validation": {
                    "hostname_valid": bool(_HOSTNAME_RE.fullmatch(hostname)),
                    "user_valid": bool(_USER_RE.fullmatch(user)),
                    "port_valid": 1 <= int(connection.port) <= 65535,
                    "expected_host_key_valid": True,
                },
                "key_file": key_result,
                "refusals": list(key_result.get("refusals") or []),
                "warnings": list(key_result.get("warnings") or []),
            }
        elif normalized_type == "key_file":
            key_result = _inspect_key_path(str(path))
            details = {
                "source_type": normalized_type,
                "discovered_names": [],
                "field_mapping": {"identity_file": "key_file"},
                "field_candidates": {},
                "missing_fields": ["hostname", "user"],
                "ambiguous_fields": {},
                "endpoint_validation": {
                    "hostname_valid": False,
                    "user_valid": False,
                    "port_valid": True,
                    "expected_host_key_valid": True,
                },
                "key_file": key_result,
                "refusals": list(key_result.get("refusals") or []),
                "warnings": list(key_result.get("warnings") or []),
            }
        elif normalized_type == "openssh_config":
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("OpenSSH credential source must be UTF-8 text") from exc
            parsed = _parse_openssh_config(text, str(host_hint or "").strip())
            identity_value = str(Path(parsed["identity_file"]).expanduser())
            key_result = _inspect_key_path(identity_value) if parsed["identity_file"] else {}
            missing = [field for field in ("user", "identity_file") if not parsed[field]]
            details = {
                "source_type": normalized_type,
                "discovered_names": [parsed["alias"]],
                "field_mapping": {
                    "hostname": "OpenSSH:HostName",
                    "user": "OpenSSH:User",
                    "port": "OpenSSH:Port",
                    "identity_file": "OpenSSH:IdentityFile",
                },
                "field_candidates": {},
                "missing_fields": missing,
                "ambiguous_fields": {},
                "endpoint_validation": {
                    "hostname_valid": bool(_HOSTNAME_RE.fullmatch(parsed["hostname"])),
                    "user_valid": bool(_USER_RE.fullmatch(parsed["user"])),
                    "port_valid": parsed["port"].isdigit() and 1 <= int(parsed["port"]) <= 65535,
                    "expected_host_key_valid": True,
                },
                "key_file": key_result,
                "refusals": list(key_result.get("refusals") or []),
                "warnings": list(key_result.get("warnings") or []),
            }
        else:  # pragma: no cover - normalized source types are exhaustive
            raise ValueError(f"Unsupported SSH credential source_type: {normalized_type}")

    refusals = list(details.get("refusals") or [])
    warnings = list(details.get("warnings") or [])
    if source_security:
        refusals.extend(source_security.get("refusals") or [])
        warnings.extend(source_security.get("warnings") or [])
    missing = list(details.get("missing_fields") or [])
    ambiguous = dict(details.get("ambiguous_fields") or {})
    ready = not refusals and not missing and not ambiguous

    public = {
        "ok": not refusals,
        "probe_id": probe_id,
        "status": "ready" if ready else ("refused" if refusals else "incomplete"),
        "ready_for_binding": ready,
        "source_type": normalized_type,
        "source_basename": source_basename,
        "source_path_identity_sha256": source_path_identity,
        "source_version_sha256": source_version_identity,
        "source_security": source_security,
        "discovered_names": details.get("discovered_names") or [],
        "field_mapping": details.get("field_mapping") or {},
        "field_candidates": details.get("field_candidates") or {},
        "missing_fields": missing,
        "ambiguous_fields": ambiguous,
        "endpoint_validation": details.get("endpoint_validation") or {},
        "key_file": details.get("key_file") or {},
        "refusals": sorted(set(str(item) for item in refusals)),
        "warnings": sorted(set(str(item) for item in warnings)),
        "created_at": _utc_now(),
        "error": "",
    }
    manifest = {
        **public,
        "source_reference": source_reference,
        "field_overrides": overrides,
        "host_hint": str(host_hint or "").strip(),
        "schema_version": "ssh-credential-probe.v1",
    }
    atomic_write_json(_probe_manifest_path(Path(runs_dir), probe_id), manifest)
    return public
