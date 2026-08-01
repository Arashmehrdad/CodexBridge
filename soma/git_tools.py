from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .safety import SECRET_VALUE_PATTERNS, validate_repo_relative_path
from .tool_owned_paths import TOOL_OWNED_PREFIXES, is_tool_owned_path

__all__ = ["TOOL_OWNED_PREFIXES", "is_tool_owned_path"]
GIT_OPERATION_TIMEOUT_SECONDS = 10.0
FULL_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_DIFF_RESPONSE_BYTES = 32 * 1024
MAX_DIFF_RESPONSE_BYTES = 32 * 1024
_DIFF_SNAPSHOT_VERSION = 1


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
    repo_root: Path,
    args: list[str],
    *,
    check: bool = False,
    env: dict[str, str] | None = None,
    timeout_seconds: float = GIT_OPERATION_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    argv = ["git", *args]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if result.stdout is None or result.stderr is None:
        result = subprocess.CompletedProcess(
            args=result.args,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
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
    repo_root: Path,
    args: list[str],
    *,
    check: bool = False,
    timeout_seconds: float = GIT_OPERATION_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    argv = ["git", *args]
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=repo_root,
        text=False,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
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
    """Return one bounded, live Git status snapshot.

    This deliberately does not reuse ``dry_run_stage_manifest``: status must
    have one explicit freshness boundary and a failure must never be turned
    into an apparently clean response by a caller.
    """
    started = time.monotonic()

    def failure(status: str, error: str, *, partial: dict[str, Any] | None = None) -> dict:
        result: dict[str, Any] = {
            "ok": False,
            "status": status,
            "branch": "",
            "head_commit": "",
            "git_status": "",
            "staged": [],
            "unstaged": [],
            "untracked": [],
            "deleted": [],
            "renamed": [],
            "changed_files": [],
            "total_changed_file_count": 0,
            "recent_commits": [],
            "diff_stat": "",
            "manifest": {},
            "generated_at": time.time(),
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "fresh": False,
            "source": "live_git",
            "truncated": False,
            "error": error[:1000],
            "recommended_action": "Retry the live repository-status check; do not use a cached snapshot.",
        }
        if partial:
            result["partial"] = partial
        return result

    try:
        status_result = _run_git(
            repo_root,
            ["status", "--short", "--branch", "--untracked-files=all"],
        )
        if status_result.returncode != 0:
            return failure(
                "failed",
                status_result.stderr.strip() or "git status failed",
            )

        head_result = _run_git(repo_root, ["rev-parse", "HEAD"])
        if head_result.returncode != 0:
            return failure(
                "failed",
                head_result.stderr.strip() or "could not resolve HEAD",
                partial={"git_status": status_result.stdout},
            )

        branch = ""
        entries: list[str] = []
        for line in status_result.stdout.splitlines():
            if line.startswith("## "):
                branch = line[3:].split("...", 1)[0].strip()
            else:
                entries.append(line)

        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []
        deleted: list[str] = []
        renamed: list[str] = []
        changed: list[str] = []
        manifest_files: list[dict[str, str]] = []
        for line in entries:
            if len(line) < 4:
                continue
            index_status, worktree_status = line[0], line[1]
            path = line[3:]
            if " -> " in path:
                old_path, path = path.split(" -> ", 1)
                renamed.append(f"{old_path} -> {path}")
            if index_status == "?" and worktree_status == "?":
                untracked.append(path)
            else:
                if index_status not in {" ", "?", "!"}:
                    staged.append(path)
                if worktree_status not in {" ", "?", "!"}:
                    unstaged.append(path)
                if "D" in {index_status, worktree_status}:
                    deleted.append(path)
            changed.append(path)
            manifest_files.append(
                {
                    "path": path,
                    "index_status": index_status,
                    "worktree_status": worktree_status,
                }
            )

        # These are useful context, but a missing log on an empty repository
        # should not erase a successfully obtained live status snapshot.
        log_result = _run_git(repo_root, ["log", "--oneline", "-n", "5"])
        diff_result = _run_git(repo_root, ["diff", "--stat"])
        return {
            "ok": True,
            "status": "available",
            "branch": branch,
            "head_commit": head_result.stdout.strip(),
            "git_status": status_result.stdout,
            "staged": sorted(set(staged)),
            "unstaged": sorted(set(unstaged)),
            "untracked": sorted(set(untracked)),
            "deleted": sorted(set(deleted)),
            "renamed": sorted(set(renamed)),
            "changed_files": sorted(set(changed)),
            "total_changed_file_count": len(set(changed)),
            "recent_commits": [line for line in log_result.stdout.splitlines() if line.strip()],
            "diff_stat": diff_result.stdout,
            "manifest": {
                "staged": sorted(set(staged)),
                "unstaged": sorted(set(unstaged)),
                "untracked": sorted(set(untracked)),
                "deleted": sorted(set(deleted)),
                "renamed": sorted(set(renamed)),
                "files": manifest_files,
            },
            "generated_at": time.time(),
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "fresh": True,
            "source": "live_git",
            "truncated": False,
            "error": "",
            "recommended_action": "",
        }
    except subprocess.TimeoutExpired as exc:
        return failure("timed_out", f"Git status timed out: {exc}")
    except (OSError, GitCommandError, ValueError) as exc:
        return failure("failed", str(exc))


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


COMMIT_EVIDENCE_COMPACTION_VERSION = 1
MAX_LISTED_PATHS = 500
_BULKY_MANIFEST_FIELDS = ("files", "untracked", "tool_owned", "git_status")
_BULKY_COMMIT_FIELDS = (
    "stage_manifest_before",
    "stage_manifest_after",
    "git_status",
    "remaining_dirty_files",
)


def _is_tool_owned_path(path: str) -> bool:
    return is_tool_owned_path(path)


def _compact_path_list(
    paths: Iterable[str], *, max_listed_paths: int = MAX_LISTED_PATHS
) -> dict[str, Any]:
    """Summarize a path list without letting repository size drive its size.

    Tool-owned paths are collapsed to counts because they are never part of an
    operation's intent. Remaining paths stay exact until ``max_listed_paths``,
    after which the list is truncated and the complete body remains available
    through the referenced evidence artifact.
    """
    ordered = [str(path) for path in paths]
    tool_owned = [path for path in ordered if _is_tool_owned_path(path)]
    retained = [path for path in ordered if not _is_tool_owned_path(path)]
    root_group_counts: dict[str, int] = {}
    for path in tool_owned:
        root = _tool_owned_root_group(path)
        root_group_counts[root] = root_group_counts.get(root, 0) + 1
    listed = retained[:max_listed_paths]
    return {
        "total_count": len(ordered),
        "tool_owned_count": len(tool_owned),
        "tool_owned_root_group_counts": {
            root: root_group_counts[root] for root in sorted(root_group_counts)
        },
        "paths": listed,
        "listed_count": len(listed),
        "omitted_count": len(ordered) - len(listed),
        "truncated": len(retained) > len(listed),
    }


def compact_stage_manifest(
    manifest: dict[str, Any], *, max_listed_paths: int = MAX_LISTED_PATHS
) -> dict[str, Any]:
    """Return a queryable stage manifest whose size reflects the operation.

    ``staged``, ``unstaged``, ``deleted``, ``renamed``, and ``ignored`` are the
    correctness-relevant lists and stay exact. The repository-scale fields are
    replaced by counts and a bounded tool-owned summary; the complete manifest
    remains authoritative in the run's evidence artifact.
    """
    if not isinstance(manifest, dict) or manifest.get("compacted"):
        # Already compact. Recompacting would replace real counts with counts of
        # the summary itself, so this must be a no-op.
        return manifest
    compact = {
        key: value
        for key, value in manifest.items()
        if key not in _BULKY_MANIFEST_FIELDS
    }
    entries = manifest.get("files")
    entries = entries if isinstance(entries, list) else []
    tool_owned_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("tool_owned")
    ]
    retained_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict) and not entry.get("tool_owned")
    ]
    compact["untracked"] = _compact_path_list(
        manifest.get("untracked") or [], max_listed_paths=max_listed_paths
    )
    compact["file_count"] = len(entries)
    compact["tool_owned_count"] = len(tool_owned_entries)
    compact["tool_owned_summary"] = _build_compact_tool_owned_summary(
        tool_owned_entries
    )
    listed_entries = retained_entries[:max_listed_paths]
    compact["files"] = listed_entries
    compact["files_listed_count"] = len(listed_entries)
    compact["files_omitted_count"] = len(entries) - len(listed_entries)
    compact["files_truncated"] = len(retained_entries) > len(listed_entries)
    compact["git_status_line_count"] = len(
        str(manifest.get("git_status") or "").splitlines()
    )
    compact["compacted"] = True
    compact["compaction_version"] = COMMIT_EVIDENCE_COMPACTION_VERSION
    return compact


