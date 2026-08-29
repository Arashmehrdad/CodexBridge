from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from .backend import BackendProjection
from .canonical import canonical_json_bytes, canonical_json_sha256

RUNTIME_RELATIVE_PATH = Path(".soma/research-map")
GENERATIONS_DIRNAME = "generations"
CURRENT_FILENAME = "CURRENT.json"
SYNC_LOCK_FILENAME = ".sync.lock"
DESIRED_FILENAME = "DESIRED.json"
RELATIONS_FILENAME = "RELATIONS.json"
HEALTH_FILENAME = "HEALTH.json"
CURRENT_SCHEMA = "soma.research-map.current.v1"
GENERATION_SCHEMA = "soma.research-map.generation.v1"
HEALTH_SCHEMA = "soma.research-map.generation-health.v1"
LEGACY_STORAGE_MODE = "generation_database_v1"
VERSIONED_STORAGE_MODE = "versioned_repository_database_v2"
_STORAGE_MODES = {LEGACY_STORAGE_MODE, VERSIONED_STORAGE_MODE}
_GENERATION_RE = re.compile(r"^gen_[0-9]{8}T[0-9]{12}Z_[0-9a-f]{12}_[0-9a-f]{8}$")
_DATABASE_RE = re.compile(r"^srm_[0-9a-f]{32}$")
_REPOSITORY_UID_RE = re.compile(r"^srepo_[0-9a-f]{16,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ResearchMapGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CurrentGeneration:
    generation: str
    database: str
    repository_uid: str
    semantic_desired_state_sha256: str
    projection_contract_sha256: str
    relation_count: int
    desired_sha256: str
    relations_sha256: str
    health_sha256: str
    storage_mode: str = LEGACY_STORAGE_MODE


def _try_lock_handle(handle: Any) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise ResearchMapGenerationError(
            "research-map sync writer lock is already held"
        ) from exc


def _unlock_handle(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class SyncWriterLock:
    """One crash-safe OS advisory lock for Research Map sync publication.

    The lock file is intentionally persistent. Kernel lock ownership, not file
    existence, determines exclusivity, so a hard-killed process cannot wedge
    future syncs with an orphan lock pathname.
    """

    def __init__(self, repository_root: str | Path) -> None:
        self.path = Path(repository_root).resolve() / RUNTIME_RELATIVE_PATH / SYNC_LOCK_FILENAME
        self._handle: Any | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            _try_lock_handle(handle)
            payload = {
                "schema": "soma.research-map.sync-lock.v1",
                "pid": os.getpid(),
                "created_at": datetime.now(UTC).isoformat(),
            }
            handle.seek(0)
            handle.truncate()
            handle.write(_json_file_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            handle.close()
            raise
        self._handle = handle
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            _unlock_handle(handle)
        finally:
            handle.close()


def _json_file_bytes(payload: object) -> bytes:
    return canonical_json_bytes(payload) + b"\n"


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_new(path: Path, payload: object) -> str:
    content = _json_file_bytes(payload)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(content).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchMapGenerationError(f"invalid research-map runtime JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ResearchMapGenerationError(f"research-map runtime JSON must be an object: {path.name}")
    return payload


def new_generation_id(
    semantic_desired_state_sha256: str,
    projection_contract_sha256: str,
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    identity = canonical_json_sha256(
        {
            "semantic_desired_state_sha256": semantic_desired_state_sha256,
            "projection_contract_sha256": projection_contract_sha256,
        }
    )[:12]
    return f"gen_{timestamp}_{identity}_{secrets.token_hex(4)}"


def generation_database_name(repository_uid: str, generation: str) -> str:
    digest = hashlib.sha256(f"{repository_uid}:{generation}".encode()).hexdigest()[:32]
    return f"srm_{digest}"


def generation_directory(repository_root: str | Path, generation: str) -> Path:
    return Path(repository_root).resolve() / RUNTIME_RELATIVE_PATH / GENERATIONS_DIRNAME / generation


def create_generation_directory(repository_root: str | Path, generation: str) -> Path:
    directory = generation_directory(repository_root, generation)
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise ResearchMapGenerationError(f"generation already exists: {generation}") from exc
    return directory


def desired_artifact_payload(
    *,
    repository_uid: str,
    semantic_desired_state_sha256: str,
    projection_contract_sha256: str,
    desired_payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": GENERATION_SCHEMA,
        "repository_uid": repository_uid,
        "semantic_desired_state_sha256": semantic_desired_state_sha256,
        "projection_contract_sha256": projection_contract_sha256,
        "desired_state": desired_payload,
    }


def relations_artifact_payload(
    *,
    projection: BackendProjection,
    projection_contract_sha256: str,
    database: str,
    storage_mode: str = LEGACY_STORAGE_MODE,
) -> dict[str, object]:
    if storage_mode not in _STORAGE_MODES:
        raise ResearchMapGenerationError("invalid research-map storage mode")
    return {
        "schema": GENERATION_SCHEMA,
        "repository_uid": projection.repository_uid,
        "semantic_desired_state_sha256": projection.semantic_desired_state_sha256,
        "projection_contract_sha256": projection_contract_sha256,
        "database": database,
        "storage_mode": storage_mode,
        "nodes": [asdict(item) for item in projection.nodes],
        "relations": [asdict(item) for item in projection.relations],
    }


def write_generation_inputs(
    directory: Path,
    *,
    desired_payload: dict[str, object],
    relations_payload: dict[str, object],
) -> tuple[str, str]:
    desired_sha256 = _write_new(directory / DESIRED_FILENAME, desired_payload)
    relations_sha256 = _write_new(directory / RELATIONS_FILENAME, relations_payload)
    return desired_sha256, relations_sha256


def write_generation_health(directory: Path, payload: dict[str, object]) -> str:
    return _write_new(directory / HEALTH_FILENAME, payload)


def publish_current(repository_root: str | Path, payload: dict[str, object]) -> None:
    root = Path(repository_root).resolve() / RUNTIME_RELATIVE_PATH
    _atomic_replace(root / CURRENT_FILENAME, _json_file_bytes(payload))


def current_payload(
    *,
    generation: str,
    database: str,
    repository_uid: str,
    semantic_desired_state_sha256: str,
    projection_contract_sha256: str,
    relation_count: int,
    desired_sha256: str,
    relations_sha256: str,
    health_sha256: str,
    storage_mode: str = LEGACY_STORAGE_MODE,
) -> dict[str, object]:
    if storage_mode not in _STORAGE_MODES:
        raise ResearchMapGenerationError("invalid research-map storage mode")
    return {
        "schema": CURRENT_SCHEMA,
        "generation": generation,
        "database": database,
        "repository_uid": repository_uid,
        "semantic_desired_state_sha256": semantic_desired_state_sha256,
        "projection_contract_sha256": projection_contract_sha256,
        "relation_count": relation_count,
        "desired_sha256": desired_sha256,
        "relations_sha256": relations_sha256,
        "health_sha256": health_sha256,
        "storage_mode": storage_mode,
    }


def health_payload(
    *,
    generation: str,
    database: str,
    repository_uid: str,
    semantic_desired_state_sha256: str,
    projection_contract_sha256: str,
    expected_relation_ids: tuple[str, ...],
    actual_relation_ids: tuple[str, ...],
    persisted: bool,
    reopen_verified: bool,
    storage_mode: str = LEGACY_STORAGE_MODE,
) -> dict[str, object]:
    if storage_mode not in _STORAGE_MODES:
        raise ResearchMapGenerationError("invalid research-map storage mode")
    return {
        "schema": HEALTH_SCHEMA,
        "status": "verified" if persisted and reopen_verified and expected_relation_ids == actual_relation_ids else "degraded",
        "generation": generation,
        "database": database,
        "repository_uid": repository_uid,
        "semantic_desired_state_sha256": semantic_desired_state_sha256,
        "projection_contract_sha256": projection_contract_sha256,
        "storage_mode": storage_mode,
        "relation_count": len(expected_relation_ids),
        "expected_relation_ids": list(expected_relation_ids),
        "actual_relation_ids": list(actual_relation_ids),
        "persisted": persisted,
        "reopen_verified": reopen_verified,
    }


def load_current_generation(repository_root: str | Path) -> CurrentGeneration | None:
    root = Path(repository_root).resolve() / RUNTIME_RELATIVE_PATH
    current_path = root / CURRENT_FILENAME
    if not current_path.is_file():
        return None
    payload = _read_json(current_path)
    required = {
        "schema": CURRENT_SCHEMA,
        "generation": str,
        "database": str,
        "repository_uid": str,
        "semantic_desired_state_sha256": str,
        "projection_contract_sha256": str,
        "relation_count": int,
        "desired_sha256": str,
        "relations_sha256": str,
        "health_sha256": str,
    }
    for key, expected in required.items():
        value = payload.get(key)
        if key == "schema":
            if value != expected:
                raise ResearchMapGenerationError("unsupported CURRENT.json schema")
            continue
        if isinstance(value, bool) or not isinstance(value, expected):
            raise ResearchMapGenerationError(f"invalid CURRENT.json field: {key}")
    if not _GENERATION_RE.fullmatch(payload["generation"]):
        raise ResearchMapGenerationError("invalid CURRENT.json generation identity")
    if not _DATABASE_RE.fullmatch(payload["database"]):
        raise ResearchMapGenerationError("invalid CURRENT.json database identity")
    if not _REPOSITORY_UID_RE.fullmatch(payload["repository_uid"]):
        raise ResearchMapGenerationError("invalid CURRENT.json repository identity")
    for key in (
        "semantic_desired_state_sha256",
        "projection_contract_sha256",
        "desired_sha256",
        "relations_sha256",
        "health_sha256",
    ):
        if not _SHA256_RE.fullmatch(payload[key]):
            raise ResearchMapGenerationError(f"invalid CURRENT.json hash field: {key}")
    if payload["relation_count"] < 0:
        raise ResearchMapGenerationError("invalid CURRENT.json relation_count")
    storage_mode = payload.get("storage_mode", LEGACY_STORAGE_MODE)
    if not isinstance(storage_mode, str) or storage_mode not in _STORAGE_MODES:
        raise ResearchMapGenerationError("invalid CURRENT.json storage_mode")

    current = CurrentGeneration(
        generation=payload["generation"],
        database=payload["database"],
        repository_uid=payload["repository_uid"],
        semantic_desired_state_sha256=payload["semantic_desired_state_sha256"],
        projection_contract_sha256=payload["projection_contract_sha256"],
        relation_count=payload["relation_count"],
        desired_sha256=payload["desired_sha256"],
        relations_sha256=payload["relations_sha256"],
        health_sha256=payload["health_sha256"],
        storage_mode=storage_mode,
    )
    directory = generation_directory(repository_root, current.generation)
    artifacts = {
        DESIRED_FILENAME: current.desired_sha256,
        RELATIONS_FILENAME: current.relations_sha256,
        HEALTH_FILENAME: current.health_sha256,
    }
    for filename, expected_sha256 in artifacts.items():
        path = directory / filename
        if not path.is_file():
            raise ResearchMapGenerationError(f"published generation artifact is missing: {filename}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise ResearchMapGenerationError(f"published generation artifact hash mismatch: {filename}")
    health = _read_json(directory / HEALTH_FILENAME)
    if health.get("status") != "verified" or health.get("reopen_verified") is not True:
        raise ResearchMapGenerationError("published generation health is not verified")
    expected_health = {
        "generation": current.generation,
        "database": current.database,
        "repository_uid": current.repository_uid,
        "semantic_desired_state_sha256": current.semantic_desired_state_sha256,
        "projection_contract_sha256": current.projection_contract_sha256,
        "relation_count": current.relation_count,
    }
    for key, expected in expected_health.items():
        if health.get(key) != expected:
            raise ResearchMapGenerationError(
                f"published generation health metadata mismatch: {key}"
            )
    health_storage_mode = health.get("storage_mode", LEGACY_STORAGE_MODE)
    if health_storage_mode != current.storage_mode:
        raise ResearchMapGenerationError(
            "published generation health metadata mismatch: storage_mode"
        )
    return current
