from __future__ import annotations

import asyncio
import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any

from jsonschema import Draft202012Validator, validate

from codexbridge.config import AppConfig, LocalModelConfig, RepoConfig
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
    "local_model_health",
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
    # repo reader tools (batch)
    "list_repo_files",
    "read_repo_file",
    "search_repo_text",
    "get_recently_modified_files",
    "repo_git_status",
    "repo_git_diff",
    # controlled local coding tools
    "preview_repo_patch",
    "apply_repo_patch",
    "create_repo_file",
    "delete_repo_file",
    "move_repo_file",
    "revert_managed_patch",
    "run_project_command",
    "git_log",
    "read_repo_files",
    "create_git_branch",
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
    "codex_plan_task": {
        "ok": True,
        "repo_name": "repo",
        "plan": "1. Inspect\n2. Patch\n",
        "result": {"summary": "narrow plan"},
        "error": "",
    },
    "codex_implement_task": {
        "ok": True,
        "repo_name": "repo",
        "changed_files": [
            "codexbridge/server.py",
            "tests/test_mcp_action_discovery.py",
        ],
        "tests": [{"command": "python -m pytest -q", "exit_code": 0}],
        "result": {"summary": "applied"},
        "error": "",
    },
    "get_latest_run_result": {
        "ok": True,
        "run_id": "run_1",
        "status": "completed",
        "repo_name": "repo",
        "result": {"summary": "done"},
        "error": "",
    },
    "git_diff_summary": {
        "git_status": "## main\n M codexbridge/server.py\n",
        "diff_stat": " 1 file changed\n",
    },
    "commit_selected_files": {
        "ok": True,
        "repo_name": "repo",
        "commit_sha": "abc123",
        "files": ["codexbridge/server.py"],
        "message": "hotfix",
        "error": "",
    },
    "run_local_self_check": {
        "ok": True,
        "checks": {"pytest": {"ok": True}, "pip_check": {"ok": True}},
        "error": "",
    },
    "local_model_health": {
        "ok": True,
        "status": "ok",
        "enabled": True,
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2",
        "models_endpoint_reachable": True,
        "configured_model_available": True,
        "completion_succeeded": True,
        "duration_seconds": 0.1,
        "timeout_seconds": 30,
        "error": "",
        "audit_event_id": "audit_1",
    },
    "start_codex_plan_task_async": {
        "ok": True,
        "run_id": "run_2",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "start_codex_implement_task_async": {
        "ok": True,
        "run_id": "run_3",
        "status": "queued",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "get_run_status": {
        "ok": True,
        "run_id": "run_2",
        "status": "running",
        "repo_name": "repo",
        "result": {},
        "error": "",
    },
    "get_run_events": {
        "ok": True,
        "run_id": "run_2",
        "events": [{"stage": "queued", "message": "Run queued"}],
        "error": "",
    },
    "get_run_result": {
        "ok": True,
        "run_id": "run_2",
        "status": "completed",
        "repo_name": "repo",
        "result": {"summary": "done"},
        "error": "",
    },
    "list_runs": {
        "ok": True,
        "runs": [{"run_id": "run_1", "status": "completed", "repo_name": "repo"}],
        "error": "",
    },
    "cancel_run": {
        "run_id": "run_2",
        "status": "cancelled",
        "cancelled": True,
        "terminated": True,
    },
    "start_supervised_recovery_task": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "queued",
        "result": {"summary": "queued"},
        "error": "",
    },
    "get_supervisor_status": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "needs_input",
        "result": {"summary": "waiting"},
        "error": "",
    },
    "get_supervisor_events": {
        "ok": True,
        "supervisor_id": "sup_1",
        "events": [{"stage": "planning", "message": "tick"}],
        "error": "",
    },
    "get_supervisor_result": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "completed",
        "result": {"summary": "done"},
        "error": "",
    },
    "resume_supervisor": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "queued",
        "result": {"summary": "resumed"},
        "error": "",
    },
    "pause_supervisor": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "paused",
        "result": {"summary": "paused"},
        "error": "",
    },
    "cancel_supervisor": {
        "ok": True,
        "supervisor_id": "sup_1",
        "status": "cancelled",
        "result": {"summary": "cancelled"},
        "error": "",
    },
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
    # repo reader tools (batch)
    "list_repo_files": {
        "ok": True,
        "repo_name": "repo",
        "directory": "",
        "files": ["codexbridge/__init__.py", "codexbridge/server.py"],
        "count": 2,
        "truncated": False,
        "max_results": 500,
        "error": "",
    },
    "read_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "path": "README.md",
        "content": "# CodexBridge\n",
        "start_line": 1,
        "end_line": 1,
        "total_lines": 1,
        "size_bytes": 16,
        "sha256": "a" * 64,
        "git_head": "b" * 40,
        "truncated": False,
        "error": "",
    },
    "search_repo_text": {
        "ok": True,
        "repo_name": "repo",
        "query": "def main",
        "directory": "",
        "case_sensitive": False,
        "hits": [
            {
                "path": "codexbridge/server.py",
                "line": 10,
                "snippet": "def main() -> None:",
            }
        ],
        "count": 1,
        "truncated": False,
        "max_results": 50,
        "error": "",
    },
    "get_recently_modified_files": {
        "ok": True,
        "repo_name": "repo",
        "files": [{"path": "codexbridge/server.py", "mtime": 1720000000.0}],
        "count": 1,
        "limit": 50,
        "error": "",
    },
    "repo_git_status": {
        "ok": True,
        "repo_name": "repo",
        "status": "## main\n M codexbridge/server.py\n",
        "error": "",
    },
    "repo_git_diff": {
        "ok": True,
        "repo_name": "repo",
        "path": "",
        "staged": False,
        "diff": "diff --git a/codexbridge/server.py b/codexbridge/server.py\n",
        "truncated": False,
        "error": "",
    },
    # controlled local coding tools
    "preview_repo_patch": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "diff": "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-old\n+new\n",
        "changed_files": ["README.md"],
        "changed_lines": 2,
        "changed_bytes": 3,
        "git_head": "b" * 40,
        "validation_errors": [],
        "error": "",
    },
    "apply_repo_patch": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "changed_files": ["README.md"],
        "results": [{"path": "README.md", "sha256": "a" * 64}],
        "git_head": "b" * 40,
        "error": "",
    },
    "create_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "path": "docs/new.md",
        "sha256": "a" * 64,
        "size_bytes": 10,
        "error": "",
    },
    "delete_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "path": "docs/old.md",
        "rollback_id": "20260624T120000Z_delete_abcd1234",
        "error": "",
    },
    "move_repo_file": {
        "ok": True,
        "repo_name": "repo",
        "source_path": "docs/old.md",
        "destination_path": "docs/new.md",
        "sha256": "a" * 64,
        "rollback_id": "20260624T120000Z_move_abcd1234",
        "error": "",
    },
    "revert_managed_patch": {
        "ok": True,
        "patch_id": "20260624T120000Z_patch_abcd1234",
        "repo_name": "repo",
        "reverted_files": ["README.md"],
        "error": "",
    },
    "run_project_command": {
        "ok": True,
        "repo_name": "repo",
        "command_id": "pytest",
        "argv": ["python", "-m", "pytest", "-q"],
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 1.5,
        "stdout": "1 passed\n",
        "stderr": "",
        "output_truncated": False,
        "error": "",
    },
    "git_log": {
        "ok": True,
        "repo_name": "repo",
        "commits": [
            {
                "sha": "a" * 40,
                "author_name": "Dev",
                "author_email": "d@example.com",
                "date": "2026-06-24",
                "subject": "fix: patch",
            }
        ],
        "count": 1,
        "path": "",
        "error": "",
    },
    "read_repo_files": {
        "ok": True,
        "repo_name": "repo",
        "results": [
            {"ok": True, "path": "README.md", "content": "# hi\n", "error": ""}
        ],
        "count": 1,
        "truncated_batch": False,
        "error": "",
    },
    "create_git_branch": {
        "ok": True,
        "repo_name": "repo",
        "branch_name": "feature/my-branch",
        "error": "",
    },
}


