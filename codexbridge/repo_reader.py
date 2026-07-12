"""
repo_reader.py — safe, read-only repository access for CodexBridge.

All public functions accept a resolved repo_root (Path) and repo-relative
POSIX strings.  They never accept or return absolute paths from the caller
and never invoke Codex CLI, any AI model, or any agent component.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .safety import validate_repo_relative_path, redact_secret_values


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
MAX_FILE_BYTES = 500_000  # cap on file content returned
MAX_DIFF_BYTES = 300_000  # cap on git diff output
MAX_SEARCH_SNIPPET_BYTES = 4_000  # cap per search hit snippet (unused directly)
MAX_BINARY_PROBE = 8_192  # bytes to probe for binary detection

# ---------------------------------------------------------------------------
# Blocked path components (applies to every segment of a path)
# ---------------------------------------------------------------------------
_BLOCKED_NAMES: frozenset[str] = frozenset(
    [
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".codex-pytest-temp",
        ".tmp.driveupload",
        ".tox",
        ".nox",
        "node_modules",
        "runs",
        "dist",
        "build",
        "coverage",
        "htmlcov",
        ".next",
        "generated",
        "media",
        "artifacts",
        "models",
        "credentials",
        "secrets",
    ]
)

_BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    [".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".bak", ".tmp"]
)

# Extra single-file blocked names (case-insensitive)
_BLOCKED_FILE_NAMES: frozenset[str] = frozenset(["desktop.ini"])

# .env files are blocked except for these exact base names
_ALLOWED_ENV_NAMES: frozenset[str] = frozenset(
    [".env.example", ".env.sample", ".env.template"]
)

# Redaction: simple key=value patterns for obvious secrets in text
_SECRET_LINE_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|credential|bearer)\s*[:=]\s*['\"]?[^'\"\s]+"
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _posix_relative(repo_root: Path, absolute: Path) -> str:
    """Return a POSIX-style repo-relative string, never exposing repo_root."""
    return absolute.relative_to(repo_root).as_posix()


def _is_blocked_name(name: str) -> bool:
    """Return True if the path component is in the blocked-name list."""
    lower = name.lower()
    # blocked exact names
    if lower in _BLOCKED_NAMES:
        return True
    # blocked single-file names
    if lower in _BLOCKED_FILE_NAMES:
        return True
    # blocked extensions
    suffix = Path(name).suffix.lower()
    if suffix in _BLOCKED_EXTENSIONS:
        return True
    return False


def _is_blocked_env(name: str) -> bool:
    """Return True if this looks like a real .env file (not the allowed examples)."""
    lower = name.lower()
    if not lower.startswith(".env"):
        return False
    # allow the specific safe templates
    return lower not in _ALLOWED_ENV_NAMES


def _path_is_allowed(repo_root: Path, absolute: Path) -> bool:
    """
    Return True only if every component of the path is allowed.
    Checks:
    - no blocked names in any path segment
    - no real .env files
    - no symlink/junction escape outside repo_root
    """
    try:
        rel = absolute.relative_to(repo_root)
    except ValueError:
        return False

    for part in rel.parts:
        if _is_blocked_name(part):
            return False
        if _is_blocked_env(part):
            return False

    # Symlink / junction escape check: resolve and verify still inside repo
    try:
        resolved = absolute.resolve()
        resolved.relative_to(repo_root.resolve())
    except (ValueError, OSError):
        return False

    # Extra: detect Windows junction points (reparse points) via st_reparse_tag
    if os.name == "nt":
        try:
            st = os.lstat(absolute)
            # FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            if st.st_file_attributes & 0x400:  # type: ignore[attr-defined]
                return False
        except (AttributeError, OSError):
            pass

    return True


def _resolve_and_validate(repo_root: Path, relative_path: str) -> Path:
    """
    Full validation pipeline for a caller-supplied relative path.
    Uses safety.validate_repo_relative_path for the structural checks,
    then additionally applies the blocked-name list and symlink escape check.
    """
    # structural checks (absolute, UNC, drive, wildcard, traversal)
    absolute = validate_repo_relative_path(repo_root, relative_path)
    if not _path_is_allowed(repo_root, absolute):
        raise ValueError(f"Path is not allowed: {relative_path}")
    return absolute


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------


def _is_binary(path: Path) -> bool:
    """Heuristic binary check: look for null bytes in the first 8 KiB."""
    try:
        with path.open("rb") as fh:
            chunk = fh.read(MAX_BINARY_PROBE)
        return b"\x00" in chunk
    except OSError:
        return True  # unreadable → treat as binary


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def _redact_text(text: str) -> str:
    """Redact obvious secret values using the existing safety helper."""
    return redact_secret_values(text)


# ---------------------------------------------------------------------------
# SHA-256 and Git HEAD helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's raw bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head(repo_root: Path) -> str:
    """Return current HEAD commit hash, or empty string if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# list_repo_files
