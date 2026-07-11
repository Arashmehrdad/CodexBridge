from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


MANAGED_ARTIFACT_ROOTS: tuple[str, ...] = (
    ".codex-tmp",
    ".pytest_cache",
    ".ruff_cache",
    "tests/pytest_tmp_probe",
)
CLEANUP_ID_RE = re.compile(r"^\d{8}T\d{6}Z_cleanup_[0-9a-f]{8}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_cleanup_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_cleanup_{uuid4().hex[:8]}"


def _repo_fingerprint(repo_root: Path) -> str:
    normalized = os.path.normcase(os.path.normpath(str(repo_root.resolve())))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_allowed_roots(
    repo_root: Path, roots: Iterable[str] | None = None
) -> list[tuple[str, Path]]:
    requested = list(roots or MANAGED_ARTIFACT_ROOTS)
    unknown = sorted(set(requested) - set(MANAGED_ARTIFACT_ROOTS))
    if unknown:
        raise ValueError(f"Unsupported managed artifact roots: {unknown}")
    resolved: list[tuple[str, Path]] = []
    root = repo_root.resolve()
    for relative in requested:
        absolute = (root / relative).resolve()
        absolute.relative_to(root)
        resolved.append((relative, absolute))
    return resolved


def snapshot_managed_artifacts(repo_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    root = repo_root.resolve()
    for _, managed_root in _resolve_allowed_roots(root):
        if not managed_root.exists():
            continue
        for path in managed_root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(root).as_posix()
                snapshot[relative] = _sha256_file(path)
    return snapshot


def cleanup_new_managed_artifacts(repo_root: Path, before: dict[str, str]) -> list[str]:
    root = repo_root.resolve()
    after = snapshot_managed_artifacts(root)
    introduced = sorted(path for path in after if path not in before)
    removed: list[str] = []
    for relative in introduced:
        absolute = (root / relative).resolve()
        absolute.relative_to(root)
        if absolute.exists() and absolute.is_file() and not absolute.is_symlink():
            absolute.unlink()
            removed.append(relative)
    _remove_empty_managed_directories(root)
    return removed


def _remove_empty_managed_directories(repo_root: Path) -> None:
    for _, managed_root in _resolve_allowed_roots(repo_root):
        if not managed_root.exists():
            continue
        directories = sorted(
            (path for path in managed_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            managed_root.rmdir()
        except OSError:
            pass


def _manifest_path(runs_dir: Path, cleanup_id: str) -> Path:
    if not CLEANUP_ID_RE.fullmatch(cleanup_id):
        raise ValueError(f"Invalid cleanup_id: {cleanup_id}")
    root = (runs_dir / "managed_cleanups").resolve()
    path = (root / f"{cleanup_id}.json").resolve()
    path.relative_to(root)
    return path


def preview_managed_artifact_cleanup(
    repo_root: Path,
    runs_dir: Path,
    roots: Iterable[str] | None = None,
) -> dict[str, Any]:
    cleanup_id = _make_cleanup_id()
    root = repo_root.resolve()
    artifacts: list[dict[str, Any]] = []
    for _, managed_root in _resolve_allowed_roots(root, roots):
        if not managed_root.exists():
            continue
        for path in sorted(managed_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            artifacts.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": _sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    manifest = {
        "cleanup_id": cleanup_id,
        "repo_fingerprint": _repo_fingerprint(root),
        "created_at": _utc_now(),
        "status": "previewed",
        "roots": list(roots or MANAGED_ARTIFACT_ROOTS),
        "artifacts": artifacts,
        "result": {},
    }
    path = _manifest_path(runs_dir, cleanup_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "cleanup_id": cleanup_id,
        "status": "previewed",
        "artifacts": artifacts,
        "file_count": len(artifacts),
        "total_bytes": sum(item["size_bytes"] for item in artifacts),
        "error": "",
    }


def apply_managed_artifact_cleanup(
    repo_root: Path, runs_dir: Path, cleanup_id: str
) -> dict[str, Any]:
    path = _manifest_path(runs_dir, cleanup_id)
    if not path.exists():
        raise ValueError(f"Unknown cleanup_id: {cleanup_id}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("repo_fingerprint") != _repo_fingerprint(repo_root):
        raise ValueError("Cleanup preview belongs to a different repository")
    if manifest.get("status") == "applied":
        result = dict(manifest.get("result") or {})
        result["idempotent_replay"] = True
        return result
    if manifest.get("status") != "previewed":
        raise ValueError(
            f"Cleanup {cleanup_id} is not applicable from status {manifest.get('status')}"
        )

    root = repo_root.resolve()
    removed: list[str] = []
    missing: list[str] = []
    for artifact in manifest.get("artifacts", []):
        relative = str(artifact["path"])
        allowed = any(
            relative == managed_root or relative.startswith(f"{managed_root}/")
            for managed_root in MANAGED_ARTIFACT_ROOTS
        )
        if not allowed:
            raise ValueError(f"Cleanup manifest contains an unmanaged path: {relative}")
        absolute = (root / relative).resolve()
        absolute.relative_to(root)
        if not absolute.exists():
            missing.append(relative)
            continue
        if not absolute.is_file() or absolute.is_symlink():
            raise ValueError(f"Managed artifact is not a regular file: {relative}")
        current_sha = _sha256_file(absolute)
        if current_sha != artifact["sha256"]:
            raise ValueError(f"Managed artifact changed since preview: {relative}")
        absolute.unlink()
        removed.append(relative)
    _remove_empty_managed_directories(root)
    result = {
        "ok": True,
        "cleanup_id": cleanup_id,
        "status": "applied",
        "removed_files": removed,
        "missing_files": missing,
        "idempotent_replay": False,
        "error": "",
    }
    manifest["status"] = "applied"
    manifest["applied_at"] = _utc_now()
    manifest["result"] = result
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return result
