from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .config import AppConfig, SSHCommandProfileConfig, load_config
from .return_loop.atomic_writer import atomic_write_json, atomic_write_text
from .ssh_capabilities import read_capability_snapshot
from .ssh_commands import (
    _run_ssh_argv,
    build_ssh_argv,
    prepare_ssh_execution,
    resolve_ssh_connection,
    ssh_host_health,
)
from .ssh_credentials import probe_ssh_credential_source
from .ssh_host_keys import (
    managed_known_hosts_path,
    read_host_key_verification,
    stage_host_key_verification,
)
from .ssh_profile_manager import (
    _build_candidate,
    _config_fingerprint,
    _read_manifest,
    _sha256_bytes,
    _write_manifest,
)
from .ssh_project_bindings import (
    build_project_binding_validation_plan,
    evaluate_project_binding_validation,
)
from .ssh_tools import run_ssh_capability_snapshot

SSH_PROFILE_ACTIVATIONS_DIR = "ssh_profile_activations"
SSH_ACTIVATION_SCHEMA_VERSION = "ssh-profile-activation.v1"
SSH_ACTIVATION_STATES = (
    "PREVIEWED",
    "SOURCE_RESOLVED",
    "LOCAL_CREDENTIAL_VALIDATED",
    "HOST_KEY_VERIFIED",
    "AUTHENTICATION_VERIFIED",
    "CAPABILITIES_DISCOVERED",
    "PROJECT_BINDINGS_VALIDATED",
    "ACTIVATION_STAGED",
    "CONFIG_ACTIVATED",
    "POST_ACTIVATION_VERIFIED",
    "COMPLETED",
    "ROLLBACK_PENDING",
    "ROLLED_BACK",
    "RECOVERY_REQUIRED",
)
TERMINAL_ACTIVATION_STATES = frozenset(
    {"COMPLETED", "ROLLED_BACK", "RECOVERY_REQUIRED"}
)

ReloadCallback = Callable[[Path], dict[str, Any] | None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_change_id(change_id: str) -> str:
    value = str(change_id or "").strip()
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in value):
        raise ValueError("Invalid SSH activation change_id")
    return value


def activation_dir(runs_dir: Path, change_id: str) -> Path:
    root = (Path(runs_dir).resolve() / SSH_PROFILE_ACTIVATIONS_DIR).resolve()
    path = (root / _safe_change_id(change_id)).resolve()
    path.relative_to(root)
    return path


def _transaction_path(runs_dir: Path, change_id: str) -> Path:
    return activation_dir(runs_dir, change_id) / "transaction.json"


def _request_path(runs_dir: Path, change_id: str) -> Path:
    return activation_dir(runs_dir, change_id) / "activation_request.json"


def _ack_path(runs_dir: Path, change_id: str) -> Path:
    return activation_dir(runs_dir, change_id) / "activation_ack.json"


def _rollback_request_path(runs_dir: Path, change_id: str) -> Path:
    return activation_dir(runs_dir, change_id) / "rollback_request.json"


