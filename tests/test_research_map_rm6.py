from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from soma import server
from soma.gateway_models import ResearchMapActionRequest
from soma.research_map import canonical_text_sha256, relation_id, scan_research_map
from soma.research_map.backend import (
    BackendPersistResult,
    BackendSearchHit,
    BackendVerification,
    ProjectedNode,
    ProjectedRelation,
)
from soma.research_map.gateway import research_map_query_gateway
from soma.research_map.generation import (
    HEALTH_FILENAME,
    RUNTIME_RELATIVE_PATH,
    ResearchMapGenerationError,
    SyncWriterLock,
    generation_directory,
    load_current_generation,
)
from soma.research_map.graphiti_backend import graphiti_projection_contract_sha256
from soma.research_map.sync import (
    ResearchMapInjectedFailure,
    ResearchMapSyncError,
    sync_research_map,
)

PROJECTION_HASH = graphiti_projection_contract_sha256()


def _write_reviewed_repo(repo: Path, *, statement: str = "RM6 statement v1") -> str:
    source_path = "docs/research/001_rm6.md"
    source_text = "# RM6\nimmutable anchor\n"
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
    rid = relation_id(source_path, "finding:rm6", "SUPPORTS", "claim:rm6")
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
        "facets": {"programme": ["RM6"]},
        "relations": [
            {
                "relation_id": rid,
                "subject": {"key": "finding:rm6", "label": "RM6 finding"},
                "predicate": "SUPPORTS",
                "object": {"key": "claim:rm6", "label": "RM6 claim"},
                "statement": statement,
                "locator": {"anchor": "immutable anchor"},
                "epistemic_class": "observed",
                "lifecycle": "current",
                "supersedes": [],
                "facets": {"stage": ["RM6"]},
                "qualifiers": {"scope": ["immutable generation"]},
            }
        ],
    }
    (sidecar_dir / "001_rm6.json").write_text(
        json.dumps(sidecar, ensure_ascii=False),
        encoding="utf-8",
    )
    return rid


def _rewrite_statement(repo: Path, statement: str) -> None:
    path = repo / "docs/research/_soma_map/001_rm6.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["relations"][0]["statement"] = statement
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class _FakeBackendStore:
    def __init__(self) -> None:
        self.persisted: dict[str, set[str]] = {}
        self.live: dict[str, set[str]] = {}
        self.persist_calls: dict[str, int] = {}

    def factory(self, _repository_uid: str, database: str) -> _FakeBackend:
        return _FakeBackend(self, database)


class _CloneBackendStore(_FakeBackendStore):
    def __init__(self) -> None:
        super().__init__()
        self.clone_calls = 0

    def factory(self, _repository_uid: str, database: str) -> _CloneBackend:
        return _CloneBackend(self, database)


class _SlowBackendStore(_FakeBackendStore):
    def factory(self, _repository_uid: str, database: str) -> _SlowBackend:
        return _SlowBackend(self, database)


class _FakeBackend:
    def __init__(self, store: _FakeBackendStore, database: str) -> None:
        self.store = store
        self.database = database
        self.store.live.setdefault(database, set(self.store.persisted.get(database, set())))

    async def build_empty(self) -> None:
        self.store.live[self.database] = set()

    async def clone_from_current(self, source: object) -> None:
        del source
        raise AssertionError("RM6 full-build tests must not clone")

    async def upsert_nodes(self, nodes: tuple[ProjectedNode, ...]) -> None:
        del nodes

    async def upsert_relations(self, relations: tuple[ProjectedRelation, ...]) -> None:
        self.store.live[self.database].update(item.relation_id for item in relations)

    async def remove_relations(self, relation_ids: tuple[str, ...]) -> None:
        self.store.live[self.database].difference_update(relation_ids)

    async def read_relation_manifest(self) -> tuple[str, ...]:
        return tuple(sorted(self.store.live[self.database]))

    async def search(self, query: str, *, limit: int = 5) -> tuple[BackendSearchHit, ...]:
        del query, limit
        return ()

    async def persist(self) -> BackendPersistResult:
        self.store.persisted[self.database] = set(self.store.live[self.database])
        self.store.persist_calls[self.database] = self.store.persist_calls.get(self.database, 0) + 1
        return BackendPersistResult(persisted=True, detail="fake-save")

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


