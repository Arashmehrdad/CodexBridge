from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final

from codexbridge.cf1_run_store_baseline import (
    RUN_INTERNAL_ONLY_COLUMNS,
    RUN_JSON_BLOB_COLUMNS,
)


CF1_RUN_QUERY_BASELINE_VERSION: Final[str] = "cf1.0.run-query.v1"


@dataclass(frozen=True)
class RunQuerySpec:
    name: str
    sql: str
    parameters: tuple[object, ...]
    public_path: str


@dataclass(frozen=True)
class RunQueryInspection:
    name: str
    selected_columns: tuple[str, ...]
    selected_json_columns: tuple[str, ...]
    selected_internal_columns: tuple[str, ...]
    query_plan: tuple[str, ...]

    @property
    def selects_full_row(self) -> bool:
        return bool(self.selected_json_columns or self.selected_internal_columns)


CURRENT_RUN_QUERY_SPECS: Final[tuple[RunQuerySpec, ...]] = (
    RunQuerySpec(
        name="run_list_unfiltered",
        sql="SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
        parameters=(20,),
        public_path="run_query(list)",
    ),
    RunQuerySpec(
        name="run_list_repo_status",
        sql=(
            "SELECT * FROM runs WHERE lower(repo_name) = lower(?) AND status = ? "
            "ORDER BY created_at DESC LIMIT ?"
        ),
        parameters=("codexbridge", "completed", 20),
        public_path="run_query(list, repo_name, status)",
    ),
    RunQuerySpec(
        name="run_status",
        sql="SELECT * FROM runs WHERE run_id = ?",
        parameters=("20260720T000000Z_baseline_00000000",),
        public_path="run_query(status/control/result)",
    ),
    RunQuerySpec(
        name="latest_run",
        sql="SELECT * FROM runs WHERE lower(repo_name) = lower(?) ORDER BY created_at DESC LIMIT 1",
        parameters=("codexbridge",),
        public_path="latest result lookup",
    ),
)


def inspect_run_query(
    conn: sqlite3.Connection,
    spec: RunQuerySpec,
) -> RunQueryInspection:
    cursor = conn.execute(spec.sql, spec.parameters)
    selected_columns = tuple(str(item[0]) for item in (cursor.description or ()))
    plan_rows = conn.execute(
        f"EXPLAIN QUERY PLAN {spec.sql}",
        spec.parameters,
    ).fetchall()
    plan = tuple(str(row[3]) for row in plan_rows)
    json_columns = tuple(
        column for column in selected_columns if column in RUN_JSON_BLOB_COLUMNS
    )
    internal_columns = tuple(
        column for column in selected_columns if column in RUN_INTERNAL_ONLY_COLUMNS
    )
    return RunQueryInspection(
        name=spec.name,
        selected_columns=selected_columns,
        selected_json_columns=json_columns,
        selected_internal_columns=internal_columns,
        query_plan=plan,
    )


def inspect_current_run_queries(
    conn: sqlite3.Connection,
) -> tuple[RunQueryInspection, ...]:
    return tuple(inspect_run_query(conn, spec) for spec in CURRENT_RUN_QUERY_SPECS)
