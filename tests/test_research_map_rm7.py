from __future__ import annotations

import hashlib
import json
from pathlib import Path

from soma.research_map import canonical_text_sha256, relation_id
from soma.research_map.backend import (
    BackendPersistResult,
    BackendSearchHit,
    BackendVerification,
    ProjectedNode,
    ProjectedRelation,
)
from soma.research_map.gateway import research_map_query_gateway
from soma.research_map.generation import RUNTIME_RELATIVE_PATH, load_current_generation
from soma.research_map.graphiti_backend import graphiti_projection_contract_sha256
from soma.research_map.sync import sync_research_map

PROJECTION_HASH = graphiti_projection_contract_sha256()


def _write_reviewed_repo(repo: Path, *, large_statement: bool = False) -> tuple[str, str]:
    source_path = "docs/research/001_rm7.md"
    source_text = "# RM7\nold anchor\ncurrent anchor\n"
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
    old_id = relation_id(source_path, "finding:old", "SUPPORTS", "claim:old")
    current_id = relation_id(source_path, "finding:current", "SUPPORTS", "claim:current")
    statement = "current governing statement"
    if large_statement:
        statement += " " + "x" * 20_000
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
        "facets": {"programme": ["RM7"]},
        "relations": [
            {
                "relation_id": old_id,
                "subject": {"key": "finding:old", "label": "Old finding"},
                "predicate": "SUPPORTS",
                "object": {"key": "claim:old", "label": "Old claim"},
                "statement": "historical statement",
                "locator": {"anchor": "old anchor"},
                "epistemic_class": "observed",
                "lifecycle": "current",
                "supersedes": [],
                "facets": {},
                "qualifiers": {},
            },
            {
                "relation_id": current_id,
                "subject": {"key": "finding:current", "label": "Current finding"},
                "predicate": "SUPPORTS",
                "object": {"key": "claim:current", "label": "Current claim"},
                "statement": statement,
                "locator": {"anchor": "current anchor"},
                "epistemic_class": "observed",
                "lifecycle": "current",
                "supersedes": [old_id],
                "facets": {},
                "qualifiers": {},
            },
        ],
    }
    (sidecar_dir / "001_rm7.json").write_text(
        json.dumps(sidecar, ensure_ascii=False),
        encoding="utf-8",
    )
    return old_id, current_id


class _SearchBackendStore:
    def __init__(self) -> None:
        self.persisted: dict[str, set[str]] = {}
        self.live: dict[str, set[str]] = {}
        self.search_hits: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.manifest_error: Exception | None = None

    def factory(self, _repository_uid: str, database: str) -> _SearchBackend:
        return _SearchBackend(self, database)


class _SearchBackend:
    def __init__(self, store: _SearchBackendStore, database: str) -> None:
        self.store = store
        self.database = database
        self.store.live.setdefault(database, set(self.store.persisted.get(database, set())))

    async def build_empty(self) -> None:
        self.store.calls.append(("build_empty", self.database))
        self.store.live[self.database] = set()

    async def clone_from_current(self, source: object) -> None:
        del source
        raise AssertionError("RM7 tests do not clone")

    async def upsert_nodes(self, nodes: tuple[ProjectedNode, ...]) -> None:
        del nodes

    async def upsert_relations(self, relations: tuple[ProjectedRelation, ...]) -> None:
        self.store.live[self.database].update(item.relation_id for item in relations)

    async def remove_relations(self, relation_ids: tuple[str, ...]) -> None:
        self.store.live[self.database].difference_update(relation_ids)

    async def read_relation_manifest(self) -> tuple[str, ...]:
        self.store.calls.append(("read_manifest", self.database))
        if self.store.manifest_error is not None:
            raise self.store.manifest_error
        return tuple(sorted(self.store.live[self.database]))

    async def search(self, query: str, *, limit: int = 5) -> tuple[BackendSearchHit, ...]:
        self.store.calls.append((f"search:{query}", self.database))
        return tuple(
            BackendSearchHit(relation_id=relation_id, score=None)
            for relation_id in self.store.search_hits[:limit]
        )

    async def persist(self) -> BackendPersistResult:
        self.store.calls.append(("persist", self.database))
        self.store.persisted[self.database] = set(self.store.live[self.database])
        return BackendPersistResult(persisted=True, detail="fake-save")

    async def close(self) -> None:
        self.store.calls.append(("close", self.database))

    async def reopen_and_verify(
        self,
        expected_relation_ids: tuple[str, ...],
    ) -> BackendVerification:
        self.store.live[self.database] = set(self.store.persisted.get(self.database, set()))
        return BackendVerification(
            expected_relation_ids=tuple(sorted(expected_relation_ids)),
            actual_relation_ids=tuple(sorted(self.store.live[self.database])),
        )


