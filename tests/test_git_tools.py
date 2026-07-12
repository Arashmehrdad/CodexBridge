from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import codexbridge.git_tools as git_tools
from codexbridge.git_tools import (
    CommitMetadataError,
    CommitPolicyError,
    GitCommandError,
    changed_files,
    commit_all_changes,
    commit_selected_files,
    create_branch,
    dry_run_stage_manifest,
    finalize_explicit_changes,
    inspect_commit_range,
    inspect_status,
    inspect_status_compact,
    stage_all,
    unstage_all,
)


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True)


def porcelain_v1_z(*entries: tuple[str, str, str] | tuple[str, str, str, str]) -> bytes:
    payload = bytearray()
    for entry in entries:
        index_status, worktree_status, path, *rest = entry
        payload.extend(f"{index_status}{worktree_status} ".encode("ascii"))
        payload.extend(path.encode("utf-8"))
        payload.append(0)
        for extra_path in rest:
            payload.extend(extra_path.encode("utf-8"))
            payload.append(0)
    return bytes(payload)


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


def test_inspect_status_has_explicit_freshness_metadata(repo: Path) -> None:
    status = inspect_status(repo)

    assert status["ok"] is True
    assert status["fresh"] is True
    assert status["source"] == "live_git"
    assert status["status"] == "available"
    assert status["head_commit"]
    assert isinstance(status["generated_at"], float)
    assert isinstance(status["duration_ms"], float)
    assert status["total_changed_file_count"] == len(status["changed_files"])


def test_inspect_status_timeout_is_structured(monkeypatch, repo: Path) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(git_tools.subprocess, "run", timeout)

    status = inspect_status(repo)

    assert status["ok"] is False
    assert status["fresh"] is False
    assert status["status"] == "timed_out"
    assert status["changed_files"] == []
    assert "Retry" in status["recommended_action"]


def test_selected_file_commit_commits_only_selected_files(repo: Path) -> None:
    (repo / "one.txt").write_text("one\n", encoding="utf-8")
    (repo / "two.txt").write_text("two\n", encoding="utf-8")
    result = commit_selected_files(repo, ["one.txt"], "commit one", "body")
    assert result["commit_hash"]
    assert "two.txt" in result["remaining_dirty_files"]
    assert "one.txt" not in result["remaining_dirty_files"]


