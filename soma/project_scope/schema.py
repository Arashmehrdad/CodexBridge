"""Ordered additive migration for the ProjectScope v1 sidecar."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Final

from .models import PROJECT_SCOPE_SCHEMA_COMPONENT, PROJECT_SCOPE_SCHEMA_VERSION


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
    CREATE TABLE project_scope_settings (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        scoped_writes_enabled INTEGER NOT NULL DEFAULT 0
            CHECK(scoped_writes_enabled IN (0, 1)),
        ever_activated INTEGER NOT NULL DEFAULT 0
            CHECK(ever_activated IN (0, 1)),
        updated_at TEXT NOT NULL
    )
    """,
    """
    INSERT INTO project_scope_settings
        (singleton, scoped_writes_enabled, ever_activated, updated_at)
    VALUES (1, 0, 0, '')
    """,
    """
    CREATE TABLE projects (
        project_id TEXT PRIMARY KEY,
        project_key TEXT NOT NULL UNIQUE,
        lifecycle_state TEXT NOT NULL
            CHECK(lifecycle_state IN ('active', 'suspended', 'archived')),
        scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE project_resources (
        resource_id TEXT PRIMARY KEY,
        resource_kind TEXT NOT NULL,
        opaque_ref TEXT NOT NULL,
        identity_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(resource_kind, identity_hash)
    )
    """,
    """
    CREATE TABLE project_resource_bindings (
        project_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        access_mode TEXT NOT NULL CHECK(access_mode IN ('exclusive', 'shared')),
        created_at TEXT NOT NULL,
        PRIMARY KEY(project_id, resource_id),
        FOREIGN KEY(project_id) REFERENCES projects(project_id),
        FOREIGN KEY(resource_id) REFERENCES project_resources(resource_id)
    )
    """,
    """
    CREATE TABLE project_repository_bindings (
        project_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        repo_name TEXT NOT NULL,
        repository_root TEXT NOT NULL,
        identity_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(project_id, resource_id),
        UNIQUE(project_id, repo_name),
        FOREIGN KEY(project_id, resource_id)
            REFERENCES project_resource_bindings(project_id, resource_id)
    )
    """,
    "CREATE INDEX idx_project_repository_locator "
    "ON project_repository_bindings(repo_name, identity_hash)",
    """
    CREATE TABLE project_task_reservations (
        task_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
        status TEXT NOT NULL
            CHECK(status IN ('reserved', 'attached', 'quarantined')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(project_id),
        UNIQUE(project_id, task_id)
    )
    """,
    """
    CREATE TABLE project_run_attempts (
        run_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
        status TEXT NOT NULL CHECK(
            status IN ('reserved', 'attached', 'recovery_pending', 'quarantined')
        ),
        recovery_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(project_id, task_id)
            REFERENCES project_task_reservations(project_id, task_id),
        FOREIGN KEY(project_id, resource_id)
            REFERENCES project_resource_bindings(project_id, resource_id),
        UNIQUE(project_id, run_id),
        UNIQUE(task_id)
    )
    """,
    "CREATE INDEX idx_project_attempt_task ON project_run_attempts(task_id, status)",
    """
    CREATE TABLE project_scope_quarantine (
        record_kind TEXT NOT NULL,
        record_id TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        evidence_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(record_kind, record_id)
    )
    """,
    """
    CREATE TABLE project_scope_bootstrap_events (
        event_id TEXT PRIMARY KEY,
        input_hash TEXT NOT NULL,
        outcome_hash TEXT NOT NULL,
        applied INTEGER NOT NULL CHECK(applied IN (0, 1)),
        created_at TEXT NOT NULL
    )
    """,
)

_MIGRATION_0002: Final[tuple[str, ...]] = (
    # Adjudication never mutates a quarantined row. It records a separate,
    # owner-supplied disposition beside the preserved original evidence, which
    # is why the quarantine tables are untouched by this version.
    """
    CREATE TABLE project_scope_adjudications (
        adjudication_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        record_kind TEXT NOT NULL
            CHECK(record_kind IN ('task_reservation', 'run_attempt')),
        record_id TEXT NOT NULL,
        disposition TEXT NOT NULL
            CHECK(disposition IN ('acknowledged', 'superseded')),
        successor_task_id TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        quarantine_evidence_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        -- At most one adjudication per quarantined record. A crash between the
        -- decision and its commit can therefore never produce two successors.
        UNIQUE(record_kind, record_id),
        UNIQUE(project_id, record_kind, record_id, idempotency_key),
        CHECK(
            (disposition = 'superseded' AND successor_task_id != '')
            OR (disposition = 'acknowledged' AND successor_task_id = '')
        ),
        CHECK(successor_task_id != record_id),
        FOREIGN KEY(project_id) REFERENCES projects(project_id),
        FOREIGN KEY(record_kind, record_id)
            REFERENCES project_scope_quarantine(record_kind, record_id)
    )
    """,
    "CREATE INDEX idx_project_adjudication_project "
    "ON project_scope_adjudications(project_id, created_at)",
)

PROJECT_SCOPE_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "additive_project_identity_foundation", _MIGRATION_0001),
    (2, "quarantine_adjudication_path", _MIGRATION_0002),
)

PROJECT_SCOPE_TABLE_NAMES: Final[tuple[str, ...]] = (
    "project_scope_settings",
    "projects",
    "project_resources",
    "project_resource_bindings",
    "project_repository_bindings",
    "project_task_reservations",
    "project_run_attempts",
    "project_scope_quarantine",
    "project_scope_bootstrap_events",
    "project_scope_adjudications",
)

BINDING_TABLE_NAMES: Final[tuple[str, ...]] = (
    "projects",
    "project_resources",
    "project_resource_bindings",
    "project_repository_bindings",
    "project_task_reservations",
    "project_run_attempts",
    "project_scope_quarantine",
    "project_scope_bootstrap_events",
    "project_scope_adjudications",
)


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = _applied_versions(conn)
    return max(versions) if versions else 0


def apply_project_scope_migrations(
    connect: Callable[[], sqlite3.Connection],
    *,
    migrations: tuple[tuple[int, str, tuple[str, ...]], ...] | None = None,
) -> list[int]:
    """Apply pending versions, with each version atomic and attempted once."""
    selected = PROJECT_SCOPE_MIGRATIONS if migrations is None else migrations
    applied: list[int] = []
    conn = connect()
    try:
        with conn:
            conn.execute(MIGRATION_TABLE_SQL)
        pending = _applied_versions(conn)
    finally:
        conn.close()

    for version, name, statements in selected:
        if version in pending:
            continue
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO soma_schema_migrations "
                    "(component, version, name, applied_at) "
                    "VALUES (?, ?, ?, datetime('now'))",
                    (PROJECT_SCOPE_SCHEMA_COMPONENT, version, name),
                )
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()
        applied.append(version)
    return applied


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (PROJECT_SCOPE_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def schema_state(conn: sqlite3.Connection) -> dict[str, object]:
    version = current_schema_version(conn)
    present = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    return {
        "component": PROJECT_SCOPE_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": PROJECT_SCOPE_SCHEMA_VERSION,
        "up_to_date": version >= PROJECT_SCOPE_SCHEMA_VERSION,
        "tables": [name for name in PROJECT_SCOPE_TABLE_NAMES if name in present],
        "missing_tables": [
            name for name in PROJECT_SCOPE_TABLE_NAMES if name not in present
        ],
    }
