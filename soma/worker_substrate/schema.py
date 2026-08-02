"""Additive migration for the interactive worker substrate.

The tables live in the existing ``runs/soma.sqlite3`` database beside ``tasks``
and ``runs``. A second database would create a second durable truth and would
make a crash between two databases unrecoverable, which is exactly the failure
this lane exists to prevent.

The migration creates tables only. It alters no existing table, rewrites no
existing row, and infers nothing about history: a record that predates the
substrate has no session, interaction, usage, or child-process identity, and
inventing one would be fabricated evidence.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Final

from .models import (
    WORKER_SUBSTRATE_SCHEMA_COMPONENT,
    WORKER_SUBSTRATE_SCHEMA_VERSION,
    utc_now,
)


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
    # ------------------------------------------------------------------
    # Provider-session binding.
    #
    # ``run_id`` is intentionally NOT a foreign key. Run identity is owned by
    # RunStore, which builds its own schema outside this migration component; a
    # foreign key here would invert that ownership and couple this migration to
    # RunStore.init_db ordering. The uniqueness rules below carry the invariant.
    #
    # COLLATE BINARY is explicit rather than implied so a provider identifier
    # can never be matched case-insensitively, whatever a future default is.
    # ------------------------------------------------------------------
    """
    CREATE TABLE worker_provider_sessions (
        session_binding_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        provider TEXT NOT NULL COLLATE BINARY,
        native_session_id TEXT NOT NULL COLLATE BINARY,
        adapter_id TEXT NOT NULL COLLATE BINARY,
        adapter_version TEXT NOT NULL DEFAULT '',
        protocol_id TEXT NOT NULL COLLATE BINARY,
        protocol_version TEXT NOT NULL DEFAULT '',
        disposition TEXT NOT NULL
            CHECK(disposition IN ('bound', 'mismatch_detected', 'unverified')),
        disposition_reason TEXT NOT NULL DEFAULT '',
        resume_cursor TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(length(project_id) > 0),
        CHECK(length(resource_id) > 0),
        CHECK(length(run_id) > 0),
        CHECK(length(provider) > 0),
        CHECK(length(native_session_id) > 0),
        -- One canonical run binds at most one native session, so a rebind can
        -- never happen silently: it collides.
        UNIQUE(run_id),
        -- One native session belongs to at most one canonical run, so two runs
        -- cannot claim the same provider conversation.
        UNIQUE(provider, native_session_id),
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_sessions_task "
    "ON worker_provider_sessions(task_id, created_at)",
    "CREATE INDEX idx_worker_sessions_project "
    "ON worker_provider_sessions(project_id, disposition)",
    # ------------------------------------------------------------------
    # Interaction delivery.
    #
    # The payload is referenced and hashed, never inlined here and never placed
    # in a command line. ``payload_ref`` points at content-addressed bytes
    # outside the database.
    # ------------------------------------------------------------------
    """
    CREATE TABLE worker_interactions (
        interaction_id TEXT PRIMARY KEY,
        session_binding_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        interaction_kind TEXT NOT NULL
            CHECK(interaction_kind IN ('steer', 'supply_input')),
        idempotency_key TEXT NOT NULL COLLATE BINARY,
        payload_ref TEXT NOT NULL,
        payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
        payload_bytes INTEGER NOT NULL CHECK(payload_bytes >= 0),
        expected_checkpoint_id TEXT NOT NULL DEFAULT '',
        requested_state_version INTEGER NOT NULL DEFAULT 0,
        delivery TEXT NOT NULL
            CHECK(delivery IN ('pending', 'acknowledged', 'rejected', 'uncertain')),
        delivery_reason TEXT NOT NULL DEFAULT '',
        delivery_evidence_ref TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        delivered_at TEXT,
        -- Caller-provided idempotency identity is unique per task, so a replay
        -- resolves to the same row and a crash cannot deliver twice.
        UNIQUE(task_id, idempotency_key),
        FOREIGN KEY(session_binding_id)
            REFERENCES worker_provider_sessions(session_binding_id)
            ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_interactions_session "
    "ON worker_interactions(session_binding_id, created_at)",
    "CREATE INDEX idx_worker_interactions_delivery "
    "ON worker_interactions(delivery, created_at)",
    # ------------------------------------------------------------------
    # Controller-checkpoint deadlines.
    #
    # A separate table complements ``task_checkpoints`` instead of altering it,
    # so every existing checkpoint read and record is byte-identical afterwards
    # and a checkpoint with no deadline row is honestly deadline-less rather
    # than back-dated with an invented one.
    # ------------------------------------------------------------------
    """
    CREATE TABLE worker_checkpoint_deadlines (
        checkpoint_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        session_binding_id TEXT NOT NULL DEFAULT '',
        deadline_policy TEXT NOT NULL
            CHECK(deadline_policy IN ('bounded', 'explicit_none')),
        deadline_at TEXT NOT NULL DEFAULT '',
        policy_owner TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        -- A bounded policy must carry a deadline; an unbounded one must name
        -- the owner who accepted that, so "no deadline" is always a decision.
        CHECK(
            (deadline_policy = 'bounded' AND length(deadline_at) > 0)
            OR (deadline_policy = 'explicit_none'
                AND length(deadline_at) = 0
                AND length(policy_owner) > 0)
        ),
        FOREIGN KEY(checkpoint_id)
            REFERENCES task_checkpoints(checkpoint_id) ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_deadlines_due "
    "ON worker_checkpoint_deadlines(deadline_at) WHERE deadline_policy = 'bounded'",
    """
    CREATE TABLE worker_checkpoint_expiries (
        expiry_id TEXT PRIMARY KEY,
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL COLLATE BINARY,
        deadline_at TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        disposition TEXT NOT NULL
            CHECK(disposition IN ('recorded', 'quiescent_confirmed', 'uncertain')),
        quiescence_proof_ref TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '',
        evidence_hash TEXT NOT NULL CHECK(length(evidence_hash) = 64),
        created_at TEXT NOT NULL,
        -- The accepted rule, enforced by the store rather than by prose: the
        -- only disposition that may later authorise releasing ownership cannot
        -- be written without a proof that the worker is quiescent or dead.
        CHECK(
            disposition <> 'quiescent_confirmed'
            OR length(quiescence_proof_ref) > 0
        ),
        UNIQUE(checkpoint_id, idempotency_key),
        FOREIGN KEY(checkpoint_id)
            REFERENCES task_checkpoints(checkpoint_id) ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_expiries_checkpoint "
    "ON worker_checkpoint_expiries(checkpoint_id, created_at)",
    # ------------------------------------------------------------------
    # Raw provider usage.
    #
    # Token columns are nullable on purpose: NULL means the provider did not
    # report the figure, which is not the same fact as a reported zero. Cost is
    # stored as the provider's own text so no float rounding enters the
    # evidence, and no Codex token count is ever converted into a dollar value.
    # ------------------------------------------------------------------
    """
    CREATE TABLE worker_usage_events (
        usage_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_binding_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        provider TEXT NOT NULL COLLATE BINARY,
        native_session_id TEXT NOT NULL COLLATE BINARY,
        event_kind TEXT NOT NULL,
        provider_event_id TEXT NOT NULL DEFAULT '' COLLATE BINARY,
        sequence INTEGER NOT NULL CHECK(sequence >= 0),
        dedupe_key TEXT NOT NULL CHECK(length(dedupe_key) = 64),
        input_tokens INTEGER,
        cached_input_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        provider_reported_cost_usd TEXT,
        raw_event_hash TEXT NOT NULL CHECK(length(raw_event_hash) = 64),
        raw_event_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        -- Resume replays provider events. Deterministic dedupe identity makes
        -- that replay a no-op instead of double counting.
        UNIQUE(session_binding_id, dedupe_key),
        FOREIGN KEY(session_binding_id)
            REFERENCES worker_provider_sessions(session_binding_id)
            ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_usage_session "
    "ON worker_usage_events(session_binding_id, sequence)",
    "CREATE INDEX idx_worker_usage_task ON worker_usage_events(task_id, created_at)",
    "CREATE INDEX idx_worker_usage_run ON worker_usage_events(run_id, created_at)",
    # ------------------------------------------------------------------
    # Provider-child process identity.
    #
    # RunStore keeps one canonical worker process per run. A provider session is
    # a tree beneath it, so this table records observations of that tree. It
    # holds no lease, requests no cancellation, and grants no ownership.
    # ------------------------------------------------------------------
    """
    CREATE TABLE worker_child_processes (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_binding_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('provider_root', 'owned_descendant')),
        pid INTEGER NOT NULL CHECK(pid > 0),
        process_start_identity TEXT NOT NULL COLLATE BINARY,
        parent_pid INTEGER,
        image_name TEXT NOT NULL DEFAULT '',
        observed_at TEXT NOT NULL,
        observation_source TEXT NOT NULL DEFAULT '',
        -- A PID alone is not identity. Recording the start identity beside it
        -- lets a later package prove a reused PID is a different process.
        CHECK(length(process_start_identity) > 0),
        UNIQUE(session_binding_id, pid, process_start_identity),
        FOREIGN KEY(session_binding_id)
            REFERENCES worker_provider_sessions(session_binding_id)
            ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_children_session "
    "ON worker_child_processes(session_binding_id, role)",
)

_MIGRATION_0002: Final[tuple[str, ...]] = (
    # Generic message identity. Historical worker_interactions remain readable;
    # no old row is backfilled with invented sender, recipient, mandate, command,
    # or attempt evidence.
    """
    CREATE TABLE worker_messages (
        message_id TEXT PRIMARY KEY,
        command_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        session_binding_id TEXT NOT NULL,
        checkpoint_id TEXT NOT NULL DEFAULT '',
        sender_ref TEXT NOT NULL COLLATE BINARY,
        recipient_ref TEXT NOT NULL COLLATE BINARY,
        mandate_ref TEXT NOT NULL DEFAULT '' COLLATE BINARY,
        mandate_version TEXT NOT NULL DEFAULT '' COLLATE BINARY,
        message_class TEXT NOT NULL CHECK(message_class IN (
            'command', 'decision', 'progress_report', 'evidence_submission',
            'outcome_proposal', 'cancellation'
        )),
        command_kind TEXT NOT NULL CHECK(command_kind IN ('steer', 'supply_input')),
        idempotency_key TEXT NOT NULL COLLATE BINARY,
        payload_ref TEXT NOT NULL,
        payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
        payload_bytes INTEGER NOT NULL CHECK(payload_bytes >= 0),
        requested_state_version INTEGER NOT NULL CHECK(requested_state_version >= 0),
        contract_hash TEXT NOT NULL CHECK(length(contract_hash) = 64),
        disposition TEXT NOT NULL CHECK(disposition IN (
            'reserved', 'acknowledged', 'rejected', 'uncertain',
            'message_cancelled', 'expired', 'superseded'
        )),
        disposition_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(length(project_id) > 0),
        CHECK(length(resource_id) > 0),
        CHECK(length(run_id) > 0),
        CHECK(length(sender_ref) > 0),
        CHECK(length(recipient_ref) > 0),
        UNIQUE(command_id),
        UNIQUE(task_id, command_kind, idempotency_key),
        FOREIGN KEY(command_id) REFERENCES task_commands(command_id) ON DELETE CASCADE,
        FOREIGN KEY(session_binding_id)
            REFERENCES worker_provider_sessions(session_binding_id)
            ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_messages_session "
    "ON worker_messages(session_binding_id, created_at)",
    "CREATE INDEX idx_worker_messages_disposition "
    "ON worker_messages(disposition, created_at)",
    # A message receives at most one durable transport claim. Outcome-unknown
    # evidence remains on that same row and therefore cannot create a resend.
    """
    CREATE TABLE worker_transport_attempts (
        attempt_id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL,
        claimer_id TEXT NOT NULL COLLATE BINARY,
        attempt_state TEXT NOT NULL CHECK(attempt_state IN (
            'claimed', 'outcome_unknown', 'acknowledged', 'rejected', 'prevented'
        )),
        reason TEXT NOT NULL DEFAULT '',
        evidence_ref TEXT NOT NULL DEFAULT '',
        claimed_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        terminal_at TEXT,
        CHECK(length(claimer_id) > 0),
        UNIQUE(message_id),
        FOREIGN KEY(message_id) REFERENCES worker_messages(message_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_worker_attempts_state "
    "ON worker_transport_attempts(attempt_state, claimed_at)",
)

WORKER_SUBSTRATE_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "interactive_worker_substrate_foundation", _MIGRATION_0001),
    (2, "interaction_message_and_transport_attempt", _MIGRATION_0002),
)

WORKER_SUBSTRATE_TABLE_NAMES: Final[tuple[str, ...]] = (
    "worker_provider_sessions",
    "worker_interactions",
    "worker_checkpoint_deadlines",
    "worker_checkpoint_expiries",
    "worker_usage_events",
    "worker_child_processes",
    "worker_messages",
    "worker_transport_attempts",
)


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(MIGRATION_TABLE_SQL)
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (WORKER_SUBSTRATE_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = _applied_versions(conn)
    return max(versions) if versions else 0


def apply_worker_substrate_migrations(
    connect: Callable[[], sqlite3.Connection],
) -> list[int]:
    """Apply each version once, rechecking after the write lock is acquired."""
    applied: list[int] = []
    for version, name, statements in WORKER_SUBSTRATE_MIGRATIONS:
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(MIGRATION_TABLE_SQL)
                row = conn.execute(
                    "SELECT 1 FROM soma_schema_migrations "
                    "WHERE component = ? AND version = ?",
                    (WORKER_SUBSTRATE_SCHEMA_COMPONENT, version),
                ).fetchone()
                if row is not None:
                    conn.commit()
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO soma_schema_migrations "
                    "(component, version, name, applied_at) VALUES (?, ?, ?, ?)",
                    (WORKER_SUBSTRATE_SCHEMA_COMPONENT, version, name, utc_now()),
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
        "component": WORKER_SUBSTRATE_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": WORKER_SUBSTRATE_SCHEMA_VERSION,
        "up_to_date": version >= WORKER_SUBSTRATE_SCHEMA_VERSION,
        "tables": [name for name in WORKER_SUBSTRATE_TABLE_NAMES if name in present],
        "missing_tables": [
            name for name in WORKER_SUBSTRATE_TABLE_NAMES if name not in present
        ],
    }
