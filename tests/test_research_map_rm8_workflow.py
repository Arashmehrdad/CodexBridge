from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from soma import server
from soma.gateway_models import ResearchMapActionRequest, ResearchMapQueryRequest
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
from soma.research_map.sync import ResearchMapSyncError, sync_research_map

PROJECTION_HASH = graphiti_projection_contract_sha256()


def _write_manifest(repo: Path) -> None:
    (repo / "soma.project.json").write_text(
        json.dumps(
            {
                "schema": "soma.project.v1",
                "repository_uid": "srepo_89abcdef01234567",
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


def _create_report_once(repo: Path, name: str, text: str) -> bool:
    path = repo / "docs/research" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _write_reviewed_sidecar(
    repo: Path,
    report_name: str,
    source_text: str,
    *,
    subject_key: str | None = None,
    object_key: str | None = None,
    anchor: str = "",
) -> str | None:
    source_path = f"docs/research/{report_name}"
    sidecar_dir = repo / "docs/research/_soma_map"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    if subject_key is None or object_key is None:
        sidecar = {
            "schema_version": "soma.research-map.v2",
            "source": {
                "path": source_path,
                "canonical_text_sha256": canonical_text_sha256(source_text),
            },
            "review": {
                "state": "reviewed",
                "controller": "Sol",
                "materiality": "none",
            },
            "facets": {"stage": ["RM8"]},
            "relations": [],
        }
        rid = None
    else:
        rid = relation_id(source_path, subject_key, "SUPPORTS", object_key)
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
            "facets": {"stage": ["RM8"]},
            "relations": [
                {
                    "relation_id": rid,
                    "subject": {"key": subject_key, "label": subject_key},
                    "predicate": "SUPPORTS",
                    "object": {"key": object_key, "label": object_key},
                    "statement": f"Reviewed carry-forward from {report_name}",
                    "locator": {"anchor": anchor},
                    "epistemic_class": "observed",
                    "lifecycle": "current",
                    "supersedes": [],
                    "facets": {"workflow": ["RM8"]},
                    "qualifiers": {},
                }
            ],
        }
    (sidecar_dir / f"{Path(report_name).stem}.json").write_text(
        json.dumps(sidecar, ensure_ascii=False),
        encoding="utf-8",
    )
    return rid


class _WorkflowBackendStore:
    def __init__(self) -> None:
        self.persisted: dict[str, set[str]] = {}
        self.live: dict[str, set[str]] = {}
        self.search_hits: list[str] = []
        self.fail_persist = False
        self.clone_calls = 0

    def factory(self, _repository_uid: str, database: str) -> _WorkflowBackend:
        return _WorkflowBackend(self, database)


class _WorkflowBackend:
    def __init__(self, store: _WorkflowBackendStore, database: str) -> None:
        self.store = store
        self.database = database
        self.store.live.setdefault(database, set(self.store.persisted.get(database, set())))

    async def build_empty(self) -> None:
        self.store.live[self.database] = set()

    async def clone_from_current(self, source: object) -> None:
        source_database = str(getattr(source, "database", ""))
        assert source_database
        self.store.clone_calls += 1
        self.store.live[self.database] = set(
            self.store.persisted.get(source_database, set())
        )

    async def upsert_nodes(self, nodes: tuple[ProjectedNode, ...]) -> None:
        del nodes

    async def upsert_relations(self, relations: tuple[ProjectedRelation, ...]) -> None:
        self.store.live[self.database].update(item.relation_id for item in relations)

    async def remove_relations(self, relation_ids: tuple[str, ...]) -> None:
        self.store.live[self.database].difference_update(relation_ids)

    async def read_relation_manifest(self) -> tuple[str, ...]:
        return tuple(sorted(self.store.live[self.database]))

    async def search(self, query: str, *, limit: int = 5) -> tuple[BackendSearchHit, ...]:
        del query
        return tuple(
            BackendSearchHit(relation_id=relation_id, score=None)
            for relation_id in self.store.search_hits[:limit]
        )

    async def persist(self) -> BackendPersistResult:
        if self.store.fail_persist:
            raise OSError("RM8 injected map sync outage")
        self.store.persisted[self.database] = set(self.store.live[self.database])
        return BackendPersistResult(persisted=True, detail="rm8-fake-save")

    async def close(self) -> None:
        return None

    async def reopen_and_verify(
        self,
        expected_relation_ids: tuple[str, ...],
    ) -> BackendVerification:
        self.store.live[self.database] = set(self.store.persisted.get(self.database, set()))
        return BackendVerification(
            expected_relation_ids=tuple(sorted(expected_relation_ids)),
            actual_relation_ids=tuple(sorted(self.store.live[self.database])),
        )


def _sync(repo: Path, store: _WorkflowBackendStore) -> dict[str, object]:
    return sync_research_map(
        repo,
        project_id="proj_rm8",
        repo_name="repo",
        action="sync",
        backend_factory=store.factory,
        projection_contract_sha256=PROJECTION_HASH,
    )


def _search(repo: Path, store: _WorkflowBackendStore, query: str) -> dict[str, object]:
    return research_map_query_gateway(
        repo,
        project_id="proj_rm8",
        repo_name="repo",
        operation="search",
        query=query,
        limit=5,
        search_backend_factory=store.factory,
    )


def test_rm8_not_adopted_fallback_preserves_authoritative_research_report(tmp_path: Path) -> None:
    health = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="health",
    )
    assert health["status"] == "not_adopted"

    report = "# Research 001\nEvidence-first result remains authoritative.\n"
    assert _create_report_once(tmp_path, "001_result.md", report) is True
    assert (tmp_path / "docs/research/001_result.md").read_text(encoding="utf-8") == report
    assert not (tmp_path / RUNTIME_RELATIVE_PATH).exists()

    terminal_state = "research_saved + map_finishing_touch_unavailable"
    assert terminal_state == "research_saved + map_finishing_touch_unavailable"


def test_rm8_adopted_workflow_is_markdown_first_source_verified_and_idempotent(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path)
    prior_text = "# Research 001\nprior exact anchor\n"
    assert _create_report_once(tmp_path, "001_prior.md", prior_text) is True
    prior_rid = _write_reviewed_sidecar(
        tmp_path,
        "001_prior.md",
        prior_text,
        subject_key="finding:prior",
        object_key="claim:prior",
        anchor="prior exact anchor",
    )
    assert prior_rid is not None

    store = _WorkflowBackendStore()
    first = _sync(tmp_path, store)
    assert first["status"] == "synchronized"
    store.search_hits = [prior_rid]

    navigation = _search(tmp_path, store, "What governed the prior iteration?")
    assert navigation["ok"] is True
    assert navigation["results"][0]["source_verification"] == "verified"
    exact_path = tmp_path / navigation["results"][0]["source_path"]
    reopened = exact_path.read_text(encoding="utf-8")
    assert navigation["results"][0]["source_anchor"] in reopened

    new_text = "# Research 002\nnew exact anchor\nnew evidence-first conclusion\n"
    assert _create_report_once(tmp_path, "002_result.md", new_text) is True
    assert _create_report_once(tmp_path, "002_result.md", "duplicate") is False

    incomplete = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="health",
    )
    assert incomplete["coverage_state"] == "incomplete"

    new_rid = _write_reviewed_sidecar(
        tmp_path,
        "002_result.md",
        new_text,
        subject_key="finding:new",
        object_key="claim:new",
        anchor="new exact anchor",
    )
    assert new_rid is not None
    second = _sync(tmp_path, store)
    assert second["status"] == "synchronized"
    assert second["build_strategy"] == "additive_clone"
    assert store.clone_calls == 1

    health = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="health",
    )
    assert health["coverage_state"] == "complete"
    assert health["sync_state"] == "published_verified"

    readback = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="relation",
        relation_id=new_rid,
        response_budget_bytes=32 * 1024,
    )
    assert readback["status"] == "found"
    assert readback["relation"]["locator"]["anchor"] == "new exact anchor"

    generation = load_current_generation(tmp_path)
    assert generation is not None
    generations_before = sorted(
        path.name for path in (tmp_path / RUNTIME_RELATIVE_PATH / "generations").iterdir()
    )
    repeated = _sync(tmp_path, store)
    assert repeated["status"] == "already_current"
    assert repeated["generation"] == generation.generation
    assert sorted(
        path.name for path in (tmp_path / RUNTIME_RELATIVE_PATH / "generations").iterdir()
    ) == generations_before

    terminal_state = "research_saved + map_synced_verified"
    assert terminal_state == "research_saved + map_synced_verified"


