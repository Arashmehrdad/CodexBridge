from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .backend import BackendProjection, ResearchMapBackend, ResearchMapBackendError
from .generation import (
    RELATIONS_FILENAME,
    VERSIONED_STORAGE_MODE,
    CurrentGeneration,
    ResearchMapGenerationError,
    create_generation_directory,
    current_payload,
    desired_artifact_payload,
    generation_database_name,
    generation_directory,
    health_payload,
    new_generation_id,
    publish_current,
    relations_artifact_payload,
    write_generation_health,
    write_generation_inputs,
)
from .versioning import version_backend_projection

BackendFactory = Callable[[str, str], ResearchMapBackend]


@dataclass(frozen=True, slots=True)
class GenerationVersions:
    node_uuids: frozenset[str]
    relation_uuid_to_id: dict[str, str]

    @property
    def relation_uuids(self) -> tuple[str, ...]:
        return tuple(sorted(self.relation_uuid_to_id))

    @property
    def relation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.relation_uuid_to_id.values()))


def _versioned_reader(backend: ResearchMapBackend) -> object | None:
    reader = getattr(backend, "read_relation_manifest_for_uuids", None)
    return reader if callable(reader) else None


def backend_supports_versioned_storage(backend: ResearchMapBackend) -> bool:
    return _versioned_reader(backend) is not None


