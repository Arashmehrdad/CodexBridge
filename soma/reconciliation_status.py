"""Durable record of startup reconciliation outcomes.

Startup reconciliation decides what happened to work that was in flight when
the previous process stopped. If it fails, Soma has lost recovery information
for those runs, workflows, tasks, or activations — but the service would
otherwise start and answer requests as though nothing was wrong.

This module makes that failure durable and observable. Each reconciliation path
claims a ``running`` row before it starts and resolves it to ``ok`` or
``failed``. A process that dies mid-reconciliation therefore leaves a
``running`` row behind, so an interrupted reconciliation is distinguishable
from one that never started and from one that succeeded.

The record lives beside the runs it describes. Run events cannot be used: the
``events`` table requires a ``run_id`` foreign key, and a startup failure is not
attributable to a single run.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

STATE_RUNNING = "running"
STATE_OK = "ok"
STATE_FAILED = "failed"

PATH_JOB_RUNS = "job_runs"
PATH_WORKFLOWS = "workflows"
PATH_PROJECT_SCOPE = "project_scope"
PATH_TASKS = "tasks"
PATH_SUPERVISORS = "supervisors"
PATH_SSH_ACTIVATION = "ssh_activation"
PATH_SSH_ACTIVATION_COORDINATOR = "ssh_activation_coordinator"

#: Paths expected to report during a normal server start.
STARTUP_PATHS = (
    PATH_JOB_RUNS,
    PATH_WORKFLOWS,
    PATH_PROJECT_SCOPE,
    PATH_TASKS,
    PATH_SUPERVISORS,
    PATH_SSH_ACTIVATION,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS startup_reconciliation (
    path TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    exception_type TEXT NOT NULL DEFAULT '',
    duration_ms REAL NOT NULL DEFAULT 0,
    process_id INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL
)
"""

DATABASE_NAME = "soma.sqlite3"


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _connect(runs_dir: Path) -> sqlite3.Connection:
    runs_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect((runs_dir / DATABASE_NAME).as_posix())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute(_SCHEMA)
    return connection


def claim(runs_dir: Path, path: str, *, process_id: int = 0) -> str:
    """Record that ``path`` has started reconciling and return its start time.

    The row is written before the work begins so that a crash during
    reconciliation is visible afterwards rather than looking like a clean start.
    """
    started_at = _utc_now()
    connection = _connect(runs_dir)
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO startup_reconciliation "
                "(path, state, detail, exception_type, duration_ms, process_id, "
                " started_at, recorded_at) VALUES (?,?,?,?,?,?,?,?)",
                (path, STATE_RUNNING, "", "", 0.0, process_id, started_at, started_at),
            )
    finally:
        connection.close()
    return started_at


def resolve(
    runs_dir: Path,
    path: str,
    *,
    ok: bool,
    detail: str = "",
    exception_type: str = "",
    duration_ms: float = 0.0,
    started_at: str = "",
    process_id: int = 0,
) -> None:
    connection = _connect(runs_dir)
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO startup_reconciliation "
                "(path, state, detail, exception_type, duration_ms, process_id, "
                " started_at, recorded_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    path,
                    STATE_OK if ok else STATE_FAILED,
                    detail[:2000],
                    exception_type[:200],
                    round(float(duration_ms), 3),
                    process_id,
                    started_at,
                    _utc_now(),
                ),
            )
    finally:
        connection.close()


def read_status(runs_dir: Path) -> dict[str, Any]:
    """Return the current reconciliation state for the readiness surface.

    Once any path has reported, every expected startup path must be present and
    successful: a partial record means something that should have run did not.

    A store with no record at all is reported as ``never_recorded`` and stays
    healthy. The server has not started, so no recovery information has been
    lost, and a check that is permanently red on a fresh install is a signal
    operators learn to ignore.
    """
    database = runs_dir / DATABASE_NAME
    if not database.exists():
        return {
            "ok": True,
            "available": False,
            "state": "never_recorded",
            "reason": "no reconciliation has been recorded yet",
            "paths": {},
            "failed": [],
            "incomplete": [],
            "missing": [],
        }
    try:
        connection = _connect(runs_dir)
    except sqlite3.Error as exc:
        return {
            "ok": False,
            "available": False,
            "state": "unreadable",
            "reason": f"reconciliation record unreadable: {exc}"[:500],
            "paths": {},
            "failed": [],
            "incomplete": [],
            "missing": list(STARTUP_PATHS),
        }
    try:
        rows = {
            str(row["path"]): dict(row)
            for row in connection.execute("SELECT * FROM startup_reconciliation")
        }
    finally:
        connection.close()

    if not rows:
        return {
            "ok": True,
            "available": False,
            "state": "never_recorded",
            "reason": "no reconciliation has been recorded yet",
            "paths": {},
            "failed": [],
            "incomplete": [],
            "missing": [],
        }

    failed = sorted(p for p, r in rows.items() if r["state"] == STATE_FAILED)
    incomplete = sorted(p for p, r in rows.items() if r["state"] == STATE_RUNNING)
    missing = sorted(p for p in STARTUP_PATHS if p not in rows)
    return {
        "ok": not (failed or incomplete or missing),
        "available": True,
        "state": "recorded",
        "reason": "",
        "paths": {
            path: {
                "state": str(row["state"]),
                "detail": str(row["detail"]),
                "exception_type": str(row["exception_type"]),
                "duration_ms": float(row["duration_ms"]),
                "recorded_at": str(row["recorded_at"]),
            }
            for path, row in sorted(rows.items())
        },
        "failed": failed,
        "incomplete": incomplete,
        "missing": missing,
    }


class ReconciliationRecorder:
    """Record a reconciliation path, publishing failure instead of swallowing it.

    Used as a context manager so the durable record is resolved on both the
    success and the exception path. The exception is re-raised only when
    ``suppress`` is false; server startup suppresses it so one broken subsystem
    cannot prevent the service from starting, but the failure is now durable and
    readiness reports it.
    """

    def __init__(
        self,
        runs_dir: Path,
        path: str,
        *,
        process_id: int = 0,
        suppress: bool = True,
    ) -> None:
        self.runs_dir = runs_dir
        self.path = path
        self.process_id = process_id
        self.suppress = suppress
        self.started_at = ""
        self._started_monotonic = 0.0
        self.failed = False

    def __enter__(self) -> "ReconciliationRecorder":
        self._started_monotonic = time.monotonic()
        try:
            self.started_at = claim(
                self.runs_dir, self.path, process_id=self.process_id
            )
        except sqlite3.Error:
            # Never let bookkeeping prevent reconciliation from being attempted.
            self.started_at = ""
        return self

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        duration_ms = (time.monotonic() - self._started_monotonic) * 1000.0
        self.failed = exc is not None
        try:
            resolve(
                self.runs_dir,
                self.path,
                ok=exc is None,
                detail="" if exc is None else f"{type(exc).__name__}: {exc}",
                exception_type="" if exc is None else type(exc).__name__,
                duration_ms=duration_ms,
                started_at=self.started_at,
                process_id=self.process_id,
            )
        except sqlite3.Error:
            pass
        return bool(exc is not None and self.suppress)
