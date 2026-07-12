from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.knowledge_tools_integration import register_knowledge_tools
from codexbridge.gateway_models import KnowledgeActionRequest, KnowledgeQueryRequest
from pydantic import TypeAdapter


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}

    def tool(self, *, output_schema: dict, annotations: dict):
        def decorator(function):
            self.tools[function.__name__] = {
                "function": function,
                "output_schema": output_schema,
                "annotations": annotations,
            }
            return function

        return decorator


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
    runtime_module = ModuleType("codexbridge_test_active_server")
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
    assert (repo / ".codexbridge" / "wiki" / "overview.md").is_file()
    assert getattr(mcp, "_codexbridge_runtime_config") is config
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
    runtime_module = ModuleType("codexbridge_test_combined_knowledge_server")
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
            {"operation": "search", "repo_name": "seedmind", "query": "repository-scoped"}
        )
    )

    assert refresh["ok"] is True
    assert remembered["ok"] is True
    assert result["ok"] is True
    assert any("Repository scoped" in hit["snippet"] for hit in result["wiki_hits"])
    assert any("repository-scoped" in hit["summary"] for hit in result["memory_hits"])
    assert len(result["server_build_hash"]) == 64
    assert len(remembered["schema_hash"]) == 64