# ---------------------------------------------------------------------------


def list_repo_files(
    repo_root: Path,
    directory: str = "",
    max_results: int = 500,
) -> dict:
    """
    Recursively list files under *directory* (repo-relative POSIX).
    Returns repo-relative POSIX paths only.
    Skips blocked names and symlinks/junctions.
    """
    max_results = max(1, min(int(max_results), 2000))

    if directory:
        base_abs = _resolve_and_validate(repo_root, directory)
        if not base_abs.is_dir():
            raise ValueError(f"Not a directory: {directory}")
    else:
        base_abs = repo_root

    # Prefer Git's ignore-aware tracked/untracked view. A filesystem fallback
    # remains necessary for test fixtures and repositories without a usable
    # Git worktree.
    git_files = _git_list_repo_files(repo_root, directory)
    if git_files is not None:
        files = git_files[:max_results]
        return {
            "ok": True,
            "repo_name": "",
            "directory": directory,
            "files": sorted(files),
            "count": len(files),
            "truncated": len(git_files) > max_results,
            "max_results": max_results,
            "error": "",
        }

    files: list[str] = []
    truncated = False
    count = 0

    for dirpath, dirnames, filenames in os.walk(base_abs):
        current = Path(dirpath)

        # Prune blocked directories in-place (modifies the walk)
        original_dirs = list(dirnames)
        dirnames[:] = []
        for d in original_dirs:
            child = current / d
            if _path_is_allowed(repo_root, child) and not child.is_symlink():
                dirnames.append(d)

        for filename in sorted(filenames):
            if count >= max_results:
                truncated = True
                break
            child = current / filename
            if not _path_is_allowed(repo_root, child):
                continue
            if child.is_symlink():
                continue
            files.append(_posix_relative(repo_root, child))
            count += 1

        if truncated:
            break

    return {
        "ok": True,
        "repo_name": "",  # filled in by server.py
        "directory": directory,
        "files": sorted(files),
        "count": len(files),
        "truncated": truncated,
        "max_results": max_results,
        "error": "",
    }


def _git_list_repo_files(repo_root: Path, directory: str) -> list[str] | None:
    git_marker = repo_root / ".git"
    if git_marker.is_dir() and not (git_marker / "HEAD").is_file():
        return None
    args = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    if directory:
        args.extend(["--", directory])
    try:
        result = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    files: list[str] = []
    for raw in result.stdout.splitlines():
        relative = raw.strip().replace("\\", "/")
        if not relative:
            continue
        try:
            absolute = _resolve_and_validate(repo_root, relative)
        except ValueError:
            continue
        if absolute.is_file() and not absolute.is_symlink():
            files.append(relative)
    return sorted(set(files))


# ---------------------------------------------------------------------------
# read_repo_file
# ---------------------------------------------------------------------------


