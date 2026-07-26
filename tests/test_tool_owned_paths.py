from __future__ import annotations

from pathlib import Path

import pytest

from soma import git_tools
from soma.repo_wiki import RepoWikiService
from soma.tool_owned_paths import TOOL_OWNED_PREFIXES, is_tool_owned_path


@pytest.mark.parametrize(
    "path",
    [
        ".codex-tmp",
        ".codex-tmp/scratch.txt",
        ".codex-tmp/cf1-performance-200-1/runs/result.json",
        ".claude/worktrees/feature-x/main.py",
        "_pytest-cf1-temp/case0/config.yaml",
        ".pytest_cache/v/cache/nodeids",
        ".ruff_cache/content.json",
        "tests/pytest_tmp_probe/probe.txt",
    ],
)
def test_tool_owned_paths_are_recognized(path: str) -> None:
    assert is_tool_owned_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "soma/server.py",
        "AGENTS.md",
        ".claude/settings.json",
        ".claude/skills/example/SKILL.md",
        ".codex-tmp-notes.md",
        "tests/test_server.py",
        "docs/.codex-tmpish/file.md",
    ],
)
def test_owner_authored_paths_are_not_tool_owned(path: str) -> None:
    assert is_tool_owned_path(path) is False


def test_claude_config_is_kept_while_worktrees_are_excluded() -> None:
    """.claude holds real project configuration; only worktrees are scratch."""
    assert is_tool_owned_path(".claude/settings.json") is False
    assert is_tool_owned_path(".claude/worktrees/x/file.py") is True


def test_git_tools_and_wiki_share_one_definition() -> None:
    # Divergence between these two is what let .codex-tmp be tool-owned for
    # commit manifests while still being indexed as repository knowledge.
    assert git_tools.TOOL_OWNED_PREFIXES is TOOL_OWNED_PREFIXES
    assert git_tools._is_tool_owned_path(".claude/worktrees/a/b.py") is True


def _wiki(repo: Path) -> RepoWikiService:
    return RepoWikiService(repo, "sample")


def test_wiki_excludes_tool_owned_paths_from_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".codex-tmp" / "nested").mkdir(parents=True)
    (repo / ".codex-tmp" / "nested" / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    (repo / ".claude" / "worktrees" / "wt").mkdir(parents=True)
    (repo / ".claude" / "worktrees" / "wt" / "mod.py").write_text("y = 2\n", encoding="utf-8")
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (repo / "soma").mkdir()
    (repo / "soma" / "real.py").write_text("z = 3\n", encoding="utf-8")

    service = _wiki(repo)

    assert service._is_source_candidate(repo / "soma" / "real.py") is True
    assert service._is_source_candidate(repo / ".claude" / "settings.json") is True
    assert (
        service._is_source_candidate(repo / ".codex-tmp" / "nested" / "scratch.py")
        is False
    )
    assert (
        service._is_source_candidate(repo / ".claude" / "worktrees" / "wt" / "mod.py")
        is False
    )


def test_wiki_relative_path_exclusion_matches_prefixes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = _wiki(repo)

    assert service._is_excluded_relative_path(".codex-tmp/a/b.txt") is True
    assert service._is_excluded_relative_path("_pytest-cf1-temp/x.yaml") is True
    assert service._is_excluded_relative_path(".claude/worktrees/w/m.py") is True
    assert service._is_excluded_relative_path(".claude/settings.json") is False
    assert service._is_excluded_relative_path("soma/server.py") is False