def test_selected_file_commit_accepts_modified_file_outside_sparse_checkout(
    repo: Path,
) -> None:
    included = repo / "included"
    excluded = repo / "excluded"
    included.mkdir()
    excluded.mkdir()
    (included / "keep.txt").write_text("keep\n", encoding="utf-8")
    (excluded / "target.txt").write_text("original\n", encoding="utf-8")
    run(["git", "add", "included/keep.txt", "excluded/target.txt"], repo)
    run(["git", "commit", "-m", "add sparse fixture"], repo)
    run(["git", "sparse-checkout", "init", "--cone"], repo)
    run(["git", "sparse-checkout", "set", "included"], repo)

    excluded.mkdir(exist_ok=True)
    (excluded / "target.txt").write_text("updated\n", encoding="utf-8")

    result = commit_selected_files(
        repo,
        ["excluded/target.txt"],
        "test: commit sparse path",
    )

    assert result["ok"] is True
    assert result["commit_hash"]
    assert "excluded/target.txt" not in result["remaining_dirty_files"]
    committed = subprocess.run(
        ["git", "show", "HEAD:excluded/target.txt"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert committed.stdout == "updated\n"


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

    result = commit_all_changes(repo, "chore: remove base", commit_mode="all_allowed")

    assert result["ok"] is True
    assert result["commit_hash"]
    assert result["commit_report"]["mode"] == "all_tracked_and_untracked"


def test_commit_all_changes_rejected_by_default_policy(repo: Path) -> None:
    (repo / "base.txt").write_text("updated\n", encoding="utf-8")

    with pytest.raises(CommitPolicyError) as caught:
        commit_all_changes(repo, "chore: update base")

    assert caught.value.reason_code == "commit_all_disabled"


def test_selected_commit_refuses_unrelated_staged_files_by_default(repo: Path) -> None:
    (repo / "base.txt").write_text("staged before operation\n", encoding="utf-8")
    run(["git", "add", "base.txt"], repo)
    (repo / "selected.txt").write_text("selected\n", encoding="utf-8")

    with pytest.raises(CommitPolicyError) as caught:
        commit_selected_files(repo, ["selected.txt"], "test: selected")

    assert caught.value.reason_code == "unrelated_staged_files"


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
    result = commit_selected_files(
        repo,
        ["selected.txt"],
        "test: failure",
        refuse_unrelated_staged_files=False,
    )

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


def test_finalize_explicit_changes_commits_only_requested_paths(repo: Path) -> None:
    (repo / "selected.txt").write_text("selected\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")

    result = finalize_explicit_changes(
        repo,
        ["selected.txt"],
        tool_name="create_repo_file",
        run_id="20260707T000000Z_run_deadbeef",
    )

    assert result["commit_required"] is True
    assert result["commit_attempted"] is True
    assert result["commit_hash"]
    assert result["commit_error"] == ""
    assert result["commit_result"]["commit_report"]["mode"] == "explicit_isolated"
    assert "selected.txt" not in result["commit_result"]["remaining_dirty_files"]
    assert "unrelated.txt" in result["commit_result"]["remaining_dirty_files"]
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert "selected.txt" not in staged
    git_temp_root = repo / ".git" / "codexbridge-tmp"
    assert not git_temp_root.exists() or not any(git_temp_root.iterdir())


def test_finalize_explicit_changes_stages_rename_source_and_destination(
    repo: Path,
) -> None:
    (repo / "rename source.txt").write_text("before\n", encoding="utf-8")
    run(["git", "add", "rename source.txt"], repo)
    run(["git", "commit", "-m", "add rename source"], repo)
    run(["git", "mv", "rename source.txt", "rename target.txt"], repo)

    result = finalize_explicit_changes(
        repo,
        ["rename source.txt", "rename target.txt"],
        tool_name="move_repo_file",
    )

    assert result["commit_hash"]
    assert result["commit_result"]["remaining_dirty_files"] == []
    name_status = subprocess.run(
        ["git", "show", "--name-status", "--format=", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert "rename source.txt" in name_status
    assert "rename target.txt" in name_status


def test_finalize_explicit_changes_skips_empty_change_sets_without_commit(
    repo: Path,
) -> None:
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    result = finalize_explicit_changes(
        repo,
        ["base.txt"],
        tool_name="apply_repo_patch",
    )

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert result["commit_required"] is False
    assert result["commit_attempted"] is False
    assert result["commit_hash"] == ""
    assert after == before


def test_finalize_explicit_changes_reports_commit_failure_and_never_pushes(
    repo: Path, monkeypatch
) -> None:
    (repo / "selected.txt").write_text("selected\n", encoding="utf-8")
    original_run_git = git_tools._run_git
    seen_commands: list[list[str]] = []

    def fail_commit(
        repo_root: Path,
        args: list[str],
        *,
        check: bool = False,
        env: dict[str, str] | None = None,
    ):
        seen_commands.append(list(args))
        if args and args[0] == "commit":
            raise GitCommandError(
                {
                    "argv": ["git", *args],
                    "exit_code": 128,
                    "stdout": "",
                    "stderr": "simulated finalize failure",
                    "duration_seconds": 0.01,
                    "index_lock": {"exists": False, "path": ".git/index.lock"},
                }
            )
        return original_run_git(repo_root, args, check=check, env=env)

    monkeypatch.setattr(git_tools, "_run_git", fail_commit)

    result = finalize_explicit_changes(
        repo,
        ["selected.txt"],
        tool_name="apply_repo_patch",
    )

    assert result["commit_required"] is True
    assert result["commit_attempted"] is True
    assert result["commit_hash"] == ""
    assert result["commit_error"] == "simulated finalize failure"
    assert all(args[0] != "push" for args in seen_commands)


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


def test_inspect_status_compact_preserves_non_tool_owned_and_summarizes_tool_owned(
    repo: Path,
) -> None:
    (repo / "alpha.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    (repo / "nested").mkdir()
    (repo / "nested" / "beta.txt").write_text("beta\n", encoding="utf-8")
    first_tool_owned = repo / ".codex-tmp" / "z-last.txt"
    first_tool_owned.parent.mkdir()
    first_tool_owned.write_bytes(b"z\n")
    (repo / ".codex-tmp" / "a-first.txt").write_bytes(b"a\nb\nc\n")
    (repo / ".ruff_cache").mkdir()
    (repo / ".ruff_cache" / "cache.txt").write_bytes(b"cache")
    (repo / ".pytest_cache").mkdir()
    (repo / ".pytest_cache" / "state.txt").write_bytes(b"state\n")
    (repo / ".codex-tmp" / "extra.txt").write_bytes(b"extra\n")

    result = inspect_status_compact(repo)

    assert result["complete_status_scan"] is True
    assert result["fallback_tool"] == "inspect_repo_status"
    assert "git_status" not in result
    assert "manifest" not in result
    assert [entry["path"] for entry in result["files"]] == [
        "alpha.txt",
        "nested/beta.txt",
    ]
    assert result["total_status_entry_count"] == 7
    assert result["returned_entry_count"] == 2
    assert result["collapsed_tool_owned_count"] == 5
    assert result["sampled_tool_owned_count"] == 5
    assert result["unsampled_tool_owned_count"] == 0
    for entry in result["files"]:
        assert entry["tool_owned"] is False
        assert "index_status" in entry
        assert "worktree_status" in entry
    assert result["tool_owned_summary"] == {
        "total_bytes": 25,
        "root_group_counts": {
            ".codex-tmp": 3,
            ".pytest_cache": 1,
            ".ruff_cache": 1,
        },
        "sample": [
            {
                "path": ".codex-tmp/a-first.txt",
                "size_bytes": 6,
                "line_count": 3,
                "tool_owned": True,
                "index_status": "?",
                "worktree_status": "?",
            },
            {
                "path": ".codex-tmp/extra.txt",
                "size_bytes": 6,
                "line_count": 1,
                "tool_owned": True,
                "index_status": "?",
                "worktree_status": "?",
            },
            {
                "path": ".codex-tmp/z-last.txt",
                "size_bytes": 2,
                "line_count": 1,
                "tool_owned": True,
                "index_status": "?",
                "worktree_status": "?",
            },
            {
                "path": ".pytest_cache/state.txt",
                "size_bytes": 6,
                "line_count": 1,
                "tool_owned": True,
                "index_status": "?",
                "worktree_status": "?",
            },
            {
                "path": ".ruff_cache/cache.txt",
                "size_bytes": 5,
                "line_count": 1,
                "tool_owned": True,
                "index_status": "?",
                "worktree_status": "?",
            },
        ],
        "truncated": False,
    }


def test_inspect_status_compact_truncates_sorted_tool_owned_sample(repo: Path) -> None:
    tool_owned_names = ["b.txt", "f.txt", "d.txt", "a.txt", "e.txt", "c.txt"]
    scratch_root = repo / ".codex-tmp"
    scratch_root.mkdir()
    for name in tool_owned_names:
        (scratch_root / name).write_text(name + "\n", encoding="utf-8")

    result = inspect_status_compact(repo)

    assert result["collapsed_tool_owned_count"] == 6
    assert result["sampled_tool_owned_count"] == 5
    assert result["unsampled_tool_owned_count"] == 1
    assert result["tool_owned_summary"]["truncated"] is True
    assert [entry["path"] for entry in result["tool_owned_summary"]["sample"]] == [
        ".codex-tmp/a.txt",
        ".codex-tmp/b.txt",
        ".codex-tmp/c.txt",
        ".codex-tmp/d.txt",
        ".codex-tmp/e.txt",
    ]


def test_inspect_status_compact_handles_spaces_and_renames(repo: Path) -> None:
    old_name = repo / "old name.txt"
    old_name.write_text("before\n", encoding="utf-8")
    run(["git", "add", "old name.txt"], repo)
    run(["git", "commit", "-m", "add old name"], repo)
    renamed = "renamed file with spaces.txt"
    ordinary = "plain file with spaces.txt"
    run(["git", "mv", "old name.txt", renamed], repo)
    (repo / ordinary).write_text("ordinary\n", encoding="utf-8")
    tool_owned = repo / ".codex-tmp" / "scratch file with spaces.txt"
    tool_owned.parent.mkdir()
    tool_owned.write_bytes(b"tool owned\n")

    result = inspect_status_compact(repo)

    assert result["returned_entry_count"] == 2
    assert result["collapsed_tool_owned_count"] == 1
    assert [entry["path"] for entry in result["files"]] == [
        ordinary,
        renamed,
    ]
    renamed_entry = next(entry for entry in result["files"] if entry["path"] == renamed)
    assert renamed_entry["index_status"] == "R"
    assert renamed_entry["worktree_status"] == " "
    assert renamed_entry["rename_source_path"] == "old name.txt"
    assert result["tool_owned_summary"]["sample"] == [
        {
            "path": ".codex-tmp/scratch file with spaces.txt",
            "size_bytes": len("tool owned\n".encode("utf-8")),
            "line_count": 1,
            "tool_owned": True,
            "index_status": "?",
            "worktree_status": "?",
        }
    ]


def test_iter_porcelain_v1_z_entries_preserves_embedded_newlines(
    repo: Path, monkeypatch
) -> None:
    original_run_git_bytes = git_tools._run_git_bytes
    renamed = "renamed file\nwith newline.txt"
    source = "old name\nwith newline.txt"
    ordinary = "plain file with spaces.txt"
    status_output = porcelain_v1_z(
        ("R", " ", renamed, source),
        ("?", "?", ordinary),
    )

    def fake_run_git_bytes(repo_root: Path, args: list[str], *, check: bool = False):
        if args == ["status", "--porcelain=v1", "-z", "--untracked-files=all"]:
            return subprocess.CompletedProcess(
                ["git", *args], 0, stdout=status_output, stderr=b""
            )
        return original_run_git_bytes(repo_root, args, check=check)

    monkeypatch.setattr(git_tools, "_run_git_bytes", fake_run_git_bytes)

    assert git_tools._iter_porcelain_v1_z_entries(repo) == [
        {
            "index_status": "R",
            "worktree_status": " ",
            "path": renamed,
            "rename_source_path": source,
        },
        {
            "index_status": "?",
            "worktree_status": "?",
            "path": ordinary,
        },
    ]


def test_inspect_status_compact_preserves_tool_owned_non_untracked_entries(
    repo: Path, monkeypatch
) -> None:
    original_run_git_bytes = git_tools._run_git_bytes
    line_count_requests: list[str] = []
    status_output = porcelain_v1_z(
        ("?", "?", ".codex-tmp/untracked.txt"),
        ("M", " ", ".codex-tmp/staged.txt"),
        (" ", "M", ".codex-tmp/modified.txt"),
        ("D", " ", ".codex-tmp/deleted.txt"),
        ("U", "U", ".codex-tmp/conflicted.txt"),
        ("C", " ", ".codex-tmp/copied.txt", "original.txt"),
        ("R", " ", ".codex-tmp/renamed.txt", "old.txt"),
        ("?", "?", "src/app.py"),
    )

    def fake_run_git_bytes(repo_root: Path, args: list[str], *, check: bool = False):
        if args == ["status", "--porcelain=v1", "-z", "--untracked-files=all"]:
            return subprocess.CompletedProcess(
                ["git", *args], 0, stdout=status_output, stderr=b""
            )
        return original_run_git_bytes(repo_root, args, check=check)

    def fake_file_metadata(
        repo_root: Path, path: str, *, include_line_count: bool = True
    ) -> dict[str, object]:
        if include_line_count:
            line_count_requests.append(path)
        return {
            "path": path,
            "size_bytes": len(path.encode("utf-8")),
            "line_count": 1 if include_line_count else None,
            "tool_owned": path.startswith(".codex-tmp/"),
        }

    monkeypatch.setattr(git_tools, "_run_git_bytes", fake_run_git_bytes)
    monkeypatch.setattr(git_tools, "_file_metadata", fake_file_metadata)

    result = inspect_status_compact(repo)

    assert [entry["path"] for entry in result["files"]] == [
        ".codex-tmp/conflicted.txt",
        ".codex-tmp/copied.txt",
        ".codex-tmp/deleted.txt",
        ".codex-tmp/modified.txt",
        ".codex-tmp/renamed.txt",
        ".codex-tmp/staged.txt",
        "src/app.py",
    ]
    assert result["total_status_entry_count"] == 8
    assert result["returned_entry_count"] == 7
    assert result["collapsed_tool_owned_count"] == 1
    assert result["sampled_tool_owned_count"] == 1
    assert result["unsampled_tool_owned_count"] == 0
    assert result["tool_owned_summary"]["root_group_counts"] == {".codex-tmp": 1}
    assert result["tool_owned_summary"]["sample"] == [
        {
            "path": ".codex-tmp/untracked.txt",
            "size_bytes": len(".codex-tmp/untracked.txt".encode("utf-8")),
            "line_count": 1,
            "tool_owned": True,
            "index_status": "?",
            "worktree_status": "?",
        }
    ]
    assert sorted(line_count_requests) == [
        ".codex-tmp/conflicted.txt",
        ".codex-tmp/copied.txt",
        ".codex-tmp/deleted.txt",
        ".codex-tmp/modified.txt",
        ".codex-tmp/renamed.txt",
        ".codex-tmp/staged.txt",
        ".codex-tmp/untracked.txt",
        "src/app.py",
    ]
    copied_entry = next(
        entry for entry in result["files"] if entry["path"] == ".codex-tmp/copied.txt"
    )
    renamed_entry = next(
        entry for entry in result["files"] if entry["path"] == ".codex-tmp/renamed.txt"
    )
    assert copied_entry["rename_source_path"] == "original.txt"
    assert renamed_entry["rename_source_path"] == "old.txt"


def test_inspect_status_compact_skips_line_counts_for_unsampled_collapsed_entries(
    repo: Path, monkeypatch
) -> None:
    original_run_git_bytes = git_tools._run_git_bytes
    line_count_requests: list[str] = []
    collapsed_paths = [f".codex-tmp/{name}.txt" for name in "fedcba"]
    status_output = porcelain_v1_z(*(("?", "?", path) for path in collapsed_paths))

    def fake_run_git_bytes(repo_root: Path, args: list[str], *, check: bool = False):
        if args == ["status", "--porcelain=v1", "-z", "--untracked-files=all"]:
            return subprocess.CompletedProcess(
                ["git", *args], 0, stdout=status_output, stderr=b""
            )
        return original_run_git_bytes(repo_root, args, check=check)

    def fake_file_metadata(
        repo_root: Path, path: str, *, include_line_count: bool = True
    ) -> dict[str, object]:
        if include_line_count:
            line_count_requests.append(path)
        return {
            "path": path,
            "size_bytes": 1,
            "line_count": 1 if include_line_count else None,
            "tool_owned": True,
        }

    monkeypatch.setattr(git_tools, "_run_git_bytes", fake_run_git_bytes)
    monkeypatch.setattr(git_tools, "_file_metadata", fake_file_metadata)

    result = inspect_status_compact(repo)

    assert result["collapsed_tool_owned_count"] == 6
    assert result["sampled_tool_owned_count"] == 5
    assert result["unsampled_tool_owned_count"] == 1
    assert [entry["path"] for entry in result["tool_owned_summary"]["sample"]] == [
        ".codex-tmp/a.txt",
        ".codex-tmp/b.txt",
        ".codex-tmp/c.txt",
        ".codex-tmp/d.txt",
        ".codex-tmp/e.txt",
    ]
    assert sorted(line_count_requests) == [
        ".codex-tmp/a.txt",
        ".codex-tmp/b.txt",
        ".codex-tmp/c.txt",
        ".codex-tmp/d.txt",
        ".codex-tmp/e.txt",
    ]


def test_inspect_status_compact_payload_is_small_and_preserves_meaningful_entries(
    repo: Path,
) -> None:
    (repo / "base.txt").write_text("updated base\n", encoding="utf-8")
    (repo / "alpha note.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    (repo / "rename source.txt").write_text("rename me\n", encoding="utf-8")
    run(["git", "add", "rename source.txt"], repo)
    run(["git", "commit", "-m", "add rename source"], repo)
    run(["git", "mv", "rename source.txt", "rename target.txt"], repo)
    nested = repo / "docs"
    nested.mkdir()
    (nested / "plain.py").write_text("print('ok')\n", encoding="utf-8")
    scratch_root = repo / ".codex-tmp"
    scratch_root.mkdir()
    for index in range(240):
        (scratch_root / f"batch-{index:03d}.txt").write_text(
            f"payload {index}\n",
            encoding="utf-8",
        )

    full = inspect_status(repo)
    compact = inspect_status_compact(repo)
    full_payload = json.dumps(full, sort_keys=True)
    compact_payload = json.dumps(compact, sort_keys=True)

    assert len(compact_payload) <= len(full_payload) * 0.25
    assert compact["collapsed_tool_owned_count"] >= 200
    assert compact["total_status_entry_count"] == len(full["manifest"]["files"])
    assert {entry["path"] for entry in compact["files"]} == {
        "alpha note.txt",
        "base.txt",
        "docs/plain.py",
        "rename target.txt",
    }
    renamed_entry = next(
        entry for entry in compact["files"] if entry["path"] == "rename target.txt"
    )
    assert renamed_entry["rename_source_path"] == "rename source.txt"


def test_inspect_commit_range_requires_full_hashes_and_returns_diff(repo: Path) -> None:
    first = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    (repo / "base.txt").write_text("updated\n", encoding="utf-8")
    run(["git", "commit", "-am", "update base"], repo)
    second = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    result = inspect_commit_range(repo, first, second)

    assert result["ok"] is True
    assert "base.txt" in result["name_status"]
    assert "base.txt" in result["diff"]
    with pytest.raises(ValueError, match="40-character"):
        inspect_commit_range(repo, first[:8], second)


def test_create_branch_failure_returns_structured_git_diagnostics(
    repo: Path, monkeypatch
) -> None:
    original_run_git = git_tools._run_git

    def fail_branch(repo_root: Path, args: list[str], *, check: bool = False):
        if args[:1] == ["branch"] and check:
            raise GitCommandError(
                {
                    "argv": ["git", *args],
                    "exit_code": 128,
                    "stdout": "",
                    "stderr": "simulated branch failure",
                    "duration_seconds": 0.01,
                    "index_lock": {"exists": False, "path": ".git/index.lock"},
                }
            )
        return original_run_git(repo_root, args, check=check)

    monkeypatch.setattr(git_tools, "_run_git", fail_branch)

    result = create_branch(repo, "feature/test")

    assert result["ok"] is False
    assert result["branch_name"] == "feature/test"
    assert result["git_error"]["stderr"] == "simulated branch failure"
