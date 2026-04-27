from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codexbridge.config import load_config, resolve_repo


def init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def test_config_example_loads_without_repo_validation() -> None:
    config = load_config("config.example.yaml", validate_repos=False)
    assert "stream_alpha" in config.repos
    assert config.codex.executable == "codex"


def test_unknown_repo_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"repos:\n  sample:\n    path: '{repo.as_posix()}'\nruns_dir: runs\n", encoding="utf-8")
    config = load_config(config_file)
    with pytest.raises(ValueError, match="Unknown repo_name"):
        resolve_repo(config, "missing")


def test_missing_repo_path_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("repos:\n  sample:\n    path: 'missing'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not exist"):
        load_config(config_file)


def test_repo_must_contain_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"repos:\n  sample:\n    path: '{repo.as_posix()}'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not contain .git"):
        load_config(config_file)