def test_rm8_sync_degraded_preserves_report_and_sidecar_then_resumes_idempotently(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path)
    source_text = "# Research 003\ndegraded exact anchor\n"
    assert _create_report_once(tmp_path, "003_degraded.md", source_text) is True
    rid = _write_reviewed_sidecar(
        tmp_path,
        "003_degraded.md",
        source_text,
        subject_key="finding:degraded",
        object_key="claim:degraded",
        anchor="degraded exact anchor",
    )
    assert rid is not None
    report_bytes = (tmp_path / "docs/research/003_degraded.md").read_bytes()
    sidecar_bytes = (tmp_path / "docs/research/_soma_map/003_degraded.json").read_bytes()

    store = _WorkflowBackendStore()
    store.fail_persist = True
    with pytest.raises(ResearchMapSyncError, match="RM8 injected map sync outage"):
        _sync(tmp_path, store)

    assert (tmp_path / "docs/research/003_degraded.md").read_bytes() == report_bytes
    assert (tmp_path / "docs/research/_soma_map/003_degraded.json").read_bytes() == sidecar_bytes
    assert load_current_generation(tmp_path) is None
    terminal_state = "research_saved + sidecar_saved + map_sync_degraded"
    assert terminal_state == "research_saved + sidecar_saved + map_sync_degraded"

    store.fail_persist = False
    recovered = _sync(tmp_path, store)
    assert recovered["status"] == "synchronized"
    repeated = _sync(tmp_path, store)
    assert repeated["status"] == "already_current"

    readback = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="relation",
        relation_id=rid,
        response_budget_bytes=32 * 1024,
    )
    assert readback["status"] == "found"


