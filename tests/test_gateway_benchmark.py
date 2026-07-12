from __future__ import annotations

import asyncio

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

import codexbridge.server as server
from codexbridge.gateway_models import (
    RepoApplyRequest,
    RepoQueryRequest,
    RunStartRequest,
)
from codexbridge.knowledge_tools_integration import register_knowledge_tools


def _actions() -> dict[str, dict]:
    register_knowledge_tools(server.mcp)
    tools = asyncio.run(server.mcp.list_tools())
    return {tool.name: tool.to_mcp_tool().model_dump(mode="json") for tool in tools}


def test_deterministic_gateway_surface_benchmark() -> None:
    actions = _actions()
    assert len(actions) == 24
    assert {"repo_query", "repo_apply", "run_start", "docker_query", "docker_action", "cloudflare_query", "cloudflare_action", "ssh_query", "ssh_action", "system_query", "system_action", "knowledge_query", "knowledge_action", "codex_plan", "codex_implement"} <= set(actions)
    retired = {
        "inspect_repo_status", "apply_previewed_repo_change", "start_project_command_async",
        "list_docker_capabilities", "start_cloudflare_action_async", "list_ssh_capabilities",
        "reload_service", "read_repo_wiki", "start_codex_plan_task_async", "start_codex_implement_task_async",
    }
    assert retired.isdisjoint(actions)
    for action in actions.values():
        Draft202012Validator.check_schema(action["inputSchema"])
        Draft202012Validator.check_schema(action["outputSchema"])
    for name in {"repo_query", "docker_query", "cloudflare_query", "ssh_query", "system_query", "knowledge_query", "codex_plan"}:
        assert actions[name]["annotations"]["readOnlyHint"] is True
    for name in {"repo_apply", "repo_commit", "run_start", "docker_action", "cloudflare_action", "ssh_action", "system_action", "knowledge_action", "codex_implement"}:
        assert actions[name]["annotations"]["readOnlyHint"] is False


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
