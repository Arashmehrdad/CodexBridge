"""Additive V3-2 worker authority schema.

The component stores only worker authentication verifier material, immutable
positive capability grants, and immutable revocation evidence. It does not own
Task, Run, ProjectScope, provider-session, role, or protected-effect lifecycle.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final

from .models import WORKER_AUTHORITY_SCHEMA_COMPONENT, WORKER_AUTHORITY_SCHEMA_VERSION


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
    CREATE TABLE worker_principals (
        principal_id TEXT PRIMARY KEY,
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        verifier_hash TEXT NOT NULL CHECK(length(verifier_hash) = 64),
        principal_json TEXT NOT NULL,
        content_hash TEXT NOT NULL UNIQUE CHECK(length(content_hash) = 64),
        created_at TEXT NOT NULL,
        CHECK(length(principal_id) > 0)
    )
    """,
    """
    CREATE TABLE worker_capability_grants (
        grant_id TEXT PRIMARY KEY,
        principal_id TEXT NOT NULL,
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        grant_json TEXT NOT NULL,
        content_hash TEXT NOT NULL UNIQUE CHECK(length(content_hash) = 64),
        created_at TEXT NOT NULL,
        CHECK(length(grant_id) > 0),
        FOREIGN KEY(principal_id) REFERENCES worker_principals(principal_id)
            ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX idx_worker_grants_principal ON worker_capability_grants(principal_id, created_at)",
    """
    CREATE TABLE worker_authority_revocations (
        revocation_id TEXT PRIMARY KEY,
        target_kind TEXT NOT NULL CHECK(target_kind IN ('principal', 'grant')),
        target_id TEXT NOT NULL,
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        reason_ref TEXT NOT NULL,
        reason_hash TEXT NOT NULL CHECK(length(reason_hash) = 64),
        issuer_ref TEXT NOT NULL,
        revoked_at TEXT NOT NULL,
        UNIQUE(target_kind, target_id),
        CHECK(length(target_id) > 0),
        CHECK(length(reason_ref) > 0),
        CHECK(length(issuer_ref) > 0)
    )
    """,
    "CREATE INDEX idx_worker_revocations_target ON worker_authority_revocations(target_kind, target_id)",
    """
    CREATE TRIGGER worker_principals_no_update
    BEFORE UPDATE ON worker_principals
    BEGIN
        SELECT RAISE(ABORT, 'worker principals are immutable');
    END
    """,
    """
    CREATE TRIGGER worker_principals_no_delete
    BEFORE DELETE ON worker_principals
    BEGIN
        SELECT RAISE(ABORT, 'worker principals are immutable');
    END
    """,
    """
    CREATE TRIGGER worker_capability_grants_no_update
    BEFORE UPDATE ON worker_capability_grants
    BEGIN
        SELECT RAISE(ABORT, 'worker capability grants are immutable');
    END
    """,
    """
    CREATE TRIGGER worker_capability_grants_no_delete
    BEFORE DELETE ON worker_capability_grants
    BEGIN
        SELECT RAISE(ABORT, 'worker capability grants are immutable');
    END
    """,
    """
    CREATE TRIGGER worker_authority_revocations_no_update
    BEFORE UPDATE ON worker_authority_revocations
    BEGIN
        SELECT RAISE(ABORT, 'worker authority revocations are immutable');
    END
    """,
    """
    CREATE TRIGGER worker_authority_revocations_no_delete
    BEFORE DELETE ON worker_authority_revocations
    BEGIN
        SELECT RAISE(ABORT, 'worker authority revocations are immutable');
    END
    """,
)

WORKER_AUTHORITY_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "worker_authority_foundation", _MIGRATION_0001),
)

WORKER_AUTHORITY_TABLE_NAMES: Final[tuple[str, ...]] = (
    "worker_principals",
    "worker_capability_grants",
    "worker_authority_revocations",
)

WORKER_AUTHORITY_TRIGGER_NAMES: Final[tuple[str, ...]] = (
    "worker_principals_no_update",
    "worker_principals_no_delete",
    "worker_capability_grants_no_update",
    "worker_capability_grants_no_delete",
    "worker_authority_revocations_no_update",
    "worker_authority_revocations_no_delete",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (WORKER_AUTHORITY_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def apply_worker_authority_migrations(
    connect: Callable[[], sqlite3.Connection],
    *,
    migrations: tuple[
        tuple[int, str, tuple[str, ...]], ...
    ] = WORKER_AUTHORITY_MIGRATIONS,
) -> list[int]:
    conn = connect()
    try:
        with conn:
            conn.execute(MIGRATION_TABLE_SQL)
        applied = _applied_versions(conn)
    finally:
        conn.close()

    result: list[int] = []
    for version, name, statements in migrations:
        if version in applied:
            continue
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO soma_schema_migrations(component, version, name, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (WORKER_AUTHORITY_SCHEMA_COMPONENT, version, name, _utc_now()),
                )
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()
        result.append(version)
    return result


def schema_state(conn: sqlite3.Connection) -> dict[str, object]:
    applied = _applied_versions(conn)
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    triggers = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
    }
    missing_tables = sorted(set(WORKER_AUTHORITY_TABLE_NAMES) - tables)
    missing_triggers = sorted(set(WORKER_AUTHORITY_TRIGGER_NAMES) - triggers)
    version = max(applied) if applied else 0
    return {
        "component": WORKER_AUTHORITY_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": WORKER_AUTHORITY_SCHEMA_VERSION,
        "up_to_date": (
            version == WORKER_AUTHORITY_SCHEMA_VERSION
            and not missing_tables
            and not missing_triggers
        ),
        "tables": sorted(set(WORKER_AUTHORITY_TABLE_NAMES) & tables),
        "missing_tables": missing_tables,
        "missing_triggers": missing_triggers,
        "live_worker_surface": False,
    }
