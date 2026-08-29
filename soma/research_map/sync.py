from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Literal

from .backend import (
    BackendProjection,
    ResearchMapBackend,
    ResearchMapBackendError,
    build_backend_projection,
)
from .embedding_cache import EMBEDDING_CACHE_FILENAME
from .generation import (
    HEALTH_FILENAME,
    RUNTIME_RELATIVE_PATH,
    VERSIONED_STORAGE_MODE,
    CurrentGeneration,
    ResearchMapGenerationError,
    SyncWriterLock,
    create_generation_directory,
    current_payload,
    desired_artifact_payload,
    generation_database_name,
    generation_directory,
    health_payload,
    load_current_generation,
    new_generation_id,
    publish_current,
    relations_artifact_payload,
    write_generation_health,
    write_generation_inputs,
)
from .graphiti_backend import (
    EMBEDDING_CACHE_NAMESPACE,
    LEGACY_V1_PROJECTION_SHA256,
    GraphitiFalkorBackend,
    graphiti_projection_contract_sha256,
)
from .manifest import load_project_manifest
from .service import ResearchMapHealthState, scan_research_map
from .versioned_sync import build_versioned_generation, verify_versioned_current

RESEARCH_MAP_SYNC_VERSION = "soma.research-map.sync.v2"
RESEARCH_MAP_SYNC_TIMEOUT_SECONDS = 900.0
RESEARCH_MAP_REBUILD_TIMEOUT_SECONDS = 1800.0
_FAILURE_POINTS = {
    "before_staging_creation",
    "after_staging_creation",
    "mid_relation_writes",
    "after_read_back",
    "before_save",
    "after_save",
    "before_current_publish",
    "after_current_publish",
}


class ResearchMapSyncError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ResearchMapInjectedFailure(ResearchMapSyncError):
    pass


BackendFactory = Callable[[str, str], ResearchMapBackend]


def _default_backend_factory(
    repository_root: Path,
    projection_contract_sha256: str,
) -> BackendFactory:
    del projection_contract_sha256
    cache_path = repository_root / RUNTIME_RELATIVE_PATH / EMBEDDING_CACHE_FILENAME

    def factory(repository_uid: str, database: str) -> ResearchMapBackend:
        return GraphitiFalkorBackend(
            repository_uid=repository_uid,
            database=database,
            embedding_cache_path=cache_path,
            embedding_cache_namespace=EMBEDDING_CACHE_NAMESPACE,
        )

    return factory


def _inject(failure_point: str | None, point: str) -> None:
    if failure_point == point:
        raise ResearchMapInjectedFailure("injected_failure", point)


def _validate_failure_point(failure_point: str | None) -> None:
    if failure_point is not None and failure_point not in _FAILURE_POINTS:
        raise ValueError(f"unknown RM6 failure point: {failure_point}")


def _prepare_projection(repository_root: Path) -> tuple[object, object, BackendProjection]:
    scan = scan_research_map(repository_root)
    if scan.health_state is ResearchMapHealthState.NOT_ADOPTED:
        raise ResearchMapSyncError("not_adopted", "research map is not adopted")
    if scan.health_state is ResearchMapHealthState.DISABLED:
        raise ResearchMapSyncError("disabled", "research map is disabled")
    if scan.health_state is not ResearchMapHealthState.HEALTHY or scan.issues:
        raise ResearchMapSyncError("semantic_state_degraded", "research map semantic state is degraded")
    if not scan.coverage.complete:
        raise ResearchMapSyncError("coverage_incomplete", "research map coverage must be complete before sync")
    if scan.desired_state is None:
        raise ResearchMapSyncError("desired_state_unavailable", "semantic desired state is unavailable")

    manifest_result = load_project_manifest(repository_root)
    if not manifest_result.valid or manifest_result.manifest is None:
        raise ResearchMapSyncError("manifest_invalid", "research map manifest is unavailable")
    projection = build_backend_projection(
        manifest_result.manifest,
        scan.sidecar_scan,
        scan.desired_state,
    )
    return scan, manifest_result.manifest, projection


