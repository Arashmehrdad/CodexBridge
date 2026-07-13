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


_UNSET = object()
_WORKFLOW_TERMINAL_STATUSES = frozenset(
    {
        WorkflowStatus.NEEDS_APPROVAL.value,
        WorkflowStatus.NEEDS_INPUT.value,
        WorkflowStatus.COMPLETED.value,
        WorkflowStatus.FAILED.value,
        WorkflowStatus.CANCELLED.value,
        WorkflowStatus.REPORTED.value,
    }
)
_WORKFLOW_UPDATE_FIELDS = frozenset(
    {
        "status",
        "terminal_status",
        "started_at",
        "ended_at",
        "launcher_pid",
        "worker_pid",
        "worker_lease_token",
        "lease_generation",
        "worker_identity",
        "worker_claimed_at",
        "launch_attempts",
        "heartbeat_at",
        "active_child_run_id",
        "failure_summary",
        "recommended_next_action",
        "artifact_paths_json",
        "result_json",
    }
)
_STEP_UPDATE_FIELDS = frozenset(
    {
        "status",
        "child_run_id",
        "child_launch_attempts",
        "started_at",
        "ended_at",
        "summary",
        "error",
        "artifact_paths_json",
        "result_json",
    }
)


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

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                    launcher_pid INTEGER,
                    worker_pid INTEGER,
                    worker_lease_token TEXT NOT NULL DEFAULT '',
                    lease_generation INTEGER NOT NULL DEFAULT 1,
                    state_version INTEGER NOT NULL DEFAULT 0,
                    worker_identity TEXT NOT NULL DEFAULT '',
                    worker_claimed_at TEXT,
                    launch_attempts INTEGER NOT NULL DEFAULT 0,
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
                    state_version INTEGER NOT NULL DEFAULT 0,
                    child_run_id TEXT,
                    child_launch_attempts INTEGER NOT NULL DEFAULT 0,
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
            for column, definition in (
                ("launcher_pid", "INTEGER"),
                ("worker_lease_token", "TEXT NOT NULL DEFAULT ''"),
                ("lease_generation", "INTEGER NOT NULL DEFAULT 1"),
                ("state_version", "INTEGER NOT NULL DEFAULT 0"),
                ("worker_identity", "TEXT NOT NULL DEFAULT ''"),
                ("worker_claimed_at", "TEXT"),
                ("launch_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ):
                self._ensure_column(conn, "workflows", column, definition)
            for column, definition in (
                ("state_version", "INTEGER NOT NULL DEFAULT 0"),
                ("child_launch_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ):
                self._ensure_column(conn, "workflow_steps", column, definition)
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
        worker_lease_token: str = "",
        lease_generation: int = 1,
        launch_attempts: int = 0,
    ) -> WorkflowRecord:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO workflows (
                    workflow_id, repo_name, objective, status, created_at, updated_at,
                    worker_lease_token, lease_generation, launch_attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    repo_name,
                    objective,
                    status.value,
                    now,
                    now,
                    worker_lease_token,
                    int(lease_generation),
                    int(launch_attempts),
                ),
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

    @staticmethod
    def _normalize_workflow_fields(fields: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(fields)
        for json_field in ("artifact_paths_json", "result_json"):
            if json_field in normalized and not isinstance(normalized[json_field], str):
                normalized[json_field] = _dumps(normalized[json_field])
        for enum_field in ("status", "terminal_status"):
            if enum_field in normalized and isinstance(normalized[enum_field], WorkflowStatus):
                normalized[enum_field] = normalized[enum_field].value
        return normalized

    @staticmethod
    def _normalize_step_fields(fields: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(fields)
        for json_field in (
            "parameters_json",
            "depends_on_json",
            "artifact_paths_json",
            "result_json",
        ):
            if json_field in normalized and not isinstance(normalized[json_field], str):
                normalized[json_field] = _dumps(normalized[json_field])
        if "status" in normalized and isinstance(
            normalized["status"], WorkflowStepStatus
        ):
            normalized["status"] = normalized["status"].value
        return normalized

    def update_workflow(self, workflow_id: str, **fields: Any) -> WorkflowRecord:
        if not fields:
            return self.get_workflow(workflow_id)
        normalized = self._normalize_workflow_fields(fields)
        normalized["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = [*normalized.values(), workflow_id]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE workflows SET {assignments} WHERE workflow_id = ?", params
            )
        return self.get_workflow(workflow_id)

    def conditional_update_workflow(
        self,
        workflow_id: str,
        *,
        fields: dict[str, Any],
        expected_statuses: list[str] | tuple[str, ...] | set[str] | None = None,
        expected_state_version: int | None = None,
        expected_lease_token: str | None = None,
        expected_lease_generation: int | None = None,
        expected_heartbeat_at: Any = _UNSET,
        reject_terminal: bool = False,
        bump_state_version: bool = True,
    ) -> WorkflowRecord | None:
        unknown = set(fields) - _WORKFLOW_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported conditional workflow fields: {sorted(unknown)}")
        normalized = self._normalize_workflow_fields(fields)
        normalized["updated_at"] = utc_now()
        assignments = [f"{key} = ?" for key in normalized]
        params: list[Any] = list(normalized.values())
        if bump_state_version:
            assignments.append("state_version = state_version + 1")

        where = ["workflow_id = ?"]
        params.append(workflow_id)
        if expected_statuses is not None:
            statuses = tuple(
                status.value if isinstance(status, WorkflowStatus) else str(status)
                for status in expected_statuses
            )
            if not statuses:
                return None
            where.append("status IN (" + ", ".join("?" for _ in statuses) + ")")
            params.extend(statuses)
        if expected_state_version is not None:
            where.append("state_version = ?")
            params.append(int(expected_state_version))
        if expected_lease_token is not None:
            where.append("worker_lease_token = ?")
            params.append(expected_lease_token)
        if expected_lease_generation is not None:
            where.append("lease_generation = ?")
            params.append(int(expected_lease_generation))
        if expected_heartbeat_at is not _UNSET:
            if expected_heartbeat_at is None:
                where.append("heartbeat_at IS NULL")
            else:
                where.append("heartbeat_at = ?")
                params.append(str(expected_heartbeat_at))
        if reject_terminal:
            terminal = tuple(sorted(_WORKFLOW_TERMINAL_STATUSES))
            where.append("status NOT IN (" + ", ".join("?" for _ in terminal) + ")")
            params.extend(terminal)

        with self.connect() as conn:
            cursor = conn.execute(
                f"UPDATE workflows SET {', '.join(assignments)} WHERE {' AND '.join(where)}",
                params,
            )
        if int(cursor.rowcount) != 1:
            return None
        return self.get_workflow(workflow_id)

    def record_worker_launch(
        self,
        workflow_id: str,
        launcher_pid: int,
        *,
        expected_state_version: int,
        lease_token: str,
        lease_generation: int,
    ) -> WorkflowRecord | None:
        return self.conditional_update_workflow(
            workflow_id,
            fields={"launcher_pid": int(launcher_pid), "heartbeat_at": utc_now()},
            expected_statuses=(WorkflowStatus.QUEUED,),
            expected_state_version=expected_state_version,
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            reject_terminal=True,
        )

    def claim_worker(
        self,
        workflow_id: str,
        *,
        lease_token: str,
        lease_generation: int,
        expected_state_version: int,
        worker_pid: int,
        worker_identity: str,
    ) -> bool:
        current = self.get_workflow(workflow_id)
        now = utc_now()
        updated = self.conditional_update_workflow(
            workflow_id,
            fields={
                "status": WorkflowStatus.RUNNING,
                "worker_pid": int(worker_pid),
                "worker_identity": worker_identity,
                "worker_claimed_at": now,
                "started_at": current.started_at or now,
                "heartbeat_at": now,
            },
            expected_statuses=(WorkflowStatus.QUEUED,),
            expected_state_version=expected_state_version,
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            reject_terminal=True,
        )
        return updated is not None

    def heartbeat_worker(
        self,
        workflow_id: str,
        *,
        lease_token: str,
        lease_generation: int,
        worker_pid: int,
    ) -> bool:
        updated = self.conditional_update_workflow(
            workflow_id,
            fields={"heartbeat_at": utc_now(), "worker_pid": int(worker_pid)},
            expected_statuses=(WorkflowStatus.RUNNING,),
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            bump_state_version=False,
        )
        return updated is not None

    def adopt_worker(
        self,
        workflow_id: str,
        *,
        expected_state_version: int,
        lease_token: str,
        lease_generation: int,
        expected_heartbeat_at: str | None,
    ) -> WorkflowRecord | None:
        return self.conditional_update_workflow(
            workflow_id,
            fields={"heartbeat_at": utc_now()},
            expected_statuses=(WorkflowStatus.RUNNING,),
            expected_state_version=expected_state_version,
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            expected_heartbeat_at=expected_heartbeat_at,
            reject_terminal=True,
        )

    def reserve_next_launch(
        self,
        workflow_id: str,
        *,
        expected_statuses: tuple[WorkflowStatus | str, ...],
        expected_state_version: int,
        expected_lease_token: str,
        expected_lease_generation: int,
        expected_heartbeat_at: str | None,
        new_lease_token: str,
    ) -> WorkflowRecord | None:
        current = self.get_workflow(workflow_id)
        return self.conditional_update_workflow(
            workflow_id,
            fields={
                "status": WorkflowStatus.QUEUED,
                "launcher_pid": None,
                "worker_pid": None,
                "worker_lease_token": new_lease_token,
                "lease_generation": int(expected_lease_generation) + 1,
                "worker_identity": "",
                "worker_claimed_at": None,
                "launch_attempts": int(current.launch_attempts) + 1,
                "heartbeat_at": utc_now(),
            },
            expected_statuses=expected_statuses,
            expected_state_version=expected_state_version,
            expected_lease_token=expected_lease_token,
            expected_lease_generation=expected_lease_generation,
            expected_heartbeat_at=expected_heartbeat_at,
            reject_terminal=True,
        )

    def claim_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        lease_token: str,
        lease_generation: int,
        child_run_id: str | None,
    ) -> WorkflowRecord | None:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            workflow_cursor = conn.execute(
                """
                UPDATE workflows
                SET active_child_run_id = ?, updated_at = ?,
                    state_version = state_version + 1
                WHERE workflow_id = ? AND status = ?
                  AND worker_lease_token = ? AND lease_generation = ?
                  AND active_child_run_id IS NULL
                """,
                (
                    child_run_id,
                    now,
                    workflow_id,
                    WorkflowStatus.RUNNING.value,
                    lease_token,
                    int(lease_generation),
                ),
            )
            if int(workflow_cursor.rowcount) != 1:
                conn.rollback()
                return None
            step_cursor = conn.execute(
                """
                UPDATE workflow_steps
                SET status = ?, state_version = state_version + 1,
                    child_run_id = ?,
                    child_launch_attempts = child_launch_attempts + ?,
                    started_at = COALESCE(started_at, ?),
                    summary = 'Step running', error = ''
                WHERE workflow_id = ? AND step_id = ? AND status = ?
                """,
                (
                    WorkflowStepStatus.RUNNING.value,
                    child_run_id,
                    1 if child_run_id else 0,
                    now,
                    workflow_id,
                    step_id,
                    WorkflowStepStatus.PENDING.value,
                ),
            )
            if int(step_cursor.rowcount) != 1:
                conn.rollback()
                return None
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_workflow(workflow_id)

    def conditional_update_step(
        self,
        workflow_id: str,
        step_id: str,
        *,
        fields: dict[str, Any],
        expected_statuses: tuple[WorkflowStepStatus | str, ...],
        lease_token: str,
        lease_generation: int,
        expected_state_version: int | None = None,
        expected_child_run_id: Any = _UNSET,
        clear_active_child: bool = False,
    ) -> WorkflowRecord | None:
        unknown = set(fields) - _STEP_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported conditional workflow step fields: {sorted(unknown)}")
        normalized = self._normalize_step_fields(fields)
        assignments = [f"{key} = ?" for key in normalized]
        assignments.append("state_version = state_version + 1")
        params: list[Any] = list(normalized.values())
        statuses = tuple(
            status.value if isinstance(status, WorkflowStepStatus) else str(status)
            for status in expected_statuses
        )
        if not statuses:
            return None
        where = [
            "workflow_id = ?",
            "step_id = ?",
            "status IN (" + ", ".join("?" for _ in statuses) + ")",
            "EXISTS (SELECT 1 FROM workflows w WHERE w.workflow_id = workflow_steps.workflow_id AND w.status = ? AND w.worker_lease_token = ? AND w.lease_generation = ?)",
        ]
        params.extend(
            [
                workflow_id,
                step_id,
                *statuses,
                WorkflowStatus.RUNNING.value,
                lease_token,
                int(lease_generation),
            ]
        )
        if expected_state_version is not None:
            where.append("state_version = ?")
            params.append(int(expected_state_version))
        if expected_child_run_id is not _UNSET:
            if expected_child_run_id is None:
                where.append("child_run_id IS NULL")
            else:
                where.append("child_run_id = ?")
                params.append(str(expected_child_run_id))

        now = utc_now()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            step_cursor = conn.execute(
                f"UPDATE workflow_steps SET {', '.join(assignments)} WHERE {' AND '.join(where)}",
                params,
            )
            if int(step_cursor.rowcount) != 1:
                conn.rollback()
                return None
            workflow_where = (
                "workflow_id = ? AND status = ? AND worker_lease_token = ? "
                "AND lease_generation = ?"
            )
            workflow_params: list[Any] = [
                now,
                workflow_id,
                WorkflowStatus.RUNNING.value,
                lease_token,
                int(lease_generation),
            ]
            active_assignment = ""
            if clear_active_child:
                if expected_child_run_id is _UNSET or expected_child_run_id is None:
                    conn.rollback()
                    raise ValueError("Clearing an active child requires its expected run ID")
                active_assignment = "active_child_run_id = NULL, "
                workflow_where += " AND active_child_run_id = ?"
                workflow_params.append(str(expected_child_run_id))
            workflow_cursor = conn.execute(
                f"""
                UPDATE workflows
                SET {active_assignment}updated_at = ?, state_version = state_version + 1
                WHERE {workflow_where}
                """,
                workflow_params,
            )
            if int(workflow_cursor.rowcount) != 1:
                conn.rollback()
                return None
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_workflow(workflow_id)

    def transition_terminal(
        self,
        workflow_id: str,
        *,
        status: WorkflowStatus,
        expected_state_version: int,
        lease_token: str,
        lease_generation: int,
        failure_summary: str,
        recommended_next_action: str,
    ) -> WorkflowRecord | None:
        if status.value not in _WORKFLOW_TERMINAL_STATUSES or status == WorkflowStatus.REPORTED:
            raise ValueError(f"Not a workflow terminal source status: {status.value}")
        return self.conditional_update_workflow(
            workflow_id,
            fields={
                "status": status,
                "terminal_status": status,
                "ended_at": utc_now(),
                "active_child_run_id": None,
                "failure_summary": failure_summary,
                "recommended_next_action": recommended_next_action,
            },
            expected_statuses=(WorkflowStatus.RUNNING,),
            expected_state_version=expected_state_version,
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            reject_terminal=True,
        )

    def cancel_workflow(
        self,
        workflow_id: str,
        *,
        expected_statuses: tuple[WorkflowStatus | str, ...],
        expected_state_version: int,
        expected_lease_token: str,
        expected_lease_generation: int,
        result: dict[str, Any],
    ) -> WorkflowRecord | None:
        statuses = tuple(
            status.value if isinstance(status, WorkflowStatus) else str(status)
            for status in expected_statuses
        )
        if not statuses:
            return None
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            workflow_cursor = conn.execute(
                """
                UPDATE workflows
                SET status = ?, terminal_status = ?, ended_at = ?,
                    active_child_run_id = NULL,
                    failure_summary = CASE
                        WHEN failure_summary = '' THEN 'Workflow cancelled'
                        ELSE failure_summary
                    END,
                    recommended_next_action = ?, result_json = ?,
                    updated_at = ?, state_version = state_version + 1
                WHERE workflow_id = ? AND state_version = ?
                  AND worker_lease_token = ? AND lease_generation = ?
                  AND status IN ("""
                + ", ".join("?" for _ in statuses)
                + ")",
                (
                    WorkflowStatus.CANCELLED.value,
                    WorkflowStatus.CANCELLED.value,
                    now,
                    "Review completed work and restart only if needed.",
                    _dumps(result),
                    now,
                    workflow_id,
                    int(expected_state_version),
                    expected_lease_token,
                    int(expected_lease_generation),
                    *statuses,
                ),
            )
            if int(workflow_cursor.rowcount) != 1:
                conn.rollback()
                return None
            conn.execute(
                """
                UPDATE workflow_steps
                SET status = ?, ended_at = ?,
                    summary = CASE
                        WHEN status = ? THEN 'Cancelled by request'
                        ELSE 'Cancelled before execution'
                    END,
                    error = CASE
                        WHEN status = ? THEN 'Workflow cancelled'
                        ELSE 'Workflow cancelled before execution'
                    END,
                    state_version = state_version + 1
                WHERE workflow_id = ? AND status IN (?, ?)
                """,
                (
                    WorkflowStepStatus.CANCELLED.value,
                    now,
                    WorkflowStepStatus.RUNNING.value,
                    WorkflowStepStatus.RUNNING.value,
                    workflow_id,
                    WorkflowStepStatus.PENDING.value,
                    WorkflowStepStatus.RUNNING.value,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_workflow(workflow_id)

    def mark_reported(
        self,
        workflow_id: str,
        *,
        expected_status: WorkflowStatus,
        expected_state_version: int,
        terminal_status: WorkflowStatus,
        artifact_paths: list[str],
    ) -> WorkflowRecord | None:
        return self.conditional_update_workflow(
            workflow_id,
            fields={
                "status": WorkflowStatus.REPORTED,
                "terminal_status": terminal_status,
                "artifact_paths_json": artifact_paths,
            },
            expected_statuses=(expected_status,),
            expected_state_version=expected_state_version,
        )

    def update_step(
        self, workflow_id: str, step_id: str, **fields: Any
    ) -> WorkflowRecord:
        normalized = self._normalize_step_fields(fields)
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
        update_workflow_metadata: bool = True,
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
            if update_workflow_metadata:
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
            launcher_pid=int(workflow_row["launcher_pid"])
            if workflow_row["launcher_pid"]
            else None,
            worker_pid=int(workflow_row["worker_pid"]) if workflow_row["worker_pid"] else None,
            worker_lease_token=str(workflow_row["worker_lease_token"] or ""),
            lease_generation=int(workflow_row["lease_generation"] or 1),
            state_version=int(workflow_row["state_version"] or 0),
            worker_identity=str(workflow_row["worker_identity"] or ""),
            worker_claimed_at=str(workflow_row["worker_claimed_at"])
            if workflow_row["worker_claimed_at"]
            else None,
            launch_attempts=int(workflow_row["launch_attempts"] or 0),
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
            state_version=int(row["state_version"] or 0),
            child_run_id=str(row["child_run_id"]) if row["child_run_id"] else None,
            child_launch_attempts=int(row["child_launch_attempts"] or 0),
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
