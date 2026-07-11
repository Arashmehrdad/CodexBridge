from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from codexbridge.run_store import utc_now

from .models import (
    WorkflowEvent,
    WorkflowRecord,
    WorkflowStatus,
    WorkflowStepRecord,
    WorkflowStepStatus,
)


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class WorkflowStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "codexbridge.sqlite3"
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    terminal_status TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    worker_pid INTEGER,
                    heartbeat_at TEXT,
                    active_child_run_id TEXT,
                    failure_summary TEXT NOT NULL DEFAULT '',
                    recommended_next_action TEXT NOT NULL DEFAULT '',
                    artifact_paths_json TEXT NOT NULL DEFAULT '[]',
                    result_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    workflow_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    step_type TEXT NOT NULL,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    depends_on_json TEXT NOT NULL DEFAULT '[]',
                    on_failure TEXT NOT NULL,
                    status TEXT NOT NULL,
                    child_run_id TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    artifact_paths_json TEXT NOT NULL DEFAULT '[]',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (workflow_id, step_id),
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status, updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_events ON workflow_events(workflow_id, id)"
            )

    def create_workflow(
        self,
        *,
        workflow_id: str,
        repo_name: str,
        objective: str,
        steps: list[dict[str, Any]],
        status: WorkflowStatus = WorkflowStatus.QUEUED,
    ) -> WorkflowRecord:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO workflows (
                    workflow_id, repo_name, objective, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (workflow_id, repo_name, objective, status.value, now, now),
            )
            conn.executemany(
                """
                INSERT INTO workflow_steps (
                    workflow_id, step_id, order_index, step_type, parameters_json,
                    depends_on_json, on_failure, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        workflow_id,
                        step["id"],
                        int(step["order_index"]),
                        step["type"],
                        _dumps(step["parameters"]),
                        _dumps(step["depends_on"]),
                        step["on_failure"],
                        WorkflowStepStatus.PENDING.value,
                    )
                    for step in steps
                ],
            )
        return self.get_workflow(workflow_id)

    def get_workflow(self, workflow_id: str) -> WorkflowRecord:
        with self.connect() as conn:
            workflow_row = conn.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
            ).fetchone()
            if workflow_row is None:
                raise KeyError(f"Workflow not found: {workflow_id}")
            step_rows = conn.execute(
                """
                SELECT * FROM workflow_steps
                WHERE workflow_id = ?
                ORDER BY order_index ASC
                """,
                (workflow_id,),
            ).fetchall()
        return self._hydrate_workflow(workflow_row, step_rows)

    def update_workflow(self, workflow_id: str, **fields: Any) -> WorkflowRecord:
        if not fields:
            return self.get_workflow(workflow_id)
        normalized = dict(fields)
        normalized["updated_at"] = utc_now()
        for json_field in ("artifact_paths_json", "result_json"):
            if json_field in normalized and not isinstance(normalized[json_field], str):
                normalized[json_field] = _dumps(normalized[json_field])
        for enum_field in ("status", "terminal_status"):
            if enum_field in normalized and isinstance(normalized[enum_field], WorkflowStatus):
                normalized[enum_field] = normalized[enum_field].value
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = [*normalized.values(), workflow_id]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE workflows SET {assignments} WHERE workflow_id = ?", params
            )
        return self.get_workflow(workflow_id)

    def update_step(
        self, workflow_id: str, step_id: str, **fields: Any
    ) -> WorkflowRecord:
        normalized = dict(fields)
        for json_field in ("parameters_json", "depends_on_json", "artifact_paths_json", "result_json"):
            if json_field in normalized and not isinstance(normalized[json_field], str):
                normalized[json_field] = _dumps(normalized[json_field])
        if "status" in normalized and isinstance(
            normalized["status"], WorkflowStepStatus
        ):
            normalized["status"] = normalized["status"].value
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = [*normalized.values(), workflow_id, step_id]
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE workflow_steps SET {assignments}
                WHERE workflow_id = ? AND step_id = ?
                """,
                params,
            )
        self.update_workflow(workflow_id)
        return self.get_workflow(workflow_id)

    def append_event(
        self,
        workflow_id: str,
        *,
        level: str,
        stage: str,
        message: str,
        data: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            timestamp=timestamp or utc_now(),
            workflow_id=workflow_id,
            level=level,  # type: ignore[arg-type]
            stage=stage,
            message=message,
            data=data or {},
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO workflow_events (
                    workflow_id, timestamp, level, stage, message, data_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    event.timestamp,
                    event.level,
                    event.stage,
                    event.message,
                    _dumps(event.data),
                ),
            )
            conn.execute(
                """
                UPDATE workflows
                SET heartbeat_at = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (event.timestamp, event.timestamp, workflow_id),
            )
        return event

    def get_events(self, workflow_id: str, limit: int = 100) -> list[WorkflowEvent]:
        bounded_limit = max(1, min(int(limit), 500))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM workflow_events
                    WHERE workflow_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (workflow_id, bounded_limit),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def iter_recoverable_workflows(self) -> list[WorkflowRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM workflows
                WHERE status IN (?, ?)
                ORDER BY created_at ASC
                """,
                (WorkflowStatus.QUEUED.value, WorkflowStatus.RUNNING.value),
            ).fetchall()
            step_rows = conn.execute(
                """
                SELECT * FROM workflow_steps
                WHERE workflow_id IN (
                    SELECT workflow_id FROM workflows
                    WHERE status IN (?, ?)
                )
                ORDER BY workflow_id ASC, order_index ASC
                """,
                (WorkflowStatus.QUEUED.value, WorkflowStatus.RUNNING.value),
            ).fetchall()
        steps_by_workflow: dict[str, list[sqlite3.Row]] = {}
        for row in step_rows:
            steps_by_workflow.setdefault(str(row["workflow_id"]), []).append(row)
        return [
            self._hydrate_workflow(row, steps_by_workflow.get(str(row["workflow_id"]), []))
            for row in rows
        ]

    def _hydrate_workflow(
        self, workflow_row: sqlite3.Row, step_rows: list[sqlite3.Row]
    ) -> WorkflowRecord:
        return WorkflowRecord(
            workflow_id=str(workflow_row["workflow_id"]),
            repo_name=str(workflow_row["repo_name"]),
            objective=str(workflow_row["objective"]),
            status=WorkflowStatus(str(workflow_row["status"])),
            terminal_status=WorkflowStatus(str(workflow_row["terminal_status"]))
            if workflow_row["terminal_status"]
            else None,
            created_at=str(workflow_row["created_at"]),
            updated_at=str(workflow_row["updated_at"]),
            started_at=str(workflow_row["started_at"])
            if workflow_row["started_at"]
            else None,
            ended_at=str(workflow_row["ended_at"]) if workflow_row["ended_at"] else None,
            worker_pid=int(workflow_row["worker_pid"]) if workflow_row["worker_pid"] else None,
            heartbeat_at=str(workflow_row["heartbeat_at"])
            if workflow_row["heartbeat_at"]
            else None,
            active_child_run_id=str(workflow_row["active_child_run_id"])
            if workflow_row["active_child_run_id"]
            else None,
            failure_summary=str(workflow_row["failure_summary"] or ""),
            recommended_next_action=str(
                workflow_row["recommended_next_action"] or ""
            ),
            artifact_paths=[
                Path(path)
                for path in _loads(workflow_row["artifact_paths_json"], default=[])
            ],
            result=_loads(workflow_row["result_json"], default={}),
            steps=[self._row_to_step(row) for row in step_rows],
        )

    def _row_to_step(self, row: sqlite3.Row) -> WorkflowStepRecord:
        return WorkflowStepRecord(
            id=str(row["step_id"]),
            type=str(row["step_type"]),
            order_index=int(row["order_index"]),
            parameters=_loads(row["parameters_json"], default={}),
            depends_on=_loads(row["depends_on_json"], default=[]),
            on_failure=str(row["on_failure"]),
            status=WorkflowStepStatus(str(row["status"])),
            child_run_id=str(row["child_run_id"]) if row["child_run_id"] else None,
            started_at=str(row["started_at"]) if row["started_at"] else None,
            ended_at=str(row["ended_at"]) if row["ended_at"] else None,
            summary=str(row["summary"] or ""),
            error=str(row["error"] or ""),
            artifact_paths=[
                Path(path) for path in _loads(row["artifact_paths_json"], default=[])
            ],
            result=_loads(row["result_json"], default={}),
        )

    def _row_to_event(self, row: sqlite3.Row) -> WorkflowEvent:
        return WorkflowEvent(
            timestamp=str(row["timestamp"]),
            workflow_id=str(row["workflow_id"]),
            level=str(row["level"]),  # type: ignore[arg-type]
            stage=str(row["stage"]),
            message=str(row["message"]),
            data=_loads(row["data_json"], default={}),
        )
