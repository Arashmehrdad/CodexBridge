from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from soma import server
from soma.cf1_gateway_operation_inventory import operation_names_by_gateway
from soma.gateway_models import SSHQueryRequest
from soma import ssh_credentials
from soma.ssh_credentials import probe_ssh_credential_source


CANARY_HOST = "host-canary-7f42.example"
CANARY_USER = "user-canary-9a31"
CANARY_SECRET = "credential-canary-4c7d2e8f"
CANARY_FINGERPRINT = "SHA256:" + "A" * 43
KEY_FINGERPRINT = "SHA256:" + "B" * 43


def _write_key(path: Path) -> Path:
    path.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        f"{CANARY_SECRET}\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _safe_security(_path: Path) -> dict[str, object]:
    return {
        "ok": True,
        "git": {
            "inside_git_repository": False,
            "tracked": False,
            "ignored": False,
            "ok": True,
            "reason": "outside_git_repository",
        },
        "acl": {
            "checked": True,
            "broad_write": False,
            "broad_read": False,
            "ok": True,
            "reason": "ok",
        },
        "refusals": [],
        "warnings": [],
    }


def _patch_safe_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_credentials, "_file_security", _safe_security)
    monkeypatch.setattr(
        ssh_credentials,
        "_key_fingerprint",
        lambda _path: (KEY_FINGERPRINT, ""),
    )


def test_env_file_probe_maps_fields_and_never_persists_resolved_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_safe_key(monkeypatch)
    key = _write_key(tmp_path / "id_ed25519")
    source = tmp_path / "andia.env"
    source.write_text(
        f"ANDIA_SSH_HOST={CANARY_HOST}\n"
        f"ANDIA_SSH_USER={CANARY_USER}\n"
        "ANDIA_SSH_PORT=22\n"
        f"ANDIA_SSH_KEY_PATH={key}\n"
        f"ANDIA_SSH_HOST_KEY={CANARY_FINGERPRINT}\n"
        f"UNRELATED_TOKEN={CANARY_SECRET}\n",
        encoding="utf-8",
    )

    result = probe_ssh_credential_source(
        tmp_path / "runs",
        source_path=str(source.resolve()),
        source_type="auto",
        host_hint="andia",
    )

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["ready_for_binding"] is True
    assert result["source_type"] == "env_file"
    assert result["field_mapping"] == {
        "hostname": "ANDIA_SSH_HOST",
        "user": "ANDIA_SSH_USER",
        "port": "ANDIA_SSH_PORT",
        "identity_file": "ANDIA_SSH_KEY_PATH",
        "expected_host_key": "ANDIA_SSH_HOST_KEY",
    }
    assert result["key_file"]["public_key_fingerprint"] == KEY_FINGERPRINT
    assert result["source_basename"] == "andia.env"
    assert str(source.resolve()) not in json.dumps(result)

    manifest = (
        tmp_path
        / "runs"
        / "ssh_credential_sources"
        / result["probe_id"]
        / "manifest.json"
    ).read_text(encoding="utf-8")
    combined = json.dumps(result, sort_keys=True) + manifest
    for resolved_value in (
        CANARY_HOST,
        CANARY_USER,
        CANARY_SECRET,
        CANARY_FINGERPRINT,
        str(key),
    ):
        assert resolved_value not in combined
    assert "ANDIA_SSH_HOST" in combined
    assert "ANDIA_SSH_KEY_PATH" in combined


def test_process_environment_probe_is_scoped_and_does_not_echo_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_safe_key(monkeypatch)
    key = _write_key(tmp_path / "process_key")
    environment = {
        "ANDIA_SSH_HOST": CANARY_HOST,
        "ANDIA_SSH_USER": CANARY_USER,
        "ANDIA_SSH_PORT": "2202",
        "ANDIA_SSH_KEY_PATH": str(key),
        "UNRELATED_TOKEN": CANARY_SECRET,
    }

    result = probe_ssh_credential_source(
        tmp_path / "runs",
        source_type="process_environment",
        host_hint="andia",
        environment=environment,
    )

    assert result["ready_for_binding"] is True
    assert "UNRELATED_TOKEN" not in result["discovered_names"]
    manifest = (
        tmp_path
        / "runs"
        / "ssh_credential_sources"
        / result["probe_id"]
        / "manifest.json"
    ).read_text(encoding="utf-8")
    combined = json.dumps(result, sort_keys=True) + manifest
    assert CANARY_HOST not in combined
    assert CANARY_USER not in combined
    assert CANARY_SECRET not in combined
    assert str(key) not in combined


