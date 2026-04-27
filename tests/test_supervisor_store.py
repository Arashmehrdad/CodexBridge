from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codexbridge.supervisor_store import (
    SupervisorStore,
    validate_lock_id,
    validate_supervisor_id,
)


SUPERVISOR_ID = "20260428T120000Z_supervisor_abcdef12"


def make_store(tmp_path: Path) -> SupervisorStore:
    return SupervisorStore(tmp_path / "runs")


def test_supervisor_store_initializes_schema_and_wal(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.db_path.exists()
    assert store.journal_mode() == "wal"
    with store.connect() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"supervisors", "supervisor_events", "supervisor_run_links", "repo_write_locks"}.issubset(tables)


def test_supervisor_create_get_list_update_survives_reload(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    created = store.create_supervisor(
        supervisor_id=SUPERVISOR_ID,
        repo_name="codexbridge",
        objective="coordinate a safe docs update",
        metadata={"batch": 1},
    )
    assert created["status"] == "queued"
    assert created["metadata"] == {"batch": 1}

    updated = store.update_supervisor(SUPERVISOR_ID, status="running", summary="started", requires_human=True)
    assert updated["status"] == "running"
    assert updated["requires_human"] is True

    reloaded = make_store(tmp_path)
    assert reloaded.get_supervisor(SUPERVISOR_ID)["summary"] == "started"
    assert reloaded.list_supervisors(repo_name="codexbridge", status="running")[0]["supervisor_id"] == SUPERVISOR_ID


def test_invalid_supervisor_and_lock_ids_rejected() -> None:
    with pytest.raises(ValueError):
        validate_supervisor_id("../bad")
    with pytest.raises(ValueError):
        validate_lock_id("bad-lock")


def test_supervisor_events_ordering_and_limit(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_supervisor(supervisor_id=SUPERVISOR_ID, repo_name="codexbridge", objective="test events")
    for index in range(4):
        store.append_event(SUPERVISOR_ID, level="info", stage="test", message=f"event {index}", data={"index": index})

    events = store.get_events(SUPERVISOR_ID, limit=2)
    assert [event["message"] for event in events] == ["event 2", "event 3"]
    assert events[0]["data"] == {"index": 2}


def test_supervisor_run_links_persist_after_reload(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.create_supervisor(supervisor_id=SUPERVISOR_ID, repo_name="codexbridge", objective="link runs")
    link = store.add_run_link(SUPERVISOR_ID, "20260428T120001Z_codex_plan_task_12345678", "plan")
    assert link["link_type"] == "plan"

    reloaded = make_store(tmp_path)
    links = reloaded.list_run_links(SUPERVISOR_ID)
    assert len(links) == 1
    assert links[0]["run_id"] == "20260428T120001Z_codex_plan_task_12345678"


def test_repo_lock_acquire_release_and_reacquire(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = store.acquire_repo_lock("codexbridge", owner_id=SUPERVISOR_ID, reason="test")
    assert first is not None
    assert first["repo_name"] == "codexbridge"

    second = store.acquire_repo_lock("codexbridge", owner_id=SUPERVISOR_ID)
    assert second is None

    assert store.release_repo_lock(first["lock_id"]) is True
    third = store.acquire_repo_lock("codexbridge", owner_id=SUPERVISOR_ID)
    assert third is not None
    assert third["lock_id"] != first["lock_id"]


def test_expired_repo_lock_can_be_replaced(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO repo_write_locks (lock_id, repo_name, owner_id, acquired_at, expires_at, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("lock_11111111", "codexbridge", SUPERVISOR_ID, expired, expired, "expired"),
        )

    replacement = store.acquire_repo_lock("codexbridge", owner_id=SUPERVISOR_ID, reason="replacement")
    assert replacement is not None
    assert replacement["lock_id"] != "lock_11111111"
    assert replacement["reason"] == "replacement"