class _CloneBackend(_FakeBackend):
    store: _CloneBackendStore

    async def clone_from_current(self, source: object) -> None:
        source_database = str(getattr(source, "database", ""))
        assert source_database
        self.store.clone_calls += 1
        self.store.live[self.database] = set(
            self.store.persisted.get(source_database, set())
        )


class _SlowBackend(_FakeBackend):
    async def build_empty(self) -> None:
        await asyncio.sleep(0.1)
        await super().build_empty()


def _sync(repo: Path, store: _FakeBackendStore, *, action: str = "sync", failure_point: str | None = None):
    return sync_research_map(
        repo,
        project_id="proj_rm6",
        repo_name="repo",
        action=action,  # type: ignore[arg-type]
        backend_factory=store.factory,
        projection_contract_sha256=PROJECTION_HASH,
        failure_point=failure_point,
    )


def test_rm6_first_sync_publishes_only_reopen_verified_generation(tmp_path: Path) -> None:
    rid = _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()

    result = _sync(tmp_path, store)
    current = load_current_generation(tmp_path)

    assert result["status"] == "synchronized"
    assert result["published"] is True
    assert result["reopen_verified"] is True
    assert current is not None
    assert current.generation == result["generation"]
    assert current.relation_count == 1
    assert store.persisted[current.database] == {rid}
    assert store.persist_calls[current.database] == 1
    assert (tmp_path / RUNTIME_RELATIVE_PATH / ".sync.lock").is_file()
    with SyncWriterLock(tmp_path):
        pass


def test_rm6_unchanged_sync_verifies_backend_without_republishing(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)
    generations_before = sorted((tmp_path / RUNTIME_RELATIVE_PATH / "generations").iterdir())

    second = _sync(tmp_path, store)

    assert second["status"] == "already_current"
    assert second["generation"] == first["generation"]
    assert second["published"] is False
    assert sorted((tmp_path / RUNTIME_RELATIVE_PATH / "generations").iterdir()) == generations_before


def test_rm6_append_only_sync_clones_verified_current_and_writes_only_delta(
    tmp_path: Path,
) -> None:
    first_rid = _write_reviewed_repo(tmp_path)
    store = _CloneBackendStore()
    first = _sync(tmp_path, store)

    sidecar_path = tmp_path / "docs/research/_soma_map/001_rm6.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    second_rid = relation_id(
        "docs/research/001_rm6.md",
        "finding:rm6:additive",
        "SUPPORTS",
        "claim:rm6:additive",
    )
    sidecar["relations"].append(
        {
            "relation_id": second_rid,
            "subject": {"key": "finding:rm6:additive", "label": "RM6 additive finding"},
            "predicate": "SUPPORTS",
            "object": {"key": "claim:rm6:additive", "label": "RM6 additive claim"},
            "statement": "RM6 additive statement",
            "locator": {"anchor": "immutable anchor"},
            "epistemic_class": "observed",
            "lifecycle": "current",
            "supersedes": [],
            "facets": {"stage": ["RM6"]},
            "qualifiers": {"scope": ["additive clone"]},
        }
    )
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")

    second = _sync(tmp_path, store)
    current = load_current_generation(tmp_path)

    assert second["status"] == "synchronized"
    assert second["generation"] != first["generation"]
    assert second["build_strategy"] == "additive_clone"
    assert second["added_relation_count"] == 1
    assert store.clone_calls == 1
    assert current is not None
    assert store.persisted[current.database] == {first_rid, second_rid}


def test_rm6_sync_timeout_bounds_live_synchronous_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_reviewed_repo(tmp_path)
    store = _SlowBackendStore()
    monkeypatch.setattr(
        "soma.research_map.sync.RESEARCH_MAP_SYNC_TIMEOUT_SECONDS",
        0.01,
    )

    with pytest.raises(ResearchMapSyncError) as exc_info:
        _sync(tmp_path, store)

    assert exc_info.value.code == "sync_timeout"


def test_rm6_backend_drift_forces_new_generation_instead_of_trusting_current(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)
    current = load_current_generation(tmp_path)
    assert current is not None
    store.persisted[current.database].add("rel_unknown_extra")

    second = _sync(tmp_path, store)

    assert second["status"] == "synchronized"
    assert second["generation"] != first["generation"]
    repaired = load_current_generation(tmp_path)
    assert repaired is not None
    assert store.persisted[repaired.database] == {relation_id("docs/research/001_rm6.md", "finding:rm6", "SUPPORTS", "claim:rm6")}


