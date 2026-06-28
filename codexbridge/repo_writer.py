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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .repo_reader import (
    _path_is_allowed,
    _is_binary,
    _resolve_and_validate,
    _posix_relative,
    MAX_FILE_BYTES,
)
from .safety import validate_repo_relative_path


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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        lineterm="",
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


# ---------------------------------------------------------------------------
# Patch validation (shared by preview and apply)
# ---------------------------------------------------------------------------


def _validate_operations(
    repo_root: Path,
    operations: list[dict],
    *,
    for_apply: bool = False,
) -> tuple[list[dict], list[str]]:
    """
    Validate a list of patch operations.

    Returns (validated_ops, errors).
    validated_ops contains enriched dicts with resolved paths and computed
    diff strings.
    errors is a list of human-readable problem strings.
    """
    errors: list[str] = []

    if not operations or not isinstance(operations, list):
        return [], ["operations must be a non-empty list"]

    if len(operations) > MAX_PATCH_FILES:
        errors.append(
            f"Patch exceeds {MAX_PATCH_FILES} file limit ({len(operations)} ops)"
        )

    seen_paths: set[str] = set()
    validated: list[dict] = []
    total_changed_lines = 0
    total_changed_bytes = 0

    for idx, op in enumerate(operations):
        op_errors: list[str] = []
        path_str = op.get("path", "")
        old_text = op.get("old_text")
        new_text = op.get("new_text")
        expected_sha = op.get("expected_sha256", "")

        # Path checks
        if not path_str:
            errors.append(f"op[{idx}]: path is required")
            continue
        if path_str in seen_paths:
            errors.append(f"op[{idx}]: duplicate path '{path_str}'")
            continue
        seen_paths.add(path_str)

        try:
            absolute = _resolve_and_validate_write(repo_root, path_str)
        except ValueError as exc:
            errors.append(f"op[{idx}]: {exc}")
            continue

        # old_text / new_text checks
        if old_text is None or not isinstance(old_text, str):
            op_errors.append(f"op[{idx}]: old_text is required and must be a string")
        if new_text is None or not isinstance(new_text, str):
            op_errors.append(f"op[{idx}]: new_text is required and must be a string")

        if op_errors:
            errors.extend(op_errors)
            continue

        # File must exist for patch (not for create)
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

        # Read current content
        try:
            current_bytes = absolute.read_bytes()
            current_text = current_bytes.decode("utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"op[{idx}]: cannot read file: {exc}")
            continue

        # Hash check
        current_sha = hashlib.sha256(current_bytes).hexdigest()
        if expected_sha and current_sha != expected_sha:
            errors.append(
                f"op[{idx}]: stale hash for '{path_str}': "
                f"expected {expected_sha[:12]}… got {current_sha[:12]}…"
            )
            continue

        # old_text must appear exactly once
        occurrences = current_text.count(old_text)  # type: ignore[arg-type]
        if occurrences == 0:
            errors.append(f"op[{idx}]: old_text not found in '{path_str}'")
            continue
        if occurrences > 1:
            errors.append(
                f"op[{idx}]: old_text appears {occurrences} times in '{path_str}'; "
                "must be unique"
            )
            continue

        # Build new content and diff
        new_content = current_text.replace(old_text, new_text, 1)  # type: ignore[arg-type]
        diff = _unified_diff_for_op(current_text, new_content, path_str)
        changed_lines = _count_changed_lines(diff)
        changed_bytes = abs(len(new_content.encode("utf-8")) - len(current_bytes))

        total_changed_lines += changed_lines
        total_changed_bytes += changed_bytes

        validated.append(
            {
                "path": path_str,
                "absolute": absolute,
                "current_sha256": current_sha,
                "current_content": current_text,
                "old_text": old_text,
                "new_text": new_text,
                "new_content": new_content,
                "diff": diff,
                "changed_lines": changed_lines,
                "changed_bytes": changed_bytes,
            }
        )

    if total_changed_lines > MAX_PATCH_LINES:
        errors.append(
            f"Patch exceeds {MAX_PATCH_LINES} changed-line limit ({total_changed_lines} lines)"
        )
    if total_changed_bytes > MAX_PATCH_BYTES:
        errors.append(f"Patch exceeds {MAX_PATCH_BYTES // 1024} KB changed-byte limit")

    return validated, errors


# ---------------------------------------------------------------------------
# preview_repo_patch
# ---------------------------------------------------------------------------


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

    for op in validated:
        combined_diff += op["diff"]
        changed_files.append(op["path"])
        total_changed_lines += op["changed_lines"]
        total_changed_bytes += op["changed_bytes"]

    # Always store the preview (even if there are errors) so the patch_id is
    # discoverable, but mark it invalid when errors are present.
    patch_dir = runs_dir / MANAGED_PATCHES_DIR / patch_id
    patch_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "patch_id": patch_id,
        "created_at": _utc_now(),
        "repo_root": "",  # never store the absolute root
        "git_head_at_preview": head,
        "status": "preview_failed" if errors else "preview_ok",
        "operations": [
            {
                "path": op["path"],
                "current_sha256": op["current_sha256"],
                "new_content_sha256": _sha256_text(op["new_content"]),
                "changed_lines": op["changed_lines"],
                "changed_bytes": op["changed_bytes"],
            }
            for op in validated
        ],
        "errors": errors,
    }
    (patch_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    if combined_diff:
        (patch_dir / "preview.diff").write_text(combined_diff, encoding="utf-8")

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
    patch_dir = runs_dir / MANAGED_PATCHES_DIR / patch_id
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

    # Save originals for rollback
    rollback_dir = patch_dir / "rollback"
    rollback_dir.mkdir(exist_ok=True)
    for op in validated:
        rollback_file = rollback_dir / (
            op["path"].replace("/", "__").replace("\\", "__")
        )
        rollback_file.write_bytes(op["current_content"].encode("utf-8"))

    # Write all files atomically (temp → rename)
    written: list[dict] = []
    try:
        for op in validated:
            absolute: Path = op["absolute"]
            new_content: str = op["new_content"]
            # Write to temp file in same directory, then atomically replace
            parent = absolute.parent
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=parent,
                delete=False,
                suffix=".codexbridge_tmp",
            ) as tf:
                tf.write(new_content)
                tmp_path = Path(tf.name)
            os.replace(tmp_path, absolute)
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
    manifest["applied_results"] = written
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


