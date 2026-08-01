from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.config import AppConfig, RepoConfig
from soma.job_manager import JobManager


def _manager(tmp_path: Path) -> JobManager:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    return JobManager(config, config_path)


def _legacy_run(
    manager: JobManager,
    run_id: str = "20260427T164656Z_codex_plan_task_53bfa283",
    *,
    result_run_id: str | None = None,
) -> Path:
    run_dir = Path(manager.config.resolve_runs_dir()) / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "input.json").write_text(
        json.dumps(
            {
                "repo_name": "sample",
                "task": "read old evidence",
                "constraints": ["read only"],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps(
            {
                "run_id": result_run_id if result_run_id is not None else run_id,
                "repo_name": "sample",
                "tool": "codex_plan_task",
                "started_at": "2026-04-27T16:46:56+00:00",
                "ended_at": "2026-04-27T16:47:01+00:00",
                "duration_seconds": 5.0,
                "exit_code": 0,
                "summary": "legacy result remains readable",
                "safety_failure": False,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "prompt.txt").write_text("legacy prompt", encoding="utf-8")
    (run_dir / "stdout.txt").write_text("legacy stdout", encoding="utf-8")
    (run_dir / "stderr.txt").write_text("", encoding="utf-8")
    return run_dir


def test_filesystem_only_legacy_run_is_readable_without_database_import(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    run_id = "20260427T164656Z_codex_plan_task_53bfa283"
    _legacy_run(manager, run_id)

    with pytest.raises(KeyError):
        manager.store.get_run(run_id)

    status = manager.get_status(run_id)
    assert status["status"] == "partial"
    assert status["legacy_filesystem_only"] is True
    assert status["database_record_present"] is False

    control = manager.get_control_status(run_id)
    assert control["status"] == "partial"
    assert control["legacy_filesystem_only"] is True
    assert control["database_record_present"] is False
    assert control["details_available"]["events"] is False
    assert control["launcher_running"] is False
    assert control["worker_running"] is False
    assert control["child_running"] is False

    compact_input = manager.get_input(run_id)
    assert compact_input["legacy_filesystem_only"] is True
    assert compact_input["database_record_present"] is False
    assert compact_input["authoritative_storage"].endswith("/input.json")

    output = manager.get_output(run_id, "combined")
    assert output["legacy_filesystem_only"] is True
    assert output["streams"]["stdout"]["text"] == "legacy stdout"

    result = manager.get_result(run_id)
    assert result["summary"] == "legacy result remains readable"
    assert result["legacy_filesystem_only"] is True
    assert result["database_record_present"] is False

    terminal = manager.get_terminal_result(run_id)
    assert terminal["terminal"] is True
    assert terminal["run_outcome"] == "partial"
    assert terminal["legacy_filesystem_only"] is True
    assert terminal["database_record_present"] is False
    assert terminal["evidence"]["authoritative_storage"].endswith("/result.json")

    events = manager.get_event_page(run_id)
    assert events["events"] == []
    assert events["legacy_filesystem_only"] is True
    assert events["events_available"] is False

    summary = manager.get_run_summary(run_id)
    assert summary["run"]["status"] == "partial"
    assert summary["run"]["legacy_filesystem_only"] is True
    assert summary["run"]["database_record_present"] is False

    with pytest.raises(KeyError):
        manager.store.get_run(run_id)


def test_empty_or_nonlegacy_filesystem_directory_remains_not_found(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    empty_id = "20260427T163343Z_codex_plan_task_c274315e"
    (Path(manager.config.resolve_runs_dir()) / empty_id).mkdir(parents=True)

    nonlegacy_id = "20260427T164656Z_project_command_53bfa283"
    nonlegacy_dir = Path(manager.config.resolve_runs_dir()) / nonlegacy_id
    nonlegacy_dir.mkdir()
    (nonlegacy_dir / "input.json").write_text("{}", encoding="utf-8")
    (nonlegacy_dir / "result.json").write_text("{}", encoding="utf-8")

    for run_id in (empty_id, nonlegacy_id):
        response = manager.get_status(run_id)
        assert response["ok"] is False
        assert response["error_code"] == "run_not_found"


def test_legacy_identity_mismatch_fails_closed_without_database_import(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    run_id = "20260427T164656Z_codex_plan_task_53bfa283"
    _legacy_run(
        manager,
        run_id,
        result_run_id="20260427T164657Z_codex_plan_task_53bfa283",
    )

    response = manager.get_status(run_id)
    assert response["ok"] is False
    assert response["error_code"] == "run_not_found"
    assert "identity" in response["error"].lower()
    with pytest.raises(KeyError):
        manager.store.get_run(run_id)