class FakeResponse:
    def __init__(self, payload: dict[str, Any] | str, status: int = 200):
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        if isinstance(self.payload, str):
            return self.payload.encode("utf-8")
        return json.dumps(self.payload).encode("utf-8")


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
        # controlled local coding tools
        "apply_repo_patch",
        "create_repo_file",
        "delete_repo_file",
        "move_repo_file",
        "revert_managed_patch",
        "run_project_command",
        "create_git_branch",
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
    assert "local_model_health" in actions
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
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "run_self_check",
        lambda **kwargs: {"ok": True, "checks": {}, "error": ""},
    )
    action = {item["name"]: item for item in discovered_actions()}[
        "run_local_self_check"
    ]

    result = server.run_local_self_check()

    validate(instance=result, schema=action["outputSchema"])


def test_local_model_health_disabled_does_not_call_http(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("no HTTP call expected")
        ),
    )
    action = {item["name"]: item for item in discovered_actions()}["local_model_health"]

    result = server.local_model_health()

    assert result["status"] == "disabled"
    assert result["ok"] is False
    assert result["models_endpoint_reachable"] is False
    validate(instance=result, schema=action["outputSchema"])


def test_local_model_health_success_uses_models_and_tiny_completion(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True, model="llama3.2", timeout_seconds=5),
    )
    server.set_config(config, tmp_path / "config.yaml")
    captured: dict[str, Any] = {}

    def fake_models(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["models_url"] = request.full_url
        captured["models_timeout"] = timeout
        return FakeResponse({"data": [{"id": "llama3.2"}]})

    def fake_completion(request: urllib.request.Request, timeout: int) -> FakeResponse:
        captured["completion_url"] = request.full_url
        captured["completion_timeout"] = timeout
        captured["completion_body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(server, "_local_model_urlopen", fake_models)
    monkeypatch.setattr(server, "_local_model_transport", fake_completion)
    action = {item["name"]: item for item in discovered_actions()}["local_model_health"]

    result = server.local_model_health()

    assert captured["models_url"] == "http://localhost:11434/v1/models"
    assert captured["models_timeout"] == 5
    assert captured["completion_url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["completion_timeout"] == 5
    assert captured["completion_body"]["model"] == "llama3.2"
    assert captured["completion_body"]["max_tokens"] == 16
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["configured_model_available"] is True
    assert result["completion_succeeded"] is True
    validate(instance=result, schema=action["outputSchema"])


def test_local_model_health_connection_failure_returns_unavailable(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: (_ for _ in ()).throw(
            urllib.error.URLError("refused")
        ),
    )

    result = server.local_model_health()

    assert result["status"] == "unavailable"
    assert result["ok"] is False
    assert result["completion_succeeded"] is False


def test_local_model_health_timeout_returns_timeout(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: (_ for _ in ()).throw(
            urllib.error.URLError(socket.timeout("timed out"))
        ),
    )

    result = server.local_model_health()

    assert result["status"] == "timeout"
    assert result["ok"] is False


def test_local_model_health_model_missing_does_not_run_completion(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True, model="missing-model"),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: FakeResponse({"data": [{"id": "llama3.2"}]}),
    )
    monkeypatch.setattr(
        server,
        "_local_model_transport",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("completion should not run")
        ),
    )

    result = server.local_model_health()

    assert result["status"] == "model_missing"
    assert result["configured_model_available"] is False
    assert result["completion_succeeded"] is False


def test_local_model_health_malformed_models_response_returns_failed(
    monkeypatch, tmp_path
) -> None:
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        local_model=LocalModelConfig(enabled=True),
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_local_model_urlopen",
        lambda request, timeout: FakeResponse({"models": ["llama3.2"]}),
    )

    result = server.local_model_health()

    assert result["status"] == "failed"
    assert result["ok"] is False
    assert result["completion_succeeded"] is False


def test_list_runs_output_matches_schema(monkeypatch) -> None:
    class FakeJobManager:
        def list_runs(self, repo_name=None, status=None, limit=20):
            return [
                {
                    "run_id": "run_1",
                    "status": "completed",
                    "repo_name": repo_name or "repo",
                }
            ]

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
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
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
    action = {item["name"]: item for item in discovered_actions()}[
        "inspect_repo_status"
    ]

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

    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobManager())
    monkeypatch.setattr(
        server, "get_supervisor_service", lambda: FakeSupervisorService()
    )
    actions = {item["name"]: item for item in discovered_actions()}

    run_events = server.get_run_events("run_1")
    supervisor_events = server.get_supervisor_events("sup_1")
    notifications = server.get_supervisor_notifications("sup_1")

    assert run_events["run_id"] == "run_1"
    assert supervisor_events["supervisor_id"] == "sup_1"
    assert notifications["supervisor_id"] == "sup_1"
    validate(instance=run_events, schema=actions["get_run_events"]["outputSchema"])
    validate(
        instance=supervisor_events,
        schema=actions["get_supervisor_events"]["outputSchema"],
    )
    validate(
        instance=notifications,
        schema=actions["get_supervisor_notifications"]["outputSchema"],
    )
