from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from .backend import BackendProjection, ProjectedNode, ProjectedRelation
from .canonical import canonical_json_sha256

OBJECT_VERSIONING_VERSION = "soma.research-map.object-versioning.v1"


def _version_uuid(repository_uid: str, kind: str, payload: dict[str, object]) -> str:
    digest = canonical_json_sha256(payload)
    return str(
        uuid5(
            NAMESPACE_URL,
            f"soma-research-map:{repository_uid}:{kind}-version:{digest}",
        )
    )


def version_backend_projection(projection: BackendProjection) -> BackendProjection:
    """Return a content-addressed physical projection for append-only storage.

    Scientific relation identity remains ``relation_id``. Only the derived
    backend object UUID changes when the exact projected object content changes.
    Unchanged objects therefore keep the same physical UUID across generations
    and can be reused without rewriting them.
    """

    versioned_nodes: list[ProjectedNode] = []
    node_uuid_by_key: dict[str, str] = {}
    for node in projection.nodes:
        uuid = _version_uuid(
            projection.repository_uid,
            "node",
            {
                "schema": OBJECT_VERSIONING_VERSION,
                "key": node.key,
                "label": node.label,
            },
        )
        node_uuid_by_key[node.key] = uuid
        versioned_nodes.append(
            ProjectedNode(
                uuid=uuid,
                key=node.key,
                label=node.label,
            )
        )

    versioned_relations: list[ProjectedRelation] = []
    for relation in projection.relations:
        source_node_uuid = node_uuid_by_key[relation.source_key]
        target_node_uuid = node_uuid_by_key[relation.target_key]
        relation_payload: dict[str, object] = {
            "schema": OBJECT_VERSIONING_VERSION,
            "relation_id": relation.relation_id,
            "source_node_uuid": source_node_uuid,
            "target_node_uuid": target_node_uuid,
            "source_key": relation.source_key,
            "target_key": relation.target_key,
            "predicate": relation.predicate,
            "statement": relation.statement,
            "source_path": relation.source_path,
            "source_canonical_text_sha256": relation.source_canonical_text_sha256,
            "source_anchor": relation.source_anchor,
            "epistemic_class": relation.epistemic_class,
            "lifecycle": relation.lifecycle,
            "record_facets_json": relation.record_facets_json,
            "facets_json": relation.facets_json,
            "qualifiers_json": relation.qualifiers_json,
        }
        versioned_relations.append(
            ProjectedRelation(
                uuid=_version_uuid(
                    projection.repository_uid,
                    "relation",
                    relation_payload,
                ),
                relation_id=relation.relation_id,
                source_node_uuid=source_node_uuid,
                target_node_uuid=target_node_uuid,
                source_key=relation.source_key,
                target_key=relation.target_key,
                predicate=relation.predicate,
                statement=relation.statement,
                source_path=relation.source_path,
                source_canonical_text_sha256=relation.source_canonical_text_sha256,
                source_anchor=relation.source_anchor,
                epistemic_class=relation.epistemic_class,
                lifecycle=relation.lifecycle,
                record_facets_json=relation.record_facets_json,
                facets_json=relation.facets_json,
                qualifiers_json=relation.qualifiers_json,
            )
        )

    return BackendProjection(
        repository_uid=projection.repository_uid,
        semantic_desired_state_sha256=projection.semantic_desired_state_sha256,
        nodes=tuple(versioned_nodes),
        relations=tuple(versioned_relations),
    )
