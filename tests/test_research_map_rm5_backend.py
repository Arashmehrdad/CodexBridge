from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import tomllib

from soma.research_map import (
    canonical_text_sha256,
    load_project_manifest,
    relation_id,
    scan_research_map,
)
from soma.research_map.backend import (
    ResearchMapBackendError,
    ResearchMapProjectionError,
    build_backend_projection,
)
from soma.research_map.graphiti_backend import (
    FALKOR_QUERY_TIMEOUT_MS,
    FALKOR_WRITE_CONCURRENCY,
    GraphitiFalkorBackend,
    _bounded_falkor_driver_type,
    _client_types,
    _load_dependencies,
    graphiti_backend_dependency_status,
    graphiti_projection_contract_sha256,
)


def _write_reviewed_repo(repo: Path) -> tuple[object, object]:
    source_path = "docs/research/001_rm5.md"
    source_text = "# RM5\nverified anchor\n"
    (repo / "docs/research/_soma_map").mkdir(parents=True)
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
    rid = relation_id(source_path, "finding:rm5", "SUPPORTS", "claim:rm5")
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
        "facets": {"programme": ["RM5"]},
        "relations": [
            {
                "relation_id": rid,
                "subject": {"key": "finding:rm5", "label": "RM5 finding"},
                "predicate": "SUPPORTS",
                "object": {"key": "claim:rm5", "label": "RM5 claim"},
                "statement": "RM5 keeps reviewed semantics backend-neutral.",
                "locator": {"anchor": "verified anchor"},
                "epistemic_class": "observed",
                "lifecycle": "current",
                "supersedes": [],
                "facets": {"dataset": ["synthetic"]},
                "qualifiers": {"scope": ["backend conformance"]},
            }
        ],
    }
    (repo / "docs/research/_soma_map/001_rm5.json").write_text(
        json.dumps(sidecar, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_result = load_project_manifest(repo)
    assert manifest_result.manifest is not None
    scan = scan_research_map(repo)
    assert scan.desired_state is not None
    return manifest_result.manifest, scan


def test_rm5_backend_projection_is_deterministic_and_primitive(tmp_path: Path) -> None:
    manifest, scan = _write_reviewed_repo(tmp_path)
    first = build_backend_projection(manifest, scan.sidecar_scan, scan.desired_state)
    second = build_backend_projection(manifest, scan.sidecar_scan, scan.desired_state)

    assert first == second
    assert len(first.nodes) == 2
    assert len(first.relations) == 1
    relation = first.relations[0]
    assert relation.record_facets_json == '{"programme":["RM5"]}'
    assert relation.facets_json == '{"dataset":["synthetic"]}'
    assert relation.qualifiers_json == '{"scope":["backend conformance"]}'
    assert relation.epistemic_class == "observed"
    assert relation.lifecycle == "current"
    assert relation.source_anchor == "verified anchor"


def test_rm5_backend_projection_rejects_conflicting_semantic_labels(tmp_path: Path) -> None:
    manifest, scan = _write_reviewed_repo(tmp_path)
    record = scan.sidecar_scan.records[0]
    sidecar = record.sidecar
    assert sidecar is not None
    relation = sidecar.relations[0]
    conflicting = relation.model_copy(
        update={"object": relation.object.model_copy(update={"key": relation.subject.key})}
    )
    bad_sidecar = sidecar.model_copy(update={"relations": [relation, conflicting]})
    bad_record = record.__class__(
        root_path=record.root_path,
        source_path=record.source_path,
        logical_record_id=record.logical_record_id,
        source_exists=record.source_exists,
        canonical_text_sha256=record.canonical_text_sha256,
        expected_sidecar_path=record.expected_sidecar_path,
        sidecar_state=record.sidecar_state,
        sidecar=bad_sidecar,
        canonical_sidecar_sha256=record.canonical_sidecar_sha256,
        malformed_sidecar_raw_sha256=record.malformed_sidecar_raw_sha256,
    )
    bad_scan = scan.sidecar_scan.__class__(records=(bad_record,), issues=())
    with pytest.raises(ResearchMapProjectionError, match="conflicting reviewed labels"):
        build_backend_projection(manifest, bad_scan, scan.desired_state)


def test_rm5_optional_dependency_contract_does_not_change_core_dependencies() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["dependencies"] == ["fastmcp", "pydantic", "pyyaml"]
    assert pyproject["project"]["optional-dependencies"]["research-map"] == [
        "graphiti-core==0.29.3",
        "fastembed==0.8.0",
        "falkordb==1.7.1",
        "httpx==0.28.1",
    ]


def test_rm5_dependency_status_is_version_pinned_when_available() -> None:
    status = graphiti_backend_dependency_status()
    assert status["embedding_dimension"] == 384
    assert status["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert graphiti_projection_contract_sha256() == graphiti_projection_contract_sha256()
    if status["available"]:
        assert status["version_match"] is True
        assert status["installed_versions"] == {
            "graphiti-core": "0.29.3",
            "fastembed": "0.8.0",
            "falkordb": "1.7.1",
            "httpx": "0.28.1",
        }


def test_rm5_nollm_fails_closed_if_optional_stack_is_present() -> None:
    if not graphiti_backend_dependency_status()["available"]:
        pytest.skip("optional research-map backend dependencies are not installed")
    deps = _load_dependencies()
    _embedder, no_llm, _cross = _client_types(deps, None)
    with pytest.raises(ResearchMapBackendError, match="LLM path is forbidden"):
        asyncio.run(no_llm()._generate_response("must not execute"))


def test_rm5_missing_optional_backend_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "soma.research_map.graphiti_backend.importlib.util.find_spec",
        lambda _name: None,
    )
    with pytest.raises(ResearchMapBackendError, match="dependencies are unavailable"):
        _load_dependencies()


def test_rm5_falkor_driver_uses_soma_bounded_query_timeout() -> None:
    calls: list[tuple[str, dict[str, object], int | None]] = []

    class FakeResult:
        def __init__(self) -> None:
            self.header = [(0, "value")]
            self.result_set = [["ok"]]

    class FakeGraph:
        async def query(
            self,
            query: str,
            params: dict[str, object],
            timeout: int | None = None,
        ) -> FakeResult:
            calls.append((query, params, timeout))
            return FakeResult()

    class FakeBaseDriver:
        def __init__(self) -> None:
            self._database = "test"
            self._graph = FakeGraph()

        def _get_graph(self, database: str) -> FakeGraph:
            assert database == "test"
            return self._graph

    driver_module = SimpleNamespace(
        FalkorDriver=FakeBaseDriver,
        convert_datetimes_to_strings=lambda value: value,
        _strip_nul_bytes=lambda value: value,
    )
    driver_type = _bounded_falkor_driver_type(driver_module)
    driver = driver_type()
    records, header, summary = asyncio.run(driver.execute_query("RETURN $value", value="ok"))

    assert calls == [("RETURN $value", {"value": "ok"}, FALKOR_QUERY_TIMEOUT_MS)]
    assert records == [{"value": "ok"}]
    assert header == ["value"]
    assert summary is None


class _FakeClient:
    def __init__(self, reply: object = True) -> None:
        self.reply = reply
        self.commands: list[str] = []

    async def execute_command(self, command: str) -> object:
        self.commands.append(command)
        return self.reply


class _FakeDriver:
    def __init__(self, client: object) -> None:
        self.client = client
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeGraphiti:
    def __init__(self) -> None:
        self.group_ids: object = "not-called"

    async def search(self, query: str, *, group_ids: object, num_results: int):
        assert query == "governing constraint"
        assert num_results == 5
        self.group_ids = group_ids
        return [SimpleNamespace(attributes={"relation_id": "rel_" + "a" * 64})]


def test_rm5_server_backend_requires_explicit_save() -> None:
    backend = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="rm5_test",
    )
    client = _FakeClient(True)
    driver = _FakeDriver(client)
    backend._driver = driver
    asyncio.run(backend.close())
    assert driver.closed is True
    assert client.commands == []

    backend = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="rm5_test",
    )
    client = _FakeClient(True)
    backend._driver = _FakeDriver(client)
    result = asyncio.run(backend.persist())
    assert result.persisted is True
    assert client.commands == ["SAVE"]

    failing = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="rm5_test",
    )
    failing._driver = _FakeDriver(_FakeClient(False))
    with pytest.raises(ResearchMapBackendError, match="SAVE did not report success"):
        asyncio.run(failing.persist())


