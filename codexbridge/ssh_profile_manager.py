from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import yaml

from .config import AppConfig, SSHCommandProfileConfig, SSHHostConfig
from .return_loop.atomic_writer import atomic_write_json, atomic_write_text
from .ssh_commands import (
    list_ssh_capabilities,
    validate_ssh_command_profile,
    validate_ssh_host_id,
)


SSH_PROFILE_CHANGE_ACTIONS = frozenset(
    {
        "add_host",
        "replace_host",
        "remove_host",
        "upsert_command",
        "remove_command",
    }
)
SSH_PROFILE_CHANGES_DIR = "ssh_profile_changes"
_CHANGE_ID_RE = re.compile(r"^\d{8}T\d{6}Z_sshcfg_[0-9a-f]{8}$")
_TOP_LEVEL_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)")

ActivationCallback = Callable[[Path], dict[str, Any] | None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_change_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_sshcfg_{uuid4().hex[:8]}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _config_fingerprint(config_path: Path) -> str:
    normalized = os.path.normcase(os.path.normpath(str(config_path.resolve())))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _manifest_path(runs_dir: Path, change_id: str) -> Path:
    if not _CHANGE_ID_RE.fullmatch(change_id):
        raise ValueError(f"Invalid SSH profile change_id: {change_id!r}")
    root = (runs_dir / SSH_PROFILE_CHANGES_DIR).resolve()
    path = (root / change_id / "manifest.json").resolve()
    path.relative_to(root)
    return path


def _read_manifest(runs_dir: Path, change_id: str) -> tuple[Path, dict[str, Any]]:
    path = _manifest_path(runs_dir, change_id)
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise ValueError(f"Unknown SSH profile change_id: {change_id}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("change_id") != change_id:
        raise ValueError("SSH profile change manifest ID mismatch")
    return path, manifest


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(path, manifest)


def _validate_repositories(config: AppConfig) -> None:
    for name, repo in config.repos.items():
        repo_path = Path(repo.path).resolve()
        if not repo_path.exists():
            raise ValueError(f"Repo '{name}' path does not exist: {repo_path}")
        if not (repo_path / ".git").exists():
            raise ValueError(f"Repo '{name}' path does not contain .git: {repo_path}")


def _config_from_data(data: dict[str, Any], config_path: Path) -> AppConfig:
    config = AppConfig(**data, config_dir=config_path.parent)
    _validate_repositories(config)
    return config


def _load_document(config_path: Path, raw_bytes: bytes) -> tuple[str, dict[str, Any], AppConfig]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("CodexBridge config must be UTF-8 text") from exc
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise ValueError("CodexBridge config root must be a YAML mapping")
    data = copy.deepcopy(loaded)
    return text, data, _config_from_data(data, config_path)


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _replace_top_level_ssh_block(text: str, ssh_data: dict[str, Any]) -> str:
    newline = _newline_for(text)
    rendered = yaml.safe_dump(
        {"ssh": ssh_data},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    if newline != "\n":
        rendered = rendered.replace("\n", newline)

    lines = text.splitlines(keepends=True)
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        logical = line.rstrip("\r\n")
        if logical.startswith((" ", "\t", "#")) or not logical.strip():
            continue
        match = _TOP_LEVEL_KEY_RE.match(logical)
        if match and match.group("key") == "ssh":
            start = index
            break
    if start is None:
        prefix = text
        if prefix and not prefix.endswith(("\n", "\r")):
            prefix += newline
        return prefix + rendered

    for index in range(start + 1, len(lines)):
        logical = lines[index].rstrip("\r\n")
        if logical.startswith((" ", "\t", "#")) or not logical.strip():
            continue
        if _TOP_LEVEL_KEY_RE.match(logical):
            end = index
            break
    return "".join(lines[:start]) + rendered + "".join(lines[end:])


def _reject_extra_fields(payload: dict[str, Any], allowed: set[str], label: str) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        raise ValueError(f"Unsupported {label} fields: {extras}")


def _normalized_host(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("host_config is required for this action")
    _reject_extra_fields(payload, set(SSHHostConfig.model_fields), "host_config")
    host = SSHHostConfig.model_validate(payload)
    for profile in host.command_profiles:
        validate_ssh_command_profile(profile)
    return host.model_dump(mode="python")


def _normalized_command(
    command_id: str, payload: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not payload:
        raise ValueError("command_profile is required for upsert_command")
    _reject_extra_fields(
        payload, set(SSHCommandProfileConfig.model_fields), "command_profile"
    )
    candidate = dict(payload)
    payload_id = str(candidate.get("command_id") or "").strip()
    requested_id = str(command_id or "").strip()
    if requested_id and payload_id and requested_id != payload_id:
        raise ValueError("command_id does not match command_profile.command_id")
    effective_id = requested_id or payload_id
    if not effective_id:
        raise ValueError("command_id is required for upsert_command")
    candidate["command_id"] = effective_id
    profile = SSHCommandProfileConfig.model_validate(candidate)
    validate_ssh_command_profile(profile)
    return effective_id, profile.model_dump(mode="python")


def _normalize_mutation(
    action: str,
    host_id: str,
    host_config: dict[str, Any] | None,
    command_id: str,
    command_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    if normalized_action not in SSH_PROFILE_CHANGE_ACTIONS:
        raise ValueError(
            f"Unsupported SSH profile action: {action!r}. "
            f"Allowed: {sorted(SSH_PROFILE_CHANGE_ACTIONS)}"
        )
    normalized_host_id = validate_ssh_host_id(host_id)
    mutation: dict[str, Any] = {
        "action": normalized_action,
        "host_id": normalized_host_id,
        "host_config": {},
        "command_id": "",
        "command_profile": {},
    }
    if normalized_action in {"add_host", "replace_host"}:
        mutation["host_config"] = _normalized_host(host_config or {})
        if command_id or command_profile:
            raise ValueError("Host actions do not accept command fields")
    elif normalized_action == "upsert_command":
        effective_id, normalized_profile = _normalized_command(
            command_id, command_profile or {}
        )
        mutation["command_id"] = effective_id
        mutation["command_profile"] = normalized_profile
        if host_config:
            raise ValueError("Command actions do not accept host_config")
    elif normalized_action == "remove_command":
        effective_id = str(command_id or "").strip()
        if not effective_id:
            raise ValueError("command_id is required for remove_command")
        validate_ssh_command_profile(
            SSHCommandProfileConfig(command_id=effective_id, argv=["true"])
        )
        mutation["command_id"] = effective_id
        if host_config or command_profile:
            raise ValueError("remove_command accepts only host_id and command_id")
    else:
        if host_config or command_id or command_profile:
            raise ValueError("remove_host accepts only host_id")
    return mutation


def _apply_mutation(data: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(data)
    ssh_data = candidate.setdefault("ssh", {})
    if not isinstance(ssh_data, dict):
        raise ValueError("Top-level ssh configuration must be a mapping")
    hosts = ssh_data.setdefault("hosts", {})
    if not isinstance(hosts, dict):
        raise ValueError("ssh.hosts must be a mapping")

    action = mutation["action"]
    host_id = mutation["host_id"]
    exists = host_id in hosts
    if action == "add_host":
        if exists:
            raise ValueError(f"SSH host already exists: {host_id}")
        hosts[host_id] = _normalized_host(dict(mutation["host_config"]))
    elif action == "replace_host":
        if not exists:
            raise ValueError(f"Unknown SSH host_id: {host_id}")
        hosts[host_id] = _normalized_host(dict(mutation["host_config"]))
    elif action == "remove_host":
        if not exists:
            raise ValueError(f"Unknown SSH host_id: {host_id}")
        del hosts[host_id]
    else:
        if not exists:
            raise ValueError(f"Unknown SSH host_id: {host_id}")
        raw_host = hosts[host_id]
        if not isinstance(raw_host, dict):
            raise ValueError(f"SSH host configuration must be a mapping: {host_id}")
        profiles = raw_host.setdefault("command_profiles", [])
        if not isinstance(profiles, list):
            raise ValueError(f"SSH host command_profiles must be a list: {host_id}")
        command_id = mutation["command_id"]
        matching = [
            index
            for index, item in enumerate(profiles)
            if isinstance(item, dict) and str(item.get("command_id") or "") == command_id
        ]
        if len(matching) > 1:
            raise ValueError(
                f"Duplicate SSH command_id for host '{host_id}': {command_id}"
            )
        if action == "upsert_command":
            _effective_id, replacement = _normalized_command(
                command_id, dict(mutation["command_profile"])
            )
            if matching:
                profiles[matching[0]] = replacement
            else:
                profiles.append(replacement)
        elif action == "remove_command":
            if not matching:
                raise ValueError(
                    f"Unknown SSH command_id for host '{host_id}': {command_id}"
                )
            del profiles[matching[0]]
    return candidate


def _capability_host_map(config: AppConfig) -> dict[str, dict[str, Any]]:
    listing = list_ssh_capabilities(config)
    return {str(item["host_id"]): item for item in listing.get("hosts", [])}


def _command_map(host: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not host:
        return {}
    return {
        str(item["command_id"]): item
        for item in host.get("commands", [])
        if isinstance(item, dict) and item.get("command_id")
    }


def _capability_diff(
    before_config: AppConfig, after_config: AppConfig
) -> dict[str, Any]:
    before = _capability_host_map(before_config)
    after = _capability_host_map(after_config)
    before_ids = set(before)
    after_ids = set(after)
    changed: list[dict[str, Any]] = []
    for host_id in sorted(before_ids & after_ids):
        if before[host_id] == after[host_id]:
            continue
        old_commands = _command_map(before[host_id])
        new_commands = _command_map(after[host_id])
        shared = set(old_commands) & set(new_commands)
        changed.append(
            {
                "host_id": host_id,
                "before": before[host_id],
                "after": after[host_id],
                "commands_added": sorted(set(new_commands) - set(old_commands)),
                "commands_removed": sorted(set(old_commands) - set(new_commands)),
                "commands_changed": sorted(
                    command_id
                    for command_id in shared
                    if old_commands[command_id] != new_commands[command_id]
                ),
            }
        )
    return {
        "hosts_added": sorted(after_ids - before_ids),
        "hosts_removed": sorted(before_ids - after_ids),
        "hosts_changed": changed,
    }


def _build_candidate(
    config_path: Path,
    base_bytes: bytes,
    mutation: dict[str, Any],
) -> tuple[str, AppConfig, dict[str, Any]]:
    base_text, data, current_config = _load_document(config_path, base_bytes)
    candidate_data = _apply_mutation(data, mutation)
    ssh_data = candidate_data.get("ssh")
    if not isinstance(ssh_data, dict):
        raise ValueError("Candidate ssh configuration must be a mapping")
    candidate_text = _replace_top_level_ssh_block(base_text, ssh_data)
    reparsed = yaml.safe_load(candidate_text) or {}
    if not isinstance(reparsed, dict):
        raise ValueError("Candidate config root must be a YAML mapping")
    candidate_config = _config_from_data(reparsed, config_path)
    capability_diff = _capability_diff(current_config, candidate_config)
    return candidate_text, candidate_config, capability_diff


def _public_status(manifest: dict[str, Any]) -> dict[str, Any]:
    result = {
        "ok": manifest.get("status") != "failed",
        "change_id": str(manifest.get("change_id", "")),
        "status": str(manifest.get("status", "unknown")),
        "action": str(manifest.get("action", "")),
        "host_id": str(manifest.get("host_id", "")),
        "command_id": str(manifest.get("command_id", "")),
        "created_at": str(manifest.get("created_at", "")),
        "applied_at": str(manifest.get("applied_at", "")),
        "failed_at": str(manifest.get("failed_at", "")),
        "base_config_sha256": str(manifest.get("base_config_sha256", "")),
        "candidate_config_sha256": str(
            manifest.get("candidate_config_sha256", "")
        ),
        "capability_diff": copy.deepcopy(manifest.get("capability_diff") or {}),
        "error": str(manifest.get("error", "")),
    }
    if manifest.get("status") == "applied":
        result["result"] = copy.deepcopy(manifest.get("result") or {})
    return result


def preview_ssh_profile_change(
    config_path: Path,
    runs_dir: Path,
    action: str,
    host_id: str,
    *,
    host_config: dict[str, Any] | None = None,
    command_id: str = "",
    command_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    if not config_path.exists() or not config_path.is_file() or config_path.is_symlink():
        raise ValueError(f"Config path is not a regular file: {config_path}")
    mutation = _normalize_mutation(
        action, host_id, host_config, command_id, command_profile
    )
    base_bytes = config_path.read_bytes()
    candidate_text, _candidate_config, capability_diff = _build_candidate(
        config_path, base_bytes, mutation
    )
    candidate_bytes = candidate_text.encode("utf-8")
    change_id = _make_change_id()
    manifest = {
        "change_id": change_id,
        "status": "previewed",
        "created_at": _utc_now(),
        "applied_at": "",
        "failed_at": "",
        "config_fingerprint": _config_fingerprint(config_path),
        "base_config_sha256": _sha256_bytes(base_bytes),
        "candidate_config_sha256": _sha256_bytes(candidate_bytes),
        "action": mutation["action"],
        "host_id": mutation["host_id"],
        "command_id": mutation["command_id"],
        "mutation": mutation,
        "capability_diff": capability_diff,
        "result": {},
        "error": "",
    }
    path = _manifest_path(runs_dir, change_id)
    _write_manifest(path, manifest)
    return _public_status(manifest)


def get_ssh_profile_change_status(
    config_path: Path, runs_dir: Path, change_id: str
) -> dict[str, Any]:
    _path, manifest = _read_manifest(runs_dir, change_id)
    if manifest.get("config_fingerprint") != _config_fingerprint(config_path):
        raise ValueError("SSH profile change belongs to a different config path")
    return _public_status(manifest)


def apply_ssh_profile_change(
    config_path: Path,
    runs_dir: Path,
    change_id: str,
    *,
    activate: ActivationCallback | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    manifest_path, manifest = _read_manifest(runs_dir, change_id)
    if manifest.get("config_fingerprint") != _config_fingerprint(config_path):
        raise ValueError("SSH profile change belongs to a different config path")
    if manifest.get("status") == "applied":
        result = copy.deepcopy(manifest.get("result") or {})
        result["idempotent_replay"] = True
        return result
    if manifest.get("status") != "previewed":
        raise ValueError(
            f"SSH profile change {change_id} cannot apply from status "
            f"{manifest.get('status')}"
        )

    original_bytes = config_path.read_bytes()
    current_sha = _sha256_bytes(original_bytes)
    expected_sha = str(manifest.get("base_config_sha256", ""))
    if current_sha != expected_sha:
        raise ValueError(
            "Config changed since SSH profile preview: "
            f"expected {expected_sha[:12]}… got {current_sha[:12]}…"
        )
    mutation = manifest.get("mutation")
    if not isinstance(mutation, dict):
        raise ValueError("SSH profile change manifest has no structured mutation")
    candidate_text, _candidate_config, capability_diff = _build_candidate(
        config_path, original_bytes, mutation
    )
    candidate_sha = _sha256_bytes(candidate_text.encode("utf-8"))
    if candidate_sha != manifest.get("candidate_config_sha256"):
        raise ValueError("SSH profile candidate no longer matches its preview")
    if capability_diff != manifest.get("capability_diff"):
        raise ValueError("SSH capability simulation no longer matches its preview")

    atomic_write_text(config_path, candidate_text)
    activation_result: dict[str, Any] = {"ok": True, "status": "not_requested"}
    try:
        if activate is not None:
            callback_result = activate(config_path)
            if callback_result is not None:
                if not isinstance(callback_result, dict):
                    raise TypeError("SSH profile activation callback must return a mapping")
                activation_result = copy.deepcopy(callback_result)
            if not activation_result.get("ok", False):
                raise RuntimeError(
                    str(activation_result.get("error") or "Config activation failed")
                )
    except Exception as exc:
        restore_error = ""
        try:
            atomic_write_text(config_path, original_bytes.decode("utf-8"))
        except Exception as restore_exc:  # pragma: no cover - catastrophic filesystem case
            restore_error = str(restore_exc)
        manifest["status"] = "failed"
        manifest["failed_at"] = _utc_now()
        manifest["error"] = str(exc)
        manifest["result"] = {
            "ok": False,
            "change_id": change_id,
            "status": "failed",
            "restored_original": not restore_error,
            "restore_error": restore_error,
            "activation": activation_result,
            "error": str(exc),
        }
        _write_manifest(manifest_path, manifest)
        return copy.deepcopy(manifest["result"])

    result = {
        "ok": True,
        "change_id": change_id,
        "status": "applied",
        "action": manifest["action"],
        "host_id": manifest["host_id"],
        "command_id": manifest["command_id"],
        "config_sha256": candidate_sha,
        "capability_diff": copy.deepcopy(capability_diff),
        "activation": activation_result,
        "idempotent_replay": False,
        "error": "",
    }
    manifest["status"] = "applied"
    manifest["applied_at"] = _utc_now()
    manifest["result"] = result
    manifest["error"] = ""
    _write_manifest(manifest_path, manifest)
    return copy.deepcopy(result)
