from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from soma.config import AppConfig, RepoConfig
from soma.gateway_models import KnowledgeActionRequest, KnowledgeQueryRequest
from soma.knowledge_tools_integration import (
    _bounded_knowledge_action,
    _bounded_knowledge_search,
    _bounded_wiki_page,
    register_knowledge_tools,
)
from soma.memory.repository import ProjectMemoryRepository
from soma.project_scope import ProjectScopeStore
from soma.repo_wiki import RepoWikiService


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}

    def tool(self, *, output_schema: dict, annotations: dict, **metadata: Any):
        del metadata
        def decorator(function):
            self.tools[function.__name__] = {
                "function": function,
                "output_schema": output_schema,
                "annotations": annotations,
            }
            return function

        return decorator


def _activate_project_scope(
    config: AppConfig, repo: Path, *, repo_name: str = "seedmind"
) -> str:
    project_id = "proj_seedmind_knowledge"
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=project_id,
        project_key="seedmind-knowledge",
        resource_id="res_seedmind_repository",
        repo_name=repo_name,
        repository_root=repo,
    )
    return project_id


def test_registers_repository_knowledge_tools_once() -> None:
    mcp = FakeMCP()

    register_knowledge_tools(mcp)
    register_knowledge_tools(mcp)

    assert set(mcp.tools) == {
        "knowledge_query",
        "knowledge_action",
    }


def test_all_tool_output_properties_have_schemas() -> None:
    mcp = FakeMCP()
    register_knowledge_tools(mcp)

    for tool in mcp.tools.values():
        schema = tool["output_schema"]
        assert schema["type"] == "object"
        assert schema["type"] == "object"
        for name, property_schema in schema["properties"].items():
            assert property_schema is not None, name
            assert "type" in property_schema, name
        if schema.get("additionalProperties") is False:
            for field in ("server_build_hash", "schema_hash", "capability_epoch"):
                assert field in schema["properties"]


def test_tools_resolve_config_from_active_mcp_module(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "SeedMind"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("# SeedMind\n", encoding="utf-8")

    config = AppConfig(repos={"seedmind": RepoConfig(path=str(repo))})
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_active_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)

    register_knowledge_tools(mcp)
    result = mcp.tools["knowledge_action"]["function"](
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {"action": "refresh_wiki", "repo_name": "seedmind"}
        )
    )

    assert result["ok"] is True
    assert result["status"] == "generated"
    current = repo / ".soma" / "wiki" / "CURRENT.json"
    generation_id = json.loads(current.read_text(encoding="utf-8"))["generation_id"]
    assert (
        repo / ".soma" / "wiki" / "generations" / generation_id / "overview.md"
    ).is_file()
    assert getattr(mcp, "_soma_runtime_config") is config
    assert len(result["server_build_hash"]) == 64
    assert len(result["schema_hash"]) == 64
    assert result["capability_epoch"]


def test_combined_search_returns_normalized_wiki_and_scoped_memory_hits(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "SeedMind"
    module = repo / "src" / "seedmind" / "knowledge.py"
    module.parent.mkdir(parents=True)
    (repo / ".git").mkdir()
    module.write_text(
        '"""Repository scoped project knowledge helper."""\n',
        encoding="utf-8",
    )

    config = AppConfig(
        repos={"seedmind": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_combined_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    refresh = mcp.tools["knowledge_action"]["function"](
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {"action": "refresh_wiki", "repo_name": "seedmind"}
        )
    )
    remembered = mcp.tools["knowledge_action"]["function"](
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {
                "action": "remember_decision",
                "repo_name": "seedmind",
                "decision": "SeedMind project knowledge must remain repository-scoped.",
            }
        )
    )
    result = mcp.tools["knowledge_query"]["function"](
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {
                "operation": "search",
                "repo_name": "seedmind",
                "query": "repository-scoped",
            }
        )
    )

    assert refresh["ok"] is True
    # `remember_decision` writes canonical Markdown now, so it requires an exact
    # active ProjectScope binding; this repository has none. The legacy combined
    # `search` keeps its own contract and still returns wiki hits, but canonical
    # memory is no longer reachable through it -- that path reads the retired
    # SQLite store, and serving memory from two surfaces was the duplicate
    # authority SOMA-SHARED-MEMORY-ARCH-1 removes.
    assert remembered["ok"] is False
    assert "seedmind" in remembered["error"]
    assert result["ok"] is True
    assert any("Repository scoped" in hit["snippet"] for hit in result["wiki_hits"])
    assert result["memory_hits"] == []
    assert len(result["server_build_hash"]) == 64
    assert len(remembered["schema_hash"]) == 64


