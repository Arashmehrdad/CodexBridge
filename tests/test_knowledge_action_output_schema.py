from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema
from fastmcp import Client, FastMCP

from soma.config import AppConfig, RepoConfig
from soma.knowledge_tools_integration import (
    KNOWLEDGE_ACTION_OUTPUT,
    register_knowledge_tools,
)


def _wiki_result() -> dict[str, Any]:
    return {
        "ok": True,
        "repo_name": "seedmind",
        "status": "generated",
        "wiki_root": ".soma/wiki",
        "pages": ["index.md"],
        "source_file_count": 1,
        "changed_source_files": ["README.md"],
        "scan_truncated": False,
        "stale": False,
        "generation_id": "generation-1",
        "indexed_head": "head-1",
        "indexed_branch": "main",
        "source_generation": 1,
        "indexed_source_generation": 1,
        "incremental": False,
        "refresh_operation_id": "refresh-1",
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "1",
        "error": "",
    }


def _memory_result() -> dict[str, Any]:
    return {
        "ok": True,
        "repo_name": "seedmind",
        "memory_id": "memory-1",
        "memory_type": "decision",
        "title": "A decision",
        "summary": "The decision summary.",
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "1",
        "error": "",
    }


def test_knowledge_action_schema_accepts_both_strict_results_and_rejects_other() -> None:
    validator = jsonschema.Draft202012Validator(KNOWLEDGE_ACTION_OUTPUT)
    validator.check_schema(KNOWLEDGE_ACTION_OUTPUT)

    validator.validate(_wiki_result())
    validator.validate(_memory_result())

    invalid = {
        "ok": True,
        "repo_name": "seedmind",
        "server_build_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "capability_epoch": "1",
        "error": "",
    }
    error = jsonschema.exceptions.ValidationError
    try:
        validator.validate(invalid)
    except error:
        pass
    else:
        raise AssertionError("an object matching neither action result was accepted")


def test_registered_fastmcp_knowledge_action_accepts_refresh_and_remember(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "SeedMind"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("# SeedMind\n", encoding="utf-8")
    config = AppConfig(
        repos={"seedmind": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )

    mcp = FastMCP("knowledge-schema-test")
    runtime_module = ModuleType("soma_test_real_knowledge_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)

    registered = asyncio.run(mcp.get_tool("knowledge_action"))
    assert registered is not None
    assert registered.output_schema == KNOWLEDGE_ACTION_OUTPUT

    async def call_tools() -> tuple[Any, Any]:
        async with Client(mcp) as client:
            refresh = await client.call_tool(
                "knowledge_action",
                {
                    "request": {"action": "refresh_wiki", "repo_name": "seedmind"}
                },
            )
            remembered = await client.call_tool(
                "knowledge_action",
                {
                    "request": {
                        "action": "remember_decision",
                        "repo_name": "seedmind",
                        "decision": "Knowledge remains repository-scoped.",
                    }
                },
            )
            return refresh, remembered

    refresh, remembered = asyncio.run(call_tools())
    assert refresh.structured_content["ok"] is True
    assert refresh.structured_content["status"] == "generated"
    assert remembered.structured_content["ok"] is True
    assert remembered.structured_content["memory_id"]
    for result in (refresh, remembered):
        assert len(result.structured_content["server_build_hash"]) == 64
        assert len(result.structured_content["schema_hash"]) == 64
        assert result.structured_content["capability_epoch"]

    current = repo / ".soma" / "wiki" / "CURRENT.json"
    assert json.loads(current.read_text(encoding="utf-8"))["generation_id"]
