from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

import codexbridge.job_manager as job_manager_module
import codexbridge.server as server
from codexbridge.gateway_models import RunQueryRequest
from codexbridge.job_manager import JobManager
from codexbridge.public_projection_contract import DEFAULT_PUBLIC_BYTE_BUDGETS
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


def test_progress_scalar_mirrors_and_backfill_preserve_control_fields(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    store.update_run(
        run_id,
        progress_json={
            "last_output_at": "2026-07-21T11:58:00+00:00",
            "cancellation_requested_at": "2026-07-21T11:59:00+00:00",
        },
    )
    snapshot = store.get_run_control_snapshot(run_id, now=NOW)
    assert snapshot["last_output_at"] == "2026-07-21T11:58:00+00:00"
    assert snapshot["cancellation_requested_at"] == "2026-07-21T11:59:00+00:00"

    with store.connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET last_output_at = '', cancellation_requested_at = '', progress_json = ?
            WHERE run_id = ?
            """,
            (
                json.dumps(
                    {
                        "last_output_at": "2026-07-21T11:56:00+00:00",
                        "cancellation_requested_at": "2026-07-21T11:57:00+00:00",
                    }
                ),
                run_id,
            ),
        )
        store._backfill_progress_scalar_columns(conn)
    backfilled = store.get_run_control_snapshot(run_id, now=NOW)
    assert backfilled["last_output_at"] == "2026-07-21T11:56:00+00:00"
    assert backfilled["cancellation_requested_at"] == "2026-07-21T11:57:00+00:00"


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


def test_compact_query_plan_uses_measurement_justified_ordering_index(
    tmp_path: Path,
) -> None:
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
        indexes = {
            str(row[1])
            for row in conn.execute("PRAGMA index_list(runs)").fetchall()
        }
    plan = " ".join(str(row[3]) for row in unfiltered)
    assert "idx_runs_created_run_id_desc" in indexes
    assert "idx_runs_created_run_id_desc" in plan
    assert "TEMP B-TREE" not in plan
    assert "idx_runs_repo_status_created_run_id_desc" not in indexes


def _payload_bytes_without_counter(payload: dict) -> int:
    without_counter = dict(payload)
    without_counter.pop("payload_bytes")
    return len(
        json.dumps(
            without_counter,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _wire_bytes(payload: dict) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _manager(store: RunStore, lock: dict | None = None) -> JobManager:
    manager = object.__new__(JobManager)
    manager.store = store
    manager.locks = SimpleNamespace(
        find_lock=lambda _repo_name, _run_id: dict(lock or {})
    )
    return manager


def test_public_run_summary_is_redacted_versioned_and_byte_bounded(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    store.update_run(
        run_id,
        summary="token=secret-value " + ("🙂" * 5000),
        error="password=hunter2 " + ("é" * 5000),
        recovery_reason="api_key=hidden " + ("r" * 3000),
        result_publication_error="credential=private " + ("p" * 3000),
    )

    response = _manager(store).get_run_summary(run_id)

    assert response["ok"] is True
    assert response["operation"] == "summary"
    assert response["view"] == "summary"
    assert response["projection_version"] == "cf1.v1"
    assert response["non_authoritative"] is True
    assert response["authoritative_operation"] == "status"
    assert response["payload_bytes"] == _payload_bytes_without_counter(response)
    assert _wire_bytes(response) <= DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary
    assert not FORBIDDEN.intersection(response["run"])
    assert not {"pid", "launcher_pid", "worker_pid", "lease_generation"}.intersection(
        response["run"]
    )
    encoded = json.dumps(response, ensure_ascii=False)
    assert "secret-value" not in encoded
    assert "hunter2" not in encoded
    assert "hidden" not in encoded
    assert "private" not in encoded
    assert response["run"]["truncated_fields"]
    encoded.encode("utf-8")


def test_public_run_control_is_scalar_bounded_and_version_pollable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = _create(store, tmp_path, 1, status="running")
    store.update_run(
        run_id,
        pid=987,
        launcher_pid=654,
        worker_pid=321,
        worker_identity="321:windows:secret-identity",
        progress_json={
            "last_output_at": "2026-07-21T11:58:00+00:00",
            "cancellation_requested_at": "2026-07-21T11:59:00+00:00",
        },
        summary="token=secret-value " + ("s" * 10000),
        error="password=hunter2 " + ("e" * 10000),
        recovery_reason="credential=hidden " + ("r" * 5000),
        result_publication_error="api_key=private " + ("p" * 5000),
    )
    lock = {"repo_name": "Sample", "run_id": run_id, "owner_pid": 321}
    manager = _manager(store, lock)
    monkeypatch.setattr(
        job_manager_module, "process_is_running", lambda pid: pid in {654, 987}
    )
    monkeypatch.setattr(
        job_manager_module,
        "process_matches_identity",
        lambda pid, identity: pid == 321 and identity == "321:windows:secret-identity",
    )

    changed = manager.get_control_status(run_id)
    assert changed["ok"] is True
    assert changed["operation"] == "control"
    assert changed["unchanged"] is False
    assert changed["view"] == "standard"
    assert changed["authoritative_operation"] == "status"
    assert changed["launcher_running"] is True
    assert changed["worker_running"] is True
    assert changed["child_running"] is True
    assert changed["last_output_at"] == "2026-07-21T11:58:00+00:00"
    assert changed["cancellation_requested_at"] == "2026-07-21T11:59:00+00:00"
    assert changed["lock"]["run_id"] == run_id
    assert changed["payload_bytes"] == _payload_bytes_without_counter(changed)
    assert _wire_bytes(changed) <= DEFAULT_PUBLIC_BYTE_BUDGETS.run_control
    encoded = json.dumps(changed, ensure_ascii=False)
    for secret in ("secret-value", "hunter2", "hidden", "private", "secret-identity"):
        assert secret not in encoded
    assert not FORBIDDEN.intersection(changed)

    def unexpected_probe(*_args, **_kwargs):
        pytest.fail("unchanged control poll performed a process or lock probe")

    manager.locks = SimpleNamespace(find_lock=unexpected_probe)
    monkeypatch.setattr(job_manager_module, "process_is_running", unexpected_probe)
    monkeypatch.setattr(job_manager_module, "process_matches_identity", unexpected_probe)
    unchanged_first = manager.get_control_status(
        run_id, if_state_version=changed["state_version"]
    )
    unchanged_second = manager.get_control_status(
        run_id, if_state_version=changed["state_version"]
    )
    assert unchanged_first == unchanged_second
    assert unchanged_first["unchanged"] is True
    assert unchanged_first["state_version"] == changed["state_version"]
    assert unchanged_first["payload_bytes"] == _payload_bytes_without_counter(
        unchanged_first
    )
    assert _wire_bytes(unchanged_first) <= DEFAULT_PUBLIC_BYTE_BUDGETS.unchanged_poll

    store.set_progress(run_id, phase="validate", elapsed_seconds=1.0)
    manager.locks = SimpleNamespace(
        find_lock=lambda _repo_name, _run_id: dict(lock)
    )
    monkeypatch.setattr(job_manager_module, "process_is_running", lambda _pid: False)
    monkeypatch.setattr(
        job_manager_module, "process_matches_identity", lambda _pid, _identity: False
    )
    refreshed = manager.get_control_status(
        run_id, if_state_version=changed["state_version"]
    )
    assert refreshed["unchanged"] is False
    assert refreshed["state_version"] > changed["state_version"]


def test_public_run_summary_list_preserves_snapshot_cursor_when_byte_limited(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    expected: set[str] = set()
    for index in range(18):
        run_id = _create(store, tmp_path, index)
        expected.add(run_id)
        store.update_run(
            run_id,
            summary="token=secret-value " + ("🙂" * 1000),
            error="password=hunter2 " + ("e" * 1000),
            recovery_reason="api_key=hidden " + ("r" * 1000),
            result_publication_error="credential=private " + ("p" * 1000),
        )

    manager = _manager(store)
    seen: list[str] = []
    cursor: str | None = None
    byte_limited = False
    while True:
        response = manager.list_run_summaries(limit=10, cursor=cursor)
        assert response["payload_bytes"] == _payload_bytes_without_counter(response)
        assert _wire_bytes(response) <= DEFAULT_PUBLIC_BYTE_BUDGETS.run_list
        assert response["requested_limit"] == 10
        assert 0 <= response["returned_count"] <= 10
        assert "snapshot_watermark" not in response
        assert all(not FORBIDDEN.intersection(run) for run in response["runs"])
        seen.extend(run["run_id"] for run in response["runs"])
        byte_limited = byte_limited or response["byte_limited"]
        if not response["has_more"]:
            break
        cursor = response["next_cursor"]
        assert cursor

    assert byte_limited is True
    assert set(seen) == expected
    assert len(seen) == len(expected)


def test_byte_limited_summary_list_projects_each_source_row_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = RunStore(tmp_path / "runs")
    for index in range(20):
        run_id = _create(store, tmp_path, index)
        store.update_run(
            run_id,
            summary="token=[REDACTED] " + ("🙂" * 1000),
            error="password=[REDACTED] " + ("e" * 1000),
        )

    original = job_manager_module._project_run_summary
    projection_calls = 0

    def counted_projection(*args, **kwargs):
        nonlocal projection_calls
        projection_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(job_manager_module, "_project_run_summary", counted_projection)
    response = _manager(store).list_run_summaries(limit=20)

    assert response["byte_limited"] is True
    assert response["returned_count"] < 20
    assert projection_calls == 20


def test_run_summary_gateway_models_are_additive_and_strict(monkeypatch) -> None:
    calls: list[tuple] = []

    class FakeJobs:
        def get_run_summary(self, run_id: str) -> dict:
            calls.append(("summary", run_id))
            return {"ok": True, "operation": "summary", "run_id": run_id}

        def get_control_status(
            self, run_id: str, if_state_version: int | None = None
        ) -> dict:
            calls.append(("control", run_id, if_state_version))
            return {"ok": True, "operation": "control", "run_id": run_id}

        def list_run_summaries(self, **kwargs) -> dict:
            calls.append(("summary_list", kwargs))
            return {"ok": True, "operation": "summary_list", "runs": []}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    adapter = TypeAdapter(RunQueryRequest)
    summary = adapter.validate_python({"operation": "summary", "run_id": "run_1"})
    control = adapter.validate_python(
        {"operation": "control", "run_id": "run_1", "if_state_version": 7}
    )
    summary_list = adapter.validate_python({"operation": "summary_list"})

    assert server.run_query(summary)["operation"] == "summary"
    assert server.run_query(control)["operation"] == "control"
    assert server.run_query(summary_list)["operation"] == "summary_list"
    assert summary_list.limit == 10
    assert calls[0] == ("summary", "run_1")
    assert calls[1] == ("control", "run_1", 7)
    assert calls[2][0] == "summary_list"
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"operation": "summary", "run_id": "run_1", "cursor": "not-allowed"}
        )
    with pytest.raises(ValidationError):
        adapter.validate_python({"operation": "summary_list", "limit": 101})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"operation": "control", "run_id": "run_1", "if_state_version": -1}
        )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"operation": "control", "run_id": "run_1", "cursor": "not-allowed"}
        )
