from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping

import pytest

from soma.config import AppConfig, SSHHostConfig, load_config
from soma.ssh_activation import (
    SSH_ACTIVATION_STATES,
    activation_dir,
    activation_status,
    reconcile_ssh_activation_request,
    run_ssh_profile_activation,
)
from soma.ssh_profile_manager import preview_ssh_profile_change


class FakeActivationAdapter:
    def __init__(
        self,
        *,
        post_ok: bool = True,
        prepare_error: str = "",
        with_staged_files: bool = True,
    ) -> None:
        self.post_ok = post_ok
        self.prepare_error = prepare_error
        self.with_staged_files = with_staged_files
        self.prepare_calls = 0
        self.post_calls = 0

    def prepare(
        self,
        *,
        candidate_config: AppConfig,
        manifest: Mapping[str, Any],
        transaction_dir: Path,
    ) -> dict[str, Any]:
        self.prepare_calls += 1
        if self.prepare_error:
            raise ValueError(self.prepare_error)
        result: dict[str, Any] = {
            "source_probe": {
                "ok": True,
                "probe_id": "20260725T000000Z_sshcred_deadbeef",
                "source_version_sha256": "a" * 64,
            },
            "host_key_verification": {
                "ok": True,
                "verification_id": "20260725T000000Z_sshkey_deadbeef",
                "selected_fingerprints": ["SHA256:" + "A" * 43],
            },
            "authentication": {
                "ok": True,
                "status": "verified",
                "writes_remote": False,
            },
            "capability_snapshot": {
                "ok": True,
                "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
                "snapshot_sha256": "b" * 64,
            },
            "project_validations": [
                {
                    "ok": True,
                    "status": "valid",
                    "binding_id": "sample_binding",
                }
            ],
            "staged_known_hosts_path": "",
            "staged_known_hosts_sha256": "",
            "capability_snapshot_path": "",
            "capability_snapshot_sha256": "",
            "capability_snapshot_record": {},
        }
        if self.with_staged_files:
            known_hosts = transaction_dir / "fake-known-hosts"
            known_hosts.write_text(
                "candidate.example ssh-ed25519 AAAA\n", encoding="utf-8"
            )
            capability = transaction_dir / "fake-capability.json"
            capability.write_text(
                json.dumps(
                    {
                        "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
                        "snapshot_sha256": "b" * 64,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            import hashlib

            result.update(
                {
                    "staged_known_hosts_path": str(known_hosts.resolve()),
                    "staged_known_hosts_sha256": hashlib.sha256(
                        known_hosts.read_bytes()
                    ).hexdigest(),
                    "capability_snapshot_path": str(capability.resolve()),
                    "capability_snapshot_sha256": hashlib.sha256(
                        capability.read_bytes()
                    ).hexdigest(),
                    "capability_snapshot_record": {
                        "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
                        "snapshot_sha256": "b" * 64,
                        "host_id": str(manifest.get("host_id") or ""),
                    },
                }
            )
        return result

    def post_activate(
        self,
        *,
        active_config: AppConfig,
        manifest: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.post_calls += 1
        return {
            "ok": self.post_ok,
            "status": "verified" if self.post_ok else "failed",
            "host_id": str(manifest.get("host_id") or ""),
            "error": "" if self.post_ok else "post-check failed",
        }


def _base_config(tmp_path: Path) -> tuple[Path, Path]:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "repos: {}\n"
        "runs_dir: runs\n"
        "ssh:\n"
        "  enabled: true\n"
        "  hosts: {}\n",
        encoding="utf-8",
    )
    runs_dir = tmp_path / "runs"
    return config_path, runs_dir


def _preview_add_host(config_path: Path, runs_dir: Path) -> str:
    identity_file = config_path.parent / "candidate_ed25519"
    identity_file.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "activation-fixture-only\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        action="add_host",
        host_id="candidate",
        host_config=SSHHostConfig(
            hostname="candidate.example",
            user="root",
            identity_file=str(identity_file.resolve()),
        ).model_dump(mode="python"),
    )
    return str(preview["change_id"])


def _wait_for(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {path}")


def _run_worker_thread(
    config_path: Path,
    runs_dir: Path,
    change_id: str,
    adapter: FakeActivationAdapter,
    result_holder: dict[str, Any],
) -> threading.Thread:
    def execute() -> None:
        result_holder["result"] = run_ssh_profile_activation(
            config_path,
            runs_dir,
            change_id,
            "20260725T000000Z_ssh_profile_activation_deadbeef",
            adapter=adapter,
            coordinator_timeout_seconds=10,
        )

    thread = threading.Thread(target=execute, daemon=True)
    thread.start()
    return thread


def _reload_recorder(calls: list[str], *, fail: bool = False):
    def reload_config(config_path: Path) -> dict[str, Any]:
        calls.append(load_config(config_path).model_dump_json())
        if fail:
            return {"ok": False, "error": "injected reload failure"}
        return {"ok": True, "status": "active"}

    return reload_config


def test_activation_state_contract_is_complete_and_ordered() -> None:
    assert SSH_ACTIVATION_STATES[0] == "PREVIEWED"
    assert SSH_ACTIVATION_STATES[-1] == "RECOVERY_REQUIRED"
    assert len(SSH_ACTIVATION_STATES) == len(set(SSH_ACTIVATION_STATES))
    for state in (
        "HOST_KEY_VERIFIED",
        "AUTHENTICATION_VERIFIED",
        "CAPABILITIES_DISCOVERED",
        "ACTIVATION_STAGED",
        "CONFIG_ACTIVATED",
        "ROLLBACK_PENDING",
        "ROLLED_BACK",
    ):
        assert state in SSH_ACTIVATION_STATES


def test_successful_activation_is_worker_server_coordinated_and_idempotent(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = _base_config(tmp_path)
    change_id = _preview_add_host(config_path, runs_dir)
    adapter = FakeActivationAdapter()
    holder: dict[str, Any] = {}
    thread = _run_worker_thread(
        config_path, runs_dir, change_id, adapter, holder
    )
    request_path = activation_dir(runs_dir, change_id) / "activation_request.json"
    _wait_for(request_path)
    reload_calls: list[str] = []
    acknowledgement = reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=_reload_recorder(reload_calls),
    )
    thread.join(timeout=10)

    assert acknowledgement["ok"] is True
    assert thread.is_alive() is False
    result = holder["result"]
    assert result["ok"] is True
    assert result["activation_state"] == "COMPLETED"
    assert load_config(config_path).ssh.hosts["candidate"].hostname == (
        "candidate.example"
    )
    assert adapter.prepare_calls == 1
    assert adapter.post_calls == 1
    assert len(reload_calls) == 1
    status = activation_status(runs_dir, change_id)
    assert status["state"] == "COMPLETED"
    assert status["capability_snapshot"]["snapshot_id"].endswith("deadbeef")

    replay = run_ssh_profile_activation(
        config_path,
        runs_dir,
        change_id,
        "20260725T000000Z_ssh_profile_activation_deadbeef",
        adapter=adapter,
        coordinator_timeout_seconds=1,
    )
    assert replay["ok"] is True
    assert replay["idempotent_replay"] is True
    assert adapter.prepare_calls == 1


def test_configure_host_acceptance_completes_without_secret_value_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "repos:\n"
        "  app:\n"
        f"    path: {json.dumps(str(app_dir.resolve()))}\n"
        "runs_dir: runs\n"
        "ssh:\n"
        "  enabled: true\n"
        "  hosts: {}\n",
        encoding="utf-8",
    )
    runs_dir = tmp_path / "runs"
    identity_file = tmp_path / "acceptance_ed25519"
    identity_file.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "acceptance-fixture-only\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    secret_hostname = "fake-acceptance.invalid"
    secret_user = "acceptance_operator"
    monkeypatch.setenv("ACCEPTANCE_SSH_HOST", secret_hostname)
    monkeypatch.setenv("ACCEPTANCE_SSH_USER", secret_user)
    monkeypatch.setenv("ACCEPTANCE_SSH_PORT", "22")
    monkeypatch.setenv("ACCEPTANCE_SSH_KEY", str(identity_file.resolve()))

    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        action="configure_host",
        host_id="acceptance",
        host_config={
            "credential_binding": {
                "source_id": "acceptance_source",
                "host_key_policy": "tofu",
                "hostname": "ACCEPTANCE_SSH_HOST",
                "user": "ACCEPTANCE_SSH_USER",
                "port": "ACCEPTANCE_SSH_PORT",
                "identity_file": "ACCEPTANCE_SSH_KEY",
            },
            "allowed_remote_roots": ["/srv"],
        },
        credential_source_id="acceptance_source",
        credential_source={"type": "process_environment"},
        project_bindings={
            "app_acceptance": {
                "repo_name": "app",
                "remote_root": "/srv/app",
                "required_capabilities": ["docker"],
                "allow_first_deployment": True,
            }
        },
        activation_intent="new_host",
    )
    preview_text = json.dumps(preview, sort_keys=True)
    assert secret_hostname not in preview_text
    assert secret_user not in preview_text
    assert str(identity_file.resolve()) not in preview_text

    class FakeSSHNetworkAdapter(FakeActivationAdapter):
        def prepare(
            self,
            *,
            candidate_config: AppConfig,
            manifest: Mapping[str, Any],
            transaction_dir: Path,
        ) -> dict[str, Any]:
            result = super().prepare(
                candidate_config=candidate_config,
                manifest=manifest,
                transaction_dir=transaction_dir,
            )
            result["project_validations"] = [
                {
                    "ok": True,
                    "status": "preparation_required",
                    "binding_id": "app_acceptance",
                    "preparation_required_checks": ["remote_root_exists"],
                }
            ]
            return result

    change_id = str(preview["change_id"])
    adapter = FakeSSHNetworkAdapter()
    holder: dict[str, Any] = {}
    thread = _run_worker_thread(
        config_path, runs_dir, change_id, adapter, holder
    )
    _wait_for(activation_dir(runs_dir, change_id) / "activation_request.json")
    acknowledgement = reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=_reload_recorder([]),
    )
    thread.join(timeout=10)

    assert acknowledgement["ok"] is True
    assert thread.is_alive() is False
    assert holder["result"]["activation_state"] == "COMPLETED"
    active = load_config(config_path)
    assert active.ssh.credential_sources["acceptance_source"].type == (
        "process_environment"
    )
    assert active.ssh.hosts["acceptance"].credential_binding is not None
    assert active.ssh.hosts["acceptance"].credential_binding.source_id == (
        "acceptance_source"
    )
    assert active.ssh.project_bindings["app_acceptance"].host_id == "acceptance"
    config_text = config_path.read_text(encoding="utf-8")
    assert secret_hostname not in config_text
    assert secret_user not in config_text
    assert str(identity_file.resolve()) not in config_text
    assert (runs_dir / "ssh_known_hosts" / "known_hosts").is_file()
    assert (
        runs_dir / "ssh_capabilities" / "acceptance" / "CURRENT.json"
    ).is_file()
    status = activation_status(runs_dir, change_id)
    assert status["state"] == "COMPLETED"
    assert status["project_validations"][0]["binding_id"] == "app_acceptance"


