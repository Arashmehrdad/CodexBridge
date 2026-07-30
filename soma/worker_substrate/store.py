"""Subordinate persistence for the interactive worker substrate.

Authority boundary, enforced by construction rather than by convention: this
store issues no ``INSERT`` or ``UPDATE`` against ``tasks``, ``runs``,
``task_commands``, ``task_checkpoints``, or any ProjectScope table. It reads
``tasks`` in exactly one place -- to refuse an acknowledgement that would
contradict a terminal task -- and writes only the six substrate tables.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

from ..tasks.models import TERMINAL_TASK_STATES
from ..tasks.schema import apply_task_migrations
from .models import (
    CheckpointDeadline,
    CheckpointDeadlinePolicy,
    CheckpointExpiryDisposition,
    CheckpointExpiryEvent,
    InteractionDelivery,
    InteractionKind,
    InteractionRecord,
    ProviderChildProcessRecord,
    ProviderChildRole,
    ProviderSessionBinding,
    SessionBindingDisposition,
    UsageEvent,
    canonical_json,
    content_hash,
    make_interaction_id,
    make_session_binding_id,
    require_opaque,
    usage_dedupe_key,
    utc_now,
)
from .schema import (
    apply_worker_substrate_migrations,
    current_schema_version,
    schema_state,
)


PAYLOAD_REFERENCE_PREFIX = "worker_payload:"

_TERMINAL_TASK_STATE_VALUES = frozenset(state.value for state in TERMINAL_TASK_STATES)


class SessionBindingConflict(ValueError):
    """A canonical binding already exists with a different provider identity."""

    def __init__(
        self, existing: ProviderSessionBinding, submitted: dict[str, str]
    ) -> None:
        super().__init__(
            f"run {existing.run_id} is already bound to provider "
            f"{existing.provider!r} session {existing.native_session_id!r}; "
            "refusing to rebind to a different native session"
        )
        self.existing = existing
        self.submitted = dict(submitted)


class InteractionConflict(ValueError):
    """Same caller idempotency identity replayed with different content."""

    def __init__(self, existing: InteractionRecord, submitted_hash: str) -> None:
        super().__init__(
            f"idempotency_key {existing.idempotency_key!r} on task "
            f"{existing.task_id} is already bound to interaction "
            f"{existing.interaction_id} with payload hash "
            f"{existing.payload_hash}, not {submitted_hash}"
        )
        self.existing = existing
        self.submitted_hash = submitted_hash


@dataclass(frozen=True)
class PayloadReference:
    """Content-addressed handle to interaction bytes held outside the database."""

    ref: str
    payload_hash: str
    payload_bytes: int


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}


class WorkerSubstrateStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "soma.sqlite3"
        self.payload_root = self.runs_dir / "worker_substrate" / "payloads"
        self.init_db()

    # ------------------------------------------------------------------
    # connections and schema
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> list[int]:
        """Apply the task plane first, then this component.

        The deadline tables reference ``task_checkpoints``, so the dependency is
        declared here instead of relying on some other component having run.
        Both migration functions are idempotent.
        """
        apply_task_migrations(self.connect)
        return apply_worker_substrate_migrations(self.connect)

    def schema_version(self) -> int:
        with self._read() as conn:
            return current_schema_version(conn)

    def schema_state(self) -> dict[str, Any]:
        with self._read() as conn:
            return dict(schema_state(conn))

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # payload storage
    # ------------------------------------------------------------------

    def put_payload(self, payload: bytes | str) -> PayloadReference:
        """Store interaction bytes content-addressed, outside the database.

        Keeping the payload out of both the row and any argv is what satisfies
        the rule that prompts and secrets never reach a command line. Identical
        content written twice is the same file, so a replay costs nothing.
        """
        data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        digest = content_hash(data)
        target = self.payload_root / digest[:2] / digest
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        return PayloadReference(
            ref=f"{PAYLOAD_REFERENCE_PREFIX}{digest}",
            payload_hash=digest,
            payload_bytes=len(data),
        )

    def payload_path(self, ref: str) -> Path:
        if not ref.startswith(PAYLOAD_REFERENCE_PREFIX):
            raise ValueError(f"Not a worker payload reference: {ref!r}")
        digest = ref[len(PAYLOAD_REFERENCE_PREFIX) :]
        if len(digest) != 64:
            raise ValueError(f"Malformed worker payload reference: {ref!r}")
        return self.payload_root / digest[:2] / digest

    def read_payload(self, ref: str) -> bytes:
        return self.payload_path(ref).read_bytes()

    # ------------------------------------------------------------------
    # row mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_binding(row: sqlite3.Row) -> ProviderSessionBinding:
        return ProviderSessionBinding.model_validate(dict(row))

    @staticmethod
    def _row_to_interaction(row: sqlite3.Row) -> InteractionRecord:
        return InteractionRecord.model_validate(dict(row))

    @staticmethod
    def _row_to_usage(row: sqlite3.Row) -> UsageEvent:
        data = dict(row)
        data["raw_event"] = _loads(data.pop("raw_event_json", "{}"))
        return UsageEvent.model_validate(data)

    # ------------------------------------------------------------------
    # provider-session binding
    # ------------------------------------------------------------------

    def bind_provider_session(
        self,
        *,
        project_id: str,
        resource_id: str,
        task_id: str,
        run_id: str,
        provider: str,
        native_session_id: str,
        adapter_id: str,
        adapter_version: str = "",
        protocol_id: str,
        protocol_version: str = "",
        resume_cursor: str = "",
    ) -> tuple[ProviderSessionBinding, bool]:
        """Bind one canonical run to one exact provider-native session.

        Returns ``(binding, created)``. An identical replay returns the existing
        binding. A replay carrying a different provider, native session, adapter,
        or protocol identity raises :class:`SessionBindingConflict` rather than
        silently rebinding the run to a different conversation.
        """
        require_opaque(provider, "provider")
        require_opaque(native_session_id, "native_session_id")
        require_opaque(adapter_id, "adapter_id")
        require_opaque(protocol_id, "protocol_id")
        require_opaque(run_id, "run_id")
        require_opaque(project_id, "project_id")
        require_opaque(resource_id, "resource_id")

        submitted = {
            "provider": provider,
            "native_session_id": native_session_id,
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "protocol_id": protocol_id,
            "protocol_version": protocol_version,
            "task_id": task_id,
            "project_id": project_id,
            "resource_id": resource_id,
        }
        now = utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_provider_sessions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is not None:
                existing = self._row_to_binding(row)
                for field, value in submitted.items():
                    if getattr(existing, field) != value:
                        raise SessionBindingConflict(existing, submitted)
                return existing, False

            binding_id = make_session_binding_id()
            conn.execute(
                """
                INSERT INTO worker_provider_sessions (
                    session_binding_id, project_id, resource_id, task_id, run_id,
                    provider, native_session_id, adapter_id, adapter_version,
                    protocol_id, protocol_version, disposition, disposition_reason,
                    resume_cursor, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)
                """,
                (
                    binding_id,
                    project_id,
                    resource_id,
                    task_id,
                    run_id,
                    provider,
                    native_session_id,
                    adapter_id,
                    adapter_version,
                    protocol_id,
                    protocol_version,
                    SessionBindingDisposition.BOUND.value,
                    resume_cursor,
                    now,
                    now,
                ),
            )
            created = conn.execute(
                "SELECT * FROM worker_provider_sessions WHERE session_binding_id = ?",
                (binding_id,),
            ).fetchone()
        return self._row_to_binding(created), True

    def get_binding(self, session_binding_id: str) -> ProviderSessionBinding:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_provider_sessions WHERE session_binding_id = ?",
                (session_binding_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session binding not found: {session_binding_id}")
        return self._row_to_binding(row)

    def find_binding_by_run(self, run_id: str) -> ProviderSessionBinding | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_provider_sessions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return None if row is None else self._row_to_binding(row)

    def list_bindings_for_task(self, task_id: str) -> list[ProviderSessionBinding]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM worker_provider_sessions WHERE task_id = ? "
                "ORDER BY created_at ASC, session_binding_id ASC",
                (task_id,),
            ).fetchall()
        return [self._row_to_binding(row) for row in rows]

    def set_binding_disposition(
        self,
        session_binding_id: str,
        *,
        disposition: SessionBindingDisposition,
        reason: str = "",
    ) -> ProviderSessionBinding:
        """Record what Soma can prove about a binding.

        This is deliberately not a state machine: any disposition may follow any
        other, because it describes evidence quality and not progress. Marking a
        binding ``mismatch_detected`` or ``unverified`` changes no task and no
        run; adjudication belongs to the canonical planes.
        """
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE worker_provider_sessions "
                "SET disposition = ?, disposition_reason = ?, updated_at = ? "
                "WHERE session_binding_id = ?",
                (disposition.value, reason, utc_now(), session_binding_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Session binding not found: {session_binding_id}")
            row = conn.execute(
                "SELECT * FROM worker_provider_sessions WHERE session_binding_id = ?",
                (session_binding_id,),
            ).fetchone()
        return self._row_to_binding(row)

    # ------------------------------------------------------------------
    # interaction delivery
    # ------------------------------------------------------------------

    def commit_interaction(
        self,
        *,
        session_binding_id: str,
        task_id: str,
        interaction_kind: InteractionKind,
        idempotency_key: str,
        payload: bytes | str | None = None,
        payload_ref: str = "",
        payload_hash: str = "",
        payload_bytes: int = 0,
        expected_checkpoint_id: str = "",
        requested_state_version: int = 0,
    ) -> tuple[InteractionRecord, bool]:
        """Persist a message before it is delivered.

        Returns ``(record, created)``. A replay with identical content returns
        the committed record so a crash between commit and send can retry
        without producing a second message. A replay with different content
        raises :class:`InteractionConflict`: the caller reused an identity for a
        new intent, and guessing which one it meant would be a delivery bug.
        """
        require_opaque(idempotency_key, "idempotency_key")
        if payload is not None:
            reference = self.put_payload(payload)
            payload_ref = reference.ref
            payload_hash = reference.payload_hash
            payload_bytes = reference.payload_bytes
        if len(payload_hash) != 64:
            raise ValueError("payload_hash must be a sha256 hex digest")
        if not payload_ref:
            raise ValueError("payload_ref is required when payload is not supplied")

        now = utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_interactions "
                "WHERE task_id = ? AND idempotency_key = ?",
                (task_id, idempotency_key),
            ).fetchone()
            if row is not None:
                existing = self._row_to_interaction(row)
                if existing.payload_hash != payload_hash:
                    raise InteractionConflict(existing, payload_hash)
                return existing, False

            interaction_id = make_interaction_id()
            conn.execute(
                """
                INSERT INTO worker_interactions (
                    interaction_id, session_binding_id, task_id, interaction_kind,
                    idempotency_key, payload_ref, payload_hash, payload_bytes,
                    expected_checkpoint_id, requested_state_version, delivery,
                    delivery_reason, delivery_evidence_ref, created_at, updated_at,
                    delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, NULL)
                """,
                (
                    interaction_id,
                    session_binding_id,
                    task_id,
                    interaction_kind.value,
                    idempotency_key,
                    payload_ref,
                    payload_hash,
                    int(payload_bytes),
                    expected_checkpoint_id,
                    int(requested_state_version),
                    InteractionDelivery.PENDING.value,
                    now,
                    now,
                ),
            )
            created = conn.execute(
                "SELECT * FROM worker_interactions WHERE interaction_id = ?",
                (interaction_id,),
            ).fetchone()
        return self._row_to_interaction(created), True

    def get_interaction(self, interaction_id: str) -> InteractionRecord:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_interactions WHERE interaction_id = ?",
                (interaction_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Interaction not found: {interaction_id}")
        return self._row_to_interaction(row)

    def list_interactions(
        self, *, task_id: str = "", session_binding_id: str = ""
    ) -> list[InteractionRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if session_binding_id:
            clauses.append("session_binding_id = ?")
            params.append(session_binding_id)
        sql = "SELECT * FROM worker_interactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, interaction_id ASC"
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_interaction(row) for row in rows]

    def record_delivery(
        self,
        interaction_id: str,
        *,
        delivery: InteractionDelivery,
        reason: str = "",
        evidence_ref: str = "",
    ) -> InteractionRecord:
        """Record the durable delivery disposition for one interaction.

        A late acknowledgement cannot resurrect work: if the canonical task is
        already terminal, or has been superseded by another task, the
        acknowledgement is downgraded to ``rejected`` with the reason preserved.
        The task row itself is read, never written -- refusing here is a
        persistence-boundary guarantee, not a lifecycle decision.
        """
        now = utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_interactions WHERE interaction_id = ?",
                (interaction_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Interaction not found: {interaction_id}")
            record = self._row_to_interaction(row)

            effective = delivery
            effective_reason = reason
            if delivery is InteractionDelivery.ACKNOWLEDGED:
                blocker = self._terminal_blocker(conn, record.task_id)
                if blocker:
                    effective = InteractionDelivery.REJECTED
                    effective_reason = blocker if not reason else f"{blocker}: {reason}"

            delivered_at = (
                now
                if effective
                in {
                    InteractionDelivery.ACKNOWLEDGED,
                    InteractionDelivery.REJECTED,
                }
                else None
            )
            conn.execute(
                "UPDATE worker_interactions "
                "SET delivery = ?, delivery_reason = ?, delivery_evidence_ref = ?, "
                "    updated_at = ?, delivered_at = ? "
                "WHERE interaction_id = ?",
                (
                    effective.value,
                    effective_reason,
                    evidence_ref,
                    now,
                    delivered_at,
                    interaction_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM worker_interactions WHERE interaction_id = ?",
                (interaction_id,),
            ).fetchone()
        return self._row_to_interaction(updated)

    @staticmethod
    def _terminal_blocker(conn: sqlite3.Connection, task_id: str) -> str:
        """Return a reason string when a task may not accept an acknowledgement."""
        row = conn.execute(
            "SELECT state FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return "task_missing"
        state = str(row["state"])
        if state in _TERMINAL_TASK_STATE_VALUES:
            return f"task_terminal:{state}"
        superseded = conn.execute(
            "SELECT 1 FROM task_links "
            "WHERE link_type = 'supersedes' AND target_kind = 'task' "
            "AND target_id = ? LIMIT 1",
            (task_id,),
        ).fetchone()
        if superseded is not None:
            return "task_superseded"
        return ""

    # ------------------------------------------------------------------
    # checkpoint deadlines and expiry evidence
    # ------------------------------------------------------------------

    def set_checkpoint_deadline(
        self,
        *,
        checkpoint_id: str,
        task_id: str,
        deadline_policy: CheckpointDeadlinePolicy,
        deadline_at: str = "",
        policy_owner: str = "",
        session_binding_id: str = "",
    ) -> CheckpointDeadline:
        """Attach a durable deadline to an existing canonical task checkpoint.

        The checkpoint row itself is untouched, so every existing checkpoint read
        returns exactly what it returned before, and a checkpoint with no row
        here is honestly deadline-less.
        """
        now = utc_now()
        with self._transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO worker_checkpoint_deadlines "
                "(checkpoint_id, task_id, session_binding_id, deadline_policy, "
                " deadline_at, policy_owner, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, "
                "        COALESCE((SELECT created_at FROM worker_checkpoint_deadlines "
                "                  WHERE checkpoint_id = ?), ?))",
                (
                    checkpoint_id,
                    task_id,
                    session_binding_id,
                    deadline_policy.value,
                    deadline_at,
                    policy_owner,
                    checkpoint_id,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM worker_checkpoint_deadlines WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        return CheckpointDeadline.model_validate(dict(row))

    def get_checkpoint_deadline(self, checkpoint_id: str) -> CheckpointDeadline | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_checkpoint_deadlines WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        return None if row is None else CheckpointDeadline.model_validate(dict(row))

    def record_checkpoint_expiry(
        self,
        *,
        checkpoint_id: str,
        task_id: str,
        idempotency_key: str,
        deadline_at: str,
        observed_at: str,
        disposition: CheckpointExpiryDisposition,
        quiescence_proof_ref: str = "",
        reason: str = "",
    ) -> tuple[CheckpointExpiryEvent, bool]:
        """Record immutable expiry evidence, idempotently.

        ``QUIESCENT_CONFIRMED`` is refused without a quiescence proof reference.
        That is the persistence half of the accepted rule: ownership may be
        released only once the worker is confirmed quiescent or terminated, and
        anything else is uncertainty that keeps ownership.
        """
        require_opaque(idempotency_key, "idempotency_key")
        if (
            disposition is CheckpointExpiryDisposition.QUIESCENT_CONFIRMED
            and not quiescence_proof_ref
        ):
            raise ValueError(
                "quiescent_confirmed requires a quiescence_proof_ref; without "
                "proof the disposition is uncertainty, not release"
            )
        payload = {
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "idempotency_key": idempotency_key,
            "deadline_at": deadline_at,
            "observed_at": observed_at,
            "disposition": disposition.value,
            "quiescence_proof_ref": quiescence_proof_ref,
            "reason": reason,
        }
        evidence_hash = content_hash(canonical_json(payload).encode("utf-8"))
        expiry_id = f"wexp_{evidence_hash[:24]}"
        now = utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_checkpoint_expiries "
                "WHERE checkpoint_id = ? AND idempotency_key = ?",
                (checkpoint_id, idempotency_key),
            ).fetchone()
            if row is not None:
                return CheckpointExpiryEvent.model_validate(dict(row)), False
            conn.execute(
                "INSERT INTO worker_checkpoint_expiries "
                "(expiry_id, checkpoint_id, task_id, idempotency_key, deadline_at, "
                " observed_at, disposition, quiescence_proof_ref, reason, "
                " evidence_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    expiry_id,
                    checkpoint_id,
                    task_id,
                    idempotency_key,
                    deadline_at,
                    observed_at,
                    disposition.value,
                    quiescence_proof_ref,
                    reason,
                    evidence_hash,
                    now,
                ),
            )
            created = conn.execute(
                "SELECT * FROM worker_checkpoint_expiries WHERE expiry_id = ?",
                (expiry_id,),
            ).fetchone()
        return CheckpointExpiryEvent.model_validate(dict(created)), True

    def list_checkpoint_expiries(self, checkpoint_id: str) -> list[CheckpointExpiryEvent]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM worker_checkpoint_expiries WHERE checkpoint_id = ? "
                "ORDER BY created_at ASC, expiry_id ASC",
                (checkpoint_id,),
            ).fetchall()
        return [CheckpointExpiryEvent.model_validate(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # raw provider usage
    # ------------------------------------------------------------------

    def record_usage_event(
        self,
        *,
        session_binding_id: str,
        task_id: str,
        run_id: str,
        provider: str,
        native_session_id: str,
        event_kind: str,
        sequence: int,
        raw_event: dict[str, Any],
        provider_event_id: str = "",
        input_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        provider_reported_cost_usd: str | None = None,
    ) -> tuple[UsageEvent, bool]:
        """Store one raw provider usage event, deduplicated deterministically.

        Nothing is normalised across providers and nothing absent is invented.
        Claude's ``total_cost_usd`` is preserved as the provider's own text under
        ``provider_reported_cost_usd``; Codex token counts stay token counts,
        with cost left ``None`` until a pricing authority with a reproducible
        conversion exists.
        """
        raw_json = canonical_json(raw_event)
        raw_event_hash = content_hash(raw_json.encode("utf-8"))
        dedupe = usage_dedupe_key(
            provider=provider,
            native_session_id=native_session_id,
            provider_event_id=provider_event_id,
            sequence=sequence,
            raw_event_hash=raw_event_hash,
        )
        now = utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_usage_events "
                "WHERE session_binding_id = ? AND dedupe_key = ?",
                (session_binding_id, dedupe),
            ).fetchone()
            if row is not None:
                return self._row_to_usage(row), False
            cursor = conn.execute(
                """
                INSERT INTO worker_usage_events (
                    session_binding_id, task_id, run_id, provider,
                    native_session_id, event_kind, provider_event_id, sequence,
                    dedupe_key, input_tokens, cached_input_tokens, output_tokens,
                    total_tokens, provider_reported_cost_usd, raw_event_hash,
                    raw_event_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_binding_id,
                    task_id,
                    run_id,
                    provider,
                    native_session_id,
                    event_kind,
                    provider_event_id,
                    int(sequence),
                    dedupe,
                    input_tokens,
                    cached_input_tokens,
                    output_tokens,
                    total_tokens,
                    provider_reported_cost_usd,
                    raw_event_hash,
                    _dumps(raw_event),
                    now,
                ),
            )
            created = conn.execute(
                "SELECT * FROM worker_usage_events WHERE usage_event_id = ?",
                (int(cursor.lastrowid or 0),),
            ).fetchone()
        return self._row_to_usage(created), True

    def list_usage_events(
        self, *, session_binding_id: str = "", task_id: str = "", run_id: str = ""
    ) -> list[UsageEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("session_binding_id", session_binding_id),
            ("task_id", task_id),
            ("run_id", run_id),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM worker_usage_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sequence ASC, usage_event_id ASC"
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_usage(row) for row in rows]

    def aggregate_usage(
        self, *, session_binding_id: str = "", task_id: str = "", run_id: str = ""
    ) -> dict[str, Any]:
        """Aggregate raw usage without inventing a missing figure.

        Sums cover only the events that reported a value, and each sum is
        published beside the count of events that did not report it, so a partial
        total can never be read as a complete one. Provider-reported cost is
        summed with ``Decimal`` over the provider's own strings and is reported
        as a provider figure, never as a Soma-computed price.
        """
        events = self.list_usage_events(
            session_binding_id=session_binding_id, task_id=task_id, run_id=run_id
        )
        summary: dict[str, Any] = {"event_count": len(events)}
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            reported = [
                getattr(event, field)
                for event in events
                if getattr(event, field) is not None
            ]
            summary[field] = sum(reported) if reported else None
            summary[f"{field}_reported_events"] = len(reported)
            summary[f"{field}_missing_events"] = len(events) - len(reported)

        cost_values = [
            event.provider_reported_cost_usd
            for event in events
            if event.provider_reported_cost_usd is not None
        ]
        total = Decimal(0)
        unparsed: list[str] = []
        for value in cost_values:
            try:
                total += Decimal(value)
            except (InvalidOperation, ValueError):
                unparsed.append(value)
        summary["provider_reported_cost_usd"] = (
            str(total) if cost_values and not unparsed else None
        )
        summary["provider_reported_cost_events"] = len(cost_values)
        summary["provider_reported_cost_missing_events"] = len(events) - len(cost_values)
        summary["provider_reported_cost_unparsed"] = unparsed
        return summary

    # ------------------------------------------------------------------
    # provider-child process identity
    # ------------------------------------------------------------------

    def record_child_process(
        self,
        *,
        session_binding_id: str,
        task_id: str,
        run_id: str,
        role: ProviderChildRole,
        pid: int,
        process_start_identity: str,
        parent_pid: int | None = None,
        image_name: str = "",
        observed_at: str = "",
        observation_source: str = "",
    ) -> tuple[ProviderChildProcessRecord, bool]:
        """Persist one observed provider process by PID *and* start identity.

        A PID alone cannot survive PID reuse. ``process_start_identity`` is the
        value produced by :func:`soma.process_control.process_identity`, so a
        later package can prove that a live PID is or is not the process that
        was recorded. Nothing here launches or terminates anything.
        """
        require_opaque(process_start_identity, "process_start_identity")
        if int(pid) <= 0:
            raise ValueError("pid must be positive")
        observed = observed_at or utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_child_processes "
                "WHERE session_binding_id = ? AND pid = ? "
                "AND process_start_identity = ?",
                (session_binding_id, int(pid), process_start_identity),
            ).fetchone()
            if row is not None:
                return ProviderChildProcessRecord.model_validate(dict(row)), False
            cursor = conn.execute(
                "INSERT INTO worker_child_processes "
                "(session_binding_id, task_id, run_id, role, pid, "
                " process_start_identity, parent_pid, image_name, observed_at, "
                " observation_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_binding_id,
                    task_id,
                    run_id,
                    role.value,
                    int(pid),
                    process_start_identity,
                    parent_pid,
                    image_name,
                    observed,
                    observation_source,
                ),
            )
            created = conn.execute(
                "SELECT * FROM worker_child_processes WHERE record_id = ?",
                (int(cursor.lastrowid or 0),),
            ).fetchone()
        return ProviderChildProcessRecord.model_validate(dict(created)), True

    def list_child_processes(
        self, session_binding_id: str
    ) -> list[ProviderChildProcessRecord]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM worker_child_processes WHERE session_binding_id = ? "
                "ORDER BY record_id ASC",
                (session_binding_id,),
            ).fetchall()
        return [ProviderChildProcessRecord.model_validate(dict(row)) for row in rows]