def _current_expected_relation_ids(
    repository_root: Path,
    current: CurrentGeneration,
) -> tuple[str, ...]:
    path = generation_directory(repository_root, current.generation) / HEALTH_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchMapGenerationError("published generation health is unreadable") from exc
    relation_ids = payload.get("expected_relation_ids") if isinstance(payload, dict) else None
    if (
        not isinstance(relation_ids, list)
        or len(relation_ids) != current.relation_count
        or any(not isinstance(item, str) or not item for item in relation_ids)
    ):
        raise ResearchMapGenerationError("published generation relation manifest is invalid")
    return tuple(sorted(relation_ids))


async def _verify_existing_current(
    repository_root: Path,
    current: CurrentGeneration,
    expected_relation_ids: tuple[str, ...],
    *,
    repository_uid: str,
    backend_factory: BackendFactory,
) -> bool:
    if current.storage_mode == VERSIONED_STORAGE_MODE:
        return await verify_versioned_current(
            repository_root,
            current,
            repository_uid=repository_uid,
            backend_factory=backend_factory,
        )
    backend = backend_factory(repository_uid, current.database)
    try:
        verification = await backend.reopen_and_verify(expected_relation_ids)
        return verification.matches
    finally:
        await backend.close()


async def _seed_embedding_cache_from_current(
    repository_root: Path,
    current: CurrentGeneration,
    *,
    repository_uid: str,
    backend_factory: BackendFactory,
) -> dict[str, object]:
    backend = backend_factory(repository_uid, current.database)
    try:
        expected_relation_ids = _current_expected_relation_ids(repository_root, current)
        verification = await backend.reopen_and_verify(expected_relation_ids)
        if not verification.matches:
            return {"verified": False, "seeded": 0}
        seed = getattr(backend, "seed_embedding_cache_from_graph", None)
        if not callable(seed):
            return {"verified": True, "seeded": 0}
        seeded = await seed()
        diagnostics = getattr(backend, "diagnostics", None)
        return {
            "verified": True,
            "seeded": int(seeded),
            "backend": diagnostics() if callable(diagnostics) else {},
        }
    finally:
        await backend.close()


