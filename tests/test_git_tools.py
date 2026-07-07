from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import codexbridge.git_tools as git_tools
from codexbridge.git_tools import (
    CommitMetadataError,
    GitCommandError,
    changed_files,
    commit_all_changes,
    commit_selected_files,
    dry_run_stage_manifest,
    inspect_status,
    stage_all,
    unstage_all,
)


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


def test_selected_file_commit_accepts_files_inside_untracked_directory(
    repo: Path,
) -> None:
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
        ".codexbridge/*\n!.codexbridge/wiki/\n!.codexbridge/wiki/**\n",
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
    result = commit_selected_files(
        repo, selected, "docs: add generated repository wiki"
    )

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


def test_commit_accepts_long_ordinary_technical_description(
    repo: Path,
) -> None:
    (repo / "technical.txt").write_text(
        "technical change\n",
        encoding="utf-8",
    )
    description = (
        "Validated repository paths and updated command capability coverage. "
        "The change adds structured diagnostics for commit metadata while "
        "preserving staging scope, shell-free execution, branch behaviour, "
        "and the rule that this operation never pushes.\n"
    ) * 20

    result = commit_selected_files(
        repo,
        ["technical.txt"],
        "fix: improve commit metadata diagnostics",
        description,
    )

    assert result["ok"] is True
    assert result["files_validated"] is True
    assert result["commit_hash"]


def test_commit_metadata_error_identifies_rejected_field(
    repo: Path,
) -> None:
    (repo / "metadata.txt").write_text(
        "metadata\n",
        encoding="utf-8",
    )

    with pytest.raises(CommitMetadataError) as caught:
        commit_selected_files(
            repo,
            ["metadata.txt"],
            "invalid\nmultiline title",
            "ordinary description",
        )

    error = caught.value
    assert error.field == "title"
    assert error.reason_code == "multiline"
    assert error.files_validated is True


def test_commit_metadata_rejects_secret_value_without_echoing_it(
    repo: Path,
) -> None:
    (repo / "secret-check.txt").write_text(
        "safe file\n",
        encoding="utf-8",
    )

    with pytest.raises(CommitMetadataError) as caught:
        commit_selected_files(
            repo,
            ["secret-check.txt"],
            "test: metadata validation",
            "api_key=example-sensitive-value",
        )

    error = caught.value
    assert error.field == "description"
    assert error.reason_code == "secret_value"
    assert "example-sensitive-value" not in str(error)


def test_stage_manifest_stage_all_and_unstage_all(repo: Path) -> None:
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    manifest = dry_run_stage_manifest(repo)
    assert "tracked.txt" in manifest["unstaged"] or "new.txt" in manifest["untracked"]

    staged = stage_all(repo)
    assert "tracked.txt" in staged["after"]["staged"]
    assert "new.txt" in staged["after"]["staged"]

    unstaged = unstage_all(repo)
    assert "tracked.txt" in unstaged["after"]["untracked"]


def test_commit_all_changes_stages_deleted_files(repo: Path) -> None:
    (repo / "base.txt").unlink()

    result = commit_all_changes(repo, "chore: remove base")

    assert result["ok"] is True
    assert result["commit_hash"]


def test_commit_failure_restores_preexisting_index_and_reports_stderr(
    repo: Path, monkeypatch
) -> None:
    (repo / "base.txt").write_text("staged before operation\n", encoding="utf-8")
    run(["git", "add", "base.txt"], repo)
    (repo / "selected.txt").write_text("selected\n", encoding="utf-8")
    original_run_git = git_tools._run_git

    def fail_commit(repo_root: Path, args: list[str], *, check: bool = False):
        if args and args[0] == "commit":
            raise GitCommandError(
                {
                    "argv": ["git", *args],
                    "exit_code": 128,
                    "stdout": "",
                    "stderr": "simulated commit failure",
                    "duration_seconds": 0.01,
                    "index_lock": {"exists": False, "path": ".git/index.lock"},
                }
            )
        return original_run_git(repo_root, args, check=check)

    monkeypatch.setattr(git_tools, "_run_git", fail_commit)
    result = commit_selected_files(repo, ["selected.txt"], "test: failure")

    assert result["ok"] is False
    assert result["index_restored"] is True
    assert result["git_error"]["stderr"] == "simulated commit failure"
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert staged == ["base.txt"]
    assert "selected.txt" in result["stage_manifest_after"]["untracked"]


def test_status_manifest_classifies_tool_owned_files(repo: Path) -> None:
    scratch = repo / ".codex-tmp" / "entry.txt"
    scratch.parent.mkdir()
    scratch.write_text("one\ntwo\n", encoding="utf-8")

    manifest = dry_run_stage_manifest(repo)
    entry = next(
        item for item in manifest["files"] if item["path"] == ".codex-tmp/entry.txt"
    )

    assert ".codex-tmp/entry.txt" in manifest["tool_owned"]
    assert entry["tool_owned"] is True
    assert entry["size_bytes"] > 0
    assert entry["line_count"] == 2
