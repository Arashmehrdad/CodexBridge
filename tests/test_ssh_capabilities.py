from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma import ssh_tools
from soma.config import AppConfig, RepoConfig, SSHConfig, SSHHostConfig
from soma.ssh_capabilities import (
    SSH_CAPABILITY_SCHEMA_VERSION,
    build_capability_snapshot_payload,
    capability_probe_specs,
    capability_snapshot_projection,
    persist_capability_snapshot,
    read_capability_snapshot,
)

FINGERPRINT = "SHA256:" + "D" * 43


def _result(
    *,
    ok: bool = True,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = None,
) -> dict[str, object]:
    return {
        "ok": ok,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": (0 if ok else 1) if exit_code is None else exit_code,
        "timed_out": False,
        "duration_seconds": 0.01,
        "output_truncated": False,
        "error": "" if ok else "unavailable",
    }


def _environment_probe(*, status: str = "ok", ok: bool = True) -> dict[str, object]:
    return {
        "ok": ok,
        "status": status,
        "environment": {
            "os": "Linux 6.8 x86_64",
            "working_directory": "/srv/project",
            "python": {"version": "3.12.4", "machine": "x86_64"},
            "torch": {"version": "2.7.0", "cuda_available": False},
            "cuda_compiler": "",
            "system_memory": {
                "total_bytes": 8_000_000_000,
                "free_bytes": 2_000_000_000,
            },
            "root_disk": {
                "filesystem": "ext4",
                "free_bytes": 100_000_000_000,
                "total_bytes": 200_000_000_000,
            },
        },
        "gpu": {
            "available": False,
            "device_count": 0,
            "devices": [],
        },
    }


def _capability_results() -> dict[str, dict[str, object]]:
    results = {spec.name: _result(ok=False) for spec in capability_probe_specs()}
    results.update(
        {
            "os_release": _result(
                stdout=(
                    'ID=ubuntu\nNAME="Ubuntu"\nVERSION_ID="24.04"\n'
                    'PRETTY_NAME="Ubuntu 24.04 LTS"\n'
                )
            ),
            "architecture": _result(stdout="x86_64\n"),
            "kernel": _result(stdout="Linux 6.8.0\n"),
            "effective_uid": _result(stdout="0\n"),
            "sudo_noninteractive": _result(),
            "timezone": _result(stdout="UTC+0000\n"),
            "locale": _result(stdout="LANG=en_US.UTF-8\nLC_ALL=\n"),
            "package_manager": _result(stdout="apt-get\n"),
            "shells": _result(
                stdout="shell=/bin/bash\nsh=/usr/bin/sh\nbash=/usr/bin/bash\npwsh=\n"
            ),
            "systemd": _result(stdout="systemd 255\n"),
            "docker": _result(stdout="Docker version 27.1.1\n"),
            "docker_compose": _result(stdout="Docker Compose version v2.29.1\n"),
            "git": _result(stdout="git version 2.45.2\n"),
            "python": _result(stdout="Python 3.12.4\n"),
            "curl": _result(stdout="curl 8.5.0\n"),
            "tar": _result(stdout="tar (GNU tar) 1.35\n"),
            "scp": _result(stdout="/usr/bin/scp\n"),
            "setsid": _result(stdout="setsid 2.39\n"),
        }
    )
    return results


def test_capability_probe_specs_are_fixed_and_unique() -> None:
    specs = capability_probe_specs()
    assert specs
    assert len({spec.name for spec in specs}) == len(specs)
    assert {"architecture", "kernel", "effective_uid"}.issubset(
        {spec.name for spec in specs if spec.required}
    )
    for spec in specs:
        assert isinstance(spec.argv, tuple)
        assert spec.argv
        assert 1 <= spec.timeout_seconds <= 60


def test_capability_payload_normalizes_tools_resources_and_requirements() -> None:
    payload = build_capability_snapshot_payload(
        host_id="production_vps",
        host_key_fingerprint=FINGERPRINT,
        endpoint_route="credential_binding",
        environment_probe=_environment_probe(),
        capability_probe_results=_capability_results(),
        required_capabilities=["docker", "docker_compose", "git", "systemd"],
    )

    assert payload["schema_version"] == SSH_CAPABILITY_SCHEMA_VERSION
    assert payload["status"] == "ok"
    assert payload["operating_system"]["pretty_name"] == "Ubuntu 24.04 LTS"
    assert payload["operating_system"]["architecture"] == "x86_64"
    assert payload["identity"] == {
        "effective_uid": 0,
        "root": True,
        "passwordless_sudo": True,
    }
    assert payload["tools"]["docker"]["available"] is True
    assert payload["tools"]["node"]["available"] is False
    assert payload["resources"]["system_memory"]["total_bytes"] == 8_000_000_000
    assert payload["required_capabilities_ok"] is True
    assert payload["missing_required_capabilities"] == []


