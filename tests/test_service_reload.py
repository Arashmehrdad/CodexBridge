from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from codexbridge.service_reload import (
    apply_reloaded_config,
    get_reload_status,
    reload_service,
    rollback_service,
    validate_config_candidate,
)
from codexbridge.repo_discovery_integration import (
    _install_server_binding,
    resolve_repo_identity_with_discovery,
)


def test_reload_service_reloads_config_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path.write_text(
        f"repos:\n  sample:\n    path: '{repo.as_posix()}'\n",
        encoding="utf-8",
    )

    result = reload_service(config_path, modules=["config"])

    assert result["ok"] is True
    assert "config" in result["reloaded"]


def test_reload_service_rebinds_server_ssh_helpers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path.write_text(
        f"repos:\n  sample:\n    path: '{repo.as_posix()}'\n",
        encoding="utf-8",
    )
    fake_server = SimpleNamespace(
        JobManager=object(),
        _list_ssh_capabilities=object(),
        _ssh_host_health=object(),
        _enrich_ssh_capabilities=object(),
        _run_ssh_environment_probe=object(),
        _run_ssh_gpu_telemetry=object(),
        _run_ssh_inspection=object(),
        start_ssh_monitored_command_async=lambda host_id, command_id: {
            "host_id": host_id,
            "command_id": command_id,
        },
    )
    monkeypatch.setitem(sys.modules, "codexbridge.server", fake_server)

    result = reload_service(
        config_path,
        modules=["ssh_commands", "ssh_tools", "job_manager"],
    )

    commands_module = sys.modules["codexbridge.ssh_commands"]
    tools_module = sys.modules["codexbridge.ssh_tools"]
    job_manager_module = sys.modules["codexbridge.job_manager"]
    assert result["ok"] is True
    assert result["restart_required"] == []
    assert fake_server._list_ssh_capabilities is commands_module.list_ssh_capabilities
    assert fake_server._ssh_host_health is commands_module.ssh_host_health
    assert fake_server._enrich_ssh_capabilities is tools_module.enrich_ssh_capabilities
    assert (
        fake_server._run_ssh_environment_probe is tools_module.run_ssh_environment_probe
    )
    assert fake_server._run_ssh_gpu_telemetry is tools_module.run_ssh_gpu_telemetry
    assert fake_server._run_ssh_inspection is tools_module.run_ssh_inspection
    assert fake_server.JobManager is job_manager_module.JobManager


def test_reload_binding_covers_python_module_main_server(monkeypatch) -> None:
    fake_main = ModuleType("__main__")
    fake_main.mcp = object()
    fake_main.resolve_repo_identity = object()
    monkeypatch.setitem(sys.modules, "__main__", fake_main)

    _install_server_binding()

    assert fake_main.resolve_repo_identity is resolve_repo_identity_with_discovery


def test_reload_service_marks_unreloadable_modules_restart_required(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path.write_text(
        f"repos:\n  sample:\n    path: '{repo.as_posix()}'\n",
        encoding="utf-8",
    )

    result = reload_service(config_path, modules=["server"])

    assert result["ok"] is False
    assert result["restart_required"] == ["codexbridge.server"]


def test_invalid_candidate_does_not_replace_last_known_good(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path.write_text(
        f"repos:\n  sample:\n    path: '{repo.as_posix()}'\n",
        encoding="utf-8",
    )
    active = apply_reloaded_config(config_path)
    assert Path(active.repos["sample"].path).resolve() == repo.resolve()

    config_path.write_text(
        "repos:\n  sample:\n    path: 'missing'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        validate_config_candidate(config_path)

    status = get_reload_status()
    lifecycle = status["config_lifecycle"]
    assert lifecycle["has_last_known_good_config"] is True
    assert Path(lifecycle["active_config_path"]).resolve() == config_path.resolve()


def test_reload_status_and_rollback_restore_previous_config(tmp_path: Path) -> None:
    repo_one = tmp_path / "repo_one"
    repo_two = tmp_path / "repo_two"
    repo_one.mkdir()
    repo_two.mkdir()
    (repo_one / ".git").mkdir()
    (repo_two / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"repos:\n  sample:\n    path: '{repo_one.as_posix()}'\n",
        encoding="utf-8",
    )

    first = apply_reloaded_config(config_path)
    assert Path(first.repos["sample"].path).resolve() == repo_one.resolve()

    config_path.write_text(
        f"repos:\n  sample:\n    path: '{repo_two.as_posix()}'\n",
        encoding="utf-8",
    )
    reloaded = reload_service(config_path, modules=["config"])
    assert reloaded["ok"] is True
    assert reloaded["config_lifecycle"]["has_previous_config"] is True

    rolled_back = rollback_service()
    assert rolled_back["ok"] is True
    restored = rolled_back["config"]
    assert Path(restored.repos["sample"].path).resolve() == repo_one.resolve()
