from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backend import (
    BackendPersistResult,
    BackendSearchHit,
    BackendVerification,
    ProjectedNode,
    ProjectedRelation,
    ResearchMapBackendError,
    ResearchMapBackendUnavailable,
)
from .canonical import canonical_json_sha256

GRAPHITI_CORE_VERSION = "0.29.3"
FASTEMBED_VERSION = "0.8.0"
FALKORDB_CLIENT_VERSION = "1.7.1"
HTTPX_VERSION = "0.28.1"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384
GRAPHITI_PROJECTION_VERSION = "soma.research-map.graphiti-falkor.v1"
_REQUIRED_MODULES = ("graphiti_core", "fastembed", "falkordb")
_REQUIRED_DISTRIBUTIONS = {
    "graphiti-core": GRAPHITI_CORE_VERSION,
    "fastembed": FASTEMBED_VERSION,
    "falkordb": FALKORDB_CLIENT_VERSION,
    "httpx": HTTPX_VERSION,
}
_REFERENCE_TIME = datetime(2000, 1, 1, tzinfo=UTC)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def graphiti_backend_dependency_status() -> dict[str, object]:
    modules = {name: importlib.util.find_spec(name) is not None for name in _REQUIRED_MODULES}
    installed_versions: dict[str, str] = {}
    version_match = True
    for distribution, expected in _REQUIRED_DISTRIBUTIONS.items():
        try:
            installed = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            installed = ""
        installed_versions[distribution] = installed
        version_match = version_match and installed == expected
    return {
        "available": all(modules.values()) and version_match,
        "modules": modules,
        "installed_versions": installed_versions,
        "version_match": version_match,
        "graphiti_core_version": GRAPHITI_CORE_VERSION,
        "fastembed_version": FASTEMBED_VERSION,
        "falkordb_client_version": FALKORDB_CLIENT_VERSION,
        "httpx_version": HTTPX_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIMENSION,
    }


def graphiti_projection_contract_sha256() -> str:
    return canonical_json_sha256(
        {
            "schema": GRAPHITI_PROJECTION_VERSION,
            "graphiti_core_version": GRAPHITI_CORE_VERSION,
            "fastembed_version": FASTEMBED_VERSION,
            "falkordb_client_version": FALKORDB_CLIENT_VERSION,
            "httpx_version": HTTPX_VERSION,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "project_isolation": "one_database_per_repository",
            "group_id_search_filter": False,
            "llm_ingestion": False,
            "cross_encoder_required": False,
            "telemetry": False,
            "structured_properties": [
                "record_facets_json",
                "facets_json",
                "qualifiers_json",
            ],
        }
    )


def _load_dependencies() -> dict[str, Any]:
    status = graphiti_backend_dependency_status()
    if not status["available"]:
        missing = [
            name for name, available in status["modules"].items() if not available  # type: ignore[union-attr]
        ]
        raise ResearchMapBackendUnavailable(
            "optional Graphiti/FalkorDB backend dependencies are unavailable: "
            + ", ".join(missing)
        )

    os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    graphiti_module = importlib.import_module("graphiti_core")
    embedder_module = importlib.import_module("graphiti_core.embedder.client")
    cross_encoder_module = importlib.import_module("graphiti_core.cross_encoder.client")
    llm_module = importlib.import_module("graphiti_core.llm_client.client")
    driver_module = importlib.import_module("graphiti_core.driver.falkordb_driver")
    nodes_module = importlib.import_module("graphiti_core.nodes")
    edges_module = importlib.import_module("graphiti_core.edges")
    fastembed_module = importlib.import_module("fastembed")
    return {
        "Graphiti": graphiti_module.Graphiti,
        "EmbedderClient": embedder_module.EmbedderClient,
        "CrossEncoderClient": cross_encoder_module.CrossEncoderClient,
        "LLMClient": llm_module.LLMClient,
        "FalkorDriver": driver_module.FalkorDriver,
        "EntityNode": nodes_module.EntityNode,
        "EntityEdge": edges_module.EntityEdge,
        "TextEmbedding": fastembed_module.TextEmbedding,
    }


