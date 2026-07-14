from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .events import redact_and_truncate
from .operation_locks import OperationLockStore


SUPERVISOR_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z_supervisor_[a-f0-9]{8}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_supervisor_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_supervisor_{uuid4().hex[:8]}"


def validate_supervisor_id(supervisor_id: str) -> None:
    if not SUPERVISOR_ID_PATTERN.match(supervisor_id):
        raise ValueError(f"Invalid supervisor_id: {supervisor_id}")


def dumps(data: dict[str, Any] | list[Any] | None) -> str:
    return json.dumps(data or {}, sort_keys=True)


def loads(value: str | None) -> Any:
    if not value:
        return {}
    return json.loads(value)


class SupervisorStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "codexbridge.sqlite3"
        self.operation_locks = OperationLockStore(self.runs_dir)
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
                CREATE TABLE IF NOT EXISTS supervisors (
                    supervisor_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    policy_tier INTEGER NOT NULL DEFAULT 1,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    requires_human INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    state_version INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_column(
                conn,
                "supervisors",
                "state_version",
                "INTEGER NOT NULL DEFAULT 0",
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS supervisor_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supervisor_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(supervisor_id) REFERENCES supervisors(supervisor_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS supervisor_run_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supervisor_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(supervisor_id) REFERENCES supervisors(supervisor_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS supervisor_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supervisor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_stage TEXT NOT NULL,
                    event_level TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    dedupe_key TEXT NOT NULL,
                    delivery_status TEXT NOT NULL DEFAULT 'pending',
                    delivery_attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    last_error TEXT NOT NULL DEFAULT '',
                    UNIQUE(supervisor_id, dedupe_key),
                    FOREIGN KEY(supervisor_id) REFERENCES supervisors(supervisor_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_supervisors_created_at ON supervisors(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_supervisors_repo_status ON supervisors(repo_name, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_supervisor_events_supervisor ON supervisor_events(supervisor_id, id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_supervisor_run_links_supervisor ON supervisor_run_links(supervisor_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_supervisor_notifications_supervisor ON supervisor_notifications(supervisor_id, id)"
            )
            conn.execute("DROP INDEX IF EXISTS idx_repo_write_locks_repo")
            conn.execute("DROP TABLE IF EXISTS repo_write_locks")

    def journal_mode(self) -> str:
        with self.connect() as conn:
            return str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def create_supervisor(
        self,
        *,
        supervisor_id: str | None = None,
        repo_name: str,
        objective: str,
        status: str = "queued",
        policy_tier: int = 1,
        risk_level: str = "low",
        requires_human: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        supervisor_id = supervisor_id or make_supervisor_id()
        validate_supervisor_id(supervisor_id)
        created_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO supervisors (
                    supervisor_id, repo_name, status, objective, policy_tier,
                    risk_level, requires_human, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    supervisor_id,
                    repo_name,
                    status,
                    objective,
                    policy_tier,
                    risk_level,
                    int(requires_human),
                    created_at,
                    dumps(metadata),
                ),
            )
        return self.get_supervisor(supervisor_id)

    def get_supervisor(self, supervisor_id: str) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM supervisors WHERE supervisor_id = ?", (supervisor_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Supervisor not found: {supervisor_id}")
        return self._row_to_supervisor(row)

    def update_supervisor(self, supervisor_id: str, **fields: Any) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        if not fields:
            return self.get_supervisor(supervisor_id)
        allowed = {
            "status",
            "started_at",
            "ended_at",
            "summary",
            "error",
            "policy_tier",
            "risk_level",
            "requires_human",
            "metadata_json",
        }
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise ValueError(f"Unsupported supervisor fields: {unknown}")
        normalized = dict(fields)
        if "requires_human" in normalized:
            normalized["requires_human"] = int(bool(normalized["requires_human"]))
        if "metadata_json" in normalized and not isinstance(
            normalized["metadata_json"], str
        ):
            normalized["metadata_json"] = dumps(normalized["metadata_json"])
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = [*normalized.values(), supervisor_id]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE supervisors SET {assignments} WHERE supervisor_id = ?", params
            )
        return self.get_supervisor(supervisor_id)

    def conditional_update_supervisor(
        self,
        supervisor_id: str,
        *,
        fields: dict[str, Any],
        expected_statuses: tuple[str, ...] | list[str] | set[str],
        expected_state_version: int,
    ) -> dict[str, Any] | None:
        validate_supervisor_id(supervisor_id)
        statuses = tuple(str(status) for status in expected_statuses)
        if not statuses:
            return None
        allowed = {
            "status",
            "started_at",
            "ended_at",
            "summary",
            "error",
            "policy_tier",
            "risk_level",
            "requires_human",
            "metadata_json",
        }
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise ValueError(f"Unsupported supervisor fields: {unknown}")
        if not fields:
            raise ValueError("Conditional supervisor update requires fields")

        normalized = dict(fields)
        if "requires_human" in normalized:
            normalized["requires_human"] = int(bool(normalized["requires_human"]))
        if "metadata_json" in normalized and not isinstance(
            normalized["metadata_json"], str
        ):
            normalized["metadata_json"] = dumps(normalized["metadata_json"])

        assignments = [f"{key} = ?" for key in normalized]
        assignments.append("state_version = state_version + 1")
        params: list[Any] = [
            *normalized.values(),
            supervisor_id,
            int(expected_state_version),
            *statuses,
        ]
        placeholders = ", ".join("?" for _ in statuses)

        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE supervisors
                SET {", ".join(assignments)}
                WHERE supervisor_id = ?
                  AND state_version = ?
                  AND status IN ({placeholders})
                """,
                params,
            )
            if int(cursor.rowcount) != 1:
                return None
            row = conn.execute(
                "SELECT * FROM supervisors WHERE supervisor_id = ?",
                (supervisor_id,),
            ).fetchone()

        return self._row_to_supervisor(row) if row is not None else None

    def attach_child(
        self,
        supervisor_id: str,
        *,
        run_id: str,
        link_type: str,
        child_kind: str,
        target_status: str,
        metadata: dict[str, Any],
        expected_statuses: tuple[str, ...] | list[str] | set[str],
        expected_state_version: int,
        started_at: str | None = None,
    ) -> dict[str, Any] | None:
        validate_supervisor_id(supervisor_id)
        statuses = tuple(str(status) for status in expected_statuses)
        if not statuses:
            return None

        attached_metadata = dict(metadata)
        attached_metadata["active_child"] = {
            "run_id": run_id,
            "kind": child_kind,
            "launch_state": "reserved",
        }
        placeholders = ", ".join("?" for _ in statuses)

        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                f"""
                UPDATE supervisors
                SET status = ?,
                    started_at = COALESCE(started_at, ?),
                    metadata_json = ?,
                    state_version = state_version + 1
                WHERE supervisor_id = ?
                  AND state_version = ?
                  AND status IN ({placeholders})
                """,
                (
                    target_status,
                    started_at,
                    dumps(attached_metadata),
                    supervisor_id,
                    int(expected_state_version),
                    *statuses,
                ),
            )
            if int(cursor.rowcount) != 1:
                conn.rollback()
                return None

            existing = conn.execute(
                """
                SELECT id FROM supervisor_run_links
                WHERE supervisor_id = ? AND run_id = ? AND link_type = ?
                """,
                (supervisor_id, run_id, link_type),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO supervisor_run_links (
                        supervisor_id, run_id, link_type, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (supervisor_id, run_id, link_type, utc_now()),
                )

            row = conn.execute(
                "SELECT * FROM supervisors WHERE supervisor_id = ?",
                (supervisor_id,),
            ).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return self._row_to_supervisor(row) if row is not None else None

    def list_supervisors(
        self, repo_name: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        where: list[str] = []
        params: list[Any] = []
        if repo_name:
            where.append("repo_name = ?")
            params.append(repo_name)
        if status:
            where.append("status = ?")
            params.append(status)
        sql = "SELECT * FROM supervisors"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_supervisor(row) for row in rows]

    def append_event(
        self,
        supervisor_id: str,
        *,
        level: str,
        stage: str,
        message: str,
        data: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        event = {
            "timestamp": timestamp or utc_now(),
            "supervisor_id": supervisor_id,
            "level": level,
            "stage": stage,
            "message": message,
            "data": data or {},
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO supervisor_events (supervisor_id, timestamp, level, stage, message, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    supervisor_id,
                    event["timestamp"],
                    level,
                    stage,
                    message,
                    dumps(event["data"]),
                ),
            )
        return event

    def get_events(self, supervisor_id: str, limit: int = 50) -> list[dict[str, Any]]:
        validate_supervisor_id(supervisor_id)
        limit = max(1, min(int(limit), 500))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM supervisor_events
                    WHERE supervisor_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (supervisor_id, limit),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def add_run_link(
        self, supervisor_id: str, run_id: str, link_type: str = "child"
    ) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        created_at = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO supervisor_run_links (supervisor_id, run_id, link_type, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (supervisor_id, run_id, link_type, created_at),
            )
        return {
            "id": cursor.lastrowid,
            "supervisor_id": supervisor_id,
            "run_id": run_id,
            "link_type": link_type,
            "created_at": created_at,
        }

    def list_run_links(self, supervisor_id: str) -> list[dict[str, Any]]:
        validate_supervisor_id(supervisor_id)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, supervisor_id, run_id, link_type, created_at
                FROM supervisor_run_links
                WHERE supervisor_id = ?
                ORDER BY id ASC
                """,
                (supervisor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_notification(
        self,
        supervisor_id: str,
        *,
        event_stage: str,
        event_level: str,
        kind: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
        dedupe_key: str,
    ) -> dict[str, Any]:
        validate_supervisor_id(supervisor_id)
        created_at = utc_now()
        safe_title = str(redact_and_truncate(title, limit=4000))
        safe_message = str(redact_and_truncate(message, limit=4000))
        safe_payload = redact_and_truncate(payload or {}, limit=4000)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO supervisor_notifications (
                    supervisor_id, created_at, event_stage, event_level, kind,
                    title, message, payload_json, dedupe_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    supervisor_id,
                    created_at,
                    event_stage,
                    event_level,
                    kind,
                    safe_title,
                    safe_message,
                    dumps(safe_payload),
                    dedupe_key,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM supervisor_notifications
                WHERE supervisor_id = ? AND dedupe_key = ?
                """,
                (supervisor_id, dedupe_key),
            ).fetchone()
        if row is None:
            raise KeyError(
                f"Notification not found after insert: {supervisor_id} {dedupe_key}"
            )
        return self._row_to_notification(row)

    def get_notification(self, notification_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM supervisor_notifications WHERE id = ?",
                (notification_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Notification not found: {notification_id}")
        return self._row_to_notification(row)

    def list_notifications(
        self,
        supervisor_id: str | None = None,
        delivery_status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        where: list[str] = []
        params: list[Any] = []
        if supervisor_id:
            validate_supervisor_id(supervisor_id)
            where.append("supervisor_id = ?")
            params.append(supervisor_id)
        if delivery_status:
            where.append("delivery_status = ?")
            params.append(delivery_status)
        sql = "SELECT * FROM supervisor_notifications"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_notification(row) for row in rows]

    def update_notification_delivery(
        self,
        notification_id: int,
        *,
        delivery_status: str,
        last_error: str = "",
        increment_attempts: bool = True,
    ) -> dict[str, Any]:
        last_attempt_at = utc_now()
        attempts_sql = (
            "delivery_attempts + 1" if increment_attempts else "delivery_attempts"
        )
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE supervisor_notifications
                SET delivery_status = ?, last_attempt_at = ?, last_error = ?,
                    delivery_attempts = {attempts_sql}
                WHERE id = ?
                """,
                (delivery_status, last_attempt_at, last_error, notification_id),
            )
        return self.get_notification(notification_id)

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _row_to_supervisor(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["requires_human"] = bool(result["requires_human"])
        result["metadata"] = loads(result.pop("metadata_json"))
        return result

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "timestamp": row["timestamp"],
            "supervisor_id": row["supervisor_id"],
            "level": row["level"],
            "stage": row["stage"],
            "message": row["message"],
            "data": loads(row["data_json"]),
        }

    def _row_to_notification(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = loads(result.pop("payload_json"))
        return result
