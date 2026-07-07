from __future__ import annotations

import hashlib
import os
import re
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
FULL_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40}$")


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


def _index_state(repo_root: Path) -> dict[str, Any]:
    path = _git_path(repo_root, "index")
    exists = path.exists()
    try:
        display_path = path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        display_path = path.name
    size_bytes = path.stat().st_size if exists and path.is_file() else 0
    sha256 = ""
    if exists and path.is_file():
        try:
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            sha256 = ""
    return {
        "exists": exists,
        "path": display_path,
        "size_bytes": size_bytes,
        "sha256": sha256,
    }


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


def _run_git_bytes(
    repo_root: Path, args: list[str], *, check: bool = False
) -> subprocess.CompletedProcess[bytes]:
    argv = ["git", *args]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=repo_root,
        text=False,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise GitCommandError(
            {
                "argv": argv,
                "exit_code": result.returncode,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
                "duration_seconds": round(time.monotonic() - started, 3),
                "index_lock": _index_lock_state(repo_root),
            }
        )
    return result


def _decode_git_path(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def _iter_porcelain_v1_z_entries(repo_root: Path) -> list[dict[str, str]]:
    output = _run_git_bytes(
        repo_root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        check=True,
    ).stdout
    fields = output.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()

    entries: list[dict[str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 3:
            continue

        index_status = chr(field[0])
        worktree_status = chr(field[1])
        path = _decode_git_path(field[3:])
        entry = {
            "index_status": index_status,
            "worktree_status": worktree_status,
            "path": path,
        }

        if (
            index_status in {"R", "C"} or worktree_status in {"R", "C"}
        ) and index < len(fields):
            entry["rename_source_path"] = _decode_git_path(fields[index])
            index += 1

        entries.append(entry)

    return entries


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


def _file_metadata(
    repo_root: Path, path: str, *, include_line_count: bool = True
) -> dict[str, Any]:
    absolute = repo_root / path
    size_bytes = 0
    line_count: int | None = None
    if absolute.exists() and absolute.is_file() and not absolute.is_symlink():
        try:
            size_bytes = absolute.stat().st_size
            if include_line_count and size_bytes <= 1_000_000:
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


def _tool_owned_root_group(path: str) -> str:
    parts = Path(path).as_posix().split("/", 1)
    return parts[0] if parts else path


def _build_compact_tool_owned_summary(
    entries: Iterable[dict[str, Any]], sample_limit: int = 5
) -> dict[str, Any]:
    tool_owned_entries = sorted(
        (dict(entry) for entry in entries),
        key=lambda entry: entry["path"],
    )
    root_group_counts: dict[str, int] = {}
    total_bytes = 0
    for entry in tool_owned_entries:
        path = str(entry["path"])
        root_group = _tool_owned_root_group(path)
        root_group_counts[root_group] = root_group_counts.get(root_group, 0) + 1
        total_bytes += int(entry.get("size_bytes") or 0)
    ordered_root_group_counts = {
        root: root_group_counts[root] for root in sorted(root_group_counts)
    }
    sample = tool_owned_entries[:sample_limit]
    return {
        "total_bytes": total_bytes,
        "root_group_counts": ordered_root_group_counts,
        "sample": sample,
        "truncated": len(tool_owned_entries) > sample_limit,
    }


def inspect_status_compact(repo_root: Path) -> dict[str, Any]:
    returned_entries: list[dict[str, Any]] = []
    collapsed_tool_owned_entries: list[dict[str, Any]] = []

    for status_entry in _iter_porcelain_v1_z_entries(repo_root):
        index_status = status_entry["index_status"]
        worktree_status = status_entry["worktree_status"]
        path = status_entry["path"]
        entry = _file_metadata(repo_root, path, include_line_count=False)
        entry.update(
            {
                "index_status": index_status,
                "worktree_status": worktree_status,
            }
        )
        if "rename_source_path" in status_entry:
            entry["rename_source_path"] = status_entry["rename_source_path"]

        if entry["tool_owned"] and index_status == "?" and worktree_status == "?":
            collapsed_tool_owned_entries.append(entry)
            continue

        entry["line_count"] = _file_metadata(repo_root, path, include_line_count=True)[
            "line_count"
        ]
        returned_entries.append(entry)

    returned_entries.sort(key=lambda entry: entry["path"])
    collapsed_tool_owned_entries.sort(key=lambda entry: entry["path"])

    sampled_tool_owned_entries: list[dict[str, Any]] = []
    for entry in collapsed_tool_owned_entries[:5]:
        sampled_entry = dict(entry)
        sampled_entry["line_count"] = _file_metadata(
            repo_root, str(entry["path"]), include_line_count=True
        )["line_count"]
        sampled_tool_owned_entries.append(sampled_entry)

    collapsed_tool_owned_summary = _build_compact_tool_owned_summary(
        collapsed_tool_owned_entries
    )
    collapsed_tool_owned_count = len(collapsed_tool_owned_entries)
    sampled_tool_owned_count = len(sampled_tool_owned_entries)
    unsampled_tool_owned_count = collapsed_tool_owned_count - sampled_tool_owned_count
    total_status_entry_count = len(returned_entries) + collapsed_tool_owned_count
    return {
        "branch": git_branch(repo_root),
        "recent_commits": recent_commits(repo_root),
        "diff_stat": diff_stat(repo_root),
        "complete_status_scan": True,
        "total_status_entry_count": total_status_entry_count,
        "returned_entry_count": len(returned_entries),
        "collapsed_tool_owned_count": collapsed_tool_owned_count,
        "sampled_tool_owned_count": sampled_tool_owned_count,
        "unsampled_tool_owned_count": unsampled_tool_owned_count,
        "files": returned_entries,
        "tool_owned_summary": {
            "total_bytes": collapsed_tool_owned_summary["total_bytes"],
            "root_group_counts": collapsed_tool_owned_summary["root_group_counts"],
            "sample": sampled_tool_owned_entries,
            "truncated": collapsed_tool_owned_summary["truncated"],
        },
        "fallback_tool": "inspect_repo_status",
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
    manifest_before = dry_run_stage_manifest(repo_root)
    try:
        _run_git(repo_root, ["branch", "--", branch_name], check=True)
    except GitCommandError as exc:
        result = _operation_failure(repo_root, exc, manifest_before=manifest_before)
        result["branch_name"] = branch_name
        return result
    return {
        "ok": True,
        "branch_name": branch_name,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "index_state_before": _index_state(repo_root),
        "index_state_after": _index_state(repo_root),
        "error": "",
    }


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


def _snapshot_to_state(snapshot: _IndexSnapshot) -> dict[str, Any]:
    try:
        display_path = snapshot.path.relative_to(
            snapshot.path.parent.parent.resolve()
        ).as_posix()
    except ValueError:
        display_path = snapshot.path.name
    return {
        "exists": snapshot.existed,
        "path": display_path,
        "size_bytes": len(snapshot.content or b""),
        "sha256": (
            hashlib.sha256(snapshot.content).hexdigest()
            if snapshot.content is not None
            else ""
        ),
    }


def _commit_failure(
    repo_root: Path,
    exc: GitCommandError,
    *,
    files_validated: bool,
    manifest_before: dict,
    index_restored: bool,
    snapshot: _IndexSnapshot,
) -> dict[str, Any]:
    return {
        "ok": False,
        "files_validated": files_validated,
        "commit_hash": "",
        "git_error": exc.diagnostics,
        "index_restored": index_restored,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "index_state_before": _snapshot_to_state(snapshot),
        "index_state_after": _index_state(repo_root),
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "recovery_guidance": (
            "Resolve the reported Git error and retry. The pre-operation index was restored."
            if index_restored
            else "Inspect the Git index before retrying; automatic restoration failed."
        ),
        "error": str(exc),
    }


def _operation_failure(
    repo_root: Path,
    exc: GitCommandError,
    *,
    manifest_before: dict[str, Any],
    snapshot: _IndexSnapshot | None = None,
    files_validated: bool | None = None,
) -> dict[str, Any]:
    index_restored = True
    if snapshot is not None:
        try:
            _restore_index(snapshot)
        except OSError:
            index_restored = False
    result = {
        "ok": False,
        "git_error": exc.diagnostics,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "index_state_before": _snapshot_to_state(snapshot)
        if snapshot is not None
        else _index_state(repo_root),
        "index_state_after": _index_state(repo_root),
        "index_restored": index_restored if snapshot is not None else None,
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "recovery_guidance": (
            "Resolve the reported Git error and retry. The pre-operation index was restored."
            if snapshot is not None and index_restored
            else "Inspect the Git index before retrying; automatic restoration failed."
            if snapshot is not None
            else "Resolve the reported Git error and retry."
        ),
        "error": str(exc),
    }
    if files_validated is not None:
        result["files_validated"] = files_validated
    return result


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
            snapshot=snapshot,
        )

    return {
        "ok": True,
        "files_validated": True,
        "commit_hash": commit_hash,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "index_state_before": _snapshot_to_state(snapshot),
        "index_state_after": _index_state(repo_root),
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
    snapshot = _snapshot_index(repo_root)
    try:
        _run_git(repo_root, ["add", "-A"], check=True)
    except GitCommandError as exc:
        result = _operation_failure(
            repo_root, exc, manifest_before=before, snapshot=snapshot
        )
        result["before"] = before
        result["after"] = result["stage_manifest_after"]
        return result
    after = dry_run_stage_manifest(repo_root)
    return {
        "ok": True,
        "before": before,
        "after": after,
        "index_state_before": _snapshot_to_state(snapshot),
        "index_state_after": _index_state(repo_root),
        "git_status": git_status(repo_root),
        "error": "",
    }


def unstage_all(repo_root: Path) -> dict:
    before = dry_run_stage_manifest(repo_root)
    snapshot = _snapshot_index(repo_root)
    try:
        _run_git(repo_root, ["reset", "HEAD", "--", "."], check=True)
    except GitCommandError as exc:
        result = _operation_failure(
            repo_root, exc, manifest_before=before, snapshot=snapshot
        )
        result["before"] = before
        result["after"] = result["stage_manifest_after"]
        return result
    after = dry_run_stage_manifest(repo_root)
    return {
        "ok": True,
        "before": before,
        "after": after,
        "index_state_before": _snapshot_to_state(snapshot),
        "index_state_after": _index_state(repo_root),
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
            snapshot=snapshot,
        )
    return {
        "ok": True,
        "files_validated": False,
        "commit_hash": commit_hash,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "index_state_before": _snapshot_to_state(snapshot),
        "index_state_after": _index_state(repo_root),
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "error": "",
    }


def inspect_commit_range(
    repo_root: Path,
    base_commit: str,
    head_commit: str,
    *,
    max_diff_bytes: int = 300_000,
) -> dict[str, Any]:
    if not FULL_COMMIT_HASH_RE.fullmatch(base_commit):
        raise ValueError(
            "base_commit must be a full 40-character hexadecimal commit hash"
        )
    if not FULL_COMMIT_HASH_RE.fullmatch(head_commit):
        raise ValueError(
            "head_commit must be a full 40-character hexadecimal commit hash"
        )

    name_status = _run_git(
        repo_root, ["diff", "--name-status", base_commit, head_commit], check=True
    ).stdout
    diff_stat_text = _run_git(
        repo_root, ["diff", "--stat", base_commit, head_commit], check=True
    ).stdout
    diff_text = _run_git(
        repo_root, ["diff", base_commit, head_commit], check=True
    ).stdout
    truncated = False
    if len(diff_text.encode("utf-8")) > max_diff_bytes:
        diff_text = diff_text.encode("utf-8")[:max_diff_bytes].decode(
            "utf-8", errors="replace"
        )
        truncated = True

    return {
        "ok": True,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "name_status": name_status,
        "diff_stat": diff_stat_text,
        "diff": diff_text,
        "truncated": truncated,
        "error": "",
    }
