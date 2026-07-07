from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .safety import SECRET_VALUE_PATTERNS, validate_repo_relative_path


TOOL_OWNED_PREFIXES = (
    ".codex-tmp/",
    ".pytest_cache/",
    ".ruff_cache/",
    "tests/pytest_tmp_probe/",
)


class GitCommandError(RuntimeError):
    """Structured Git failure preserving diagnostics needed for recovery."""

    def __init__(self, diagnostics: dict[str, Any]) -> None:
        self.diagnostics = diagnostics
        message = diagnostics.get("stderr") or diagnostics.get("stdout") or "Git failed"
        super().__init__(str(message).strip())


@dataclass(frozen=True)
class _IndexSnapshot:
    path: Path
    existed: bool
    content: bytes | None


def _git_path(repo_root: Path, name: str) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", name],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    value = result.stdout.strip()
    path = Path(value) if value else repo_root / ".git" / name
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _index_lock_state(repo_root: Path) -> dict[str, Any]:
    lock_path = _git_path(repo_root, "index.lock")
    exists = lock_path.exists()
    try:
        display_path = lock_path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        display_path = lock_path.name
    return {
        "exists": exists,
        "path": display_path,
        "size_bytes": lock_path.stat().st_size if exists and lock_path.is_file() else 0,
    }


def _run_git(
    repo_root: Path, args: list[str], *, check: bool = False
) -> subprocess.CompletedProcess[str]:
    argv = ["git", *args]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise GitCommandError(
            {
                "argv": argv,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_seconds": round(time.monotonic() - started, 3),
                "index_lock": _index_lock_state(repo_root),
            }
        )
    return result


def git_branch(repo_root: Path) -> str:
    result = _run_git(repo_root, ["branch", "--show-current"])
    return result.stdout.strip()


def git_status(repo_root: Path) -> str:
    return _run_git(
        repo_root,
        ["status", "--short", "--branch", "--untracked-files=all"],
    ).stdout


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


def _file_metadata(repo_root: Path, path: str) -> dict[str, Any]:
    absolute = repo_root / path
    size_bytes = 0
    line_count: int | None = None
    if absolute.exists() and absolute.is_file() and not absolute.is_symlink():
        try:
            size_bytes = absolute.stat().st_size
            if size_bytes <= 1_000_000:
                data = absolute.read_bytes()
                if b"\0" not in data:
                    text = data.decode("utf-8", errors="replace")
                    line_count = len(text.splitlines())
        except OSError:
            pass
    normalized = Path(path).as_posix()
    return {
        "path": normalized,
        "size_bytes": size_bytes,
        "line_count": line_count,
        "tool_owned": any(
            normalized == prefix.rstrip("/") or normalized.startswith(prefix)
            for prefix in TOOL_OWNED_PREFIXES
        ),
    }


