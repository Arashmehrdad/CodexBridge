from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .process_control import process_is_running, process_matches_identity
from .run_store import TERMINAL_STATUSES, RunStore, utc_now


@dataclass(frozen=True)
class LockAcquisition:
    acquired: bool
    duplicate: bool
    repo_name: str
    lock_key: str
    reason: str = ""
    fingerprint: str = ""


def normalize_input_fingerprint(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class OperationLockStore:
    def __init__(self, runs_dir: Path):
        self.store = RunStore(runs_dir)
        self.store.init_db()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_locks (
                    repo_name TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    owner_pid INTEGER,
                    owner_token TEXT NOT NULL DEFAULT '',
                    lease_generation INTEGER NOT NULL DEFAULT 1,
                    acquired_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL
                )
                """
            )
            self.store._ensure_column(
                conn,
                "operation_locks",
                "owner_token",
                "TEXT NOT NULL DEFAULT ''",
            )
            self.store._ensure_column(
                conn,
                "operation_locks",
                "lease_generation",
                "INTEGER NOT NULL DEFAULT 1",
            )

    def acquire(
        self,
        *,
        repo_name: str,
        tool: str,
        normalized_input: dict[str, Any],
        run_id: str,
        owner_pid: int | None = None,
        owner_token: str = "",
        lease_generation: int = 1,
    ) -> LockAcquisition:
        fingerprint = normalize_input_fingerprint(normalized_input)
        now = utc_now()
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM operation_locks WHERE repo_name = ?",
                (repo_name,),
            ).fetchone()
            if row is not None:
                existing = dict(row)
                if self._is_stale(conn, existing):
                    conn.execute(
                        "DELETE FROM operation_locks WHERE repo_name = ?",
                        (repo_name,),
                    )
                else:
                    duplicate = (
                        existing["tool"] == tool
                        and existing["input_fingerprint"] == fingerprint
                    )
                    return LockAcquisition(
                        acquired=False,
                        duplicate=duplicate,
                        repo_name=repo_name,
                        lock_key=repo_name,
                        reason="duplicate active task"
                        if duplicate
                        else "repository busy",
                        fingerprint=fingerprint,
                    )
            conn.execute(
                """
                INSERT INTO operation_locks (
                    repo_name, tool, input_fingerprint, run_id, owner_pid,
                    owner_token, lease_generation, acquired_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_name,
                    tool,
                    fingerprint,
                    run_id,
                    owner_pid,
                    owner_token,
                    int(lease_generation),
                    now,
                    now,
                ),
            )
        return LockAcquisition(
            acquired=True,
            duplicate=False,
            repo_name=repo_name,
            lock_key=repo_name,
            fingerprint=fingerprint,
        )

    def claim_owner(
        self,
        repo_name: str,
        run_id: str,
        *,
        owner_pid: int,
        owner_token: str,
        lease_generation: int | None = None,
    ) -> bool:
        where = "repo_name = ? AND run_id = ? AND owner_token = ?"
        params: list[Any] = [owner_pid, utc_now(), repo_name, run_id, owner_token]
        if lease_generation is not None:
            where += " AND lease_generation = ?"
            params.append(int(lease_generation))
        with self.store.connect() as conn:
            cursor = conn.execute(
                f"UPDATE operation_locks SET owner_pid = ?, heartbeat_at = ? WHERE {where}",
                params,
            )
        return int(cursor.rowcount) == 1

    def heartbeat(
        self,
        repo_name: str,
        run_id: str,
        owner_token: str | None = None,
        lease_generation: int | None = None,
    ) -> bool:
        where = "repo_name = ? AND run_id = ?"
        params: list[Any] = [utc_now(), repo_name, run_id]
        if owner_token is not None:
            where += " AND owner_token = ?"
            params.append(owner_token)
        if lease_generation is not None:
            where += " AND lease_generation = ?"
            params.append(int(lease_generation))
        with self.store.connect() as conn:
            cursor = conn.execute(
                f"UPDATE operation_locks SET heartbeat_at = ? WHERE {where}",
                params,
            )
        return int(cursor.rowcount) == 1

    def release(
        self,
        repo_name: str,
        run_id: str,
        owner_token: str | None = None,
        lease_generation: int | None = None,
    ) -> bool:
        where = "repo_name = ? AND run_id = ?"
        params: list[Any] = [repo_name, run_id]
        if owner_token is not None:
            where += " AND owner_token = ?"
            params.append(owner_token)
        if lease_generation is not None:
            where += " AND lease_generation = ?"
            params.append(int(lease_generation))
        with self.store.connect() as conn:
            cursor = conn.execute(f"DELETE FROM operation_locks WHERE {where}", params)
        return int(cursor.rowcount) == 1

    def reserve_next_launch(
        self,
        *,
        repo_name: str,
        run_id: str,
        expected_statuses: tuple[str, ...] | list[str] | set[str],
        expected_state_version: int,
        expected_owner_token: str,
        expected_lease_generation: int,
        new_owner_token: str,
        owner_pid: int | None,
    ) -> dict[str, int | str] | None:
        statuses = tuple(str(status) for status in expected_statuses)
        if not statuses:
            return None
        now = utc_now()
        new_generation = int(expected_lease_generation) + 1
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            run_cursor = conn.execute(
                """
                UPDATE runs
                SET status = 'launch_pending', current_phase = 'launch_pending',
                    worker_lease_token = ?, lease_generation = ?,
                    state_version = state_version + 1,
                    launch_attempts = launch_attempts + 1,
                    launcher_pid = NULL, worker_pid = NULL,
                    worker_identity = '', worker_claimed_at = NULL, pid = NULL,
                    heartbeat_at = ?, recovery_reason = '', ended_at = NULL
                WHERE run_id = ? AND state_version = ?
                  AND worker_lease_token = ? AND lease_generation = ?
                  AND status IN ("""
                + ", ".join("?" for _ in statuses)
                + ")",
                (
                    new_owner_token,
                    new_generation,
                    now,
                    run_id,
                    int(expected_state_version),
                    expected_owner_token,
                    int(expected_lease_generation),
                    *statuses,
                ),
            )
            if int(run_cursor.rowcount) != 1:
                conn.rollback()
                return None
            lock_cursor = conn.execute(
                """
                UPDATE operation_locks
                SET owner_pid = ?, owner_token = ?, lease_generation = ?,
                    heartbeat_at = ?
                WHERE repo_name = ? AND run_id = ?
                  AND owner_token = ? AND lease_generation = ?
                """,
                (
                    owner_pid,
                    new_owner_token,
                    new_generation,
                    now,
                    repo_name,
                    run_id,
                    expected_owner_token,
                    int(expected_lease_generation),
                ),
            )
            if int(lock_cursor.rowcount) != 1:
                conn.rollback()
                return None
            row = conn.execute(
                """
                SELECT state_version, lease_generation, launch_attempts
                FROM runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "owner_token": new_owner_token,
            "lease_generation": int(row["lease_generation"]),
            "state_version": int(row["state_version"]),
            "launch_attempts": int(row["launch_attempts"]),
        }

    def list_locks(
        self,
        repo_name: str | None = None,
        *,
        include_stale: bool = True,
    ) -> list[dict[str, Any]]:
        where = ""
        params: tuple[Any, ...] = ()
        if repo_name:
            where = " WHERE lower(repo_name) = lower(?)"
            params = (repo_name,)
        now = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operation_locks" + where + " ORDER BY acquired_at",
                params,
            ).fetchall()
            for row in rows:
                lock = dict(row)
                stale = self._is_stale(conn, lock)
                if stale and not include_stale:
                    continue
                run = conn.execute(
                    """
                    SELECT status, launcher_pid, worker_pid, worker_identity, pid
                    FROM runs WHERE run_id = ?
                    """,
                    (lock["run_id"],),
                ).fetchone()
                heartbeat = datetime.fromisoformat(str(lock["heartbeat_at"]))
                results.append(
                    {
                        "repo_name": str(lock["repo_name"]),
                        "tool": str(lock["tool"]),
                        "run_id": str(lock["run_id"]),
                        "owner_pid": int(lock["owner_pid"] or 0),
                        "lease_generation": int(lock["lease_generation"] or 1),
                        "acquired_at": str(lock["acquired_at"]),
                        "heartbeat_at": str(lock["heartbeat_at"]),
                        "heartbeat_age_seconds": round(
                            max(0.0, (now - heartbeat).total_seconds()), 3
                        ),
                        "stale": stale,
                        "run_status": str(run["status"] or "") if run else "",
                        "launcher_pid": int(run["launcher_pid"] or 0) if run else 0,
                        "worker_pid": int(run["worker_pid"] or 0) if run else 0,
                        "worker_identity_present": bool(
                            run and str(run["worker_identity"] or "")
                        ),
                        "child_pid": int(run["pid"] or 0) if run else 0,
                    }
                )
        return results

    def find_lock(self, repo_name: str, run_id: str) -> dict[str, Any] | None:
        for lock in self.list_locks(repo_name, include_stale=True):
            if lock["run_id"] == run_id:
                return lock
        return None

    def recover_stale(self) -> int:
        removed = 0
        with self.store.connect() as conn:
            rows = conn.execute("SELECT * FROM operation_locks").fetchall()
            for row in rows:
                existing = dict(row)
                if self._is_stale(conn, existing):
                    cursor = conn.execute(
                        """
                        DELETE FROM operation_locks
                        WHERE repo_name = ? AND run_id = ?
                          AND owner_token = ? AND lease_generation = ?
                        """,
                        (
                            existing["repo_name"],
                            existing["run_id"],
                            existing["owner_token"],
                            int(existing.get("lease_generation") or 1),
                        ),
                    )
                    removed += int(cursor.rowcount)
        return removed

    def _is_stale(self, conn, row: dict[str, Any]) -> bool:
        run = conn.execute(
            """
            SELECT status, launcher_pid, worker_pid, worker_identity, pid
            FROM runs WHERE run_id = ?
            """,
            (row["run_id"],),
        ).fetchone()
        if run is None:
            owner_pid = row.get("owner_pid")
            return not bool(owner_pid and _pid_is_running(int(owner_pid)))

        status = str(run["status"] or "")
        worker_pid = int(run["worker_pid"] or 0)
        worker_identity = str(run["worker_identity"] or "")
        launcher_pid = int(run["launcher_pid"] or 0)
        child_pid = int(run["pid"] or 0)
        verified_worker = process_matches_identity(worker_pid, worker_identity)
        live_launcher = process_is_running(launcher_pid)
        live_child = process_is_running(child_pid)

        if status in TERMINAL_STATUSES:
            return not (verified_worker or live_launcher or live_child)
        if status in {"cancellation_pending", "recovery_pending"}:
            return False
        # Non-terminal ownership is retained until JobManager reconciliation makes
        # a process-aware recovery or terminal decision.
        return False
@contextmanager
def repository_operation_lock(
    runs_dir: Path,
    *,
    repo_name: str,
    tool: str,
    normalized_input: dict[str, Any],
) -> Iterator[str]:
    """Use the durable repository lock for synchronous mutating operations."""
    store = OperationLockStore(runs_dir)
    owner_id = f"sync_{os.getpid()}_{uuid4().hex[:12]}"
    acquisition = store.acquire(
        repo_name=repo_name,
        tool=tool,
        normalized_input=normalized_input,
        run_id=owner_id,
        owner_pid=os.getpid(),
    )
    if not acquisition.acquired:
        raise RuntimeError(
            f"Repository operation lock unavailable for {repo_name}: {acquisition.reason}"
        )
    try:
        yield owner_id
    finally:
        store.release(repo_name, owner_id)


def _pid_is_running(pid: int) -> bool:
    return process_is_running(pid)