def test_project_knowledge_gateway_saves_searches_and_reports_health(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "SeedMind"
    repo.mkdir()
    (repo / ".git").mkdir()
    config = AppConfig(
        repos={"seedmind": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    project_id = _activate_project_scope(config, repo)
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_project_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    saved = mcp.tools["knowledge_action"]["function"](
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {
                "action": "save_knowledge",
                "project_id": project_id,
                "repo_name": "seedmind",
                "vault_path": "research/chatgpt-architecture.md",
                "kind": "research_note",
                "title": "Durable architecture research",
                "body": "دانش پروژه must remain available across agent sessions.",
                "idempotency_key": "chatgpt-architecture-1",
                "sources": [
                    {
                        "source_id": "src_owner_chat",
                        "uri": "chat://architecture-research",
                        "title": "Architecture research chat",
                    }
                ],
                "locators": [
                    {
                        "source_id": "src_owner_chat",
                        "locator": "owner synthesis",
                    }
                ],
            }
        )
    )
    found = mcp.tools["knowledge_query"]["function"](
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {
                "operation": "search_knowledge",
                "project_id": project_id,
                "repo_name": "seedmind",
                "query": "دانش پروژه",
            }
        )
    )
    health = mcp.tools["knowledge_query"]["function"](
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {
                "operation": "knowledge_health",
                "project_id": project_id,
                "repo_name": "seedmind",
            }
        )
    )

    assert saved["ok"] is True
    assert saved["project_id"] == project_id
    assert saved["source_count"] == 1
    assert Path(saved["canonical_path"]).is_file()
    assert found["ok"] is True
    assert [item["knowledge_id"] for item in found["records"]] == [
        saved["knowledge_id"]
    ]
    assert found["records"][0]["sources"][0]["source_id"] == "src_owner_chat"
    assert health["ok"] is True
    assert health["status"] == "healthy"


def test_legacy_research_gateway_variants_are_retired() -> None:
    query_adapter = TypeAdapter(KnowledgeQueryRequest)
    action_adapter = TypeAdapter(KnowledgeActionRequest)

    for payload in (
        {
            "operation": "search_research",
            "project_id": "proj_soma",
            "repo_name": "soma",
            "query": "legacy",
        },
        {
            "operation": "build_context_packet",
            "project_id": "proj_soma",
            "repo_name": "soma",
            "query": "legacy",
        },
        {
            "operation": "research_health",
            "project_id": "proj_soma",
            "repo_name": "soma",
        },
    ):
        with pytest.raises(ValidationError):
            query_adapter.validate_python(payload)

    for payload in (
        {
            "action": "import_research_source",
            "project_id": "proj_soma",
            "repo_name": "soma",
        },
        {
            "action": "preserve_research_packet",
            "project_id": "proj_soma",
            "repo_name": "soma",
        },
        {
            "action": "rebuild_research_index",
            "project_id": "proj_soma",
            "repo_name": "soma",
        },
    ):
        with pytest.raises(ValidationError):
            action_adapter.validate_python(payload)


