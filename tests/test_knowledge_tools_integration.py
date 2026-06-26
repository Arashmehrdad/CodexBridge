from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.knowledge_tools_integration import register_knowledge_tools


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
        "refresh_repo_wiki",
        "read_repo_wiki",
        "search_repo_knowledge",
        "remember_repo_decision",
    }


def test_all_tool_output_properties_have_schemas() -> None:
    mcp = FakeMCP()
    register_knowledge_tools(mcp)

    for tool in mcp.tools.values():
        schema = tool["output_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        for name, property_schema in schema["properties"].items():
            assert property_schema is not None, name
            assert "type" in property_schema, name


def test_tools_resolve_config_from_active_mcp_module(tmp_path: Path, monkeypatch) -> None:
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
    result = mcp.tools["refresh_repo_wiki"]["function"]("seedmind")

    assert result["ok"] is True
    assert result["status"] == "generated"
    assert (repo / ".codexbridge" / "wiki" / "overview.md").is_file()
    assert getattr(mcp, "_codexbridge_runtime_config") is config
