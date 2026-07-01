from __future__ import annotations

from pathlib import Path

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.job_manager import JobManager


class FakeProcess:
    pid = 12345


def make_git_repo(path: Path) -> None:
    path.mkdir()
    (path / ".git").mkdir()


def make_manager(tmp_path: Path, monkeypatch) -> JobManager:
    repo = tmp_path / "repo"
    make_git_repo(repo)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    monkeypatch.setattr(
        "codexbridge.job_manager.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    return JobManager(config, config_path)


def test_start_async_plan_creates_run_and_event(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    assert response["accepted"] is True
    assert response["run_id"]
    status = manager.get_status(response["run_id"])
    assert status["status"] == "queued"
    events = manager.get_events(response["run_id"])
    assert events[-1]["stage"] == "worker"


def test_start_async_implementation_validates_files(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_implementation("sample", "edit docs", ["README.md"], [])
    assert response["accepted"] is True
    assert manager.get_status(response["run_id"])["tool"] == "codex_implement_task"


def test_start_async_project_command_creates_durable_run(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_project_command("sample", "pytest")

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["command_id"] == "pytest"
    assert response["run_id"]
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "project_command"
    assert status["input"]["command_id"] == "pytest"


def test_cancel_run_marks_cancelled(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "codexbridge.job_manager.subprocess.run", lambda *args, **kwargs: None
    )
    response = manager.start_plan("sample", "inspect docs")
    cancelled = manager.cancel_run(response["run_id"])
    assert cancelled["cancelled"] is True
    assert manager.get_status(response["run_id"])["status"] == "cancelled"


def test_reconcile_startup_marks_running_failed(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("sample", "inspect docs")
    manager.store.update_run(response["run_id"], status="running")
    assert manager.reconcile_startup() == 1
    assert manager.get_status(response["run_id"])["status"] == "failed"