def _load_generation_versions(
    repository_root: Path,
    current: CurrentGeneration,
) -> GenerationVersions:
    if current.storage_mode != VERSIONED_STORAGE_MODE:
        raise ResearchMapGenerationError("published generation is not versioned storage")
    path = generation_directory(repository_root, current.generation) / RELATIONS_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchMapGenerationError("published versioned projection is unreadable") from exc
    if not isinstance(payload, dict):
        raise ResearchMapGenerationError("published versioned projection must be an object")
    expected = {
        "repository_uid": current.repository_uid,
        "semantic_desired_state_sha256": current.semantic_desired_state_sha256,
        "projection_contract_sha256": current.projection_contract_sha256,
        "database": current.database,
        "storage_mode": VERSIONED_STORAGE_MODE,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ResearchMapGenerationError(
                f"published versioned projection metadata mismatch: {key}"
            )
    raw_nodes = payload.get("nodes")
    raw_relations = payload.get("relations")
    if not isinstance(raw_nodes, list) or not isinstance(raw_relations, list):
        raise ResearchMapGenerationError("published versioned projection lists are invalid")
    if len(raw_relations) != current.relation_count:
        raise ResearchMapGenerationError("published versioned relation count mismatch")

    node_uuids: set[str] = set()
    for raw in raw_nodes:
        if not isinstance(raw, dict) or not isinstance(raw.get("uuid"), str) or not raw["uuid"]:
            raise ResearchMapGenerationError("published versioned node UUID is invalid")
        node_uuids.add(raw["uuid"])
    if len(node_uuids) != len(raw_nodes):
        raise ResearchMapGenerationError("published versioned node UUIDs are not unique")

    relation_uuid_to_id: dict[str, str] = {}
    relation_ids: set[str] = set()
    for raw in raw_relations:
        if not isinstance(raw, dict):
            raise ResearchMapGenerationError("published versioned relation entry is invalid")
        edge_uuid = raw.get("uuid")
        relation_id = raw.get("relation_id")
        if not isinstance(edge_uuid, str) or not edge_uuid:
            raise ResearchMapGenerationError("published versioned relation UUID is invalid")
        if not isinstance(relation_id, str) or not relation_id:
            raise ResearchMapGenerationError("published versioned relation identity is invalid")
        if edge_uuid in relation_uuid_to_id or relation_id in relation_ids:
            raise ResearchMapGenerationError("published versioned relation identities are not unique")
        relation_uuid_to_id[edge_uuid] = relation_id
        relation_ids.add(relation_id)
    return GenerationVersions(
        node_uuids=frozenset(node_uuids),
        relation_uuid_to_id=relation_uuid_to_id,
    )


async def _read_filtered_manifest(
    backend: ResearchMapBackend,
    edge_uuids: tuple[str, ...],
) -> tuple[str, ...]:
    reader = _versioned_reader(backend)
    if reader is None:
        raise ResearchMapBackendError(
            "backend does not support exact version-filtered Research Map reads"
        )
    result = await reader(edge_uuids)
    return tuple(sorted(str(item) for item in result))


async def verify_versioned_current(
    repository_root: Path,
    current: CurrentGeneration,
    *,
    repository_uid: str,
    backend_factory: BackendFactory,
) -> bool:
    versions = _load_generation_versions(repository_root, current)
    backend = backend_factory(repository_uid, current.database)
    try:
        if not backend_supports_versioned_storage(backend):
            return False
        actual = await _read_filtered_manifest(backend, versions.relation_uuids)
        return actual == versions.relation_ids
    finally:
        await backend.close()


def _inject(failure_point: str | None, point: str) -> None:
    if failure_point == point:
        from .sync import ResearchMapInjectedFailure

        raise ResearchMapInjectedFailure("injected_failure", point)


async def build_versioned_generation(
    repository_root: Path,
    *,
    repository_uid: str,
    desired_state: object,
    projection: BackendProjection,
    projection_contract_sha256: str,
    backend_factory: BackendFactory,
    current: CurrentGeneration | None,
    force_rebuild: bool,
    failure_point: str | None,
) -> dict[str, object] | None:
    """Build and publish one verified generation over append-only object versions.

    Returns ``None`` only when the selected backend does not implement the
    exact-version read primitive required for safe immutable publication.
    """

    versioned_projection = version_backend_projection(projection)
    expected_relation_ids = tuple(
        relation.relation_id for relation in versioned_projection.relations
    )
    expected_edge_uuids = tuple(
        relation.uuid for relation in versioned_projection.relations
    )
    generation = new_generation_id(
        projection.semantic_desired_state_sha256,
        projection_contract_sha256,
    )

    incremental = (
        not force_rebuild
        and current is not None
        and current.storage_mode == VERSIONED_STORAGE_MODE
        and current.repository_uid == repository_uid
        and current.projection_contract_sha256 == projection_contract_sha256
    )
    database = (
        current.database
        if incremental and current is not None
        else generation_database_name(repository_uid, generation)
    )
    backend = backend_factory(repository_uid, database)
    if not backend_supports_versioned_storage(backend):
        await backend.close()
        return None

    prior = GenerationVersions(node_uuids=frozenset(), relation_uuid_to_id={})
    build_strategy = "full_versioned_rebuild"
    phase_timings: dict[str, float] = {}
    published = False
    verifier: ResearchMapBackend | None = None
    try:
        if incremental and current is not None:
            prior = _load_generation_versions(repository_root, current)
            started = time.perf_counter()
            actual_current = await _read_filtered_manifest(backend, prior.relation_uuids)
            phase_timings["verify_current"] = time.perf_counter() - started
            if actual_current != prior.relation_ids:
                await backend.close()
                generation = new_generation_id(
                    projection.semantic_desired_state_sha256,
                    projection_contract_sha256,
                )
                database = generation_database_name(repository_uid, generation)
                backend = backend_factory(repository_uid, database)
                if not backend_supports_versioned_storage(backend):
                    await backend.close()
                    return None
                prior = GenerationVersions(node_uuids=frozenset(), relation_uuid_to_id={})
                incremental = False
                build_strategy = "full_versioned_repair"
            else:
                build_strategy = "incremental_versioned_append"

        desired_node_uuids = {node.uuid for node in versioned_projection.nodes}
        desired_relation_uuid_to_id = {
            relation.uuid: relation.relation_id
            for relation in versioned_projection.relations
        }
        added_nodes = tuple(
            node
            for node in versioned_projection.nodes
            if node.uuid not in prior.node_uuids
        )
        added_relations = tuple(
            relation
            for relation in versioned_projection.relations
            if relation.uuid not in prior.relation_uuid_to_id
        )
        retired_node_uuids = tuple(sorted(prior.node_uuids - desired_node_uuids))
        retired_relation_uuids = tuple(
            sorted(set(prior.relation_uuid_to_id) - set(desired_relation_uuid_to_id))
        )
        reused_node_count = len(desired_node_uuids & prior.node_uuids)
        reused_relation_count = len(
            set(desired_relation_uuid_to_id) & set(prior.relation_uuid_to_id)
        )

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
            projection=versioned_projection,
            projection_contract_sha256=projection_contract_sha256,
            database=database,
            storage_mode=VERSIONED_STORAGE_MODE,
        )
        desired_sha256, relations_sha256 = write_generation_inputs(
            directory,
            desired_payload=desired_payload,
            relations_payload=relations_payload,
        )

        if not incremental:
            started = time.perf_counter()
            await backend.build_empty()
            phase_timings["build_empty"] = time.perf_counter() - started

        started = time.perf_counter()
        await backend.upsert_nodes(added_nodes)
        phase_timings["upsert_nodes"] = time.perf_counter() - started

        started = time.perf_counter()
        if failure_point == "mid_relation_writes" and added_relations:
            split = max(1, len(added_relations) // 2)
            await backend.upsert_relations(added_relations[:split])
            _inject(failure_point, "mid_relation_writes")
        else:
            await backend.upsert_relations(added_relations)
            _inject(failure_point, "mid_relation_writes")
        phase_timings["upsert_relations"] = time.perf_counter() - started

        started = time.perf_counter()
        actual_before_save = await _read_filtered_manifest(backend, expected_edge_uuids)
        phase_timings["readback_manifest"] = time.perf_counter() - started
        if actual_before_save != tuple(sorted(expected_relation_ids)):
            from .sync import ResearchMapSyncError

            raise ResearchMapSyncError(
                "relation_reconciliation_failed",
                "version-filtered backend manifest does not match candidate generation",
            )
        _inject(failure_point, "after_read_back")
        _inject(failure_point, "before_save")

        backend_mutated = bool(added_nodes or added_relations or not incremental)
        if backend_mutated:
            started = time.perf_counter()
            persist_result = await backend.persist()
            phase_timings["persist"] = time.perf_counter() - started
            if not persist_result.persisted:
                from .sync import ResearchMapSyncError

                raise ResearchMapSyncError(
                    "persistence_failed",
                    "backend did not confirm explicit persistence",
                )
        else:
            phase_timings["persist"] = 0.0
        _inject(failure_point, "after_save")

        await backend.close()
        verifier = backend_factory(repository_uid, database)
        started = time.perf_counter()
        actual_after_reopen = await _read_filtered_manifest(verifier, expected_edge_uuids)
        phase_timings["reopen_verify"] = time.perf_counter() - started
        if actual_after_reopen != tuple(sorted(expected_relation_ids)):
            from .sync import ResearchMapSyncError

            raise ResearchMapSyncError(
                "reopen_reconciliation_failed",
                "version-filtered backend manifest does not match after reopen",
            )
        await verifier.close()
        verifier = None

        health = health_payload(
            generation=generation,
            database=database,
            repository_uid=repository_uid,
            semantic_desired_state_sha256=projection.semantic_desired_state_sha256,
            projection_contract_sha256=projection_contract_sha256,
            expected_relation_ids=tuple(sorted(expected_relation_ids)),
            actual_relation_ids=actual_after_reopen,
            persisted=True,
            reopen_verified=True,
            storage_mode=VERSIONED_STORAGE_MODE,
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
            storage_mode=VERSIONED_STORAGE_MODE,
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
            "storage_mode": VERSIONED_STORAGE_MODE,
            "build_strategy": build_strategy,
            "embedding_strategy": "persistent_deterministic_cache",
            "node_count": len(versioned_projection.nodes),
            "phase_timings_seconds": phase_timings,
            "backend_diagnostics": diagnostics() if callable(diagnostics) else {},
            "delta": {
                "added_nodes": len(added_nodes),
                "reused_nodes": reused_node_count,
                "retired_node_versions": len(retired_node_uuids),
                "added_relations": len(added_relations),
                "reused_relations": reused_relation_count,
                "retired_relation_versions": len(retired_relation_uuids),
                "backend_mutated": backend_mutated,
            },
        }
    finally:
        if verifier is not None:
            with suppress(ResearchMapBackendError, OSError, RuntimeError):
                await verifier.close()
        if not published:
            with suppress(ResearchMapBackendError, OSError, RuntimeError):
                await backend.close()