def _client_types(deps: dict[str, Any], model_cache_dir: Path | None) -> tuple[type, type, type]:
    embedder_base = deps["EmbedderClient"]
    llm_base = deps["LLMClient"]
    cross_encoder_base = deps["CrossEncoderClient"]
    text_embedding = deps["TextEmbedding"]

    class LocalFastEmbed(embedder_base):
        def __init__(self) -> None:
            kwargs: dict[str, object] = {"model_name": EMBEDDING_MODEL}
            if model_cache_dir is not None:
                kwargs["cache_dir"] = str(model_cache_dir)
            self.model = text_embedding(**kwargs)

        async def create(self, input_data: object) -> list[float]:
            if isinstance(input_data, list):
                text = " ".join(str(item) for item in input_data)
            else:
                text = str(input_data)
            return next(iter(self.model.embed([text]))).tolist()

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            return [vector.tolist() for vector in self.model.embed(input_data_list)]

    class NoLLM(llm_base):
        def __init__(self) -> None:
            super().__init__(config=None, cache=False)

        async def _generate_response(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise ResearchMapBackendError(
                "Graphiti LLM path is forbidden for reviewed research-map projection"
            )

    class NoCrossEncoder(cross_encoder_base):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            del query
            return [(passage, 0.0) for passage in passages]

    return LocalFastEmbed, NoLLM, NoCrossEncoder


class GraphitiFalkorBackend:
    """Optional Graphiti projection over a local/server-backed FalkorDB database.

    Imports and model initialization are deliberately lazy. Merely importing
    Soma or this module never requires Graphiti, FastEmbed, FalkorDB, a running
    database, or an external model-provider credential.
    """

    def __init__(
        self,
        *,
        repository_uid: str,
        database: str,
        host: str = "127.0.0.1",
        port: int = 6379,
        model_cache_dir: Path | None = None,
    ) -> None:
        self.repository_uid = repository_uid
        self.database = database
        self.host = host
        self.port = port
        self.model_cache_dir = model_cache_dir
        self._deps: dict[str, Any] | None = None
        self._driver: Any | None = None
        self._graphiti: Any | None = None
        self._embedder: Any | None = None

    async def _open(self) -> None:
        if self._driver is not None:
            return
        deps = _load_dependencies()
        local_embedder, no_llm, no_cross = _client_types(deps, self.model_cache_dir)
        driver = deps["FalkorDriver"](
            host=self.host,
            port=self.port,
            database=self.database,
        )
        embedder = local_embedder()
        graphiti = deps["Graphiti"](
            graph_driver=driver,
            llm_client=no_llm(),
            embedder=embedder,
            cross_encoder=no_cross(),
        )
        self._deps = deps
        self._driver = driver
        self._embedder = embedder
        self._graphiti = graphiti

    async def build_empty(self) -> None:
        await self._open()
        await self._graphiti.build_indices_and_constraints(delete_existing=True)

    async def clone_from_current(self, source: object) -> None:
        del source
        raise ResearchMapBackendError(
            "Graphiti/FalkorDB clone_from_current is not activated in RM5; "
            "RM6 may select a verified copy strategy or full rebuild"
        )

    async def upsert_nodes(self, nodes: tuple[ProjectedNode, ...]) -> None:
        if not nodes:
            return
        await self._open()
        names = [node.key for node in nodes]
        embeddings = await self._embedder.create_batch(names)
        entity_node = self._deps["EntityNode"]
        for node, embedding in zip(nodes, embeddings, strict=True):
            stored = entity_node(
                uuid=node.uuid,
                name=node.key,
                group_id=self.repository_uid,
                labels=["ReviewedResearchEntity"],
                name_embedding=embedding,
                attributes={"semantic_label": node.label},
            )
            await stored.save(self._driver)

    async def upsert_relations(self, relations: tuple[ProjectedRelation, ...]) -> None:
        if not relations:
            return
        await self._open()
        embeddings = await self._embedder.create_batch(
            [relation.statement for relation in relations]
        )
        entity_edge = self._deps["EntityEdge"]
        for relation, embedding in zip(relations, embeddings, strict=True):
            stored = entity_edge(
                uuid=relation.uuid,
                group_id=self.repository_uid,
                source_node_uuid=relation.source_node_uuid,
                target_node_uuid=relation.target_node_uuid,
                created_at=_REFERENCE_TIME,
                name=relation.predicate,
                fact=relation.statement,
                fact_embedding=embedding,
                reference_time=_REFERENCE_TIME,
                attributes={
                    "relation_id": relation.relation_id,
                    "source_path": relation.source_path,
                    "source_canonical_text_sha256": relation.source_canonical_text_sha256,
                    "source_anchor": relation.source_anchor,
                    "epistemic_class": relation.epistemic_class,
                    "lifecycle": relation.lifecycle,
                    "record_facets_json": relation.record_facets_json,
                    "facets_json": relation.facets_json,
                    "qualifiers_json": relation.qualifiers_json,
                    "reviewed_by": "Sol",
                    "authority": "research_doc",
                },
            )
            await stored.save(self._driver)

    async def remove_relations(self, relation_ids: tuple[str, ...]) -> None:
        if not relation_ids:
            return
        await self._open()
        await self._driver.execute_query(
            "MATCH ()-[r:RELATES_TO]->() "
            "WHERE r.relation_id IN $relation_ids DELETE r",
            relation_ids=list(relation_ids),
        )

    async def read_relation_manifest(self) -> tuple[str, ...]:
        await self._open()
        records, _header, _summary = await self._driver.execute_query(
            "MATCH ()-[r:RELATES_TO]->() "
            "WHERE r.relation_id IS NOT NULL "
            "RETURN r.relation_id AS relation_id ORDER BY relation_id"
        )
        relation_ids = [
            str(record["relation_id"])
            for record in records
            if record.get("relation_id")
        ]
        return tuple(sorted(relation_ids))

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> tuple[BackendSearchHit, ...]:
        if not query.strip():
            raise ValueError("research-map search query must not be blank")
        if limit < 1 or limit > 100:
            raise ValueError("research-map search limit must be between 1 and 100")
        await self._open()
        edges = await self._graphiti.search(query, group_ids=None, num_results=limit)
        hits: list[BackendSearchHit] = []
        for edge in edges:
            attributes = getattr(edge, "attributes", {}) or {}
            relation_id = str(attributes.get("relation_id", ""))
            if relation_id:
                hits.append(BackendSearchHit(relation_id=relation_id))
        return tuple(hits)

    async def persist(self) -> BackendPersistResult:
        await self._open()
        client = getattr(self._driver, "client", None)
        execute_command = getattr(client, "execute_command", None)
        if execute_command is None:
            raise ResearchMapBackendError(
                "FalkorDB client does not expose an explicit SAVE command"
            )
        reply = await _maybe_await(execute_command("SAVE"))
        persisted = bool(reply)
        if not persisted:
            raise ResearchMapBackendError("FalkorDB SAVE did not report success")
        return BackendPersistResult(persisted=True, detail=str(reply))

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
        self._deps = None
        self._driver = None
        self._graphiti = None
        self._embedder = None

    async def reopen_and_verify(
        self,
        expected_relation_ids: tuple[str, ...],
    ) -> BackendVerification:
        expected = tuple(sorted(expected_relation_ids))
        await self.close()
        actual = await self.read_relation_manifest()
        return BackendVerification(
            expected_relation_ids=expected,
            actual_relation_ids=actual,
        )
