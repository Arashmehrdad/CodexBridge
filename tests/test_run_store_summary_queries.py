from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codexbridge.run_store import (
    RUN_CONTROL_PROJECTION_COLUMNS,
    RUN_SUMMARY_ORDERING,
    RUN_SUMMARY_PROJECTION_COLUMNS,
    RunStore,
)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
FORBIDDEN = {
    "input_json",
    "progress_json",
    "result_json",
    "worker_lease_token",
    "run_dir",
}


def _run_id(index: int) -> str:
    return f"20260721T1200{index:02d}Z_project_command_{index:08x}"


def _create(
    store: RunStore,
    tmp_path: Path,
    index: int,
    *,
    created_at: str | None = None,
    status: str = "queued",
) -> str:
    run_id = _run_id(index)
    store.create_run(
        run_id=run_id,
        repo_name="Sample",
        tool="project_command",
        run_dir=tmp_path / "runs" / run_id,
        input_data={"index": index},
        status=status,
    )
    if created_at is not None:
        store.update_run(run_id, created_at=created_at)
    return run_id


def test_compact_keys_exclude_blobs_and_internal_values(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    with store.connect() as conn:
        conn.execute(
            "UPDATE runs SET input_json = ?, progress_json = ?, result_json = ?, "
            "worker_lease_token = ?, run_dir = ?, worker_identity = ? WHERE run_id = ?",
            ("{", "{", "{", "secret-lease", "C:/private", "pid-secret", run_id),
        )

    summary = store.get_run_summary(run_id, now=NOW)
    control = store.get_run_control_snapshot(run_id, now=NOW)

    assert set(summary) == set(RUN_SUMMARY_PROJECTION_COLUMNS) | {
        "heartbeat_age_seconds",
        "worker_stale",
    }
    assert set(control) == (
        set(RUN_CONTROL_PROJECTION_COLUMNS) - {"worker_identity"}
    ) | {"worker_identity_present", "heartbeat_age_seconds", "worker_stale"}
    assert not FORBIDDEN.intersection(summary)
    assert not FORBIDDEN.intersection(control)
    assert "worker_identity" not in control
    assert control["worker_identity_present"] is True
    assert control["worker_pid"] is None


def test_compact_sql_is_explicit_and_never_decodes_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    with store.connect() as conn:
        conn.execute(
            "UPDATE runs SET input_json = ?, progress_json = ?, result_json = ? WHERE run_id = ?",
            ("{", "{", "{" * 10000, run_id),
        )

    captured: list[str] = []
    original_connect = store.connect

    class TracedConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.connection = connection

        def __enter__(self) -> "TracedConnection":
            self.connection.__enter__()
            return self

        def __exit__(self, *args: object) -> None:
            self.connection.__exit__(*args)

        def execute(self, sql: str, parameters: object = ()) -> sqlite3.Cursor:
            captured.append(sql)
            return self.connection.execute(sql, parameters)

    monkeypatch.setattr(
        store, "connect", lambda: TracedConnection(original_connect())
    )
    monkeypatch.setattr("codexbridge.run_store.loads", lambda value: pytest.fail("loads called"))

    store.get_run_summary(run_id, now=NOW)
    store.get_run_control_snapshot(run_id, now=NOW)
    store.list_run_summaries(now=NOW)

    compact_sql = " ".join(captured).lower()
    assert "select *" not in compact_sql
    assert not any(column in compact_sql for column in FORBIDDEN)
    assert any(sql.lower().startswith("select run_id") for sql in captured)


def test_scalar_derivation_is_deterministic_and_rejects_naive_now(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    store.update_run(
        run_id,
        started_at=(NOW - timedelta(seconds=12.25)).isoformat(),
        heartbeat_at=(NOW - timedelta(seconds=45.5)).isoformat(),
        elapsed_seconds=0.0,
    )

    first = store.get_run_summary(run_id, now=NOW)
    second = store.get_run_control_snapshot(run_id, now=NOW)
    assert first["elapsed_seconds"] == 12.25
    assert first["heartbeat_age_seconds"] == 45.5
    assert first["worker_stale"] is True
    assert second["elapsed_seconds"] == 12.25
    assert second["heartbeat_age_seconds"] == 45.5
    assert second["worker_stale"] is True
    with pytest.raises(ValueError, match="timezone-aware"):
        store.get_run_summary(run_id, now=datetime(2026, 7, 21, 12, 0))


def test_scalar_derivation_never_decreases_persisted_elapsed(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    store.update_run(
        run_id,
        started_at=(NOW - timedelta(seconds=5)).isoformat(),
        elapsed_seconds=12.5,
    )

    assert store.get_run_summary(run_id, now=NOW)["elapsed_seconds"] == 12.5
    assert store.get_run_control_snapshot(run_id, now=NOW)["elapsed_seconds"] == 12.5


def test_summary_ordering_limits_and_watermarked_keyset_pages(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    created = "2026-07-21T11:00:00+00:00"
    ids = [_create(store, tmp_path, index, created_at=created) for index in range(25)]
    expected = sorted(ids, reverse=True)

    first = store.list_run_summaries(now=NOW)
    assert first["limit"] == 10
    assert first["ordering"] == RUN_SUMMARY_ORDERING
    assert first["has_more"] is True
    assert [item["run_id"] for item in first["runs"]] == expected[:10]
    assert first["snapshot_watermark"] > 0

    all_ids = [item["run_id"] for item in first["runs"]]
    page = first
    while page["has_more"]:
        page = store.list_run_summaries(cursor=page["next_cursor"], now=NOW)
        all_ids.extend(item["run_id"] for item in page["runs"])
    assert all_ids == expected
    assert len(all_ids) == len(set(all_ids))

    maximum = store.list_run_summaries(limit=100, now=NOW)
    assert maximum["limit"] == 100
    assert len(maximum["runs"]) == 25
    clamped = store.list_run_summaries(limit=1000, now=NOW)
    assert clamped["limit"] == 100


def test_backdated_insert_is_excluded_and_scalar_state_refreshes_between_pages(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    ids = [_create(store, tmp_path, index) for index in range(4)]
    for index, run_id in enumerate(ids):
        store.update_run(run_id, created_at=f"2026-07-21T10:0{index}:00+00:00")

    first = store.list_run_summaries(limit=2, now=NOW)
    third_id = ids[1]
    store.update_run(third_id, status="running", summary="refreshed")
    _create(store, tmp_path, 50, created_at="2020-01-01T00:00:00+00:00")

    second = store.list_run_summaries(
        cursor=first["next_cursor"], limit=2, now=NOW + timedelta(seconds=1)
    )
    observed = [item["run_id"] for item in first["runs"] + second["runs"]]
    assert observed == [ids[3], ids[2], ids[1], ids[0]]
    assert len(observed) == len(set(observed))
    assert second["runs"][0]["run_id"] == ids[1]
    assert second["runs"][0]["status"] == "running"
    assert second["runs"][0]["summary"] == "refreshed"


def test_cursor_validation_errors_are_deterministic(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    for index in range(3):
        _create(store, tmp_path, index)
    first = store.list_run_summaries(limit=1, now=NOW)
    cursor = first["next_cursor"]
    assert cursor

    with pytest.raises(ValueError, match="checksum mismatch"):
        store.list_run_summaries(cursor=cursor[:-1] + ("0" if cursor[-1] != "0" else "1"), now=NOW)
    body, checksum = cursor.split(".")
    with pytest.raises(ValueError, match="Invalid run summary cursor"):
        store.list_run_summaries(cursor=f"{body}=.{checksum}", now=NOW)
    with pytest.raises(ValueError, match="expired"):
        store.list_run_summaries(cursor=cursor, now=NOW + timedelta(seconds=301))
    with pytest.raises(ValueError, match="filter mismatch"):
        store.list_run_summaries(cursor=cursor, repo_name="other", now=NOW)
    with pytest.raises(ValueError, match="byte budget mismatch"):
        store.list_run_summaries(cursor=cursor, byte_budget=1024, now=NOW)


def test_control_snapshot_exposes_process_and_publication_state_without_identity_or_lease(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    store.update_run(
        run_id,
        pid=987,
        launcher_pid=654,
        worker_pid=321,
        worker_identity="secret-worker-identity",
        worker_lease_token="secret-lease",
        result_publication_status="failed",
        result_published_hash="hash",
        result_publication_error="publication failed",
        error="run failed",
    )
    snapshot = store.get_run_control_snapshot(run_id, now=NOW)
    assert snapshot["pid"] == 987
    assert snapshot["launcher_pid"] == 654
    assert snapshot["worker_pid"] == 321
    assert snapshot["worker_identity_present"] is True
    assert snapshot["result_publication_status"] == "failed"
    assert snapshot["result_publication_error"] == "publication failed"
    assert snapshot["error"] == "run failed"
    assert "secret-worker-identity" not in json.dumps(snapshot)
    assert "secret-lease" not in json.dumps(snapshot)


def test_legacy_full_methods_still_decode_full_rows(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1)
    store.update_run(
        run_id,
        input_json={"secret": "input"},
        progress_json={"percent": 25},
        result_json={"answer": "complete"},
    )
    full = store.get_run(run_id)
    assert full["input"] == {"secret": "input"}
    assert full["progress"] == {"percent": 25}
    assert full["result"] == {"answer": "complete"}
    assert store.list_runs(limit=1)[0]["result"] == {"answer": "complete"}
    assert store.latest_run()["input"] == {"secret": "input"}


def test_compact_query_plans_are_measured_without_new_indexes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    for index in range(12):
        _create(store, tmp_path, index)
    with store.connect() as conn:
        unfiltered = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT run_id, repo_name, tool, status, created_at "
            "FROM runs WHERE rowid <= ? ORDER BY created_at DESC, run_id DESC LIMIT ?",
            (999999, 11),
        ).fetchall()
        filtered = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT run_id, repo_name, tool, status, created_at "
            "FROM runs WHERE rowid <= ? AND lower(repo_name) = ? AND status = ? "
            "ORDER BY created_at DESC, run_id DESC LIMIT ?",
            (999999, "sample", "queued", 11),
        ).fetchall()
        indexes = {
            str(row[1])
            for row in conn.execute("PRAGMA index_list(runs)").fetchall()
        }
    assert unfiltered
    assert filtered
    assert all(str(row[3]) for row in unfiltered)
    assert all(str(row[3]) for row in filtered)
    assert "idx_runs_created_run_id_desc" not in indexes
    assert "idx_runs_repo_status_created_run_id_desc" not in indexes