def _rollback_ack_path(runs_dir: Path, change_id: str) -> Path:
    return activation_dir(runs_dir, change_id) / "rollback_ack.json"


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _write_bytes(path: Path, data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Activation file {path.name!r} is not UTF-8") from exc
    atomic_write_text(path, text)


def _file_record(path: Path, backup_path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"Activation target {path} must not be a symlink")
    exists = path.is_file()
    if path.exists() and not exists:
        raise ValueError(f"Activation target {path} is not a regular file")
    data = path.read_bytes() if exists else b""
    if exists:
        _write_bytes(backup_path, data)
    return {
        "path": str(path.resolve()),
        "existed": exists,
        "sha256": _sha256(data) if exists else "",
        "backup_path": str(backup_path.resolve()) if exists else "",
        "backup_sha256": _sha256(data) if exists else "",
    }


def _restore_file(record: Mapping[str, Any]) -> None:
    path = Path(str(record.get("path") or "")).resolve()
    if bool(record.get("existed")):
        backup = Path(str(record.get("backup_path") or "")).resolve()
        data = backup.read_bytes()
        if _sha256(data) != str(record.get("backup_sha256") or ""):
            raise ValueError(f"Activation backup hash mismatch for {path.name}")
        _write_bytes(path, data)
    elif path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Activation rollback target {path} is unsafe")
        path.unlink()


def _copy_verified(source: Path, destination: Path, expected_sha256: str) -> None:
    source = source.resolve()
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Activation staged file is missing: {source.name}")
    data = source.read_bytes()
    if _sha256(data) != expected_sha256:
        raise ValueError(f"Activation staged file hash mismatch: {source.name}")
    _write_bytes(destination.resolve(), data)


def _load_transaction(runs_dir: Path, change_id: str) -> dict[str, Any]:
    path = _transaction_path(runs_dir, change_id)
    if not path.exists():
        return {}
    transaction = _read_json(path, label="SSH activation transaction")
    if transaction.get("change_id") != change_id:
        raise ValueError("SSH activation transaction ID mismatch")
    return transaction


def _write_transaction(runs_dir: Path, change_id: str, transaction: dict[str, Any]) -> None:
    atomic_write_json(_transaction_path(runs_dir, change_id), transaction)


def _set_state(
    runs_dir: Path,
    change_id: str,
    transaction: dict[str, Any],
    state: str,
    *,
    evidence: Mapping[str, Any] | None = None,
    error: str = "",
) -> None:
    if state not in SSH_ACTIVATION_STATES:
        raise ValueError(f"Unknown SSH activation state: {state}")
    transaction["state"] = state
    transaction["updated_at"] = _utc_now()
    transaction["error"] = str(error or "")
    history = transaction.setdefault("history", [])
    history.append(
        {
            "state": state,
            "at": transaction["updated_at"],
            "evidence": copy.deepcopy(dict(evidence or {})),
            "error": transaction["error"],
        }
    )
    _write_transaction(runs_dir, change_id, transaction)


def activation_status(runs_dir: Path, change_id: str) -> dict[str, Any]:
    transaction = _load_transaction(runs_dir, change_id)
    if not transaction:
        return {
            "ok": False,
            "change_id": change_id,
            "state": "not_started",
            "run_id": "",
            "error": "SSH activation transaction has not started",
        }
    return {
        "ok": str(transaction.get("state")) not in {"RECOVERY_REQUIRED"},
        "change_id": change_id,
        "run_id": str(transaction.get("run_id") or ""),
        "state": str(transaction.get("state") or "unknown"),
        "host_id": str(transaction.get("host_id") or ""),
        "activation_intent": str(transaction.get("activation_intent") or ""),
        "created_at": str(transaction.get("created_at") or ""),
        "updated_at": str(transaction.get("updated_at") or ""),
        "host_key_verification": copy.deepcopy(
            transaction.get("host_key_verification") or {}
        ),
        "authentication": copy.deepcopy(transaction.get("authentication") or {}),
        "capability_snapshot": copy.deepcopy(
            transaction.get("capability_snapshot") or {}
        ),
        "project_validations": copy.deepcopy(
            transaction.get("project_validations") or []
        ),
        "activation": copy.deepcopy(transaction.get("activation") or {}),
        "rollback": copy.deepcopy(transaction.get("rollback") or {}),
        "error": str(transaction.get("error") or ""),
    }


class SSHActivationAdapter(Protocol):
    def prepare(
        self,
        *,
        candidate_config: AppConfig,
        manifest: Mapping[str, Any],
        transaction_dir: Path,
    ) -> dict[str, Any]: ...

    def post_activate(
        self,
        *,
        active_config: AppConfig,
        manifest: Mapping[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class DefaultSSHActivationAdapter:
    runs_dir: Path

    def _source_probe(
        self,
        candidate_config: AppConfig,
        manifest: Mapping[str, Any],
    ) -> dict[str, Any]:
        host_id = str(manifest.get("host_id") or "")
        host = candidate_config.ssh.hosts[host_id]
        binding = host.credential_binding
        if binding is None:
            return {"ok": True, "status": "legacy", "ready_for_binding": True}
        source = candidate_config.ssh.credential_sources[binding.source_id]
        overrides = {
            field: value
            for field, value in {
                "hostname": binding.hostname,
                "user": binding.user,
                "port": binding.port,
                "identity_file": binding.identity_file,
                "expected_host_key": binding.expected_host_key,
            }.items()
            if value
        }
        probe = probe_ssh_credential_source(
            self.runs_dir,
            source_path=source.path,
            source_type=source.type,
            host_hint=source.alias,
            field_overrides=overrides,
        )
        if source.type == "key_file":
            acceptable = bool(probe.get("ok")) and not probe.get("refusals")
        else:
            acceptable = bool(probe.get("ready_for_binding"))
        if not acceptable:
            raise ValueError("SSH credential source did not pass candidate validation")
        return probe

    def _sandbox_config(
        self,
        candidate_config: AppConfig,
        transaction_dir: Path,
        staged_known_hosts: Path,
    ) -> AppConfig:
        sandbox_runs = (transaction_dir / "candidate_runs").resolve()
        sandbox_known_hosts = managed_known_hosts_path(sandbox_runs)
        sandbox_known_hosts.parent.mkdir(parents=True, exist_ok=True)
        _copy_verified(
            staged_known_hosts,
            sandbox_known_hosts,
            _sha256(staged_known_hosts.read_bytes()),
        )
        sandbox = candidate_config.model_copy(deep=True)
        sandbox.runs_dir = str(sandbox_runs)
        return sandbox

    def _run_project_checks(
        self,
        candidate_config: AppConfig,
        manifest: Mapping[str, Any],
        capability: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        validations: list[dict[str, Any]] = []
        for binding_id in list(manifest.get("project_binding_ids") or []):
            resolved, checks = build_project_binding_validation_plan(
                candidate_config,
                str(binding_id),
            )
            results: dict[str, dict[str, Any]] = {}
            for check in checks:
                profile = SSHCommandProfileConfig(
                    command_id=f"ssh_activation_{check.name}",
                    argv=list(check.argv),
                    timeout_seconds=30,
                    writes_remote=False,
                    permission_tier="T0",
                )
                argv = build_ssh_argv(candidate_config, resolved.host_id, profile)
                prepared, stdin_text, _destination = prepare_ssh_execution(
                    resolved.host, argv
                )
                results[check.name] = _run_ssh_argv(
                    prepared,
                    cwd=candidate_config.config_dir,
                    timeout_seconds=profile.timeout_seconds,
                    output_limit=candidate_config.ssh.max_output_bytes,
                    stdin_text=stdin_text,
                )
            validation = evaluate_project_binding_validation(
                resolved,
                checks,
                results,
                capability_snapshot=capability,
            )
            validations.append(validation)
            if not validation.get("ok"):
                raise ValueError(
                    f"SSH project binding validation failed: {binding_id}"
                )
        return validations

    def prepare(
        self,
        *,
        candidate_config: AppConfig,
        manifest: Mapping[str, Any],
        transaction_dir: Path,
    ) -> dict[str, Any]:
        action = str(manifest.get("action") or "")
        if action != "configure_host":
            return {
                "source_probe": {"ok": True, "status": "not_required"},
                "host_key_verification": {},
                "authentication": {"ok": True, "status": "not_required"},
                "capability_snapshot": {},
                "project_validations": [],
                "staged_known_hosts_path": "",
                "staged_known_hosts_sha256": "",
                "capability_snapshot_path": "",
                "capability_snapshot_sha256": "",
            }

        host_id = str(manifest.get("host_id") or "")
        intent = str(manifest.get("activation_intent") or "")
        host = candidate_config.ssh.hosts[host_id]
        binding = host.credential_binding
        if binding is None:
            raise ValueError("configure_host candidate has no credential binding")
        source_probe = self._source_probe(candidate_config, manifest)
        connection = resolve_ssh_connection(host, candidate_config.ssh)
        user, hostname = connection.destination.split("@", 1)
        _ = user

        previous_fingerprints: list[str] = []
        if intent == "rotation":
            mutation = dict(manifest.get("mutation") or {})
            previous = str(
                dict(mutation.get("previous_host_identity") or {}).get(
                    "expected_host_key"
                )
                or ""
            )
            if previous:
                previous_fingerprints.append(previous)
        verification = stage_host_key_verification(
            self.runs_dir,
            host_id=host_id,
            hostname=hostname,
            port=connection.port,
            policy=connection.host_key_policy,
            expected_fingerprint=connection.expected_host_key,
            intent=intent,
            previous_fingerprints=previous_fingerprints,
        )
        verification_record = read_host_key_verification(
            self.runs_dir, str(verification["verification_id"])
        )
        sandbox = self._sandbox_config(
            candidate_config,
            transaction_dir,
            verification_record.staged_known_hosts_path,
        )
        authentication = ssh_host_health(sandbox, host_id)
        if not authentication.get("ok"):
            raise ValueError("SSH candidate authentication failed")

        required = sorted(
            {
                capability
                for binding_id in list(manifest.get("project_binding_ids") or [])
                for capability in candidate_config.ssh.project_bindings[
                    str(binding_id)
                ].required_capabilities
            }
        )
        selected_fingerprints = list(
            verification.get("selected_fingerprints") or []
        )
        capability = run_ssh_capability_snapshot(
            sandbox,
            host_id,
            host_key_fingerprint=(
                str(selected_fingerprints[0]) if selected_fingerprints else ""
            ),
            endpoint_route="candidate_credential_binding",
            required_capabilities=required,
        )
        if not capability.get("ok"):
            raise ValueError("SSH candidate capability requirements failed")
        project_validations = self._run_project_checks(
            sandbox, manifest, capability
        )
        full_capability = read_capability_snapshot(
            sandbox.resolve_runs_dir(),
            host_id=host_id,
            snapshot_id=str(capability["snapshot_id"]),
        )
        source_capability_path = (
            sandbox.resolve_runs_dir()
            / "ssh_capabilities"
            / host_id
            / f"{capability['snapshot_id']}.json"
        ).resolve()
        staged_capability_path = (
            transaction_dir / "staged_capability_snapshot.json"
        ).resolve()
        _write_bytes(staged_capability_path, source_capability_path.read_bytes())
        return {
            "source_probe": source_probe,
            "host_key_verification": verification,
            "authentication": {
                "ok": True,
                "status": "verified",
                "host_id": host_id,
                "writes_remote": False,
            },
            "capability_snapshot": capability,
            "project_validations": project_validations,
            "staged_known_hosts_path": str(
                verification_record.staged_known_hosts_path.resolve()
            ),
            "staged_known_hosts_sha256": _sha256(
                verification_record.staged_known_hosts_path.read_bytes()
            ),
            "capability_snapshot_path": str(staged_capability_path),
            "capability_snapshot_sha256": _sha256(
                staged_capability_path.read_bytes()
            ),
            "capability_snapshot_record": {
                "snapshot_id": str(full_capability["snapshot_id"]),
                "snapshot_sha256": str(full_capability["snapshot_sha256"]),
                "host_id": host_id,
            },
        }

    def post_activate(
        self,
        *,
        active_config: AppConfig,
        manifest: Mapping[str, Any],
    ) -> dict[str, Any]:
        if str(manifest.get("action") or "") != "configure_host":
            return {"ok": True, "status": "not_required"}
        host_id = str(manifest.get("host_id") or "")
        health = ssh_host_health(active_config, host_id)
        return {
            "ok": bool(health.get("ok")),
            "status": "verified" if health.get("ok") else "failed",
            "host_id": host_id,
            "writes_remote": False,
            "error": str(health.get("error") or ""),
        }


def _candidate_material(
    config_path: Path,
    runs_dir: Path,
    change_id: str,
) -> tuple[Path, dict[str, Any], bytes, str, AppConfig]:
    manifest_path, manifest = _read_manifest(runs_dir, change_id)
    if manifest.get("config_fingerprint") != _config_fingerprint(config_path):
        raise ValueError("SSH profile change belongs to a different config path")
    original = config_path.read_bytes()
    if _sha256_bytes(original) != str(manifest.get("base_config_sha256") or ""):
        raise ValueError("Config changed since SSH profile preview")
    mutation = manifest.get("mutation")
    if not isinstance(mutation, dict):
        raise ValueError("SSH profile change manifest has no structured mutation")
    candidate_text, candidate_config, capability_diff = _build_candidate(
        config_path, original, mutation
    )
    candidate_bytes = candidate_text.encode("utf-8")
    if _sha256_bytes(candidate_bytes) != str(
        manifest.get("candidate_config_sha256") or ""
    ):
        raise ValueError("SSH profile candidate no longer matches its preview")
    if capability_diff != manifest.get("capability_diff"):
        raise ValueError("SSH capability simulation no longer matches its preview")
    return manifest_path, manifest, original, candidate_text, candidate_config


def _initial_transaction(
    *,
    change_id: str,
    run_id: str,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
        "change_id": change_id,
        "run_id": run_id,
        "state": "PREVIEWED",
        "host_id": str(manifest.get("host_id") or ""),
        "action": str(manifest.get("action") or ""),
        "activation_intent": str(manifest.get("activation_intent") or ""),
        "created_at": now,
        "updated_at": now,
        "history": [
            {"state": "PREVIEWED", "at": now, "evidence": {}, "error": ""}
        ],
        "host_key_verification": {},
        "authentication": {},
        "capability_snapshot": {},
        "project_validations": [],
        "activation": {},
        "rollback": {},
        "error": "",
    }


def _wait_for_json(path: Path, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file() and not path.is_symlink():
            return _read_json(path, label=path.name)
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {path.name}")


def run_ssh_profile_activation(
    config_path: Path,
    runs_dir: Path,
    change_id: str,
    run_id: str,
    *,
    adapter: SSHActivationAdapter | None = None,
    coordinator_timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Durable worker side of one SSH profile activation transaction."""

    config_path = config_path.resolve()
    runs_dir = runs_dir.resolve()
    manifest_path, manifest, original, candidate_text, candidate_config = (
        _candidate_material(config_path, runs_dir, change_id)
    )
    transaction = _load_transaction(runs_dir, change_id)
    if transaction:
        existing_run = str(transaction.get("run_id") or "")
        if existing_run and existing_run != run_id:
            raise ValueError(
                f"SSH activation {change_id} already belongs to run {existing_run}"
            )
        if transaction.get("state") == "COMPLETED":
            result = copy.deepcopy(transaction.get("result") or {})
            result["idempotent_replay"] = True
            return result
        if transaction.get("state") == "ROLLED_BACK":
            result = copy.deepcopy(transaction.get("result") or {})
            result["idempotent_replay"] = True
            return result
    else:
        transaction = _initial_transaction(
            change_id=change_id, run_id=run_id, manifest=manifest
        )
        _write_transaction(runs_dir, change_id, transaction)

    tx_dir = activation_dir(runs_dir, change_id)
    candidate_path = tx_dir / "candidate_config.yaml"
    _write_bytes(candidate_path, candidate_text.encode("utf-8"))
    original_path = tx_dir / "original_config.yaml"
    _write_bytes(original_path, original)
    adapter = adapter or DefaultSSHActivationAdapter(runs_dir)

    try:
        _set_state(runs_dir, change_id, transaction, "SOURCE_RESOLVED")
        prepared = adapter.prepare(
            candidate_config=candidate_config,
            manifest=manifest,
            transaction_dir=tx_dir,
        )
        source_probe = dict(prepared.get("source_probe") or {})
        _set_state(
            runs_dir,
            change_id,
            transaction,
            "LOCAL_CREDENTIAL_VALIDATED",
            evidence={
                "probe_id": str(source_probe.get("probe_id") or ""),
                "source_version_sha256": str(
                    source_probe.get("source_version_sha256") or ""
                ),
            },
        )
        transaction["host_key_verification"] = copy.deepcopy(
            prepared.get("host_key_verification") or {}
        )
        _set_state(
            runs_dir,
            change_id,
            transaction,
            "HOST_KEY_VERIFIED",
            evidence={
                "verification_id": str(
                    transaction["host_key_verification"].get("verification_id")
                    or ""
                ),
                "fingerprints": list(
                    transaction["host_key_verification"].get(
                        "selected_fingerprints"
                    )
                    or []
                ),
            },
        )
        transaction["authentication"] = copy.deepcopy(
            prepared.get("authentication") or {}
        )
        _set_state(
            runs_dir,
            change_id,
            transaction,
            "AUTHENTICATION_VERIFIED",
            evidence=transaction["authentication"],
        )
        transaction["capability_snapshot"] = copy.deepcopy(
            prepared.get("capability_snapshot") or {}
        )
        _set_state(
            runs_dir,
            change_id,
            transaction,
            "CAPABILITIES_DISCOVERED",
            evidence={
                "snapshot_id": str(
                    transaction["capability_snapshot"].get("snapshot_id") or ""
                ),
                "snapshot_sha256": str(
                    transaction["capability_snapshot"].get("snapshot_sha256")
                    or ""
                ),
            },
        )
        transaction["project_validations"] = copy.deepcopy(
            prepared.get("project_validations") or []
        )
        _set_state(
            runs_dir,
            change_id,
            transaction,
            "PROJECT_BINDINGS_VALIDATED",
            evidence={
                "binding_count": len(transaction["project_validations"]),
                "statuses": [
                    str(item.get("status") or "")
                    for item in transaction["project_validations"]
                    if isinstance(item, dict)
                ],
            },
        )

        request = {
            "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
            "change_id": change_id,
            "run_id": run_id,
            "config_fingerprint": str(manifest["config_fingerprint"]),
            "base_config_sha256": str(manifest["base_config_sha256"]),
            "candidate_config_path": str(candidate_path.resolve()),
            "candidate_config_sha256": str(
                manifest["candidate_config_sha256"]
            ),
            "staged_known_hosts_path": str(
                prepared.get("staged_known_hosts_path") or ""
            ),
            "staged_known_hosts_sha256": str(
                prepared.get("staged_known_hosts_sha256") or ""
            ),
            "capability_snapshot_path": str(
                prepared.get("capability_snapshot_path") or ""
            ),
            "capability_snapshot_sha256": str(
                prepared.get("capability_snapshot_sha256") or ""
            ),
            "capability_snapshot_record": copy.deepcopy(
                prepared.get("capability_snapshot_record") or {}
            ),
            "host_id": str(manifest.get("host_id") or ""),
            "requested_at": _utc_now(),
            "status": "pending",
        }
        atomic_write_json(_request_path(runs_dir, change_id), request)
        _set_state(
            runs_dir,
            change_id,
            transaction,
            "ACTIVATION_STAGED",
            evidence={"request_sha256": _sha256(json.dumps(request, sort_keys=True).encode("utf-8"))},
        )
        ack = _wait_for_json(
            _ack_path(runs_dir, change_id), coordinator_timeout_seconds
        )
        transaction["activation"] = copy.deepcopy(ack)
        if not ack.get("ok"):
            state = (
                "ROLLED_BACK"
                if ack.get("rollback_verified")
                else "RECOVERY_REQUIRED"
            )
            _set_state(
                runs_dir,
                change_id,
                transaction,
                state,
                evidence=ack,
                error=str(ack.get("error") or "Activation failed"),
            )
            result = {
                "ok": False,
                "change_id": change_id,
                "run_id": run_id,
                "status": state.lower(),
                "activation_state": state,
                "rollback_verified": bool(ack.get("rollback_verified")),
                "error": str(ack.get("error") or "Activation failed"),
                "idempotent_replay": False,
            }
            transaction["result"] = result
            _write_transaction(runs_dir, change_id, transaction)
            manifest["status"] = "failed"
            manifest["failed_at"] = _utc_now()
            manifest["error"] = result["error"]
            manifest["result"] = result
            _write_manifest(manifest_path, manifest)
            return result

        _set_state(
            runs_dir,
            change_id,
            transaction,
            "CONFIG_ACTIVATED",
            evidence={
                "config_sha256": str(ack.get("config_sha256") or ""),
                "known_hosts_sha256": str(
                    ack.get("known_hosts_sha256") or ""
                ),
            },
        )
        active_config = load_config(config_path)
        post = adapter.post_activate(
            active_config=active_config,
            manifest=manifest,
        )
        if not post.get("ok"):
            rollback_request = {
                "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
                "change_id": change_id,
                "run_id": run_id,
                "reason": str(post.get("error") or "Post-activation verification failed"),
                "requested_at": _utc_now(),
            }
            atomic_write_json(
                _rollback_request_path(runs_dir, change_id), rollback_request
            )
            _set_state(
                runs_dir,
                change_id,
                transaction,
                "ROLLBACK_PENDING",
                evidence=post,
                error=rollback_request["reason"],
            )
            rollback_ack = _wait_for_json(
                _rollback_ack_path(runs_dir, change_id),
                coordinator_timeout_seconds,
            )
            transaction["rollback"] = copy.deepcopy(rollback_ack)
            state = (
                "ROLLED_BACK"
                if rollback_ack.get("ok")
                else "RECOVERY_REQUIRED"
            )
            _set_state(
                runs_dir,
                change_id,
                transaction,
                state,
                evidence=rollback_ack,
                error=rollback_request["reason"],
            )
            result = {
                "ok": False,
                "change_id": change_id,
                "run_id": run_id,
                "status": state.lower(),
                "activation_state": state,
                "rollback_verified": bool(rollback_ack.get("ok")),
                "error": rollback_request["reason"],
                "idempotent_replay": False,
            }
            transaction["result"] = result
            _write_transaction(runs_dir, change_id, transaction)
            manifest["status"] = "failed"
            manifest["failed_at"] = _utc_now()
            manifest["error"] = result["error"]
            manifest["result"] = result
            _write_manifest(manifest_path, manifest)
            return result

        _set_state(
            runs_dir,
            change_id,
            transaction,
            "POST_ACTIVATION_VERIFIED",
            evidence=post,
        )
        result = {
            "ok": True,
            "change_id": change_id,
            "run_id": run_id,
            "status": "completed",
            "activation_state": "COMPLETED",
            "action": str(manifest.get("action") or ""),
            "host_id": str(manifest.get("host_id") or ""),
            "config_sha256": str(manifest["candidate_config_sha256"]),
            "host_key_verification": copy.deepcopy(
                transaction["host_key_verification"]
            ),
            "capability_snapshot": copy.deepcopy(
                transaction["capability_snapshot"]
            ),
            "project_validations": copy.deepcopy(
                transaction["project_validations"]
            ),
            "post_activation": copy.deepcopy(post),
            "idempotent_replay": False,
            "error": "",
        }
        transaction["result"] = result
        _set_state(runs_dir, change_id, transaction, "COMPLETED", evidence=post)
        manifest["status"] = "applied"
        manifest["applied_at"] = _utc_now()
        manifest["result"] = result
        manifest["error"] = ""
        _write_manifest(manifest_path, manifest)
        return result
    except Exception as exc:
        state = str(transaction.get("state") or "")
        if state in {"CONFIG_ACTIVATED", "ROLLBACK_PENDING"}:
            terminal = "RECOVERY_REQUIRED"
        else:
            terminal = "ROLLED_BACK"
        _set_state(
            runs_dir,
            change_id,
            transaction,
            terminal,
            error=str(exc),
        )
        result = {
            "ok": False,
            "change_id": change_id,
            "run_id": run_id,
            "status": terminal.lower(),
            "activation_state": terminal,
            "rollback_verified": terminal == "ROLLED_BACK",
            "error": str(exc),
            "idempotent_replay": False,
        }
        transaction["result"] = result
        _write_transaction(runs_dir, change_id, transaction)
        manifest["status"] = "failed"
        manifest["failed_at"] = _utc_now()
        manifest["error"] = str(exc)
        manifest["result"] = result
        _write_manifest(manifest_path, manifest)
        return result


def _active_capability_pointer_path(runs_dir: Path, host_id: str) -> Path:
    return (
        Path(runs_dir).resolve()
        / "ssh_capabilities"
        / str(host_id)
        / "CURRENT.json"
    ).resolve()


def _backup_state(
    config_path: Path,
    runs_dir: Path,
    request: Mapping[str, Any],
    tx_dir: Path,
) -> dict[str, Any]:
    backup_dir = tx_dir / "backups"
    host_id = str(request.get("host_id") or "")
    return {
        "config": _file_record(config_path, backup_dir / "config.yaml"),
        "known_hosts": _file_record(
            managed_known_hosts_path(runs_dir),
            backup_dir / "known_hosts",
        ),
        "capability_pointer": _file_record(
            _active_capability_pointer_path(runs_dir, host_id),
            backup_dir / "capability_CURRENT.json",
        ),
        "created_at": _utc_now(),
    }


def _restore_activation_state(
    state: Mapping[str, Any],
    *,
    reload_callback: ReloadCallback,
    config_path: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    for key in ("capability_pointer", "known_hosts", "config"):
        try:
            _restore_file(dict(state.get("backups") or {})[key])
        except Exception as exc:  # catastrophic path tested via injected faults
            errors.append(f"{key}: {exc}")
    reload_result: dict[str, Any] = {"ok": False, "error": "not attempted"}
    if not errors:
        try:
            result = reload_callback(config_path)
            reload_result = dict(result or {"ok": True})
            if not reload_result.get("ok"):
                errors.append(str(reload_result.get("error") or "Reload failed"))
        except Exception as exc:
            errors.append(f"reload: {exc}")
    return {
        "ok": not errors,
        "rollback_verified": not errors,
        "reload": reload_result,
        "errors": errors,
        "error": "; ".join(errors),
    }


def reconcile_ssh_activation_request(
    config_path: Path,
    runs_dir: Path,
    change_id: str,
    *,
    reload_callback: ReloadCallback,
) -> dict[str, Any]:
    """Live-server side: activate or roll back one staged transaction."""

    config_path = config_path.resolve()
    runs_dir = runs_dir.resolve()
    tx_dir = activation_dir(runs_dir, change_id)
    request = _read_json(
        _request_path(runs_dir, change_id), label="SSH activation request"
    )
    if request.get("change_id") != change_id:
        raise ValueError("SSH activation request ID mismatch")
    if str(request.get("config_fingerprint") or "") != _config_fingerprint(
        config_path
    ):
        raise ValueError("SSH activation request belongs to a different config path")

    state_path = tx_dir / "server_activation_state.json"
    state = _read_json(state_path, label="SSH server activation state") if state_path.exists() else {}
    if not state:
        if _sha256(config_path.read_bytes()) != str(
            request.get("base_config_sha256") or ""
        ):
            raise ValueError("Active config changed before SSH activation")
        state = {
            "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
            "change_id": change_id,
            "status": "snapshotted",
            "backups": _backup_state(config_path, runs_dir, request, tx_dir),
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "applied": {},
            "error": "",
        }
        atomic_write_json(state_path, state)

    rollback_request = _rollback_request_path(runs_dir, change_id)
    if rollback_request.exists():
        rollback_ack = _rollback_ack_path(runs_dir, change_id)
        if rollback_ack.exists():
            return _read_json(rollback_ack, label="SSH rollback acknowledgement")
        restored = _restore_activation_state(
            state,
            reload_callback=reload_callback,
            config_path=config_path,
        )
        state["status"] = "rolled_back" if restored["ok"] else "recovery_required"
        state["updated_at"] = _utc_now()
        state["rollback"] = restored
        state["error"] = str(restored.get("error") or "")
        atomic_write_json(state_path, state)
        ack = {
            "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
            "change_id": change_id,
            "ok": bool(restored["ok"]),
            "status": state["status"],
            "rollback_verified": bool(restored["rollback_verified"]),
            "reload": restored["reload"],
            "created_at": _utc_now(),
            "error": state["error"],
        }
        atomic_write_json(rollback_ack, ack)
        return ack

    ack_path = _ack_path(runs_dir, change_id)
    if ack_path.exists():
        return _read_json(ack_path, label="SSH activation acknowledgement")

    try:
        candidate_path = Path(str(request["candidate_config_path"])).resolve()
        _copy_verified(
            candidate_path,
            config_path,
            str(request["candidate_config_sha256"]),
        )
        state["status"] = "config_written"
        state["applied"]["config_sha256"] = str(
            request["candidate_config_sha256"]
        )
        state["updated_at"] = _utc_now()
        atomic_write_json(state_path, state)

        staged_known_hosts = str(request.get("staged_known_hosts_path") or "")
        if staged_known_hosts:
            _copy_verified(
                Path(staged_known_hosts),
                managed_known_hosts_path(runs_dir),
                str(request["staged_known_hosts_sha256"]),
            )
            state["applied"]["known_hosts_sha256"] = str(
                request["staged_known_hosts_sha256"]
            )

        snapshot_path = str(request.get("capability_snapshot_path") or "")
        snapshot_record = dict(request.get("capability_snapshot_record") or {})
        if snapshot_path:
            host_id = str(snapshot_record["host_id"])
            snapshot_id = str(snapshot_record["snapshot_id"])
            target = (
                runs_dir
                / "ssh_capabilities"
                / host_id
                / f"{snapshot_id}.json"
            ).resolve()
            _copy_verified(
                Path(snapshot_path),
                target,
                str(request["capability_snapshot_sha256"]),
            )
            pointer = {
                "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
                "host_id": host_id,
                "snapshot_id": snapshot_id,
                "snapshot_sha256": str(snapshot_record["snapshot_sha256"]),
                "activated_at": _utc_now(),
            }
            atomic_write_json(
                _active_capability_pointer_path(runs_dir, host_id), pointer
            )
            state["applied"]["capability_snapshot_id"] = snapshot_id

        reload_result = dict(reload_callback(config_path) or {"ok": True})
        if not reload_result.get("ok"):
            raise RuntimeError(
                str(reload_result.get("error") or "Config reload failed")
            )
        state["status"] = "activated"
        state["updated_at"] = _utc_now()
        state["reload"] = reload_result
        atomic_write_json(state_path, state)
        ack = {
            "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
            "change_id": change_id,
            "ok": True,
            "status": "activated",
            "config_sha256": str(request["candidate_config_sha256"]),
            "known_hosts_sha256": str(
                request.get("staged_known_hosts_sha256") or ""
            ),
            "capability_snapshot_id": str(
                snapshot_record.get("snapshot_id") or ""
            ),
            "reload": reload_result,
            "rollback_verified": False,
            "created_at": _utc_now(),
            "error": "",
        }
        atomic_write_json(ack_path, ack)
        return ack
    except Exception as exc:
        restored = _restore_activation_state(
            state,
            reload_callback=reload_callback,
            config_path=config_path,
        )
        state["status"] = "rolled_back" if restored["ok"] else "recovery_required"
        state["updated_at"] = _utc_now()
        state["rollback"] = restored
        state["error"] = str(exc)
        atomic_write_json(state_path, state)
        ack = {
            "schema_version": SSH_ACTIVATION_SCHEMA_VERSION,
            "change_id": change_id,
            "ok": False,
            "status": state["status"],
            "rollback_verified": bool(restored["ok"]),
            "reload": restored["reload"],
            "created_at": _utc_now(),
            "error": str(exc),
        }
        atomic_write_json(ack_path, ack)
        return ack


def reconcile_pending_ssh_activations(
    config_path: Path,
    runs_dir: Path,
    *,
    reload_callback: ReloadCallback,
) -> list[dict[str, Any]]:
    root = (Path(runs_dir).resolve() / SSH_PROFILE_ACTIVATIONS_DIR).resolve()
    if not root.exists():
        return []
    results: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_symlink() or not child.is_dir():
            continue
        request = child / "activation_request.json"
        if not request.is_file() or request.is_symlink():
            continue
        try:
            results.append(
                reconcile_ssh_activation_request(
                    config_path,
                    runs_dir,
                    child.name,
                    reload_callback=reload_callback,
                )
            )
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "change_id": child.name,
                    "status": "recovery_required",
                    "error": str(exc),
                }
            )
    return results