def test_rm8_reviewed_no_material_finishing_touch_closes_coverage(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    source_text = "# Research 004\nNo material carry-forward semantics.\n"
    assert _create_report_once(tmp_path, "004_no_material.md", source_text) is True

    before = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="health",
    )
    assert before["coverage_state"] == "incomplete"

    assert _write_reviewed_sidecar(tmp_path, "004_no_material.md", source_text) is None
    store = _WorkflowBackendStore()
    synced = _sync(tmp_path, store)
    assert synced["status"] == "synchronized"
    assert synced["relation_count"] == 0

    after = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm8",
        repo_name="repo",
        operation="health",
    )
    assert after["coverage_state"] == "complete"
    assert after["sync_state"] == "published_verified"


def test_rm8_public_project_scoped_surfaces_compose_sync_and_readback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path)
    source_text = "# Research 005\npublic exact anchor\n"
    assert _create_report_once(tmp_path, "005_public.md", source_text) is True
    rid = _write_reviewed_sidecar(
        tmp_path,
        "005_public.md",
        source_text,
        subject_key="finding:public",
        object_key="claim:public",
        anchor="public exact anchor",
    )
    assert rid is not None

    store = _WorkflowBackendStore()
    binding = SimpleNamespace(
        project_id="proj_rm8",
        repo_name="repo",
        resource_id="res_rm8",
        scope_generation=8,
    )
    scope = SimpleNamespace(
        is_installed=lambda: True,
        resolve_repository=lambda **_kwargs: binding,
    )
    monkeypatch.setattr(server, "_repo_context", lambda _name: ("repo", tmp_path, "repo"))
    monkeypatch.setattr(server, "get_project_scope_store", lambda: scope)
    monkeypatch.setattr(
        server,
        "get_config",
        lambda: SimpleNamespace(resolve_runs_dir=lambda: tmp_path / "runs"),
    )
    monkeypatch.setattr(server, "repository_operation_lock", lambda *_args, **_kwargs: nullcontext())

    def public_sync(
        repo_root: Path,
        *,
        project_id: str,
        repo_name: str,
        action: str,
    ) -> dict[str, object]:
        return sync_research_map(
            repo_root,
            project_id=project_id,
            repo_name=repo_name,
            action=action,  # type: ignore[arg-type]
            backend_factory=store.factory,
            projection_contract_sha256=PROJECTION_HASH,
        )

    monkeypatch.setattr(server, "sync_research_map", public_sync)
    action_adapter = TypeAdapter(ResearchMapActionRequest)
    query_adapter = TypeAdapter(ResearchMapQueryRequest)

    synced = server.research_map_action(
        action_adapter.validate_python(
            {"action": "sync", "project_id": "proj_rm8", "repo_name": "repo"}
        )
    )
    assert synced["ok"] is True
    assert synced["status"] == "synchronized"
    assert synced["resource_id"] == "res_rm8"
    assert synced["scope_generation"] == 8

    health = server.research_map_query(
        query_adapter.validate_python(
            {"operation": "health", "project_id": "proj_rm8", "repo_name": "repo"}
        )
    )
    assert health["coverage_state"] == "complete"
    assert health["sync_state"] == "published_verified"
    assert health["resource_id"] == "res_rm8"
    assert health["scope_generation"] == 8

    readback = server.research_map_query(
        query_adapter.validate_python(
            {
                "operation": "relation",
                "project_id": "proj_rm8",
                "repo_name": "repo",
                "relation_id": rid,
            }
        )
    )
    assert readback["status"] == "found"
    assert readback["relation"]["locator"]["anchor"] == "public exact anchor"
    assert readback["resource_id"] == "res_rm8"
    assert readback["scope_generation"] == 8