def test_environment_mapping_reports_ambiguity_without_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_safe_key(monkeypatch)
    key = _write_key(tmp_path / "ambiguous_key")
    source = tmp_path / "ambiguous.env"
    source.write_text(
        f"A_SSH_HOST={CANARY_HOST}\n"
        "B_SSH_HOST=other.example\n"
        f"SSH_USER={CANARY_USER}\n"
        f"SSH_KEY_PATH={key}\n",
        encoding="utf-8",
    )

    result = probe_ssh_credential_source(
        tmp_path / "runs",
        source_path=str(source.resolve()),
        source_type="env_file",
    )

    assert result["status"] == "incomplete"
    assert result["ready_for_binding"] is False
    assert result["ambiguous_fields"]["hostname"] == ["A_SSH_HOST", "B_SSH_HOST"]
    assert "hostname" not in result["field_mapping"]


def test_field_override_resolves_ambiguity_and_missing_override_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_safe_key(monkeypatch)
    key = _write_key(tmp_path / "override_key")
    source = tmp_path / "override.env"
    source.write_text(
        f"PRIMARY_HOST={CANARY_HOST}\n"
        "SECONDARY_HOST=other.example\n"
        f"SSH_USER={CANARY_USER}\n"
        f"SSH_KEY_PATH={key}\n",
        encoding="utf-8",
    )

    result = probe_ssh_credential_source(
        tmp_path / "runs",
        source_path=str(source.resolve()),
        source_type="env_file",
        field_overrides={"hostname": "PRIMARY_HOST"},
    )
    assert result["ready_for_binding"] is True
    assert result["field_mapping"]["hostname"] == "PRIMARY_HOST"

    with pytest.raises(ValueError, match="unavailable variable"):
        probe_ssh_credential_source(
            tmp_path / "runs",
            source_path=str(source.resolve()),
            source_type="env_file",
            field_overrides={"hostname": "MISSING_HOST"},
        )


def test_auto_detected_key_file_is_safe_but_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_safe_key(monkeypatch)
    key = _write_key(tmp_path / "id_agent")

    result = probe_ssh_credential_source(
        tmp_path / "runs",
        source_path=str(key.resolve()),
        source_type="auto",
    )

    assert result["source_type"] == "key_file"
    assert result["status"] == "incomplete"
    assert result["missing_fields"] == ["hostname", "user"]
    assert result["key_file"]["public_key_fingerprint"] == KEY_FINGERPRINT
    assert CANARY_SECRET not in json.dumps(result)


def test_unignored_credential_source_inside_git_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = shutil.which("git")
    if not git:
        pytest.skip("git is unavailable")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run([git, "init", "-q", str(repo)], check=True)
    key = _write_key(tmp_path / "outside_key")
    monkeypatch.setattr(
        ssh_credentials,
        "_key_fingerprint",
        lambda _path: (KEY_FINGERPRINT, ""),
    )
    source = repo / "server.env"
    source.write_text(
        f"SSH_HOST={CANARY_HOST}\n"
        f"SSH_USER={CANARY_USER}\n"
        f"SSH_KEY_PATH={key}\n",
        encoding="utf-8",
    )

    result = probe_ssh_credential_source(
        tmp_path / "runs",
        source_path=str(source.resolve()),
        source_type="env_file",
    )

    assert result["ok"] is False
    assert result["status"] == "refused"
    assert "secret_source_inside_git_is_not_ignored" in result["refusals"]


