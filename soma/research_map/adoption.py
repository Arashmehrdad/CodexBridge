from __future__ import annotations

import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

from .manifest import MANIFEST_FILENAME, ManifestState, load_project_manifest
from .models import ProjectManifest, ResearchMapConfig, ResearchRootConfig

RESEARCH_MAP_ACTION_GATEWAY_VERSION = "soma.research-map.action.v1"
RESEARCH_MAP_RUNTIME_PATH = ".soma/research-map"
RESEARCH_MAP_GENERATIONS_PATH = ".soma/research-map/generations"
LOCAL_GIT_EXCLUDE_RULE = "/.soma/"


class ResearchMapAdoptionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _new_repository_uid() -> str:
    return f"srepo_{secrets.token_hex(16)}"


def _normalized_roots(roots: list[dict[str, Any]]) -> tuple[ResearchRootConfig, ...]:
    try:
        config = ResearchMapConfig(roots=[ResearchRootConfig.model_validate(item) for item in roots])
    except (TypeError, ValueError) as exc:
        raise ResearchMapAdoptionError("invalid_roots", str(exc)) from exc
    return tuple(sorted(config.roots, key=lambda item: item.path))


def _roots_payload(roots: tuple[ResearchRootConfig, ...]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json", exclude_none=True) for item in roots]


def _manifest_bytes(manifest: ProjectManifest) -> bytes:
    payload = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _publish_manifest_no_replace(path: Path, content: bytes) -> None:
    """Publish a complete manifest atomically while refusing to replace an existing one."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ResearchMapAdoptionError(
                "manifest_already_exists",
                "soma.project.json appeared during adoption; retry against the existing manifest",
            ) from exc
        except OSError as exc:
            raise ResearchMapAdoptionError("manifest_publish_failed", str(exc)) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _git_exclude_path(repository_root: Path) -> Path:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ResearchMapAdoptionError("git_exclude_unavailable", str(exc)) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git rev-parse failed"
        raise ResearchMapAdoptionError("git_exclude_unavailable", detail)
    raw = completed.stdout.strip()
    if not raw:
        raise ResearchMapAdoptionError("git_exclude_unavailable", "git returned an empty exclude path")
    path = Path(raw)
    return path if path.is_absolute() else repository_root / path


def _ensure_local_git_exclude(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_bytes() if path.exists() else b""
    if any(line.strip() == LOCAL_GIT_EXCLUDE_RULE.encode("ascii") for line in existing.splitlines()):
        return False
    suffix = b"" if not existing or existing.endswith((b"\n", b"\r")) else b"\n"
    with path.open("ab") as handle:
        handle.write(suffix + LOCAL_GIT_EXCLUDE_RULE.encode("ascii") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return True


def _initialize_runtime(repository_root: Path) -> bool:
    runtime_root = repository_root / RESEARCH_MAP_RUNTIME_PATH
    generations = repository_root / RESEARCH_MAP_GENERATIONS_PATH
    changed = not runtime_root.is_dir() or not generations.is_dir()
    generations.mkdir(parents=True, exist_ok=True)
    return changed


def _database_state(repository_root: Path) -> str:
    current = repository_root / RESEARCH_MAP_RUNTIME_PATH / "CURRENT.json"
    return "stale_unverified" if current.is_file() else "missing"


def adopt_research_map(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    roots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Explicitly adopt or attach one exact repository without semantic side effects."""
    root = Path(repository_root).resolve()
    manifest_result = load_project_manifest(root)
    requested_roots = _normalized_roots(roots) if roots else ()

    manifest_created = False
    if manifest_result.state is ManifestState.MISSING:
        if not requested_roots:
            raise ResearchMapAdoptionError(
                "roots_required",
                "first research-map adoption requires at least one explicit research root",
            )
        manifest = ProjectManifest(
            repository_uid=_new_repository_uid(),
            research_map=ResearchMapConfig(roots=list(requested_roots)),
        )
        existing_roots = requested_roots
        action_status = "adopted"
    elif manifest_result.state is ManifestState.MALFORMED or manifest_result.manifest is None:
        raise ResearchMapAdoptionError(
            manifest_result.error_code or "manifest_malformed",
            "existing soma.project.json is malformed; adoption refuses to repair or replace it",
        )
    else:
        manifest = manifest_result.manifest
        existing_roots = tuple(sorted(manifest.research_map.roots, key=lambda item: item.path))
        if requested_roots and _roots_payload(requested_roots) != _roots_payload(existing_roots):
            raise ResearchMapAdoptionError(
                "root_conflict",
                "requested research roots conflict with the existing portable manifest",
            )
        action_status = "attached"

    exclude_path = _git_exclude_path(root)
    if manifest_result.state is ManifestState.MISSING:
        _publish_manifest_no_replace(root / MANIFEST_FILENAME, _manifest_bytes(manifest))
        manifest_created = True

    exclude_changed = _ensure_local_git_exclude(exclude_path)
    runtime_initialized = _initialize_runtime(root)
    database_state = _database_state(root)

    return {
        "ok": True,
        "action": "adopt",
        "status": action_status,
        "project_id": project_id,
        "repo_name": repo_name,
        "repository_uid": manifest.repository_uid,
        "manifest_state": "created" if manifest_created else "existing",
        "manifest_created": manifest_created,
        "research_map_enabled": manifest.research_map.enabled,
        "roots": _roots_payload(existing_roots),
        "git_exclude_rule": LOCAL_GIT_EXCLUDE_RULE,
        "git_exclude_changed": exclude_changed,
        "runtime_path": RESEARCH_MAP_RUNTIME_PATH,
        "runtime_initialized": runtime_initialized,
        "database_state": database_state,
        "sync_state": "not_initialized" if database_state == "missing" else "stale",
        "backend_state": "unavailable",
        "sidecars_generated": False,
        "index_built": False,
        "gateway_version": RESEARCH_MAP_ACTION_GATEWAY_VERSION,
        "error": "",
    }
