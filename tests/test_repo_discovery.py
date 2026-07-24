from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from soma.config import (
    AppConfig,
    RepoConfig,
    resolve_repo,
    resolve_repo_identity,
)
from soma.repo_discovery import (
    canonical_repo_name,
    discover_repositories,
    discover_repository,
)


def make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    return path


def config_with_known_repo(root: Path, config_dir: Path) -> AppConfig:
    known = make_git_repo(root / "Known")
    return AppConfig(
        repos={"known": RepoConfig(path=str(known))}, config_dir=config_dir
    )


def test_canonical_repo_name_is_stable() -> None:
    assert canonical_repo_name("AI-Voice-Lead-Agent") == "ai_voice_lead_agent"
    assert canonical_repo_name("Wan2.2-local") == "wan2_2_local"
    assert canonical_repo_name("Andia_Beauty") == "andia_beauty"
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
    config = config_with_known_repo(root, tmp_path)

    new_repo = make_git_repo(root / "SeedMind")

    assert resolve_repo(config, "seedmind") == new_repo.resolve()
    assert "seedmind" in config.repos


def test_direct_child_repo_identity_is_discovered_without_explicit_entry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    wan_repo = make_git_repo(root / "Wan2.2")

    canonical_name, repo_path, repo_config = resolve_repo_identity(config, "Wan2.2")

    assert canonical_name == "wan2_2"
    assert repo_path == wan_repo.resolve()
    assert Path(repo_config.path).resolve() == wan_repo.resolve()


def test_andia_beauty_folder_and_canonical_names_resolve_same_repo(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    repo = make_git_repo(root / "Andia_Beauty")
    exact_directory_name = repo.name

    resolved = [
        resolve_repo(config, requested_name)
        for requested_name in (
            "Andia_Beauty",
            "andia_beauty",
            exact_directory_name,
        )
    ]

    assert resolved == [repo.resolve(), repo.resolve(), repo.resolve()]
    assert config.repos["andia_beauty"].path == str(repo.resolve())


def test_exact_folder_match_precedes_canonical_fallback(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    canonical_first = make_git_repo(root / "Andia-Beauty")
    exact = make_git_repo(root / "Andia.Beauty")

    exact_match = discover_repository(
        roots=[root], requested_name="Andia.Beauty", require_git=True
    )
    canonical_match = discover_repository(
        roots=[root], requested_name="andia_beauty", require_git=True
    )

    assert exact_match is not None
    assert exact_match.path == exact.resolve()
    assert canonical_match is not None
    assert canonical_match.path == canonical_first.resolve()


def test_folder_name_is_accepted_as_alias(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    repo = make_git_repo(root / "AI-Voice-Lead-Agent")

    assert resolve_repo(config, "AI-Voice-Lead-Agent") == repo.resolve()


def test_separator_alias_resolves_camelcase_sibling(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    repo = make_git_repo(root / "TradingLab")

    for alias in ("tradinglab", "trading-lab", "trading_lab", "trading lab"):
        assert resolve_repo(config, alias) == repo.resolve()

    assert config.repos["tradinglab"].path == str(repo.resolve())


def test_exact_canonical_match_wins_over_separator_insensitive_fallback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Github"
    exact_canonical = make_git_repo(root / "Trading-Lab")
    make_git_repo(root / "TradingLab")

    match = discover_repository(
        roots=[root], requested_name="trading_lab", require_git=True
    )

    assert match is not None
    assert match.path == exact_canonical.resolve()


def test_separator_alias_reports_matching_non_git_folder(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    (root / "TradingLab").mkdir()

    with pytest.raises(ValueError, match=r"TradingLab.*\.git is missing"):
        resolve_repo(config, "trading-lab")


def test_explicit_repo_keeps_priority(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    explicit = make_git_repo(root / "ExplicitSeedMind")
    make_git_repo(root / "seedmind")
    config = AppConfig(
        repos={"seedmind": RepoConfig(path=str(explicit))}, config_dir=tmp_path
    )

    assert resolve_repo(config, "seedmind") == explicit.resolve()


def test_matching_non_git_folder_reports_rejection_reason(tmp_path: Path) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    (root / "Andia_Beauty").mkdir()

    with pytest.raises(ValueError, match=r"Andia_Beauty.*\.git is missing"):
        resolve_repo(config, "andia_beauty")


def test_discovery_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "Github"
    config = config_with_known_repo(root, tmp_path)
    make_git_repo(root / "SeedMind")
    monkeypatch.setenv("SOMA_AUTO_DISCOVER_REPOS", "0")

    with pytest.raises(ValueError, match="Unknown repo_name"):
        resolve_repo(config, "seedmind")


def test_environment_root_allows_empty_static_repo_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "Github"
    repo = make_git_repo(root / "SeedMind")
    config = AppConfig(repos={}, config_dir=tmp_path)
    monkeypatch.setenv("SOMA_REPO_ROOTS", str(root))

    assert resolve_repo(config, "seedmind") == repo.resolve()