def _publish(repo: Path, store: _SearchBackendStore) -> None:
    result = sync_research_map(
        repo,
        project_id="proj_rm7",
        repo_name="repo",
        action="sync",
        backend_factory=store.factory,
        projection_contract_sha256=PROJECTION_HASH,
    )
    assert result["status"] == "synchronized"


def _search(
    repo: Path,
    store: _SearchBackendStore,
    *,
    include_noncurrent: bool = False,
    response_budget_bytes: int = 12 * 1024,
) -> dict:
    return research_map_query_gateway(
        repo,
        project_id="proj_rm7",
        repo_name="repo",
        operation="search",
        query="governing constraint",
        limit=5,
        include_noncurrent=include_noncurrent,
        response_budget_bytes=response_budget_bytes,
        search_backend_factory=store.factory,
    )


def _snapshot(repo: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (path.relative_to(repo).as_posix(), path.read_bytes())
        for path in repo.rglob("*")
        if path.is_file()
    )


def test_rm7_search_uses_only_verified_published_generation_and_is_read_only(tmp_path: Path) -> None:
    old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [old_id, current_id]
    store.calls.clear()
    before = _snapshot(tmp_path)

    first = _search(tmp_path, store)
    second = _search(tmp_path, store)

    assert first["ok"] is True
    assert first["status"] == "found"
    assert first["backend_state"] == "verified"
    assert [item["relation_id"] for item in first["results"]] == [current_id]
    candidate = first["results"][0]
    assert candidate["source_path"] == "docs/research/001_rm7.md"
    assert candidate["source_verification"] == "verified"
    assert candidate["source_canonical_text_sha256"] == canonical_text_sha256(
        (tmp_path / "docs/research/001_rm7.md").read_bytes()
    )
    assert candidate["source_anchor"] == "current anchor"
    assert second["results"] == first["results"]
    assert _snapshot(tmp_path) == before
    assert all(call[0] not in {"build_empty", "persist"} for call in store.calls)
    assert sum(call[0] == "read_manifest" for call in store.calls) == 2


def test_rm7_include_noncurrent_can_return_superseded_reviewed_relation(tmp_path: Path) -> None:
    old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [old_id, current_id]

    current_only = _search(tmp_path, store)
    with_history = _search(tmp_path, store, include_noncurrent=True)

    assert [item["relation_id"] for item in current_only["results"]] == [current_id]
    assert [item["relation_id"] for item in with_history["results"]] == [old_id, current_id]
    assert with_history["results"][0]["lifecycle"] == "superseded"


def test_rm7_stale_source_fails_before_backend_search_without_repair(tmp_path: Path) -> None:
    _old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [current_id]
    store.calls.clear()
    before_generation = load_current_generation(tmp_path)
    (tmp_path / "docs/research/001_rm7.md").write_text(
        "# RM7\nold anchor\ncurrent anchor\nchanged\n",
        encoding="utf-8",
    )
    before = _snapshot(tmp_path)

    result = _search(tmp_path, store)

    assert result["ok"] is False
    assert result["status"] == "semantic_state_degraded"
    assert result["results"] == []
    assert not any(call[0].startswith("search:") for call in store.calls)
    assert _snapshot(tmp_path) == before
    after_generation = load_current_generation(tmp_path)
    assert after_generation == before_generation