def test_knowledge_search_full_view_preserves_complete_hits(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "SeedMind"
    repo.mkdir()
    (repo / ".git").mkdir()
    config = AppConfig(
        repos={"seedmind": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_full_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    monkeypatch.setattr(
        RepoWikiService,
        "search_with_metadata",
        lambda self, query, limit: {
            "hits": [
                {
                    "source": "wiki",
                    "page": f"page-{index}",
                    "line": index,
                    "snippet": "x" * 1000,
                }
                for index in range(limit)
            ],
            "generation_id": "generation-1",
            "stale": False,
            "indexed_head": "a" * 40,
            "indexed_branch": "main",
            "source_generation": 1,
            "indexed_source_generation": 1,
        },
    )
    monkeypatch.setattr(
        ProjectMemoryRepository,
        "search",
        lambda self, *args, **kwargs: SimpleNamespace(records=[]),
    )
    register_knowledge_tools(mcp)

    result = mcp.tools["knowledge_query"]["function"](
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {
                "operation": "search",
                "repo_name": "seedmind",
                "query": "needle",
                "limit": 20,
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )

    assert len(result["wiki_hits"]) == 20
    assert len(result["wiki_hits"][0]["snippet"]) == 1000
    assert "truncated" not in result


def test_knowledge_search_projection_is_bounded_and_marks_truncation() -> None:
    result = {
        "ok": True,
        "repo_name": "seedmind",
        "query": "needle",
        "wiki_hits": [
            {
                "source": "wiki",
                "page": f"page-{index}",
                "line": index,
                "snippet": "x" * 2_000,
            }
            for index in range(20)
        ],
        "memory_hits": [
            {
                "memory_id": f"memory-{index}",
                "memory_type": "decision",
                "title": "t" * 500,
                "summary": "s" * 1_000,
                "tags": [],
                "repo_name": "seedmind",
            }
            for index in range(20)
        ],
        "generation_id": "generation-1",
        "stale": False,
        "indexed_head": "a" * 40,
        "indexed_branch": "main",
        "source_generation": 1,
        "indexed_source_generation": 1,
        "error": "",
    }

    bounded = _bounded_knowledge_search(result)

    assert bounded["view"] == "compact"
    assert bounded["projection_version"] == "cf1.v1"
    assert bounded["non_authoritative"] is True
    assert "authoritative" in bounded["notice"]
    assert bounded["truncated"] is True
    assert bounded["has_more"] is True
    assert bounded["response_budget_bytes"] == 12 * 1024
    assert bounded["response_bytes"] <= 12 * 1024
    assert bounded["wiki_hits"] or bounded["memory_hits"]


def test_wiki_page_projection_is_bounded_and_marks_truncation() -> None:
    bounded = _bounded_wiki_page(
        {
            "ok": True,
            "repo_name": "seedmind",
            "page": "overview.md",
            "content": "x" * 40_000,
            "size_bytes": 40_000,
            "truncated": False,
            "generation_id": "generation-1",
            "stale": False,
            "error": "",
        },
        4096,
    )
    assert bounded["view"] == "compact"
    assert bounded["projection_version"] == "cf1.v1"
    assert bounded["non_authoritative"] is True
    assert bounded["truncated"] is True
    assert bounded["has_more"] is True
    assert bounded["response_bytes"] <= 4096


def test_knowledge_action_projection_is_bounded() -> None:
    bounded = _bounded_knowledge_action(
        {
            "ok": True,
            "repo_name": "seedmind",
            "status": "generated",
            "pages": [f"page-{index}.md" for index in range(5000)],
            "changed_source_files": [f"src/{index}.py" for index in range(5000)],
            "summary": "x" * 20_000,
            "error": "",
        },
        4096,
    )
    assert bounded["view"] == "compact"
    assert bounded["projection_version"] == "cf1.v1"
    assert bounded["non_authoritative"] is True
    assert bounded["response_bytes"] <= 4096
    assert bounded["page_count"] == 5000
    assert bounded["changed_source_file_count"] == 5000
    assert "pages" not in bounded


def test_knowledge_tools_follow_the_active_config_after_reload(
    tmp_path: Path, monkeypatch
) -> None:
    first_repo = tmp_path / "FirstRepo"
    second_repo = tmp_path / "SecondRepo"
    for repo, marker in (
        (first_repo, "first repository marker"),
        (second_repo, "second repository marker"),
    ):
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "status.py").write_text(f'"""{marker}"""\n', encoding="utf-8")

    first = AppConfig(
        repos={"first": RepoConfig(path=str(first_repo))},
        runs_dir=str(tmp_path / "first-runs"),
        config_dir=tmp_path,
    )
    second = AppConfig(
        repos={"second": RepoConfig(path=str(second_repo))},
        runs_dir=str(tmp_path / "second-runs"),
        config_dir=tmp_path,
    )
    active = {"config": first}
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_reloaded_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: active["config"]
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    action = mcp.tools["knowledge_action"]["function"]
    query = mcp.tools["knowledge_query"]["function"]
    action(
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {"action": "refresh_wiki", "repo_name": "first"}
        )
    )

    active["config"] = second
    refreshed = action(
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {"action": "refresh_wiki", "repo_name": "second"}
        )
    )
    page = query(
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {"operation": "read_wiki", "repo_name": "second", "page": "modules.md"}
        )
    )

    assert refreshed["ok"] is True
    assert refreshed["repo_name"] == "second"
    assert page["ok"] is True
    assert page["repo_name"] == "second"
    assert "second repository marker" in page["content"]
    assert (first_repo / ".soma" / "wiki" / "CURRENT.json").is_file()
    assert (second_repo / ".soma" / "wiki" / "CURRENT.json").is_file()


def test_refresh_read_and_search_share_the_active_wiki_generation(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "SeedMind"
    (repo / "src" / "seedmind").mkdir(parents=True)
    (repo / ".git").mkdir()
    marker = "Current implementation status: pending work marker"
    (repo / "src" / "seedmind" / "status.py").write_text(
        f'"""{marker}"""\n', encoding="utf-8"
    )
    config = AppConfig(
        repos={"seedmind": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_generation_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    action = mcp.tools["knowledge_action"]["function"]
    query = mcp.tools["knowledge_query"]["function"]
    refreshed = action(
        TypeAdapter(KnowledgeActionRequest).validate_python(
            {"action": "refresh_wiki", "repo_name": "seedmind"}
        )
    )
    page = query(
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {"operation": "read_wiki", "repo_name": "seedmind", "page": "modules.md"}
        )
    )
    searched = query(
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {"operation": "search", "repo_name": "seedmind", "query": marker}
        )
    )

    assert refreshed["ok"] is True
    assert page["generation_id"] == refreshed["generation_id"]
    assert searched["generation_id"] == refreshed["generation_id"]
    assert searched["stale"] is False
    assert any(marker in hit["snippet"] for hit in searched["wiki_hits"])
