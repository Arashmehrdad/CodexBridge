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


def test_selected_file_commit_accepts_files_inside_untracked_directory(repo: Path) -> None:
    wiki = repo / ".codexbridge" / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "overview.md").write_text("# Overview\n", encoding="utf-8")
    (wiki / "architecture.md").write_text("# Architecture\n", encoding="utf-8")

    assert ".codexbridge/wiki/overview.md" in changed_files(repo)
    assert ".codexbridge/wiki/architecture.md" in changed_files(repo)

    result = commit_selected_files(
        repo,
        [".codexbridge/wiki/overview.md"],
        "docs: add repository wiki",
    )

    assert result["commit_hash"]
    assert ".codexbridge/wiki/overview.md" not in result["remaining_dirty_files"]
    assert ".codexbridge/wiki/architecture.md" in result["remaining_dirty_files"]


def test_selected_file_commit_accepts_unignored_wiki_files(repo: Path) -> None:
    (repo / ".gitignore").write_text(
        ".codexbridge/*\n"
        "!.codexbridge/wiki/\n"
        "!.codexbridge/wiki/**\n",
        encoding="utf-8",
    )
    wiki = repo / ".codexbridge" / "wiki"
    wiki.mkdir(parents=True)
    files = {
        ".codexbridge/wiki/architecture.md": "# Architecture\n",
        ".codexbridge/wiki/manifest.json": "{}\n",
        ".codexbridge/wiki/modules.md": "# Modules\n",
        ".codexbridge/wiki/overview.md": "# Overview\n",
        ".codexbridge/wiki/validation.md": "# Validation\n",
    }
    for relative, content in files.items():
        (repo / relative).write_text(content, encoding="utf-8")

    selected = [".gitignore", *files]
    result = commit_selected_files(repo, selected, "docs: add generated repository wiki")

    assert result["commit_hash"]
    assert result["remaining_dirty_files"] == []


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
