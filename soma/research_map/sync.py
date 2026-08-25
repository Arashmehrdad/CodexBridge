from __future__ import annotations

import asyncio
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
from .generation import (
    CurrentGeneration,
    ResearchMapGenerationError,
    SyncWriterLock,
    create_generation_directory,
    current_payload,
    desired_artifact_payload,
    generation_database_name,
    health_payload,
    load_current_generation,
    new_generation_id,
    publish_current,
    relations_artifact_payload,
    write_generation_health,
    write_generation_inputs,
)
from .graphiti_backend import GraphitiFalkorBackend, graphiti_projection_contract_sha256
from .manifest import load_project_manifest
from .service import ResearchMapHealthState, scan_research_map

RESEARCH_MAP_SYNC_VERSION = "soma.research-map.sync.v1"
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


def _default_backend_factory(repository_uid: str, database: str) -> ResearchMapBackend:
    return GraphitiFalkorBackend(repository_uid=repository_uid, database=database)


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


async def _verify_existing_current(
    current: CurrentGeneration,
    expected_relation_ids: tuple[str, ...],
    *,
    repository_uid: str,
    backend_factory: BackendFactory,
) -> bool:
    backend = backend_factory(repository_uid, current.database)
    try:
        verification = await backend.reopen_and_verify(expected_relation_ids)
        return verification.matches
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
    try:
        await backend.build_empty()
        await backend.upsert_nodes(projection.nodes)
        if failure_point == "mid_relation_writes" and projection.relations:
            split = max(1, len(projection.relations) // 2)
            await backend.upsert_relations(projection.relations[:split])
            _inject(failure_point, "mid_relation_writes")
        else:
            await backend.upsert_relations(projection.relations)
            _inject(failure_point, "mid_relation_writes")

        actual_before_save = tuple(sorted(await backend.read_relation_manifest()))
        if actual_before_save != expected_relation_ids:
            raise ResearchMapSyncError(
                "relation_reconciliation_failed",
                "backend relation manifest does not match desired projection before persistence",
            )
        _inject(failure_point, "after_read_back")
        _inject(failure_point, "before_save")

        persist_result = await backend.persist()
        if not persist_result.persisted:
            raise ResearchMapSyncError("persistence_failed", "backend did not confirm explicit persistence")
        _inject(failure_point, "after_save")

        verification = await backend.reopen_and_verify(expected_relation_ids)
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
        publish_current(repository_root, pointer)
        published = True
        _inject(failure_point, "after_current_publish")
        return {
            "generation": generation,
            "database": database,
            "relation_count": len(expected_relation_ids),
            "semantic_desired_state_sha256": projection.semantic_desired_state_sha256,
            "projection_contract_sha256": projection_contract_sha256,
            "published": True,
            "reopen_verified": True,
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
    root = Path(repository_root).resolve()
    scan, manifest, projection = _prepare_projection(root)
    backend_factory = backend_factory or _default_backend_factory
    projection_hash = projection_contract_sha256 or graphiti_projection_contract_sha256()
    expected_relation_ids = tuple(relation.relation_id for relation in projection.relations)

    with SyncWriterLock(root):
        current: CurrentGeneration | None
        try:
            current = load_current_generation(root)
        except ResearchMapGenerationError:
            current = None

        if (
            action == "sync"
            and current is not None
            and current.repository_uid == manifest.repository_uid
            and current.semantic_desired_state_sha256 == projection.semantic_desired_state_sha256
            and current.projection_contract_sha256 == projection_hash
            and current.relation_count == len(expected_relation_ids)
        ):
            verified = await _verify_existing_current(
                current,
                expected_relation_ids,
                repository_uid=manifest.repository_uid,
                backend_factory=backend_factory,
            )
            if verified:
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
                    "error": "",
                }

        built = await _build_generation(
            root,
            repository_uid=manifest.repository_uid,
            desired_state=scan.desired_state,
            projection=projection,
            projection_contract_sha256=projection_hash,
            backend_factory=backend_factory,
            failure_point=failure_point,
        )
        return {
            "ok": True,
            "action": action,
            "status": "rebuilt" if action == "rebuild" else "synchronized",
            "project_id": project_id,
            "repo_name": repo_name,
            "repository_uid": manifest.repository_uid,
            **built,
            "sync_version": RESEARCH_MAP_SYNC_VERSION,
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
    try:
        return asyncio.run(
            sync_research_map_async(
                repository_root,
                project_id=project_id,
                repo_name=repo_name,
                action=action,
                backend_factory=backend_factory,
                projection_contract_sha256=projection_contract_sha256,
                failure_point=failure_point,
            )
        )
    except ResearchMapSyncError:
        raise
    except (ResearchMapBackendError, ResearchMapGenerationError) as exc:
        raise ResearchMapSyncError("backend_or_generation_failure", str(exc)) from exc
    except Exception as exc:
        raise ResearchMapSyncError("backend_runtime_failure", str(exc)) from exc
