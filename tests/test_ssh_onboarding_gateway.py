from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

import soma.server as server
from soma import ssh_tools
from soma.config import (
    AppConfig,
    RepoConfig,
    SSHConfig,
    SSHHostConfig,
    SSHProjectBindingConfig,
)
from soma.gateway_models import SSHActionRequest, SSHQueryRequest
from soma.ssh_capabilities import capability_snapshot_projection


def test_profile_preview_model_requires_atomic_configure_host_inputs() -> None:
    request = TypeAdapter(SSHQueryRequest).validate_python(
        {
            "operation": "profile_preview",
            "action": "configure_host",
            "host_id": "production",
            "host_config": {
                "credential_binding": {"source_id": "production_source"}
            },
            "credential_source_id": "production_source",
            "credential_source": {"type": "env_file", "path": ".env.ssh"},
            "project_bindings": {
                "app_production": {
                    "repo_name": "app",
                    "remote_root": "/srv/app",
                }
            },
            "activation_intent": "new_host",
        }
    )

    assert request.action == "configure_host"
    assert request.credential_source_id == "production_source"
    assert request.activation_intent == "new_host"

    with pytest.raises(ValidationError, match="requires credential_source_id"):
        TypeAdapter(SSHQueryRequest).validate_python(
            {
                "operation": "profile_preview",
                "action": "configure_host",
                "host_id": "production",
                "host_config": {"credential_binding": {"source_id": "missing"}},
            }
        )
    with pytest.raises(ValidationError, match="require action=configure_host"):
        TypeAdapter(SSHQueryRequest).validate_python(
            {
                "operation": "profile_preview",
                "action": "add_host",
                "host_id": "production",
                "credential_source_id": "unexpected",
            }
        )


def test_capability_and_binding_query_models_are_strict() -> None:
    snapshot = TypeAdapter(SSHQueryRequest).validate_python(
        {
            "operation": "capability_snapshot",
            "host_id": "production",
            "required_capabilities": ["docker", "root"],
        }
    )
    assert snapshot.required_capabilities == ["docker", "root"]
    assert TypeAdapter(SSHQueryRequest).validate_python(
        {"operation": "project_bindings", "host_id": "production"}
    ).host_id == "production"
    assert TypeAdapter(SSHQueryRequest).validate_python(
        {
            "operation": "project_binding_validation",
            "binding_id": "app_production",
        }
    ).binding_id == "app_production"

    with pytest.raises(ValidationError, match="only when collecting"):
        TypeAdapter(SSHQueryRequest).validate_python(
            {
                "operation": "capability_snapshot",
                "host_id": "production",
                "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
                "required_capabilities": ["docker"],
            }
        )


def test_ssh_query_forwards_atomic_profile_preview_fields(monkeypatch) -> None:
    captured: dict[str, tuple[object, ...]] = {}

    def fake_preview(*args: object) -> dict[str, object]:
        captured["args"] = args
        return {"ok": True, "status": "previewed", "change_id": "change_1"}

    monkeypatch.setattr(server, "preview_ssh_profile_change", fake_preview)
    request = TypeAdapter(SSHQueryRequest).validate_python(
        {
            "operation": "profile_preview",
            "action": "configure_host",
            "host_id": "production",
            "host_config": {"credential_binding": {"source_id": "source_1"}},
            "credential_source_id": "source_1",
            "credential_source": {"type": "process_environment"},
            "project_bindings": {"app": {"remote_root": "/srv/app"}},
            "activation_intent": "existing_host",
            "view": "full",
        }
    )

    result = server.ssh_query(request)

    assert result["change_id"] == "change_1"
    args = captured["args"]
    assert args[0:2] == ("configure_host", "production")
    assert args[5] == "source_1"
    assert args[6] == {"type": "process_environment"}
    assert args[7] == {"app": {"remote_root": "/srv/app"}}
    assert args[8] == "existing_host"


def test_ssh_query_collects_and_reads_capability_snapshots(
    monkeypatch, tmp_path: Path
) -> None:
    projection = {
        "ok": True,
        "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
        "snapshot_sha256": "a" * 64,
        "schema_version": "ssh-capability-snapshot.v1",
        "host_id": "production",
        "status": "ok",
        "collected_at": "2026-07-25T00:00:00+00:00",
        "available_tools": ["docker", "git"],
        "available_capabilities": ["docker", "git", "root"],
        "required_capabilities": ["docker"],
        "required_capabilities_ok": True,
        "missing_required_capabilities": [],
        "unknown_required_capabilities": [],
        "memory_total_bytes": 1024,
        "root_disk_free_bytes": 2048,
        "gpu_available": False,
        "gpu_device_count": 0,
        "error": "",
    }
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(server, "_get_runs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        server,
        "_run_ssh_capability_snapshot",
        lambda *args, **kwargs: dict(projection),
    )

    compact = server.ssh_query(
        TypeAdapter(SSHQueryRequest).validate_python(
            {
                "operation": "capability_snapshot",
                "host_id": "production",
                "required_capabilities": ["docker"],
                "response_budget_bytes": 4096,
            }
        )
    )
    assert compact["snapshot_id"] == projection["snapshot_id"]
    assert compact["available_capabilities"] == ["docker", "git", "root"]
    assert compact["response_bytes"] <= 4096

    full_record = {**projection, "checks": {"docker": {"ok": True}}}
    monkeypatch.setattr(
        server,
        "_read_ssh_capability_snapshot",
        lambda *args, **kwargs: dict(full_record),
    )
    full = server.ssh_query(
        TypeAdapter(SSHQueryRequest).validate_python(
            {
                "operation": "capability_snapshot",
                "host_id": "production",
                "snapshot_id": projection["snapshot_id"],
                "view": "full",
            }
        )
    )
    assert full["checks"]["docker"]["ok"] is True


