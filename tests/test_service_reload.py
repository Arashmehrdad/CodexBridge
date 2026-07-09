from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

from codexbridge.service_reload import reload_service


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
        _list_ssh_capabilities=object(),
        _ssh_host_health=object(),
        _enrich_ssh_capabilities=object(),
        _run_ssh_inspection=object(),
    )
    monkeypatch.setitem(sys.modules, "codexbridge.server", fake_server)

    result = reload_service(
        config_path,
        modules=["ssh_commands", "ssh_tools"],
    )

    commands_module = sys.modules["codexbridge.ssh_commands"]
    tools_module = sys.modules["codexbridge.ssh_tools"]
    assert result["ok"] is True
    assert result["restart_required"] == []
    assert fake_server._list_ssh_capabilities is commands_module.list_ssh_capabilities
    assert fake_server._ssh_host_health is commands_module.ssh_host_health
    assert fake_server._enrich_ssh_capabilities is tools_module.enrich_ssh_capabilities
    assert fake_server._run_ssh_inspection is tools_module.run_ssh_inspection


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