def inspect_status(repo_root: Path) -> dict:
    manifest = dry_run_stage_manifest(repo_root)
    return {
        "branch": git_branch(repo_root),
        "git_status": manifest["git_status"],
        "recent_commits": recent_commits(repo_root),
        "diff_stat": diff_stat(repo_root),
        "changed_files": changed_files(repo_root),
        "manifest": manifest,
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


def _snapshot_index(repo_root: Path) -> _IndexSnapshot:
    path = _git_path(repo_root, "index")
    return _IndexSnapshot(
        path=path,
        existed=path.exists(),
        content=path.read_bytes() if path.exists() else None,
    )


def _restore_index(snapshot: _IndexSnapshot) -> None:
    if snapshot.existed:
        assert snapshot.content is not None
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = snapshot.path.with_name(
            f".{snapshot.path.name}.codexbridge-{os.getpid()}.tmp"
        )
        temporary.write_bytes(snapshot.content)
        os.replace(temporary, snapshot.path)
    elif snapshot.path.exists():
        snapshot.path.unlink()


def _commit_failure(
    repo_root: Path,
    exc: GitCommandError,
    *,
    files_validated: bool,
    manifest_before: dict,
    index_restored: bool,
) -> dict[str, Any]:
    return {
        "ok": False,
        "files_validated": files_validated,
        "commit_hash": "",
        "git_error": exc.diagnostics,
        "index_restored": index_restored,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "recovery_guidance": (
            "Resolve the reported Git error and retry. The pre-operation index was restored."
            if index_restored
            else "Inspect the Git index before retrying; automatic restoration failed."
        ),
        "error": str(exc),
    }


def commit_selected_files(
    repo_root: Path,
    files: Iterable[str],
    title: str,
    description: str = "",
) -> dict:
    selected = list(files)
    if not selected:
        raise ValueError("files must not be empty")
    for file_name in selected:
        validate_repo_relative_path(repo_root, file_name)
    description = description or ""
    _validate_commit_metadata(title, description, files_validated=True)
    changed = set(changed_files(repo_root))
    missing = [file_name for file_name in selected if file_name not in changed]
    if missing:
        raise ValueError(f"Files are not currently changed: {missing}")

    manifest_before = dry_run_stage_manifest(repo_root)
    snapshot = _snapshot_index(repo_root)
    try:
        _run_git(repo_root, ["add", "--", *selected], check=True)
        _run_git(
            repo_root,
            ["commit", "-m", title, "-m", description],
            check=True,
        )
        commit_hash = _run_git(
            repo_root, ["rev-parse", "HEAD"], check=True
        ).stdout.strip()
    except GitCommandError as exc:
        restored = True
        try:
            _restore_index(snapshot)
        except OSError:
            restored = False
        return _commit_failure(
            repo_root,
            exc,
            files_validated=True,
            manifest_before=manifest_before,
            index_restored=restored,
        )

    return {
        "ok": True,
        "files_validated": True,
        "commit_hash": commit_hash,
        "stage_manifest_before": manifest_before,
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "error": "",
    }


def dry_run_stage_manifest(repo_root: Path, *, include_ignored: bool = False) -> dict:
    args = ["status", "--porcelain=v1", "--untracked-files=all"]
    if include_ignored:
        args.append("--ignored=matching")
    output = _run_git(repo_root, args, check=True).stdout
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    deleted: list[str] = []
    ignored: list[str] = []
    renamed: list[str] = []
    entries: list[dict[str, Any]] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        x_status = line[0]
        y_status = line[1]
        path = line[3:]
        if " -> " in path:
            renamed.append(path)
            path = path.split(" -> ", 1)[1]
        if x_status == "!" and y_status == "!":
            ignored.append(path)
        elif x_status == "?" and y_status == "?":
            untracked.append(path)
        else:
            if x_status != " ":
                staged.append(path)
            if y_status != " ":
                unstaged.append(path)
            if "D" in {x_status, y_status}:
                deleted.append(path)
        entry = _file_metadata(repo_root, path)
        entry.update({"index_status": x_status, "worktree_status": y_status})
        entries.append(entry)
    tool_owned = sorted(entry["path"] for entry in entries if entry["tool_owned"])
    return {
        "ok": True,
        "staged": sorted(set(staged)),
        "unstaged": sorted(set(unstaged)),
        "untracked": sorted(set(untracked)),
        "deleted": sorted(set(deleted)),
        "ignored": sorted(set(ignored)),
        "renamed": sorted(set(renamed)),
        "tool_owned": tool_owned,
        "files": entries,
        "git_status": git_status(repo_root),
    }


def stage_all(repo_root: Path) -> dict:
    before = dry_run_stage_manifest(repo_root)
    try:
        _run_git(repo_root, ["add", "-A"], check=True)
    except GitCommandError as exc:
        return {
            "ok": False,
            "before": before,
            "after": dry_run_stage_manifest(repo_root),
            "git_error": exc.diagnostics,
            "git_status": git_status(repo_root),
            "error": str(exc),
        }
    after = dry_run_stage_manifest(repo_root)
    return {
        "ok": True,
        "before": before,
        "after": after,
        "git_status": git_status(repo_root),
        "error": "",
    }


def unstage_all(repo_root: Path) -> dict:
    before = dry_run_stage_manifest(repo_root)
    try:
        _run_git(repo_root, ["reset", "HEAD", "--", "."], check=True)
    except GitCommandError as exc:
        return {
            "ok": False,
            "before": before,
            "after": dry_run_stage_manifest(repo_root),
            "git_error": exc.diagnostics,
            "git_status": git_status(repo_root),
            "error": str(exc),
        }
    after = dry_run_stage_manifest(repo_root)
    return {
        "ok": True,
        "before": before,
        "after": after,
        "git_status": git_status(repo_root),
        "error": "",
    }


def commit_all_changes(repo_root: Path, title: str, description: str = "") -> dict:
    _validate_commit_metadata(title, description or "", files_validated=False)
    manifest_before = dry_run_stage_manifest(repo_root)
    snapshot = _snapshot_index(repo_root)
    try:
        _run_git(repo_root, ["add", "-A"], check=True)
        _run_git(
            repo_root,
            ["commit", "-m", title, "-m", description or ""],
            check=True,
        )
        commit_hash = _run_git(
            repo_root, ["rev-parse", "HEAD"], check=True
        ).stdout.strip()
    except GitCommandError as exc:
        restored = True
        try:
            _restore_index(snapshot)
        except OSError:
            restored = False
        return _commit_failure(
            repo_root,
            exc,
            files_validated=False,
            manifest_before=manifest_before,
            index_restored=restored,
        )
    return {
        "ok": True,
        "files_validated": False,
        "commit_hash": commit_hash,
        "stage_manifest_before": manifest_before,
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "error": "",
    }
