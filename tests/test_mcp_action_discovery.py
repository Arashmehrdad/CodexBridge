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
REALISTIC_ACTION_OUTPUTS = {
    "inspect_repo_status": {
        "ok": True,
        "repo_name": "repo",
        "branch": "main",
        "git_status": "## main\n M codexbridge/server.py\n",
        "recent_commits": ["abc123 hotfix", "def456 previous change"],
        "diff_stat": " codexbridge/server.py | 10 +++++-----\n 1 file changed, 5 insertions(+), 5 deletions(-)\n",
        "changed_files": ["codexbridge/server.py"],
    },
    "codex_plan_task": {"ok": True, "repo_name": "repo", "plan": "1. Inspect\n2. Patch\n", "result": {"summary": "narrow plan"}, "error": ""},
    "codex_implement_task": {
        "ok": True,
        "repo_name": "repo",
        "changed_files": ["codexbridge/server.py", "tests/test_mcp_action_discovery.py"],
        "tests": [{"command": "python -m pytest -q", "exit_code": 0}],
        "result": {"summary": "applied"},
        "error": "",
    },
    "get_latest_run_result": {"ok": True, "run_id": "run_1", "status": "completed", "repo_name": "repo", "result": {"summary": "done"}, "error": ""},
    "git_diff_summary": {"git_status": "## main\n M codexbridge/server.py\n", "diff_stat": " 1 file changed\n"},
    "commit_selected_files": {"ok": True, "repo_name": "repo", "commit_sha": "abc123", "files": ["codexbridge/server.py"], "message": "hotfix", "error": ""},
    "run_local_self_check": {"ok": True, "checks": {"pytest": {"ok": True}, "pip_check": {"ok": True}}, "error": ""},
    "start_codex_plan_task_async": {"ok": True, "run_id": "run_2", "status": "queued", "repo_name": "repo", "result": {}, "error": ""},
    "start_codex_implement_task_async": {"ok": True, "run_id": "run_3", "status": "queued", "repo_name": "repo", "result": {}, "error": ""},
    "get_run_status": {"ok": True, "run_id": "run_2", "status": "running", "repo_name": "repo", "result": {}, "error": ""},
    "get_run_events": {"ok": True, "run_id": "run_2", "events": [{"stage": "queued", "message": "Run queued"}], "error": ""},
    "get_run_result": {"ok": True, "run_id": "run_2", "status": "completed", "repo_name": "repo", "result": {"summary": "done"}, "error": ""},
    "list_runs": {"ok": True, "runs": [{"run_id": "run_1", "status": "completed", "repo_name": "repo"}], "error": ""},
    "cancel_run": {"run_id": "run_2", "status": "cancelled", "cancelled": True, "terminated": True},
    "start_supervised_recovery_task": {"ok": True, "supervisor_id": "sup_1", "status": "queued", "result": {"summary": "queued"}, "error": ""},
    "get_supervisor_status": {"ok": True, "supervisor_id": "sup_1", "status": "needs_input", "result": {"summary": "waiting"}, "error": ""},
    "get_supervisor_events": {"ok": True, "supervisor_id": "sup_1", "events": [{"stage": "planning", "message": "tick"}], "error": ""},
    "get_supervisor_result": {"ok": True, "supervisor_id": "sup_1", "status": "completed", "result": {"summary": "done"}, "error": ""},
    "resume_supervisor": {"ok": True, "supervisor_id": "sup_1", "status": "queued", "result": {"summary": "resumed"}, "error": ""},
    "pause_supervisor": {"ok": True, "supervisor_id": "sup_1", "status": "paused", "result": {"summary": "paused"}, "error": ""},
    "cancel_supervisor": {"ok": True, "supervisor_id": "sup_1", "status": "cancelled", "result": {"summary": "cancelled"}, "error": ""},
    "get_supervisor_notifications": {
        "ok": True,
        "supervisor_id": "sup_1",
        "notifications": [{"id": 1, "delivery_status": "pending", "channel": "file"}],
        "error": "",
    },
    "get_supervisor_resume_prompt": {
        "supervisor_id": "sup_1",
        "exists": True,
        "path": "D:\\Github\\CodexBridge\\runs\\supervisors\\sup_1\\resume_prompt.txt",
        "content": "resume prompt",
    },
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


def test_realistic_outputs_validate_against_public_action_output_schemas() -> None:
    actions = {action["name"]: action for action in discovered_actions()}

    assert set(REALISTIC_ACTION_OUTPUTS) == set(actions)

    for name, sample in REALISTIC_ACTION_OUTPUTS.items():
        json.dumps(sample, sort_keys=True)
        validate(instance=sample, schema=actions[name]["outputSchema"])


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

    result = server.list_runs(repo_name="repo")

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


def test_inspect_repo_status_normalizes_live_git_shapes(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path)
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "inspect_status",
        lambda repo_root: {
            "branch": "main",
            "git_status": "## main\n M codexbridge/server.py\n",
            "recent_commits": "abc123 first\n\ndef456 second\n",
            "diff_stat": " 1 file changed\n",
            "changed_files": ["codexbridge/server.py"],
        },
    )
    action = {item["name"]: item for item in discovered_actions()}["inspect_repo_status"]

    result = server.inspect_repo_status("repo")

    assert result["recent_commits"] == ["abc123 first", "def456 second"]
    assert result["changed_files"] == ["codexbridge/server.py"]
    validate(instance=result, schema=action["outputSchema"])


def test_event_list_actions_return_wrapped_dicts(monkeypatch, tmp_path) -> None:
    class FakeJobManager:
        def get_events(self, run_id, limit=50):
            return [{"stage": "queued", "message": "Run queued"}]

    class FakeSupervisorService:
        def get_events(self, supervisor_id, limit=50):
            return [{"stage": "planning", "message": "Supervisor tick"}]

        def get_notifications(self, supervisor_id, delivery_status=None, limit=50):
            return [{"id": 1, "delivery_status": "pending"}]

    config = AppConfig(repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path)
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())
    monkeypatch.setattr(server, "get_supervisor_service", lambda: FakeSupervisorService())
    actions = {item["name"]: item for item in discovered_actions()}

    run_events = server.get_run_events("run_1")
    supervisor_events = server.get_supervisor_events("sup_1")
    notifications = server.get_supervisor_notifications("sup_1")

    assert run_events["run_id"] == "run_1"
    assert supervisor_events["supervisor_id"] == "sup_1"
    assert notifications["supervisor_id"] == "sup_1"
    validate(instance=run_events, schema=actions["get_run_events"]["outputSchema"])
    validate(instance=supervisor_events, schema=actions["get_supervisor_events"]["outputSchema"])
    validate(instance=notifications, schema=actions["get_supervisor_notifications"]["outputSchema"])
