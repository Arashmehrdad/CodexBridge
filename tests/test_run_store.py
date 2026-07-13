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


def test_event_cursor_is_ascending_and_preserves_legacy_latest_page(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(run_id=RUN_ID, repo_name="sample", tool="project_command", run_dir=tmp_path / "runs" / RUN_ID, input_data={})
    for index in range(4):
        store.append_event(RUN_ID, level="info", stage="test", message=str(index))
    legacy = store.get_events(RUN_ID, limit=2)
    assert [event["message"] for event in legacy] == ["2", "3"]
    first_page = store.get_events(RUN_ID, limit=2, after_id=0)
    assert [event["message"] for event in first_page] == ["0", "1"]
    cursor = first_page[-1]["id"]
    assert [event["message"] for event in store.get_events(RUN_ID, limit=2, after_id=cursor)] == ["2", "3"]
    assert store.get_events(RUN_ID, limit=2, after_id=999999) == []


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


def test_worker_launch_claim_and_heartbeat_are_lease_scoped(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={"command_id": "pytest"},
        status="launch_pending",
        worker_lease_token="lease-1",
    )

    created = store.get_run(RUN_ID)
    assert created["status"] == "launch_pending"
    assert created["current_phase"] == "launch_pending"

    launched = store.record_worker_launch(RUN_ID, 111)
    assert launched["status"] == "queued"
    assert launched["launcher_pid"] == 111
    assert launched["launch_attempts"] == 1

    assert (
        store.claim_worker(
            RUN_ID,
            lease_token="wrong",
            worker_pid=222,
            worker_identity="222:windows:1",
        )
        is False
    )
    assert store.claim_worker(
        RUN_ID,
        lease_token="lease-1",
        worker_pid=222,
        worker_identity="222:windows:1",
    )
    claimed = store.get_run(RUN_ID)
    assert claimed["status"] == "running"
    assert claimed["worker_pid"] == 222
    assert claimed["worker_identity"] == "222:windows:1"
    assert claimed["worker_claimed_at"]

    assert (
        store.heartbeat_worker(
            RUN_ID,
            lease_token="wrong",
            elapsed_seconds=1.0,
            progress_updates={"phase": "ignored"},
        )
        is False
    )
    assert store.heartbeat_worker(
        RUN_ID,
        lease_token="lease-1",
        elapsed_seconds=2.0,
        progress_updates={"phase": "active"},
    )
    assert store.get_run(RUN_ID)["progress"]["phase"] == "active"


def test_recoverable_run_listing_and_legacy_stale_method_are_conservative(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    recoverable_statuses = [
        "launch_pending",
        "queued",
        "running",
        "cancellation_pending",
        "recovery_pending",
    ]
    for index, status in enumerate(recoverable_statuses):
        run_id = f"20260711T12000{index}Z_project_command_deadbee{index}"
        store.create_run(
            run_id=run_id,
            repo_name="sample",
            tool="project_command",
            run_dir=tmp_path / "runs" / run_id,
            input_data={},
            status=status,
        )

    assert [run["status"] for run in store.list_recoverable_runs()] == (
        recoverable_statuses
    )
    assert store.mark_stale_running() == 0
    assert store.list_runs(status="running")[0]["status"] == "running"


def test_terminal_transition_rejects_stale_lease_and_terminal_overwrite(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="launch_pending",
        worker_lease_token="lease-current",
    )
    launched = store.record_worker_launch(RUN_ID, 111)
    assert launched is not None
    assert store.claim_worker(
        RUN_ID,
        lease_token="lease-current",
        lease_generation=1,
        expected_state_version=launched["state_version"],
        worker_pid=222,
        worker_identity="222:windows:1",
    )
    running = store.get_run(RUN_ID)

    assert (
        store.transition_terminal(
            RUN_ID,
            status="completed",
            result={"status": "completed", "summary": "stale"},
            expected_statuses=("running",),
            expected_state_version=running["state_version"],
            expected_lease_token="lease-stale",
            expected_lease_generation=1,
        )
        is None
    )
    completed = store.transition_terminal(
        RUN_ID,
        status="completed",
        result={"status": "completed", "summary": "winner"},
        expected_statuses=("running",),
        expected_state_version=running["state_version"],
        expected_lease_token="lease-current",
        expected_lease_generation=1,
        summary="winner",
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"]["summary"] == "winner"

    assert (
        store.transition_terminal(
            RUN_ID,
            status="timed_out",
            result={"status": "timed_out", "summary": "loser"},
            expected_statuses=("running", "completed"),
            expected_state_version=completed["state_version"],
            expected_lease_token="lease-current",
            expected_lease_generation=1,
        )
        is None
    )
    preserved = store.get_run(RUN_ID)
    assert preserved["status"] == "completed"
    assert preserved["result"]["summary"] == "winner"


def test_completion_and_timeout_from_same_version_have_one_winner(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="running",
        worker_lease_token="lease-current",
    )
    observed = store.get_run(RUN_ID)
    completed = store.transition_terminal(
        RUN_ID,
        status="completed",
        result={"status": "completed"},
        expected_statuses=("running",),
        expected_state_version=observed["state_version"],
        expected_lease_token="lease-current",
        expected_lease_generation=1,
    )
    timed_out = store.transition_terminal(
        RUN_ID,
        status="timed_out",
        result={"status": "timed_out"},
        expected_statuses=("running",),
        expected_state_version=observed["state_version"],
        expected_lease_token="lease-current",
        expected_lease_generation=1,
    )

    assert completed is not None
    assert timed_out is None
    assert store.get_run(RUN_ID)["status"] == "completed"


def test_recovery_transition_loses_to_new_worker_heartbeat(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="running",
        worker_lease_token="lease-current",
    )
    observed = store.get_run(RUN_ID)
    assert store.heartbeat_worker(
        RUN_ID,
        lease_token="lease-current",
        lease_generation=1,
        elapsed_seconds=1.0,
        progress_updates={"worker_pid": 222},
    )

    recovered = store.mark_recovery_pending(
        RUN_ID,
        "stale recovery decision",
        expected_statuses=("running",),
        expected_state_version=observed["state_version"],
        expected_lease_token="lease-current",
        expected_lease_generation=1,
        expected_heartbeat_at=observed["heartbeat_at"],
    )

    assert recovered is None
    assert store.get_run(RUN_ID)["status"] == "running"


def test_stale_worker_heartbeat_is_rejected_after_lease_replacement(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / RUN_ID,
        input_data={},
        status="running",
        worker_lease_token="lease-old",
    )
    observed = store.get_run(RUN_ID)
    replacement = store.conditional_update(
        RUN_ID,
        fields={
            "status": "launch_pending",
            "current_phase": "launch_pending",
            "worker_lease_token": "lease-new",
            "lease_generation": 2,
            "worker_pid": None,
            "worker_identity": "",
        },
        expected_statuses=("running",),
        expected_state_version=observed["state_version"],
        expected_lease_token="lease-old",
        expected_lease_generation=1,
        reject_terminal=True,
    )
    assert replacement is not None

    assert (
        store.heartbeat_worker(
            RUN_ID,
            lease_token="lease-old",
            lease_generation=1,
            elapsed_seconds=5.0,
            progress_updates={"stale": True},
        )
        is False
    )
    current = store.get_run(RUN_ID)
    assert current["worker_lease_token"] == "lease-new"
    assert current["lease_generation"] == 2
    assert "stale" not in current["progress"]
