from __future__ import annotations

from pathlib import Path

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