async def _build_generation(
    repository_root: Path,
    *,
    repository_uid: str,
    desired_state: object,
    projection: BackendProjection,
    projection_contract_sha256: str,
    backend_factory: BackendFactory,
    failure_point: str | None,
) -> dict[str, object]:
    expected_relation_ids = tuple(relation.relation_id for relation in projection.relations)
    generation = new_generation_id(
        projection.semantic_desired_state_sha256,
        projection_contract_sha256,
    )
    database = generation_database_name(repository_uid, generation)

    _inject(failure_point, "before_staging_creation")
    directory = create_generation_directory(repository_root, generation)
    _inject(failure_point, "after_staging_creation")

    desired_payload = desired_artifact_payload(
        repository_uid=repository_uid,
        semantic_desired_state_sha256=projection.semantic_desired_state_sha256,
        projection_contract_sha256=projection_contract_sha256,
        desired_payload=desired_state.payload,  # type: ignore[attr-defined]
    )
    relations_payload = relations_artifact_payload(
        projection=projection,
        projection_contract_sha256=projection_contract_sha256,
        database=database,
    )
    desired_sha256, relations_sha256 = write_generation_inputs(
        directory,
        desired_payload=desired_payload,
        relations_payload=relations_payload,
    )

    backend = backend_factory(repository_uid, database)
    published = False
    phase_timings: dict[str, float] = {}
    try:
        started = time.perf_counter()
        await backend.build_empty()
        phase_timings["build_empty"] = time.perf_counter() - started

        started = time.perf_counter()
        await backend.upsert_nodes(projection.nodes)
        phase_timings["upsert_nodes"] = time.perf_counter() - started

        started = time.perf_counter()
        if failure_point == "mid_relation_writes" and projection.relations:
            split = max(1, len(projection.relations) // 2)
            await backend.upsert_relations(projection.relations[:split])
            _inject(failure_point, "mid_relation_writes")
        else:
            await backend.upsert_relations(projection.relations)
            _inject(failure_point, "mid_relation_writes")
        phase_timings["upsert_relations"] = time.perf_counter() - started

        started = time.perf_counter()
        actual_before_save = tuple(sorted(await backend.read_relation_manifest()))
        phase_timings["readback_manifest"] = time.perf_counter() - started
        if actual_before_save != expected_relation_ids:
            raise ResearchMapSyncError(
                "relation_reconciliation_failed",
                "backend relation manifest does not match desired projection before persistence",
            )
        _inject(failure_point, "after_read_back")
        _inject(failure_point, "before_save")

        started = time.perf_counter()
        persist_result = await backend.persist()
        phase_timings["persist"] = time.perf_counter() - started
        if not persist_result.persisted:
            raise ResearchMapSyncError("persistence_failed", "backend did not confirm explicit persistence")
        _inject(failure_point, "after_save")

        started = time.perf_counter()
        verification = await backend.reopen_and_verify(expected_relation_ids)
        phase_timings["reopen_verify"] = time.perf_counter() - started
        if not verification.matches:
            raise ResearchMapSyncError(
                "reopen_reconciliation_failed",
                "backend relation manifest does not match after reopen",
            )
        await backend.close()

        health = health_payload(
            generation=generation,
            database=database,
            repository_uid=repository_uid,
            semantic_desired_state_sha256=projection.semantic_desired_state_sha256,
            projection_contract_sha256=projection_contract_sha256,
            expected_relation_ids=expected_relation_ids,
            actual_relation_ids=verification.actual_relation_ids,
            persisted=True,
            reopen_verified=True,
        )
        health_sha256 = write_generation_health(directory, health)
        pointer = current_payload(
            generation=generation,
            database=database,
            repository_uid=repository_uid,
            semantic_desired_state_sha256=projection.semantic_desired_state_sha256,
            projection_contract_sha256=projection_contract_sha256,
            relation_count=len(expected_relation_ids),
            desired_sha256=desired_sha256,
            relations_sha256=relations_sha256,
            health_sha256=health_sha256,
        )
        _inject(failure_point, "before_current_publish")
        started = time.perf_counter()
        publish_current(repository_root, pointer)
        phase_timings["publish_current"] = time.perf_counter() - started
        published = True
        _inject(failure_point, "after_current_publish")
        diagnostics = getattr(backend, "diagnostics", None)
        return {
            "generation": generation,
            "database": database,
            "relation_count": len(expected_relation_ids),
            "semantic_desired_state_sha256": projection.semantic_desired_state_sha256,
            "projection_contract_sha256": projection_contract_sha256,
            "published": True,
            "reopen_verified": True,
            "build_strategy": "full_rebuild_bounded_parallel",
            "embedding_strategy": "persistent_deterministic_cache",
            "node_count": len(projection.nodes),
            "phase_timings_seconds": phase_timings,
            "backend_diagnostics": diagnostics() if callable(diagnostics) else {},
        }
    finally:
        if not published:
            with suppress(ResearchMapBackendError, OSError, RuntimeError):
                await backend.close()


async def sync_research_map_async(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    action: Literal["sync", "rebuild"],
    backend_factory: BackendFactory | None = None,
    projection_contract_sha256: str | None = None,
    failure_point: str | None = None,
) -> dict[str, object]:
    _validate_failure_point(failure_point)
    if action not in {"sync", "rebuild"}:
        raise ResearchMapSyncError("invalid_action", f"unsupported research-map action: {action}")
    operation_started = time.perf_counter()
    root = Path(repository_root).resolve()
    phase_timings: dict[str, float] = {}
    started = time.perf_counter()
    scan, manifest, projection = _prepare_projection(root)
    phase_timings["prepare_projection"] = time.perf_counter() - started
    projection_hash = projection_contract_sha256 or graphiti_projection_contract_sha256()
    backend_factory = backend_factory or _default_backend_factory(root, projection_hash)
    expected_relation_ids = tuple(relation.relation_id for relation in projection.relations)

    with SyncWriterLock(root):
        current: CurrentGeneration | None
        started = time.perf_counter()
        try:
            current = load_current_generation(root)
        except ResearchMapGenerationError:
            current = None
        phase_timings["load_current"] = time.perf_counter() - started

        if (
            action == "sync"
            and current is not None
            and current.repository_uid == manifest.repository_uid
            and current.semantic_desired_state_sha256 == projection.semantic_desired_state_sha256
            and current.projection_contract_sha256 == projection_hash
            and current.relation_count == len(expected_relation_ids)
        ):
            started = time.perf_counter()
            verified = await _verify_existing_current(
                root,
                current,
                expected_relation_ids,
                repository_uid=manifest.repository_uid,
                backend_factory=backend_factory,
            )
            phase_timings["verify_current"] = time.perf_counter() - started
            if verified:
                phase_timings["total"] = time.perf_counter() - operation_started
                return {
                    "ok": True,
                    "action": action,
                    "status": "already_current",
                    "project_id": project_id,
                    "repo_name": repo_name,
                    "repository_uid": manifest.repository_uid,
                    "generation": current.generation,
                    "relation_count": current.relation_count,
                    "semantic_desired_state_sha256": current.semantic_desired_state_sha256,
                    "projection_contract_sha256": current.projection_contract_sha256,
                    "published": False,
                    "reopen_verified": True,
                    "sync_version": RESEARCH_MAP_SYNC_VERSION,
                    "phase_timings_seconds": phase_timings,
                    "error": "",
                }

        cache_seed: dict[str, object] = {"verified": False, "seeded": 0}
        if (
            current is not None
            and current.storage_mode != VERSIONED_STORAGE_MODE
            and current.repository_uid == manifest.repository_uid
            and current.projection_contract_sha256
            in {projection_hash, LEGACY_V1_PROJECTION_SHA256}
        ):
            started = time.perf_counter()
            cache_seed = await _seed_embedding_cache_from_current(
                root,
                current,
                repository_uid=manifest.repository_uid,
                backend_factory=backend_factory,
            )
            phase_timings["seed_embedding_cache"] = time.perf_counter() - started

        built = await build_versioned_generation(
            root,
            repository_uid=manifest.repository_uid,
            desired_state=scan.desired_state,
            projection=projection,
            projection_contract_sha256=projection_hash,
            backend_factory=backend_factory,
            current=current,
            force_rebuild=action == "rebuild",
            failure_point=failure_point,
        )
        if built is None:
            if current is not None and current.storage_mode == VERSIONED_STORAGE_MODE:
                raise ResearchMapSyncError(
                    "versioned_backend_unsupported",
                    "current Research Map generation requires exact version-filtered backend reads",
                )
            built = await _build_generation(
                root,
                repository_uid=manifest.repository_uid,
                desired_state=scan.desired_state,
                projection=projection,
                projection_contract_sha256=projection_hash,
                backend_factory=backend_factory,
                failure_point=failure_point,
            )
        build_phases = built.get("phase_timings_seconds")
        if isinstance(build_phases, dict):
            phase_timings.update(
                {f"build.{key}": float(value) for key, value in build_phases.items()}
            )
        phase_timings["total"] = time.perf_counter() - operation_started
        return {
            "ok": True,
            "action": action,
            "status": "rebuilt" if action == "rebuild" else "synchronized",
            "project_id": project_id,
            "repo_name": repo_name,
            "repository_uid": manifest.repository_uid,
            **built,
            "sync_version": RESEARCH_MAP_SYNC_VERSION,
            "embedding_cache_seed": cache_seed,
            "phase_timings_seconds": phase_timings,
            "error": "",
        }


def sync_research_map(
    repository_root: str | Path,
    *,
    project_id: str,
    repo_name: str,
    action: Literal["sync", "rebuild"],
    backend_factory: BackendFactory | None = None,
    projection_contract_sha256: str | None = None,
    failure_point: str | None = None,
) -> dict[str, object]:
    timeout_seconds = (
        RESEARCH_MAP_SYNC_TIMEOUT_SECONDS
        if action == "sync"
        else RESEARCH_MAP_REBUILD_TIMEOUT_SECONDS
    )

    async def _run_with_timeout() -> dict[str, object]:
        return await asyncio.wait_for(
            sync_research_map_async(
                repository_root,
                project_id=project_id,
                repo_name=repo_name,
                action=action,
                backend_factory=backend_factory,
                projection_contract_sha256=projection_contract_sha256,
                failure_point=failure_point,
            ),
            timeout=timeout_seconds,
        )

    try:
        return asyncio.run(_run_with_timeout())
    except TimeoutError as exc:
        raise ResearchMapSyncError(
            "sync_timeout",
            f"research-map {action} exceeded {timeout_seconds:.0f} seconds",
        ) from exc
    except ResearchMapSyncError:
        raise
    except (ResearchMapBackendError, ResearchMapGenerationError) as exc:
        raise ResearchMapSyncError("backend_or_generation_failure", str(exc)) from exc
    except Exception as exc:
        raise ResearchMapSyncError("backend_runtime_failure", str(exc)) from exc
