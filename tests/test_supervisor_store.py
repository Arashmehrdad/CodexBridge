from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from soma.supervisor_store import SupervisorStore, validate_supervisor_id


SUPERVISOR_ID = "20260428T120000Z_supervisor_abcdef12"


def make_store(tmp_path: Path) -> SupervisorStore:
    return SupervisorStore(tmp_path / "runs")


def test_supervisor_store_initializes_schema_and_wal(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.db_path.exists()
    assert store.journal_mode() == "wal"
    with store.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "supervisors",
        "supervisor_events",
        "supervisor_run_links",
        "operation_locks",
        "supervisor_notifications",
    }.issubset(tables)
    assert "repo_write_locks" not in tables


def test_supervisor_create_get_list_update_survives_reload(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    created = store.create_supervisor(
        supervisor_id=SUPERVISOR_ID,
        repo_name="soma",
        objective="coordinate a safe docs update",
        metadata={"batch": 1},
    )
    assert created["status"] == "queued"
    assert created["metadata"] == {"batch": 1}

    updated = store.update_supervisor(
        SUPERVISOR_ID, status="running", summary="started", requires_human=True
    )
    assert updated["status"] == "running"
    assert updated["requires_human"] is True

    reloaded = make_store(tmp_path)
    assert reloaded.get_supervisor(SUPERVISOR_ID)["summary"] == "started"
    assert (
        reloaded.list_supervisors(repo_name="soma", status="running")[0][
            "supervisor_id"
        ]
        == SUPERVISOR_ID
    )


def test_invalid_supervisor_id_rejected() -> None:
    with pytest.raises(ValueError):
        validate_supervisor_id("../bad")


def test_supervisor_conditional_update_rejects_stale_version(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    created = store.create_supervisor(
        supervisor_id=SUPERVISOR_ID,
        repo_name="soma",
        objective="conditional update",
    )
    assert created["state_version"] == 0

    updated = store.conditional_update_supervisor(
        SUPERVISOR_ID,
        fields={"status": "running", "summary": "claimed"},
        expected_statuses=("queued",),
        expected_state_version=0,
    )
    assert updated is not None
    assert updated["status"] == "running"
    assert updated["state_version"] == 1

    stale = store.conditional_update_supervisor(
        SUPERVISOR_ID,
        fields={"status": "failed"},
        expected_statuses=("running",),
        expected_state_version=0,
    )
    assert stale is None
    assert store.get_supervisor(SUPERVISOR_ID)["status"] == "running"


def test_attach_child_is_atomic_and_version_guarded(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    created = store.create_supervisor(
        supervisor_id=SUPERVISOR_ID,
        repo_name="soma",
        objective="attach child",
        metadata={"active_child": None},
    )
    run_id = "20260428T120001Z_codex_plan_task_12345678"

    attached = store.attach_child(
        SUPERVISOR_ID,
        run_id=run_id,
        link_type="plan",
        child_kind="plan",
        target_status="planning",
        metadata=created["metadata"],
        expected_statuses=("queued",),
        expected_state_version=0,
        started_at="2026-04-28T12:00:00+00:00",
    )
    assert attached is not None
    assert attached["state_version"] == 1
    assert attached["metadata"]["active_child"] == {
        "run_id": run_id,
        "kind": "plan",
        "launch_state": "reserved",
    }
    assert [link["run_id"] for link in store.list_run_links(SUPERVISOR_ID)] == [
        run_id
    ]

    stale = store.attach_child(
        SUPERVISOR_ID,
        run_id="20260428T120002Z_codex_plan_task_87654321",
        link_type="plan",
        child_kind="plan",
        target_status="planning",
        metadata=created["metadata"],
        expected_statuses=("queued", "planning"),
        expected_state_version=0,
    )
    assert stale is None
    assert len(store.list_run_links(SUPERVISOR_ID)) == 1


def test_supervisor_events_ordering_and_limit(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_supervisor(
        supervisor_id=SUPERVISOR_ID, repo_name="soma", objective="test events"
    )
    for index in range(4):
        store.append_event(
            SUPERVISOR_ID,
            level="info",
            stage="test",
            message=f"event {index}",
            data={"index": index},
        )

    events = store.get_events(SUPERVISOR_ID, limit=2)
    assert [event["message"] for event in events] == ["event 2", "event 3"]
    assert events[0]["data"] == {"index": 2}


def test_supervisor_run_links_persist_after_reload(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_supervisor(
        supervisor_id=SUPERVISOR_ID, repo_name="soma", objective="link runs"
    )
    link = store.add_run_link(
        SUPERVISOR_ID, "20260428T120001Z_codex_plan_task_12345678", "plan"
    )
    assert link["link_type"] == "plan"

    reloaded = make_store(tmp_path)
    links = reloaded.list_run_links(SUPERVISOR_ID)
    assert len(links) == 1
    assert links[0]["run_id"] == "20260428T120001Z_codex_plan_task_12345678"


def test_supervisor_store_removes_legacy_repo_write_lock_schema(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    db_path = runs_dir / "soma.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE repo_write_locks (
                lock_id TEXT PRIMARY KEY,
                repo_name TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT,
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX idx_repo_write_locks_repo ON repo_write_locks(repo_name)"
        )

    store = SupervisorStore(runs_dir)
    with store.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert "operation_locks" in tables
    assert "repo_write_locks" not in tables
    assert "idx_repo_write_locks_repo" not in indexes


def test_supervisor_notifications_crud_dedupe_and_delivery_update(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    store.create_supervisor(
        supervisor_id=SUPERVISOR_ID, repo_name="soma", objective="notify"
    )
    notification = store.create_notification(
        SUPERVISOR_ID,
        event_stage="completed",
        event_level="info",
        kind="completed",
        title="Done",
        message="API_KEY=abc123",
        payload={"token": "token: secret-value", "summary": "ok"},
        dedupe_key="completed",
    )
    duplicate = store.create_notification(
        SUPERVISOR_ID,
        event_stage="completed",
        event_level="info",
        kind="completed",
        title="Duplicate",
        message="Duplicate",
        payload={},
        dedupe_key="completed",
    )
    assert duplicate["id"] == notification["id"]
    assert "abc123" not in notification["message"]
    assert "secret-value" not in str(notification["payload"])
    assert store.get_notification(notification["id"])["kind"] == "completed"
    assert store.list_notifications(SUPERVISOR_ID)[0]["dedupe_key"] == "completed"

    delivered = store.update_notification_delivery(
        notification["id"], delivery_status="delivered"
    )
    assert delivered["delivery_status"] == "delivered"
    assert delivered["delivery_attempts"] == 1
