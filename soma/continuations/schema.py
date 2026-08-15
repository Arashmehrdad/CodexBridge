"""Ordered additive migration for the minimal Sol continuation persistence kernel."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Final

from .models import CONTINUATION_SCHEMA_COMPONENT, CONTINUATION_SCHEMA_VERSION, utc_now


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
    CREATE TABLE controller_continuations (
        continuation_id TEXT PRIMARY KEY,
        label TEXT NOT NULL DEFAULT '',
        lifecycle TEXT NOT NULL CHECK(lifecycle IN ('open', 'completed', 'cancelled')),
        current_contract_revision_id TEXT NOT NULL,
        creation_controller_request_id TEXT NOT NULL UNIQUE,
        creation_request_hash TEXT NOT NULL CHECK(length(creation_request_hash) = 64),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        closed_at TEXT,
        closure_controller_request_id TEXT NOT NULL DEFAULT '',
        closure_request_hash TEXT NOT NULL DEFAULT '',
        CHECK(
            (lifecycle = 'open' AND closed_at IS NULL)
            OR (lifecycle IN ('completed', 'cancelled') AND closed_at IS NOT NULL)
        ),
        CHECK(
            closure_request_hash = '' OR length(closure_request_hash) = 64
        ),
        FOREIGN KEY(current_contract_revision_id, continuation_id)
            REFERENCES continuation_contract_revisions(contract_revision_id, continuation_id)
            DEFERRABLE INITIALLY DEFERRED
    )
    """,
    "CREATE INDEX idx_controller_continuations_lifecycle "
    "ON controller_continuations(lifecycle, updated_at)",
    """
    CREATE TABLE continuation_contract_revisions (
        contract_revision_id TEXT PRIMARY KEY,
        continuation_id TEXT NOT NULL,
        parent_revision_id TEXT,
        revision_number INTEGER NOT NULL CHECK(revision_number >= 1),
        instruction_text TEXT NOT NULL DEFAULT '',
        instruction_ref TEXT NOT NULL DEFAULT '',
        content_hash TEXT NOT NULL CHECK(length(content_hash) = 64),
        provenance_class TEXT NOT NULL CHECK(provenance_class <> ''),
        provenance_ref TEXT NOT NULL DEFAULT '',
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        created_at TEXT NOT NULL,
        CHECK(
            (instruction_text <> '' AND instruction_ref = '')
            OR (instruction_text = '' AND instruction_ref <> '')
        ),
        UNIQUE(continuation_id, revision_number),
        UNIQUE(contract_revision_id, continuation_id),
        FOREIGN KEY(continuation_id)
            REFERENCES controller_continuations(continuation_id),
        FOREIGN KEY(parent_revision_id)
            REFERENCES continuation_contract_revisions(contract_revision_id)
    )
    """,
    "CREATE INDEX idx_continuation_contract_history "
    "ON continuation_contract_revisions(continuation_id, revision_number)",
    """
    CREATE TABLE continuation_handoffs (
        handoff_id TEXT PRIMARY KEY,
        continuation_id TEXT NOT NULL,
        contract_revision_id TEXT NOT NULL,
        sequence_number INTEGER NOT NULL CHECK(sequence_number >= 1),
        handoff_text TEXT NOT NULL CHECK(handoff_text <> ''),
        content_hash TEXT NOT NULL CHECK(length(content_hash) = 64),
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        created_at TEXT NOT NULL,
        UNIQUE(continuation_id, sequence_number),
        FOREIGN KEY(contract_revision_id, continuation_id)
            REFERENCES continuation_contract_revisions(contract_revision_id, continuation_id),
        FOREIGN KEY(continuation_id)
            REFERENCES controller_continuations(continuation_id)
    )
    """,
    "CREATE INDEX idx_continuation_handoffs_latest "
    "ON continuation_handoffs(continuation_id, sequence_number DESC)",
    """
    CREATE TABLE continuation_effect_links (
        link_id TEXT PRIMARY KEY,
        continuation_id TEXT NOT NULL,
        contract_revision_id TEXT NOT NULL,
        effect_kind TEXT NOT NULL CHECK(effect_kind IN ('task', 'run')),
        effect_id TEXT NOT NULL CHECK(effect_id <> ''),
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        created_at TEXT NOT NULL,
        UNIQUE(effect_kind, effect_id),
        FOREIGN KEY(contract_revision_id, continuation_id)
            REFERENCES continuation_contract_revisions(contract_revision_id, continuation_id),
        FOREIGN KEY(continuation_id)
            REFERENCES controller_continuations(continuation_id)
    )
    """,
    "CREATE INDEX idx_continuation_effect_links_continuation "
    "ON continuation_effect_links(continuation_id, created_at, link_id)",
)

CONTINUATION_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "minimal_sol_semantic_continuation", _MIGRATION_0001),
)

CONTINUATION_TABLE_NAMES: Final[tuple[str, ...]] = (
    "controller_continuations",
    "continuation_contract_revisions",
    "continuation_handoffs",
    "continuation_effect_links",
)


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (CONTINUATION_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = _applied_versions(conn)
    return max(versions) if versions else 0


def apply_continuation_migrations(
    connect: Callable[[], sqlite3.Connection],
    *,
    migrations: tuple[tuple[int, str, tuple[str, ...]], ...] | None = None,
) -> list[int]:
    """Apply every pending continuation migration transactionally and once."""
    selected = CONTINUATION_MIGRATIONS if migrations is None else migrations
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
                    "(component, version, name, applied_at) VALUES (?, ?, ?, ?)",
                    (CONTINUATION_SCHEMA_COMPONENT, version, name, utc_now()),
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
        "component": CONTINUATION_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": CONTINUATION_SCHEMA_VERSION,
        "up_to_date": version >= CONTINUATION_SCHEMA_VERSION,
        "tables": [name for name in CONTINUATION_TABLE_NAMES if name in present],
        "missing_tables": [
            name for name in CONTINUATION_TABLE_NAMES if name not in present
        ],
    }
