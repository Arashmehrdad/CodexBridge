from __future__ import annotations

from pathlib import Path

from soma.cf1_run_store_baseline import (
    CF1_RUN_STORE_BASELINE_VERSION,
    RUN_INTERNAL_ONLY_COLUMNS,
    RUN_JSON_BLOB_COLUMNS,
    RUN_SCALAR_SUMMARY_COLUMNS,
    RUN_STORE_INDEX_PROPOSALS,
)
from soma.run_store import RunStore


def _table_columns(store: RunStore) -> set[str]:
    with store.connect() as conn:
        return {str(row[1]) for row in conn.execute("PRAGMA table_info(runs)").fetchall()}


def _indexes(store: RunStore) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    with store.connect() as conn:
        for row in conn.execute("PRAGMA index_list(runs)").fetchall():
            name = str(row[1])
            columns = tuple(str(info[2]) for info in conn.execute(f"PRAGMA index_info('{name}')").fetchall())
            result[name] = columns
    return result


def test_cf1_run_store_baseline_partitions_every_persisted_run_column(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    actual = _table_columns(store)
    classified = set(RUN_SCALAR_SUMMARY_COLUMNS) | set(RUN_JSON_BLOB_COLUMNS) | set(RUN_INTERNAL_ONLY_COLUMNS)

    assert CF1_RUN_STORE_BASELINE_VERSION == "cf1.2.run-store.v3"
    assert classified == actual
    assert not (set(RUN_SCALAR_SUMMARY_COLUMNS) & set(RUN_JSON_BLOB_COLUMNS))
    assert not (set(RUN_SCALAR_SUMMARY_COLUMNS) & set(RUN_INTERNAL_ONLY_COLUMNS))
    assert not (set(RUN_JSON_BLOB_COLUMNS) & set(RUN_INTERNAL_ONLY_COLUMNS))


def test_cf1_compact_summary_baseline_excludes_json_and_sensitive_internal_fields() -> None:
    forbidden = set(RUN_JSON_BLOB_COLUMNS) | set(RUN_INTERNAL_ONLY_COLUMNS)

    assert forbidden.isdisjoint(RUN_SCALAR_SUMMARY_COLUMNS)
    assert {"input_json", "progress_json", "result_json", "worker_lease_token", "run_dir"} <= forbidden
    assert {
        "state_version",
        "current_phase",
        "heartbeat_at",
        "last_output_at",
        "cancellation_requested_at",
        "result_publication_status",
        "result_published_hash",
    } <= set(RUN_SCALAR_SUMMARY_COLUMNS)


def test_cf1_index_inventory_records_measured_index_decisions(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    actual = _indexes(store)
    proposals = {proposal.name: proposal for proposal in RUN_STORE_INDEX_PROPOSALS}

    assert actual["idx_runs_created_at"] == ("created_at",)
    assert actual["idx_runs_created_run_id_desc"] == ("created_at", "run_id")
    assert actual["idx_runs_repo_status"] == ("repo_name", "status")
    assert proposals["idx_runs_created_at"].status == "existing"
    assert proposals["idx_runs_repo_status"].status == "existing"
    assert proposals["idx_runs_created_run_id_desc"].status == "measurement_accepted"
    assert (
        proposals["idx_runs_repo_status_created_run_id_desc"].status
        == "measurement_rejected"
    )
    assert "idx_runs_repo_status_created_run_id_desc" not in actual
