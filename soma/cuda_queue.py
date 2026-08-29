from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable

from .process_control import process_matches_identity

CUDA_RESOURCE_CLASS = "cuda_exclusive"
CUDA_QUEUE_DB_FILENAME = "cuda_queue.sqlite3"
CUDA_HEARTBEAT_INTERVAL_SECONDS = 2.0
CUDA_LEASE_TIMEOUT_SECONDS = 30.0
CUDA_QUEUED_STALE_SECONDS = 60.0
CUDA_RELEASE_COOLDOWN_SECONDS = 2.0
CUDA_QUEUE_POLL_SECONDS = 0.25

_TERMINAL_QUEUE_STATES = {"released", "cancelled", "abandoned"}


class CudaQueueCancelled(RuntimeError):
    pass


def _epoch(value: str | float | int | None) -> float:
    if value is None:
        return time.time()
    if isinstance(value, (float, int)):
        return float(value)
    return datetime.fromisoformat(value).timestamp()


def _request_id(run_id: str) -> str:
    return "cuda_" + sha256(run_id.encode("utf-8")).hexdigest()[:24]


class CudaQueueStore:
    """Machine-global exclusive CUDA reservation queue.

    The queue is deliberately independent of repository locks. One local
    machine has one CUDA resource ledger under the shared Soma runs directory,
    so unrelated repositories and Chats arbitrate the same physical GPU.
    """

    def __init__(self, runs_dir: str | Path) -> None:
        root = Path(runs_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / CUDA_QUEUE_DB_FILENAME
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _ensure_schema(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cuda_queue_requests (
                    request_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    repo_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    requested_at REAL NOT NULL,
                    acquired_at REAL,
                    heartbeat_at REAL NOT NULL,
                    released_at REAL,
                    owner_pid INTEGER NOT NULL DEFAULT 0,
                    owner_identity TEXT NOT NULL DEFAULT '',
                    owner_key TEXT NOT NULL DEFAULT '',
                    child_pid INTEGER NOT NULL DEFAULT 0,
                    child_identity TEXT NOT NULL DEFAULT '',
                    lease_generation INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_cuda_queue_fifo
                    ON cuda_queue_requests(state, requested_at, request_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_cuda_queue_one_active
                    ON cuda_queue_requests(state) WHERE state = 'active';
                CREATE TABLE IF NOT EXISTS cuda_queue_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    cooldown_until REAL NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO cuda_queue_state(singleton, cooldown_until)
                    VALUES (1, 0);
                """
            )
        finally:
            connection.close()

    def enqueue(
        self,
        run_id: str,
        repo_name: str,
        *,
        requested_at: str | float | int | None = None,
        now: float | None = None,
    ) -> dict[str, object]:
        current = time.time() if now is None else float(now)
        request_time = _epoch(requested_at)
        request_id = _request_id(run_id)
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO cuda_queue_requests(
                    request_id, run_id, repo_name, state, requested_at, heartbeat_at
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (request_id, run_id, repo_name, request_time, current),
            )
            row = connection.execute(
                "SELECT * FROM cuda_queue_requests WHERE run_id = ?", (run_id,)
            ).fetchone()
            connection.commit()
            if row is None:
                raise RuntimeError("CUDA queue failed to persist request")
            return self._public_row(row, current)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _recover_stale_in_connection(
        self, connection: sqlite3.Connection, now: float
    ) -> int:
        recovered = 0
        active = connection.execute(
            "SELECT * FROM cuda_queue_requests WHERE state = 'active'"
        ).fetchone()
        if active is not None:
            heartbeat = float(active["heartbeat_at"] or 0.0)
            worker_identity_matches = process_matches_identity(
                int(active["owner_pid"] or 0), str(active["owner_identity"] or "")
            )
            child_pid = int(active["child_pid"] or 0)
            child_identity_matches = child_pid > 0 and process_matches_identity(
                child_pid, str(active["child_identity"] or "")
            )
            if (
                now - heartbeat > CUDA_LEASE_TIMEOUT_SECONDS
                and not worker_identity_matches
                and not child_identity_matches
            ):
                connection.execute(
                    """
                    UPDATE cuda_queue_requests
                    SET state = 'abandoned', released_at = ?, reason = ?
                    WHERE request_id = ? AND state = 'active'
                    """,
                    (now, "active_owner_stale", active["request_id"]),
                )
                connection.execute(
                    "UPDATE cuda_queue_state SET cooldown_until = MAX(cooldown_until, ?) WHERE singleton = 1",
                    (now + CUDA_RELEASE_COOLDOWN_SECONDS,),
                )
                recovered += 1

        stale_before = now - CUDA_QUEUED_STALE_SECONDS
        queued = connection.execute(
            """
            SELECT * FROM cuda_queue_requests
            WHERE state = 'queued' AND heartbeat_at < ?
            """,
            (stale_before,),
        ).fetchall()
        for row in queued:
            owner_pid = int(row["owner_pid"] or 0)
            owner_identity = str(row["owner_identity"] or "")
            if owner_pid > 0 and process_matches_identity(owner_pid, owner_identity):
                continue
            connection.execute(
                """
                UPDATE cuda_queue_requests
                SET state = 'abandoned', released_at = ?, reason = ?
                WHERE request_id = ? AND state = 'queued'
                """,
                (now, "queued_owner_stale", row["request_id"]),
            )
            recovered += 1
        return recovered

    def recover_stale(self, *, now: float | None = None) -> int:
        current = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            recovered = self._recover_stale_in_connection(connection, current)
            connection.commit()
            return recovered
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def try_acquire(
        self,
        run_id: str,
        *,
        repo_name: str,
        owner_pid: int,
        owner_identity: str,
        owner_key: str,
        requested_at: str | float | int | None = None,
        now: float | None = None,
    ) -> dict[str, object]:
        current = time.time() if now is None else float(now)
        self.enqueue(
            run_id,
            repo_name,
            requested_at=requested_at,
            now=current,
        )
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE cuda_queue_requests
                SET heartbeat_at = ?, owner_pid = ?, owner_identity = ?, owner_key = ?
                WHERE run_id = ? AND state = 'queued'
                """,
                (current, owner_pid, owner_identity, owner_key, run_id),
            )
            self._recover_stale_in_connection(connection, current)
            row = connection.execute(
                "SELECT * FROM cuda_queue_requests WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError("CUDA queue request disappeared")
            if str(row["state"]) == "active":
                if str(row["owner_key"] or "") != owner_key:
                    raise RuntimeError("CUDA reservation is owned by another worker lease")
                connection.execute(
                    "UPDATE cuda_queue_requests SET heartbeat_at = ? WHERE request_id = ?",
                    (current, row["request_id"]),
                )
                refreshed = connection.execute(
                    "SELECT * FROM cuda_queue_requests WHERE request_id = ?",
                    (row["request_id"],),
                ).fetchone()
                connection.commit()
                return self._public_row(refreshed, current)
            if str(row["state"]) in _TERMINAL_QUEUE_STATES:
                connection.commit()
                return self._public_row(row, current)

            active = connection.execute(
                "SELECT request_id FROM cuda_queue_requests WHERE state = 'active'"
            ).fetchone()
            cooldown = float(
                connection.execute(
                    "SELECT cooldown_until FROM cuda_queue_state WHERE singleton = 1"
                ).fetchone()[0]
            )
            first = connection.execute(
                """
                SELECT request_id FROM cuda_queue_requests
                WHERE state = 'queued'
                ORDER BY requested_at, request_id LIMIT 1
                """
            ).fetchone()
            if active is None and cooldown <= current and first is not None and first[0] == row["request_id"]:
                connection.execute(
                    """
                    UPDATE cuda_queue_requests
                    SET state = 'active', acquired_at = ?, heartbeat_at = ?,
                        owner_pid = ?, owner_identity = ?, owner_key = ?,
                        lease_generation = lease_generation + 1, reason = ''
                    WHERE request_id = ? AND state = 'queued'
                    """,
                    (
                        current,
                        current,
                        owner_pid,
                        owner_identity,
                        owner_key,
                        row["request_id"],
                    ),
                )
            refreshed = connection.execute(
                "SELECT * FROM cuda_queue_requests WHERE request_id = ?",
                (row["request_id"],),
            ).fetchone()
            connection.commit()
            return self._public_row(refreshed, current, cooldown_until=cooldown)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat(
        self,
        run_id: str,
        *,
        owner_key: str,
        lease_generation: int,
        now: float | None = None,
    ) -> bool:
        current = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            cursor = connection.execute(
                """
                UPDATE cuda_queue_requests SET heartbeat_at = ?
                WHERE run_id = ? AND state = 'active' AND owner_key = ?
                  AND lease_generation = ?
                """,
                (current, run_id, owner_key, int(lease_generation)),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def bind_child(
        self,
        run_id: str,
        *,
        owner_key: str,
        lease_generation: int,
        child_pid: int,
        child_identity: str,
        now: float | None = None,
    ) -> bool:
        if int(child_pid) <= 0 or not str(child_identity):
            raise ValueError("CUDA child binding requires canonical process identity")
        current = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            cursor = connection.execute(
                """
                UPDATE cuda_queue_requests
                SET child_pid = ?, child_identity = ?, heartbeat_at = ?
                WHERE run_id = ? AND state = 'active' AND owner_key = ?
                  AND lease_generation = ?
                """,
                (
                    int(child_pid),
                    str(child_identity),
                    current,
                    run_id,
                    owner_key,
                    int(lease_generation),
                ),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def cancel_waiting(self, run_id: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            cursor = connection.execute(
                """
                UPDATE cuda_queue_requests
                SET state = 'cancelled', released_at = ?, reason = 'cancelled_before_acquire'
                WHERE run_id = ? AND state = 'queued'
                """,
                (current, run_id),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def release(
        self,
        run_id: str,
        *,
        owner_key: str,
        lease_generation: int,
        now: float | None = None,
    ) -> bool:
        current = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cuda_queue_requests WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                connection.commit()
                return False
            if str(row["state"]) == "released":
                connection.commit()
                return (
                    str(row["owner_key"] or "") == owner_key
                    and int(row["lease_generation"] or 0) == int(lease_generation)
                )
            if (
                str(row["state"]) != "active"
                or str(row["owner_key"] or "") != owner_key
                or int(row["lease_generation"] or 0) != int(lease_generation)
            ):
                connection.commit()
                return False
            connection.execute(
                """
                UPDATE cuda_queue_requests
                SET state = 'released', released_at = ?, heartbeat_at = ?, reason = ''
                WHERE request_id = ?
                """,
                (current, current, row["request_id"]),
            )
            connection.execute(
                "UPDATE cuda_queue_state SET cooldown_until = MAX(cooldown_until, ?) WHERE singleton = 1",
                (current + CUDA_RELEASE_COOLDOWN_SECONDS,),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def wait_for_turn(
        self,
        run_id: str,
        *,
        repo_name: str,
        owner_pid: int,
        owner_identity: str,
        owner_key: str,
        requested_at: str | float | int | None,
        cancelled: Callable[[], bool],
    ) -> dict[str, object]:
        while True:
            if cancelled():
                self.cancel_waiting(run_id)
                raise CudaQueueCancelled("CUDA reservation wait cancelled before process launch")
            status = self.try_acquire(
                run_id,
                repo_name=repo_name,
                owner_pid=owner_pid,
                owner_identity=owner_identity,
                owner_key=owner_key,
                requested_at=requested_at,
            )
            if status["state"] == "active":
                return status
            if status["state"] in _TERMINAL_QUEUE_STATES:
                raise CudaQueueCancelled(
                    f"CUDA reservation became {status['state']} before process launch"
                )
            time.sleep(CUDA_QUEUE_POLL_SECONDS)

    def snapshot(self, *, limit: int = 50, now: float | None = None) -> dict[str, object]:
        current = time.time() if now is None else float(now)
        bounded_limit = max(1, min(int(limit), 200))
        connection = self.connect()
        try:
            active = connection.execute(
                "SELECT * FROM cuda_queue_requests WHERE state = 'active'"
            ).fetchone()
            queued = connection.execute(
                """
                SELECT * FROM cuda_queue_requests WHERE state = 'queued'
                ORDER BY requested_at, request_id LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
            total_queued = int(
                connection.execute(
                    "SELECT COUNT(*) FROM cuda_queue_requests WHERE state = 'queued'"
                ).fetchone()[0]
            )
            cooldown_until = float(
                connection.execute(
                    "SELECT cooldown_until FROM cuda_queue_state WHERE singleton = 1"
                ).fetchone()[0]
            )
            return {
                "ok": True,
                "resource": "cuda",
                "mode": "exclusive_fifo",
                "active": self._public_row(active, current) if active is not None else None,
                "queued": [self._public_row(row, current) for row in queued],
                "queued_count": total_queued,
                "cooldown_remaining_seconds": max(0.0, cooldown_until - current),
                "lease_timeout_seconds": CUDA_LEASE_TIMEOUT_SECONDS,
                "heartbeat_interval_seconds": CUDA_HEARTBEAT_INTERVAL_SECONDS,
                "release_cooldown_seconds": CUDA_RELEASE_COOLDOWN_SECONDS,
            }
        finally:
            connection.close()

    def _public_row(
        self,
        row: sqlite3.Row | None,
        now: float,
        *,
        cooldown_until: float = 0.0,
    ) -> dict[str, object]:
        if row is None:
            return {}
        position = 0
        if str(row["state"]) == "queued":
            connection = self.connect()
            try:
                position = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM cuda_queue_requests
                        WHERE state = 'queued'
                          AND (requested_at < ? OR (requested_at = ? AND request_id <= ?))
                        """,
                        (row["requested_at"], row["requested_at"], row["request_id"]),
                    ).fetchone()[0]
                )
            finally:
                connection.close()
        heartbeat = float(row["heartbeat_at"] or 0.0)
        return {
            "request_id": str(row["request_id"]),
            "run_id": str(row["run_id"]),
            "repo_name": str(row["repo_name"]),
            "state": str(row["state"]),
            "queue_position": position,
            "requested_at_epoch": float(row["requested_at"]),
            "acquired_at_epoch": (
                None if row["acquired_at"] is None else float(row["acquired_at"])
            ),
            "heartbeat_age_seconds": max(0.0, now - heartbeat),
            "owner_pid": int(row["owner_pid"] or 0),
            "owner_identity_present": bool(str(row["owner_identity"] or "")),
            "child_pid": int(row["child_pid"] or 0),
            "child_identity_present": bool(str(row["child_identity"] or "")),
            "lease_generation": int(row["lease_generation"] or 0),
            "reason": str(row["reason"] or ""),
            "cooldown_remaining_seconds": max(0.0, cooldown_until - now),
        }
