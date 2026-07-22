from __future__ import annotations

from pathlib import Path

from soma.cf1_run_query_baseline import (
    CF1_RUN_QUERY_BASELINE_VERSION,
    CURRENT_RUN_QUERY_SPECS,
    inspect_current_run_queries,
)
from soma.cf1_run_store_baseline import (
    RUN_INTERNAL_ONLY_COLUMNS,
    RUN_JSON_BLOB_COLUMNS,
)
from soma.run_store import RunStore


def test_cf1_current_run_queries_record_column_and_plan_baseline(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    with store.connect() as conn:
        inspections = inspect_current_run_queries(conn)

    assert CF1_RUN_QUERY_BASELINE_VERSION == "cf1.0.run-query.v1"
    assert tuple(item.name for item in inspections) == tuple(
        spec.name for spec in CURRENT_RUN_QUERY_SPECS
    )
    assert all(item.selected_columns for item in inspections)
    assert all(item.query_plan for item in inspections)


def test_cf1_current_run_queries_prove_full_json_and_internal_selection(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    with store.connect() as conn:
        inspections = inspect_current_run_queries(conn)

    expected_json = set(RUN_JSON_BLOB_COLUMNS)
    expected_internal = set(RUN_INTERNAL_ONLY_COLUMNS)
    for item in inspections:
        assert item.selects_full_row is True
        assert set(item.selected_json_columns) == expected_json
        assert set(item.selected_internal_columns) == expected_internal


def test_cf1_query_plan_baseline_captures_current_index_behavior(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    with store.connect() as conn:
        inspections = {
            item.name: item for item in inspect_current_run_queries(conn)
        }

    unfiltered_plan = " | ".join(inspections["run_list_unfiltered"].query_plan)
    filtered_plan = " | ".join(inspections["run_list_repo_status"].query_plan)
    status_plan = " | ".join(inspections["run_status"].query_plan)
    latest_plan = " | ".join(inspections["latest_run"].query_plan)

    assert "idx_runs_created_at" in unfiltered_plan
    assert "sqlite_autoindex_runs_1" in status_plan
    assert "idx_runs_created_at" in filtered_plan or "idx_runs_repo_status" in filtered_plan
    assert "idx_runs_created_at" in latest_plan


def test_cf1_query_specs_remain_measurement_only_and_match_public_paths() -> None:
    public_paths = {spec.public_path for spec in CURRENT_RUN_QUERY_SPECS}

    assert public_paths == {
        "run_query(list)",
        "run_query(list, repo_name, status)",
        "run_query(status/control/result)",
        "latest result lookup",
    }
    assert all(spec.sql.startswith("SELECT * FROM runs") for spec in CURRENT_RUN_QUERY_SPECS)
