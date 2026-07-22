"""
repo_writer.py — safe, controlled write operations for CodexBridge.

Rules:
- All paths are resolved through resolve_and_validate_write (extending repo_reader checks).
- No Codex CLI, Gemini, Ollama, or any agent component is invoked.
- Patches are previewed before apply; apply requires a valid patch_id.
- All writes are preceded by stale-hash checks against the current file.
- Original content is saved for rollback before any file is touched.
- No git reset, git checkout, or destructive shell commands are used.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .repo_reader import (
    _is_binary,
    _resolve_and_validate,
)
from .payload_chunks import assemble_payload, build_payload_parts
from .return_loop.atomic_writer import _atomic_write_bytes as _shared_atomic_write_bytes
from .transactions import (
    TransactionContext,
    build_transaction_result,
    rollback_transaction,
)
from .git_tools import _validate_commit_metadata


# ---------------------------------------------------------------------------
# Write-specific limits
# ---------------------------------------------------------------------------
MAX_PATCH_FILES = 50
MAX_PATCH_LINES = 10_000
MAX_PATCH_BYTES = 2 * 1024 * 1024  # 2 MB total content change
MAX_NEWLINE_DIAGNOSTIC_BYTES = 8 * 1024
MAX_NEWLINE_DIAGNOSTIC_LOCATIONS = 20
MAX_CREATE_BYTES = 200 * 1024  # 200 KB for create_repo_file
MANAGED_PATCHES_DIR = "managed_patches"

# ---------------------------------------------------------------------------
# Additional write-blocked extensions / names (on top of reader exclusions)
# ---------------------------------------------------------------------------
_WRITE_BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    [".bak", ".tmp", ".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx"]
)
_WRITE_BLOCKED_NAMES_EXTRA: frozenset[str] = frozenset(["desktop.ini"])

# Branch names that must never be created
_PROTECTED_BRANCHES: frozenset[str] = frozenset(
    ["master", "main", "production", "release", "deployment"]
)
# Branch names may not *start with* these prefixes either
_PROTECTED_BRANCH_PREFIXES: tuple[str, ...] = ("release/", "deployment/")

# Branch name must be a safe identifier
_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_patch_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}_patch_{uuid4().hex[:8]}"


_PATCH_ID_RE = re.compile(r"^\d{8}T\d{6}Z_patch_[0-9a-f]{8}$")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repo_fingerprint(repo_root: Path) -> str:
    resolved = repo_root.resolve()
    normalized = os.path.normcase(os.path.normpath(str(resolved)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _resolve_managed_patch_dir(runs_dir: Path, patch_id: str) -> Path:
    if not _PATCH_ID_RE.fullmatch(patch_id):
        raise ValueError(f"Invalid patch_id: {patch_id!r}")
    base_dir = (runs_dir / MANAGED_PATCHES_DIR).resolve()
    patch_dir = (base_dir / patch_id).resolve()
    patch_dir.relative_to(base_dir)
    return patch_dir


def _atomic_write_bytes(path: Path, data: bytes, suffix: str) -> None:
    del suffix
    _shared_atomic_write_bytes(path, data)


def _atomic_write_text(path: Path, text: str, suffix: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"), suffix)


def _resolve_and_validate_write(repo_root: Path, relative_path: str) -> Path:
    """
    Full validation for write operations.  Extends _resolve_and_validate with
    additional write-blocked extensions and names.
    """
    absolute = _resolve_and_validate(repo_root, relative_path)
    name_lower = Path(relative_path).name.lower()
    suffix_lower = Path(relative_path).suffix.lower()

    if suffix_lower in _WRITE_BLOCKED_EXTENSIONS:
        raise ValueError(f"Writing to this file type is not allowed: {relative_path}")
    if name_lower in _WRITE_BLOCKED_NAMES_EXTRA:
        raise ValueError(f"Writing to this file is not allowed: {relative_path}")

    return absolute


def _count_changed_lines(unified_diff: str) -> int:
    """Count lines added or removed in a unified diff."""
    count = 0
    for line in unified_diff.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            count += 1
    return count


def _unified_diff_for_op(old_text: str, new_text: str, path: str) -> str:
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="\n",
    )
    return "".join(diff_lines)


def _change_line_counts(old_text: str, new_text: str, path: str) -> tuple[int, int, int]:
    raw_diff = _unified_diff_for_op(old_text, new_text, path)
    logical_diff = _unified_diff_for_op(
        _normalize_newlines(old_text),
        _normalize_newlines(new_text),
        path,
    )
    changed_lines = _count_changed_lines(raw_diff)
    logical_changed_lines = _count_changed_lines(logical_diff)
    newline_only_changed_lines = max(0, changed_lines - logical_changed_lines)
    return changed_lines, logical_changed_lines, newline_only_changed_lines


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _dominant_newline(text: str) -> str:
    crlf = text.count("\r\n")
    lf = _normalize_newlines(text).count("\n")
    return "\r\n" if crlf and crlf >= max(1, lf - crlf) else "\n"


def _restore_newlines(text: str, newline: str) -> str:
    normalized = _normalize_newlines(text)
    return normalized if newline == "\n" else normalized.replace("\n", newline)


def _newline_diagnostic(old_text: str, new_text: str) -> dict[str, Any]:
    """Return a small, exact diagnostic for newline-form changes."""
    def counts(text: str) -> dict[str, int]:
        crlf = text.count("\r\n")
        bare_cr = text.replace("\r\n", "").count("\r")
        lf = text.replace("\r\n", "").count("\n")
        return {"lf": lf, "crlf": crlf, "cr": bare_cr}

    def endings(text: str) -> list[str]:
        return [
            "crlf" if line.endswith("\r\n") else "cr" if line.endswith("\r") else "lf"
            for line in text.splitlines(keepends=True)
            if line.endswith(("\r\n", "\r", "\n"))
        ]

    old_endings = endings(old_text)
    new_endings = endings(new_text)
    affected = [
        index + 1
        for index in range(max(len(old_endings), len(new_endings)))
        if (old_endings[index] if index < len(old_endings) else "")
        != (new_endings[index] if index < len(new_endings) else "")
    ]
    locations = affected[:MAX_NEWLINE_DIAGNOSTIC_LOCATIONS]
    return {
        "old_counts": counts(old_text),
        "new_counts": counts(new_text),
        "mixed_old": sum(value > 0 for value in counts(old_text).values()) > 1,
        "mixed_new": sum(value > 0 for value in counts(new_text).values()) > 1,
        "affected_lines": locations,
        "affected_lines_total": len(affected),
        "affected_lines_truncated": len(affected) > len(locations),
    }


def _bounded_newline_diagnostics(items: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"items": items, "truncated": False}
    while len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) > MAX_NEWLINE_DIAGNOSTIC_BYTES and payload["items"]:
        payload["items"].pop()
        payload["truncated"] = True
    payload["response_bytes"] = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return payload


def _git_head(repo_root: Path) -> str:
    """Return current HEAD commit hash, or empty string if not available."""
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _validate_create_target(
    repo_root: Path, path: str, content: str
) -> tuple[Path, int]:
    absolute = _resolve_and_validate_write(repo_root, path)
    if absolute.exists():
        raise ValueError(f"File already exists: {path}")

    parent = absolute.parent
    try:
        parent.relative_to(repo_root)
    except ValueError:
        raise ValueError(f"Parent directory is outside the repository: {path}")

    size_bytes = len(content.encode("utf-8"))
    if size_bytes > MAX_CREATE_BYTES:
        raise ValueError(
            f"Content exceeds {MAX_CREATE_BYTES // 1024} KB limit for create_repo_file"
        )

    return absolute, size_bytes


def _validate_remove_target(
    repo_root: Path, path: str, expected_sha256: str
) -> tuple[Path, bytes, str]:
    absolute = _resolve_and_validate_write(repo_root, path)
    if not absolute.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if absolute.is_dir():
        raise ValueError(f"Directory deletion is not allowed: {path}")
    if absolute.is_symlink():
        raise ValueError(f"Symlinks are not allowed: {path}")

    current_bytes = absolute.read_bytes()
    current_sha = hashlib.sha256(current_bytes).hexdigest()
    if current_sha != expected_sha256:
        raise ValueError(
            f"Stale hash for '{path}': "
            f"expected {expected_sha256[:12]}… got {current_sha[:12]}…"
        )
    return absolute, current_bytes, current_sha


def _payload_file_name(index: int) -> str:
    return f"payload_{index}.bin"


def _rollback_file_name(index: int) -> str:
    return f"rollback_{index}.bin"


def _legacy_rollback_file_name(path: str) -> str:
    return path.replace("/", "__").replace("\\", "__")


def _resolve_bundle_file(
    base_dir: Path,
    filename: str,
    expected_name: str,
    *,
    kind: str,
) -> Path:
    if filename != expected_name:
        raise ValueError(
            f"{kind.capitalize()} filename mismatch: expected '{expected_name}'"
        )

    candidate = base_dir / filename
    if not candidate.exists():
        if kind == "payload":
            raise ValueError(f"Patch bundle is missing the opaque payload: {filename}")
        raise ValueError(f"Missing {kind} file: {filename}")
    if candidate.is_symlink():
        raise ValueError(f"{kind.capitalize()} file must not be a symlink: {filename}")
    if not candidate.is_file():
        raise ValueError(f"{kind.capitalize()} file is not a regular file: {filename}")

    resolved_base = base_dir.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Invalid {kind} path: {filename!r}") from exc

    return resolved_candidate


def _preview_payload_sha(op: dict[str, Any]) -> str:
    payload_sha = op.get("payload_sha256", "")
    if isinstance(payload_sha, str) and payload_sha:
        return payload_sha
    legacy_sha = op.get("new_content_sha256", "")
    if isinstance(legacy_sha, str):
        return legacy_sha
    return ""


def get_patch_status(repo_root: Path, patch_id: str, runs_dir: Path) -> dict[str, Any]:
    """Return repository-bound patch lifecycle state without modifying files."""
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    if not patch_dir.exists():
        raise ValueError(f"Unknown patch_id: {patch_id}")
    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_fingerprint = manifest.get("repo_fingerprint", "")
    if expected_fingerprint and expected_fingerprint != _repo_fingerprint(repo_root):
        raise ValueError(
            f"Patch {patch_id} does not belong to the requested repository"
        )
    return {
        "ok": True,
        "patch_id": patch_id,
        "status": str(manifest.get("status", "unknown")),
        "created_at": str(manifest.get("created_at", "")),
        "applied_at": str(manifest.get("applied_at", "")),
        "reverted_at": str(manifest.get("reverted_at", "")),
        "changed_files": [
            str(item.get("path", ""))
            for item in manifest.get("operations", [])
            if item.get("path")
        ],
        "apply_result": dict(manifest.get("apply_result") or {}),
        "errors": list(manifest.get("errors") or []),
        "error": "",
    }


def _idempotent_apply_result(manifest: dict[str, Any], patch_id: str) -> dict[str, Any]:
    result = dict(manifest.get("apply_result") or {})
    if not result:
        result = {
            "ok": True,
            "patch_id": patch_id,
            "changed_files": [
                str(item.get("path", ""))
                for item in manifest.get("applied_results", [])
                if item.get("path")
            ],
            "results": [
                {
                    "path": str(item.get("path", "")),
                    "sha256": str(item.get("sha256", "")),
                }
                for item in manifest.get("applied_results", [])
                if item.get("path")
            ],
            "git_head": str(manifest.get("applied_git_head", "")),
            "error": "",
        }
    result["idempotent_replay"] = True
    return result


def _remove_change_stats(
    path: str, absolute: Path, current_bytes: bytes
) -> tuple[int, int]:
    if _is_binary(absolute):
        diff_text = (
            f"--- a/{path}\n+++ b/{path}\n@@ -1 +0,0 @@\n-[binary content omitted]\n"
        )
    else:
        current_text = current_bytes.decode("utf-8", errors="replace")
        diff_text = _unified_diff_for_op(current_text, "", path)
    return _count_changed_lines(diff_text), len(current_bytes)


def _rollback_applied_preview_ops(
    repo_root: Path,
    rollback_dir: Path,
    applied_results: list[dict[str, Any]],
) -> None:
    for index in range(len(applied_results) - 1, -1, -1):
        applied = applied_results[index]
        absolute = _resolve_and_validate_write(repo_root, applied["path"])
        if applied["action"] == "create":
            if absolute.exists():
                absolute.unlink()
            continue

        rollback_file = applied.get("rollback_file", "")
        rollback_path = _resolve_bundle_file(
            rollback_dir,
            rollback_file,
            _rollback_file_name(index),
            kind="rollback",
        )
        rollback_bytes = rollback_path.read_bytes()
        _atomic_write_bytes(
            absolute,
            rollback_bytes,
            ".codexbridge_apply_rollback_tmp",
        )


def _write_preview_bundle(
    repo_root: Path,
    runs_dir: Path,
    patch_id: str,
    operations: list[dict[str, Any]],
    diff_text: str,
    *,
    git_head: str,
    errors: list[str],
    warnings: list[str] | None = None,
    commit_title: str = "",
    commit_description: str = "",
) -> Path:
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    patch_dir.mkdir(parents=True, exist_ok=True)
    for index, op in enumerate(operations):
        payload_text = op.get("payload_text")
        if payload_text is None:
            continue
        _, payload_parts = build_payload_parts(index, payload_text.encode("utf-8"))
        for filename, payload_bytes in payload_parts:
            _atomic_write_bytes(
                patch_dir / filename,
                payload_bytes,
                ".codexbridge_payload_tmp",
            )

    manifest = {
        "patch_id": patch_id,
        "bundle_version": 3,
        "created_at": _utc_now(),
        "repo_root": "",
        "repo_fingerprint": _repo_fingerprint(repo_root),
        "git_head_at_preview": git_head,
        "status": "preview_failed" if errors else "preview_ok",
        "operations": [],
        "errors": errors,
        "warnings": list(warnings or []),
        "commit_title": commit_title,
        "commit_description": commit_description,
    }
    for index, op in enumerate(operations):
        entry = {
            "index": index,
            "action": op["action"],
            "path": op["path"],
            "current_sha256": op.get("current_sha256", ""),
            "payload_file": "",
            "payload_chunks": [],
            "payload_sha256": "",
            "payload_size_bytes": 0,
            "changed_lines": op["changed_lines"],
            "logical_changed_lines": op.get(
                "logical_changed_lines", op["changed_lines"]
            ),
            "newline_only_changed_lines": op.get("newline_only_changed_lines", 0),
            "newline_diagnostic": op.get("newline_diagnostic", {}),
            "warnings": list(op.get("warnings") or []),
            "changed_bytes": op["changed_bytes"],
        }
        payload_text = op.get("payload_text")
        if payload_text is not None:
            descriptor, _ = build_payload_parts(index, payload_text.encode("utf-8"))
            entry.update(descriptor)
        manifest["operations"].append(entry)

    _atomic_write_text(
        patch_dir / "manifest.json",
        json.dumps(manifest, indent=2),
        ".codexbridge_manifest_tmp",
    )
    if diff_text:
        _atomic_write_text(
            patch_dir / "preview.diff",
            diff_text,
            ".codexbridge_diff_tmp",
        )
    return patch_dir


def _apply_exact_text_operation(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    old_text = op.get("old_text")
    new_text = op.get("new_text")
    if old_text is None or not isinstance(old_text, str):
        raise ValueError(f"op[{idx}]: old_text is required and must be a string")
    if new_text is None or not isinstance(new_text, str):
        raise ValueError(f"op[{idx}]: new_text is required and must be a string")
    normalized_old = _normalize_newlines(old_text)
    normalized_new = _normalize_newlines(new_text)
    occurrences = content.count(normalized_old)
    if occurrences == 0:
        raise ValueError(f"op[{idx}]: old_text not found in '{path_str}'")
    if occurrences > 1:
        raise ValueError(
            f"op[{idx}]: old_text appears {occurrences} times in '{path_str}'; must be unique"
        )
    return content.replace(normalized_old, normalized_new, 1)


def _apply_exact_text_preserving_newlines(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    old_text = op.get("old_text")
    new_text = op.get("new_text")
    if old_text is None or not isinstance(old_text, str):
        raise ValueError(f"op[{idx}]: old_text is required and must be a string")
    if new_text is None or not isinstance(new_text, str):
        raise ValueError(f"op[{idx}]: new_text is required and must be a string")

    normalized_old = _normalize_newlines(old_text)
    normalized_new = _normalize_newlines(new_text)
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for newline in ("\n", "\r\n"):
        candidate = normalized_old.replace("\n", newline)
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append((candidate, newline))

    matches: list[tuple[str, str, int]] = []
    for candidate, newline in candidates:
        occurrences = content.count(candidate)
        if occurrences:
            matches.append((candidate, newline, occurrences))
    total_occurrences = sum(item[2] for item in matches)
    if total_occurrences == 0:
        raise ValueError(f"op[{idx}]: old_text not found in '{path_str}'")
    if total_occurrences > 1:
        raise ValueError(
            f"op[{idx}]: old_text appears {total_occurrences} times in "
            f"'{path_str}'; must be unique"
        )

    candidate, newline, _ = matches[0]
    replacement = normalized_new.replace("\n", newline)
    return content.replace(candidate, replacement, 1)


def _apply_line_range_operation(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    start_line = int(op.get("start_line", 0))
    end_line = int(op.get("end_line", 0))
    new_text = op.get("new_text")
    if start_line < 1 or end_line < start_line:
        raise ValueError(f"op[{idx}]: invalid line range for '{path_str}'")
    if not isinstance(new_text, str):
        raise ValueError(f"op[{idx}]: new_text is required and must be a string")
    lines = content.splitlines(keepends=True)
    replacement = _normalize_newlines(new_text)
    replacement_lines = replacement.splitlines(keepends=True)
    if replacement and not replacement.endswith("\n"):
        replacement_lines[-1] = replacement_lines[-1]
    return "".join(lines[: start_line - 1] + replacement_lines + lines[end_line:])


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _line_range_replacement_newline(
    content: str,
    lines: list[str],
    start_index: int,
    end_index: int,
) -> str:
    for line in lines[start_index:end_index]:
        newline = _line_ending(line)
        if newline:
            return newline
    for line in reversed(lines[:start_index]):
        newline = _line_ending(line)
        if newline:
            return newline
    for line in lines[end_index:]:
        newline = _line_ending(line)
        if newline:
            return newline
    return _dominant_newline(content)


def _apply_line_range_preserving_newlines(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    start_line = int(op.get("start_line", 0))
    end_line = int(op.get("end_line", 0))
    new_text = op.get("new_text")
    if start_line < 1 or end_line < start_line:
        raise ValueError(f"op[{idx}]: invalid line range for '{path_str}'")
    if not isinstance(new_text, str):
        raise ValueError(f"op[{idx}]: new_text is required and must be a string")

    lines = content.splitlines(keepends=True)
    start_index = start_line - 1
    end_index = end_line
    newline = _line_range_replacement_newline(
        content,
        lines,
        start_index,
        end_index,
    )
    replacement = _restore_newlines(new_text, newline)
    return "".join(lines[:start_index] + [replacement] + lines[end_index:])


def _parse_unified_hunks(diff_text: str) -> list[tuple[int, list[str]]]:
    hunks: list[tuple[int, list[str]]] = []
    current_start = 0
    current_lines: list[str] = []
    header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if current_lines:
                hunks.append((current_start, current_lines))
            match = header_re.match(line)
            if not match:
                raise ValueError("Invalid unified diff hunk header")
            current_start = int(match.group(1))
            current_lines = []
            continue
        if line.startswith(("---", "+++")):
            continue
        current_lines.append(line)
    if current_lines:
        hunks.append((current_start, current_lines))
    return hunks


def _apply_unified_diff_operation(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    diff_text = op.get("diff") or op.get("unified_diff")
    if not isinstance(diff_text, str) or not diff_text.strip():
        raise ValueError(f"op[{idx}]: unified diff text is required for '{path_str}'")
    lines = content.splitlines(keepends=False)
    offset = 0
    for start_line, hunk_lines in _parse_unified_hunks(_normalize_newlines(diff_text)):
        pointer = max(0, start_line - 1 + offset)
        rebuilt: list[str] = []
        for line in hunk_lines:
            if not line:
                marker = " "
                text = ""
            else:
                marker = line[0]
                text = line[1:]
            if marker == " ":
                if pointer >= len(lines) or lines[pointer] != text:
                    raise ValueError(
                        f"op[{idx}]: unified diff context mismatch in '{path_str}'"
                    )
                rebuilt.append(lines[pointer])
                pointer += 1
            elif marker == "-":
                if pointer >= len(lines) or lines[pointer] != text:
                    raise ValueError(
                        f"op[{idx}]: unified diff removal mismatch in '{path_str}'"
                    )
                pointer += 1
            elif marker == "+":
                rebuilt.append(text)
            else:
                raise ValueError(f"op[{idx}]: unsupported diff line in '{path_str}'")
        hunk_start = max(0, start_line - 1 + offset)
        consumed = pointer - hunk_start
        lines[hunk_start:pointer] = rebuilt
        offset += len(rebuilt) - consumed
    return "\n".join(lines) + ("\n" if content.endswith("\n") or lines else "")


def _apply_unified_diff_preserving_newlines(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    diff_text = op.get("diff") or op.get("unified_diff")
    if not isinstance(diff_text, str) or not diff_text.strip():
        raise ValueError(f"op[{idx}]: unified diff text is required for '{path_str}'")

    lines = content.splitlines(keepends=True)
    offset = 0
    for start_line, hunk_lines in _parse_unified_hunks(_normalize_newlines(diff_text)):
        hunk_start = max(0, start_line - 1 + offset)
        pointer = hunk_start
        newline = _line_range_replacement_newline(
            content,
            lines,
            hunk_start,
            min(len(lines), hunk_start + max(1, len(hunk_lines))),
        )
        rebuilt: list[str] = []
        for line in hunk_lines:
            if not line:
                marker = " "
                text = ""
            else:
                marker = line[0]
                text = line[1:]
            if marker == " ":
                if pointer >= len(lines) or lines[pointer].removesuffix(
                    _line_ending(lines[pointer])
                ) != text:
                    raise ValueError(
                        f"op[{idx}]: unified diff context mismatch in '{path_str}'"
                    )
                rebuilt.append(lines[pointer])
                pointer += 1
            elif marker == "-":
                if pointer >= len(lines) or lines[pointer].removesuffix(
                    _line_ending(lines[pointer])
                ) != text:
                    raise ValueError(
                        f"op[{idx}]: unified diff removal mismatch in '{path_str}'"
                    )
                pointer += 1
            elif marker == "+":
                rebuilt.append(f"{text}{newline}")
            else:
                raise ValueError(f"op[{idx}]: unsupported diff line in '{path_str}'")
        consumed = pointer - hunk_start
        lines[hunk_start:pointer] = rebuilt
        offset += len(rebuilt) - consumed
    return "".join(lines)


def _node_source_segment(text: str, node: Any) -> str:
    lines = text.splitlines(keepends=True)
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", getattr(node, "lineno", 1))
    return "".join(lines[start:end])


def _apply_python_ast_operation(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    import ast

    target_type = str(op.get("target_type", "")).strip()
    target_name = str(op.get("target_name", "")).strip()
    new_text = op.get("new_text")
    insert_if_missing = bool(op.get("insert_if_missing"))
    if target_type not in {"function", "class", "import"}:
        raise ValueError(
            f"op[{idx}]: unsupported python_ast target_type for '{path_str}'"
        )
    if not isinstance(new_text, str):
        raise ValueError(f"op[{idx}]: new_text is required and must be a string")
    tree = ast.parse(content or "\n")
    lines = content.splitlines(keepends=True)
    replacement = _normalize_newlines(new_text)
    for node in tree.body:
        if (
            target_type == "function"
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == target_name
        ):
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[:start] + [replacement] + lines[end:])
        if (
            target_type == "class"
            and isinstance(node, ast.ClassDef)
            and node.name == target_name
        ):
            start = node.lineno - 1
            end = node.end_lineno
            return "".join(lines[:start] + [replacement] + lines[end:])
        if target_type == "import" and isinstance(node, (ast.Import, ast.ImportFrom)):
            segment = _normalize_newlines(_node_source_segment(content, node)).strip()
            if segment == target_name:
                start = node.lineno - 1
                end = node.end_lineno
                return "".join(lines[:start] + [replacement] + lines[end:])
    if not insert_if_missing:
        raise ValueError(f"op[{idx}]: python_ast target not found in '{path_str}'")
    insertion = replacement if replacement.endswith("\n") else f"{replacement}\n"
    if target_type == "import":
        return f"{insertion}{content}"
    return content + ("" if content.endswith("\n") or not content else "\n") + insertion


def _apply_python_ast_preserving_newlines(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    import ast

    target_type = str(op.get("target_type", "")).strip()
    target_name = str(op.get("target_name", "")).strip()
    new_text = op.get("new_text")
    insert_if_missing = bool(op.get("insert_if_missing"))
    if target_type not in {"function", "class", "import"}:
        raise ValueError(
            f"op[{idx}]: unsupported python_ast target_type for '{path_str}'"
        )
    if not isinstance(new_text, str):
        raise ValueError(f"op[{idx}]: new_text is required and must be a string")

    tree = ast.parse(content or "\n")
    lines = content.splitlines(keepends=True)
    for node in tree.body:
        matches_target = (
            target_type == "function"
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == target_name
        ) or (
            target_type == "class"
            and isinstance(node, ast.ClassDef)
            and node.name == target_name
        )
        if target_type == "import" and isinstance(node, (ast.Import, ast.ImportFrom)):
            segment = _normalize_newlines(_node_source_segment(content, node)).strip()
            matches_target = segment == target_name
        if matches_target:
            start = node.lineno - 1
            end = node.end_lineno
            newline = _line_range_replacement_newline(content, lines, start, end)
            replacement = _restore_newlines(new_text, newline)
            return "".join(lines[:start] + [replacement] + lines[end:])

    if not insert_if_missing:
        raise ValueError(f"op[{idx}]: python_ast target not found in '{path_str}'")
    newline = _dominant_newline(content)
    replacement = _restore_newlines(new_text, newline)
    insertion = replacement if replacement.endswith(newline) else f"{replacement}{newline}"
    if target_type == "import":
        return f"{insertion}{content}"
    separator = "" if not content or content.endswith(("\n", "\r")) else newline
    return f"{content}{separator}{insertion}"


def _apply_operation_to_content(
    content: str, op: dict[str, Any], path_str: str, idx: int
) -> str:
    operation_type = str(op.get("type") or op.get("operation") or "exact_text").strip()
    if operation_type in {"exact_text", "replace_exact", "modify", ""}:
        return _apply_exact_text_operation(content, op, path_str, idx)
    if operation_type in {"replace_lines", "line_range"}:
        return _apply_line_range_operation(content, op, path_str, idx)
    if operation_type in {"unified_diff", "apply_unified_diff"}:
        return _apply_unified_diff_operation(content, op, path_str, idx)
    if operation_type in {"python_ast", "ast_python"}:
        return _apply_python_ast_operation(content, op, path_str, idx)
    raise ValueError(f"op[{idx}]: unsupported operation type '{operation_type}'")


# ---------------------------------------------------------------------------
# Patch validation (shared by preview and apply)
# ---------------------------------------------------------------------------


def _validate_operations(
    repo_root: Path,
    operations: list[dict],
    *,
    for_apply: bool = False,
) -> tuple[list[dict], list[str]]:
    """Validate and compose patch operations into one final edit per file.

    Multiple operations may target the same file when each ``old_text`` occurs
    exactly once in the original file and their source ranges do not overlap.
    Every operation is checked against the original file hash. The final
    validated result contains one atomic write per changed file so a later edit
    cannot overwrite an earlier same-file edit.
    """
    del for_apply
    if not operations or not isinstance(operations, list):
        return [], ["operations must be a non-empty list"]

    errors: list[str] = []
    requested_paths = {
        str(op.get("path", ""))
        for op in operations
        if isinstance(op, dict) and op.get("path")
    }
    if len(requested_paths) > MAX_PATCH_FILES:
        errors.append(
            f"Patch exceeds {MAX_PATCH_FILES} file limit ({len(requested_paths)} files)"
        )

    states: dict[str, dict[str, Any]] = {}
    path_order: list[str] = []

    for idx, op in enumerate(operations):
        if not isinstance(op, dict):
            errors.append(f"op[{idx}]: operation must be an object")
            continue

        path_str = op.get("path", "")
        expected_sha = op.get("expected_sha256", "")

        if not path_str or not isinstance(path_str, str):
            errors.append(f"op[{idx}]: path is required")
            continue

        state = states.get(path_str)
        if state is None:
            try:
                absolute = _resolve_and_validate_write(repo_root, path_str)
            except ValueError as exc:
                errors.append(f"op[{idx}]: {exc}")
                continue

            if not absolute.exists():
                errors.append(f"op[{idx}]: file does not exist: {path_str}")
                continue
            if absolute.is_dir():
                errors.append(f"op[{idx}]: path is a directory: {path_str}")
                continue
            if absolute.is_symlink():
                errors.append(f"op[{idx}]: symlinks are not allowed: {path_str}")
                continue
            if _is_binary(absolute):
                errors.append(f"op[{idx}]: binary files are not supported: {path_str}")
                continue

            try:
                current_bytes = absolute.read_bytes()
                current_text = current_bytes.decode("utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"op[{idx}]: cannot read file: {exc}")
                continue

            state = {
                "path": path_str,
                "absolute": absolute,
                "current_bytes": current_bytes,
                "current_content": current_text,
                "working_content": _normalize_newlines(current_text),
                "working_content_preserved": current_text,
                "newline_mode": "",
                "dominant_newline": _dominant_newline(current_text),
                "current_sha256": hashlib.sha256(current_bytes).hexdigest(),
                "validation_results": [],
                "applied_exact_old_texts": {},
            }
            states[path_str] = state
            path_order.append(path_str)

        current_sha = state["current_sha256"]
        if expected_sha and current_sha != expected_sha:
            errors.append(
                f"op[{idx}]: stale hash for '{path_str}': "
                f"expected {expected_sha[:12]}… got {current_sha[:12]}…"
            )
            continue
        operation_type = str(
            op.get("type") or op.get("operation") or "exact_text"
        )
        exact_text_operation = operation_type in {
            "exact_text",
            "replace_exact",
            "modify",
            "",
        }
        line_range_operation = operation_type in {"replace_lines", "line_range"}
        unified_diff_operation = operation_type in {
            "unified_diff",
            "apply_unified_diff",
        }
        python_ast_operation = operation_type in {"python_ast", "ast_python"}
        byte_preserving_operation = (
            exact_text_operation
            or line_range_operation
            or unified_diff_operation
            or python_ast_operation
        )
        preserve_newlines_value = op.get("preserve_newlines")
        preserve_newlines = (
            byte_preserving_operation
            if preserve_newlines_value is None
            else bool(preserve_newlines_value)
        )
        requested_newline_mode = "preserved" if preserve_newlines else "normalized"
        try:
            existing_newline_mode = state["newline_mode"]
            if existing_newline_mode and existing_newline_mode != requested_newline_mode:
                raise ValueError(
                    f"op[{idx}]: cannot mix preserve_newlines and normalized edits "
                    f"for '{path_str}'"
                )
            if preserve_newlines:
                if exact_text_operation:
                    state["working_content_preserved"] = (
                        _apply_exact_text_preserving_newlines(
                            state["working_content_preserved"], op, path_str, idx
                        )
                    )
                elif line_range_operation:
                    state["working_content_preserved"] = (
                        _apply_line_range_preserving_newlines(
                            state["working_content_preserved"], op, path_str, idx
                        )
                    )
                elif unified_diff_operation:
                    state["working_content_preserved"] = (
                        _apply_unified_diff_preserving_newlines(
                            state["working_content_preserved"], op, path_str, idx
                        )
                    )
                elif python_ast_operation:
                    state["working_content_preserved"] = (
                        _apply_python_ast_preserving_newlines(
                            state["working_content_preserved"], op, path_str, idx
                        )
                    )
                else:
                    raise ValueError(
                        f"op[{idx}]: preserve_newlines is supported only for "
                        f"exact_text, line_range, unified_diff, and python_ast edits "
                        f"in '{path_str}'"
                    )
            else:
                state["working_content"] = _apply_operation_to_content(
                    state["working_content"], op, path_str, idx
                )
            state["newline_mode"] = requested_newline_mode
            if operation_type in {"exact_text", "replace_exact", "modify", ""}:
                old_text = _normalize_newlines(str(op.get("old_text", "")))
                state["applied_exact_old_texts"][old_text] = idx
            state["validation_results"].append(
                {
                    "index": idx,
                    "path": path_str,
                    "type": operation_type,
                    "ok": True,
                }
            )
        except ValueError as exc:
            operation_type = str(op.get("type") or op.get("operation") or "exact_text")
            if operation_type in {
                "exact_text",
                "replace_exact",
                "modify",
                "",
            } and "old_text not found" in str(exc):
                old_text = _normalize_newlines(str(op.get("old_text", "")))
                prior = state["applied_exact_old_texts"].get(old_text)
                if prior is not None:
                    message = f"op[{idx}]: edit overlaps op[{prior}] in '{path_str}'"
                else:
                    message = str(exc)
            else:
                message = str(exc)
            errors.append(message)
            state["validation_results"].append(
                {
                    "index": idx,
                    "path": path_str,
                    "type": operation_type,
                    "ok": False,
                    "error": message,
                }
            )
            continue

    validated: list[dict] = []
    total_changed_lines = 0
    total_changed_bytes = 0
    for path_str in path_order:
        state = states[path_str]
        current_text = state["current_content"]
        if not state["validation_results"] or not all(
            item.get("ok") for item in state["validation_results"]
        ):
            continue
        if state["newline_mode"] == "preserved":
            new_content = state["working_content_preserved"]
        else:
            new_content = _restore_newlines(
                state["working_content"], state["dominant_newline"]
            )
        diff = _unified_diff_for_op(current_text, new_content, path_str)
        (
            changed_lines,
            logical_changed_lines,
            newline_only_changed_lines,
        ) = _change_line_counts(current_text, new_content, path_str)
        newline_diagnostic = _newline_diagnostic(current_text, new_content)
        warnings: list[str] = []
        if (
            state["newline_mode"] == "normalized"
            and newline_diagnostic["mixed_old"]
            and newline_diagnostic["old_counts"] != newline_diagnostic["new_counts"]
        ):
            warnings.append(
                f"'{path_str}' requests whole-file newline normalization; "
                "set preserve_newlines=true to keep untouched newline sequences"
            )
        if state["newline_mode"] == "preserved" and newline_only_changed_lines:
            errors.append(
                f"Patch for '{path_str}' introduces "
                f"{newline_only_changed_lines} newline-only changed lines while "
                f"preserve_newlines is enabled"
            )
            continue
        changed_bytes = abs(
            len(new_content.encode("utf-8")) - len(state["current_bytes"])
        )
        total_changed_lines += changed_lines
        total_changed_bytes += changed_bytes
        validated.append(
            {
                "path": path_str,
                "absolute": state["absolute"],
                "current_sha256": state["current_sha256"],
                "current_content": current_text,
                "new_content": new_content,
                "diff": diff,
                "changed_lines": changed_lines,
                "logical_changed_lines": logical_changed_lines,
                "newline_only_changed_lines": newline_only_changed_lines,
                "newline_diagnostic": newline_diagnostic,
                "warnings": warnings,
                "changed_bytes": changed_bytes,
                "operation_count": len(state["validation_results"]),
                "validation_results": list(state["validation_results"]),
            }
        )

    if total_changed_lines > MAX_PATCH_LINES:
        errors.append(
            f"Patch exceeds {MAX_PATCH_LINES} changed-line limit "
            f"({total_changed_lines} lines)"
        )
    if total_changed_bytes > MAX_PATCH_BYTES:
        errors.append(f"Patch exceeds {MAX_PATCH_BYTES // 1024} KB changed-byte limit")

    return validated, errors


def preview_repo_patch(
    repo_root: Path,
    operations: list[dict],
    runs_dir: Path,
    *,
    commit_title: str = "",
    commit_description: str = "",
) -> dict:
    """
    Validate operations and store a preview.  Never modifies files.
    Returns patch_id, unified diff, changed files, stats, and validation errors.
    """
    patch_id = _make_patch_id()
    bound_commit_description = commit_description
    if commit_title or commit_description:
        bound_commit_description = "\n".join(
            item
            for item in (commit_description, f"Preview-ID: {patch_id}")
            if item
        )
    if commit_title or commit_description:
        _validate_commit_metadata(
            commit_title or "CodexBridge: repo_apply",
            bound_commit_description,
            files_validated=True,
        )
    head = _git_head(repo_root)
    validated, errors = _validate_operations(repo_root, operations)

    combined_diff = ""
    changed_files: list[str] = []
    total_changed_lines = 0
    total_logical_changed_lines = 0
    total_newline_only_changed_lines = 0
    total_changed_bytes = 0
    bundle_operations: list[dict[str, Any]] = []
    newline_diagnostics: list[dict[str, Any]] = []
    warnings: list[str] = []

    for op in validated:
        combined_diff += op["diff"]
        changed_files.append(op["path"])
        total_changed_lines += op["changed_lines"]
        total_logical_changed_lines += op["logical_changed_lines"]
        total_newline_only_changed_lines += op["newline_only_changed_lines"]
        newline_diagnostics.append(
            {"path": op["path"], **op["newline_diagnostic"]}
        )
        warnings.extend(op.get("warnings") or [])
        total_changed_bytes += op["changed_bytes"]
        bundle_operations.append(
            {
                "action": "modify",
                "path": op["path"],
                "current_sha256": op["current_sha256"],
                "payload_text": op["new_content"],
                "changed_lines": op["changed_lines"],
                "logical_changed_lines": op["logical_changed_lines"],
                "newline_only_changed_lines": op["newline_only_changed_lines"],
                "newline_diagnostic": op["newline_diagnostic"],
                "changed_bytes": op["changed_bytes"],
            }
        )

    _write_preview_bundle(
        repo_root,
        runs_dir,
        patch_id,
        bundle_operations,
        combined_diff,
        git_head=head,
        errors=errors,
        warnings=warnings,
        commit_title=commit_title,
        commit_description=bound_commit_description,
    )

    return {
        "ok": not bool(errors),
        "patch_id": patch_id,
        "repo_name": "",
        "diff": combined_diff,
        "changed_files": changed_files,
        "changed_lines": total_changed_lines,
        "logical_changed_lines": total_logical_changed_lines,
        "newline_only_changed_lines": total_newline_only_changed_lines,
        "newline_diagnostics": _bounded_newline_diagnostics(newline_diagnostics),
        "warnings": warnings[:20],
        "changed_bytes": total_changed_bytes,
        "git_head": head,
        "validation_errors": errors,
        "error": "; ".join(errors) if errors else "",
        "commit_title": commit_title,
        "commit_description": bound_commit_description,
    }


def preview_repo_file_creation(
    repo_root: Path, path: str, content: str, runs_dir: Path
) -> dict:
    patch_id = _make_patch_id()
    head = _git_head(repo_root)

    changed_files = [path]
    validation_errors: list[str] = []
    diff_text = ""
    size_bytes = 0

    try:
        _, size_bytes = _validate_create_target(repo_root, path, content)
        diff_text = _unified_diff_for_op("", content, path)
        changed_lines = _count_changed_lines(diff_text)
        bundle_operations = [
            {
                "action": "create",
                "path": path,
                "current_sha256": "",
                "payload_text": content,
                "changed_lines": changed_lines,
                "changed_bytes": size_bytes,
            }
        ]
    except (OSError, ValueError, FileNotFoundError) as exc:
        validation_errors = [str(exc)]
        changed_lines = 0
        bundle_operations = []

    _write_preview_bundle(
        repo_root,
        runs_dir,
        patch_id,
        bundle_operations,
        diff_text,
        git_head=head,
        errors=validation_errors,
    )

    return {
        "ok": not bool(validation_errors),
        "patch_id": patch_id,
        "repo_name": "",
        "diff": diff_text,
        "changed_files": changed_files if not validation_errors else [],
        "changed_lines": changed_lines,
        "changed_bytes": size_bytes if not validation_errors else 0,
        "git_head": head,
        "validation_errors": validation_errors,
        "error": "; ".join(validation_errors) if validation_errors else "",
    }


def preview_repo_file_removal(
    repo_root: Path, path: str, expected_sha256: str, runs_dir: Path
) -> dict:
    patch_id = _make_patch_id()
    head = _git_head(repo_root)

    diff_text = ""
    validation_errors: list[str] = []
    changed_bytes = 0
    changed_lines = 0

    try:
        absolute, current_bytes, current_sha = _validate_remove_target(
            repo_root, path, expected_sha256
        )
        if _is_binary(absolute):
            diff_text = (
                f"--- a/{path}\n"
                f"+++ b/{path}\n"
                "@@ -1 +0,0 @@\n"
                "-[binary content omitted]\n"
            )
        else:
            current_text = current_bytes.decode("utf-8", errors="replace")
            diff_text = _unified_diff_for_op(current_text, "", path)
        changed_lines = _count_changed_lines(diff_text)
        changed_bytes = len(current_bytes)
        bundle_operations = [
            {
                "action": "remove",
                "path": path,
                "current_sha256": current_sha,
                "changed_lines": changed_lines,
                "changed_bytes": changed_bytes,
            }
        ]
    except (OSError, ValueError, FileNotFoundError) as exc:
        validation_errors = [str(exc)]
        bundle_operations = []

    _write_preview_bundle(
        repo_root,
        runs_dir,
        patch_id,
        bundle_operations,
        diff_text,
        git_head=head,
        errors=validation_errors,
    )

    return {
        "ok": not bool(validation_errors),
        "patch_id": patch_id,
        "repo_name": "",
        "diff": diff_text,
        "changed_files": [path] if not validation_errors else [],
        "changed_lines": changed_lines,
        "changed_bytes": changed_bytes,
        "git_head": head,
        "validation_errors": validation_errors,
        "error": "; ".join(validation_errors) if validation_errors else "",
    }


# ---------------------------------------------------------------------------
# apply_repo_patch
# ---------------------------------------------------------------------------


def apply_repo_patch(
    repo_root: Path,
    operations: list[dict],
    patch_id: str,
    runs_dir: Path,
) -> dict:
    """
    Apply a patch that was previously validated by preview_repo_patch.

    Rechecks everything before touching any file.  Applies atomically via
    a write-to-temp-then-rename pattern.  Saves originals for rollback.
    """
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    if not patch_dir.exists():
        raise ValueError(f"Unknown patch_id: {patch_id}")

    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("status") == "applied":
        return _idempotent_apply_result(manifest, patch_id)
    if manifest.get("status") == "reverted":
        raise ValueError(f"Patch {patch_id} has been reverted")
    if manifest.get("status") == "preview_failed":
        raise ValueError(
            f"Patch {patch_id} preview had validation errors; cannot apply"
        )

    # Recheck git HEAD
    current_head = _git_head(repo_root)
    preview_head = manifest.get("git_head_at_preview", "")
    if preview_head and current_head and current_head != preview_head:
        raise ValueError(
            f"Git HEAD has changed since preview "
            f"(preview: {preview_head[:12]}, current: {current_head[:12]})"
        )

    # Full re-validation (re-reads files to detect any changes since preview)
    validated, errors = _validate_operations(repo_root, operations, for_apply=True)
    if errors:
        raise ValueError(f"Re-validation failed: {'; '.join(errors)}")
    transaction = TransactionContext(
        repo_root,
        [op["path"] for op in validated],
    )
    transaction.set_phase("preflight", {"patch_id": patch_id})
    transaction.validation_results = [
        item for op in validated for item in op.get("validation_results", [])
    ]

    # Cross-check validated ops against the manifest
    manifest_ops = {op["path"]: op for op in manifest.get("operations", [])}
    for op in validated:
        m = manifest_ops.get(op["path"])
        if m is None:
            raise ValueError(
                f"Operation for '{op['path']}' was not in the preview manifest"
            )
        if op["current_sha256"] != m["current_sha256"]:
            raise ValueError(
                f"File '{op['path']}' has changed since preview (hash mismatch)"
            )
        expected_payload_sha = _preview_payload_sha(m)
        if not expected_payload_sha:
            raise ValueError(
                f"Patch {patch_id} is missing opaque payload metadata for '{op['path']}'"
            )
        if _sha256_text(op["new_content"]) != expected_payload_sha:
            raise ValueError(
                f"Operation for '{op['path']}' does not match the previewed payload"
            )

    # Save originals for rollback
    rollback_dir = patch_dir / "rollback"
    rollback_dir.mkdir(exist_ok=True)
    transaction.register_temp_artifact(rollback_dir)
    rollback_files: dict[str, str] = {}
    transaction.set_phase("snapshot", {"touched_files": len(validated)})
    for op in validated:
        rollback_name = _legacy_rollback_file_name(op["path"])
        rollback_files[op["path"]] = rollback_name
        rollback_file = rollback_dir / rollback_name
        rollback_file.write_bytes(op["current_content"].encode("utf-8"))

    # Write all files atomically (temp → rename)
    written: list[dict] = []
    manifest["status"] = "applying"
    manifest["applying_at"] = _utc_now()
    try:
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2),
            ".codexbridge_manifest_tmp",
        )
    except Exception as exc:
        raise RuntimeError(f"Apply failed before writes: {exc}") from exc
    try:
        transaction.set_phase("apply", {"touched_files": len(validated)})
        for op in validated:
            absolute: Path = op["absolute"]
            new_content: str = op["new_content"]
            _atomic_write_bytes(
                absolute,
                new_content.encode("utf-8"),
                ".codexbridge_tmp",
            )
            new_sha = _sha256_file(absolute)
            written.append({"path": op["path"], "sha256": new_sha})
        transaction.set_phase("validate", {"written_files": len(written)})
    except Exception as exc:
        rollback = rollback_transaction(
            transaction,
            write_bytes=lambda path, data: _atomic_write_bytes(path, data, ".rollback"),
            unlink_path=lambda path: path.unlink(),
        )
        manifest["status"] = "failed" if rollback.get("ok") else "rollback_failed"
        manifest["failed_at"] = _utc_now()
        manifest["errors"] = [str(exc), *list(rollback.get("errors") or [])]
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2),
            ".codexbridge_manifest_tmp",
        )
        raise RuntimeError(f"Apply failed (partial rollback attempted): {exc}") from exc

    # Update manifest
    transaction.set_phase("commit", {"written_files": len(written)})
    manifest["status"] = "applied"
    manifest["applied_at"] = _utc_now()
    manifest["applied_git_head"] = current_head
    manifest["applied_results"] = [
        {
            "action": "modify",
            "path": item["path"],
            "sha256": item["sha256"],
            "rollback_file": rollback_files[item["path"]],
        }
        for item in written
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = {
        "ok": True,
        "patch_id": patch_id,
        "repo_name": "",
        "changed_files": [w["path"] for w in written],
        "results": written,
        "git_head": current_head,
        "error": "",
        "commit_title": str(manifest.get("commit_title") or ""),
        "commit_description": str(manifest.get("commit_description") or ""),
    }
    result.update(build_transaction_result(transaction))
    result["idempotent_replay"] = False
    manifest["apply_result"] = result
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2),
        ".codexbridge_manifest_tmp",
    )
    return result


def apply_previewed_repo_change(repo_root: Path, patch_id: str, runs_dir: Path) -> dict:
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    if not patch_dir.exists():
        raise ValueError(f"Unknown patch_id: {patch_id}")

    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    status = manifest.get("status")
    if status == "applied":
        return _idempotent_apply_result(manifest, patch_id)
    if status == "reverted":
        raise ValueError(f"Patch {patch_id} has been reverted")
    if status == "preview_failed":
        raise ValueError(
            f"Patch {patch_id} preview had validation errors; cannot apply"
        )
    if manifest.get("bundle_version") not in {2, 3}:
        raise ValueError(f"Patch {patch_id} does not include an opaque preview bundle")

    expected_repo_fingerprint = manifest.get("repo_fingerprint", "")
    if not expected_repo_fingerprint:
        raise ValueError(f"Patch {patch_id} is missing repository binding metadata")
    current_repo_fingerprint = _repo_fingerprint(repo_root)
    if current_repo_fingerprint != expected_repo_fingerprint:
        raise ValueError(
            f"Patch {patch_id} does not belong to the requested repository"
        )

    manifest_ops = manifest.get("operations", [])
    if not isinstance(manifest_ops, list) or not manifest_ops:
        raise ValueError(f"Patch {patch_id} does not include any previewed operations")
    if len(manifest_ops) > MAX_PATCH_FILES:
        raise ValueError(
            f"Patch exceeds {MAX_PATCH_FILES} file limit ({len(manifest_ops)} files)"
        )

    manifest_paths: set[str] = set()
    resolved_ops: list[tuple[dict[str, Any], Path]] = []
    for op in manifest_ops:
        action = op.get("action")
        path_str = op.get("path", "")
        if action not in {"modify", "create", "remove"} or not isinstance(
            path_str, str
        ):
            raise ValueError(f"Patch {patch_id} has an invalid operation entry")
        absolute = _resolve_and_validate_write(repo_root, path_str)
        normalized_path = os.path.normcase(os.path.normpath(str(absolute.resolve())))
        if normalized_path in manifest_paths:
            raise ValueError(f"Patch {patch_id} includes duplicate paths: {path_str}")
        manifest_paths.add(normalized_path)
        resolved_ops.append((op, absolute))

    current_head = _git_head(repo_root)
    preview_head = manifest.get("git_head_at_preview", "")
    requires_head_match = any(
        op.get("action") in {"modify", "remove"} for op in manifest_ops
    )
    if (
        requires_head_match
        and preview_head
        and current_head
        and current_head != preview_head
    ):
        raise ValueError(
            f"Git HEAD has changed since preview "
            f"(preview: {preview_head[:12]}, current: {current_head[:12]})"
        )

    prepared_ops: list[dict[str, Any]] = []
    total_changed_lines = 0
    total_changed_bytes = 0
    for index, (op, absolute) in enumerate(resolved_ops):
        action = op["action"]
        path_str = op["path"]
        if action == "modify":
            if not absolute.exists():
                raise ValueError(f"File does not exist: {path_str}")
            if absolute.is_dir():
                raise ValueError(f"Path is a directory: {path_str}")
            if absolute.is_symlink():
                raise ValueError(f"Symlinks are not allowed: {path_str}")
            if _is_binary(absolute):
                raise ValueError(f"Binary files are not supported: {path_str}")
            current_bytes = absolute.read_bytes()
            current_sha = hashlib.sha256(current_bytes).hexdigest()
            if current_sha != op.get("current_sha256", ""):
                raise ValueError(
                    f"File '{path_str}' has changed since preview (hash mismatch)"
                )
            try:
                payload_bytes = assemble_payload(
                    index,
                    op,
                    lambda filename, expected: _resolve_bundle_file(
                        patch_dir,
                        filename,
                        expected,
                        kind="payload",
                    ).read_bytes(),
                )
            except ValueError as exc:
                raise ValueError(
                    f"Patch {patch_id} payload verification failed for '{path_str}': {exc}"
                ) from exc
            payload_text = payload_bytes.decode("utf-8")
            diff_text = _unified_diff_for_op(
                current_bytes.decode("utf-8", errors="replace"), payload_text, path_str
            )
            changed_lines = _count_changed_lines(diff_text)
            changed_bytes = abs(len(payload_bytes) - len(current_bytes))
            prepared_ops.append(
                {
                    "action": action,
                    "path": path_str,
                    "absolute": absolute,
                    "payload_bytes": payload_bytes,
                    "rollback_bytes": current_bytes,
                }
            )
        elif action == "create":
            try:
                payload_bytes = assemble_payload(
                    index,
                    op,
                    lambda filename, expected: _resolve_bundle_file(
                        patch_dir,
                        filename,
                        expected,
                        kind="payload",
                    ).read_bytes(),
                )
            except ValueError as exc:
                raise ValueError(
                    f"Patch {patch_id} payload verification failed for '{path_str}': {exc}"
                ) from exc
            payload_text = payload_bytes.decode("utf-8")
            _, size_bytes = _validate_create_target(repo_root, path_str, payload_text)
            diff_text = _unified_diff_for_op("", payload_text, path_str)
            changed_lines = _count_changed_lines(diff_text)
            changed_bytes = size_bytes
            prepared_ops.append(
                {
                    "action": action,
                    "path": path_str,
                    "absolute": absolute,
                    "payload_bytes": payload_bytes,
                    "rollback_bytes": None,
                }
            )
        else:
            _, current_bytes, _ = _validate_remove_target(
                repo_root, path_str, op.get("current_sha256", "")
            )
            changed_lines, changed_bytes = _remove_change_stats(
                path_str, absolute, current_bytes
            )
            prepared_ops.append(
                {
                    "action": action,
                    "path": path_str,
                    "absolute": absolute,
                    "payload_bytes": None,
                    "rollback_bytes": current_bytes,
                }
            )

        total_changed_lines += int(changed_lines)
        total_changed_bytes += int(changed_bytes)

    if total_changed_lines > MAX_PATCH_LINES:
        raise ValueError(
            f"Patch exceeds {MAX_PATCH_LINES} changed-line limit "
            f"({total_changed_lines} lines)"
        )
    if total_changed_bytes > MAX_PATCH_BYTES:
        raise ValueError(
            f"Patch exceeds {MAX_PATCH_BYTES // 1024} KB changed-byte limit"
        )

    transaction = TransactionContext(
        repo_root,
        [op["path"] for op in prepared_ops],
    )
    transaction.set_phase("preflight", {"patch_id": patch_id})
    rollback_dir = patch_dir / "rollback"
    rollback_dir.mkdir(exist_ok=True)
    transaction.register_temp_artifact(rollback_dir)
    applied_results: list[dict[str, Any]] = []
    manifest["status"] = "applying"
    manifest["applying_at"] = _utc_now()
    try:
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2),
            ".codexbridge_manifest_tmp",
        )
    except Exception as exc:
        raise RuntimeError(f"Apply failed before writes: {exc}") from exc
    try:
        transaction.set_phase("snapshot", {"touched_files": len(prepared_ops)})
        for index, op in enumerate(prepared_ops):
            rollback_bytes = op["rollback_bytes"]
            rollback_file = ""
            if rollback_bytes is not None:
                rollback_file = _rollback_file_name(index)
                _atomic_write_bytes(
                    rollback_dir / rollback_file,
                    rollback_bytes,
                    ".codexbridge_rollback_tmp",
                )

            absolute = op["absolute"]
            transaction.set_phase("apply", {"path": op["path"], "index": index})
            if op["action"] in {"modify", "create"}:
                payload_bytes = op["payload_bytes"]
                result_sha = _sha256_bytes(payload_bytes)
                _atomic_write_bytes(
                    absolute,
                    payload_bytes,
                    ".codexbridge_apply_tmp",
                )
            else:
                absolute.unlink()
                result_sha = ""

            applied_results.append(
                {
                    "action": op["action"],
                    "path": op["path"],
                    "sha256": result_sha,
                    "rollback_file": rollback_file,
                }
            )

        transaction.set_phase("validate", {"written_files": len(applied_results)})
        manifest["status"] = "applied"
        manifest["applied_at"] = _utc_now()
        manifest["applied_git_head"] = current_head
        manifest["applied_results"] = applied_results
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2),
            ".codexbridge_manifest_tmp",
        )
    except Exception as exc:
        rollback_errors: list[str] = []
        try:
            _rollback_applied_preview_ops(repo_root, rollback_dir, applied_results)
            rollback = rollback_transaction(
                transaction,
                write_bytes=lambda path, data: _atomic_write_bytes(
                    path, data, ".rollback"
                ),
                unlink_path=lambda path: path.unlink(),
            )
            rollback_errors.extend(list(rollback.get("errors") or []))
        except Exception as rollback_exc:
            rollback_errors.append(str(rollback_exc))
        manifest["status"] = "rollback_failed" if rollback_errors else "failed"
        manifest["failed_at"] = _utc_now()
        manifest["errors"] = [str(exc), *rollback_errors]
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2),
            ".codexbridge_manifest_tmp",
        )
        raise RuntimeError(f"Apply failed (partial rollback attempted): {exc}") from exc

    transaction.set_phase("commit", {"written_files": len(applied_results)})
    result = {
        "ok": True,
        "patch_id": patch_id,
        "repo_name": "",
        "changed_files": [result["path"] for result in applied_results],
        "results": [
            {"path": result["path"], "sha256": result["sha256"]}
            for result in applied_results
        ],
        "git_head": current_head,
        "error": "",
        "commit_title": str(manifest.get("commit_title") or ""),
        "commit_description": str(manifest.get("commit_description") or ""),
    }
    result.update(build_transaction_result(transaction))
    result["idempotent_replay"] = False
    manifest["apply_result"] = result
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2),
        ".codexbridge_manifest_tmp",
    )
    return result


# ---------------------------------------------------------------------------
# revert_managed_patch
# ---------------------------------------------------------------------------


def revert_managed_patch(repo_root: Path, patch_id: str, runs_dir: Path) -> dict:
    """
    Revert a previously applied managed patch using saved rollback content.
    Verifies current hashes match applied-result hashes before reverting.
    Never uses git reset, git checkout, or shell commands.
    """
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    if not patch_dir.exists():
        raise ValueError(f"Unknown patch_id: {patch_id}")

    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("status") != "applied":
        raise ValueError(
            f"Patch {patch_id} is not in 'applied' state (status: {manifest.get('status')})"
        )

    applied_results = manifest.get("applied_results", [])
    if not isinstance(applied_results, list) or not applied_results:
        raise ValueError(f"Patch {patch_id} is missing applied result metadata")
    rollback_dir = patch_dir / "rollback"

    for result in applied_results:
        action = result.get("action", "modify")
        path_str = result["path"]
        absolute = _resolve_and_validate_write(repo_root, path_str)
        expected_sha = result.get("sha256", "")

        if action == "remove":
            if absolute.exists():
                raise ValueError(
                    f"Cannot revert: removed file '{path_str}' now exists on disk"
                )
            continue

        if not absolute.exists():
            raise ValueError(
                f"Cannot revert: file '{path_str}' no longer exists on disk"
            )
        current_sha = _sha256_file(absolute)
        if current_sha != expected_sha:
            raise ValueError(
                f"Cannot revert: file '{path_str}' has been modified since the patch "
                f"was applied (expected {expected_sha[:12]}…, got {current_sha[:12]}…)"
            )

    # Apply rollback content atomically
    reverted: list[str] = []
    try:
        for index in range(len(applied_results) - 1, -1, -1):
            result = applied_results[index]
            action = result.get("action", "modify")
            path_str = result["path"]
            absolute = _resolve_and_validate_write(repo_root, path_str)

            if action == "create":
                absolute.unlink()
                reverted.append(path_str)
                continue

            rollback_file = result.get("rollback_file", "")
            if not rollback_file:
                rollback_file = _legacy_rollback_file_name(path_str)
            indexed_name = _rollback_file_name(index)
            legacy_name = _legacy_rollback_file_name(path_str)
            if rollback_file == indexed_name:
                expected_name = indexed_name
            elif rollback_file == legacy_name:
                expected_name = legacy_name
            else:
                expected_name = (
                    indexed_name if result.get("rollback_file") else legacy_name
                )
            rollback_path = _resolve_bundle_file(
                rollback_dir,
                rollback_file,
                expected_name,
                kind="rollback",
            )
            original = rollback_path.read_bytes()
            _atomic_write_bytes(
                absolute,
                original,
                ".codexbridge_revert_tmp",
            )
            reverted.append(path_str)
    except Exception as exc:
        raise RuntimeError(f"Revert failed after partial write: {exc}") from exc

    manifest["status"] = "reverted"
    manifest["reverted_at"] = _utc_now()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "patch_id": patch_id,
        "repo_name": "",
        "reverted_files": reverted,
        "changed_files": list(reverted),
        "error": "",
    }


# ---------------------------------------------------------------------------
# create_repo_file
# ---------------------------------------------------------------------------


def create_repo_file(repo_root: Path, path: str, content: str) -> dict:
    """
    Create a new file at *path* with *content*.
    Rejects existing files. Creates parent directories only inside the repo.
    """
    absolute, size_bytes = _validate_create_target(repo_root, path, content)
    _atomic_write_text(absolute, content, ".codexbridge_create_tmp")
    sha = _sha256_file(absolute)

    return {
        "ok": True,
        "repo_name": "",
        "path": path,
        "changed_files": [path],
        "sha256": sha,
        "size_bytes": size_bytes,
        "error": "",
    }


# ---------------------------------------------------------------------------
# delete_repo_file
# ---------------------------------------------------------------------------


def delete_repo_file(
    repo_root: Path,
    path: str,
    expected_sha256: str,
    runs_dir: Path,
) -> dict:
    """
    Delete a file after verifying expected_sha256.
    Saves rollback content so the deletion can be undone if needed.
    """
    absolute, current_bytes, current_sha = _validate_remove_target(
        repo_root, path, expected_sha256
    )

    # Save rollback copy
    del_id = _make_patch_id().replace("_patch_", "_delete_")
    del_dir = runs_dir / MANAGED_PATCHES_DIR / del_id
    del_dir.mkdir(parents=True, exist_ok=True)
    rollback_file = del_dir / "original_content.txt"
    rollback_file.write_bytes(current_bytes)
    manifest = {
        "patch_id": del_id,
        "operation": "delete",
        "path": path,
        "sha256_at_delete": current_sha,
        "created_at": _utc_now(),
        "status": "deleted",
    }
    (del_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    absolute.unlink()

    return {
        "ok": True,
        "repo_name": "",
        "path": path,
        "changed_files": [path],
        "rollback_id": del_id,
        "error": "",
    }


# ---------------------------------------------------------------------------
# move_repo_file
# ---------------------------------------------------------------------------


def move_repo_file(
    repo_root: Path,
    source_path: str,
    destination_path: str,
    expected_sha256: str,
    runs_dir: Path,
) -> dict:
    """
    Move *source_path* to *destination_path*, both repo-relative.
    Requires expected_sha256 for the source file.
    Saves rollback information.
    """
    src_abs = _resolve_and_validate_write(repo_root, source_path)
    dst_abs = _resolve_and_validate_write(repo_root, destination_path)

    if not src_abs.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    if src_abs.is_dir():
        raise ValueError(f"Directory moves are not allowed: {source_path}")
    if src_abs.is_symlink():
        raise ValueError(f"Symlinks are not allowed: {source_path}")
    if dst_abs.exists():
        raise ValueError(f"Destination already exists: {destination_path}")

    current_sha = _sha256_file(src_abs)
    if current_sha != expected_sha256:
        raise ValueError(
            f"Stale hash for '{source_path}': "
            f"expected {expected_sha256[:12]}… got {current_sha[:12]}…"
        )

    # Ensure destination parent is inside repo
    dst_parent = dst_abs.parent
    try:
        dst_parent.relative_to(repo_root)
    except ValueError:
        raise ValueError(
            f"Destination parent is outside the repository: {destination_path}"
        )

    # Save rollback info
    mv_id = _make_patch_id().replace("_patch_", "_move_")
    mv_dir = runs_dir / MANAGED_PATCHES_DIR / mv_id
    mv_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "patch_id": mv_id,
        "operation": "move",
        "source_path": source_path,
        "destination_path": destination_path,
        "sha256_at_move": current_sha,
        "created_at": _utc_now(),
        "status": "moved",
    }
    (mv_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    dst_parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_abs), str(dst_abs))
    new_sha = _sha256_file(dst_abs)

    return {
        "ok": True,
        "repo_name": "",
        "source_path": source_path,
        "destination_path": destination_path,
        "changed_files": [source_path, destination_path],
        "sha256": new_sha,
        "rollback_id": mv_id,
        "error": "",
    }
