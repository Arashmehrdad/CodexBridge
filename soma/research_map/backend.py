from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import NAMESPACE_URL, uuid5

from .canonical import canonical_json_bytes
from .desired_state import DesiredStateResult
from .models import ProjectManifest, RelationLifecycle
from .sidecars import SidecarScanResult, SidecarState

BACKEND_PROTOCOL_VERSION = "soma.research-map.backend.v1"
PROJECTION_CONTRACT_VERSION = "soma.research-map.graph-projection.v1"


class ResearchMapBackendError(RuntimeError):
    """Base class for derived research-map backend failures."""


class ResearchMapBackendUnavailable(ResearchMapBackendError):
    """Raised when an optional derived backend cannot be used."""


class ResearchMapProjectionError(ResearchMapBackendError):
    """Raised when reviewed semantic state cannot be projected deterministically."""


@dataclass(frozen=True, slots=True)
class ProjectedNode:
    uuid: str
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class ProjectedRelation:
    uuid: str
    relation_id: str
    source_node_uuid: str
    target_node_uuid: str
    source_key: str
    target_key: str
    predicate: str
    statement: str
    source_path: str
    source_canonical_text_sha256: str
    source_anchor: str
    epistemic_class: str
    lifecycle: str
    record_facets_json: str
    facets_json: str
    qualifiers_json: str


@dataclass(frozen=True, slots=True)
class BackendProjection:
    repository_uid: str
    semantic_desired_state_sha256: str
    nodes: tuple[ProjectedNode, ...]
    relations: tuple[ProjectedRelation, ...]


@dataclass(frozen=True, slots=True)
class BackendSearchHit:
    relation_id: str
    score: float | None = None


@dataclass(frozen=True, slots=True)
class BackendPersistResult:
    persisted: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BackendVerification:
    expected_relation_ids: tuple[str, ...]
    actual_relation_ids: tuple[str, ...]

    @property
    def matches(self) -> bool:
        return self.expected_relation_ids == self.actual_relation_ids


@runtime_checkable
class ResearchMapBackend(Protocol):
    async def build_empty(self) -> None: ...

    async def clone_from_current(self, source: object) -> None: ...

    async def upsert_nodes(self, nodes: tuple[ProjectedNode, ...]) -> None: ...

    async def upsert_relations(self, relations: tuple[ProjectedRelation, ...]) -> None: ...

    async def remove_relations(self, relation_ids: tuple[str, ...]) -> None: ...

    async def read_relation_manifest(self) -> tuple[str, ...]: ...

    async def search(self, query: str, *, limit: int = 5) -> tuple[BackendSearchHit, ...]: ...

    async def persist(self) -> BackendPersistResult: ...

    async def close(self) -> None: ...

    async def reopen_and_verify(
        self,
        expected_relation_ids: tuple[str, ...],
    ) -> BackendVerification: ...


def _node_uuid(repository_uid: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"soma-research-map:{repository_uid}:node:{key}"))


def _relation_uuid(repository_uid: str, relation_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"soma-research-map:{repository_uid}:relation:{relation_id}",
        )
    )


def _canonical_map_json(value: dict[str, list[str]]) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def build_backend_projection(
    manifest: ProjectManifest,
    scan: SidecarScanResult,
    desired_state: DesiredStateResult,
) -> BackendProjection:
    """Project already-reviewed sidecars into backend-neutral graph records.

    This function performs no semantic inference. It only carries reviewed
    relation fields into a deterministic primitive representation suitable for
    optional graph backends.
    """

    effective_lifecycle = {
        relation.relation_id: relation.effective_lifecycle
        for relation in desired_state.governance.relations
    }
    nodes_by_key: dict[str, ProjectedNode] = {}
    relations: list[ProjectedRelation] = []

    for record in sorted(scan.records, key=lambda item: item.source_path):
        if record.sidecar_state is not SidecarState.VALID or record.sidecar is None:
            continue
        if record.canonical_text_sha256 is None:
            raise ResearchMapProjectionError(
                f"valid sidecar is missing canonical source hash: {record.source_path}"
            )

        record_facets_json = _canonical_map_json(record.sidecar.facets)
        for relation in sorted(record.sidecar.relations, key=lambda item: item.relation_id):
            for semantic_node in (relation.subject, relation.object):
                existing = nodes_by_key.get(semantic_node.key)
                projected = ProjectedNode(
                    uuid=_node_uuid(manifest.repository_uid, semantic_node.key),
                    key=semantic_node.key,
                    label=semantic_node.label,
                )
                if existing is not None and existing.label != projected.label:
                    raise ResearchMapProjectionError(
                        "semantic node key has conflicting reviewed labels: "
                        f"{semantic_node.key}"
                    )
                nodes_by_key[semantic_node.key] = projected

            lifecycle = effective_lifecycle.get(relation.relation_id, relation.lifecycle)
            if not isinstance(lifecycle, RelationLifecycle):
                lifecycle = RelationLifecycle(str(lifecycle))
            relations.append(
                ProjectedRelation(
                    uuid=_relation_uuid(manifest.repository_uid, relation.relation_id),
                    relation_id=relation.relation_id,
                    source_node_uuid=nodes_by_key[relation.subject.key].uuid,
                    target_node_uuid=nodes_by_key[relation.object.key].uuid,
                    source_key=relation.subject.key,
                    target_key=relation.object.key,
                    predicate=relation.predicate.value,
                    statement=relation.statement,
                    source_path=record.source_path,
                    source_canonical_text_sha256=record.canonical_text_sha256,
                    source_anchor=relation.locator.anchor,
                    epistemic_class=relation.epistemic_class.value,
                    lifecycle=lifecycle.value,
                    record_facets_json=record_facets_json,
                    facets_json=_canonical_map_json(relation.facets),
                    qualifiers_json=_canonical_map_json(relation.qualifiers),
                )
            )

    relations.sort(key=lambda item: item.relation_id)
    relation_ids = [item.relation_id for item in relations]
    if len(relation_ids) != len(set(relation_ids)):
        raise ResearchMapProjectionError("backend projection contains duplicate relation IDs")

    return BackendProjection(
        repository_uid=manifest.repository_uid,
        semantic_desired_state_sha256=desired_state.semantic_desired_state_sha256,
        nodes=tuple(sorted(nodes_by_key.values(), key=lambda item: item.key)),
        relations=tuple(relations),
    )