@pytest.mark.parametrize(
    "failure_point",
    [
        "before_staging_creation",
        "after_staging_creation",
        "mid_relation_writes",
        "after_read_back",
        "before_save",
        "after_save",
        "before_current_publish",
    ],
)
def test_rm6_prepublication_crashes_preserve_previous_current(
    tmp_path: Path,
    failure_point: str,
) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)
    current_before = (tmp_path / RUNTIME_RELATIVE_PATH / "CURRENT.json").read_bytes()

    with pytest.raises(ResearchMapInjectedFailure):
        _sync(tmp_path, store, action="rebuild", failure_point=failure_point)

    assert (tmp_path / RUNTIME_RELATIVE_PATH / "CURRENT.json").read_bytes() == current_before
    current = load_current_generation(tmp_path)
    assert current is not None
    assert current.generation == first["generation"]
    assert (tmp_path / RUNTIME_RELATIVE_PATH / ".sync.lock").is_file()
    with SyncWriterLock(tmp_path):
        pass


def test_rm6_after_publish_failure_leaves_new_verified_generation_current(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)

    with pytest.raises(ResearchMapInjectedFailure):
        _sync(tmp_path, store, action="rebuild", failure_point="after_current_publish")

    current = load_current_generation(tmp_path)
    assert current is not None
    assert current.generation != first["generation"]
    assert store.persisted[current.database]


def test_rm6_statement_drift_with_same_relation_id_makes_old_generation_stale_and_syncs_new(
    tmp_path: Path,
) -> None:
    rid = _write_reviewed_repo(tmp_path, statement="statement one")
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)
    old = load_current_generation(tmp_path)
    assert old is not None

    _rewrite_statement(tmp_path, "statement two")
    live_scan = scan_research_map(tmp_path)
    assert live_scan.semantic_desired_state_sha256 != old.semantic_desired_state_sha256
    sidecar = json.loads((tmp_path / "docs/research/_soma_map/001_rm6.json").read_text(encoding="utf-8"))
    assert sidecar["relations"][0]["relation_id"] == rid

    second = _sync(tmp_path, store)
    new = load_current_generation(tmp_path)

    assert second["generation"] != first["generation"]
    assert new is not None
    assert new.semantic_desired_state_sha256 == live_scan.semantic_desired_state_sha256

    corrected = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm6",
        repo_name="repo",
        operation="relation",
        relation_id=rid,
        response_budget_bytes=32 * 1024,
    )
    assert corrected["sync_state"] == "published_verified"
    assert corrected["relation"]["statement"] == "statement two"


def test_rm6_corrupt_published_artifact_is_not_trusted_and_rebuild_restores_current(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)
    current = load_current_generation(tmp_path)
    assert current is not None
    (generation_directory(tmp_path, current.generation) / HEALTH_FILENAME).write_text("{corrupt", encoding="utf-8")

    with pytest.raises(ResearchMapGenerationError):
        load_current_generation(tmp_path)

    repaired = _sync(tmp_path, store, action="rebuild")
    current_after = load_current_generation(tmp_path)
    assert current_after is not None
    assert repaired["generation"] != first["generation"]


def test_rm6_writer_lock_fails_closed_without_overwrite(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    runtime = tmp_path / RUNTIME_RELATIVE_PATH
    runtime.mkdir(parents=True, exist_ok=True)

    with SyncWriterLock(tmp_path):
        with pytest.raises(ResearchMapSyncError, match="already held") as caught:
            _sync(tmp_path, store)
        assert caught.value.code == "backend_or_generation_failure"

    assert (runtime / ".sync.lock").is_file()
    with SyncWriterLock(tmp_path):
        pass


def test_rm6_hard_crash_releases_os_writer_lock(tmp_path: Path) -> None:
    runtime = tmp_path / RUNTIME_RELATIVE_PATH
    runtime.mkdir(parents=True, exist_ok=True)
    script = (
        "import os, sys; "
        "from soma.research_map.generation import SyncWriterLock; "
        "lock = SyncWriterLock(sys.argv[1]); lock.__enter__(); "
        "print('LOCKED', flush=True); os._exit(23)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 23
    assert completed.stdout.strip() == "LOCKED"
    assert (runtime / ".sync.lock").is_file()

    with SyncWriterLock(tmp_path):
        pass


def test_rm6_health_reports_published_then_stale_without_backend_io(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path, statement="statement one")
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)

    healthy = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm6",
        repo_name="repo",
        operation="health",
    )
    assert healthy["sync_state"] == "published_verified"
    assert healthy["backend_state"] == "not_checked"
    assert healthy["published_generation"] == first["generation"]

    _rewrite_statement(tmp_path, "statement two")
    stale = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm6",
        repo_name="repo",
        operation="health",
    )
    assert stale["sync_state"] == "stale"
    assert stale["backend_state"] == "not_checked"
    assert stale["published_generation"] == first["generation"]


