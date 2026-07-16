from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from codexbridge.local_agent import (
    LocalAgentCommandRunner,
    LocalAgentOrchestrator,
    LocalAgentTaskInput,
)
from codexbridge.local_agent.models import (
    CommandRunStatus,
    PermissionTier,
    RoutingDecision,
)


def fake_completed(
    stdout: str = "ok\n", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_allowed_pytest_profile_returns_structured_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, **kwargs})
        return fake_completed("tests passed\n")

    monkeypatch.setattr("codexbridge.local_agent.runner.subprocess.run", fake_run)
    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="pytest", repo_path=tmp_path
    )

    assert result.command_id == "pytest"
    assert result.argv == ["python", "-m", "pytest", "-q"]
    assert result.status == CommandRunStatus.SUCCESS
    assert result.exit_code == 0
    assert result.permission_tier == PermissionTier.SAFE_LOCAL_TEST
    assert result.working_directory == tmp_path.resolve()
    assert result.duration_seconds >= 0
    assert result.timeout_seconds == 120
    assert result.timed_out is False
    assert result.audit_event_id
    assert calls[0]["shell"] is False


def test_allowed_pip_check_profile_returns_structured_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: fake_completed(),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="pip_check", repo_path=tmp_path
    )

    assert result.command_id == "pip_check"
    assert result.argv == ["python", "-m", "pip", "check"]
    assert result.status == CommandRunStatus.SUCCESS
    assert result.timeout_seconds == 60


def test_allowed_git_status_profile_returns_structured_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: fake_completed(" M file.py\n"),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="git_status", repo_path=tmp_path
    )

    assert result.command_id == "git_status"
    assert result.argv == ["git", "status", "--short"]
    assert result.permission_tier == PermissionTier.READ_ONLY
    assert result.status == CommandRunStatus.SUCCESS


def test_unknown_command_id_does_not_call_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("subprocess should not be called")

    monkeypatch.setattr("codexbridge.local_agent.runner.subprocess.run", fail_run)
    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="unknown", repo_path=tmp_path
    )

    assert result.status == CommandRunStatus.PROFILE_MISSING
    assert result.exit_code is None


def test_arbitrary_shell_like_command_text_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess should not be called")
        ),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="python -c import os", repo_path=tmp_path
    )

    assert result.status == CommandRunStatus.PROFILE_MISSING
    assert result.argv == []


def test_timeout_is_handled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            cmd=["python"], timeout=1, output="partial", stderr="late"
        )

    monkeypatch.setattr("codexbridge.local_agent.runner.subprocess.run", fake_run)
    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="pytest", repo_path=tmp_path, timeout_seconds=1
    )

    assert result.status == CommandRunStatus.TIMEOUT
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.stderr_path is not None
    assert result.stderr_path.read_text(encoding="utf-8") == "late"


def test_missing_repo_path_is_handled_without_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess should not be called")
        ),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="pytest", repo_path=tmp_path / "missing"
    )

    assert result.status == CommandRunStatus.REPO_MISSING
    assert result.error


def test_permission_mismatch_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess should not be called")
        ),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="pytest",
        repo_path=tmp_path,
        permission_tier=PermissionTier.READ_ONLY,
    )

    assert result.status == CommandRunStatus.PERMISSION_DENIED
    assert "Permission tier mismatch" in result.error


def test_result_artifacts_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: fake_completed("out", "err", 1),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="pytest", repo_path=tmp_path
    )

    assert result.status == CommandRunStatus.FAILED
    assert result.result_path is not None
    assert result.stdout_path is not None
    assert result.stderr_path is not None
    assert result.result_path.match("*/runs/local_agent/commands/*/result.json")
    assert result.stdout_path.read_text(encoding="utf-8") == "out"
    assert result.stderr_path.read_text(encoding="utf-8") == "err"
    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == result.run_id
    assert payload["command_id"] == "pytest"
    assert payload["status"] == "failed"
    assert payload["stdout_path"]
    assert payload["stderr_path"]


def test_timeout_above_profile_default_is_denied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess should not be called")
        ),
    )

    result = LocalAgentCommandRunner(runs_dir=tmp_path / "runs").run_project_command(
        command_id="git_status", repo_path=tmp_path, timeout_seconds=31
    )

    assert result.status == CommandRunStatus.PERMISSION_DENIED
    assert "timeout" in result.error.lower()


def test_orchestrator_routes_run_pytest_to_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: fake_completed("ok"),
    )
    runner = LocalAgentCommandRunner(runs_dir=tmp_path / "runs")

    result = LocalAgentOrchestrator(runner=runner).handle_task(
        LocalAgentTaskInput(objective="run pytest", repo_path=tmp_path)
    )

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.command_result is not None
    assert result.command_result.command_id == "pytest"
    assert result.audit_event.metadata["codex_called"] is False


def test_orchestrator_routes_git_status_to_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: fake_completed(""),
    )
    runner = LocalAgentCommandRunner(runs_dir=tmp_path / "runs")

    result = LocalAgentOrchestrator(runner=runner).handle_task(
        LocalAgentTaskInput(objective="inspect git status", repo_path=tmp_path)
    )

    assert result.command_result is not None
    assert result.command_result.command_id == "git_status"


def test_orchestrator_does_not_route_edit_tasks_to_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "codexbridge.local_agent.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess should not be called")
        ),
    )

    result = LocalAgentOrchestrator(
        runner=LocalAgentCommandRunner(runs_dir=tmp_path / "runs")
    ).handle_task("fix and refactor the runner")

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.command_result is None
    assert result.audit_event.metadata["codex_called"] is False


def test_orchestrator_requires_explicit_execution_context_for_project_commands(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="requires durable application context"):
        LocalAgentOrchestrator().handle_task(
            LocalAgentTaskInput(objective="run pytest", repo_path=tmp_path)
        )


def test_orchestrator_uses_durable_runner_when_app_config_is_available(monkeypatch) -> None:
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
    local_agent_files = [
        Path("codexbridge/local_agent/runner.py"),
        Path("codexbridge/local_agent/orchestrator.py"),
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in local_agent_files)

    assert "CodexRunner" not in source
    assert "ollama" not in source.lower()