def test_rm7_backend_drift_fails_closed_without_rebuild(tmp_path: Path) -> None:
    _old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    current = load_current_generation(tmp_path)
    assert current is not None
    store.search_hits = [current_id]
    store.live[current.database].add("rel_" + "f" * 64)
    store.calls.clear()
    before = _snapshot(tmp_path)
    generations_before = sorted(
        path.name for path in (tmp_path / RUNTIME_RELATIVE_PATH / "generations").iterdir()
    )

    result = _search(tmp_path, store)

    assert result["ok"] is False
    assert result["status"] == "backend_drift"
    assert result["backend_state"] == "drifted"
    assert not any(call[0].startswith("search:") for call in store.calls)
    assert _snapshot(tmp_path) == before
    assert sorted(
        path.name for path in (tmp_path / RUNTIME_RELATIVE_PATH / "generations").iterdir()
    ) == generations_before


def test_rm7_backend_outage_is_bounded_and_does_not_stage_generation(tmp_path: Path) -> None:
    _old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [current_id]
    store.manifest_error = OSError("x" * 100_000)
    before = _snapshot(tmp_path)

    result = _search(tmp_path, store, response_budget_bytes=4 * 1024)

    assert result["ok"] is False
    assert result["status"] == "backend_runtime_failure"
    assert result["backend_state"] == "unavailable"
    assert result["results"] == []
    assert len(result["error"]) <= 1_000
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4 * 1024
    assert _snapshot(tmp_path) == before


def test_rm7_unknown_backend_hit_is_detected_as_drift(tmp_path: Path) -> None:
    _old_id, _current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = ["rel_" + "e" * 64]
    before = _snapshot(tmp_path)

    result = _search(tmp_path, store)

    assert result["ok"] is False
    assert result["status"] == "backend_drift"
    assert result["results"] == []
    assert _snapshot(tmp_path) == before


def test_rm7_corrupt_published_generation_is_rejected_before_backend_io(tmp_path: Path) -> None:
    _old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [current_id]
    current = load_current_generation(tmp_path)
    assert current is not None
    relations_path = (
        tmp_path
        / RUNTIME_RELATIVE_PATH
        / "generations"
        / current.generation
        / "RELATIONS.json"
    )
    relations_path.write_text("{corrupt", encoding="utf-8")
    store.calls.clear()
    before = _snapshot(tmp_path)

    result = _search(tmp_path, store)

    assert result["ok"] is False
    assert result["status"] == "published_generation_degraded"
    assert result["results"] == []
    assert not store.calls
    assert _snapshot(tmp_path) == before


def test_rm7_malformed_published_source_path_is_artifact_corruption(tmp_path: Path) -> None:
    _old_id, current_id = _write_reviewed_repo(tmp_path)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [current_id]
    current = load_current_generation(tmp_path)
    assert current is not None
    relations_path = (
        tmp_path
        / RUNTIME_RELATIVE_PATH
        / "generations"
        / current.generation
        / "RELATIONS.json"
    )
    payload = json.loads(relations_path.read_text(encoding="utf-8"))
    payload["relations"][0]["source_path"] = "../escape.md"
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    relations_path.write_bytes(raw)
    current_path = tmp_path / RUNTIME_RELATIVE_PATH / "CURRENT.json"
    current_payload = json.loads(current_path.read_text(encoding="utf-8"))
    current_payload["relations_sha256"] = hashlib.sha256(raw).hexdigest()
    current_path.write_text(json.dumps(current_payload), encoding="utf-8")
    store.calls.clear()
    before = _snapshot(tmp_path)

    result = _search(tmp_path, store)

    assert result["ok"] is False
    assert result["status"] == "published_relation_artifact_invalid"
    assert result["results"] == []
    assert not store.calls
    assert _snapshot(tmp_path) == before


def test_rm7_search_response_is_bounded_for_pathological_statement(tmp_path: Path) -> None:
    _old_id, current_id = _write_reviewed_repo(tmp_path, large_statement=True)
    store = _SearchBackendStore()
    _publish(tmp_path, store)
    store.search_hits = [current_id]

    result = _search(tmp_path, store, response_budget_bytes=4 * 1024)

    assert result["ok"] is True
    assert result["response_bytes"] <= 4 * 1024
    assert result["truncated"] is True
    if result["results"]:
        assert "statement" in result["results"][0]["truncated_fields"]
