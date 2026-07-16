from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from codexbridge.local_agent.durable_command_runner import DurableProjectCommandRunner
from codexbridge.local_agent.models import CommandRunStatus, PermissionTier


class FakeStore:
    def __init__(self, runs: list[dict]):
        self.runs = list(runs)

    def get_run(self, run_id: str) -> dict:
        assert run_id == "run_1"
        if len(self.runs) > 1:
            return self.runs.pop(0)
        return self.runs[0]


class FakeJobManager:
    def __init__(self, runs: list[dict]):
        self.store = FakeStore(runs)
        self.started: list[tuple[str, str]] = []
        self.cancelled: list[str] = []

    def start_project_command(self, repo_name: str, command_id: str) -> dict:
        self.started.append((repo_name, command_id))
        return {"run_id": "run_1"}

    def cancel_run(self, run_id: str) -> None:
        self.cancelled.append(run_id)


def _run(tmp_path: Path, *, status: str, exit_code: int | None = 0, error: str = "") -> dict:
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_id": "run_1",
        "run_dir": str(run_dir),
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": 0.25,
        "error": error,
    }


@pytest.fixture
def configured_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    local_profile = SimpleNamespace(
        permission_tier=PermissionTier.SAFE_LOCAL_TEST,
        default_timeout_seconds=120,
    )
    durable_profile = SimpleNamespace(argv=["python", "-m", "pytest", "-q"])
    monkeypatch.setattr(
        "codexbridge.local_agent.durable_command_runner.resolve_repo_config",
        lambda config, repo_name: ("sample", SimpleNamespace(command_profiles=[])),
    )
    monkeypatch.setattr(
        "codexbridge.local_agent.durable_command_runner.resolve_repo",
        lambda config, repo_name: repo.resolve(),
    )
    monkeypatch.setattr(
        "codexbridge.local_agent.durable_command_runner.get_command_profile",
        lambda command_id: local_profile if command_id == "pytest" else None,
    )
    monkeypatch.setattr(
        "codexbridge.local_agent.durable_command_runner.resolve_command_profile",
        lambda command_id, profiles: durable_profile,
    )

    def make(runs: list[dict], **kwargs) -> tuple[DurableProjectCommandRunner, FakeJobManager]:
        manager = FakeJobManager(runs)
        runner = DurableProjectCommandRunner(
            config=SimpleNamespace(),
            job_manager=manager,
            poll_interval_seconds=0,
            wait_grace_seconds=kwargs.get("wait_grace_seconds", 0),
        )
        return runner, manager

    return repo, make


def test_durable_completion_returns_artifact_references(configured_runner, tmp_path: Path) -> None:
    repo, make = configured_runner
    runner, manager = make([_run(tmp_path, status="completed")])

    result = runner.run_project_command(
        command_id="pytest", repo_name="sample", repo_path=repo
    )

    assert result.status == CommandRunStatus.SUCCESS
    assert result.exit_code == 0
    assert result.run_id == "run_1"
    assert result.stdout_path == tmp_path / "runs" / "run_1" / "stdout.txt"
    assert result.stderr_path == tmp_path / "runs" / "run_1" / "stderr.txt"
    assert result.result_path == tmp_path / "runs" / "run_1" / "result.json"
    assert manager.started == [("sample", "pytest")]


def test_nonzero_durable_exit_maps_to_failed(configured_runner, tmp_path: Path) -> None:
    repo, make = configured_runner
    runner, _ = make([_run(tmp_path, status="failed", exit_code=3, error="failed")])

    result = runner.run_project_command(
        command_id="pytest", repo_name="sample", repo_path=repo
    )

    assert result.status == CommandRunStatus.FAILED
    assert result.exit_code == 3
    assert result.error == "failed"


def test_wait_timeout_requests_durable_cancellation(
    configured_runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moments = iter((0.0, 1.0))
    monkeypatch.setattr(
        "codexbridge.local_agent.durable_command_runner.time.monotonic",
        lambda: next(moments),
    )
    repo, make = configured_runner
    runner, manager = make(
        [
            _run(tmp_path, status="running", exit_code=None),
            _run(tmp_path, status="cancelled", exit_code=None),
        ]
    )

    result = runner.run_project_command(
        command_id="pytest",
        repo_name="sample",
        repo_path=repo,
        timeout_seconds=1,
    )

    assert manager.cancelled == ["run_1"]
    assert result.status == CommandRunStatus.TIMEOUT
    assert result.timed_out is True


def test_repository_path_mismatch_is_blocked_before_launch(configured_runner, tmp_path: Path) -> None:
    _, make = configured_runner
    runner, manager = make([_run(tmp_path, status="completed")])

    result = runner.run_project_command(
        command_id="pytest",
        repo_name="sample",
        repo_path=tmp_path / "other",
    )

    assert result.status == CommandRunStatus.BLOCKED
    assert "does not match" in result.error
    assert manager.started == []


def test_permission_mismatch_is_blocked_before_launch(configured_runner, tmp_path: Path) -> None:
    repo, make = configured_runner
    runner, manager = make([_run(tmp_path, status="completed")])

    result = runner.run_project_command(
        command_id="pytest",
        repo_name="sample",
        repo_path=repo,
        permission_tier=PermissionTier.READ_ONLY,
    )

    assert result.status == CommandRunStatus.BLOCKED
    assert "Permission tier mismatch" in result.error
    assert manager.started == []
