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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .repo_reader import (
    _is_binary,
    _resolve_and_validate,
)


# ---------------------------------------------------------------------------
# Write-specific limits
# ---------------------------------------------------------------------------
MAX_PATCH_FILES = 10
MAX_PATCH_LINES = 1_000
MAX_PATCH_BYTES = 200 * 1024  # 200 KB total content change
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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        delete=False,
        suffix=suffix,
    ) as tf:
        tf.write(data)
        tmp_path = Path(tf.name)
    try:
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


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
) -> Path:
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    patch_dir.mkdir(parents=True, exist_ok=True)
    for index, op in enumerate(operations):
        payload_text = op.get("payload_text")
        if payload_text is None:
            continue
        payload_bytes = payload_text.encode("utf-8")
        _atomic_write_bytes(
            patch_dir / _payload_file_name(index),
            payload_bytes,
            ".codexbridge_payload_tmp",
        )

    manifest = {
        "patch_id": patch_id,
        "bundle_version": 2,
        "created_at": _utc_now(),
        "repo_root": "",
        "repo_fingerprint": _repo_fingerprint(repo_root),
        "git_head_at_preview": git_head,
        "status": "preview_failed" if errors else "preview_ok",
        "operations": [],
        "errors": errors,
    }
    for index, op in enumerate(operations):
        entry = {
            "index": index,
            "action": op["action"],
            "path": op["path"],
            "current_sha256": op.get("current_sha256", ""),
            "payload_file": "",
            "payload_sha256": "",
            "changed_lines": op["changed_lines"],
            "changed_bytes": op["changed_bytes"],
        }
        payload_text = op.get("payload_text")
        if payload_text is not None:
            payload_bytes = payload_text.encode("utf-8")
            entry["payload_file"] = _payload_file_name(index)
            entry["payload_sha256"] = _sha256_bytes(payload_bytes)
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
    invalid_paths: set[str] = set()

    for idx, op in enumerate(operations):
        if not isinstance(op, dict):
            errors.append(f"op[{idx}]: operation must be an object")
            continue

        path_str = op.get("path", "")
        old_text = op.get("old_text")
        new_text = op.get("new_text")
        expected_sha = op.get("expected_sha256", "")

        if not path_str or not isinstance(path_str, str):
            errors.append(f"op[{idx}]: path is required")
            continue
        if old_text is None or not isinstance(old_text, str):
            errors.append(f"op[{idx}]: old_text is required and must be a string")
            invalid_paths.add(path_str)
            continue
        if new_text is None or not isinstance(new_text, str):
            errors.append(f"op[{idx}]: new_text is required and must be a string")
            invalid_paths.add(path_str)
            continue

        state = states.get(path_str)
        if state is None:
            try:
                absolute = _resolve_and_validate_write(repo_root, path_str)
            except ValueError as exc:
                errors.append(f"op[{idx}]: {exc}")
                invalid_paths.add(path_str)
                continue

            if not absolute.exists():
                errors.append(f"op[{idx}]: file does not exist: {path_str}")
                invalid_paths.add(path_str)
                continue
            if absolute.is_dir():
                errors.append(f"op[{idx}]: path is a directory: {path_str}")
                invalid_paths.add(path_str)
                continue
            if absolute.is_symlink():
                errors.append(f"op[{idx}]: symlinks are not allowed: {path_str}")
                invalid_paths.add(path_str)
                continue
            if _is_binary(absolute):
                errors.append(f"op[{idx}]: binary files are not supported: {path_str}")
                invalid_paths.add(path_str)
                continue

            try:
                current_bytes = absolute.read_bytes()
                current_text = current_bytes.decode("utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"op[{idx}]: cannot read file: {exc}")
                invalid_paths.add(path_str)
                continue

            state = {
                "path": path_str,
                "absolute": absolute,
                "current_bytes": current_bytes,
                "current_content": current_text,
                "current_sha256": hashlib.sha256(current_bytes).hexdigest(),
                "edits": [],
            }
            states[path_str] = state
            path_order.append(path_str)

        current_sha = state["current_sha256"]
        if expected_sha and current_sha != expected_sha:
            errors.append(
                f"op[{idx}]: stale hash for '{path_str}': "
                f"expected {expected_sha[:12]}… got {current_sha[:12]}…"
            )
            invalid_paths.add(path_str)
            continue

        current_text = state["current_content"]
        occurrences = current_text.count(old_text)
        if occurrences == 0:
            errors.append(f"op[{idx}]: old_text not found in '{path_str}'")
            invalid_paths.add(path_str)
            continue
        if occurrences > 1:
            errors.append(
                f"op[{idx}]: old_text appears {occurrences} times in '{path_str}'; "
                "must be unique"
            )
            invalid_paths.add(path_str)
            continue

        start = current_text.index(old_text)
        end = start + len(old_text)
        overlap = next(
            (
                edit
                for edit in state["edits"]
                if start < edit["end"] and edit["start"] < end
            ),
            None,
        )
        if overlap is not None:
            errors.append(
                f"op[{idx}]: edit overlaps op[{overlap['index']}] in '{path_str}'"
            )
            invalid_paths.add(path_str)
            continue

        state["edits"].append(
            {
                "index": idx,
                "start": start,
                "end": end,
                "old_text": old_text,
                "new_text": new_text,
            }
        )

    validated: list[dict] = []
    total_changed_lines = 0
    total_changed_bytes = 0
    for path_str in path_order:
        if path_str in invalid_paths:
            continue
        state = states[path_str]
        current_text = state["current_content"]
        new_content = current_text
        for edit in sorted(
            state["edits"], key=lambda item: item["start"], reverse=True
        ):
            new_content = (
                new_content[: edit["start"]]
                + edit["new_text"]
                + new_content[edit["end"] :]
            )

        diff = _unified_diff_for_op(current_text, new_content, path_str)
        changed_lines = _count_changed_lines(diff)
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
                "changed_bytes": changed_bytes,
                "operation_count": len(state["edits"]),
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
) -> dict:
    """
    Validate operations and store a preview.  Never modifies files.
    Returns patch_id, unified diff, changed files, stats, and validation errors.
    """
    patch_id = _make_patch_id()
    head = _git_head(repo_root)
    validated, errors = _validate_operations(repo_root, operations)

    combined_diff = ""
    changed_files: list[str] = []
    total_changed_lines = 0
    total_changed_bytes = 0
    bundle_operations: list[dict[str, Any]] = []

    for op in validated:
        combined_diff += op["diff"]
        changed_files.append(op["path"])
        total_changed_lines += op["changed_lines"]
        total_changed_bytes += op["changed_bytes"]
        bundle_operations.append(
            {
                "action": "modify",
                "path": op["path"],
                "current_sha256": op["current_sha256"],
                "payload_text": op["new_content"],
                "changed_lines": op["changed_lines"],
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
    )

    return {
        "ok": not bool(errors),
        "patch_id": patch_id,
        "repo_name": "",
        "diff": combined_diff,
        "changed_files": changed_files,
        "changed_lines": total_changed_lines,
        "changed_bytes": total_changed_bytes,
        "git_head": head,
        "validation_errors": errors,
        "error": "; ".join(errors) if errors else "",
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
        raise ValueError(f"Patch {patch_id} has already been applied")
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
    rollback_files: dict[str, str] = {}
    for op in validated:
        rollback_name = _legacy_rollback_file_name(op["path"])
        rollback_files[op["path"]] = rollback_name
        rollback_file = rollback_dir / rollback_name
        rollback_file.write_bytes(op["current_content"].encode("utf-8"))

    # Write all files atomically (temp → rename)
    written: list[dict] = []
    try:
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
    except Exception as exc:
        # Attempt to rollback already-written files
        for w in written:
            rollback_content_path = rollback_dir / (
                w["path"].replace("/", "__").replace("\\", "__")
            )
            if rollback_content_path.exists():
                try:
                    abs_p = repo_root / w["path"]
                    abs_p.write_bytes(rollback_content_path.read_bytes())
                except Exception:
                    pass
        raise RuntimeError(f"Apply failed (partial rollback attempted): {exc}") from exc

    # Update manifest
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

    return {
        "ok": True,
        "patch_id": patch_id,
        "repo_name": "",
        "changed_files": [w["path"] for w in written],
        "results": written,
        "git_head": current_head,
        "error": "",
    }


def apply_previewed_repo_change(repo_root: Path, patch_id: str, runs_dir: Path) -> dict:
    patch_dir = _resolve_managed_patch_dir(runs_dir, patch_id)
    if not patch_dir.exists():
        raise ValueError(f"Unknown patch_id: {patch_id}")

    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    status = manifest.get("status")
    if status == "applied":
        raise ValueError(f"Patch {patch_id} has already been applied")
    if status == "reverted":
        raise ValueError(f"Patch {patch_id} has been reverted")
    if status == "preview_failed":
        raise ValueError(
            f"Patch {patch_id} preview had validation errors; cannot apply"
        )
    if manifest.get("bundle_version") != 2:
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
            payload_file = op.get("payload_file", "")
            payload_sha = _preview_payload_sha(op)
            if not payload_file or not payload_sha:
                raise ValueError(
                    f"Patch {patch_id} is missing opaque payload metadata for '{path_str}'"
                )
            payload_path = _resolve_bundle_file(
                patch_dir,
                payload_file,
                _payload_file_name(index),
                kind="payload",
            )
            payload_bytes = payload_path.read_bytes()
            if _sha256_bytes(payload_bytes) != payload_sha:
                raise ValueError(
                    f"Patch {patch_id} payload verification failed for '{path_str}'"
                )
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
            payload_file = op.get("payload_file", "")
            payload_sha = _preview_payload_sha(op)
            if not payload_file or not payload_sha:
                raise ValueError(
                    f"Patch {patch_id} is missing opaque payload metadata for '{path_str}'"
                )
            payload_path = _resolve_bundle_file(
                patch_dir,
                payload_file,
                _payload_file_name(index),
                kind="payload",
            )
            payload_bytes = payload_path.read_bytes()
            if _sha256_bytes(payload_bytes) != payload_sha:
                raise ValueError(
                    f"Patch {patch_id} payload verification failed for '{path_str}'"
                )
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

    rollback_dir = patch_dir / "rollback"
    rollback_dir.mkdir(exist_ok=True)
    applied_results: list[dict[str, Any]] = []
    try:
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
        try:
            _rollback_applied_preview_ops(repo_root, rollback_dir, applied_results)
        except Exception:
            pass
        raise RuntimeError(f"Apply failed (partial rollback attempted): {exc}") from exc

    return {
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
    }


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
        "sha256": new_sha,
        "rollback_id": mv_id,
        "error": "",
    }
