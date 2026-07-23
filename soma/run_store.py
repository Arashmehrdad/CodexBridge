from __future__ import annotations

import json
import re
import sqlite3
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from soma.public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
    PublicView,
)
from soma.run_public_result import (
    PUBLIC_RESULT_SCHEMA_VERSION,
    PUBLIC_RESULT_STATUSES,
    PUBLIC_RESULT_STATUS_NOT_MATERIALIZED,
)


RUN_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[a-z0-9_]+_[a-f0-9]{8}$")
TERMINAL_STATUSES = {
    "completed",
    "partial",
    "failed",
    "cancelled",
    "timed_out",
    "needs_input",
}
# Historical durable run types whose records stay readable but for which no
# new instances can ever be created or relaunched. Soma no longer executes
# Codex; coding work is handed off manually via external-coder handoffs.
LEGACY_READ_ONLY_TOOLS = frozenset({"codex_plan_task", "codex_implement_task"})
_UNSET = object()
_CONDITIONAL_UPDATE_FIELDS = frozenset(
    {
        "status",
        "current_phase",
        "launcher_pid",
        "worker_pid",
        "worker_lease_token",
        "lease_generation",
        "worker_identity",
        "worker_claimed_at",
        "launch_attempts",
        "started_at",
        "ended_at",
        "duration_seconds",
        "pid",
        "exit_code",
        "summary",
        "error",
        "safety_failure",
        "heartbeat_at",
        "elapsed_seconds",
        "progress_json",
        "result_json",
        "result_publication_status",
        "result_published_hash",
        "result_published_at",
        "result_publication_error",
        "public_result_json",
        "public_result_schema_version",
        "public_result_source_sha256",
        "public_result_status",
        "public_result_error",
        "recovery_reason",
    }
)

RUN_SUMMARY_ORDERING: Final[str] = "created_at DESC, run_id DESC"
RUN_SUMMARY_DEFAULT_LIMIT: Final[int] = 10
RUN_SUMMARY_MAX_LIMIT: Final[int] = 100
RUN_SUMMARY_CURSOR_OPERATION: Final[str] = "run_summary_list"
RUN_SUMMARY_CURSOR_TTL_SECONDS: Final[int] = 300
RUN_EVENT_DEFAULT_LIMIT: Final[int] = 20
RUN_EVENT_MAX_LIMIT: Final[int] = 500
RUN_EVENT_CURSOR_OPERATION: Final[str] = "run_event_delta"
RUN_EVENT_CURSOR_TTL_SECONDS: Final[int] = 300

RUN_SUMMARY_PROJECTION_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "repo_name",
    "tool",
    "status",
    "risk_level",
    "requires_human",
    "created_at",
    "started_at",
    "ended_at",
    "duration_seconds",
    "pid",
    "launcher_pid",
    "worker_pid",
    "lease_generation",
    "state_version",
    "worker_claimed_at",
    "launch_attempts",
    "recovery_reason",
    "exit_code",
    "summary",
    "error",
    "safety_failure",
    "current_phase",
    "elapsed_seconds",
    "heartbeat_at",
    "result_publication_status",
    "result_published_hash",
    "result_published_at",
    "result_publication_error",
)

RUN_CONTROL_PROJECTION_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "repo_name",
    "tool",
    "status",
    "risk_level",
    "requires_human",
    "started_at",
    "ended_at",
    "pid",
    "launcher_pid",
    "worker_pid",
    "worker_identity",
    "state_version",
    "current_phase",
    "elapsed_seconds",
    "heartbeat_at",
    "last_output_at",
    "cancellation_requested_at",
    "result_publication_status",
    "result_published_hash",
    "result_published_at",
    "result_publication_error",
    "summary",
    "error",
    "safety_failure",
    "recovery_reason",
)

