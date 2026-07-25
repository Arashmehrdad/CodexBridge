"""Ordered, transactional schema support for the canonical task plane.

The task tables live in the existing ``runs/soma.sqlite3`` database next to the
authoritative ``runs`` table. Sharing one database keeps a single durable store
and lets the canonical task reference a durable run without a second authority.

Every migration is applied inside its own transaction and recorded in
``soma_schema_migrations``. A partially applied migration rolls back completely,
so a fresh database and an existing run database converge on the same schema.
No existing table is rewritten, dropped, or backfilled.
"""

from __future__ import annotations

import sqlite3
from typing import Final

from .models import TASK_SCHEMA_COMPONENT, TASK_SCHEMA_VERSION, utc_now


MIGRATION_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS soma_schema_migrations (
    component TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY (component, version)
)
"""

_MIGRATION_0001: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        parent_task_id TEXT NOT NULL DEFAULT '',
        task_kind TEXT NOT NULL,
        controller_request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        objective_ref TEXT NOT NULL DEFAULT '',
        constraints_ref TEXT NOT NULL DEFAULT '',
        backend_kind TEXT NOT NULL,
        backend_executor TEXT NOT NULL DEFAULT '',
        backend_ref TEXT NOT NULL DEFAULT '',
        backend_identity_json TEXT NOT NULL DEFAULT '{}',
        workspace_kind TEXT NOT NULL DEFAULT '',
        workspace_ref TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL,
        phase TEXT NOT NULL DEFAULT '',
        state_version INTEGER NOT NULL DEFAULT 0,
        checkpoint_ref TEXT NOT NULL DEFAULT '',
        result_ref TEXT NOT NULL DEFAULT '',
        result_hash TEXT NOT NULL DEFAULT '',
        evidence_ref TEXT NOT NULL DEFAULT '',
        recovery_state TEXT NOT NULL DEFAULT 'none',
        recovery_reason TEXT NOT NULL DEFAULT '',
        reconciled_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT,
        ended_at TEXT
    )
    """,
    # Top-level idempotency: one controller request ID owns at most one task.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_controller_request "
    "ON tasks(controller_request_id)",
    # One backend reference is owned by at most one canonical task, so a retry
    # or a duplicate reconciler can never attach two tasks to one durable run.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_backend_ref "
    "ON tasks(backend_kind, backend_ref) WHERE backend_ref <> ''",
    "CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id)",
    """
    CREATE TABLE IF NOT EXISTS task_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        link_type TEXT NOT NULL,
        target_kind TEXT NOT NULL,
        target_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_links_identity "
    "ON task_links(task_id, link_type, target_kind, target_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_links_target "
    "ON task_links(target_kind, target_id)",
    """
    CREATE TABLE IF NOT EXISTS task_commands (
        command_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        command_kind TEXT NOT NULL,
        controller_request_id TEXT NOT NULL DEFAULT '',
        requested_state_version INTEGER NOT NULL,
        observed_state_version INTEGER NOT NULL,
        status TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_commands_task "
    "ON task_commands(task_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS task_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        prompt TEXT NOT NULL DEFAULT '',
        expected_input_schema_json TEXT NOT NULL DEFAULT '{}',
        context_ref TEXT NOT NULL DEFAULT '',
        evidence_ref TEXT NOT NULL DEFAULT '',
        required_state_version INTEGER NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_checkpoints_task "
    "ON task_checkpoints(task_id, status)",
    """
    CREATE TABLE IF NOT EXISTS task_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        level TEXT NOT NULL,
        stage TEXT NOT NULL,
        message TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT '',
        state_version INTEGER NOT NULL DEFAULT 0,
        data_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, id)",
)

TASK_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "canonical_task_plane_foundation", _MIGRATION_0001),
)

TASK_TABLE_NAMES: Final[tuple[str, ...]] = (
    "tasks",
    "task_links",
    "task_commands",
    "task_checkpoints",
    "task_events",
)


def applied_versions(conn: sqlite3.Connection, component: str) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (component,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn, TASK_SCHEMA_COMPONENT)
    return max(versions) if versions else 0


def apply_task_migrations(connect) -> list[int]:
    """Apply every pending task migration in order, one transaction each.

    ``connect`` is a zero-argument callable returning a fresh connection so a
    failed migration cannot leave a half-open transaction on a shared handle.
    """
    applied: list[int] = []
    conn = connect()
    try:
        with conn:
            conn.execute(MIGRATION_TABLE_SQL)
        pending = applied_versions(conn, TASK_SCHEMA_COMPONENT)
    finally:
        conn.close()

    for version, name, statements in TASK_MIGRATIONS:
        if version in pending:
            continue
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT OR IGNORE INTO soma_schema_migrations "
                    "(component, version, name, applied_at) VALUES (?, ?, ?, ?)",
                    (TASK_SCHEMA_COMPONENT, version, name, utc_now()),
                )
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()
        applied.append(version)
    return applied


def schema_state(conn: sqlite3.Connection) -> dict[str, object]:
    version = current_schema_version(conn)
    present = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    return {
        "component": TASK_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": TASK_SCHEMA_VERSION,
        "up_to_date": version >= TASK_SCHEMA_VERSION,
        "tables": [name for name in TASK_TABLE_NAMES if name in present],
        "missing_tables": [
            name for name in TASK_TABLE_NAMES if name not in present
        ],
    }