def compact_commit_result(
    commit_result: dict[str, Any], *, max_listed_paths: int = MAX_LISTED_PATHS
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a commit result into a compact record and its authoritative body.

    The second element contains every field removed or reduced, so the complete
    evidence can be written to an immutable artifact and referenced by hash.
    Returns the input unchanged when there is nothing bulky to separate.
    """
    if not isinstance(commit_result, dict):
        return commit_result, {}
    if commit_result.get("compacted"):
        # Never re-externalize an already-compacted record: the authoritative
        # body has already been moved out, and a second pass would overwrite it
        # with these summaries.
        return commit_result, {}
    full_body: dict[str, Any] = {}
    compact = dict(commit_result)
    for field in _BULKY_COMMIT_FIELDS:
        if field not in compact:
            continue
        value = compact[field]
        full_body[field] = value
        if field.startswith("stage_manifest"):
            compact[field] = compact_stage_manifest(
                value, max_listed_paths=max_listed_paths
            )
        elif field == "git_status":
            compact[field + "_line_count"] = len(str(value or "").splitlines())
            compact.pop(field, None)
        else:
            compact[field] = _compact_path_list(
                value or [], max_listed_paths=max_listed_paths
            )
    if not full_body:
        return compact, {}
    compact["compacted"] = True
    compact["compaction_version"] = COMMIT_EVIDENCE_COMPACTION_VERSION
    return compact, full_body


def inspect_status_compact(repo_root: Path) -> dict[str, Any]:
    started = time.monotonic()
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
        "ok": True,
        "status": "available",
        "branch": git_branch(repo_root),
        "recent_commits": recent_commits(repo_root),
        "diff_stat": diff_stat(repo_root),
        "generated_at": time.time(),
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "fresh": True,
        "source": "live_git",
        "error": "",
        "recommended_action": "",
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


def git_diff_snapshot(
    repo_root: Path,
    path: str = "",
    staged: bool = False,
    *,
    view: str = "summary",
    snapshot_id: str = "",
    hunk_id: str = "",
    response_budget_bytes: int = DEFAULT_DIFF_RESPONSE_BYTES,
) -> dict:
    """Return a bounded diff summary or snapshot-bound exact evidence view."""
    if view not in {"summary", "hunk", "full"}:
        raise ValueError("view must be summary, hunk, or full")
    if view == "hunk" and not hunk_id:
        raise ValueError("hunk_id is required for hunk view")
    if view in {"hunk", "full"} and not snapshot_id:
        raise ValueError("snapshot_id is required for explicit diff retrieval")
    response_budget_bytes = max(
        4 * 1024, min(int(response_budget_bytes), MAX_DIFF_RESPONSE_BYTES)
    )
    validated_path = ""
    if path:
        validated = validate_repo_relative_path(repo_root, path)
        validated_path = str(validated.relative_to(repo_root)).replace(os.sep, "/")
    args = ["diff"]
    if staged:
        args.append("--cached")
    if validated_path:
        args.extend(["--", validated_path])
    result = _run_git(repo_root, args)
    raw = result.stdout or ""
    if result.returncode != 0:
        return {
            "ok": False,
            "status": "failed",
            "fresh": False,
            "view": view,
            "path": path,
            "staged": staged,
            "changed_files": [],
            "hunks": [],
            "snapshot_id": "",
            "response_bytes": 0,
            "truncated": False,
            "error": result.stderr.strip(),
        }
    snapshot = _parse_diff_snapshot(raw, path, staged)
    hunk_texts = snapshot.pop("_hunk_texts", {})
    if snapshot_id and snapshot_id != snapshot["snapshot_id"]:
        return {
            "ok": False,
            "status": "stale_snapshot",
            "fresh": False,
            "view": view,
            "path": path,
            "staged": staged,
            "snapshot_id": snapshot["snapshot_id"],
            "expected_snapshot_id": snapshot_id,
            "changed_files": [],
            "hunks": [],
            "truncated": False,
            "response_bytes": 0,
            "error": "Diff changed; restart from a fresh diff summary",
        }
    if view == "full":
        return _bounded_diff_result(
            {**snapshot, "view": "full", "diff": raw, "truncated": False},
            response_budget_bytes,
            allow_full=True,
        )
    if view == "hunk":
        selected = next(
            (item for item in snapshot["hunks"] if item["hunk_id"] == hunk_id),
            None,
        )
        if selected is None:
            raise ValueError("Unknown hunk_id for this diff snapshot")
        return _bounded_diff_result(
            {
                "ok": True,
                "status": "available",
                "fresh": True,
                "view": "hunk",
                "path": path,
                "staged": staged,
                "snapshot_id": snapshot["snapshot_id"],
                "hunk_id": hunk_id,
                "hunk": hunk_texts.get(hunk_id, ""),
                "truncated": False,
                "error": "",
            },
            response_budget_bytes,
        )
    return _bounded_diff_result(
        {
            **snapshot,
            "view": "summary",
            "diff": "",
            "full_retrieval": "Use view=full with snapshot_id",
            "truncated": False,
        },
        response_budget_bytes,
    )


def _parse_diff_snapshot(raw: str, path: str, staged: bool) -> dict:
    identity = json.dumps(
        {"version": _DIFF_SNAPSHOT_VERSION, "path": path, "staged": staged, "diff": raw},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    snapshot_id = hashlib.sha256(identity).hexdigest()
    files: list[dict[str, Any]] = []
    hunks: list[dict[str, Any]] = []
    current_file: dict[str, Any] | None = None
    current_hunk: dict[str, Any] | None = None
    for line in raw.splitlines(keepends=True):
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+) b/(.+)", line.rstrip("\r\n"))
            file_path = match.group(2) if match else line.rstrip("\r\n")[11:]
            current_file = {
                "path": file_path.replace("\\", "/"),
                "status": "modified",
                "additions": 0,
                "deletions": 0,
                "hunks": [],
            }
            files.append(current_file)
            current_hunk = None
            continue
        if line.startswith("@@ ") and current_file is not None:
            match = re.match(
                r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)",
                line.rstrip("\r\n"),
            )
            if not match:
                continue
            hunk_index = len(current_file["hunks"])
            hunk_id = hashlib.sha256(
                f"{snapshot_id}:{current_file['path']}:{hunk_index}".encode("utf-8")
            ).hexdigest()[:20]
            current_hunk = {
                "hunk_id": hunk_id,
                "path": current_file["path"],
                "old_start": int(match.group(1)),
                "old_lines": int(match.group(2) or 1),
                "new_start": int(match.group(3)),
                "new_lines": int(match.group(4) or 1),
                "header": line.rstrip("\r\n"),
                "additions": 0,
                "deletions": 0,
                "text": line,
            }
            current_file["hunks"].append(current_hunk)
            hunks.append(current_hunk)
            continue
        if current_hunk is not None:
            current_hunk["text"] += line
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk["additions"] += 1
                current_file["additions"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk["deletions"] += 1
                current_file["deletions"] += 1
    for item in files:
        if item["additions"] and not item["deletions"]:
            item["status"] = "added"
        elif item["deletions"] and not item["additions"]:
            item["status"] = "deleted"
    hunk_index = [
        {key: value for key, value in item.items() if key != "text"}
        for item in hunks
    ]
    file_index = [
        {
            **{key: value for key, value in item.items() if key != "hunks"},
            "hunks": [
                {key: value for key, value in hunk.items() if key != "text"}
                for hunk in item["hunks"]
            ],
        }
        for item in files
    ]
    return {
        "ok": True,
        "status": "available",
        "fresh": True,
        "path": path,
        "staged": staged,
        "snapshot_id": snapshot_id,
        "changed_files": file_index,
        "hunks": hunk_index,
        "_hunk_texts": {item["hunk_id"]: item["text"] for item in hunks},
        "file_count": len(files),
        "hunk_count": len(hunks),
        "additions": sum(item["additions"] for item in files),
        "deletions": sum(item["deletions"] for item in files),
        "error": "",
    }


def _bounded_diff_result(result: dict, budget: int, *, allow_full: bool = False) -> dict:
    if allow_full:
        result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        return result
    result["changed_files"] = result.get("changed_files", [])
    result["hunks"] = result.get("hunks", [])
    while len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > budget:
        if result["hunks"]:
            removed = result["hunks"].pop()
            for file_item in result["changed_files"]:
                file_item["hunks"] = [
                    item for item in file_item.get("hunks", [])
                    if item.get("hunk_id") != removed.get("hunk_id")
                ]
        elif result["changed_files"]:
            result["changed_files"].pop()
        else:
            result["truncated"] = True
            break
        result["truncated"] = True
    result["response_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return result


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
AUTO_COMMIT_TITLE_LIMIT = 72
SOMA_COMMITTER_NAME = "Soma"
SOMA_COMMITTER_EMAIL = "soma@local.invalid"


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


class CommitPolicyError(ValueError):
    """Structured validation error for repository commit policy enforcement."""

    def __init__(
        self,
        reason_code: str,
        reason: str,
        *,
        files_validated: bool,
        blocked_field: str = "policy",
    ) -> None:
        super().__init__(reason)
        self.field = blocked_field
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
            f".{snapshot.path.name}.soma-{os.getpid()}.tmp"
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


def _normalize_explicit_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        normalized_path = Path(raw_path).as_posix()
        if normalized_path in seen:
            continue
        seen.add(normalized_path)
        normalized.append(normalized_path)
    return normalized


def _sanitize_commit_label(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "-", value).strip(" .-")
    return cleaned or fallback


def canonical_commit_metadata(title: str, description: str, paths: Iterable[str]) -> bytes:
    return json.dumps(
        {"title": title, "description": description, "paths": list(paths)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _build_auto_commit_metadata(
    tool_name: str,
    run_id: str = "",
    staged_paths: Iterable[str] | None = None,
) -> tuple[str, str]:
    safe_tool = _sanitize_commit_label(tool_name, fallback="write")
    title = f"Soma: {safe_tool}"
    if len(title) > AUTO_COMMIT_TITLE_LIMIT:
        suffix_limit = AUTO_COMMIT_TITLE_LIMIT - len("Soma: ")
        title = f"Soma: {safe_tool[:suffix_limit].rstrip()}"

    safe_run_id = _sanitize_commit_label(run_id, fallback="")
    normalized_paths = sorted(_normalize_explicit_paths(staged_paths or []))
    path_digest = hashlib.sha256(
        "\n".join(normalized_paths).encode("utf-8")
    ).hexdigest()
    metadata_lines = [f"Changed-Paths-SHA256: {path_digest}"]
    if safe_run_id:
        metadata_lines.insert(0, f"Run-ID: {safe_run_id}")
    description = "\n".join(metadata_lines)
    return title, description


def _build_commit_report(
    *,
    commit_hash: str,
    title: str,
    description: str,
    mode: str,
    files_validated: bool,
    staged_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized_paths = sorted(_normalize_explicit_paths(staged_paths or []))
    metadata_sha256 = hashlib.sha256(
        canonical_commit_metadata(title, description, normalized_paths)
    ).hexdigest()
    return {
        "commit_hash": commit_hash,
        "title": title,
        "description": description,
        "mode": mode,
        "files_validated": files_validated,
        "staged_paths": list(staged_paths or []),
        "metadata_sha256": metadata_sha256,
    }


def _reject_unrelated_staged_files(
    manifest_before: dict[str, Any],
    allowed_paths: Iterable[str],
    *,
    files_validated: bool,
) -> None:
    allowed = set(_normalize_explicit_paths(allowed_paths))
    unrelated = [
        path for path in manifest_before.get("staged", []) if Path(path).as_posix() not in allowed
    ]
    if unrelated:
        raise CommitPolicyError(
            "unrelated_staged_files",
            "Commit refused because unrelated staged files are present in the real index",
            files_validated=files_validated,
        )


def _finalize_stage_paths(repo_root: Path, requested_paths: Iterable[str]) -> list[str]:
    selected = set(_normalize_explicit_paths(requested_paths))
    if not selected:
        return []

    stage_paths: list[str] = []
    seen: set[str] = set()
    for entry in _iter_porcelain_v1_z_entries(repo_root):
        entry_path = entry["path"]
        source_path = entry.get("rename_source_path", "")
        if entry_path not in selected and source_path not in selected:
            continue
        for candidate in (entry_path, source_path):
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            stage_paths.append(candidate)
    return stage_paths


def finalize_explicit_changes(
    repo_root: Path,
    paths: Iterable[str],
    *,
    tool_name: str,
    run_id: str = "",
    require_commit_report: bool = True,
    commit_title: str | None = None,
    commit_description: str = "",
) -> dict[str, Any]:
    selected = _normalize_explicit_paths(paths)
    for file_name in selected:
        validate_repo_relative_path(repo_root, file_name)

    if not selected:
        return {
            "commit_required": False,
            "commit_attempted": False,
            "commit_hash": "",
            "commit_error": "",
            "commit_result": {
                "ok": True,
                "reason": "no_paths",
                "staged_paths": [],
                "git_status": git_status(repo_root),
                "remaining_dirty_files": changed_files(repo_root),
            },
        }

    stage_paths = _finalize_stage_paths(repo_root, selected)
    if not stage_paths:
        return {
            "commit_required": False,
            "commit_attempted": False,
            "commit_hash": "",
            "commit_error": "",
            "commit_result": {
                "ok": True,
                "reason": "no_matching_changes",
                "staged_paths": [],
                "git_status": git_status(repo_root),
                "remaining_dirty_files": changed_files(repo_root),
            },
        }

    auto_title, auto_description = _build_auto_commit_metadata(
        tool_name, run_id, stage_paths
    )
    title = commit_title or auto_title
    description = commit_description or ""
    if commit_title:
        description = "\n".join(item for item in (description, auto_description) if item)
    else:
        description = auto_description
    _validate_commit_metadata(title, description, files_validated=True)
    manifest_before = dry_run_stage_manifest(repo_root)
    before_head = git_head(repo_root)
    commit_env = os.environ.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": SOMA_COMMITTER_NAME,
            "GIT_AUTHOR_EMAIL": SOMA_COMMITTER_EMAIL,
            "GIT_COMMITTER_NAME": SOMA_COMMITTER_NAME,
            "GIT_COMMITTER_EMAIL": SOMA_COMMITTER_EMAIL,
        }
    )

    git_temp_root = _git_path(repo_root, "index").parent / "soma-tmp"
    git_temp_root.mkdir(parents=True, exist_ok=True)
    commit_hash = ""
    with tempfile.TemporaryDirectory(prefix="finalize-", dir=git_temp_root) as temp_dir:
        temp_index = str(Path(temp_dir) / "index")
        commit_env["GIT_INDEX_FILE"] = temp_index
        try:
            if before_head:
                _run_git(repo_root, ["read-tree", "HEAD"], check=True, env=commit_env)
            else:
                _run_git(
                    repo_root, ["read-tree", "--empty"], check=True, env=commit_env
                )
            _run_git(
                repo_root,
                ["add", "-A", "--", *stage_paths],
                check=True,
                env=commit_env,
            )
            staged_diff = _run_git(
                repo_root,
                ["diff", "--cached", "--name-only", "--", *stage_paths],
                check=True,
                env=commit_env,
            ).stdout.splitlines()
            if not staged_diff:
                return {
                    "commit_required": False,
                    "commit_attempted": False,
                    "commit_hash": "",
                    "commit_error": "",
                    "commit_result": {
                        "ok": True,
                        "reason": "no_staged_diff",
                        "staged_paths": stage_paths,
                        "git_status": git_status(repo_root),
                        "remaining_dirty_files": changed_files(repo_root),
                    },
                }
            _run_git(
                repo_root,
                ["commit", "-m", title, "-m", description],
                check=True,
                env=commit_env,
            )
            commit_hash = _run_git(
                repo_root,
                ["rev-parse", "HEAD"],
                check=True,
            ).stdout.strip()
            # The commit was built with an isolated index so unrelated staged
            # changes remain untouched. Synchronize only the committed paths in
            # the real index with the new HEAD to avoid reporting them as dirty.
            _run_git(
                repo_root,
                ["add", "-A", "--", *stage_paths],
                check=True,
            )
        except GitCommandError as exc:
            failure = {
                "ok": False,
                "files_validated": True,
                "git_error": exc.diagnostics,
                "error": str(exc),
                "stage_manifest_before": manifest_before,
                "stage_manifest_after": dry_run_stage_manifest(repo_root),
                "remaining_dirty_files": changed_files(repo_root),
                "git_status": git_status(repo_root),
                "staged_paths": stage_paths,
                "title": title,
                "description": description,
            }
            return {
                "commit_required": True,
                "commit_attempted": True,
                "commit_hash": commit_hash,
                "commit_error": str(exc),
                "commit_result": failure,
            }
    success = {
        "ok": True,
        "files_validated": True,
        "commit_hash": commit_hash,
        "stage_manifest_before": manifest_before,
        "stage_manifest_after": dry_run_stage_manifest(repo_root),
        "remaining_dirty_files": changed_files(repo_root),
        "git_status": git_status(repo_root),
        "staged_paths": stage_paths,
        "title": title,
        "description": description,
        "commit_report": (
            _build_commit_report(
                commit_hash=commit_hash,
                title=title,
                description=description,
                mode="explicit_isolated",
                files_validated=True,
                staged_paths=stage_paths,
            )
            if require_commit_report
            else {}
        ),
        "error": "",
    }
    return {
        "commit_required": True,
        "commit_attempted": True,
        "commit_hash": commit_hash,
        "commit_error": "",
        "commit_result": success,
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
    *,
    refuse_unrelated_staged_files: bool = True,
    require_commit_report: bool = True,
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
    if refuse_unrelated_staged_files:
        _reject_unrelated_staged_files(
            manifest_before, selected, files_validated=True
        )
    snapshot = _snapshot_index(repo_root)
    try:
        _run_git(repo_root, ["add", "--sparse", "--", *selected], check=True)
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
        "commit_report": (
            _build_commit_report(
                commit_hash=commit_hash,
                title=title,
                description=description,
                mode="explicit_selected",
                files_validated=True,
                staged_paths=selected,
            )
            if require_commit_report
            else {}
        ),
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


def commit_all_changes(
    repo_root: Path,
    title: str,
    description: str = "",
    *,
    commit_mode: str = "explicit_only",
    require_commit_report: bool = True,
) -> dict:
    if commit_mode == "explicit_only":
        raise CommitPolicyError(
            "commit_all_disabled",
            "Repository policy forbids commit-all behavior unless commit_mode allows it",
            files_validated=False,
        )
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
        "commit_report": (
            _build_commit_report(
                commit_hash=commit_hash,
                title=title,
                description=description or "",
                mode="all_tracked_and_untracked",
                files_validated=False,
                staged_paths=manifest_before.get("staged", []),
            )
            if require_commit_report
            else {}
        ),
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
