"""Additive durable schema for subordinate reasoning backend evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final


REASONING_BACKEND_SCHEMA_COMPONENT: Final[str] = "reasoning_backend"
REASONING_BACKEND_SCHEMA_VERSION: Final[int] = 1

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
    CREATE TABLE reasoning_backend_runs (
        backend_ref TEXT PRIMARY KEY,
        reasoning_spec_ref TEXT NOT NULL,
        reasoning_spec_hash TEXT NOT NULL CHECK(length(reasoning_spec_hash) = 64),
        provider_route_ref TEXT NOT NULL,
        provider_route_hash TEXT NOT NULL CHECK(length(provider_route_hash) = 64),
        start_delivery_disposition TEXT NOT NULL DEFAULT 'not_attempted'
            CHECK(start_delivery_disposition IN (
                'not_attempted', 'claimed_not_sent', 'accepted_bound',
                'rejected', 'outcome_unknown'
            )),
        provider_binding_disposition TEXT NOT NULL DEFAULT 'unbound'
            CHECK(provider_binding_disposition IN ('unbound', 'bound', 'uncertain')),
        provider_operation_ref TEXT NOT NULL DEFAULT '',
        provider_binding_ref TEXT NOT NULL DEFAULT '',
        provider_binding_hash TEXT NOT NULL DEFAULT '',
        provider_status_raw TEXT NOT NULL DEFAULT '',
        provider_terminal_claim TEXT NOT NULL DEFAULT 'none'
            CHECK(provider_terminal_claim IN (
                'none', 'success', 'failure', 'cancelled', 'incomplete'
            )),
        continuation_ref TEXT NOT NULL DEFAULT '',
        last_event_cursor TEXT NOT NULL DEFAULT '',
        output_contract_disposition TEXT NOT NULL DEFAULT 'not_available'
            CHECK(output_contract_disposition IN (
                'not_available', 'valid', 'invalid', 'uncertain'
            )),
        output_contract_version TEXT NOT NULL DEFAULT '',
        result_ref TEXT NOT NULL DEFAULT '',
        result_hash TEXT NOT NULL DEFAULT '',
        evidence_index_ref TEXT NOT NULL DEFAULT '',
        evidence_index_hash TEXT NOT NULL DEFAULT '',
        provider_provenance_index_ref TEXT NOT NULL DEFAULT '',
        provider_provenance_index_hash TEXT NOT NULL DEFAULT '',
        raw_provider_evidence_root_ref TEXT NOT NULL DEFAULT '',
        raw_provider_evidence_root_hash TEXT NOT NULL DEFAULT '',
        usage_ref TEXT NOT NULL DEFAULT '',
        usage_hash TEXT NOT NULL DEFAULT '',
        usage_summary_json TEXT NOT NULL DEFAULT '{}',
        error_code TEXT NOT NULL DEFAULT '',
        cancellation_disposition TEXT NOT NULL DEFAULT 'not_requested'
            CHECK(cancellation_disposition IN (
                'not_requested', 'accepted', 'rejected', 'uncertain'
            )),
        cancellation_evidence_ref TEXT NOT NULL DEFAULT '',
        cancellation_evidence_hash TEXT NOT NULL DEFAULT '',
        cancellation_requested_at TEXT,
        result_published_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(length(backend_ref) > 0),
        CHECK(length(reasoning_spec_ref) > 0),
        CHECK(length(provider_route_ref) > 0),
        CHECK(
            (provider_binding_ref = '' AND provider_binding_hash = '')
            OR (provider_binding_ref <> '' AND length(provider_binding_hash) = 64)
        ),
        CHECK(
            (result_ref = '' AND result_hash = '')
            OR (result_ref <> '' AND length(result_hash) = 64)
        ),
        CHECK(
            (evidence_index_ref = '' AND evidence_index_hash = '')
            OR (evidence_index_ref <> '' AND length(evidence_index_hash) = 64)
        ),
        CHECK(
            (provider_provenance_index_ref = '' AND provider_provenance_index_hash = '')
            OR (provider_provenance_index_ref <> ''
                AND length(provider_provenance_index_hash) = 64)
        ),
        CHECK(
            (raw_provider_evidence_root_ref = '' AND raw_provider_evidence_root_hash = '')
            OR (raw_provider_evidence_root_ref <> ''
                AND length(raw_provider_evidence_root_hash) = 64)
        ),
        CHECK(
            (usage_ref = '' AND usage_hash = '')
            OR (usage_ref <> '' AND length(usage_hash) = 64)
        ),
        CHECK(
            (cancellation_evidence_ref = '' AND cancellation_evidence_hash = '')
            OR (cancellation_evidence_ref <> ''
                AND length(cancellation_evidence_hash) = 64)
        )
    )
    """,
    "CREATE INDEX idx_reasoning_backend_start_delivery "
    "ON reasoning_backend_runs(start_delivery_disposition, created_at)",
    "CREATE INDEX idx_reasoning_backend_provider_operation "
    "ON reasoning_backend_runs(provider_operation_ref) "
    "WHERE provider_operation_ref <> ''",
    """
    CREATE TABLE reasoning_backend_start_attempts (
        start_attempt_id TEXT PRIMARY KEY,
        backend_ref TEXT NOT NULL UNIQUE,
        start_request_hash TEXT NOT NULL CHECK(length(start_request_hash) = 64),
        disposition TEXT NOT NULL
            CHECK(disposition IN (
                'claimed_not_sent', 'accepted_bound', 'rejected', 'outcome_unknown'
            )),
        provider_operation_ref TEXT NOT NULL DEFAULT '',
        outcome_unknown_evidence_ref TEXT NOT NULL DEFAULT '',
        outcome_unknown_evidence_hash TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(
            (outcome_unknown_evidence_ref = '' AND outcome_unknown_evidence_hash = '')
            OR (outcome_unknown_evidence_ref <> ''
                AND length(outcome_unknown_evidence_hash) = 64)
        ),
        FOREIGN KEY(backend_ref)
            REFERENCES reasoning_backend_runs(backend_ref) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_reasoning_backend_attempt_disposition "
    "ON reasoning_backend_start_attempts(disposition, created_at)",
)

REASONING_BACKEND_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "reasoning_backend_foundation", _MIGRATION_0001),
)

REASONING_BACKEND_TABLE_NAMES: Final[tuple[str, ...]] = (
    "reasoning_backend_runs",
    "reasoning_backend_start_attempts",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (REASONING_BACKEND_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn)
    return max(versions) if versions else 0


def apply_reasoning_backend_migrations(
    connect: Callable[[], sqlite3.Connection],
    *,
    migrations: tuple[
        tuple[int, str, tuple[str, ...]], ...
    ] = REASONING_BACKEND_MIGRATIONS,
) -> list[int]:
    """Apply pending reasoning-backend migrations transactionally."""

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
                    (REASONING_BACKEND_SCHEMA_COMPONENT, version, name, utc_now()),
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
        "component": REASONING_BACKEND_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": REASONING_BACKEND_SCHEMA_VERSION,
        "up_to_date": version == REASONING_BACKEND_SCHEMA_VERSION,
        "tables": [name for name in REASONING_BACKEND_TABLE_NAMES if name in present],
        "missing_tables": [
            name for name in REASONING_BACKEND_TABLE_NAMES if name not in present
        ],
    }