def test_probe_rejects_symlinked_source(tmp_path: Path) -> None:
    target = tmp_path / "target.env"
    target.write_text("SSH_HOST=example.test\n", encoding="utf-8")
    link = tmp_path / "link.env"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")

    with pytest.raises(ValueError, match="regular non-link file"):
        probe_ssh_credential_source(
            tmp_path / "runs",
            source_path=str(link.absolute()),
            source_type="env_file",
        )


def test_credential_probe_gateway_model_is_strict() -> None:
    adapter = TypeAdapter(SSHQueryRequest)
    request = adapter.validate_python(
        {
            "operation": "credential_probe",
            "source_path": "C:/Users/owner/credentials.env",
            "source_type": "env_file",
            "field_overrides": {"hostname": "SSH_HOST"},
        }
    )
    assert request.operation == "credential_probe"

    with pytest.raises(ValidationError, match="does not accept source_path"):
        adapter.validate_python(
            {
                "operation": "credential_probe",
                "source_type": "process_environment",
                "source_path": "C:/wrong.env",
            }
        )
    with pytest.raises(ValidationError, match="Unsupported SSH credential field"):
        adapter.validate_python(
            {
                "operation": "credential_probe",
                "source_path": "C:/credentials.env",
                "field_overrides": {"password": "SSH_PASSWORD"},
            }
        )


def test_server_credential_probe_delegates_and_compact_projection_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_probe(source_path, source_type, host_hint, field_overrides):
        captured.update(
            {
                "source_path": source_path,
                "source_type": source_type,
                "host_hint": host_hint,
                "field_overrides": field_overrides,
            }
        )
        return {
            "ok": True,
            "probe_id": "20260725T000000Z_sshcred_deadbeef",
            "status": "ready",
            "ready_for_binding": True,
            "source_type": "env_file",
            "source_basename": "server.env",
            "source_path_identity_sha256": "a" * 64,
            "source_version_sha256": "b" * 64,
            "discovered_names": [f"HOST_{index:04d}" for index in range(500)],
            "field_mapping": {"hostname": "HOST_0000"},
            "field_candidates": {"hostname": [f"HOST_{index:04d}" for index in range(500)]},
            "missing_fields": [],
            "ambiguous_fields": {},
            "endpoint_validation": {"hostname_valid": True},
            "key_file": {"ok": True, "public_key_fingerprint": KEY_FINGERPRINT},
            "refusals": [],
            "warnings": [],
            "created_at": "2026-07-25T00:00:00Z",
            "error": "",
        }

    monkeypatch.setattr(server, "probe_ssh_credential_source", fake_probe)
    request = TypeAdapter(SSHQueryRequest).validate_python(
        {
            "operation": "credential_probe",
            "source_path": "C:/credentials.env",
            "source_type": "env_file",
            "host_hint": "production",
            "response_budget_bytes": 2048,
        }
    )
    result = server.ssh_query(request)

    assert captured["source_path"] == "C:/credentials.env"
    assert captured["source_type"] == "env_file"
    assert captured["host_hint"] == "production"
    assert result["probe_id"].endswith("deadbeef")
    assert result["field_mapping"] == {"hostname": "HOST_0000"}
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 2048


def test_server_internal_probe_uses_runs_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(server, "_get_runs_dir", lambda: tmp_path / "runs")

    def fake_probe(runs_dir, **kwargs):
        captured["runs_dir"] = runs_dir
        captured.update(kwargs)
        return {"ok": True, "probe_id": "probe"}

    monkeypatch.setattr(server, "_probe_ssh_credential_source", fake_probe)
    result = server.probe_ssh_credential_source(
        "C:/credentials.env",
        "env_file",
        "production",
        {"hostname": "SSH_HOST"},
    )

    assert result == {"ok": True, "probe_id": "probe"}
    assert captured["runs_dir"] == tmp_path / "runs"
    assert captured["field_overrides"] == {"hostname": "SSH_HOST"}


def test_authoritative_operation_inventory_includes_credential_probe() -> None:
    assert "credential_probe" in operation_names_by_gateway()["ssh_query"]
