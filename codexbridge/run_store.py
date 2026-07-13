from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[a-z0-9_]+_[a-f0-9]{8}$")
TERMINAL_STATUSES = {
    "completed",
    "partial",
    "failed",
    "cancelled",
    "timed_out",
    "needs_input",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id}")


def dumps(data: dict[str, Any] | list[Any] | None) -> str:
    return json.dumps({} if data is None else data, sort_keys=True)


def loads(value: str | None) -> Any:
    if not value:
        return {}
    return json.loads(value)


class RunStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
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
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    requires_human INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_seconds REAL,
                    pid INTEGER,
                    launcher_pid INTEGER,
                    worker_pid INTEGER,
                    worker_lease_token TEXT NOT NULL DEFAULT '',
                    worker_identity TEXT NOT NULL DEFAULT '',
                    worker_claimed_at TEXT,
                    launch_attempts INTEGER NOT NULL DEFAULT 0,
                    recovery_reason TEXT NOT NULL DEFAULT '',
                    exit_code INTEGER,
                    run_dir TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    safety_failure INTEGER NOT NULL DEFAULT 0,
                    current_phase TEXT NOT NULL DEFAULT '',
                    elapsed_seconds REAL NOT NULL DEFAULT 0,
                    heartbeat_at TEXT,
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_repo_status ON runs(repo_name, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id, id)"
            )
            self._ensure_column(
                conn, "runs", "current_phase", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                conn, "runs", "elapsed_seconds", "REAL NOT NULL DEFAULT 0"
            )
            self._ensure_column(conn, "runs", "heartbeat_at", "TEXT")
            self._ensure_column(
                conn, "runs", "progress_json", "TEXT NOT NULL DEFAULT '{}'"
            )
            self._ensure_column(conn, "runs", "launcher_pid", "INTEGER")
            self._ensure_column(
                conn, "runs", "worker_lease_token", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(
                conn, "runs", "worker_identity", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(conn, "runs", "worker_claimed_at", "TEXT")
            self._ensure_column(
                conn, "runs", "launch_attempts", "INTEGER NOT NULL DEFAULT 0"
            )
            self._ensure_column(
                conn, "runs", "recovery_reason", "TEXT NOT NULL DEFAULT ''"
            )

    def journal_mode(self) -> str:
        with self.connect() as conn:
            return str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def create_run(
        self,
        *,
        run_id: str,
        repo_name: str,
        tool: str,
        run_dir: Path,
        input_data: dict[str, Any],
        risk_level: str = "low",
        requires_human: bool = False,
        status: str = "queued",
        worker_lease_token: str = "",
    ) -> dict[str, Any]:
        validate_run_id(run_id)
        created_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, repo_name, tool, status, risk_level, requires_human,
                    created_at, run_dir, current_phase, heartbeat_at, input_json,
                    worker_lease_token
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_name,
                    tool,
                    status,
                    risk_level,
                    int(requires_human),
                    created_at,
                    str(run_dir),
                    status,
                    created_at,
                    dumps(input_data),
                    worker_lease_token,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        validate_run_id(run_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        return self._row_to_run(row)

    def list_runs(
        self, repo_name: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        where: list[str] = []
        params: list[Any] = []
        if repo_name:
            where.append("lower(repo_name) = lower(?)")
            params.append(repo_name)
        if status:
            where.append("status = ?")
            params.append(status)
        sql = "SELECT * FROM runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_run(row) for row in rows]

    def latest_run(
        self, repo_name: str | None = None, tool: str | None = None
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if repo_name:
            where.append("lower(repo_name) = lower(?)")
            params.append(repo_name)
        if tool:
            where.append("tool = ?")
            params.append(tool)
        sql = "SELECT * FROM runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if row is None:
            raise KeyError("No runs found")
        return self._row_to_run(row)

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        validate_run_id(run_id)
        if not fields:
            return self.get_run(run_id)
        normalized = dict(fields)
        if "requires_human" in normalized:
            normalized["requires_human"] = int(bool(normalized["requires_human"]))
        if "safety_failure" in normalized:
            normalized["safety_failure"] = int(bool(normalized["safety_failure"]))
        if "input_json" in normalized and not isinstance(normalized["input_json"], str):
            normalized["input_json"] = dumps(normalized["input_json"])
        if "result_json" in normalized and not isinstance(
            normalized["result_json"], str
        ):
            normalized["result_json"] = dumps(normalized["result_json"])
        if "progress_json" in normalized and not isinstance(
            normalized["progress_json"], str
        ):
            normalized["progress_json"] = dumps(normalized["progress_json"])
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = [*normalized.values(), run_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE runs SET {assignments} WHERE run_id = ?", params)
        return self.get_run(run_id)

    def append_event(
        self,
        run_id: str,
        *,
        level: str,
        stage: str,
        message: str,
        data: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        validate_run_id(run_id)
        event = {
            "timestamp": timestamp or utc_now(),
            "run_id": run_id,
            "level": level,
            "stage": stage,
            "message": message,
            "data": data or {},
        }
        self.update_run(
            run_id,
            heartbeat_at=event["timestamp"],
            current_phase=stage,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events (run_id, timestamp, level, stage, message, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event["timestamp"],
                    level,
                    stage,
                    message,
                    dumps(event["data"]),
                ),
            )
        return event

    def get_events(
        self, run_id: str, limit: int = 50, after_id: int | None = None
    ) -> list[dict[str, Any]]:
        validate_run_id(run_id)
        limit = max(1, min(int(limit), 500))
        with self.connect() as conn:
            if after_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM events WHERE run_id = ? ORDER BY id DESC LIMIT ?
                    ) ORDER BY id ASC
                    """,
                    (run_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
                    (run_id, max(0, int(after_id)), limit),
                ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def list_recoverable_runs(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM runs
                WHERE status IN (
                    'launch_pending', 'queued', 'running',
                    'cancellation_pending', 'recovery_pending'
                )
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def record_worker_launch(self, run_id: str, launcher_pid: int) -> dict[str, Any]:
        validate_run_id(run_id)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = 'queued', current_phase = 'queued',
                    launcher_pid = ?, launch_attempts = launch_attempts + 1,
                    heartbeat_at = ?, recovery_reason = ''
                WHERE run_id = ?
                  AND status IN ('launch_pending', 'queued', 'recovery_pending')
                """,
                (int(launcher_pid), now, run_id),
            )
        return self.get_run(run_id)

    def claim_worker(
        self,
        run_id: str,
        *,
        lease_token: str,
        worker_pid: int,
        worker_identity: str,
    ) -> bool:
        validate_run_id(run_id)
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE runs
                SET status = 'running', current_phase = 'worker',
                    worker_pid = ?, worker_identity = ?, worker_claimed_at = ?,
                    started_at = COALESCE(started_at, ?), heartbeat_at = ?,
                    recovery_reason = ''
                WHERE run_id = ?
                  AND worker_lease_token = ?
                  AND status IN ('launch_pending', 'queued', 'running', 'recovery_pending')
                """,
                (
                    int(worker_pid),
                    worker_identity,
                    now,
                    now,
                    now,
                    run_id,
                    lease_token,
                ),
            )
        return int(cursor.rowcount) == 1

    def heartbeat_worker(
        self,
        run_id: str,
        *,
        lease_token: str,
        elapsed_seconds: float,
        progress_updates: dict[str, Any] | None = None,
    ) -> bool:
        current = self.get_run(run_id)
        progress = dict(current.get("progress") or {})
        progress.update(progress_updates or {})
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE runs
                SET heartbeat_at = ?, elapsed_seconds = ?, progress_json = ?
                WHERE run_id = ? AND worker_lease_token = ?
                """,
                (utc_now(), elapsed_seconds, dumps(progress), run_id, lease_token),
            )
        return int(cursor.rowcount) == 1

    def mark_recovery_pending(self, run_id: str, reason: str) -> dict[str, Any]:
        return self.update_run(
            run_id,
            status="recovery_pending",
            current_phase="recovery_pending",
            recovery_reason=reason,
            error=reason,
            ended_at=None,
        )

    def fail_infrastructure(self, run_id: str, reason: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        ended_at = utc_now()
        result = {
            "run_id": run_id,
            "repo_name": run["repo_name"],
            "tool": run["tool"],
            "status": "failed",
            "classification": "infrastructure_failure",
            "process_success": None,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "started_at": run.get("started_at"),
            "ended_at": ended_at,
            "duration_seconds": run.get("duration_seconds"),
            "summary": reason,
            "error": reason,
            "cancelled": False,
            "timed_out": False,
        }
        return self.update_run(
            run_id,
            status="failed",
            current_phase="result",
            ended_at=ended_at,
            error=reason,
            recovery_reason=reason,
            result_json=result,
        )

    def mark_stale_running(self) -> int:
        """Deprecated: startup recovery is process-aware in JobManager."""
        return 0

    def set_progress(
        self,
        run_id: str,
        *,
        phase: str,
        progress: dict[str, Any] | None = None,
        elapsed_seconds: float | None = None,
        heartbeat_at: str | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "current_phase": phase,
            "heartbeat_at": heartbeat_at or utc_now(),
            "progress_json": progress or {},
        }
        if elapsed_seconds is not None:
            fields["elapsed_seconds"] = elapsed_seconds
        return self.update_run(run_id, **fields)

    def heartbeat(
        self,
        run_id: str,
        *,
        elapsed_seconds: float,
        progress_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_run(run_id)
        progress = dict(current.get("progress") or {})
        progress.update(progress_updates or {})
        return self.set_progress(
            run_id,
            phase=str(current.get("current_phase") or "running"),
            progress=progress,
            elapsed_seconds=elapsed_seconds,
        )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _row_to_run(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["requires_human"] = bool(result["requires_human"])
        result["safety_failure"] = bool(result["safety_failure"])
        result["input"] = loads(result.pop("input_json"))
        result["progress"] = loads(result.pop("progress_json"))
        result["result"] = loads(result.pop("result_json"))

        now = datetime.now(timezone.utc)
        started_at = result.get("started_at")
        if started_at:
            started = datetime.fromisoformat(str(started_at))
            ended_at = result.get("ended_at")
            ended = datetime.fromisoformat(str(ended_at)) if ended_at else now
            dynamic_elapsed = max(0.0, (ended - started).total_seconds())
            result["elapsed_seconds"] = round(
                max(float(result.get("elapsed_seconds") or 0.0), dynamic_elapsed), 3
            )

        heartbeat_at = result.get("heartbeat_at")
        heartbeat_age = None
        if heartbeat_at:
            heartbeat = datetime.fromisoformat(str(heartbeat_at))
            heartbeat_age = round(max(0.0, (now - heartbeat).total_seconds()), 3)
        result["heartbeat_age_seconds"] = heartbeat_age
        result["worker_stale"] = bool(
            result.get("status") == "running"
            and heartbeat_age is not None
            and heartbeat_age > 30.0
        )
        return result

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "run_id": row["run_id"],
            "level": row["level"],
            "stage": row["stage"],
            "message": row["message"],
            "data": loads(row["data_json"]),
        }