def read_repo_file(
    repo_root: Path,
    path: str,
    start_line: int = 1,
    end_line: int = 0,
) -> dict:
    """
    Read a text file at *path* (repo-relative POSIX), optionally bounded by
    *start_line*/*end_line* (1-indexed, inclusive; 0 = no limit).

    Rejects binary files and files larger than MAX_FILE_BYTES.
    Redacts obvious secret values before returning.
    """
    absolute = _resolve_and_validate(repo_root, path)

    if not absolute.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if absolute.is_dir():
        raise ValueError(f"Path is a directory: {path}")
    if absolute.is_symlink():
        raise ValueError(f"Symlinks are not allowed: {path}")

    size = absolute.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"File exceeds {MAX_FILE_BYTES} byte limit ({size} bytes): {path}"
        )
    if _is_binary(absolute):
        raise ValueError(f"Binary files are not supported: {path}")

    raw = absolute.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    total_lines = len(lines)

    # Normalise line numbers (1-indexed, inclusive)
    start = max(1, int(start_line))
    end = int(end_line) if end_line and end_line > 0 else total_lines

    if start > end or start > total_lines:
        selected = ""
    else:
        selected = "".join(lines[start - 1 : end])

    content = _redact_text(selected)
    truncated = start > 1 or end < total_lines

    return {
        "ok": True,
        "repo_name": "",
        "path": path,
        "content": content,
        "start_line": start,
        "end_line": min(end, total_lines),
        "total_lines": total_lines,
        "size_bytes": size,
        "sha256": _sha256_file(absolute),
        "git_head": _git_head(repo_root),
        "truncated": truncated,
        "error": "",
    }


# ---------------------------------------------------------------------------
# search_repo_text
# ---------------------------------------------------------------------------


