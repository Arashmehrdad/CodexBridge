from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

import codexbridge.server as server
from codexbridge.gateway_models import (
    RepoApplyRequest,
    RepoQueryRequest,
    RunQueryRequest,
    RunStartRequest,
)
from codexbridge.knowledge_tools_integration import register_knowledge_tools
from codexbridge.public_gateway_inventory import PUBLIC_GATEWAY_NAMES


def _actions() -> dict[str, dict]:
    register_knowledge_tools(server.mcp)
    tools = asyncio.run(server.mcp.list_tools())
    return {tool.name: tool.to_mcp_tool().model_dump(mode="json") for tool in tools}


def test_deterministic_gateway_surface_benchmark() -> None:
    actions = _actions()
    assert set(actions) == set(PUBLIC_GATEWAY_NAMES)
    retired = {
        "inspect_repo_status", "apply_previewed_repo_change", "start_project_command_async",
        "list_docker_capabilities", "start_cloudflare_action_async", "list_ssh_capabilities",
        "reload_service", "read_repo_wiki", "start_codex_plan_task_async", "start_codex_implement_task_async",
    }
    assert retired.isdisjoint(actions)
    for action in actions.values():
        Draft202012Validator.check_schema(action["inputSchema"])
        Draft202012Validator.check_schema(action["outputSchema"])
    for name in {
        "repo_query",
        "docker_query",
        "cloudflare_query",
        "ssh_query",
        "system_query",
        "knowledge_query",
        "codex_plan",
        "trading_query",
        "trading_signal_get",
        "trading_signal_list",
    }:
        assert actions[name]["annotations"]["readOnlyHint"] is True
    for name in {
        "repo_apply",
        "repo_commit",
        "run_start",
        "docker_action",
        "cloudflare_action",
        "ssh_action",
        "system_action",
        "knowledge_action",
        "codex_implement",
        "trading_signal_submit",
        "trading_signal_cancel_before_entry",
    }:
        assert actions[name]["annotations"]["readOnlyHint"] is False


def test_mcp_transport_uses_small_text_summary_without_structured_duplication(
    monkeypatch,
) -> None:
    payload = {
        "ok": True,
        "operation": "summary_list",
        "runs": [
            {
                "run_id": f"run-{index}",
                "status": "completed",
                "summary": "x" * 1000,
            }
            for index in range(20)
        ],
        "error": "",
    }

    class FakeJobs:
        def list_run_summaries(self, **kwargs):
            assert kwargs["limit"] == 20
            return dict(payload)

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())

    async def call_tool():
        async with Client(server.mcp) as client:
            return await client.call_tool(
                "run_query",
                {"request": {"operation": "summary_list", "limit": 20}},
            )

    result = asyncio.run(call_tool())
    assert result.structured_content is not None
    assert result.structured_content["runs"] == payload["runs"]
    text = "".join(
        block.text for block in result.content if getattr(block, "type", "") == "text"
    )
    structured_json = json.dumps(
        result.structured_content,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert 0 < len(text.encode("utf-8")) <= 512
    assert "structured result" in text
    assert structured_json not in text
    assert len(text.encode("utf-8")) < len(structured_json.encode("utf-8")) // 10

    direct = server.run_query(
        TypeAdapter(RunQueryRequest).validate_python(
            {"operation": "summary_list", "limit": 20}
        )
    )
    assert isinstance(direct, dict)
    assert direct["runs"] == payload["runs"]


def test_benchmark_schema_rejects_cross_operation_fields() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(RepoQueryRequest).validate_python(
            {"operation": "status", "repo_name": "repo", "path": "outside"}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(RepoApplyRequest).validate_python(
            {"operation": "previewed_change", "repo_name": "repo", "patch_id": "p", "expected_sha256": "a" * 64}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(RunStartRequest).validate_python(
            {"operation": "project_command", "repo_name": "repo", "command_id": "pytest", "argv": ["pytest"]}
        )
