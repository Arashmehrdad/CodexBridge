from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from codexbridge.config import AppConfig, RepoConfig, SupervisorAutonomyProfile, SupervisorsConfig, load_config, resolve_repo


def init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def test_config_example_loads_without_repo_validation() -> None:
    config = load_config("config.example.yaml", validate_repos=False)
    assert "stream_alpha" in config.repos
    assert config.codex.executable == "codex"
    assert config.supervisors.default_autonomy_profile == "balanced"
    assert config.supervisors.effective_profile().max_implementation_tier == 2


def test_config_defaults_to_balanced_supervisor_profile(tmp_path: Path) -> None:
    config = AppConfig(repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path)
    assert config.supervisors.default_autonomy_profile == "balanced"
    assert config.supervisors.effective_profile().stop_on_requires_human is True


def test_config_loads_named_supervisor_profiles(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        supervisors=SupervisorsConfig(
            default_autonomy_profile="custom",
            autonomy_profiles={
                "custom": SupervisorAutonomyProfile(max_plan_tier=1, max_implementation_tier=1),
            },
        ),
        config_dir=tmp_path,
    )
    assert config.supervisors.effective_profile().max_implementation_tier == 1


def test_unknown_default_supervisor_profile_rejected() -> None:
    with pytest.raises(ValidationError):
        SupervisorsConfig(default_autonomy_profile="missing", autonomy_profiles={"balanced": SupervisorAutonomyProfile()})


def test_invalid_supervisor_profile_values_rejected() -> None:
    with pytest.raises(ValidationError):
        SupervisorAutonomyProfile(max_plan_tier=0)


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
