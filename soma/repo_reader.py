"""
repo_reader.py — safe, read-only repository access for Soma.

All public functions accept a resolved repo_root (Path) and repo-relative
POSIX strings.  They never accept or return absolute paths from the caller
and never invoke an AI model, coding-agent CLI, or agent component.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from pathlib import Path

from .public_projection_contract import DEFAULT_PUBLIC_BYTE_BUDGETS
from .safety import validate_repo_relative_path, redact_secret_values


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
MAX_FILE_BYTES = 500_000  # cap on file content returned
MAX_DIFF_BYTES = 300_000  # cap on git diff output
MAX_SEARCH_SNIPPET_BYTES = 4_000  # cap per search hit snippet (unused directly)
MAX_BINARY_PROBE = 8_192  # bytes to probe for binary detection
DEFAULT_FILE_WINDOW_LINES = 300
DEFAULT_READ_RESPONSE_BYTES = DEFAULT_PUBLIC_BYTE_BUDGETS.repository_read_batch
MAX_READ_RESPONSE_BYTES = 128 * 1024
_READ_RESPONSE_METADATA_RESERVE = 4 * 1024
_FILE_CURSOR_VERSION = 1
DEFAULT_SEARCH_RESPONSE_BYTES = 16 * 1024
MAX_SEARCH_RESPONSE_BYTES = 16 * 1024
MAX_NEWLINE_DIAGNOSTIC_BYTES = 8 * 1024
MAX_NEWLINE_DIAGNOSTIC_RANGES = 20
_SEARCH_CURSOR_VERSION = 1
_SEARCH_SNIPPET_CHARS = 800

# ---------------------------------------------------------------------------
# Blocked path components (applies to every segment of a path)
# ---------------------------------------------------------------------------
_BLOCKED_NAMES: frozenset[str] = frozenset(
    [
        ".git",
        ".soma",
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
    *,
    start_byte: int | None = None,
    continuation: str = "",
    content_budget_bytes: int = 40 * 1024,
) -> dict:
    """
    Read a text file at *path* (repo-relative POSIX), optionally bounded by
    *start_line*/*end_line* (1-indexed, inclusive; 0 = no limit).

    Large text files are streamed. Returned content is bounded and redacted.
    Continuations are bound to the repository-relative path and content SHA-256.
    """
    absolute = _resolve_and_validate(repo_root, path)

    if not absolute.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if absolute.is_dir():
        raise ValueError(f"Path is a directory: {path}")
    if absolute.is_symlink():
        raise ValueError(f"Symlinks are not allowed: {path}")

    if _is_binary(absolute):
        raise ValueError(f"Binary files are not supported: {path}")

    initial_stat = absolute.stat()
    analysis = analyze_text_file(absolute)
    size = analysis["size_bytes"]
    content_sha256 = analysis["sha256"]
    total_lines = analysis["total_lines"]
    cursor_state = _decode_file_cursor(continuation) if continuation else None
    if cursor_state:
        if cursor_state["path"] != path:
            raise ValueError("File continuation path mismatch")
        if cursor_state["content_sha256"] != content_sha256:
            return _stale_file_response(path, content_sha256, size, total_lines)
        mode = cursor_state["mode"]
        start = int(cursor_state["next_start_line"])
        byte_offset = int(cursor_state["next_byte_offset"])
    else:
        mode = "byte" if start_byte is not None else "line"
        start = max(1, int(start_line))
        byte_offset = max(0, int(start_byte or 0))

    budget = max(1, int(content_budget_bytes))
    requested_end = int(end_line) if end_line and end_line > 0 else 0
    if mode == "byte":
        raw, next_byte_offset = _read_byte_window(absolute, byte_offset, budget)
        start = _line_number_at_offset(absolute, byte_offset)
        end = _line_number_at_offset(absolute, next_byte_offset)
        next_start_line = end
        window_complete = next_byte_offset >= size
    else:
        raw, byte_offset, next_byte_offset, end, next_start_line, window_complete = (
            _read_line_window(
                absolute,
                start,
                requested_end,
                budget,
                initial_offset=(
                    byte_offset if cursor_state and mode == "line" else None
                ),
            )
        )

    content, consumed_bytes = _decode_redacted_prefix(raw, budget)
    if consumed_bytes < len(raw):
        next_byte_offset = byte_offset + consumed_bytes
        next_start_line = _line_number_at_offset(absolute, next_byte_offset)
        window_complete = False
        continuation_mode = "byte"
    else:
        continuation_mode = mode
    unchanged = absolute.stat()
    if (unchanged.st_size, unchanged.st_mtime_ns) != (
        initial_stat.st_size,
        initial_stat.st_mtime_ns,
    ):
        return _stale_file_response(path, _sha256_file(absolute), unchanged.st_size, 0)

    has_more = not window_complete
    next_cursor = (
        _encode_file_cursor(
            path=path,
            content_sha256=content_sha256,
            mode=continuation_mode,
            next_start_line=next_start_line,
            next_byte_offset=next_byte_offset,
        )
        if has_more
        else ""
    )
    truncated = byte_offset > 0 or start > 1 or has_more
    truncation_reason = ""
    if has_more:
        if requested_end and end >= requested_end:
            truncation_reason = "requested_range"
        elif mode == "line" and end - start + 1 >= DEFAULT_FILE_WINDOW_LINES:
            truncation_reason = "line_window"
        else:
            truncation_reason = "response_budget"

    return {
        "ok": True,
        "repo_name": "",
        "path": path,
        "content": content,
        "start_line": start,
        "end_line": min(end, total_lines),
        "total_lines": total_lines,
        "size_bytes": size,
        "sha256": content_sha256,
        "content_sha256": content_sha256,
        "newline_diagnostic": analysis["newline_diagnostic"],
        "start_byte": byte_offset,
        "end_byte": next_byte_offset,
        "next_start_line": next_start_line if has_more else None,
        "next_byte_offset": next_byte_offset if has_more else None,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "truncation_reason": truncation_reason,
        "git_head": _git_head(repo_root),
        "truncated": truncated,
        "error": "",
    }


def analyze_text_file(path: Path) -> dict:
    """Return one streaming identity and exact bounded newline diagnostic."""
    digest = hashlib.sha256()
    size = 0
    counts = {"lf": 0, "crlf": 0, "cr": 0}
    newline_ranges: list[dict[str, int | str]] = []
    newline_ranges_total = 0
    current_kind = ""
    current_end_line = 0
    current_range_index: int | None = None
    line_number = 1
    pending_cr = False
    ends_with_newline = False

    def record(kind: str) -> None:
        nonlocal current_kind, current_end_line, current_range_index
        nonlocal line_number, newline_ranges_total
        counts[kind] += 1
        if current_kind == kind and current_end_line == line_number - 1:
            current_end_line = line_number
            if current_range_index is not None:
                newline_ranges[current_range_index]["end_line"] = line_number
        else:
            current_kind = kind
            current_end_line = line_number
            newline_ranges_total += 1
            if len(newline_ranges) < MAX_NEWLINE_DIAGNOSTIC_RANGES:
                newline_ranges.append(
                    {
                        "start_line": line_number,
                        "end_line": line_number,
                        "newline": kind,
                    }
                )
                current_range_index = len(newline_ranges) - 1
            else:
                current_range_index = None
        line_number += 1

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
            data = (b"\r" if pending_cr else b"") + chunk
            pending_cr = False
            if data.endswith(b"\r"):
                pending_cr = True
                data = data[:-1]
            matches = list(re.finditer(rb"\r\n|\r|\n", data))
            for match in matches:
                token = match.group(0)
                record("crlf" if token == b"\r\n" else "cr" if token == b"\r" else "lf")
            if data:
                ends_with_newline = bool(matches and matches[-1].end() == len(data))
    if pending_cr:
        record("cr")
        ends_with_newline = True

    total_lines = sum(counts.values()) + (1 if size and not ends_with_newline else 0)
    diagnostic: dict[str, object] = {
        "counts": counts,
        "mixed": sum(value > 0 for value in counts.values()) > 1,
        "newline_ranges": newline_ranges,
        "newline_ranges_total": newline_ranges_total,
        "newline_ranges_truncated": newline_ranges_total > len(newline_ranges),
        "ends_with_newline": ends_with_newline,
        "response_bytes": 0,
    }
    while True:
        response_bytes = len(
            json.dumps(diagnostic, separators=(",", ":")).encode("utf-8")
        )
        if response_bytes <= MAX_NEWLINE_DIAGNOSTIC_BYTES or not newline_ranges:
            diagnostic["response_bytes"] = response_bytes
            final_bytes = len(
                json.dumps(diagnostic, separators=(",", ":")).encode("utf-8")
            )
            if final_bytes == response_bytes:
                break
            diagnostic["response_bytes"] = final_bytes
            if len(
                json.dumps(diagnostic, separators=(",", ":")).encode("utf-8")
            ) == final_bytes:
                break
        else:
            newline_ranges.pop()
            diagnostic["newline_ranges_truncated"] = True

    return {
        "sha256": digest.hexdigest(),
        "size_bytes": size,
        "total_lines": total_lines,
        "newline_diagnostic": diagnostic,
    }


def _read_line_window(
    path: Path,
    start_line: int,
    end_line: int,
    budget: int,
    *,
    initial_offset: int | None = None,
) -> tuple[bytes, int, int, int, int, bool]:
    selected: list[bytes] = []
    selected_bytes = 0
    start_offset = 0
    next_offset = 0
    end = max(0, start_line - 1)
    next_start_line = start_line
    window_complete = True
    maximum_lines = end_line - start_line + 1 if end_line else DEFAULT_FILE_WINDOW_LINES
    with path.open("rb") as handle:
        if initial_offset is not None:
            handle.seek(initial_offset)
            line_number = start_line - 1
        else:
            line_number = 0
        while True:
            line_offset = handle.tell()
            remaining_budget = max(1, budget - selected_bytes)
            raw_line = handle.readline(remaining_budget + 1)
            if not raw_line:
                break
            line_number += 1
            if line_number < start_line:
                continue
            if not selected:
                start_offset = line_offset
            if line_number > end_line > 0 or len(selected) >= maximum_lines:
                next_offset = line_offset
                next_start_line = line_number
                window_complete = False
                break
            if selected and selected_bytes + len(raw_line) > budget:
                next_offset = line_offset
                next_start_line = line_number
                window_complete = False
                break
            selected.append(raw_line)
            selected_bytes += len(raw_line)
            next_offset = handle.tell()
            end = line_number
            next_start_line = line_number + 1
            if selected_bytes >= budget:
                window_complete = next_offset >= path.stat().st_size
                break
    return b"".join(selected), start_offset, next_offset, end, next_start_line, window_complete


def _read_byte_window(path: Path, start_byte: int, budget: int) -> tuple[bytes, int]:
    size = path.stat().st_size
    offset = min(start_byte, size)
    with path.open("rb") as handle:
        handle.seek(offset)
        raw = handle.read(budget)
    return raw, offset + len(raw)


def _line_number_at_offset(path: Path, offset: int) -> int:
    remaining = max(0, int(offset))
    newline_count = 0
    with path.open("rb") as handle:
        while remaining:
            chunk = handle.read(min(64 * 1024, remaining))
            if not chunk:
                break
            newline_count += chunk.count(b"\n")
            remaining -= len(chunk)
    return newline_count + 1


def _decode_redacted_prefix(raw: bytes, budget: int) -> tuple[str, int]:
    low, high = 0, len(raw)
    best_text = ""
    best_size = 0
    while low <= high:
        midpoint = (low + high) // 2
        decoded = raw[:midpoint].decode("utf-8", errors="replace")
        text = _redact_text(decoded.replace("\r\n", "\n").replace("\r", "\n"))
        if len(text.encode("utf-8")) <= budget:
            best_text = text
            best_size = midpoint
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best_text, best_size


def _encode_file_cursor(**payload: object) -> str:
    encoded = json.dumps(
        {"version": _FILE_CURSOR_VERSION, **payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    return f"{body}.{hashlib.sha256(encoded).hexdigest()}"


def _decode_file_cursor(cursor: str) -> dict:
    try:
        body, checksum = cursor.split(".", 1)
        encoded = urlsafe_b64decode(body + ("=" * (-len(body) % 4)))
        if hashlib.sha256(encoded).hexdigest() != checksum:
            raise ValueError("File continuation checksum mismatch")
        payload = json.loads(encoded.decode("utf-8"))
    except (BinasciiError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid file continuation") from exc
    if payload.get("version") != _FILE_CURSOR_VERSION:
        raise ValueError("Unsupported file continuation version")
    return payload


def _stale_file_response(path: str, sha256: str, size: int, total_lines: int) -> dict:
    return {
        "ok": False,
        "status": "stale_content",
        "fresh": False,
        "repo_name": "",
        "path": path,
        "content": "",
        "content_sha256": sha256,
        "sha256": sha256,
        "size_bytes": size,
        "total_lines": total_lines,
        "next_cursor": "",
        "has_more": False,
        "truncated": False,
        "error": "File content changed; restart reading from the first window",
    }


# ---------------------------------------------------------------------------
# search_repo_fast
# ---------------------------------------------------------------------------

DEFAULT_FAST_SEARCH_RESPONSE_BYTES = 16 * 1024
MAX_FAST_SEARCH_RESPONSE_BYTES = 64 * 1024
_FAST_SEARCH_NOTICE = (
    "Fast lexical search results are navigation evidence only; reopen exact source "
    "with repo_query(read_files) before relying on source content."
)


def _run_fast_git(repo_root: Path, args: list[str], deadline: float) -> subprocess.CompletedProcess[bytes]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(["git", *args], 0)
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=False,
        timeout=max(0.001, remaining),
        env=env,
        check=False,
    )


def _fast_search_patterns(file_patterns: list[str] | None) -> list[str]:
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
    return patterns


def _fast_search_read_head(repo_root: Path) -> str:
    """Resolve HEAD from the exact repository marker without spawning Git."""
    marker = repo_root / ".git"
    try:
        if marker.is_symlink():
            return ""
        if marker.is_dir():
            git_dir = marker
        elif marker.is_file():
            marker_text = marker.read_text(encoding="utf-8", errors="strict").strip()
            if not marker_text.lower().startswith("gitdir:"):
                return ""
            raw_git_dir = marker_text.split(":", 1)[1].strip()
            if not raw_git_dir:
                return ""
            candidate = Path(raw_git_dir)
            git_dir = (
                candidate if candidate.is_absolute() else repo_root / candidate
            ).resolve()
            if not git_dir.is_dir():
                return ""
        else:
            return ""

        common_dir = git_dir
        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            raw_common = commondir_file.read_text(
                encoding="utf-8", errors="strict"
            ).strip()
            if not raw_common:
                return ""
            candidate = Path(raw_common)
            common_dir = (
                candidate if candidate.is_absolute() else git_dir / candidate
            ).resolve()
            if not common_dir.is_dir():
                return ""

        head_text = (git_dir / "HEAD").read_text(
            encoding="utf-8", errors="strict"
        ).strip()
        if head_text.startswith("ref:"):
            reference = head_text[4:].strip().replace("\\", "/")
            reference_parts = reference.split("/")
            if (
                not reference.startswith("refs/")
                or any(part in {"", ".", ".."} for part in reference_parts)
            ):
                return ""
            relative_ref = Path(*reference_parts)
            for base in (git_dir, common_dir):
                ref_file = base / relative_ref
                if ref_file.is_file():
                    candidate_head = ref_file.read_text(
                        encoding="ascii", errors="strict"
                    ).strip()
                    if re.fullmatch(r"[0-9A-Fa-f]{40,64}", candidate_head):
                        return candidate_head.lower()
            packed_refs = common_dir / "packed-refs"
            if packed_refs.is_file():
                with packed_refs.open("r", encoding="ascii", errors="strict") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line or line.startswith(("#", "^")):
                            continue
                        parts = line.split(" ", 1)
                        if len(parts) != 2 or parts[1] != reference:
                            continue
                        if re.fullmatch(r"[0-9A-Fa-f]{40,64}", parts[0]):
                            return parts[0].lower()
            return ""
        if re.fullmatch(r"[0-9A-Fa-f]{40,64}", head_text):
            return head_text.lower()
    except (OSError, UnicodeError):
        return ""
    return ""


def _fast_search_fallback_identity(
    repo_root: Path, deadline: float
) -> tuple[str, str]:
    """Fallback for unusual Git layouts while preserving exact-root identity."""
    identity = _run_fast_git(
        repo_root,
        ["rev-parse", "--is-inside-work-tree", "--show-toplevel", "HEAD"],
        deadline,
    )
    lines = identity.stdout.decode("utf-8", errors="replace").splitlines()
    exact_root = False
    if identity.returncode == 0 and len(lines) >= 3:
        try:
            exact_root = Path(lines[1]).resolve() == repo_root.resolve()
        except OSError:
            exact_root = False
    if (
        identity.returncode == 0
        and len(lines) >= 3
        and lines[0] == "true"
        and exact_root
        and re.fullmatch(r"[0-9A-Fa-f]{40,64}", lines[2].strip())
    ):
        return lines[2].strip().lower(), ""
    error = identity.stderr.decode("utf-8", errors="replace").strip()[:1000]
    return "", error or "Resolved Git top-level does not match the registered repository root"


def _fast_search_path_allowed(
    repo_root: Path, relative: str, patterns: list[str]
) -> bool:
    """Lexically validate a tracked path emitted by Git grep."""
    del repo_root
    normalized = relative.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith(("/", "//"))
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        return False
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    if any(_is_blocked_name(part) or _is_blocked_env(part) for part in parts):
        return False
    name = parts[-1]
    return not patterns or any(Path(name).match(pattern) for pattern in patterns)


def _fast_search_common_args(
    query: str,
    *,
    match_mode: str,
    case_sensitive: bool,
    operation_args: list[str],
) -> list[str]:
    args = ["grep", "-z", "-I", *operation_args]
    args.append("-F" if match_mode == "literal" else "-E")
    if not case_sensitive:
        args.append("-i")
    args.extend(["-e", query])
    return args


def _fast_search_scope_args(directory: str) -> list[str]:
    if not directory:
        return ["--"]
    return ["--", f":(top,literal){Path(directory).as_posix()}"]


def _fast_search_parse_counts(raw: bytes) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in raw.splitlines():
        parts = record.split(b"\x00", 1)
        if len(parts) != 2:
            continue
        path = parts[0].decode("utf-8", errors="replace").replace("\\", "/")
        try:
            count = int(parts[1].decode("ascii", errors="strict"))
        except (UnicodeDecodeError, ValueError):
            continue
        counts[path] = count
    return counts


def _fast_search_parse_matches(raw: bytes) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for record in raw.splitlines():
        parts = record.split(b"\x00", 3)
        if len(parts) != 4:
            continue
        path = parts[0].decode("utf-8", errors="replace").replace("\\", "/")
        try:
            line = int(parts[1].decode("ascii", errors="strict"))
            column = int(parts[2].decode("ascii", errors="strict"))
        except (UnicodeDecodeError, ValueError):
            continue
        text = parts[3].decode("utf-8", errors="replace").rstrip("\r\n")
        hits.append(
            {
                "path": path,
                "line": line,
                "column": column,
                "snippet": _redact_text(text[:_SEARCH_SNIPPET_CHARS]),
            }
        )
    return hits


def _fast_search_add_context(
    repo_root: Path,
    hits: list[dict[str, object]],
    context_lines: int,
) -> None:
    if context_lines <= 0 or not hits:
        return
    grouped: dict[str, list[dict[str, object]]] = {}
    for hit in hits:
        grouped.setdefault(str(hit["path"]), []).append(hit)
    for relative, file_hits in grouped.items():
        requested: set[int] = set()
        for hit in file_hits:
            center = int(hit["line"])
            requested.update(
                range(max(1, center - context_lines), center + context_lines + 1)
            )
        if not requested:
            continue
        wanted_max = max(requested)
        lines: dict[int, str] = {}
        path = repo_root / Path(relative)
        if not _path_is_allowed(repo_root, path) or path.is_symlink():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, text in enumerate(handle, 1):
                    if line_number in requested:
                        lines[line_number] = _redact_text(
                            text.rstrip("\r\n")[:_SEARCH_SNIPPET_CHARS]
                        )
                    if line_number >= wanted_max:
                        break
        except OSError:
            continue
        for hit in file_hits:
            center = int(hit["line"])
            hit["context"] = [
                {"line": line_number, "text": lines[line_number]}
                for line_number in range(
                    max(1, center - context_lines), center + context_lines + 1
                )
                if line_number in lines
            ]


def _fast_search_finalize(result: dict, response_budget_bytes: int) -> dict:
    def payload_size() -> int:
        return len(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )

    initial_size = payload_size()
    if initial_size <= response_budget_bytes:
        result["response_bytes"] = initial_size
        return result

    collection_key = "hits" if result.get("hits") else "files" if result.get("files") else ""
    if collection_key:
        original = list(result[collection_key])
        result["truncated"] = True
        result["has_more"] = True
        result["truncation_reason"] = "response_budget"
        low, high, best = 0, len(original), 0
        while low <= high:
            midpoint = (low + high) // 2
            result[collection_key] = original[:midpoint]
            result["count"] = midpoint
            if collection_key == "hits":
                result["match_count"] = midpoint
                result["match_count_complete"] = False
            if payload_size() <= response_budget_bytes:
                best = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1
        result[collection_key] = original[:best]
        result["count"] = best
        if collection_key == "hits":
            result["match_count"] = best
            result["match_count_complete"] = False
    else:
        if len(str(result.get("error", ""))) > 256:
            result["error"] = str(result["error"])[:256]
        if len(str(result.get("notice", ""))) > 160:
            result["notice"] = str(result["notice"])[:160]
    result["response_bytes"] = payload_size()
    return result


def search_repo_fast(
    repo_root: Path,
    query: str,
    *,
    scope: str = "tracked",
    match_mode: str = "literal",
    case_sensitive: bool = False,
    directory: str = "",
    file_patterns: list[str] | None = None,
    max_results: int = 100,
    context_lines: int = 0,
    result_mode: str = "matches",
    budget_ms: int = 5_000,
    response_budget_bytes: int = DEFAULT_FAST_SEARCH_RESPONSE_BYTES,
) -> dict:
    """Fast navigation-only lexical search over Git-tracked repository files."""
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if scope != "tracked":
        raise ValueError("search_repo_fast currently supports scope=tracked only")
    if match_mode not in {"literal", "regex"}:
        raise ValueError("match_mode must be literal or regex")
    if result_mode not in {"matches", "files", "count"}:
        raise ValueError("result_mode must be matches, files, or count")
    max_results = max(1, min(int(max_results), 500))
    context_lines = max(0, min(int(context_lines), 5))
    budget_ms = max(100, min(int(budget_ms), 30_000))
    response_budget_bytes = max(
        4_096, min(int(response_budget_bytes), MAX_FAST_SEARCH_RESPONSE_BYTES)
    )
    patterns = _fast_search_patterns(file_patterns)
    if directory:
        base = _resolve_and_validate(repo_root, directory)
        if not base.is_dir():
            raise ValueError(f"Not a directory: {directory}")
        directory = Path(directory).as_posix().rstrip("/")

    started = time.monotonic()
    deadline = started + budget_ms / 1000
    base_result = {
        "ok": True,
        "status": "available",
        "fresh": True,
        "partial": False,
        "timeout": False,
        "repo_name": "",
        "query": query,
        "scope": "tracked",
        "match_mode": match_mode,
        "case_sensitive": case_sensitive,
        "directory": directory,
        "file_patterns": patterns,
        "result_mode": result_mode,
        "engine": "git-grep",
        "navigation_only": True,
        "notice": _FAST_SEARCH_NOTICE,
        "git_head": "",
        "match_count": 0,
        "match_count_complete": True,
        "files_matched": 0,
        "hits": [],
        "files": [],
        "count": 0,
        "duration_ms": 0.0,
        "truncated": False,
        "truncation_reason": "",
        "max_results": max_results,
        "has_more": False,
        "error": "",
        "response_budget_bytes": response_budget_bytes,
    }

    try:
        head = _fast_search_read_head(repo_root)
        identity_error = ""
        if not head:
            head, identity_error = _fast_search_fallback_identity(repo_root, deadline)
        if not head:
            base_result.update(
                ok=False,
                status="not_git_repository",
                fresh=False,
                error=identity_error
                or "Repository has no exact readable Git worktree identity",
            )
            base_result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
            return _fast_search_finalize(base_result, response_budget_bytes)
        base_result["git_head"] = head
        scope_args = _fast_search_scope_args(directory)

        if result_mode in {"files", "count"}:
            command = _fast_search_common_args(
                query,
                match_mode=match_mode,
                case_sensitive=case_sensitive,
                operation_args=["-c"],
            ) + scope_args
            completed = _run_fast_git(repo_root, command, deadline)
            if completed.returncode not in {0, 1}:
                base_result.update(
                    ok=False,
                    status="search_failed",
                    fresh=False,
                    error=completed.stderr.decode("utf-8", errors="replace").strip()[:1000],
                )
            else:
                counts = {
                    path: count
                    for path, count in _fast_search_parse_counts(completed.stdout).items()
                    if _fast_search_path_allowed(repo_root, path, patterns)
                }
                ordered_files = sorted(counts)
                base_result["match_count"] = sum(counts.values())
                base_result["files_matched"] = len(ordered_files)
                if result_mode == "files":
                    base_result["files"] = ordered_files[:max_results]
                    base_result["count"] = len(base_result["files"])
                    if len(ordered_files) > max_results:
                        base_result["truncated"] = True
                        base_result["has_more"] = True
                        base_result["truncation_reason"] = "max_results"
                else:
                    base_result["count"] = int(base_result["match_count"])
        else:
            match_command = _fast_search_common_args(
                query,
                match_mode=match_mode,
                case_sensitive=case_sensitive,
                operation_args=["-n", "--column", f"-m{max_results + 1}"],
            ) + scope_args
            matched = _run_fast_git(repo_root, match_command, deadline)
            if matched.returncode not in {0, 1}:
                base_result.update(
                    ok=False,
                    status="search_failed",
                    fresh=False,
                    error=matched.stderr.decode("utf-8", errors="replace").strip()[:1000],
                )
            else:
                parsed_hits = _fast_search_parse_matches(matched.stdout)
                allowed_paths: dict[str, bool] = {}
                all_hits: list[dict[str, object]] = []
                for hit in parsed_hits:
                    path = str(hit["path"])
                    allowed = allowed_paths.get(path)
                    if allowed is None:
                        allowed = _fast_search_path_allowed(repo_root, path, patterns)
                        allowed_paths[path] = allowed
                    if allowed:
                        all_hits.append(hit)
                all_hits.sort(
                    key=lambda hit: (
                        str(hit["path"]),
                        int(hit["line"]),
                        int(hit["column"]),
                    )
                )
                base_result["files_matched"] = len(
                    {str(hit["path"]) for hit in all_hits}
                )
                truncated = len(all_hits) > max_results
                hits = all_hits[:max_results]
                _fast_search_add_context(repo_root, hits, context_lines)
                base_result["hits"] = hits
                base_result["count"] = len(hits)
                base_result["match_count"] = len(hits)
                base_result["match_count_complete"] = not truncated
                if truncated:
                    base_result["truncated"] = True
                    base_result["has_more"] = True
                    base_result["truncation_reason"] = "max_results"
    except subprocess.TimeoutExpired:
        base_result["ok"] = False
        base_result["status"] = "search_timeout"
        base_result["fresh"] = False
        base_result["partial"] = bool(base_result.get("hits") or base_result.get("files"))
        base_result["timeout"] = True
        base_result["truncated"] = True
        base_result["has_more"] = True
        base_result["truncation_reason"] = "timeout"
        base_result["error"] = "Fast repository search exceeded its end-to-end budget"
    except OSError as exc:
        base_result["ok"] = False
        base_result["status"] = "git_unavailable"
        base_result["fresh"] = False
        base_result["error"] = str(exc)[:1000]

    base_result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    return _fast_search_finalize(base_result, response_budget_bytes)


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
    *,
    file_path: str = "",
    cursor: str = "",
    response_budget_bytes: int | None = None,
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

    if file_path or cursor or response_budget_bytes is not None:
        return _search_repo_text_bounded(
            repo_root,
            query,
            directory=directory,
            file_path=file_path,
            max_results=max_results,
            case_sensitive=case_sensitive,
            file_patterns=patterns,
            budget_ms=budget_ms,
            cursor=cursor,
            response_budget_bytes=response_budget_bytes
            if response_budget_bytes is not None
            else DEFAULT_SEARCH_RESPONSE_BYTES,
        )

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


def _search_repo_text_bounded(
    repo_root: Path,
    query: str,
    *,
    directory: str,
    file_path: str,
    max_results: int,
    case_sensitive: bool,
    file_patterns: list[str],
    budget_ms: int,
    cursor: str,
    response_budget_bytes: int,
) -> dict:
    if file_path and (directory or file_patterns):
        raise ValueError("file_path cannot be combined with directory or file_patterns")
    response_budget_bytes = max(
        1_024, min(int(response_budget_bytes), MAX_SEARCH_RESPONSE_BYTES)
    )
    started = time.monotonic()
    if file_path:
        target = _resolve_and_validate(repo_root, file_path)
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"Not a regular file: {file_path}")
        candidates = [target]
    else:
        base_abs = _resolve_and_validate(repo_root, directory) if directory else repo_root
        if not base_abs.is_dir():
            raise ValueError(f"Not a directory: {directory}")
        candidates = []
        for dirpath, dirnames, filenames in os.walk(base_abs):
            current = Path(dirpath)
            dirnames[:] = [
                name
                for name in dirnames
                if _path_is_allowed(repo_root, current / name)
                and not (current / name).is_symlink()
            ]
            for filename in sorted(filenames):
                child = current / filename
                if not _path_is_allowed(repo_root, child) or child.is_symlink():
                    continue
                if file_patterns and not any(Path(filename).match(p) for p in file_patterns):
                    continue
                candidates.append(child)
        candidates.sort(key=lambda item: _posix_relative(repo_root, item))

    file_entries: list[dict[str, str]] = []
    searchable: list[Path] = []
    for candidate in candidates:
        if _is_binary(candidate):
            continue
        try:
            stat = candidate.stat()
            if stat.st_size > MAX_FILE_BYTES:
                continue
            digest = _sha256_file(candidate)
        except OSError:
            continue
        relative = _posix_relative(repo_root, candidate)
        file_entries.append({"path": relative, "sha256": digest})
        searchable.append(candidate)
    snapshot_sha256 = hashlib.sha256(
        json.dumps(file_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cursor_state: dict | None = None
    if cursor:
        try:
            cursor_state = _decode_search_cursor(cursor)
        except ValueError as exc:
            return _search_error_response(
                query, directory, file_path, case_sensitive, max_results, budget_ms,
                "invalid_cursor", str(exc), started,
            )
        expected = {
            "query": query,
            "directory": directory,
            "file_path": file_path,
            "case_sensitive": case_sensitive,
            "file_patterns": file_patterns,
            "max_results": max_results,
            "snapshot_sha256": snapshot_sha256,
        }
        if any(cursor_state.get(key) != value for key, value in expected.items()):
            return _search_error_response(
                query, directory, file_path, case_sensitive, max_results, budget_ms,
                "stale_content", "Search snapshot changed; restart the search", started,
            )
        file_index = max(0, int(cursor_state.get("file_index", 0)))
        start_line = max(1, int(cursor_state.get("line", 1)))
    else:
        file_index = 0
        start_line = 1

    deadline = started + budget_ms / 1000
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(query), flags)
    hits: list[dict[str, object]] = []
    next_file_index, next_line = file_index, start_line
    timed_out = False
    truncation_reason = ""
    for index in range(file_index, len(searchable)):
        path = searchable[index]
        line_start = start_line if index == file_index else 1
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, 1):
                    if line_number < line_start:
                        continue
                    if time.monotonic() >= deadline:
                        timed_out = True
                        next_file_index, next_line = index, line_number
                        break
                    if pattern.search(line):
                        hit = {
                            "path": _posix_relative(repo_root, path),
                            "line": line_number,
                            "snippet": _redact_text(line.rstrip("\r\n")[:_SEARCH_SNIPPET_CHARS]),
                        }
                        candidate = _search_result_payload(
                            query, directory, file_path, case_sensitive, max_results,
                            response_budget_bytes, hits + [hit], snapshot_sha256,
                        )
                        if len(json.dumps(candidate, separators=(",", ":")).encode("utf-8")) > response_budget_bytes:
                            truncation_reason = "response_budget"
                            next_file_index, next_line = index, line_number
                            break
                        hits.append(hit)
                        next_file_index, next_line = index, line_number + 1
                        if len(hits) >= max_results:
                            truncation_reason = "max_results"
                            break
                if timed_out or truncation_reason:
                    break
        except OSError:
            next_file_index, next_line = index + 1, 1
            continue
        if timed_out or truncation_reason:
            break
        next_file_index, next_line = index + 1, 1

    has_more = next_file_index < len(searchable)
    next_cursor = (
        _encode_search_cursor(
            query=query, directory=directory, file_path=file_path,
            case_sensitive=case_sensitive, file_patterns=file_patterns,
            max_results=max_results, snapshot_sha256=snapshot_sha256,
            file_index=next_file_index, line=next_line,
        )
        if has_more else ""
    )
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    partial = timed_out
    result = {
        "ok": not timed_out,
        "status": "search_timeout" if timed_out else "available",
        "fresh": not timed_out,
        "partial": partial,
        "timeout": timed_out,
        "repo_name": "",
        "query": query,
        "directory": directory,
        "file_path": file_path,
        "case_sensitive": case_sensitive,
        "file_patterns": file_patterns,
        "response_budget_bytes": response_budget_bytes,
        "snapshot_sha256": snapshot_sha256,
        "hits": hits,
        "partial_results": hits if partial else [],
        "count": len(hits),
        "files_examined": len(searchable),
        "duration_ms": duration_ms,
        "truncated": bool(has_more or truncation_reason),
        "truncation_reason": truncation_reason,
        "max_results": max_results,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "recommended_action": "Continue with next_cursor" if has_more else "",
        "error": "Search timed out; results are partial" if timed_out else "",
    }
    while len(json.dumps(result, separators=(",", ":")).encode("utf-8")) > response_budget_bytes and result["hits"]:
        result["hits"].pop()
        if timed_out:
            result["partial_results"] = result["hits"]
        result["count"] = len(result["hits"])
    result["response_bytes"] = len(json.dumps(result, separators=(",", ":")).encode("utf-8"))
    return result


def _search_result_payload(*args: object) -> dict:
    query, directory, file_path, case_sensitive, max_results, response_budget, hits, snapshot = args
    return {
        "ok": True, "status": "available", "fresh": True,
        "query": query, "directory": directory, "file_path": file_path,
        "case_sensitive": case_sensitive, "response_budget_bytes": response_budget,
        "snapshot_sha256": snapshot, "hits": hits, "count": len(hits),
        "max_results": max_results,
    }


def _search_error_response(
    query: str, directory: str, file_path: str, case_sensitive: bool,
    max_results: int, budget_ms: int, status: str, error: str, started: float,
) -> dict:
    return {
        "ok": False, "status": status, "fresh": False, "partial": False,
        "timeout": False, "repo_name": "", "query": query, "directory": directory,
        "file_path": file_path, "case_sensitive": case_sensitive, "hits": [],
        "partial_results": [], "count": 0, "files_examined": 0,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "truncated": False, "max_results": max_results, "budget_ms": budget_ms,
        "has_more": False, "next_cursor": "", "error": error,
    }


def _encode_search_cursor(**payload: object) -> str:
    encoded = json.dumps(
        {"version": _SEARCH_CURSOR_VERSION, **payload}, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    return f"{body}.{hashlib.sha256(encoded).hexdigest()}"


def _decode_search_cursor(cursor: str) -> dict:
    try:
        body, checksum = cursor.split(".", 1)
        encoded = urlsafe_b64decode(body + ("=" * (-len(body) % 4)))
        if hashlib.sha256(encoded).hexdigest() != checksum:
            raise ValueError("Search continuation checksum mismatch")
        payload = json.loads(encoded.decode("utf-8"))
    except (BinasciiError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid search continuation") from exc
    if payload.get("version") != _SEARCH_CURSOR_VERSION:
        raise ValueError("Unsupported search continuation version")
    return payload


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


def read_repo_files(
    repo_root: Path,
    requests: list[dict],
    response_budget_bytes: int = DEFAULT_READ_RESPONSE_BYTES,
) -> dict:
    """
    Read multiple files in a single call.

    Each request: {"path": str, "start_line": int, "end_line": int}
    At most MAX_BATCH_REQUESTS requests.
    The complete public response is capped by response_budget_bytes.
    Reuses read_repo_file security, size, and redaction logic.
    """
    if not isinstance(requests, list):
        raise ValueError("requests must be a list")
    if len(requests) > MAX_BATCH_REQUESTS:
        raise ValueError(
            f"Too many requests: {len(requests)} (max {MAX_BATCH_REQUESTS})"
        )

    budget = max(
        DEFAULT_READ_RESPONSE_BYTES,
        min(int(response_budget_bytes), MAX_READ_RESPONSE_BYTES),
    )
    results: list[dict] = []
    truncated_batch = False

    for req in requests:
        path = req.get("path", "")
        start_line = int(req.get("start_line", 1) or 1)
        end_line = int(req.get("end_line", 0) or 0)
        current_size = len(json.dumps({"results": results}).encode("utf-8"))
        content_budget = max(1, budget - current_size - _READ_RESPONSE_METADATA_RESERVE)
        try:
            item = read_repo_file(
                repo_root,
                path,
                start_line=start_line,
                end_line=end_line,
                start_byte=req.get("start_byte"),
                continuation=str(req.get("continuation") or ""),
                content_budget_bytes=content_budget,
            )
            results.append(item)
            truncated_batch = truncated_batch or bool(item.get("has_more"))
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
                    "status": "read_failed",
                    "error": str(exc),
                }
            )

    response = {
        "ok": True,
        "repo_name": "",
        "results": results,
        "count": len(results),
        "truncated_batch": truncated_batch,
        "has_more": truncated_batch,
        "response_budget_bytes": budget,
        "error": "",
    }
    while len(json.dumps(response).encode("utf-8")) > budget and results:
        item = results[-1]
        content = str(item.get("content") or "")
        if content:
            item["content"] = content[: max(0, len(content) - 1024)]
            item["truncated"] = True
            item["has_more"] = True
            response["truncated_batch"] = True
            response["has_more"] = True
        else:
            results.pop()
            response["count"] = len(results)
            response["truncated_batch"] = True
            response["has_more"] = True
    response["payload_bytes"] = len(json.dumps(response).encode("utf-8"))
    response["response_bytes"] = response["payload_bytes"]
    return response


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
