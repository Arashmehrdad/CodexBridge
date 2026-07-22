from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from soma.ssh_profile_manager import (
    apply_ssh_profile_change,
    get_ssh_profile_change_status,
    preview_ssh_profile_change,
)


def write_config(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "# prefix marker\n"
        "repos:\n"
        "  sample:\n"
        f"    path: '{repo.as_posix()}'\n"
        "runs_dir: runs\n"
        "ssh:\n"
        "  enabled: true\n"
        "  hosts:\n"
        "    alpha:\n"
        "      ssh_alias: alpha-host\n"
        "      connect_timeout_seconds: 15\n"
        "      command_profiles:\n"
        "        - command_id: status\n"
        "          argv: [uptime]\n"
        "          description: Current status\n"
        "# suffix marker\n"
        "dashboard:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )
    return config_path, tmp_path / "runs"


def manifest_path(runs_dir: Path, change_id: str) -> Path:
    return runs_dir / "ssh_profile_changes" / change_id / "manifest.json"


def test_preview_add_host_is_sanitized_and_persists_opaque_manifest(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = write_config(tmp_path)

    result = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "add_host",
        "beta",
        host_config={
            "ssh_alias": "beta-host",
            "command_profiles": [
                {
                    "command_id": "disk",
                    "argv": ["df", "-h"],
                    "description": "Disk usage",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert result["status"] == "previewed"
    assert result["capability_diff"]["hosts_added"] == ["beta"]
    assert "mutation" not in result
    assert "host_config" not in result
    assert "command_profile" not in result
    assert "argv" not in json.dumps(result)

    manifest = json.loads(
        manifest_path(runs_dir, result["change_id"]).read_text(encoding="utf-8")
    )
    assert manifest["mutation"]["host_id"] == "beta"
    assert "candidate_text" not in manifest
    assert "config_text" not in manifest


def test_apply_add_host_is_atomic_preserves_outside_text_and_is_idempotent(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = write_config(tmp_path)
    original = config_path.read_text(encoding="utf-8")
    prefix = original.split("ssh:\n", 1)[0]
    suffix = "dashboard:\n  enabled: false\n"
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "add_host",
        "beta",
        host_config={"ssh_alias": "beta-host"},
    )
    activations: list[Path] = []

    applied = apply_ssh_profile_change(
        config_path,
        runs_dir,
        preview["change_id"],
        activate=lambda path: activations.append(path) or {"ok": True, "status": "active"},
    )

    assert applied["ok"] is True
    assert applied["status"] == "applied"
    assert applied["idempotent_replay"] is False
    assert activations == [config_path.resolve()]
    updated = config_path.read_text(encoding="utf-8")
    assert updated.startswith(prefix)
    assert updated.endswith(suffix)
    parsed = yaml.safe_load(updated)
    assert parsed["ssh"]["hosts"]["beta"]["ssh_alias"] == "beta-host"

    replay = apply_ssh_profile_change(
        config_path,
        runs_dir,
        preview["change_id"],
        activate=lambda _path: pytest.fail("idempotent replay must not reactivate"),
    )
    assert replay["ok"] is True
    assert replay["idempotent_replay"] is True


def test_replace_and_remove_host_capability_diffs(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)
    replace = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "replace_host",
        "alpha",
        host_config={"ssh_alias": "new-alpha", "connect_timeout_seconds": 30},
    )
    changed = replace["capability_diff"]["hosts_changed"]
    assert [item["host_id"] for item in changed] == ["alpha"]
    assert changed[0]["before"]["ssh_alias"] == "alpha-host"
    assert changed[0]["after"]["ssh_alias"] == "new-alpha"

    remove = preview_ssh_profile_change(
        config_path, runs_dir, "remove_host", "alpha"
    )
    assert remove["capability_diff"]["hosts_removed"] == ["alpha"]


def test_upsert_and_remove_command_report_command_id_diffs(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)
    add = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "upsert_command",
        "alpha",
        command_id="disk",
        command_profile={
            "argv": ["df", "-h"],
            "description": "Disk usage",
            "writes_remote": False,
        },
    )
    changed = add["capability_diff"]["hosts_changed"][0]
    assert changed["commands_added"] == ["disk"]
    assert "argv" not in json.dumps(changed)

    remove = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "remove_command",
        "alpha",
        command_id="status",
    )
    changed = remove["capability_diff"]["hosts_changed"][0]
    assert changed["commands_removed"] == ["status"]


def test_upsert_replaces_command_in_place_and_marks_changed(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "upsert_command",
        "alpha",
        command_id="status",
        command_profile={
            "argv": ["df", "-h"],
            "description": "Different safe status",
            "timeout_seconds": 60,
        },
    )
    changed = preview["capability_diff"]["hosts_changed"][0]
    assert changed["commands_changed"] == ["status"]


def test_unsafe_command_profile_is_rejected_before_manifest_creation(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = write_config(tmp_path)

    with pytest.raises(ValueError, match="wrapper: bash"):
        preview_ssh_profile_change(
            config_path,
            runs_dir,
            "upsert_command",
            "alpha",
            command_id="unsafe",
            command_profile={"argv": ["bash", "-lc", "whoami"]},
        )

    assert not (runs_dir / "ssh_profile_changes").exists()


def test_preview_rejects_unsupported_fields_and_invalid_targets(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)

    with pytest.raises(ValueError, match="Unsupported host_config fields"):
        preview_ssh_profile_change(
            config_path,
            runs_dir,
            "add_host",
            "beta",
            host_config={"ssh_alias": "beta", "secret": "not-allowed"},
        )
    with pytest.raises(ValueError, match="already exists"):
        preview_ssh_profile_change(
            config_path,
            runs_dir,
            "add_host",
            "alpha",
            host_config={"ssh_alias": "duplicate"},
        )
    with pytest.raises(ValueError, match="Unknown SSH host_id"):
        preview_ssh_profile_change(
            config_path, runs_dir, "remove_host", "missing"
        )


def test_apply_rejects_stale_config_hash(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "add_host",
        "beta",
        host_config={"ssh_alias": "beta-host"},
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "# external change\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="changed since SSH profile preview"):
        apply_ssh_profile_change(config_path, runs_dir, preview["change_id"])


def test_apply_rejects_candidate_hash_tampering(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "add_host",
        "beta",
        host_config={"ssh_alias": "beta-host"},
    )
    path = manifest_path(runs_dir, preview["change_id"])
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["candidate_config_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="no longer matches its preview"):
        apply_ssh_profile_change(config_path, runs_dir, preview["change_id"])


def test_activation_failure_restores_original_config_and_marks_failed(
    tmp_path: Path,
) -> None:
    config_path, runs_dir = write_config(tmp_path)
    original = config_path.read_bytes()
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "add_host",
        "beta",
        host_config={"ssh_alias": "beta-host"},
    )

    result = apply_ssh_profile_change(
        config_path,
        runs_dir,
        preview["change_id"],
        activate=lambda _path: {"ok": False, "error": "simulated activation failure"},
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["restored_original"] is True
    assert config_path.read_bytes() == original
    status = get_ssh_profile_change_status(
        config_path, runs_dir, preview["change_id"]
    )
    assert status["ok"] is False
    assert status["status"] == "failed"
    assert "simulated activation failure" in status["error"]


def test_status_rejects_preview_for_different_config_path(tmp_path: Path) -> None:
    config_path, runs_dir = write_config(tmp_path)
    preview = preview_ssh_profile_change(
        config_path,
        runs_dir,
        "add_host",
        "beta",
        host_config={"ssh_alias": "beta-host"},
    )
    other = tmp_path / "other.yaml"
    other.write_bytes(config_path.read_bytes())

    with pytest.raises(ValueError, match="different config path"):
        get_ssh_profile_change_status(other, runs_dir, preview["change_id"])
