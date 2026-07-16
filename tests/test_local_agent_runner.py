from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.local_agent import LocalAgentOrchestrator, LocalAgentTaskInput
from codexbridge.local_agent.models import (
    CommandRunResult,
    CommandRunStatus,
    PermissionTier,
    RoutingDecision,
)


class StubProjectCommandRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run_project_command(self, **kwargs) -> CommandRunResult:
        self.calls.append(kwargs)
        return CommandRunResult(
            run_id="stub-run",
            command_id=kwargs["command_id"],
            repo_name=kwargs.get("repo_name"),
            repo_path=kwargs.get("repo_path"),
            working_directory=kwargs.get("repo_path"),
            argv=[kwargs["command_id"]],
            permission_tier=PermissionTier(kwargs["permission_tier"]),
            status=CommandRunStatus.SUCCESS,
            exit_code=0,
            duration_seconds=0.0,
            timeout_seconds=30,
            timed_out=False,
            audit_event_id="stub-audit",
            created_at="2026-07-16T00:00:00+00:00",
        )


def test_orchestrator_routes_run_pytest_to_injected_runner(tmp_path: Path) -> None:
    runner = StubProjectCommandRunner()

    result = LocalAgentOrchestrator(runner=runner).handle_task(
        LocalAgentTaskInput(objective="run pytest", repo_path=tmp_path)
    )

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.command_result is not None
    assert result.command_result.command_id == "pytest"
    assert runner.calls[0]["repo_path"] == tmp_path
    assert result.audit_event.metadata["codex_called"] is False


def test_orchestrator_routes_git_status_to_injected_runner(tmp_path: Path) -> None:
    runner = StubProjectCommandRunner()

    result = LocalAgentOrchestrator(runner=runner).handle_task(
        LocalAgentTaskInput(objective="inspect git status", repo_path=tmp_path)
    )

    assert result.command_result is not None
    assert result.command_result.command_id == "git_status"
    assert runner.calls[0]["permission_tier"] == PermissionTier.READ_ONLY


def test_orchestrator_does_not_route_edit_tasks_to_runner() -> None:
    runner = StubProjectCommandRunner()

    result = LocalAgentOrchestrator(runner=runner).handle_task(
        "fix and refactor the runner"
    )

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.command_result is None
    assert runner.calls == []
    assert result.audit_event.metadata["codex_called"] is False


def test_orchestrator_requires_explicit_execution_context_for_project_commands(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="requires durable application context"):
        LocalAgentOrchestrator().handle_task(
            LocalAgentTaskInput(objective="run pytest", repo_path=tmp_path)
        )


def test_orchestrator_uses_durable_runner_when_app_config_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codexbridge.local_agent import orchestrator as orchestrator_module

    captured = {}

    class FakeDurableRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        orchestrator_module, "DurableProjectCommandRunner", FakeDurableRunner
    )
    app_config = object()
    job_manager = object()
    config_path = Path("config.yaml")

    orchestrator = LocalAgentOrchestrator(
        app_config=app_config,
        config_path=config_path,
        durable_job_manager=job_manager,
    )

    assert isinstance(orchestrator.runner, FakeDurableRunner)
    assert captured == {
        "config": app_config,
        "config_path": config_path,
        "job_manager": job_manager,
    }


def test_local_agent_runner_introduces_no_codex_or_local_model_calls() -> None:
    source = Path("codexbridge/local_agent/orchestrator.py").read_text(encoding="utf-8")

    assert "CodexRunner" not in source
    assert "ollama" not in source.lower()