# ---------------------------------------------------------------------------
# revert_managed_patch
# ---------------------------------------------------------------------------


def revert_managed_patch(repo_root: Path, patch_id: str, runs_dir: Path) -> dict:
    """
    Revert a previously applied managed patch using saved rollback content.
    Verifies current hashes match applied-result hashes before reverting.
    Never uses git reset, git checkout, or shell commands.
    """
    patch_dir = runs_dir / MANAGED_PATCHES_DIR / patch_id
    if not patch_dir.exists():
        raise ValueError(f"Unknown patch_id: {patch_id}")

    manifest_path = patch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("status") != "applied":
        raise ValueError(
            f"Patch {patch_id} is not in 'applied' state (status: {manifest.get('status')})"
        )

    applied_results = {
        r["path"]: r["sha256"] for r in manifest.get("applied_results", [])
    }
    rollback_dir = patch_dir / "rollback"

    # Verify current hashes match applied hashes before reverting
    for path_str, expected_sha in applied_results.items():
        absolute = repo_root / path_str
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
        for path_str in applied_results:
            absolute = repo_root / path_str
            rollback_file = rollback_dir / (
                path_str.replace("/", "__").replace("\\", "__")
            )
            if not rollback_file.exists():
                raise ValueError(f"Rollback content missing for '{path_str}'")
            original = rollback_file.read_bytes()
            parent = absolute.parent
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=parent,
                delete=False,
                suffix=".codexbridge_revert_tmp",
            ) as tf:
                tf.write(original)
                tmp_path = Path(tf.name)
            os.replace(tmp_path, absolute)
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
    absolute = _resolve_and_validate_write(repo_root, path)

    if absolute.exists():
        raise ValueError(f"File already exists: {path}")

    # Ensure parent is inside the repo
    parent = absolute.parent
    try:
        parent.relative_to(repo_root)
    except ValueError:
        raise ValueError(f"Parent directory is outside the repository: {path}")

    if len(content.encode("utf-8")) > MAX_CREATE_BYTES:
        raise ValueError(
            f"Content exceeds {MAX_CREATE_BYTES // 1024} KB limit for create_repo_file"
        )

    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=parent,
        delete=False,
        suffix=".codexbridge_create_tmp",
    ) as tf:
        tf.write(content)
        tmp_path = Path(tf.name)
    os.replace(tmp_path, absolute)
    sha = _sha256_file(absolute)

    return {
        "ok": True,
        "repo_name": "",
        "path": path,
        "sha256": sha,
        "size_bytes": len(content.encode("utf-8")),
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
    absolute = _resolve_and_validate_write(repo_root, path)

    if not absolute.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if absolute.is_dir():
        raise ValueError(f"Directory deletion is not allowed: {path}")
    if absolute.is_symlink():
        raise ValueError(f"Symlinks are not allowed: {path}")

    current_sha = _sha256_file(absolute)
    if current_sha != expected_sha256:
        raise ValueError(
            f"Stale hash for '{path}': "
            f"expected {expected_sha256[:12]}… got {current_sha[:12]}…"
        )

    # Save rollback copy
    del_id = _make_patch_id().replace("_patch_", "_delete_")
    del_dir = runs_dir / MANAGED_PATCHES_DIR / del_id
    del_dir.mkdir(parents=True, exist_ok=True)
    rollback_file = del_dir / "original_content.txt"
    rollback_file.write_bytes(absolute.read_bytes())
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
