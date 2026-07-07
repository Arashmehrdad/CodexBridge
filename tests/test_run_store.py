from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def test_run_store_computes_dynamic_elapsed_and_stale_heartbeat(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )
    now = datetime.now(timezone.utc)
    store.update_run(
        RUN_ID,
        status="running",
        started_at=(now - timedelta(seconds=12)).isoformat(),
        heartbeat_at=(now - timedelta(seconds=45)).isoformat(),
        elapsed_seconds=0.0,
    )

    current = store.get_run(RUN_ID)

    assert current["elapsed_seconds"] >= 11.0
    assert current["heartbeat_age_seconds"] >= 44.0
    assert current["worker_stale"] is True


def test_run_store_heartbeat_merges_existing_progress(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )
    store.set_progress(
        RUN_ID,
        phase="execute",
        progress={"phase_item": "one"},
        elapsed_seconds=1.0,
    )

    current = store.heartbeat(
        RUN_ID,
        elapsed_seconds=2.5,
        progress_updates={"last_output_at": "now"},
    )

    assert current["current_phase"] == "execute"
    assert current["elapsed_seconds"] >= 2.5
    assert current["progress"] == {
        "phase_item": "one",
        "last_output_at": "now",
    }


def test_invalid_run_id_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("../bad")


def test_run_store_repo_filters_are_case_insensitive(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="Sample",
        tool="codex_plan_task",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
    )

    assert store.list_runs(repo_name="sample")[0]["repo_name"] == "Sample"
    assert store.latest_run(repo_name="sample")["repo_name"] == "Sample"
