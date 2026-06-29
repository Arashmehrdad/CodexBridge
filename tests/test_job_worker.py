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
