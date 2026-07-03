from __future__ import annotations

from pathlib import Path

from codexbridge.job_worker import JobWorker
from codexbridge.run_store import RunStore, utc_now


def test_blocked_zero_exit_run_is_persisted_as_failed(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260629T000000Z_codex_implement_task_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="codex_implement_task",
        run_dir=run_dir,
        input_data={"repo_name": "sample"},
    )
    worker = JobWorker(config_path, run_id)
    result = {
        "run_id": run_id,
        "repo_name": "sample",
        "tool": "codex_implement_task",
        "status": "failed",
        "exit_code": 0,
        "started_at": utc_now(),
        "ended_at": utc_now(),
        "duration_seconds": 0.0,
        "changed_files": [],
        "git_status": "## main\n",
        "diff_stat": "",
        "tests_run": [],
        "test_results": "",
        "summary": "Access to the path is denied.",
        "remaining_risks": ["Codex final response reports an implementation blocker"],
        "blocked": True,
        "blockers": ["Codex final response reports an implementation blocker"],
        "error": "Codex final response reports an implementation blocker",
        "safety_failure": False,
    }
    monkeypatch.setattr(worker, "_execute_inner", lambda _started_at: result)

    assert worker.execute() == 1
    persisted = store.get_run(run_id)
    assert persisted["status"] == "failed"
    assert persisted["exit_code"] == 0
    assert persisted["error"]


def test_project_command_worker_persists_output_and_isolates_pytest(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000000Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    captured: dict = {}

    def fake_run(profile, cwd, *, extra_env=None):
        captured["profile"] = profile
        captured["cwd"] = cwd
        captured["extra_env"] = dict(extra_env or {})
        return {
            "ok": True,
            "command_id": "pytest",
            "argv": ["python", "-m", "pytest", "-q"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "1 passed\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_command_profile", fake_run)
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])
    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert result["command_id"] == "pytest"
    assert result["timed_out"] is False
    assert Path(result["temporary_directory"]).is_dir()
    assert Path(result["pytest_basetemp"]).is_dir()
    assert captured["cwd"] == repo
    assert captured["extra_env"]["TMP"] == result["temporary_directory"]
    assert "--basetemp=" in captured["extra_env"]["PYTEST_ADDOPTS"]
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == "1 passed\n"


def test_project_command_worker_rebuilds_scoped_pytest_profile(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    target_file = repo / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260701T000000Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "command_id": "pytest_path",
            "path": r"tests\test_api.py::test_ok",
        },
    )
    captured: dict = {}

    def fake_run(profile, cwd, *, extra_env=None):
        captured["profile"] = profile
        captured["cwd"] = cwd
        captured["extra_env"] = dict(extra_env or {})
        return {
            "ok": True,
            "command_id": "pytest_path",
            "argv": list(profile.argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "stdout": "1 passed\n",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr("codexbridge.job_worker.run_command_profile", fake_run)
    monkeypatch.setattr("codexbridge.job_worker.git_tools.git_status", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.diff_stat", lambda _: "")
    monkeypatch.setattr("codexbridge.job_worker.git_tools.changed_files", lambda _: [])
    worker = JobWorker(config_path, run_id)

    assert worker.execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert captured["cwd"] == repo
    assert captured["profile"].argv == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_api.py::test_ok",
    ]
    assert captured["extra_env"]["TMP"] == result["temporary_directory"]
    assert "--basetemp=" in captured["extra_env"]["PYTEST_ADDOPTS"]
    assert result["command_id"] == "pytest_path"
    assert result["path"] == "tests/test_api.py::test_ok"
    assert result["tests_run"] == ["pytest_path:tests/test_api.py::test_ok"]
    assert result["argv"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_api.py::test_ok",
    ]
