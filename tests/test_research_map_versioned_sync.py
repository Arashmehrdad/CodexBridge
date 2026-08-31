from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from soma.research_map import canonical_text_sha256, relation_id, scan_research_map
from soma.research_map.backend import (
    BackendPersistResult,
    BackendSearchHit,
    BackendVerification,
    ProjectedNode,
    ProjectedRelation,
    build_backend_projection,
)
from soma.research_map.generation import (
    RELATIONS_FILENAME,
    RUNTIME_RELATIVE_PATH,
    VERSIONED_STORAGE_MODE,
    generation_directory,
    load_current_generation,
)
from soma.research_map.graphiti_backend import (
    GraphitiFalkorBackend,
    graphiti_projection_contract_sha256,
)
from soma.research_map.manifest import load_project_manifest
from soma.research_map.sync import ResearchMapInjectedFailure, sync_research_map
from soma.research_map.versioned_sync import verify_versioned_current
from soma.research_map.versioning import version_backend_projection

PROJECTION_HASH = graphiti_projection_contract_sha256()


def _write_repo(repo: Path, *, statement: str = "statement one") -> str:
    source_path = "docs/research/001_versioned.md"
    source_text = "# Versioned\nexact anchor\n"
    sidecar_dir = repo / "docs/research/_soma_map"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    (repo / source_path).write_text(source_text, encoding="utf-8")
    (repo / "soma.project.json").write_text(
        json.dumps(
            {
                "schema": "soma.project.v1",
                "repository_uid": "srepo_0123456789abcdef",
                "research_map": {
                    "enabled": True,
                    "schema": "soma.research-map.v2",
                    "roots": [
                        {
                            "path": "docs/research",
                            "sidecar_dir": "_soma_map",
                            "include": ["*.md"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    rid = relation_id(source_path, "finding:versioned", "SUPPORTS", "claim:versioned")
    sidecar = {
        "schema_version": "soma.research-map.v2",
        "source": {
            "path": source_path,
            "canonical_text_sha256": canonical_text_sha256(source_text),
        },
        "review": {
            "state": "reviewed",
            "controller": "Sol",
            "materiality": "material",
        },
        "facets": {},
        "relations": [
            {
                "relation_id": rid,
                "subject": {"key": "finding:versioned", "label": "Versioned finding"},
                "predicate": "SUPPORTS",
                "object": {"key": "claim:versioned", "label": "Versioned claim"},
                "statement": statement,
                "locator": {"anchor": "exact anchor"},
                "epistemic_class": "observed",
                "lifecycle": "current",
                "supersedes": [],
                "facets": {},
                "qualifiers": {},
            }
        ],
    }
    (sidecar_dir / "001_versioned.json").write_text(
        json.dumps(sidecar, ensure_ascii=False),
        encoding="utf-8",
    )
    return rid


def _rewrite_statement(repo: Path, statement: str) -> None:
    path = repo / "docs/research/_soma_map/001_versioned.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["relations"][0]["statement"] = statement
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _current_edge_uuid(repo: Path) -> str:
    current = load_current_generation(repo)
    assert current is not None
    payload = json.loads(
        (generation_directory(repo, current.generation) / RELATIONS_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    return str(payload["relations"][0]["uuid"])


class _VersionedStore:
    def __init__(self) -> None:
        self.persisted_edges: dict[str, dict[str, str]] = {}
        self.live_edges: dict[str, dict[str, str]] = {}
        self.persisted_nodes: dict[str, set[str]] = {}
        self.live_nodes: dict[str, set[str]] = {}
        self.calls: list[tuple[str, str, int]] = []

    def factory(self, _repository_uid: str, database: str) -> _VersionedBackend:
        return _VersionedBackend(self, database)


class _VersionedBackend:
    def __init__(self, store: _VersionedStore, database: str) -> None:
        self.store = store
        self.database = database
        self.store.live_edges.setdefault(
            database,
            dict(self.store.persisted_edges.get(database, {})),
        )
        self.store.live_nodes.setdefault(
            database,
            set(self.store.persisted_nodes.get(database, set())),
        )

    async def build_empty(self) -> None:
        self.store.calls.append(("build_empty", self.database, 0))
        self.store.live_edges[self.database] = {}
        self.store.live_nodes[self.database] = set()

    async def clone_from_current(self, source: object) -> None:
        del source
        raise AssertionError("versioned sync never clones")

    async def upsert_nodes(self, nodes: tuple[ProjectedNode, ...]) -> None:
        self.store.calls.append(("upsert_nodes", self.database, len(nodes)))
        self.store.live_nodes[self.database].update(node.uuid for node in nodes)

    async def upsert_relations(self, relations: tuple[ProjectedRelation, ...]) -> None:
        self.store.calls.append(("upsert_relations", self.database, len(relations)))
        for relation in relations:
            self.store.live_edges[self.database][relation.uuid] = relation.relation_id

    async def remove_relations(self, relation_ids: tuple[str, ...]) -> None:
        raise AssertionError(f"append-only sync must not delete {relation_ids!r}")

    async def read_relation_manifest(self) -> tuple[str, ...]:
        return tuple(sorted(self.store.live_edges[self.database].values()))

    async def read_relation_manifest_for_uuids(
        self,
        edge_uuids: tuple[str, ...],
    ) -> tuple[str, ...]:
        edges = self.store.live_edges[self.database]
        return tuple(sorted(edges[uuid] for uuid in edge_uuids if uuid in edges))

    async def search_relation_versions(
        self,
        query: str,
        *,
        edge_uuids: tuple[str, ...],
        limit: int = 5,
    ) -> tuple[BackendSearchHit, ...]:
        del query
        edges = self.store.live_edges[self.database]
        return tuple(
            BackendSearchHit(relation_id=edges[uuid], score=None)
            for uuid in edge_uuids
            if uuid in edges
        )[:limit]

    async def search(self, query: str, *, limit: int = 5) -> tuple[BackendSearchHit, ...]:
        del query, limit
        raise AssertionError("versioned search must use exact edge UUID filtering")

    async def persist(self) -> BackendPersistResult:
        self.store.calls.append(("persist", self.database, 0))
        self.store.persisted_edges[self.database] = dict(self.store.live_edges[self.database])
        self.store.persisted_nodes[self.database] = set(self.store.live_nodes[self.database])
        return BackendPersistResult(persisted=True, detail="fake-save")

    async def close(self) -> None:
        return None

    async def reopen_and_verify(
        self,
        expected_relation_ids: tuple[str, ...],
    ) -> BackendVerification:
        self.store.live_edges[self.database] = dict(
            self.store.persisted_edges.get(self.database, {})
        )
        actual = tuple(sorted(self.store.live_edges[self.database].values()))
        return BackendVerification(
            expected_relation_ids=tuple(sorted(expected_relation_ids)),
            actual_relation_ids=actual,
        )


def _sync(
    repo: Path,
    store: _VersionedStore,
    *,
    action: str = "sync",
    failure_point: str | None = None,
) -> dict[str, object]:
    return sync_research_map(
        repo,
        project_id="proj_versioned",
        repo_name="repo",
        action=action,  # type: ignore[arg-type]
        backend_factory=store.factory,
        projection_contract_sha256=PROJECTION_HASH,
        failure_point=failure_point,
    )


def test_content_addressing_reuses_nodes_but_versions_changed_relation(tmp_path: Path) -> None:
    _write_repo(tmp_path, statement="one")
    manifest = load_project_manifest(tmp_path).manifest
    scan = scan_research_map(tmp_path)
    assert manifest is not None and scan.desired_state is not None
    first = version_backend_projection(
        build_backend_projection(manifest, scan.sidecar_scan, scan.desired_state)
    )

    _rewrite_statement(tmp_path, "two")
    scan = scan_research_map(tmp_path)
    assert scan.desired_state is not None
    second = version_backend_projection(
        build_backend_projection(manifest, scan.sidecar_scan, scan.desired_state)
    )

    assert [node.uuid for node in first.nodes] == [node.uuid for node in second.nodes]
    assert first.relations[0].relation_id == second.relations[0].relation_id
    assert first.relations[0].uuid != second.relations[0].uuid


def test_normal_sync_reuses_database_and_writes_only_changed_relation_version(tmp_path: Path) -> None:
    rid = _write_repo(tmp_path, statement="one")
    store = _VersionedStore()
    first = _sync(tmp_path, store)
    first_edge_uuid = _current_edge_uuid(tmp_path)
    first_database = str(first["database"])

    _rewrite_statement(tmp_path, "two")
    calls_before = len(store.calls)
    second = _sync(tmp_path, store)
    second_edge_uuid = _current_edge_uuid(tmp_path)
    second_calls = store.calls[calls_before:]

    assert first["storage_mode"] == VERSIONED_STORAGE_MODE
    assert first["build_strategy"] == "full_versioned_rebuild"
    assert second["database"] == first_database
    assert second["build_strategy"] == "incremental_versioned_append"
    assert second["delta"] == {
        "added_nodes": 0,
        "reused_nodes": 2,
        "retired_node_versions": 0,
        "added_relations": 1,
        "reused_relations": 0,
        "retired_relation_versions": 1,
        "backend_mutated": True,
    }
    assert first_edge_uuid != second_edge_uuid
    assert store.persisted_edges[first_database][first_edge_uuid] == rid
    assert store.persisted_edges[first_database][second_edge_uuid] == rid
    assert not any(call[0] == "build_empty" for call in second_calls)
    assert ("upsert_nodes", first_database, 0) in second_calls
    assert ("upsert_relations", first_database, 1) in second_calls


def test_unchanged_versioned_sync_verifies_without_republishing(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    store = _VersionedStore()
    first = _sync(tmp_path, store)
    before_calls = len(store.calls)

    second = _sync(tmp_path, store)

    assert second["status"] == "already_current"
    assert second["generation"] == first["generation"]
    assert second["published"] is False
    assert not any(call[0].startswith("upsert") for call in store.calls[before_calls:])


def test_prepublish_failure_leaves_current_pointer_and_old_versions_intact(tmp_path: Path) -> None:
    _write_repo(tmp_path, statement="one")
    store = _VersionedStore()
    first = _sync(tmp_path, store)
    current_before = (tmp_path / RUNTIME_RELATIVE_PATH / "CURRENT.json").read_bytes()
    first_edge_uuid = _current_edge_uuid(tmp_path)

    _rewrite_statement(tmp_path, "two")
    with pytest.raises(ResearchMapInjectedFailure):
        _sync(tmp_path, store, failure_point="before_current_publish")

    assert (tmp_path / RUNTIME_RELATIVE_PATH / "CURRENT.json").read_bytes() == current_before
    current = load_current_generation(tmp_path)
    assert current is not None
    assert current.generation == first["generation"]
    assert len(store.persisted_edges[current.database]) == 2
    assert first_edge_uuid in store.persisted_edges[current.database]
    assert asyncio.run(
        verify_versioned_current(
            tmp_path,
            current,
            repository_uid=current.repository_uid,
            backend_factory=store.factory,
        )
    )


def test_explicit_rebuild_creates_fresh_physical_lineage_database(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    store = _VersionedStore()
    first = _sync(tmp_path, store)
    first_database = str(first["database"])

    rebuilt = _sync(tmp_path, store, action="rebuild")

    assert rebuilt["build_strategy"] == "full_versioned_rebuild"
    assert rebuilt["database"] != first_database
    assert first_database in store.persisted_edges
    assert str(rebuilt["database"]) in store.persisted_edges
    assert store.persisted_edges[first_database]
    assert store.persisted_edges[str(rebuilt["database"])]


def test_graphiti_versioned_search_uses_exact_edge_uuid_vectors() -> None:
    captured: dict[str, object] = {}
    relation_a = "rel_" + "a" * 64
    relation_b = "rel_" + "b" * 64
    relation_c = "rel_" + "c" * 64

    class FakeDriver:
        async def execute_query(self, query: str, **kwargs: object) -> tuple[list[dict[str, object]], list[str], None]:
            captured.update(query=query, edge_uuids=list(kwargs["edge_uuids"]))
            return (
                [
                    {"relation_id": relation_b, "embedding": [0.0, 1.0]},
                    {"relation_id": relation_c, "embedding": [-1.0, 0.0]},
                    {"relation_id": relation_a, "embedding": [1.0, 0.0]},
                ],
                ["relation_id", "embedding"],
                None,
            )

    class FakeEmbedder:
        async def create(self, query: str) -> list[float]:
            captured["semantic_query"] = query
            return [1.0, 0.0]

    backend = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="srm_" + "a" * 32,
    )
    backend._driver = FakeDriver()
    backend._embedder = FakeEmbedder()

    hits = asyncio.run(
        backend.search_relation_versions(
            "constraint",
            edge_uuids=("edge-b", "edge-a"),
            limit=2,
        )
    )

    assert captured["edge_uuids"] == ["edge-b", "edge-a"]
    assert "r.uuid IN $edge_uuids" in str(captured["query"])
    assert captured["semantic_query"] == "constraint"
    assert [hit.relation_id for hit in hits] == [relation_a, relation_b]
    assert [hit.score for hit in hits] == pytest.approx([1.0, 0.0])