def test_prepare_failure_never_creates_activation_request_or_mutates_config(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = _base_config(tmp_path)
    original = config_path.read_bytes()
    change_id = _preview_add_host(config_path, runs_dir)
    result = run_ssh_profile_activation(
        config_path,
        runs_dir,
        change_id,
        "20260725T000000Z_ssh_profile_activation_deadbeef",
        adapter=FakeActivationAdapter(prepare_error="authentication failed"),
        coordinator_timeout_seconds=1,
    )

    assert result["ok"] is False
    assert result["activation_state"] == "ROLLED_BACK"
    assert result["rollback_verified"] is True
    assert config_path.read_bytes() == original
    assert not (
        activation_dir(runs_dir, change_id) / "activation_request.json"
    ).exists()


def test_server_reload_failure_restores_config_trust_and_pointer(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = _base_config(tmp_path)
    original_config = config_path.read_bytes()
    known_hosts = runs_dir / "ssh_known_hosts" / "known_hosts"
    known_hosts.parent.mkdir(parents=True)
    known_hosts.write_text("old.example ssh-ed25519 OLD\n", encoding="utf-8")
    pointer = runs_dir / "ssh_capabilities" / "candidate" / "CURRENT.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text('{"snapshot_id":"old"}\n', encoding="utf-8")
    original_known_hosts = known_hosts.read_bytes()
    original_pointer = pointer.read_bytes()

    change_id = _preview_add_host(config_path, runs_dir)
    holder: dict[str, Any] = {}
    thread = _run_worker_thread(
        config_path,
        runs_dir,
        change_id,
        FakeActivationAdapter(),
        holder,
    )
    _wait_for(activation_dir(runs_dir, change_id) / "activation_request.json")
    reload_calls: list[str] = []

    def fail_activation_then_restore(path: Path) -> dict[str, Any]:
        reload_calls.append(load_config(path).model_dump_json())
        if len(reload_calls) == 1:
            return {"ok": False, "error": "injected activation reload failure"}
        return {"ok": True, "status": "restored"}

    acknowledgement = reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=fail_activation_then_restore,
    )
    thread.join(timeout=10)

    assert acknowledgement["ok"] is False
    assert acknowledgement["rollback_verified"] is True
    assert holder["result"]["activation_state"] == "ROLLED_BACK"
    assert config_path.read_bytes() == original_config
    assert known_hosts.read_bytes() == original_known_hosts
    assert pointer.read_bytes() == original_pointer
    assert len(reload_calls) == 2


def test_post_activation_failure_requests_and_verifies_rollback(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = _base_config(tmp_path)
    original = config_path.read_bytes()
    change_id = _preview_add_host(config_path, runs_dir)
    holder: dict[str, Any] = {}
    thread = _run_worker_thread(
        config_path,
        runs_dir,
        change_id,
        FakeActivationAdapter(post_ok=False),
        holder,
    )
    tx_dir = activation_dir(runs_dir, change_id)
    _wait_for(tx_dir / "activation_request.json")
    reload_calls: list[str] = []
    reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=_reload_recorder(reload_calls),
    )
    _wait_for(tx_dir / "rollback_request.json")
    rollback = reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=_reload_recorder(reload_calls),
    )
    thread.join(timeout=10)

    assert rollback["ok"] is True
    assert rollback["rollback_verified"] is True
    assert holder["result"]["activation_state"] == "ROLLED_BACK"
    assert holder["result"]["error"] == "post-check failed"
    assert config_path.read_bytes() == original
    assert len(reload_calls) == 2


