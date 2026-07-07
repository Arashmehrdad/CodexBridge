from __future__ import annotations

import json
from pathlib import Path

from codexbridge.config import (
    AppConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHHostConfig,
)
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
        ssh=SSHConfig(
            enabled=True,
            hosts={
                "my_vps": SSHHostConfig(
                    ssh_alias="my-vps",
                    command_profiles=[
                        SSHCommandProfileConfig(
                            command_id="uptime",
                            argv=["uptime"],
                            timeout_seconds=30,
                        )
                    ],
                )
            },
        ),
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
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "codex_implement_task"
    assert status["input"]["requirement_manifest"] == []


def test_start_async_implementation_persists_requirement_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_implementation(
        "sample",
        "REQ-001 Independent requirement accounting\nREQ-002 Canonical repository identity",
        ["README.md"],
        [],
    )

    manifest = manager.get_status(response["run_id"])["input"]["requirement_manifest"]
    assert manifest == [
        {
            "requirement_id": "REQ-001",
            "text": "REQ-001 Independent requirement accounting",
            "mandatory": True,
        },
        {
            "requirement_id": "REQ-002",
            "text": "REQ-002 Canonical repository identity",
            "mandatory": True,
        },
    ]


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


def test_start_pytest_path_persists_normalized_target(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    target_file = tmp_path / "repo" / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    response = manager.start_pytest_path("sample", r"tests\test_api.py::test_ok")

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["command_id"] == "pytest_path"
    assert response["path"] == "tests/test_api.py::test_ok"
    status = manager.get_status(response["run_id"])
    assert status["tool"] == "project_command"
    assert status["input"]["command_id"] == "pytest_path"
    assert status["input"]["path"] == "tests/test_api.py::test_ok"
    input_data = json.loads(
        (tmp_path / "runs" / response["run_id"] / "input.json").read_text(
            encoding="utf-8"
        )
    )
    assert input_data["command_id"] == "pytest_path"
    assert input_data["path"] == "tests/test_api.py::test_ok"


def test_start_ssh_command_creates_durable_run(tmp_path: Path, monkeypatch) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_ssh_command("my_vps", "uptime")

    assert response["accepted"] is True
    assert response["host_id"] == "my_vps"
    assert response["command_id"] == "uptime"
    assert response["writes_remote"] is False
    status = manager.get_status(response["run_id"])
    assert status["repo_name"] == "ssh:my_vps"
    assert status["tool"] == "ssh_command"
    assert status["input"] == {"host_id": "my_vps", "command_id": "uptime"}


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


def test_start_async_duplicate_project_command_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    first = manager.start_project_command("sample", "pytest")
    second = manager.start_project_command("sample", "pytest")

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["duplicate"] is True


def test_start_json_validation_path_persists_normalized_target(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    target_file = tmp_path / "repo" / "data" / "config.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text('{"ok": true}\n', encoding="utf-8")

    response = manager.start_json_validation_path("sample", r"data\config.json")

    assert response["accepted"] is True
    assert response["path"] == "data/config.json"


def test_start_project_command_accepts_case_insensitive_repo_name(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)

    response = manager.start_project_command("Sample", "pytest")

    assert response["accepted"] is True
    assert response["repo_name"] == "sample"
    assert response["requested_repo_name"] == "Sample"


def test_list_runs_and_latest_result_use_canonical_repo_filters(
    tmp_path: Path, monkeypatch
) -> None:
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_plan("Sample", "inspect docs")
    run_id = response["run_id"]
    manager.store.update_run(
        run_id,
        status="completed",
        result_json={"run_id": run_id, "repo_name": "sample", "summary": "done"},
    )

    listed = manager.list_runs(repo_name="Sample")
    latest = manager.latest_result(repo_name="Sample")

    assert listed[0]["repo_name"] == "sample"
    assert latest["repo_name"] == "sample"