RUN_SUMMARY_SELECT_SQL: Final[str] = (
    "SELECT " + ", ".join(RUN_SUMMARY_PROJECTION_COLUMNS) + " FROM runs"
)
RUN_CONTROL_SELECT_SQL: Final[str] = (
    "SELECT " + ", ".join(RUN_CONTROL_PROJECTION_COLUMNS) + " FROM runs"
)


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
        self.db_path = self.runs_dir / "soma.sqlite3"
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
                    lease_generation INTEGER NOT NULL DEFAULT 1,
                    state_version INTEGER NOT NULL DEFAULT 0,
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
                    last_output_at TEXT NOT NULL DEFAULT '',
                    cancellation_requested_at TEXT NOT NULL DEFAULT '',
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    result_publication_status TEXT NOT NULL DEFAULT 'not_published',
                    result_published_hash TEXT NOT NULL DEFAULT '',
                    result_published_at TEXT,
                    result_publication_error TEXT NOT NULL DEFAULT '',
                    public_result_json TEXT NOT NULL DEFAULT '{}',
                    public_result_schema_version TEXT NOT NULL DEFAULT '',
                    public_result_source_sha256 TEXT NOT NULL DEFAULT '',
                    public_result_status TEXT NOT NULL DEFAULT 'not_materialized',
                    public_result_error TEXT NOT NULL DEFAULT ''
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
                "CREATE INDEX IF NOT EXISTS idx_runs_created_run_id_desc "
                "ON runs(created_at DESC, run_id DESC)"
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
                conn, "runs", "lease_generation", "INTEGER NOT NULL DEFAULT 1"
            )
            self._ensure_column(
                conn, "runs", "state_version", "INTEGER NOT NULL DEFAULT 0"
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
            self._ensure_column(
                conn,
                "runs",
                "result_publication_status",
                "TEXT NOT NULL DEFAULT 'not_published'",
            )
            self._ensure_column(
                conn, "runs", "result_published_hash", "TEXT NOT NULL DEFAULT ''"
            )
            self._ensure_column(conn, "runs", "result_published_at", "TEXT")
            last_output_added = self._ensure_column(
                conn, "runs", "last_output_at", "TEXT NOT NULL DEFAULT ''"
            )
            cancellation_added = self._ensure_column(
                conn,
                "runs",
                "cancellation_requested_at",
                "TEXT NOT NULL DEFAULT ''",
            )
            if last_output_added or cancellation_added:
                self._backfill_progress_scalar_columns(conn)
            self._ensure_column(
                conn,
                "runs",
                "result_publication_error",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn, "runs", "public_result_json", "TEXT NOT NULL DEFAULT '{}'"
            )
            self._ensure_column(
                conn,
                "runs",
                "public_result_schema_version",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "runs",
                "public_result_source_sha256",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                conn,
                "runs",
                "public_result_status",
                "TEXT NOT NULL DEFAULT 'not_materialized'",
            )
            self._ensure_column(
                conn, "runs", "public_result_error", "TEXT NOT NULL DEFAULT ''"
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

    def get_result_source_snapshot(self, run_id: str) -> dict[str, Any]:
        """Return projection inputs including the exact authoritative JSON text."""
        validate_run_id(run_id)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, repo_name, tool, status, summary, error,
                       safety_failure, started_at, ended_at, duration_seconds,
                       exit_code, state_version, run_dir, result_json,
                       result_publication_status, result_published_hash,
                       result_published_at, result_publication_error,
                       public_result_json, public_result_schema_version,
                       public_result_source_sha256, public_result_status,
                       public_result_error
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        snapshot = dict(row)
        snapshot["safety_failure"] = bool(snapshot["safety_failure"])
        raw_result = str(snapshot["result_json"] or "{}")
        snapshot["result_json"] = raw_result
        snapshot["result"] = loads(raw_result)
        snapshot["public_result"] = loads(snapshot.pop("public_result_json"))
        return snapshot

    def get_public_result_snapshot(self, run_id: str) -> dict[str, Any]:
        """Return only the bounded public result and its scalar bindings."""
        validate_run_id(run_id)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, repo_name, tool, status, summary, error,
                       safety_failure, started_at, ended_at, duration_seconds,
                       exit_code, state_version, public_result_json,
                       public_result_schema_version, public_result_source_sha256,
                       public_result_status, public_result_error
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        snapshot = dict(row)
        snapshot["safety_failure"] = bool(snapshot["safety_failure"])
        snapshot["public_result"] = loads(snapshot.pop("public_result_json"))
        return snapshot

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

    @staticmethod
    def _compact_now(now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now override must be timezone-aware")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _scalar_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _derived_compact_values(
        cls, row: sqlite3.Row, now: datetime
    ) -> dict[str, Any]:
        started_at = cls._scalar_datetime(row["started_at"])
        ended_at = cls._scalar_datetime(row["ended_at"])
        elapsed_seconds = float(row["elapsed_seconds"] or 0.0)
        if started_at is not None:
            elapsed_end = ended_at or now
            dynamic_elapsed = max(0.0, (elapsed_end - started_at).total_seconds())
            elapsed_seconds = max(elapsed_seconds, dynamic_elapsed)

        heartbeat_age_seconds: float | None = None
        heartbeat_at = cls._scalar_datetime(row["heartbeat_at"])
        if heartbeat_at is not None:
            heartbeat_age_seconds = round(
                max(0.0, (now - heartbeat_at).total_seconds()), 3
            )
        return {
            "elapsed_seconds": round(elapsed_seconds, 3),
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "worker_stale": bool(
                row["status"] == "running"
                and heartbeat_age_seconds is not None
                and heartbeat_age_seconds > 30.0
            ),
        }

    @classmethod
    def _compact_summary_from_row(
        cls, row: sqlite3.Row, now: datetime
    ) -> dict[str, Any]:
        result = {column: row[column] for column in RUN_SUMMARY_PROJECTION_COLUMNS}
        result["requires_human"] = bool(result["requires_human"])
        result["safety_failure"] = bool(result["safety_failure"])
        result.update(cls._derived_compact_values(row, now))
        return result

    @classmethod
    def _compact_control_from_row(
        cls, row: sqlite3.Row, now: datetime
    ) -> dict[str, Any]:
        result = {
            column: row[column]
            for column in RUN_CONTROL_PROJECTION_COLUMNS
            if column != "worker_identity"
        }
        result["requires_human"] = bool(result["requires_human"])
        result["safety_failure"] = bool(result["safety_failure"])
        result["worker_identity_present"] = bool(row["worker_identity"])
        result.update(cls._derived_compact_values(row, now))
        return result

    @staticmethod
    def _normalized_summary_filters(
        repo_name: str | None, status: str | None, tool: str | None
    ) -> dict[str, str | None]:
        return {
            "repo_name": str(repo_name).lower() if repo_name else None,
            "status": str(status) if status else None,
            "tool": str(tool) if tool else None,
        }

    @staticmethod
    def _filter_identity(filters: dict[str, str | None]) -> str:
        encoded = json.dumps(
            filters, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _positive_byte_budget(byte_budget: int) -> int:
        if isinstance(byte_budget, bool) or not isinstance(byte_budget, int) or byte_budget <= 0:
            raise ValueError("byte budget must be a positive integer")
        return byte_budget

    @staticmethod
    def _encode_summary_cursor(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
        return f"{body}.{sha256(encoded).hexdigest()}"

    @classmethod
    def _decode_summary_cursor(
        cls,
        cursor: str,
        *,
        filters: dict[str, str | None],
        byte_budget: int,
        now: datetime,
    ) -> dict[str, Any]:
        if not isinstance(cursor, str) or not cursor or cursor.count(".") != 1:
            raise ValueError("Invalid run summary cursor")
        body, checksum = cursor.split(".")
        if not body or len(checksum) != 64:
            raise ValueError("Invalid run summary cursor")
        try:
            encoded = urlsafe_b64decode(body + ("=" * (-len(body) % 4)))
            canonical_body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
            if canonical_body != body:
                raise ValueError("Invalid run summary cursor")
            if sha256(encoded).hexdigest() != checksum:
                raise ValueError("Run summary cursor checksum mismatch")
            payload = json.loads(encoded.decode("utf-8"))
            canonical = json.dumps(
                payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        except ValueError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError):
            raise ValueError("Invalid run summary cursor") from None
        if canonical != encoded or not isinstance(payload, dict):
            raise ValueError("Invalid run summary cursor")
        expected_keys = {
            "operation",
            "filters",
            "filters_sha256",
            "ordering",
            "view",
            "projection_version",
            "byte_budget",
            "snapshot_watermark",
            "final_sort_key",
            "expires_at_utc",
        }
        if set(payload) != expected_keys:
            raise ValueError("Invalid run summary cursor")

        if payload.get("operation") != RUN_SUMMARY_CURSOR_OPERATION:
            raise ValueError("Run summary cursor operation mismatch")
        if payload.get("filters") != filters:
            raise ValueError("Run summary cursor filter mismatch")
        if payload.get("filters_sha256") != cls._filter_identity(filters):
            raise ValueError("Run summary cursor filter identity mismatch")
        if payload.get("ordering") != RUN_SUMMARY_ORDERING:
            raise ValueError("Run summary cursor ordering mismatch")
        if payload.get("view") != PublicView.SUMMARY.value:
            raise ValueError("Run summary cursor view mismatch")
        if payload.get("projection_version") != PUBLIC_PROJECTION_SCHEMA_VERSION:
            raise ValueError("Run summary cursor projection version mismatch")
        if payload.get("byte_budget") != byte_budget:
            raise ValueError("Run summary cursor byte budget mismatch")
        try:
            expires_at = cls._scalar_datetime(payload["expires_at_utc"])
            watermark = payload["snapshot_watermark"]
            final_sort_key = payload["final_sort_key"]
            if (
                expires_at is None
                or isinstance(watermark, bool)
                or not isinstance(watermark, int)
                or watermark < 0
                or not isinstance(final_sort_key, dict)
                or set(final_sort_key) != {"created_at", "run_id"}
                or not isinstance(final_sort_key["created_at"], str)
                or not isinstance(final_sort_key["run_id"], str)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("Invalid run summary cursor") from None
        if expires_at <= now:
            raise ValueError("Run summary cursor expired")
        return payload

    @staticmethod
    def _encode_event_cursor(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
        return f"{body}.{sha256(encoded).hexdigest()}"

    @classmethod
    def _decode_event_cursor(
        cls,
        cursor: str,
        *,
        run_id: str,
        byte_budget: int,
        now: datetime,
    ) -> dict[str, Any]:
        if not isinstance(cursor, str) or not cursor or cursor.count(".") != 1:
            raise ValueError("Invalid run event cursor")
        body, checksum = cursor.split(".")
        if not body or len(checksum) != 64:
            raise ValueError("Invalid run event cursor")
        try:
            encoded = urlsafe_b64decode(body + ("=" * (-len(body) % 4)))
            canonical_body = urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
            if canonical_body != body:
                raise ValueError("Invalid run event cursor")
            if sha256(encoded).hexdigest() != checksum:
                raise ValueError("Run event cursor checksum mismatch")
            payload = json.loads(encoded.decode("utf-8"))
            canonical = json.dumps(
                payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        except ValueError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError):
            raise ValueError("Invalid run event cursor") from None
        if canonical != encoded or not isinstance(payload, dict):
            raise ValueError("Invalid run event cursor")
        expected_keys = {
            "operation",
            "run_id",
            "after_id",
            "view",
            "projection_version",
            "byte_budget",
            "expires_at_utc",
        }
        if set(payload) != expected_keys:
            raise ValueError("Invalid run event cursor")
        if payload.get("operation") != RUN_EVENT_CURSOR_OPERATION:
            raise ValueError("Run event cursor operation mismatch")
        if payload.get("run_id") != run_id:
            raise ValueError("Run event cursor run mismatch")
        if payload.get("view") != PublicView.STANDARD.value:
            raise ValueError("Run event cursor view mismatch")
        if payload.get("projection_version") != PUBLIC_PROJECTION_SCHEMA_VERSION:
            raise ValueError("Run event cursor projection version mismatch")
        if payload.get("byte_budget") != byte_budget:
            raise ValueError("Run event cursor byte budget mismatch")
        try:
            after_id = payload["after_id"]
            expires_at = cls._scalar_datetime(payload["expires_at_utc"])
            if (
                isinstance(after_id, bool)
                or not isinstance(after_id, int)
                or after_id < 0
                or expires_at is None
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("Invalid run event cursor") from None
        if expires_at <= now:
            raise ValueError("Run event cursor expired")
        return payload

    @classmethod
    def _event_cursor_payload(
        cls,
        *,
        run_id: str,
        after_id: int,
        byte_budget: int,
        expires_at: datetime,
    ) -> dict[str, Any]:
        return {
            "operation": RUN_EVENT_CURSOR_OPERATION,
            "run_id": run_id,
            "after_id": after_id,
            "view": PublicView.STANDARD.value,
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "byte_budget": byte_budget,
            "expires_at_utc": expires_at.isoformat(),
        }

    @staticmethod
    def _summary_filter_sql(
        filters: dict[str, str | None],
    ) -> tuple[list[str], list[Any]]:
        where: list[str] = []
        params: list[Any] = []
        if filters["repo_name"] is not None:
            where.append("lower(repo_name) = ?")
            params.append(filters["repo_name"])
        if filters["status"] is not None:
            where.append("status = ?")
            params.append(filters["status"])
        if filters["tool"] is not None:
            where.append("tool = ?")
            params.append(filters["tool"])
        return where, params

    def get_run_summary(
        self, run_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        validate_run_id(run_id)
        current = self._compact_now(now)
        with self.connect() as conn:
            row = conn.execute(
                f"{RUN_SUMMARY_SELECT_SQL} WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        return self._compact_summary_from_row(row, current)

    def get_run_control_observation(
        self, run_id: str, *, now: datetime | None = None
    ) -> tuple[dict[str, Any], str]:
        """Return a scalar control snapshot plus internal worker identity."""
        validate_run_id(run_id)
        current = self._compact_now(now)
        with self.connect() as conn:
            row = conn.execute(
                f"{RUN_CONTROL_SELECT_SQL} WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        return self._compact_control_from_row(row, current), str(
            row["worker_identity"] or ""
        )

    def get_run_control_snapshot(
        self, run_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        snapshot, _worker_identity = self.get_run_control_observation(run_id, now=now)
        return snapshot

    def list_run_summaries(
        self,
        *,
        repo_name: str | None = None,
        status: str | None = None,
        tool: str | None = None,
        limit: int = RUN_SUMMARY_DEFAULT_LIMIT,
        cursor: str | None = None,
        byte_budget: int = DEFAULT_PUBLIC_BYTE_BUDGETS.run_list,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("summary limit must be an integer")
        limit = max(1, min(limit, RUN_SUMMARY_MAX_LIMIT))
        byte_budget = self._positive_byte_budget(byte_budget)
        current = self._compact_now(now)
        filters = self._normalized_summary_filters(repo_name, status, tool)
        watermark: int
        final_sort_key: dict[str, str] | None = None
        if cursor is None:
            watermark = 0
        else:
            payload = self._decode_summary_cursor(
                cursor,
                filters=filters,
                byte_budget=byte_budget,
                now=current,
            )
            watermark = int(payload["snapshot_watermark"])
            final_sort_key = payload["final_sort_key"]

        where, params = self._summary_filter_sql(filters)
        where.insert(0, "rowid <= ?")
        if cursor is not None and final_sort_key is not None:
            where.append(
                "(created_at < ? OR (created_at = ? AND run_id < ?))"
            )
            params.extend(
                [
                    final_sort_key["created_at"],
                    final_sort_key["created_at"],
                    final_sort_key["run_id"],
                ]
            )
        params.insert(0, watermark)
        params.append(limit + 1)
        sql = (
            f"{RUN_SUMMARY_SELECT_SQL} WHERE {' AND '.join(where)} "
            f"ORDER BY {RUN_SUMMARY_ORDERING} LIMIT ?"
        )
        with self.connect() as conn:
            if cursor is None:
                watermark = int(
                    conn.execute("SELECT MAX(rowid) FROM runs").fetchone()[0] or 0
                )
                params[0] = watermark
            rows = conn.execute(sql, params).fetchall()

        summaries = [self._compact_summary_from_row(row, current) for row in rows[:limit]]
        has_more = len(rows) > limit
        next_cursor: str | None = None
        if has_more:
            last = summaries[-1]
            expires_at = (
                current + timedelta(seconds=RUN_SUMMARY_CURSOR_TTL_SECONDS)
                if cursor is None
                else self._scalar_datetime(
                    self._decode_summary_cursor(
                        cursor,
                        filters=filters,
                        byte_budget=byte_budget,
                        now=current,
                    )["expires_at_utc"]
                )
            )
            assert expires_at is not None
            normalized_filters = filters
            next_cursor = self._encode_summary_cursor(
                {
                    "operation": RUN_SUMMARY_CURSOR_OPERATION,
                    "filters": normalized_filters,
                    "filters_sha256": self._filter_identity(normalized_filters),
                    "ordering": RUN_SUMMARY_ORDERING,
                    "view": PublicView.SUMMARY.value,
                    "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
                    "byte_budget": byte_budget,
                    "snapshot_watermark": watermark,
                    "final_sort_key": {
                        "created_at": str(last["created_at"]),
                        "run_id": str(last["run_id"]),
                    },
                    "expires_at_utc": expires_at.isoformat(),
                }
            )
        return {
            "runs": summaries,
            "limit": limit,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "ordering": RUN_SUMMARY_ORDERING,
            "snapshot_watermark": watermark,
            "view": PublicView.SUMMARY.value,
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "byte_budget": byte_budget,
        }

    def truncate_run_summary_page(
        self,
        page: dict[str, Any],
        returned_count: int,
        *,
        repo_name: str | None = None,
        status: str | None = None,
        tool: str | None = None,
        source_cursor: str | None = None,
        byte_budget: int = DEFAULT_PUBLIC_BYTE_BUDGETS.run_list,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if isinstance(returned_count, bool) or not isinstance(returned_count, int):
            raise ValueError("returned_count must be an integer")
        runs = page.get("runs")
        if not isinstance(runs, list) or returned_count < 1 or returned_count > len(runs):
            raise ValueError("returned_count must select a non-empty prefix of the page")
        byte_budget = self._positive_byte_budget(byte_budget)
        if page.get("view") != PublicView.SUMMARY.value:
            raise ValueError("Run summary page view mismatch")
        if page.get("projection_version") != PUBLIC_PROJECTION_SCHEMA_VERSION:
            raise ValueError("Run summary page projection version mismatch")
        if page.get("byte_budget") != byte_budget:
            raise ValueError("Run summary page byte budget mismatch")

        current = self._compact_now(now)
        filters = self._normalized_summary_filters(repo_name, status, tool)
        watermark = page.get("snapshot_watermark")
        if isinstance(watermark, bool) or not isinstance(watermark, int) or watermark < 0:
            raise ValueError("Invalid run summary page watermark")

        binding_cursor = source_cursor or page.get("next_cursor")
        if binding_cursor:
            binding = self._decode_summary_cursor(
                str(binding_cursor),
                filters=filters,
                byte_budget=byte_budget,
                now=current,
            )
            if int(binding["snapshot_watermark"]) != watermark:
                raise ValueError("Run summary page watermark mismatch")
            expires_at = self._scalar_datetime(binding["expires_at_utc"])
        else:
            expires_at = current + timedelta(seconds=RUN_SUMMARY_CURSOR_TTL_SECONDS)
        assert expires_at is not None

        selected = runs[:returned_count]
        has_more = returned_count < len(runs) or bool(page.get("has_more"))
        next_cursor: str | None = None
        if has_more:
            last = selected[-1]
            next_cursor = self._encode_summary_cursor(
                {
                    "operation": RUN_SUMMARY_CURSOR_OPERATION,
                    "filters": filters,
                    "filters_sha256": self._filter_identity(filters),
                    "ordering": RUN_SUMMARY_ORDERING,
                    "view": PublicView.SUMMARY.value,
                    "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
                    "byte_budget": byte_budget,
                    "snapshot_watermark": watermark,
                    "final_sort_key": {
                        "created_at": str(last["created_at"]),
                        "run_id": str(last["run_id"]),
                    },
                    "expires_at_utc": expires_at.isoformat(),
                }
            )

        resized = dict(page)
        resized.update(
            {
                "runs": selected,
                "limit": returned_count,
                "has_more": has_more,
                "next_cursor": next_cursor,
            }
        )
        return resized

    @staticmethod
    def _normalize_update_values(fields: dict[str, Any]) -> dict[str, Any]:
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
        if "public_result_json" in normalized and not isinstance(
            normalized["public_result_json"], str
        ):
            normalized["public_result_json"] = dumps(normalized["public_result_json"])
        if "progress_json" in normalized and not isinstance(
            normalized["progress_json"], str
        ):
            progress_value = normalized["progress_json"]
            if isinstance(progress_value, dict):
                for column in ("last_output_at", "cancellation_requested_at"):
                    if column in progress_value and column not in normalized:
                        normalized[column] = str(progress_value.get(column) or "")[:128]
            normalized["progress_json"] = dumps(progress_value)
        for column in ("last_output_at", "cancellation_requested_at"):
            if column in normalized:
                normalized[column] = str(normalized[column] or "")[:128]
        if "result_publication_status" in normalized:
            normalized["result_publication_status"] = str(
                normalized["result_publication_status"]
            )[:32]
        if "result_published_hash" in normalized:
            normalized["result_published_hash"] = str(
                normalized["result_published_hash"]
            )[:128]
        if "result_publication_error" in normalized:
            normalized["result_publication_error"] = str(
                normalized["result_publication_error"]
            )[:2000]
        for column, maximum in (
            ("public_result_schema_version", 128),
            ("public_result_source_sha256", 128),
            ("public_result_status", 32),
            ("public_result_error", 2000),
        ):
            if column in normalized:
                normalized[column] = str(normalized[column] or "")[:maximum]
        return normalized

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        validate_run_id(run_id)
        if not fields:
            return self.get_run(run_id)
        normalized = self._normalize_update_values(fields)
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = [*normalized.values(), run_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE runs SET {assignments} WHERE run_id = ?", params)
        return self.get_run(run_id)

    def conditional_update(
        self,
        run_id: str,
        *,
        fields: dict[str, Any],
        expected_statuses: list[str] | tuple[str, ...] | set[str] | None = None,
        expected_state_version: int | None = None,
        expected_lease_token: str | None = None,
        expected_lease_generation: int | None = None,
        expected_heartbeat_at: Any = _UNSET,
        reject_terminal: bool = False,
        bump_state_version: bool = True,
        bump_state_version_if_phase_changes: bool = False,
    ) -> dict[str, Any] | None:
        """Apply one ownership-sensitive update only when all observed state matches."""
        validate_run_id(run_id)
        unknown = set(fields) - _CONDITIONAL_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported conditional run fields: {sorted(unknown)}")
        normalized = self._normalize_update_values(fields)
        if bump_state_version and bump_state_version_if_phase_changes:
            raise ValueError("State version bump modes are mutually exclusive")
        if not normalized and not (
            bump_state_version or bump_state_version_if_phase_changes
        ):
            raise ValueError("Conditional update requires fields or a version bump")

        assignments = [f"{key} = ?" for key in normalized]
        params: list[Any] = list(normalized.values())
        if bump_state_version:
            assignments.append("state_version = state_version + 1")
        elif bump_state_version_if_phase_changes:
            if "current_phase" not in normalized:
                raise ValueError(
                    "Phase-sensitive state version bump requires current_phase"
                )
            assignments.append(
                "state_version = state_version + "
                "CASE WHEN current_phase IS NOT ? THEN 1 ELSE 0 END"
            )
            params.append(normalized["current_phase"])

        where = ["run_id = ?"]
        params.append(run_id)
        if expected_statuses is not None:
            statuses = tuple(str(status) for status in expected_statuses)
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
            terminal = tuple(sorted(TERMINAL_STATUSES))
            where.append("status NOT IN (" + ", ".join("?" for _ in terminal) + ")")
            params.extend(terminal)

        with self.connect() as conn:
            cursor = conn.execute(
                f"UPDATE runs SET {', '.join(assignments)} WHERE {' AND '.join(where)}",
                params,
            )
        if int(cursor.rowcount) != 1:
            return None
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
        update_run_metadata: bool = True,
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
        if update_run_metadata:
            updated = self.conditional_update(
                run_id,
                fields={
                    "heartbeat_at": event["timestamp"],
                    "current_phase": stage,
                },
                bump_state_version=False,
                bump_state_version_if_phase_changes=True,
            )
            if updated is None:
                raise KeyError(f"Run not found: {run_id}")
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

    def get_event_page(
        self,
        run_id: str,
        *,
        limit: int = RUN_EVENT_DEFAULT_LIMIT,
        after_id: int | None = None,
        cursor: str | None = None,
        byte_budget: int = DEFAULT_PUBLIC_BYTE_BUDGETS.events,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        validate_run_id(run_id)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("event limit must be an integer")
        limit = max(1, min(limit, RUN_EVENT_MAX_LIMIT))
        byte_budget = self._positive_byte_budget(byte_budget)
        if cursor and after_id is not None:
            raise ValueError("Run event cursor cannot be combined with after_id")
        current = self._compact_now(now)
        effective_after_id: int | None
        if cursor:
            binding = self._decode_event_cursor(
                cursor,
                run_id=run_id,
                byte_budget=byte_budget,
                now=current,
            )
            effective_after_id = int(binding["after_id"])
            expires_at = self._scalar_datetime(binding["expires_at_utc"])
        else:
            if isinstance(after_id, bool):
                raise ValueError("after_id must be a non-negative integer")
            effective_after_id = None if after_id is None else max(0, int(after_id))
            expires_at = current + timedelta(seconds=RUN_EVENT_CURSOR_TTL_SECONDS)
        assert expires_at is not None

        with self.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone() is None:
                raise KeyError(f"Run not found: {run_id}")
            bounds = conn.execute(
                "SELECT MIN(id), MAX(id) FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()
            earliest_event_id = int(bounds[0]) if bounds and bounds[0] is not None else None
            latest_event_id = int(bounds[1]) if bounds and bounds[1] is not None else None

            if effective_after_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM events WHERE run_id = ? ORDER BY id DESC LIMIT ?
                    ) ORDER BY id ASC
                    """,
                    (run_id, limit),
                ).fetchall()
                has_more = False
            else:
                if effective_after_id > 0:
                    anchor = conn.execute(
                        "SELECT 1 FROM events WHERE run_id = ? AND id = ?",
                        (run_id, effective_after_id),
                    ).fetchone()
                    if anchor is None:
                        if latest_event_id is None or effective_after_id > latest_event_id:
                            raise ValueError("Run event cursor ahead of latest event")
                        raise ValueError(
                            "Run event cursor gap: anchor event is unavailable"
                        )
                rows = conn.execute(
                    """
                    SELECT * FROM events
                    WHERE run_id = ? AND id > ?
                    ORDER BY id ASC LIMIT ?
                    """,
                    (run_id, effective_after_id, limit + 1),
                ).fetchall()
                has_more = len(rows) > limit
                rows = rows[:limit]

        events = [self._row_to_event(row) for row in rows]
        if events:
            next_after_id = int(events[-1]["id"])
        elif effective_after_id is not None:
            next_after_id = effective_after_id
        else:
            next_after_id = latest_event_id or 0
        next_cursor = self._encode_event_cursor(
            self._event_cursor_payload(
                run_id=run_id,
                after_id=next_after_id,
                byte_budget=byte_budget,
                expires_at=expires_at,
            )
        )
        return {
            "events": events,
            "limit": limit,
            "has_more": has_more,
            "next_after_id": next_after_id,
            "next_cursor": next_cursor,
            "ordering": "id ASC",
            "effective_after_id": effective_after_id,
            "earliest_event_id": earliest_event_id,
            "latest_event_id": latest_event_id,
            "cursor_expires_at_utc": expires_at.isoformat(),
            "view": PublicView.STANDARD.value,
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "byte_budget": byte_budget,
        }

    def truncate_event_page(
        self,
        page: dict[str, Any],
        returned_count: int,
    ) -> dict[str, Any]:
        events = page.get("events")
        if (
            not isinstance(events, list)
            or isinstance(returned_count, bool)
            or not isinstance(returned_count, int)
            or returned_count < 1
            or returned_count > len(events)
        ):
            raise ValueError("returned_count must select a non-empty event prefix")
        if page.get("view") != PublicView.STANDARD.value:
            raise ValueError("Run event page view mismatch")
        if page.get("projection_version") != PUBLIC_PROJECTION_SCHEMA_VERSION:
            raise ValueError("Run event page projection version mismatch")
        byte_budget = self._positive_byte_budget(page.get("byte_budget"))
        expires_at = self._scalar_datetime(page.get("cursor_expires_at_utc"))
        if expires_at is None:
            raise ValueError("Invalid run event page expiry")

        selected = events[:returned_count]
        next_after_id = int(selected[-1]["id"])
        resized = dict(page)
        resized.update(
            {
                "events": selected,
                "limit": returned_count,
                "has_more": returned_count < len(events) or bool(page.get("has_more")),
                "next_after_id": next_after_id,
                "next_cursor": self._encode_event_cursor(
                    self._event_cursor_payload(
                        run_id=str(selected[-1]["run_id"]),
                        after_id=next_after_id,
                        byte_budget=byte_budget,
                        expires_at=expires_at,
                    )
                ),
            }
        )
        return resized

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

    def list_terminal_runs(self) -> list[dict[str, Any]]:
        statuses = tuple(sorted(TERMINAL_STATUSES))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE status IN ("
                + ", ".join("?" for _ in statuses)
                + ") ORDER BY created_at ASC",
                statuses,
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def record_worker_launch(
        self,
        run_id: str,
        launcher_pid: int,
        *,
        expected_state_version: int | None = None,
        expected_lease_token: str | None = None,
        expected_lease_generation: int | None = None,
        increment_attempt: bool = True,
    ) -> dict[str, Any] | None:
        current = self.get_run(run_id)
        version = (
            int(current["state_version"])
            if expected_state_version is None
            else int(expected_state_version)
        )
        lease_token = (
            str(current["worker_lease_token"])
            if expected_lease_token is None
            else expected_lease_token
        )
        generation = (
            int(current["lease_generation"])
            if expected_lease_generation is None
            else int(expected_lease_generation)
        )
        fields: dict[str, Any] = {
            "status": "queued",
            "current_phase": "queued",
            "launcher_pid": int(launcher_pid),
            "heartbeat_at": utc_now(),
            "recovery_reason": "",
        }
        if increment_attempt:
            fields["launch_attempts"] = int(current.get("launch_attempts") or 0) + 1
        return self.conditional_update(
            run_id,
            fields=fields,
            expected_statuses=("launch_pending",),
            expected_state_version=version,
            expected_lease_token=lease_token,
            expected_lease_generation=generation,
            reject_terminal=True,
        )

    def claim_worker(
        self,
        run_id: str,
        *,
        lease_token: str,
        worker_pid: int,
        worker_identity: str,
        lease_generation: int | None = None,
        expected_state_version: int | None = None,
    ) -> bool:
        current = self.get_run(run_id)
        generation = (
            int(current["lease_generation"])
            if lease_generation is None
            else int(lease_generation)
        )
        version = (
            int(current["state_version"])
            if expected_state_version is None
            else int(expected_state_version)
        )
        now = utc_now()
        updated = self.conditional_update(
            run_id,
            fields={
                "status": "running",
                "current_phase": "worker",
                "worker_pid": int(worker_pid),
                "worker_identity": worker_identity,
                "worker_claimed_at": now,
                "started_at": current.get("started_at") or now,
                "heartbeat_at": now,
                "recovery_reason": "",
            },
            expected_statuses=("launch_pending", "queued"),
            expected_state_version=version,
            expected_lease_token=lease_token,
            expected_lease_generation=generation,
            reject_terminal=True,
        )
        return updated is not None

    def update_worker_progress(
        self,
        run_id: str,
        *,
        lease_token: str,
        lease_generation: int,
        phase: str,
        elapsed_seconds: float,
        progress: dict[str, Any] | None = None,
    ) -> bool:
        return (
            self.conditional_update(
                run_id,
                fields={
                    "current_phase": phase,
                    "heartbeat_at": utc_now(),
                    "elapsed_seconds": elapsed_seconds,
                    "progress_json": progress or {},
                },
                expected_statuses=("running",),
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
                bump_state_version=False,
                bump_state_version_if_phase_changes=True,
            )
            is not None
        )

    def heartbeat_worker(
        self,
        run_id: str,
        *,
        lease_token: str,
        elapsed_seconds: float,
        progress_updates: dict[str, Any] | None = None,
        lease_generation: int | None = None,
    ) -> bool:
        current = self.get_run(run_id)
        generation = (
            int(current["lease_generation"])
            if lease_generation is None
            else int(lease_generation)
        )
        progress = dict(current.get("progress") or {})
        progress.update(progress_updates or {})
        updated = self.conditional_update(
            run_id,
            fields={
                "heartbeat_at": utc_now(),
                "elapsed_seconds": elapsed_seconds,
                "progress_json": progress,
            },
            expected_statuses=("running",),
            expected_lease_token=lease_token,
            expected_lease_generation=generation,
            bump_state_version=False,
        )
        return updated is not None

    def attach_child_pid(
        self,
        run_id: str,
        *,
        child_pid: int,
        lease_token: str,
        lease_generation: int,
    ) -> bool:
        return (
            self.conditional_update(
                run_id,
                fields={"pid": int(child_pid), "heartbeat_at": utc_now()},
                expected_statuses=("running",),
                expected_lease_token=lease_token,
                expected_lease_generation=lease_generation,
            )
            is not None
        )

    def adopt_worker(
        self,
        run_id: str,
        *,
        expected_state_version: int,
        lease_token: str,
        lease_generation: int,
        expected_heartbeat_at: str | None,
    ) -> dict[str, Any] | None:
        return self.conditional_update(
            run_id,
            fields={
                "current_phase": "worker",
                "heartbeat_at": utc_now(),
                "recovery_reason": "",
            },
            expected_statuses=("running",),
            expected_state_version=expected_state_version,
            expected_lease_token=lease_token,
            expected_lease_generation=lease_generation,
            expected_heartbeat_at=expected_heartbeat_at,
            reject_terminal=True,
        )

    def mark_recovery_pending(
        self,
        run_id: str,
        reason: str,
        *,
        expected_statuses: tuple[str, ...] | list[str] | set[str] | None = None,
        expected_state_version: int | None = None,
        expected_lease_token: str | None = None,
        expected_lease_generation: int | None = None,
        expected_heartbeat_at: Any = _UNSET,
    ) -> dict[str, Any] | None:
        current = self.get_run(run_id)
        statuses = expected_statuses or (str(current["status"]),)
        version = (
            int(current["state_version"])
            if expected_state_version is None
            else int(expected_state_version)
        )
        return self.conditional_update(
            run_id,
            fields={
                "status": "recovery_pending",
                "current_phase": "recovery_pending",
                "recovery_reason": reason,
                "error": reason,
                "ended_at": None,
            },
            expected_statuses=statuses,
            expected_state_version=version,
            expected_lease_token=expected_lease_token,
            expected_lease_generation=expected_lease_generation,
            expected_heartbeat_at=expected_heartbeat_at,
            reject_terminal=True,
        )

    def transition_terminal(
        self,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any],
        expected_statuses: tuple[str, ...] | list[str] | set[str],
        expected_state_version: int,
        expected_lease_token: str | None = None,
        expected_lease_generation: int | None = None,
        expected_heartbeat_at: Any = _UNSET,
        ended_at: str | None = None,
        duration_seconds: float | None = None,
        exit_code: int | None = None,
        summary: str = "",
        error: str = "",
        safety_failure: bool = False,
        recovery_reason: str = "",
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"Not a terminal run status: {status}")
        terminal_at = ended_at or utc_now()
        fields: dict[str, Any] = {
            "status": status,
            "current_phase": "result",
            "ended_at": terminal_at,
            "duration_seconds": duration_seconds,
            "exit_code": exit_code,
            "summary": summary,
            "error": error,
            "safety_failure": safety_failure,
            "result_json": result,
            "result_publication_status": "pending",
            "result_published_hash": "",
            "result_published_at": None,
            "result_publication_error": "",
            "public_result_json": {},
            "public_result_schema_version": "",
            "public_result_source_sha256": "",
            "public_result_status": PUBLIC_RESULT_STATUS_NOT_MATERIALIZED,
            "public_result_error": "",
            "recovery_reason": recovery_reason,
        }
        if progress is not None:
            fields["progress_json"] = progress
        return self.conditional_update(
            run_id,
            fields=fields,
            expected_statuses=expected_statuses,
            expected_state_version=expected_state_version,
            expected_lease_token=expected_lease_token,
            expected_lease_generation=expected_lease_generation,
            expected_heartbeat_at=expected_heartbeat_at,
            reject_terminal=True,
        )

    def record_result_publication(
        self,
        run_id: str,
        *,
        status: str,
        published_hash: str = "",
        published_at: str | None = None,
        error: str = "",
        expected_state_version: int,
    ) -> dict[str, Any] | None:
        if status not in {"published", "failed", "pending"}:
            raise ValueError(f"Invalid result publication status: {status}")
        return self.conditional_update(
            run_id,
            fields={
                "result_publication_status": status,
                "result_published_hash": published_hash,
                "result_published_at": published_at,
                "result_publication_error": error,
            },
            expected_statuses=tuple(sorted(TERMINAL_STATUSES)),
            expected_state_version=expected_state_version,
        )

    def record_result_publication_with_projection(
        self,
        run_id: str,
        *,
        status: str,
        published_hash: str = "",
        published_at: str | None = None,
        error: str = "",
        public_result: dict[str, Any],
        public_result_source_sha256: str,
        public_result_status: str,
        public_result_error: str = "",
        expected_state_version: int,
    ) -> dict[str, Any] | None:
        if status not in {"published", "failed", "pending"}:
            raise ValueError(f"Invalid result publication status: {status}")
        if public_result_status not in PUBLIC_RESULT_STATUSES:
            raise ValueError(f"Invalid public result status: {public_result_status}")
        return self.conditional_update(
            run_id,
            fields={
                "result_publication_status": status,
                "result_published_hash": published_hash,
                "result_published_at": published_at,
                "result_publication_error": error,
                "public_result_json": public_result,
                "public_result_schema_version": PUBLIC_RESULT_SCHEMA_VERSION,
                "public_result_source_sha256": public_result_source_sha256,
                "public_result_status": public_result_status,
                "public_result_error": public_result_error,
            },
            expected_statuses=tuple(sorted(TERMINAL_STATUSES)),
            expected_state_version=expected_state_version,
        )

    def record_public_result(
        self,
        run_id: str,
        *,
        public_result: dict[str, Any],
        source_sha256: str,
        status: str,
        error: str = "",
        expected_state_version: int,
    ) -> dict[str, Any] | None:
        if status not in PUBLIC_RESULT_STATUSES:
            raise ValueError(f"Invalid public result status: {status}")
        return self.conditional_update(
            run_id,
            fields={
                "public_result_json": public_result,
                "public_result_schema_version": PUBLIC_RESULT_SCHEMA_VERSION,
                "public_result_source_sha256": source_sha256,
                "public_result_status": status,
                "public_result_error": error,
            },
            expected_statuses=tuple(sorted(TERMINAL_STATUSES)),
            expected_state_version=expected_state_version,
        )

    def fail_infrastructure(
        self,
        run_id: str,
        reason: str,
        *,
        expected_statuses: tuple[str, ...] | list[str] | set[str] | None = None,
        expected_state_version: int | None = None,
        expected_lease_token: str | None = None,
        expected_lease_generation: int | None = None,
        expected_heartbeat_at: Any = _UNSET,
    ) -> dict[str, Any] | None:
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
        return self.transition_terminal(
            run_id,
            status="failed",
            result=result,
            expected_statuses=expected_statuses or (str(run["status"]),),
            expected_state_version=(
                int(run["state_version"])
                if expected_state_version is None
                else int(expected_state_version)
            ),
            expected_lease_token=expected_lease_token,
            expected_lease_generation=expected_lease_generation,
            expected_heartbeat_at=expected_heartbeat_at,
            ended_at=ended_at,
            duration_seconds=run.get("duration_seconds"),
            exit_code=None,
            summary=reason,
            error=reason,
            recovery_reason=reason,
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
        updated = self.conditional_update(
            run_id,
            fields=fields,
            bump_state_version=False,
            bump_state_version_if_phase_changes=True,
        )
        if updated is None:
            raise KeyError(f"Run not found: {run_id}")
        return updated

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
    ) -> bool:
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in existing:
            return False
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True

    @staticmethod
    def _backfill_progress_scalar_columns(conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT run_id, progress_json, last_output_at, cancellation_requested_at
            FROM runs
            WHERE progress_json NOT IN ('', '{}')
              AND (last_output_at = '' OR cancellation_requested_at = '')
            """
        ).fetchall()
        for row in rows:
            try:
                progress = json.loads(str(row["progress_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(progress, dict):
                continue
            updates: dict[str, str] = {}
            for column in ("last_output_at", "cancellation_requested_at"):
                value = progress.get(column)
                if not row[column] and isinstance(value, str) and value:
                    updates[column] = value[:128]
            if not updates:
                continue
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(
                f"UPDATE runs SET {assignments} WHERE run_id = ?",
                (*updates.values(), row["run_id"]),
            )

    def _row_to_run(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["requires_human"] = bool(result["requires_human"])
        result["safety_failure"] = bool(result["safety_failure"])
        result["input"] = loads(result.pop("input_json"))
        result["progress"] = loads(result.pop("progress_json"))
        result["result"] = loads(result.pop("result_json"))
        result["public_result"] = loads(result.pop("public_result_json"))

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
