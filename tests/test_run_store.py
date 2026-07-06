from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.run_store import RunStore, validate_run_id


RUN_ID = "20260427T120000Z_codex_plan_task_abcdef12"


def test_run_store_initializes_wal_schema(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    assert store.db_path.exists()
    assert store.journal_mode() == "wal"


def test_run_store_create_list_get_latest_and_reload(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_dir = tmp_path / "runs" / RUN_ID
    created = store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="codex_plan_task",
        run_dir=run_dir,
        input_data={"task": "plan"},
    )
    assert created["status"] == "queued"
    assert store.get_run(RUN_ID)["input"]["task"] == "plan"
    assert store.list_runs(repo_name="sample")[0]["run_id"] == RUN_ID
    assert store.latest_run(tool="codex_plan_task")["run_id"] == RUN_ID

    reloaded = RunStore(tmp_path / "runs")
    assert reloaded.get_run(RUN_ID)["run_id"] == RUN_ID


def test_run_store_updates_status_and_result(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="codex_plan_task",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )
    updated = store.update_run(
        RUN_ID,
        status="completed",
        result_json={"summary": "done"},
        safety_failure=False,
    )
    assert updated["status"] == "completed"
    assert updated["result"]["summary"] == "done"


def test_run_store_tracks_progress_metadata(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )

    updated = store.set_progress(
        RUN_ID,
        phase="apply",
        progress={"current_phase": "apply", "percent": 50},
        elapsed_seconds=1.25,
    )

    assert updated["current_phase"] == "apply"
    assert updated["elapsed_seconds"] == 1.25
    assert updated["progress"]["percent"] == 50
    assert updated["heartbeat_at"]


def test_invalid_run_id_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("../bad")
