from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.config import AppConfig, RepoConfig, resolve_repo
from codexbridge.repo_discovery import canonical_repo_name, discover_repositories


def make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    return path


def test_canonical_repo_name_is_stable() -> None:
    assert canonical_repo_name("AI-Voice-Lead-Agent") == "ai_voice_lead_agent"
    assert canonical_repo_name("Wan2.2-local") == "wan2_2_local"
    assert canonical_repo_name(" SeedMind ") == "seedmind"


def test_discovery_respects_depth_and_git_requirement(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    make_git_repo(root / "SeedMind")
    (root / "ordinary-folder").mkdir(parents=True)
    make_git_repo(root / "group" / "NestedRepo")

    immediate = discover_repositories(roots=[root], max_depth=1, require_git=True)
    nested = discover_repositories(roots=[root], max_depth=2, require_git=True)

    assert set(immediate) == {"seedmind"}
    assert set(nested) == {"nestedrepo", "seedmind"}


def test_new_sibling_repo_is_discovered_without_reload(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    known = make_git_repo(root / "Known")
    config = AppConfig(repos={"known": RepoConfig(path=str(known))}, config_dir=tmp_path)

    new_repo = make_git_repo(root / "SeedMind")

    assert resolve_repo(config, "seedmind") == new_repo.resolve()
    assert "seedmind" in config.repos


def test_folder_name_is_accepted_as_alias(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    known = make_git_repo(root / "Known")
    repo = make_git_repo(root / "AI-Voice-Lead-Agent")
    config = AppConfig(repos={"known": RepoConfig(path=str(known))}, config_dir=tmp_path)

    assert resolve_repo(config, "AI-Voice-Lead-Agent") == repo.resolve()


def test_explicit_repo_keeps_priority(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    explicit = make_git_repo(root / "ExplicitSeedMind")
    make_git_repo(root / "seedmind")
    config = AppConfig(repos={"seedmind": RepoConfig(path=str(explicit))}, config_dir=tmp_path)

    assert resolve_repo(config, "seedmind") == explicit.resolve()


def test_discovery_can_be_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "Github"
    known = make_git_repo(root / "Known")
    make_git_repo(root / "SeedMind")
    config = AppConfig(repos={"known": RepoConfig(path=str(known))}, config_dir=tmp_path)
    monkeypatch.setenv("CODEXBRIDGE_AUTO_DISCOVER_REPOS", "0")

    with pytest.raises(ValueError, match="Unknown repo_name"):
        resolve_repo(config, "seedmind")


def test_environment_root_allows_empty_static_repo_map(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "Github"
    repo = make_git_repo(root / "SeedMind")
    config = AppConfig(repos={}, config_dir=tmp_path)
    monkeypatch.setenv("CODEXBRIDGE_REPO_ROOTS", str(root))

    assert resolve_repo(config, "seedmind") == repo.resolve()