def test_ssh_query_filters_bindings_and_delegates_validation(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_list_ssh_project_bindings",
        lambda _config: [
            {
                "binding_id": "app_prod",
                "host_id": "production",
                "repo_name": "app",
                "source": "canonical",
                "remote_root": "/srv/app",
                "required_capabilities": ["docker"],
                "allow_first_deployment": False,
                "health_command_id": "health",
            },
            {
                "binding_id": "app_stage",
                "host_id": "staging",
                "repo_name": "app",
                "source": "canonical",
                "remote_root": "/srv/app-stage",
                "required_capabilities": [],
                "allow_first_deployment": False,
                "health_command_id": "",
            },
        ],
    )
    bindings = server.ssh_query(
        TypeAdapter(SSHQueryRequest).validate_python(
            {"operation": "project_bindings", "host_id": "production"}
        )
    )
    assert bindings["binding_count"] == 1
    assert bindings["bindings"][0]["binding_id"] == "app_prod"

    calls: list[tuple[object, ...]] = []

    def fake_validate(
        config: object,
        binding_id: str,
        *,
        host_id: str,
        capability_snapshot_id: str,
    ) -> dict[str, object]:
        calls.append((config, binding_id, host_id, capability_snapshot_id))
        return {
            "ok": True,
            "status": "preparation_required",
            "binding_id": binding_id,
            "host_id": host_id or "production",
            "repo_name": "app",
            "failed_checks": [],
            "preparation_required_checks": ["remote_root_exists"],
            "checks": [
                {
                    "name": "remote_root_exists",
                    "state": "preparation_required",
                    "required": True,
                    "preparation_allowed": True,
                    "exit_code": 1,
                    "timed_out": False,
                    "error": "missing",
                }
            ],
            "writes_remote": False,
            "high_risk": False,
            "error": "",
        }

    monkeypatch.setattr(server, "_run_ssh_project_binding_validation", fake_validate)
    validation = server.ssh_query(
        TypeAdapter(SSHQueryRequest).validate_python(
            {
                "operation": "project_binding_validation",
                "binding_id": "app_prod",
                "host_id": "production",
                "capability_snapshot_id": "20260725T000000Z_sshcap_deadbeef",
            }
        )
    )
    assert validation["status"] == "preparation_required"
    assert validation["preparation_required_checks"] == ["remote_root_exists"]
    assert calls[0][1:] == (
        "app_prod",
        "production",
        "20260725T000000Z_sshcap_deadbeef",
    )


def test_profile_apply_compact_response_preserves_durable_polling(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "apply_ssh_profile_change",
        lambda change_id: {
            "accepted": True,
            "status": "queued",
            "run_id": "run_activation_1",
            "repo_name": "__soma_config__",
            "change_id": change_id,
            "host_id": "production",
            "activation_intent": "rotation",
            "risk_level": "high",
            "requires_human": False,
            "reason": "accepted",
            "duplicate": False,
            "error": "",
        },
    )
    result = server.ssh_action(
        TypeAdapter(SSHActionRequest).validate_python(
            {"action": "profile_apply", "change_id": "change_1"}
        )
    )

    assert result["ok"] is True
    assert result["run_id"] == "run_activation_1"
    assert result["polling"]["request"] == {
        "operation": "control",
        "run_id": "run_activation_1",
    }
    assert result["evidence"]["request"]["operation"] == "terminal"


def test_snapshot_projection_and_binding_validator_include_non_tool_capabilities(
    tmp_path: Path, monkeypatch
) -> None:
    projection = capability_snapshot_projection(
        {
            "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
            "snapshot_sha256": "a" * 64,
            "schema_version": "ssh-capability-snapshot.v1",
            "host_id": "production",
            "status": "ok",
            "required_capabilities_ok": True,
            "identity": {"root": True, "passwordless_sudo": True},
            "process_group_controls": True,
            "tools": {"git": {"available": True}},
            "resources": {},
            "operating_system": {},
        }
    )
    assert {"root", "passwordless_sudo", "process_group_controls"}.issubset(
        set(projection["available_capabilities"])
    )

    config = AppConfig(
        repos={"app": RepoConfig(path=str(tmp_path / "app"))},
        config_dir=tmp_path,
        runs_dir="runs",
        ssh=SSHConfig(
            enabled=True,
            hosts={"production": SSHHostConfig(ssh_alias="production")},
            project_bindings={
                "app_prod": SSHProjectBindingConfig(
                    host_id="production",
                    repo_name="app",
                    remote_root="/srv/app",
                    required_capabilities=["root"],
                )
            },
        ),
    )
    monkeypatch.setattr(
        ssh_tools,
        "run_ssh_capability_snapshot",
        lambda *args, **kwargs: {
            "ok": True,
            "snapshot_id": "20260725T000000Z_sshcap_deadbeef",
            "available_tools": [],
            "available_capabilities": ["root"],
            "required_capabilities_ok": True,
            "missing_required_capabilities": [],
            "unknown_required_capabilities": [],
        },
    )

    def fake_specs(_config, _host_id, specs):
        return {
            spec.name: {
                "ok": True,
                "exit_code": 0,
                "timed_out": False,
                "error": "",
            }
            for spec in specs
        }

    monkeypatch.setattr(ssh_tools, "_run_probe_specs", fake_specs)
    result = ssh_tools.run_ssh_project_binding_validation(config, "app_prod")

    assert result["ok"] is True
    assert result["status"] == "valid"
    assert result["writes_remote"] is False
    assert result["high_risk"] is False
