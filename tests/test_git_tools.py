from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codexbridge.git_tools import changed_files, commit_selected_files, inspect_status


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    run(["git", "add", "base.txt"], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)
    return tmp_path


def test_temporary_git_repo_status_works(repo: Path) -> None:
    (repo / "changed.txt").write_text("hello\n", encoding="utf-8")
    status = inspect_status(repo)
    assert "changed.txt" in status["changed_files"]
    assert status["branch"] in {"master", "main"}


def test_selected_file_commit_commits_only_selected_files(repo: Path) -> None:
    (repo / "one.txt").write_text("one\n", encoding="utf-8")
    (repo / "two.txt").write_text("two\n", encoding="utf-8")
    result = commit_selected_files(repo, ["one.txt"], "commit one", "body")
    assert result["commit_hash"]
    assert "two.txt" in result["remaining_dirty_files"]
    assert "one.txt" not in result["remaining_dirty_files"]


def test_commit_refuses_empty_files(repo: Path) -> None:
    with pytest.raises(ValueError):
        commit_selected_files(repo, [], "title", "")


def test_commit_refuses_empty_title(repo: Path) -> None:
    with pytest.raises(ValueError):
        commit_selected_files(repo, ["base.txt"], "", "")


def test_commit_refuses_unchanged_file(repo: Path) -> None:
    with pytest.raises(ValueError, match="not currently changed"):
        commit_selected_files(repo, ["base.txt"], "title", "")


def test_changed_files_reports_modified(repo: Path) -> None:
    (repo / "base.txt").write_text("updated\n", encoding="utf-8")
    assert "base.txt" in changed_files(repo)

