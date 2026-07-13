from __future__ import annotations

from pathlib import Path

from codexbridge.config import LocalModelConfig
from codexbridge.local_agent import LocalAgentOrchestrator
from codexbridge.local_agent.local_model import LocalModelClient
from codexbridge.local_agent.models import (
    LocalAgentTaskType,
    LocalModelResult,
    LocalModelStatus,
    RoutingDecision,
)
from codexbridge.run_store import utc_now


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        return _result(kwargs["task_type"], "local answer")

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        return _result(kwargs["task_type"], '{"ok": true}', parsed_json={"ok": True})


def _result(task_type: str, content: str, parsed_json=None) -> LocalModelResult:
    return LocalModelResult(
        request_id=f"req_{task_type}",
        task_type=task_type,
        model="fake",
        base_url="http://localhost:11434/v1",
        temperature=0.2,
        max_tokens=128,
        timeout_seconds=5,
        status=LocalModelStatus.SUCCESS,
        content=content,
        parsed_json=parsed_json,
        audit_event_id=f"audit_{task_type}",
        created_at=utc_now(),
    )


def enabled_client(adapter: FakeAdapter) -> LocalModelClient:
    return LocalModelClient(
        config=LocalModelConfig(
            enabled=True, model="fake", timeout_seconds=5, max_tokens=128
        ),
        adapter=adapter,
    )


def test_summarize_log_uses_adapter() -> None:
    adapter = FakeAdapter()
    result = enabled_client(adapter).summarize_log("pytest failed")

    assert result.status == LocalModelStatus.SUCCESS
    assert result.task_type == "summarize_log"
    assert adapter.calls[0]["messages"][0]["role"] == "system"


def test_classify_error_uses_adapter() -> None:
    adapter = FakeAdapter()
    result = enabled_client(adapter).classify_error("ValueError")

    assert result.task_type == "classify_error"
    assert adapter.calls


def test_explain_test_failure_uses_adapter() -> None:
    adapter = FakeAdapter()
    result = enabled_client(adapter).explain_test_failure("assert 1 == 2")

    assert result.task_type == "explain_test_failure"


def test_draft_codex_prompt_does_not_call_codex() -> None:
    adapter = FakeAdapter()
    result = enabled_client(adapter).draft_codex_prompt("failure report")

    assert result.task_type == "draft_codex_prompt"
    assert result.content == "local answer"


def test_decide_whether_codex_needed_returns_local_output_only() -> None:
    adapter = FakeAdapter()
    result = enabled_client(adapter).decide_whether_codex_needed("needs edits?")

    assert result.task_type == "decide_whether_codex_needed"
    assert result.audit_event_id


def test_json_helper_returns_parsed_json() -> None:
    adapter = FakeAdapter()
    result = enabled_client(adapter).classify_error_json("traceback")

    assert result.parsed_json == {"ok": True}


def test_disabled_local_model_returns_blocked() -> None:
    result = LocalModelClient(
        config=LocalModelConfig(enabled=False), adapter=FakeAdapter()
    ).summarize_log("log")

    assert result.status == LocalModelStatus.BLOCKED
    assert "disabled" in result.error


def test_orchestrator_routes_summarize_pytest_output_when_enabled() -> None:
    adapter = FakeAdapter()
    result = LocalAgentOrchestrator(local_model=enabled_client(adapter)).handle_task(
        "summarize this pytest output: failed"
    )

    assert result.task_type == LocalAgentTaskType.LOCAL_MODEL_REASONING
    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.local_model_result is not None
    assert result.local_model_result.task_type == "summarize_log"
    assert result.audit_event.metadata["codex_called"] is False


def test_orchestrator_does_not_route_edit_tasks_to_local_model() -> None:
    adapter = FakeAdapter()
    result = LocalAgentOrchestrator(local_model=enabled_client(adapter)).handle_task(
        "fix this bug in the runner"
    )

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.local_model_result is None
    assert adapter.calls == []


def test_local_model_modules_do_not_execute_commands_or_call_codex() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            Path("codexbridge/local_agent/local_model.py"),
            Path("codexbridge/local_agent/ollama_adapter.py"),
        ]
    )

    assert "subprocess" not in source
    assert "CodexRunner" not in source
    assert "codex_implement" not in source
    assert "ollama run" not in source.lower()