def test_rm5_clone_from_current_is_disabled_after_live_copy_crash() -> None:
    backend = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="rm5_destination",
    )
    with pytest.raises(ResearchMapBackendError, match="clone_from_current is disabled"):
        asyncio.run(backend.clone_from_current(SimpleNamespace(database="rm5_source")))


def test_rm5_node_writes_use_bounded_parallelism() -> None:
    active = 0
    max_active = 0
    saved: list[str] = []

    class FakeEmbedder:
        async def create_batch(self, values: list[str]) -> list[list[float]]:
            return [[float(index)] for index, _value in enumerate(values)]

    class FakeEntityNode:
        def __init__(self, **kwargs: object) -> None:
            self.uuid = str(kwargs["uuid"])

        async def save(self, _driver: object) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            try:
                await asyncio.sleep(0.01)
                saved.append(self.uuid)
            finally:
                active -= 1

    backend = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="rm5_parallel",
    )
    backend._driver = object()
    backend._embedder = FakeEmbedder()
    backend._deps = {"EntityNode": FakeEntityNode}
    nodes = tuple(
        SimpleNamespace(uuid=f"node-{index}", key=f"key-{index}", label=f"label-{index}")
        for index in range(FALKOR_WRITE_CONCURRENCY * 3)
    )

    asyncio.run(backend.upsert_nodes(nodes))  # type: ignore[arg-type]

    assert len(saved) == len(nodes)
    assert 1 < max_active <= FALKOR_WRITE_CONCURRENCY


def test_rm5_search_deliberately_avoids_group_id_filter() -> None:
    backend = GraphitiFalkorBackend(
        repository_uid="srepo_0123456789abcdef",
        database="rm5_test",
    )
    graphiti = _FakeGraphiti()
    backend._driver = _FakeDriver(_FakeClient())
    backend._graphiti = graphiti
    hits = asyncio.run(backend.search("governing constraint", limit=5))
    assert graphiti.group_ids is None
    assert [hit.relation_id for hit in hits] == ["rel_" + "a" * 64]
