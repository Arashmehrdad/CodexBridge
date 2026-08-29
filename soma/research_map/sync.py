from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from .backend import (
    BackendProjection,
    ProjectedNode,
    ProjectedRelation,
    ResearchMapBackend,
    ResearchMapBackendError,
    build_backend_projection,
)
from .generation import (
    RELATIONS_FILENAME,
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
from .graphiti_backend import GraphitiFalkorBackend, graphiti_projection_contract_sha256
from .manifest import load_project_manifest
from .service import ResearchMapHealthState, scan_research_map

RESEARCH_MAP_SYNC_VERSION = "soma.research-map.sync.v1"
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


def _additive_delta_from_current(
    repository_root: Path,
    current: CurrentGeneration,
    projection: BackendProjection,
) -> tuple[
    tuple[ProjectedNode, ...],
    tuple[ProjectedRelation, ...],
    tuple[str, ...],
] | None:
    """Return a safe append-only delta, otherwise require a full rebuild."""
    path = generation_directory(repository_root, current.generation) / RELATIONS_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchMapGenerationError(
            "published RELATIONS.json cannot be decoded for incremental sync"
        ) from exc
    if not isinstance(payload, dict):
        raise ResearchMapGenerationError(
            "published RELATIONS.json must be an object for incremental sync"
        )
    expected_metadata = {
        "repository_uid": current.repository_uid,
        "semantic_desired_state_sha256": current.semantic_desired_state_sha256,
        "projection_contract_sha256": current.projection_contract_sha256,
        "database": current.database,
    }
    for key, expected in expected_metadata.items():
        if payload.get(key) != expected:
            raise ResearchMapGenerationError(
                f"published RELATIONS.json metadata mismatch for incremental sync: {key}"
            )
    raw_nodes = payload.get("nodes")
    raw_relations = payload.get("relations")
    if not isinstance(raw_nodes, list) or not isinstance(raw_relations, list):
        raise ResearchMapGenerationError(
            "published RELATIONS.json is missing node/relation arrays"
        )
    if len(raw_relations) != current.relation_count:
        raise ResearchMapGenerationError(
            "published RELATIONS.json relation count does not match CURRENT"
        )

    prior_nodes: dict[str, dict[str, object]] = {}
    for raw in raw_nodes:
        if not isinstance(raw, dict) or not isinstance(raw.get("uuid"), str):
            raise ResearchMapGenerationError("published node entry is invalid")
        uuid = str(raw["uuid"])
        if uuid in prior_nodes:
            raise ResearchMapGenerationError("published node UUIDs are not unique")
        prior_nodes[uuid] = raw

    prior_relations: dict[str, dict[str, object]] = {}
    for raw in raw_relations:
        if not isinstance(raw, dict) or not isinstance(raw.get("relation_id"), str):
            raise ResearchMapGenerationError("published relation entry is invalid")
        relation_id = str(raw["relation_id"])
        if relation_id in prior_relations:
            raise ResearchMapGenerationError("published relation IDs are not unique")
        prior_relations[relation_id] = raw

    desired_nodes = {item.uuid: asdict(item) for item in projection.nodes}
    desired_relations = {item.relation_id: asdict(item) for item in projection.relations}
    if any(desired_nodes.get(key) != value for key, value in prior_nodes.items()):
        return None
    if any(
        desired_relations.get(key) != value for key, value in prior_relations.items()
    ):
        return None

    added_nodes = tuple(item for item in projection.nodes if item.uuid not in prior_nodes)
    added_relations = tuple(
        item for item in projection.relations if item.relation_id not in prior_relations
    )
    return added_nodes, added_relations, tuple(sorted(prior_relations))


async def _build_generation(
    repository_root: Path,
    *,
    repository_uid: str,
    desired_state: object,
    projection: BackendProjection,
    projection_contract_sha256: str,
    backend_factory: BackendFactory,
    failure_point: str | None,
    source_current: CurrentGeneration | None = None,
    added_nodes: tuple[ProjectedNode, ...] = (),
    added_relations: tuple[ProjectedRelation, ...] = (),
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
        if source_current is None:
            await backend.build_empty()
            await backend.upsert_nodes(projection.nodes)
            if failure_point == "mid_relation_writes" and projection.relations:
                split = max(1, len(projection.relations) // 2)
                await backend.upsert_relations(projection.relations[:split])
                _inject(failure_point, "mid_relation_writes")
            else:
                await backend.upsert_relations(projection.relations)
                _inject(failure_point, "mid_relation_writes")
        else:
            await backend.clone_from_current(source_current)
            await backend.upsert_nodes(added_nodes)
            await backend.upsert_relations(added_relations)
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
            "build_strategy": (
                "full_rebuild" if source_current is None else "additive_clone"
            ),
            "added_node_count": (
                len(projection.nodes) if source_current is None else len(added_nodes)
            ),
            "added_relation_count": (
                len(projection.relations)
                if source_current is None
                else len(added_relations)
            ),
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

        source_current: CurrentGeneration | None = None
        added_nodes: tuple[ProjectedNode, ...] = ()
        added_relations: tuple[ProjectedRelation, ...] = ()
        if (
            action == "sync"
            and current is not None
            and current.repository_uid == manifest.repository_uid
            and current.projection_contract_sha256 == projection_hash
        ):
            additive_delta = _additive_delta_from_current(root, current, projection)
            if additive_delta is not None:
                candidate_nodes, candidate_relations, current_relation_ids = additive_delta
                source_verified = await _verify_existing_current(
                    current,
                    current_relation_ids,
                    repository_uid=manifest.repository_uid,
                    backend_factory=backend_factory,
                )
                if source_verified:
                    source_current = current
                    added_nodes = candidate_nodes
                    added_relations = candidate_relations

        built = await _build_generation(
            root,
            repository_uid=manifest.repository_uid,
            desired_state=scan.desired_state,
            projection=projection,
            projection_contract_sha256=projection_hash,
            backend_factory=backend_factory,
            failure_point=failure_point,
            source_current=source_current,
            added_nodes=added_nodes,
            added_relations=added_relations,
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
