from __future__ import annotations

import sys
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.knowledge_tools_integration import (
    _bounded_knowledge_action,
    _bounded_knowledge_search,
    _bounded_wiki_page,
    register_knowledge_tools,
)
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
    current = repo / ".codexbridge" / "wiki" / "CURRENT.json"
    generation_id = json.loads(current.read_text(encoding="utf-8"))["generation_id"]
    assert (repo / ".codexbridge" / "wiki" / "generations" / generation_id / "overview.md").is_file()
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


def test_knowledge_search_projection_is_bounded_and_marks_truncation() -> None:
    result = {
        "ok": True,
        "repo_name": "seedmind",
        "query": "needle",
        "wiki_hits": [
            {"source": "wiki", "page": f"page-{index}", "line": index, "snippet": "x" * 2_000}
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
    runtime_module = ModuleType("codexbridge_test_reloaded_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: active["config"]
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    action = mcp.tools["knowledge_action"]["function"]
    query = mcp.tools["knowledge_query"]["function"]
    action(TypeAdapter(KnowledgeActionRequest).validate_python(
        {"action": "refresh_wiki", "repo_name": "first"}
    ))

    active["config"] = second
    refreshed = action(TypeAdapter(KnowledgeActionRequest).validate_python(
        {"action": "refresh_wiki", "repo_name": "second"}
    ))
    page = query(TypeAdapter(KnowledgeQueryRequest).validate_python(
        {"operation": "read_wiki", "repo_name": "second", "page": "modules.md"}
    ))

    assert refreshed["ok"] is True
    assert refreshed["repo_name"] == "second"
    assert page["ok"] is True
    assert page["repo_name"] == "second"
    assert "second repository marker" in page["content"]
    assert (first_repo / ".codexbridge" / "wiki" / "CURRENT.json").is_file()
    assert (second_repo / ".codexbridge" / "wiki" / "CURRENT.json").is_file()


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
    runtime_module = ModuleType("codexbridge_test_generation_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    action = mcp.tools["knowledge_action"]["function"]
    query = mcp.tools["knowledge_query"]["function"]
    refreshed = action(TypeAdapter(KnowledgeActionRequest).validate_python(
        {"action": "refresh_wiki", "repo_name": "seedmind"}
    ))
    page = query(TypeAdapter(KnowledgeQueryRequest).validate_python(
        {"operation": "read_wiki", "repo_name": "seedmind", "page": "modules.md"}
    ))
    searched = query(TypeAdapter(KnowledgeQueryRequest).validate_python(
        {"operation": "search", "repo_name": "seedmind", "query": marker}
    ))

    assert refreshed["ok"] is True
    assert page["generation_id"] == refreshed["generation_id"]
    assert searched["generation_id"] == refreshed["generation_id"]
    assert searched["stale"] is False
    assert any(marker in hit["snippet"] for hit in searched["wiki_hits"])
