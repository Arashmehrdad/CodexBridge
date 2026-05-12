from __future__ import annotations

import asyncio
import json
import re

from jsonschema import Draft202012Validator, validate

from codexbridge.config import AppConfig, RepoConfig
import codexbridge.server as server


ACTION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
EXPECTED_EXPOSED_ACTIONS = {
    "inspect_repo_status",
    "codex_plan_task",
    "codex_implement_task",
    "get_latest_run_result",
    "git_diff_summary",
    "commit_selected_files",
    "run_local_self_check",
    "start_codex_plan_task_async",
    "start_codex_implement_task_async",
    "get_run_status",
    "get_run_events",
    "get_run_result",
    "list_runs",
    "cancel_run",
    "start_supervised_recovery_task",
    "get_supervisor_status",
    "get_supervisor_events",
    "get_supervisor_result",
    "resume_supervisor",
    "pause_supervisor",
    "cancel_supervisor",
    "get_supervisor_notifications",
    "get_supervisor_resume_prompt",
}


def discovered_actions() -> list[dict]:
    async def _list() -> list[dict]:
        tools = await server.mcp.list_tools()
        return [tool.to_mcp_tool().model_dump(mode="json") for tool in tools]

    return asyncio.run(_list())


def test_mcp_action_discovery_is_json_serializable() -> None:
    actions = discovered_actions()

    encoded = json.dumps(actions, sort_keys=True)

    assert "cancel_run" in encoded
    assert len(actions) == len(EXPECTED_EXPOSED_ACTIONS)


def test_mcp_action_names_are_unique_stable_and_valid() -> None:
    actions = discovered_actions()
    names = [action["name"] for action in actions]

    assert set(names) == EXPECTED_EXPOSED_ACTIONS
    assert len(names) == len(set(names))
    assert all(ACTION_NAME_RE.match(name) for name in names)


def test_mcp_actions_have_descriptions_annotations_and_valid_input_schemas() -> None:
    for action in discovered_actions():
        assert action["description"]
        assert len(action["description"]) <= 300
        schema = action["inputSchema"]
        Draft202012Validator.check_schema(schema)
        assert schema["type"] == "object"
        assert "anyOf" not in json.dumps(schema)
        assert "oneOf" not in json.dumps(schema)
        annotations = action["annotations"]
        assert isinstance(annotations, dict)
        assert isinstance(annotations["readOnlyHint"], bool)
        assert isinstance(annotations["destructiveHint"], bool)
        assert isinstance(annotations["idempotentHint"], bool)
        assert isinstance(annotations["openWorldHint"], bool)
        assert action["outputSchema"] is not None
        Draft202012Validator.check_schema(action["outputSchema"])


def test_mcp_risky_actions_are_not_marked_read_only_or_destructive() -> None:
    actions = {action["name"]: action for action in discovered_actions()}
    write_actions = {
        "codex_implement_task",
        "commit_selected_files",
        "start_codex_implement_task_async",
        "cancel_run",
        "start_supervised_recovery_task",
        "resume_supervisor",
        "pause_supervisor",
        "cancel_supervisor",
    }
    for name, action in actions.items():
        annotations = action["annotations"]
        if name in write_actions:
            assert annotations["readOnlyHint"] is False
            assert annotations["destructiveHint"] is False
        else:
            assert annotations["readOnlyHint"] is True


def test_currently_exposed_batch_actions_are_discoverable() -> None:
    actions = {action["name"]: action for action in discovered_actions()}

    assert "git_diff_summary" in actions
    assert "list_runs" in actions
    assert "get_supervisor_status" in actions
    assert "run_local_self_check" in actions
    assert "pytest" not in actions
    assert "pip_check" not in actions
    assert "dashboard_summary" not in actions
    assert "memory_search" not in actions
    assert "policy_evaluate" not in actions
    assert "local_coding_preview" not in actions


def test_all_mcp_action_output_schemas_are_json_serializable_and_valid() -> None:
    for action in discovered_actions():
        encoded = json.dumps(action["outputSchema"], sort_keys=True)
        assert encoded
        Draft202012Validator.check_schema(action["outputSchema"])


def test_run_local_self_check_output_matches_schema(monkeypatch, tmp_path) -> None:
    config = AppConfig(repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path)
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(server, "run_self_check", lambda **kwargs: {"ok": True, "checks": {}, "error": ""})
    action = {item["name"]: item for item in discovered_actions()}["run_local_self_check"]

    result = server.run_local_self_check()

    validate(instance=result, schema=action["outputSchema"])


def test_list_runs_output_matches_schema(monkeypatch) -> None:
    class FakeJobManager:
        def list_runs(self, repo_name=None, status=None, limit=20):
            return [{"run_id": "run_1", "status": "completed", "repo_name": repo_name or "repo"}]

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())
    action = {item["name"]: item for item in discovered_actions()}["list_runs"]

    result = {"result": server.list_runs(repo_name="repo")}

    validate(instance=result, schema=action["outputSchema"])


def test_run_status_events_result_and_supervisor_schemas_are_present() -> None:
    actions = {item["name"]: item for item in discovered_actions()}
    for name in {
        "get_run_status",
        "get_run_events",
        "get_run_result",
        "get_supervisor_status",
        "get_supervisor_events",
        "get_supervisor_result",
        "get_supervisor_notifications",
        "get_supervisor_resume_prompt",
    }:
        assert actions[name]["outputSchema"] is not None
