"""Additive durable schema for protected mutation request/effect evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final


PROTECTED_TOOL_SCHEMA_COMPONENT: Final[str] = "protected_tools"
PROTECTED_TOOL_SCHEMA_VERSION: Final[int] = 2

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
    CREATE TABLE protected_tool_calls (
        call_request_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL UNIQUE CHECK(length(request_hash) = 64),
        call_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK(length(call_request_id) > 0),
        CHECK(length(idempotency_key) > 0)
    )
    """,
    """
    CREATE TABLE protected_tool_provider_provenance (
        call_request_id TEXT NOT NULL,
        provider_ref TEXT NOT NULL,
        provider_hash TEXT NOT NULL CHECK(length(provider_hash) = 64),
        created_at TEXT NOT NULL,
        PRIMARY KEY(call_request_id, provider_ref, provider_hash),
        FOREIGN KEY(call_request_id)
            REFERENCES protected_tool_calls(call_request_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE protected_tool_delivery (
        call_request_id TEXT PRIMARY KEY,
        delivery_state TEXT NOT NULL
            CHECK(delivery_state IN ('reserved', 'effect_begun', 'resolved')),
        begin_evidence_ref TEXT NOT NULL DEFAULT '',
        begin_evidence_hash TEXT NOT NULL DEFAULT '',
        effect_begun_at TEXT,
        updated_at TEXT NOT NULL,
        CHECK(
            (begin_evidence_ref = '' AND begin_evidence_hash = '')
            OR (begin_evidence_ref <> '' AND length(begin_evidence_hash) = 64)
        ),
        FOREIGN KEY(call_request_id)
            REFERENCES protected_tool_calls(call_request_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE protected_tool_effects (
        call_request_id TEXT PRIMARY KEY,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        effect_hash TEXT NOT NULL UNIQUE CHECK(length(effect_hash) = 64),
        effect_json TEXT NOT NULL,
        disposition TEXT NOT NULL
            CHECK(disposition IN ('prevented', 'rejected', 'acknowledged', 'outcome_unknown')),
        completed_at TEXT NOT NULL,
        FOREIGN KEY(call_request_id)
            REFERENCES protected_tool_calls(call_request_id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX idx_protected_tool_delivery_state "
    "ON protected_tool_delivery(delivery_state, updated_at)",
    """
    CREATE TRIGGER protected_tool_calls_no_update
    BEFORE UPDATE ON protected_tool_calls
    BEGIN
        SELECT RAISE(ABORT, 'protected_tool_calls are immutable');
    END
    """,
    """
    CREATE TRIGGER protected_tool_calls_no_delete
    BEFORE DELETE ON protected_tool_calls
    BEGIN
        SELECT RAISE(ABORT, 'protected_tool_calls are immutable');
    END
    """,
    """
    CREATE TRIGGER protected_tool_provenance_no_update
    BEFORE UPDATE ON protected_tool_provider_provenance
    BEGIN
        SELECT RAISE(ABORT, 'protected tool provenance is immutable');
    END
    """,
    """
    CREATE TRIGGER protected_tool_provenance_no_delete
    BEFORE DELETE ON protected_tool_provider_provenance
    BEGIN
        SELECT RAISE(ABORT, 'protected tool provenance is immutable');
    END
    """,
    """
    CREATE TRIGGER protected_tool_effects_no_update
    BEFORE UPDATE ON protected_tool_effects
    BEGIN
        SELECT RAISE(ABORT, 'protected_tool_effects are immutable');
    END
    """,
    """
    CREATE TRIGGER protected_tool_effects_no_delete
    BEFORE DELETE ON protected_tool_effects
    BEGIN
        SELECT RAISE(ABORT, 'protected_tool_effects are immutable');
    END
    """,
)

_MIGRATION_0002: Final[tuple[str, ...]] = (
    """
    CREATE TABLE protected_resource_leases (
        lease_ref TEXT PRIMARY KEY,
        resource_key TEXT NOT NULL,
        call_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        task_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL,
        owner_ref TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('held', 'uncertain', 'released', 'contained')),
        acquired_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resolution_evidence_ref TEXT NOT NULL DEFAULT '',
        resolution_evidence_hash TEXT NOT NULL DEFAULT '',
        CHECK(length(resource_key) > 0),
        CHECK(length(task_id) > 0),
        CHECK(length(attempt_id) > 0),
        CHECK(length(owner_ref) > 0),
        CHECK(
            (resolution_evidence_ref = '' AND resolution_evidence_hash = '')
            OR (resolution_evidence_ref <> '' AND length(resolution_evidence_hash) = 64)
        ),
        FOREIGN KEY(call_request_id)
            REFERENCES protected_tool_calls(call_request_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE UNIQUE INDEX idx_protected_resource_active_key
    ON protected_resource_leases(resource_key)
    WHERE state IN ('held', 'uncertain')
    """,
    "CREATE INDEX idx_protected_resource_state "
    "ON protected_resource_leases(state, updated_at)",
    """
    CREATE TRIGGER protected_resource_lease_identity_immutable
    BEFORE UPDATE OF
        lease_ref, resource_key, call_request_id, request_hash,
        task_id, attempt_id, owner_ref, acquired_at
    ON protected_resource_leases
    BEGIN
        SELECT RAISE(ABORT, 'protected resource lease identity is immutable');
    END
    """,
    """
    CREATE TRIGGER protected_resource_leases_no_delete
    BEFORE DELETE ON protected_resource_leases
    BEGIN
        SELECT RAISE(ABORT, 'protected resource lease history is immutable');
    END
    """,
)

PROTECTED_TOOL_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "protected_tool_foundation", _MIGRATION_0001),
    (2, "protected_resource_serialization", _MIGRATION_0002),
)

PROTECTED_TOOL_TABLE_NAMES: Final[tuple[str, ...]] = (
    "protected_tool_calls",
    "protected_tool_provider_provenance",
    "protected_tool_delivery",
    "protected_tool_effects",
    "protected_resource_leases",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (PROTECTED_TOOL_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn)
    return max(versions) if versions else 0


def apply_protected_tool_migrations(
    connect: Callable[[], sqlite3.Connection],
    *,
    migrations: tuple[
        tuple[int, str, tuple[str, ...]], ...
    ] = PROTECTED_TOOL_MIGRATIONS,
) -> list[int]:
    """Apply pending protected-tool migrations transactionally."""

    conn = connect()
    try:
        with conn:
            conn.execute(MIGRATION_TABLE_SQL)
        pending = applied_versions(conn)
    finally:
        conn.close()

    applied: list[int] = []
    for version, name, statements in migrations:
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
                    "(component, version, name, applied_at) VALUES (?, ?, ?, ?)",
                    (PROTECTED_TOOL_SCHEMA_COMPONENT, version, name, utc_now()),
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
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    present = {str(row[0]) for row in rows}
    missing = sorted(set(PROTECTED_TOOL_TABLE_NAMES) - present)
    return {
        "component": PROTECTED_TOOL_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": PROTECTED_TOOL_SCHEMA_VERSION,
        "up_to_date": version == PROTECTED_TOOL_SCHEMA_VERSION and not missing,
        "missing_tables": missing,
    }
