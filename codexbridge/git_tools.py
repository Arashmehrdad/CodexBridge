from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from .safety import SECRET_VALUE_PATTERNS, validate_repo_relative_path


def _run_git(
    repo_root: Path, args: list[str], *, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=check,
    )


def git_branch(repo_root: Path) -> str:
    result = _run_git(repo_root, ["branch", "--show-current"])
    return result.stdout.strip()


def git_status(repo_root: Path) -> str:
    return _run_git(repo_root, ["status", "--short", "--branch"]).stdout


def recent_commits(repo_root: Path, limit: int = 5) -> str:
    return _run_git(repo_root, ["log", "--oneline", "-n", str(limit)]).stdout


def diff_stat(repo_root: Path) -> str:
    return _run_git(repo_root, ["diff", "--stat"]).stdout


def changed_files(repo_root: Path) -> list[str]:
    """Return changed repository-relative paths, including every untracked file.

    Git normally collapses a wholly untracked directory into one ``?? dir/``
    status entry. ``commit_selected_files`` operates on explicit files, so the
    status query must enumerate untracked files individually.
    """
    output = _run_git(
        repo_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    ).stdout
    files: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        name = line[3:]
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        files.append(name)
    return files


def inspect_status(repo_root: Path) -> dict:
    return {
        "branch": git_branch(repo_root),
        "git_status": git_status(repo_root),
        "recent_commits": recent_commits(repo_root),
        "diff_stat": diff_stat(repo_root),
        "changed_files": changed_files(repo_root),
    }


def git_diff(
    repo_root: Path,
    path: str = "",
    staged: bool = False,
    max_bytes: int = 300_000,
) -> dict:
    """
    Return the actual unified diff for the repo, optionally limited to one
    validated relative path and/or the staging area.

    path      – repo-relative POSIX path (empty → whole repo)
    staged    – if True, uses --cached (staged diff)
    max_bytes – hard cap on diff output; indicates truncation when hit
    """
    from .safety import validate_repo_relative_path  # local import to avoid circular

    args = ["diff"]
    if staged:
        args.append("--cached")

    if path:
        validated = validate_repo_relative_path(repo_root, path)
        args.extend(["--", str(validated.relative_to(repo_root))])

    result = _run_git(repo_root, args)
    raw = result.stdout
    truncated = False
    if len(raw.encode("utf-8")) > max_bytes:
        raw = raw.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        truncated = True

    return {
        "ok": True,
        "repo_name": "",
        "path": path,
        "staged": staged,
        "diff": raw,
        "truncated": truncated,
        "error": result.stderr.strip() if result.returncode != 0 else "",
    }


def git_head(repo_root: Path) -> str:
    """Return current HEAD commit hash, or empty string if unavailable."""
    result = _run_git(repo_root, ["rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""


def git_branch_list(repo_root: Path) -> list[str]:
    """Return list of local branch names."""
    result = _run_git(repo_root, ["branch", "--list", "--format=%(refname:short)"])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def create_branch(repo_root: Path, branch_name: str) -> dict:
    """
    Create a new local branch without switching to it.
    Returns ok, branch_name, and error.
    """
    result = _run_git(repo_root, ["branch", "--", branch_name])
    if result.returncode != 0:
        raise ValueError(f"git branch failed: {result.stderr.strip()}")
    return {"ok": True, "branch_name": branch_name, "error": ""}


MAX_COMMIT_TITLE_LENGTH = 200
MAX_COMMIT_DESCRIPTION_LENGTH = 10_000


class CommitMetadataError(ValueError):
    """Structured validation error for inert Git commit metadata."""

    def __init__(
        self,
        field: str,
        reason_code: str,
        reason: str,
        *,
        files_validated: bool,
    ) -> None:
        super().__init__(reason)
        self.field = field
        self.reason_code = reason_code
        self.reason = reason
        self.files_validated = files_validated


def _validate_commit_metadata(
    title: str,
    description: str,
    *,
    files_validated: bool,
) -> None:
    if not title or not title.strip():
        raise CommitMetadataError(
            "title",
            "empty",
            "Commit title must not be empty",
            files_validated=files_validated,
        )

    if len(title) > MAX_COMMIT_TITLE_LENGTH:
        raise CommitMetadataError(
            "title",
            "too_long",
            f"Commit title exceeds {MAX_COMMIT_TITLE_LENGTH} characters",
            files_validated=files_validated,
        )

    if "\n" in title or "\r" in title:
        raise CommitMetadataError(
            "title",
            "multiline",
            "Commit title must be a single line",
            files_validated=files_validated,
        )

    if any(ord(character) < 32 for character in title):
        raise CommitMetadataError(
            "title",
            "control_character",
            "Commit title contains a control character",
            files_validated=files_validated,
        )

    if len(description) > MAX_COMMIT_DESCRIPTION_LENGTH:
        raise CommitMetadataError(
            "description",
            "too_long",
            (f"Commit description exceeds {MAX_COMMIT_DESCRIPTION_LENGTH} characters"),
            files_validated=files_validated,
        )

    if any(
        ord(character) < 32 and character not in "\t\n\r" for character in description
    ):
        raise CommitMetadataError(
            "description",
            "control_character",
            "Commit description contains a control character",
            files_validated=files_validated,
        )

    for field, value in (
        ("title", title),
        ("description", description),
    ):
        if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
            raise CommitMetadataError(
                field,
                "secret_value",
                f"Commit {field} appears to contain a secret value",
                files_validated=files_validated,
            )


def commit_selected_files(
    repo_root: Path,
    files: Iterable[str],
    title: str,
    description: str = "",
) -> dict:
    selected = list(files)
    if not selected:
        raise ValueError("files must not be empty")

    # Validate repository scope before inspecting commit metadata.
    for file_name in selected:
        validate_repo_relative_path(repo_root, file_name)

    description = description or ""
    _validate_commit_metadata(
        title,
        description,
        files_validated=True,
    )

    changed = set(changed_files(repo_root))
    missing = [file_name for file_name in selected if file_name not in changed]
    if missing:
        raise ValueError(f"Files are not currently changed: {missing}")

    _run_git(repo_root, ["add", "--", *selected], check=True)

    # Title and description are passed as argv values with shell=False.
    # They are inert Git metadata and are never executed.
    _run_git(
        repo_root,
        ["commit", "-m", title, "-m", description],
        check=True,
    )

    commit_hash = _run_git(
        repo_root,
        ["rev-parse", "HEAD"],
        check=True,
    ).stdout.strip()

    return {
        "ok": True,
        "files_validated": True,
        "commit_hash": commit_hash,
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
    }