def test_rm6_current_rejects_path_escape_and_metadata_mismatch(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    _sync(tmp_path, store)
    current_path = tmp_path / RUNTIME_RELATIVE_PATH / "CURRENT.json"
    payload = json.loads(current_path.read_text(encoding="utf-8"))
    payload["generation"] = "../../outside"
    current_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResearchMapGenerationError, match="generation identity"):
        load_current_generation(tmp_path)


def test_rm6_untyped_backend_failure_is_bounded(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)

    class BrokenBackend(_FakeBackend):
        async def build_empty(self) -> None:
            raise OSError("backend socket failed")

    store = _FakeBackendStore()

    def broken_factory(_repository_uid: str, database: str) -> BrokenBackend:
        return BrokenBackend(store, database)

    with pytest.raises(ResearchMapSyncError, match="backend socket failed") as caught:
        sync_research_map(
            tmp_path,
            project_id="proj_rm6",
            repo_name="repo",
            action="sync",
            backend_factory=broken_factory,
            projection_contract_sha256=PROJECTION_HASH,
        )
    assert caught.value.code == "backend_runtime_failure"
    assert os.path.isfile(tmp_path / RUNTIME_RELATIVE_PATH / ".sync.lock")


def test_rm6_existing_current_backend_outage_does_not_stage_rebuild(tmp_path: Path) -> None:
    _write_reviewed_repo(tmp_path)
    store = _FakeBackendStore()
    first = _sync(tmp_path, store)
    generations = tmp_path / RUNTIME_RELATIVE_PATH / "generations"
    before = sorted(path.name for path in generations.iterdir())

    class VerifyOutageBackend(_FakeBackend):
        async def reopen_and_verify(
            self,
            expected_relation_ids: tuple[str, ...],
        ) -> BackendVerification:
            del expected_relation_ids
            raise OSError("backend temporarily unavailable")

    def outage_factory(_repository_uid: str, database: str) -> VerifyOutageBackend:
        return VerifyOutageBackend(store, database)

    with pytest.raises(ResearchMapSyncError, match="temporarily unavailable") as caught:
        sync_research_map(
            tmp_path,
            project_id="proj_rm6",
            repo_name="repo",
            action="sync",
            backend_factory=outage_factory,
            projection_contract_sha256=PROJECTION_HASH,
        )
    assert caught.value.code == "backend_runtime_failure"
    assert sorted(path.name for path in generations.iterdir()) == before
    current = load_current_generation(tmp_path)
    assert current is not None
    assert current.generation == first["generation"]


def test_rm6_action_schema_and_server_dispatch_sync_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter = TypeAdapter(ResearchMapActionRequest)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "action": "sync",
                "project_id": "proj_rm6",
                "repo_name": "repo",
                "roots": [{"path": "docs/research"}],
            }
        )

    binding = SimpleNamespace(
        project_id="proj_rm6",
        repo_name="repo",
        resource_id="res_rm6",
        scope_generation=7,
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

    calls: list[str] = []

    def fake_sync(
        _repo_root: Path,
        *,
        project_id: str,
        repo_name: str,
        action: str,
    ) -> dict[str, object]:
        assert project_id == "proj_rm6"
        assert repo_name == "repo"
        calls.append(action)
        return {"ok": True, "action": action, "status": f"{action}_ok", "error": ""}

    monkeypatch.setattr(server, "sync_research_map", fake_sync)
    for action in ("sync", "rebuild"):
        request = adapter.validate_python(
            {"action": action, "project_id": "proj_rm6", "repo_name": "repo"}
        )
        result = server.research_map_action(request)
        assert result["ok"] is True
        assert result["status"] == f"{action}_ok"
        assert result["resource_id"] == "res_rm6"
        assert result["scope_generation"] == 7

    assert calls == ["sync", "rebuild"]
