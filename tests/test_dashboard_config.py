from __future__ import annotations

from pathlib import Path

from codexbridge.config import AppConfig, DashboardConfig, RepoConfig


def test_dashboard_config_defaults_are_read_only(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )

    assert isinstance(config.dashboard, DashboardConfig)
    assert config.dashboard.dashboard_enabled is True
    assert config.dashboard.dashboard_host == "127.0.0.1"
    assert config.dashboard.dashboard_port == 8765
    assert config.dashboard.dashboard_read_only is True
    assert config.dashboard.dashboard_artifact_only_repo_status is True
    assert config.resolve_dashboard_runs_dir() == tmp_path / "runs"