def test_tampered_staged_known_hosts_fails_and_restores_original(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = _base_config(tmp_path)
    original = config_path.read_bytes()
    change_id = _preview_add_host(config_path, runs_dir)
    holder: dict[str, Any] = {}
    thread = _run_worker_thread(
        config_path,
        runs_dir,
        change_id,
        FakeActivationAdapter(),
        holder,
    )
    tx_dir = activation_dir(runs_dir, change_id)
    request_path = tx_dir / "activation_request.json"
    _wait_for(request_path)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    Path(request["staged_known_hosts_path"]).write_text(
        "tampered ssh-ed25519 BAD\n", encoding="utf-8"
    )
    acknowledgement = reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=_reload_recorder([]),
    )
    thread.join(timeout=10)

    assert acknowledgement["ok"] is False
    assert acknowledgement["rollback_verified"] is True
    assert "hash mismatch" in acknowledgement["error"]
    assert holder["result"]["activation_state"] == "ROLLED_BACK"
    assert config_path.read_bytes() == original


def test_recovery_required_is_honest_when_rollback_reload_fails(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = _base_config(tmp_path)
    change_id = _preview_add_host(config_path, runs_dir)
    holder: dict[str, Any] = {}
    thread = _run_worker_thread(
        config_path,
        runs_dir,
        change_id,
        FakeActivationAdapter(),
        holder,
    )
    tx_dir = activation_dir(runs_dir, change_id)
    _wait_for(tx_dir / "activation_request.json")

    call_count = 0

    def always_fail(_path: Path) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"ok": False, "error": "reload unavailable"}

    acknowledgement = reconcile_ssh_activation_request(
        config_path,
        runs_dir,
        change_id,
        reload_callback=always_fail,
    )
    thread.join(timeout=10)

    assert call_count >= 2
    assert acknowledgement["ok"] is False
    assert acknowledgement["rollback_verified"] is False
    assert acknowledgement["status"] == "recovery_required"
    assert holder["result"]["activation_state"] == "RECOVERY_REQUIRED"
