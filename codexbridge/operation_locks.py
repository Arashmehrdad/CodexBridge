from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
                    acquired_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL
                )
                """
            )

    def acquire(
        self,
        *,
        repo_name: str,
        tool: str,
        normalized_input: dict[str, Any],
        run_id: str,
        owner_pid: int | None = None,
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
                    repo_name, tool, input_fingerprint, run_id, owner_pid, acquired_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (repo_name, tool, fingerprint, run_id, owner_pid, now, now),
            )
        return LockAcquisition(
            acquired=True,
            duplicate=False,
            repo_name=repo_name,
            lock_key=repo_name,
            fingerprint=fingerprint,
        )

    def heartbeat(self, repo_name: str, run_id: str) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                UPDATE operation_locks
                SET heartbeat_at = ?
                WHERE repo_name = ? AND run_id = ?
                """,
                (utc_now(), repo_name, run_id),
            )

    def release(self, repo_name: str, run_id: str) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "DELETE FROM operation_locks WHERE repo_name = ? AND run_id = ?",
                (repo_name, run_id),
            )

    def recover_stale(self) -> int:
        removed = 0
        with self.store.connect() as conn:
            rows = conn.execute("SELECT * FROM operation_locks").fetchall()
            for row in rows:
                existing = dict(row)
                if self._is_stale(conn, existing):
                    conn.execute(
                        "DELETE FROM operation_locks WHERE repo_name = ?",
                        (existing["repo_name"],),
                    )
                    removed += 1
        return removed

    def _is_stale(self, conn, row: dict[str, Any]) -> bool:
        run = conn.execute(
            "SELECT status, worker_pid, pid FROM runs WHERE run_id = ?",
            (row["run_id"],),
        ).fetchone()
        if run is None:
            return True
        status = str(run["status"] or "")
        if status in TERMINAL_STATUSES:
            return True
        owner_pid = row.get("owner_pid") or run["worker_pid"] or run["pid"]
        if owner_pid and not _pid_is_running(int(owner_pid)):
            return True
        return False


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        os.kill(pid, 0)
        return True
    except Exception:
        return False