def search_repo_text(
    repo_root: Path,
    query: str,
    directory: str = "",
    max_results: int = 50,
    case_sensitive: bool = False,
    file_patterns: list[str] | None = None,
    budget_ms: int = 5_000,
) -> dict:
    """
    Search for *query* as a literal substring in text files under *directory*.
    Returns up to *max_results* hits, each with file path, line number, and
    redacted snippet.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    max_results = max(1, min(int(max_results), 500))
    budget_ms = max(100, min(int(budget_ms), 30_000))

    if directory:
        base_abs = _resolve_and_validate(repo_root, directory)
        if not base_abs.is_dir():
            raise ValueError(f"Not a directory: {directory}")
    else:
        base_abs = repo_root

    patterns = list(file_patterns or [])
    if len(patterns) > 20 or any(
        not isinstance(pattern, str)
        or not pattern.strip()
        or len(pattern) > 200
        or Path(pattern).is_absolute()
        or ".." in Path(pattern).parts
        for pattern in patterns
    ):
        raise ValueError("file_patterns must contain safe, non-empty glob patterns")

    rg = shutil.which("rg")
    if rg:
        return _search_with_ripgrep(
            repo_root,
            query,
            directory,
            max_results,
            case_sensitive,
            patterns,
            budget_ms,
        )

    # Safe bounded fallback for environments without ripgrep.
    started = time.monotonic()
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    hits: list[dict] = []
    files_examined = 0
    timed_out = False
    for dirpath, dirnames, filenames in os.walk(base_abs):
        current = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if _path_is_allowed(repo_root, current / d)
            and not (current / d).is_symlink()
        ]
        for filename in sorted(filenames):
            if (time.monotonic() - started) * 1000 >= budget_ms:
                timed_out = True
                break
            child = current / filename
            if not _path_is_allowed(repo_root, child) or child.is_symlink():
                continue
            if patterns and not any(Path(filename).match(p) for p in patterns):
                continue
            files_examined += 1
            if _is_binary(child):
                continue
            try:
                if child.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = child.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append({"path": _posix_relative(repo_root, child), "line": lineno, "snippet": _redact_text(line[:200])})
                    if len(hits) >= max_results:
                        timed_out = True
                        break
            if timed_out:
                break
        if timed_out:
            break
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    if timed_out and len(hits) < max_results:
        return {
            "ok": False,
            "status": "interactive_search_budget_exceeded",
            "fresh": False,
            "repo_name": "",
            "query": query,
            "directory": directory,
            "case_sensitive": case_sensitive,
            "hits": [],
            "partial_results": hits,
            "count": len(hits),
            "files_examined": files_examined,
            "duration_ms": duration_ms,
            "truncated": True,
            "max_results": max_results,
            "recommended_action": "Narrow the directory/query or start a durable repository-analysis job.",
            "error": "Interactive search budget exceeded",
        }
    return {
        "ok": True,
        "status": "available",
        "fresh": True,
        "repo_name": "",
        "query": query,
        "directory": directory,
        "case_sensitive": case_sensitive,
        "hits": hits[:max_results],
        "count": min(len(hits), max_results),
        "files_examined": files_examined,
        "duration_ms": duration_ms,
        "truncated": len(hits) >= max_results,
        "max_results": max_results,
        "error": "",
    }


def _search_with_ripgrep(
    repo_root: Path,
    query: str,
    directory: str,
    max_results: int,
    case_sensitive: bool,
    file_patterns: list[str],
    budget_ms: int,
) -> dict:
    started = time.monotonic()
    args = [
        "rg",
        "--json",
        "--no-heading",
        "--color",
        "never",
        "--fixed-strings",
        "--max-filesize",
        str(MAX_FILE_BYTES),
    ]
    if not case_sensitive:
        args.append("--ignore-case")
    for pattern in file_patterns:
        args.extend(["--glob", pattern])
    # rg already honors .gitignore; these additional ignores cover generated
    # artifacts that are often outside a repository's .gitignore.
    target_is_generated = directory and any(
        part.lower() in _BLOCKED_NAMES for part in Path(directory).parts
    )
    if not target_is_generated:
        for excluded in ("runs", ".codex-pytest-temp", "generated", "media", "artifacts", "models"):
            args.extend(["--glob", f"!{excluded}/**"])
    args.extend(["--", query, directory or "."])
    try:
        completed = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=budget_ms / 1000,
        )
        timed_out = False
        raw_output = completed.stdout
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw_output = exc.stdout or ""
        if isinstance(raw_output, bytes):
            raw_output = raw_output.decode("utf-8", errors="replace")
    except OSError as exc:
        return {
            "ok": False,
            "status": "failed",
            "fresh": False,
            "repo_name": "",
            "query": query,
            "directory": directory,
            "case_sensitive": case_sensitive,
            "hits": [],
            "partial_results": [],
            "count": 0,
            "files_examined": 0,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "truncated": False,
            "max_results": max_results,
            "error": str(exc),
        }

    hits: list[dict] = []
    files: set[str] = set()
    for line in str(raw_output).splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data") or {}
        path_data = data.get("path") or {}
        relative = str(path_data.get("text") or "").replace("\\", "/")
        if relative.startswith("./"):
            relative = relative[2:]
        if not relative:
            continue
        files.add(relative)
        text = str(data.get("lines", {}).get("text", "")).rstrip("\r\n")
        hits.append({"path": relative, "line": int(data.get("line_number") or 0), "snippet": _redact_text(text[:200])})
        if len(hits) >= max_results:
            break
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    if timed_out:
        return {
            "ok": False,
            "status": "interactive_search_budget_exceeded",
            "fresh": False,
            "repo_name": "",
            "query": query,
            "directory": directory,
            "case_sensitive": case_sensitive,
            "hits": [],
            "partial_results": hits,
            "count": len(hits),
            "files_examined": len(files),
            "duration_ms": duration_ms,
            "truncated": True,
            "max_results": max_results,
            "recommended_action": "Narrow the directory/query or start a durable repository-analysis job.",
            "error": "Interactive search budget exceeded",
        }
    if completed.returncode not in {0, 1}:
        return {
            "ok": False,
            "status": "failed",
            "fresh": False,
            "repo_name": "",
            "query": query,
            "directory": directory,
            "case_sensitive": case_sensitive,
            "hits": [],
            "partial_results": hits,
            "count": len(hits),
            "files_examined": len(files),
            "duration_ms": duration_ms,
            "truncated": False,
            "max_results": max_results,
            "error": completed.stderr.strip()[:1000],
        }
    return {
        "ok": True,
        "status": "available",
        "fresh": True,
        "repo_name": "",
        "query": query,
        "directory": directory,
        "case_sensitive": case_sensitive,
        "hits": hits,
        "count": len(hits),
        "files_examined": len(files),
        "duration_ms": duration_ms,
        "truncated": len(hits) >= max_results,
        "max_results": max_results,
        "error": "",
    }


# ---------------------------------------------------------------------------
# get_recently_modified_files
# ---------------------------------------------------------------------------


def get_recently_modified_files(repo_root: Path, limit: int = 50) -> dict:
    """
    Return up to *limit* files sorted by filesystem mtime (newest first).
    Uses local filesystem mtime so unsaved / unstaged changes are visible.
    Skips blocked names, symlinks, and binary files.
    """
    limit = max(1, min(int(limit), 500))
    candidates: list[tuple[float, str]] = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        current = Path(dirpath)

        original_dirs = list(dirnames)
        dirnames[:] = []
        for d in original_dirs:
            child = current / d
            if _path_is_allowed(repo_root, child) and not child.is_symlink():
                dirnames.append(d)

        for filename in filenames:
            child = current / filename
            if not _path_is_allowed(repo_root, child):
                continue
            if child.is_symlink():
                continue
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, _posix_relative(repo_root, child)))

    candidates.sort(key=lambda t: t[0], reverse=True)
    top = candidates[:limit]

    return {
        "ok": True,
        "repo_name": "",
        "files": [{"path": rel_path, "mtime": mtime} for mtime, rel_path in top],
        "count": len(top),
        "limit": limit,
        "error": "",
    }


# ---------------------------------------------------------------------------
# read_repo_files (batch)
# ---------------------------------------------------------------------------

MAX_BATCH_REQUESTS = 20
MAX_BATCH_COMBINED_BYTES = 2_000_000  # 2 MB combined content


def read_repo_files(
    repo_root: Path,
    requests: list[dict],
) -> dict:
    """
    Read multiple files in a single call.

    Each request: {"path": str, "start_line": int, "end_line": int}
    At most MAX_BATCH_REQUESTS requests.
    Combined content capped at MAX_BATCH_COMBINED_BYTES.
    Reuses read_repo_file security, size, and redaction logic.
    """
    if not isinstance(requests, list):
        raise ValueError("requests must be a list")
    if len(requests) > MAX_BATCH_REQUESTS:
        raise ValueError(
            f"Too many requests: {len(requests)} (max {MAX_BATCH_REQUESTS})"
        )

    results: list[dict] = []
    combined_bytes = 0
    truncated_batch = False

    for req in requests:
        path = req.get("path", "")
        start_line = int(req.get("start_line", 1) or 1)
        end_line = int(req.get("end_line", 0) or 0)
        try:
            item = read_repo_file(
                repo_root, path, start_line=start_line, end_line=end_line
            )
            combined_bytes += len(item.get("content", "").encode("utf-8"))
            if combined_bytes > MAX_BATCH_COMBINED_BYTES:
                truncated_batch = True
                item["content"] = ""
                item["truncated"] = True
                item["error"] = "Combined output limit reached; content omitted"
            results.append(item)
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "repo_name": "",
                    "path": path,
                    "content": "",
                    "start_line": start_line,
                    "end_line": end_line,
                    "total_lines": 0,
                    "size_bytes": 0,
                    "sha256": "",
                    "git_head": "",
                    "truncated": False,
                    "error": str(exc),
                }
            )

    return {
        "ok": True,
        "repo_name": "",
        "results": results,
        "count": len(results),
        "truncated_batch": truncated_batch,
        "error": "",
    }


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------


def git_log(
    repo_root: Path,
    limit: int = 20,
    path: str = "",
) -> dict:
    """
    Return structured git log entries.

    limit – max number of commits to return (1–200)
    path  – optional repo-relative path to scope the log
    """
    limit = max(1, min(int(limit), 200))

    args = [
        "log",
        f"-n{limit}",
        "--format=%H%x1f%an%x1f%ae%x1f%ai%x1f%s",
    ]

    if path:
        validated = validate_repo_relative_path(repo_root, path)
        rel = validated.relative_to(repo_root)
        args.extend(["--", rel.as_posix()])

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        raw = result.stdout.strip()
    except OSError as exc:
        return {
            "ok": False,
            "repo_name": "",
            "commits": [],
            "count": 0,
            "path": path,
            "error": str(exc),
        }

    commits: list[dict] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 4)
        if len(parts) < 5:
            continue
        commits.append(
            {
                "sha": parts[0],
                "author_name": parts[1],
                "author_email": parts[2],
                "date": parts[3],
                "subject": parts[4],
            }
        )

    return {
        "ok": True,
        "repo_name": "",
        "commits": commits,
        "count": len(commits),
        "path": path,
        "error": "",
    }