def test_missing_and_unknown_required_capabilities_are_explicit() -> None:
    payload = build_capability_snapshot_payload(
        host_id="production_vps",
        host_key_fingerprint=FINGERPRINT,
        endpoint_route="credential_binding",
        environment_probe=_environment_probe(),
        capability_probe_results=_capability_results(),
        required_capabilities=["node", "future_runtime"],
    )

    assert payload["status"] == "partial"
    assert payload["required_capabilities_ok"] is False
    assert payload["missing_required_capabilities"] == ["node"]
    assert payload["unknown_required_capabilities"] == ["future_runtime"]
    assert payload["error"]


def test_unavailable_environment_marks_snapshot_unavailable() -> None:
    payload = build_capability_snapshot_payload(
        host_id="candidate",
        host_key_fingerprint="",
        endpoint_route="legacy",
        environment_probe=_environment_probe(status="unavailable", ok=False),
        capability_probe_results=_capability_results(),
    )
    assert payload["status"] == "unavailable"


def test_snapshot_persistence_projection_and_hash_verification(tmp_path: Path) -> None:
    payload = build_capability_snapshot_payload(
        host_id="production_vps",
        host_key_fingerprint=FINGERPRINT,
        endpoint_route="credential_binding",
        environment_probe=_environment_probe(),
        capability_probe_results=_capability_results(),
        required_capabilities=["docker", "git"],
    )
    projection = persist_capability_snapshot(tmp_path / "runs", payload)

    assert projection["ok"] is True
    assert projection["snapshot_id"]
    assert projection["snapshot_sha256"]
    assert projection["available_tools"] == sorted(projection["available_tools"])
    assert projection["memory_total_bytes"] == 8_000_000_000
    assert "checks" not in projection
    assert "working_directory" not in json.dumps(projection)

    full = read_capability_snapshot(
        tmp_path / "runs",
        host_id="production_vps",
        snapshot_id=projection["snapshot_id"],
    )
    assert full["snapshot_sha256"] == projection["snapshot_sha256"]
    assert full["environment"]["working_directory"] == "/srv/project"
    assert capability_snapshot_projection(full) == projection

    path = (
        tmp_path
        / "runs"
        / "ssh_capabilities"
        / "production_vps"
        / f"{projection['snapshot_id']}.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    record["package_manager"] = "tampered"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_capability_snapshot(
            tmp_path / "runs",
            host_id="production_vps",
            snapshot_id=projection["snapshot_id"],
        )


def test_ssh_tool_collector_reuses_existing_probe_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir="runs",
        config_dir=tmp_path,
        ssh=SSHConfig(
            enabled=True,
            hosts={
                "production_vps": SSHHostConfig(ssh_alias="production-alias")
            },
        ),
    )
    calls: dict[str, object] = {}

    def fake_run_specs(_config, host_id, specs):
        calls["host_id"] = host_id
        calls["spec_names"] = [spec.name for spec in specs]
        return _capability_results()

    monkeypatch.setattr(ssh_tools, "_run_probe_specs", fake_run_specs)
    monkeypatch.setattr(
        ssh_tools,
        "run_ssh_environment_probe",
        lambda _config, _host_id: _environment_probe(),
    )

    result = ssh_tools.run_ssh_capability_snapshot(
        config,
        "production_vps",
        host_key_fingerprint=FINGERPRINT,
        endpoint_route="active_alias",
        required_capabilities=["git", "systemd"],
    )

    assert result["ok"] is True
    assert result["writes_remote"] is False
    assert result["high_risk"] is False
    assert calls["host_id"] == "production_vps"
    assert "architecture" in calls["spec_names"]
    full = read_capability_snapshot(
        config.resolve_runs_dir(),
        host_id="production_vps",
        snapshot_id=result["snapshot_id"],
    )
    assert full["endpoint_route"] == "active_alias"
