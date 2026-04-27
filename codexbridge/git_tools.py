from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from .safety import validate_repo_relative_path


def _run_git(repo_root: Path, args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
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
    output = _run_git(repo_root, ["status", "--porcelain"]).stdout
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


def commit_selected_files(repo_root: Path, files: Iterable[str], title: str, description: str = "") -> dict:
    selected = list(files)
    if not selected:
        raise ValueError("files must not be empty")
    if not title or not title.strip():
        raise ValueError("title must not be empty")

    for file_name in selected:
        validate_repo_relative_path(repo_root, file_name)

    changed = set(changed_files(repo_root))
    missing = [file_name for file_name in selected if file_name not in changed]
    if missing:
        raise ValueError(f"Files are not currently changed: {missing}")

    _run_git(repo_root, ["add", "--", *selected], check=True)
    _run_git(repo_root, ["commit", "-m", title, "-m", description or ""], check=True)
    commit_hash = _run_git(repo_root, ["rev-parse", "HEAD"], check=True).stdout.strip()
    return {
        "commit_hash": commit_hash,
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
    }

