from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from soma.reasoning.git_snapshot import GitCommitSourceLoader
from soma.reasoning.repository_evidence import RepositoryEvidenceError


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "soma@example.invalid")
    _git(root, "config", "user.name", "Soma Test")
    (root / "sample.txt").write_text("frozen\ncontent\n", encoding="utf-8")
    _git(root, "add", "sample.txt")
    _git(root, "commit", "-m", "fixture")
    return root, _git(root, "rev-parse", "HEAD")


def test_loader_resolves_exact_commit_and_ignores_worktree_changes(tmp_path: Path) -> None:
    root, commit = _repo(tmp_path)
    loader = GitCommitSourceLoader(root, "HEAD")
    (root / "sample.txt").write_text("changed\nworktree\n", encoding="utf-8")

    assert loader.source_commit == commit.lower()
    assert loader.source_revision_ref == f"git:{commit.lower()}"
    assert loader.load("sample.txt") == b"frozen\ncontent\n"


def test_loader_rejects_unknown_revision_or_path(tmp_path: Path) -> None:
    root, _commit = _repo(tmp_path)
    with pytest.raises(RepositoryEvidenceError):
        GitCommitSourceLoader(root, "definitely-not-a-revision")

    loader = GitCommitSourceLoader(root)
    with pytest.raises(RepositoryEvidenceError):
        loader.load("missing.txt")
