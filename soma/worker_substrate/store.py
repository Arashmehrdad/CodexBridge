"""Subordinate persistence for the interactive worker substrate.

Authority boundary, enforced by construction rather than by convention: this
store issues no ``INSERT`` or ``UPDATE`` against ``tasks``, ``runs``,
``task_commands``, ``task_checkpoints``, or any ProjectScope table. It reads
canonical task, run, checkpoint, and ProjectScope identity only to fail closed
before writing subordinate evidence, and writes only worker-substrate tables.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

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
    MessageClass,
    MessageDisposition,
    ProviderChildProcessRecord,
    ProviderChildRole,
    ProviderSessionBinding,
    SessionBindingDisposition,
    TransportAttemptRecord,
    TransportAttemptState,
    UsageEvent,
    WorkerMessageRecord,
    canonical_json,
    content_hash,
    make_interaction_id,
    make_message_id,
    make_session_binding_id,
    make_transport_attempt_id,
    message_contract_hash,
    normalize_message_contract,
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
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

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


class CanonicalBindingMismatch(ValueError):
    """Submitted subordinate identity does not match canonical Task -> Run scope."""


class EvidenceConflict(ValueError):
    """One immutable or idempotent evidence identity was replayed differently."""

    def __init__(self, record_kind: str, identity: str, detail: str) -> None:
        super().__init__(
            f"{record_kind} {identity!r} conflicts with durable evidence: {detail}"
        )
        self.record_kind = record_kind
        self.identity = identity
        self.detail = detail


class InteractionConflict(ValueError):
    """Same caller idempotency identity replayed with a different command contract."""

    def __init__(
        self,
        existing: InteractionRecord,
        submitted_hash: str,
        mismatched_fields: tuple[str, ...] = (),
    ) -> None:
        detail = ", ".join(mismatched_fields) or "payload_hash"
        super().__init__(
            f"idempotency_key {existing.idempotency_key!r} on task "
            f"{existing.task_id} is already bound to interaction "
            f"{existing.interaction_id}; conflicting fields: {detail}"
        )
        self.existing = existing
        self.submitted_hash = submitted_hash
        self.mismatched_fields = tuple(mismatched_fields)


class MessageConflict(ValueError):
    """One complete message idempotency identity was replayed differently."""

    def __init__(
        self, existing: WorkerMessageRecord, submitted_contract_hash: str
    ) -> None:
        super().__init__(
            f"idempotency_key {existing.idempotency_key!r} on task "
            f"{existing.task_id} is already bound to message {existing.message_id} "
            "with a different complete contract"
        )
        self.existing = existing
        self.submitted_contract_hash = submitted_contract_hash


class AttemptClaimBlocked(ValueError):
    """Canonical precedence does not permit a transport attempt to begin."""

    def __init__(self, message_id: str, reason: str) -> None:
        super().__init__(f"transport attempt blocked for {message_id}: {reason}")
        self.message_id = message_id
        self.reason = reason


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

    @staticmethod
    def _require_sha256(value: str, field: str) -> str:
        if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{field} must be a lowercase sha256 hex digest")
        return value

    @staticmethod
    def _parse_timestamp(value: str, field: str) -> datetime:
        if not value:
            raise ValueError(f"{field} is required")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"{field} must include a timezone")
        return parsed.astimezone(timezone.utc)

    def _validate_payload_reference(
        self, ref: str, payload_hash: str, payload_bytes: int
    ) -> Path:
        self._require_sha256(payload_hash, "payload_hash")
        expected_ref = f"{PAYLOAD_REFERENCE_PREFIX}{payload_hash}"
        if ref != expected_ref:
            raise ValueError(
                "payload_ref must be the content-addressed reference for payload_hash"
            )
        path = self.payload_path(ref)
        if not path.is_file():
            raise ValueError(f"payload_ref does not exist: {ref}")
        data = path.read_bytes()
        if len(data) != int(payload_bytes):
            raise ValueError("payload_bytes does not match the referenced payload")
        if content_hash(data) != payload_hash:
            raise ValueError("referenced payload content does not match payload_hash")
        return path

    @staticmethod
    def _verify_payload_target(
        target: Path,
        *,
        digest: str,
        expected_bytes: int,
        timeout_seconds: float = 2.0,
    ) -> None:
        """Wait briefly for one exact immutable winner after a Windows race.

        The write itself is never retried. A concurrent winner is accepted only
        after the target is readable, is a regular file, and matches both the
        expected size and content hash. A mismatched winner fails immediately;
        transient sharing violations are bounded and become explicit evidence
        conflicts rather than guessed success.
        """
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        last_error = ""
        while True:
            try:
                if target.exists() and not target.is_file():
                    raise EvidenceConflict(
                        "worker_payload",
                        digest,
                        "content-addressed target exists but is not a regular file",
                    )
                if target.is_file():
                    winner = target.read_bytes()
                    if len(winner) != int(expected_bytes):
                        raise EvidenceConflict(
                            "worker_payload",
                            digest,
                            "concurrent target has the wrong byte length",
                        )
                    if content_hash(winner) != digest:
                        raise EvidenceConflict(
                            "worker_payload",
                            digest,
                            "concurrent target does not match the submitted hash",
                        )
                    return
            except EvidenceConflict:
                raise
            except OSError as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            if time.monotonic() >= deadline:
                detail = "content-addressed target did not become readable"
                if last_error:
                    detail += f"; last error: {last_error}"
                raise EvidenceConflict("worker_payload", digest, detail)
            time.sleep(0.01)

    def put_payload(self, payload: bytes | str) -> PayloadReference:
        """Store interaction bytes content-addressed, outside the database."""
        data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        digest = content_hash(data)
        target = self.payload_root / digest[:2] / digest
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.{os.getpid()}.{uuid4().hex}.tmp")
            try:
                tmp.write_bytes(data)
                try:
                    os.replace(tmp, target)
                except OSError:
                    # A competing writer may have installed the same immutable
                    # target but Windows can keep it briefly unreadable. Verify
                    # that winner below; never retry or overwrite the target.
                    pass
            finally:
                if tmp.exists():
                    tmp.unlink()
        self._verify_payload_target(
            target,
            digest=digest,
            expected_bytes=len(data),
        )
        return PayloadReference(
            ref=f"{PAYLOAD_REFERENCE_PREFIX}{digest}",
            payload_hash=digest,
            payload_bytes=len(data),
        )


    def payload_path(self, ref: str) -> Path:
        if not ref.startswith(PAYLOAD_REFERENCE_PREFIX):
            raise ValueError(f"Not a worker payload reference: {ref!r}")
        digest = ref[len(PAYLOAD_REFERENCE_PREFIX) :]
        self._require_sha256(digest, "payload reference digest")
        return self.payload_root / digest[:2] / digest


    def read_payload(self, ref: str) -> bytes:
        path = self.payload_path(ref)
        data = path.read_bytes()
        digest = ref[len(PAYLOAD_REFERENCE_PREFIX) :]
        if content_hash(data) != digest:
            raise ValueError(f"worker payload integrity mismatch: {ref}")
        return data


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
    def _row_to_message(row: sqlite3.Row) -> WorkerMessageRecord:
        return WorkerMessageRecord.model_validate(dict(row))

    @staticmethod
    def _row_to_attempt(row: sqlite3.Row) -> TransportAttemptRecord:
        data = dict(row)
        data["state"] = data.pop("attempt_state")
        return TransportAttemptRecord.model_validate(data)

    @staticmethod
    def _row_to_usage(row: sqlite3.Row) -> UsageEvent:
        data = dict(row)
        data["raw_event"] = _loads(data.pop("raw_event_json", "{}"))
        return UsageEvent.model_validate(data)

    # ------------------------------------------------------------------
    # canonical identity guards (read-only)
    # ------------------------------------------------------------------

    @staticmethod
    def _require_canonical_task_run_scope(
        conn: sqlite3.Connection,
        *,
        project_id: str,
        resource_id: str,
        task_id: str,
        run_id: str,
    ) -> None:
        required_tables = {
            "runs",
            "project_task_reservations",
            "project_run_attempts",
            "project_repository_bindings",
        }
        present = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(required_tables - present)
        if missing:
            raise CanonicalBindingMismatch(
                f"canonical identity tables are unavailable: {missing}"
            )

        task = conn.execute(
            "SELECT backend_ref FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if task is None:
            raise CanonicalBindingMismatch(f"canonical task not found: {task_id}")
        if str(task["backend_ref"] or "") != run_id:
            raise CanonicalBindingMismatch(
                f"task {task_id} is not attached to canonical run {run_id}"
            )

        run = conn.execute(
            "SELECT repo_name FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run is None:
            raise CanonicalBindingMismatch(f"canonical run not found: {run_id}")

        scope = conn.execute(
            """
            SELECT repository.repo_name
            FROM project_run_attempts attempt
            JOIN project_task_reservations reservation
              ON reservation.project_id = attempt.project_id
             AND reservation.task_id = attempt.task_id
            JOIN project_repository_bindings repository
              ON repository.project_id = attempt.project_id
             AND repository.resource_id = attempt.resource_id
            WHERE attempt.project_id = ?
              AND attempt.task_id = ?
              AND attempt.run_id = ?
              AND attempt.resource_id = ?
              AND attempt.status != 'quarantined'
              AND reservation.status != 'quarantined'
            """,
            (project_id, task_id, run_id, resource_id),
        ).fetchone()
        if scope is None:
            raise CanonicalBindingMismatch(
                "project/task/run/resource identity does not match ProjectScope"
            )
        if str(scope["repo_name"]) != str(run["repo_name"]):
            raise CanonicalBindingMismatch(
                "canonical run repository does not match its ProjectScope resource"
            )

    @staticmethod
    def _require_binding_identity(
        conn: sqlite3.Connection,
        session_binding_id: str,
        *,
        task_id: str = "",
        run_id: str = "",
        provider: str = "",
        native_session_id: str = "",
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM worker_provider_sessions WHERE session_binding_id = ?",
            (session_binding_id,),
        ).fetchone()
        if row is None:
            raise CanonicalBindingMismatch(
                f"provider-session binding not found: {session_binding_id}"
            )
        expected = {
            "task_id": task_id,
            "run_id": run_id,
            "provider": provider,
            "native_session_id": native_session_id,
        }
        mismatches = [
            field for field, value in expected.items()
            if value and str(row[field]) != value
        ]
        if mismatches:
            raise CanonicalBindingMismatch(
                "provider-session binding mismatch for " + ", ".join(mismatches)
            )
        return row

    @staticmethod
    def _require_checkpoint_identity(
        conn: sqlite3.Connection,
        *,
        checkpoint_id: str,
        task_id: str,
        session_binding_id: str = "",
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM task_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise CanonicalBindingMismatch(
                f"canonical checkpoint not found: {checkpoint_id}"
            )
        if str(row["task_id"]) != task_id:
            raise CanonicalBindingMismatch(
                "checkpoint does not belong to the submitted task"
            )
        if session_binding_id:
            WorkerSubstrateStore._require_binding_identity(
                conn, session_binding_id, task_id=task_id
            )
        return row

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
        """Bind one exact canonical task/run/scope to one provider-native session."""
        require_opaque(provider, "provider")
        require_opaque(native_session_id, "native_session_id")
        require_opaque(adapter_id, "adapter_id")
        require_opaque(protocol_id, "protocol_id")
        require_opaque(run_id, "run_id")
        require_opaque(task_id, "task_id")
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
            self._require_canonical_task_run_scope(
                conn,
                project_id=project_id,
                resource_id=resource_id,
                task_id=task_id,
                run_id=run_id,
            )
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
                    binding_id, project_id, resource_id, task_id, run_id,
                    provider, native_session_id, adapter_id, adapter_version,
                    protocol_id, protocol_version,
                    SessionBindingDisposition.BOUND.value,
                    resume_cursor, now, now,
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
    # generic message reservation and transport attempts
    # ------------------------------------------------------------------

    def reserve_message_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        command_id: str,
        project_id: str,
        resource_id: str,
        task_id: str,
        run_id: str,
        session_binding_id: str,
        checkpoint_id: str,
        sender_ref: str,
        recipient_ref: str,
        mandate_ref: str,
        mandate_version: str,
        message_class: MessageClass,
        command_kind: str,
        idempotency_key: str,
        payload_ref: str,
        payload_hash: str,
        payload_bytes: int,
        requested_state_version: int,
        contract_hash: str,
    ) -> tuple[WorkerMessageRecord, bool]:
        """Reserve one subordinate message inside a shared main-store transaction."""
        for value, field in (
            (command_id, "command_id"),
            (project_id, "project_id"),
            (resource_id, "resource_id"),
            (task_id, "task_id"),
            (run_id, "run_id"),
            (session_binding_id, "session_binding_id"),
            (sender_ref, "sender_ref"),
            (recipient_ref, "recipient_ref"),
            (idempotency_key, "idempotency_key"),
        ):
            require_opaque(value, field)
        if mandate_ref:
            require_opaque(mandate_ref, "mandate_ref")
        if int(requested_state_version) < 0:
            raise ValueError("requested_state_version must be non-negative")
        if command_kind not in {"steer", "supply_input"}:
            raise ValueError("command_kind must be steer or supply_input")

        self._require_sha256(contract_hash, "contract_hash")
        self._validate_payload_reference(payload_ref, payload_hash, int(payload_bytes))
        contract = normalize_message_contract(
            project_id=project_id,
            resource_id=resource_id,
            task_id=task_id,
            run_id=run_id,
            session_binding_id=session_binding_id,
            checkpoint_id=checkpoint_id,
            sender_ref=sender_ref,
            recipient_ref=recipient_ref,
            mandate_ref=mandate_ref,
            mandate_version=mandate_version,
            message_class=message_class,
            command_kind=command_kind,
            idempotency_key=idempotency_key,
            payload_ref=payload_ref,
            payload_hash=payload_hash,
            payload_bytes=int(payload_bytes),
            requested_state_version=int(requested_state_version),
        )
        computed_hash = message_contract_hash(contract)
        if computed_hash != contract_hash:
            raise ValueError("contract_hash does not match the complete message contract")

        self._require_canonical_task_run_scope(
            conn,
            project_id=project_id,
            resource_id=resource_id,
            task_id=task_id,
            run_id=run_id,
        )
        self._require_binding_identity(
            conn,
            session_binding_id,
            task_id=task_id,
            run_id=run_id,
        )
        if checkpoint_id:
            self._require_checkpoint_identity(
                conn,
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                session_binding_id=session_binding_id,
            )

        command = conn.execute(
            "SELECT task_id, command_kind, controller_request_id, "
            "requested_state_version FROM task_commands WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if command is None:
            raise CanonicalBindingMismatch(f"canonical command not found: {command_id}")
        command_identity = (
            str(command["task_id"]),
            str(command["command_kind"]),
            str(command["controller_request_id"]),
            int(command["requested_state_version"]),
        )
        submitted_identity = (
            task_id,
            command_kind,
            idempotency_key,
            int(requested_state_version),
        )
        if command_identity != submitted_identity:
            raise CanonicalBindingMismatch(
                "canonical command identity does not match the message contract"
            )

        existing_row = conn.execute(
            "SELECT * FROM worker_messages WHERE task_id = ? "
            "AND command_kind = ? AND idempotency_key = ?",
            (task_id, command_kind, idempotency_key),
        ).fetchone()
        if existing_row is not None:
            existing = self._row_to_message(existing_row)
            if (
                existing.contract_hash != contract_hash
                or existing.command_id != command_id
            ):
                raise MessageConflict(existing, contract_hash)
            return existing, False

        now = utc_now()
        message_id = make_message_id()
        conn.execute(
            """
            INSERT INTO worker_messages (
                message_id, command_id, project_id, resource_id, task_id, run_id,
                session_binding_id, checkpoint_id, sender_ref, recipient_ref,
                mandate_ref, mandate_version, message_class, command_kind,
                idempotency_key, payload_ref, payload_hash, payload_bytes,
                requested_state_version, contract_hash, disposition,
                disposition_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, '', ?, ?)
            """,
            (
                message_id,
                command_id,
                project_id,
                resource_id,
                task_id,
                run_id,
                session_binding_id,
                checkpoint_id,
                sender_ref,
                recipient_ref,
                mandate_ref,
                mandate_version,
                message_class.value,
                command_kind,
                idempotency_key,
                payload_ref,
                payload_hash,
                int(payload_bytes),
                int(requested_state_version),
                contract_hash,
                MessageDisposition.RESERVED.value,
                now,
                now,
            ),
        )
        created = conn.execute(
            "SELECT * FROM worker_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return self._row_to_message(created), True

    def get_message(self, message_id: str) -> WorkerMessageRecord:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_messages WHERE message_id = ?", (message_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Worker message not found: {message_id}")
        return self._row_to_message(row)

    def list_messages(self, *, task_id: str = "") -> list[WorkerMessageRecord]:
        sql = "SELECT * FROM worker_messages"
        params: tuple[Any, ...] = ()
        if task_id:
            sql += " WHERE task_id = ?"
            params = (task_id,)
        sql += " ORDER BY created_at ASC, message_id ASC"
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_message(row) for row in rows]

    @staticmethod
    def _message_claim_blocker(
        conn: sqlite3.Connection, message: WorkerMessageRecord
    ) -> str:
        blocker = WorkerSubstrateStore._terminal_blocker(conn, message.task_id)
        if blocker:
            return blocker
        task = conn.execute(
            "SELECT state FROM tasks WHERE task_id = ?", (message.task_id,)
        ).fetchone()
        state = str(task["state"])
        if state in {"cancellation_pending", "recovery_pending", "uncertain"}:
            return f"task_not_dispatchable:{state}"
        binding = conn.execute(
            "SELECT disposition FROM worker_provider_sessions "
            "WHERE session_binding_id = ?",
            (message.session_binding_id,),
        ).fetchone()
        if binding is None or str(binding["disposition"]) != "bound":
            return "session_binding_not_bound"
        if message.checkpoint_id:
            checkpoint = conn.execute(
                "SELECT status FROM task_checkpoints WHERE checkpoint_id = ?",
                (message.checkpoint_id,),
            ).fetchone()
            if checkpoint is None or str(checkpoint["status"]) != "open":
                return "checkpoint_not_open"
            expired = conn.execute(
                "SELECT 1 FROM worker_checkpoint_expiries "
                "WHERE checkpoint_id = ? LIMIT 1",
                (message.checkpoint_id,),
            ).fetchone()
            if expired is not None:
                return "checkpoint_expired"
        return ""

    def claim_transport_attempt(
        self, message_id: str, *, claimer_id: str
    ) -> tuple[TransportAttemptRecord, bool]:
        """Claim the sole transport attempt, or return the identical prior claim."""
        require_opaque(claimer_id, "claimer_id")
        with self._transaction() as conn:
            message_row = conn.execute(
                "SELECT * FROM worker_messages WHERE message_id = ?", (message_id,)
            ).fetchone()
            if message_row is None:
                raise KeyError(f"Worker message not found: {message_id}")
            message = self._row_to_message(message_row)

            existing_row = conn.execute(
                "SELECT * FROM worker_transport_attempts WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            if existing_row is not None:
                existing = self._row_to_attempt(existing_row)
                if existing.claimer_id != claimer_id:
                    raise EvidenceConflict(
                        "transport_attempt",
                        message_id,
                        "message already claimed by a different sender",
                    )
                return existing, False

            if message.disposition is not MessageDisposition.RESERVED:
                raise AttemptClaimBlocked(
                    message_id, f"message_disposition:{message.disposition.value}"
                )
            blocker = self._message_claim_blocker(conn, message)
            if blocker:
                raise AttemptClaimBlocked(message_id, blocker)

            now = utc_now()
            attempt_id = make_transport_attempt_id()
            conn.execute(
                """
                INSERT INTO worker_transport_attempts (
                    attempt_id, message_id, claimer_id, attempt_state, reason,
                    evidence_ref, claimed_at, updated_at, terminal_at
                ) VALUES (?, ?, ?, ?, '', '', ?, ?, NULL)
                """,
                (
                    attempt_id,
                    message_id,
                    claimer_id,
                    TransportAttemptState.CLAIMED.value,
                    now,
                    now,
                ),
            )
            created = conn.execute(
                "SELECT * FROM worker_transport_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        return self._row_to_attempt(created), True

    def get_transport_attempt(self, attempt_id: str) -> TransportAttemptRecord:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_transport_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Transport attempt not found: {attempt_id}")
        return self._row_to_attempt(row)

    def list_transport_attempts(
        self, *, message_id: str = ""
    ) -> list[TransportAttemptRecord]:
        sql = "SELECT * FROM worker_transport_attempts"
        params: tuple[Any, ...] = ()
        if message_id:
            sql += " WHERE message_id = ?"
            params = (message_id,)
        sql += " ORDER BY claimed_at ASC, attempt_id ASC"
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_attempt(row) for row in rows]

    def record_transport_attempt(
        self,
        attempt_id: str,
        *,
        state: TransportAttemptState,
        reason: str = "",
        evidence_ref: str = "",
    ) -> TransportAttemptRecord:
        """Record transport evidence without interpreting canonical lifecycle."""
        now = utc_now()
        terminal_states = {
            TransportAttemptState.ACKNOWLEDGED,
            TransportAttemptState.REJECTED,
            TransportAttemptState.PREVENTED,
        }
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM worker_transport_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Transport attempt not found: {attempt_id}")
            record = self._row_to_attempt(row)
            if record.state in terminal_states:
                if record.state is not state:
                    raise EvidenceConflict(
                        "transport_attempt",
                        attempt_id,
                        f"terminal {record.state.value} cannot become {state.value}",
                    )
                return record
            if state is TransportAttemptState.CLAIMED:
                if record.state is TransportAttemptState.CLAIMED:
                    return record
                raise EvidenceConflict(
                    "transport_attempt",
                    attempt_id,
                    f"{record.state.value} cannot return to claimed",
                )
            if (
                record.state is TransportAttemptState.OUTCOME_UNKNOWN
                and state is TransportAttemptState.OUTCOME_UNKNOWN
            ):
                return record

            terminal_at = now if state in terminal_states else None
            conn.execute(
                "UPDATE worker_transport_attempts SET attempt_state = ?, reason = ?, "
                "evidence_ref = ?, updated_at = ?, terminal_at = ? "
                "WHERE attempt_id = ?",
                (state.value, reason, evidence_ref, now, terminal_at, attempt_id),
            )

            disposition_map = {
                TransportAttemptState.OUTCOME_UNKNOWN: MessageDisposition.UNCERTAIN,
                TransportAttemptState.ACKNOWLEDGED: MessageDisposition.ACKNOWLEDGED,
                TransportAttemptState.REJECTED: MessageDisposition.REJECTED,
                TransportAttemptState.PREVENTED: MessageDisposition.REJECTED,
            }
            disposition = disposition_map.get(state)
            if disposition is not None:
                message = conn.execute(
                    "SELECT disposition FROM worker_messages WHERE message_id = ?",
                    (record.message_id,),
                ).fetchone()
                protected = {
                    MessageDisposition.CANCELLED.value,
                    MessageDisposition.EXPIRED.value,
                    MessageDisposition.SUPERSEDED.value,
                }
                if message is not None and str(message["disposition"]) not in protected:
                    conn.execute(
                        "UPDATE worker_messages SET disposition = ?, "
                        "disposition_reason = ?, updated_at = ? WHERE message_id = ?",
                        (disposition.value, reason, now, record.message_id),
                    )

            updated = conn.execute(
                "SELECT * FROM worker_transport_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        return self._row_to_attempt(updated)

    # ------------------------------------------------------------------
    # legacy v1 interaction delivery
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
        """Persist one complete interaction command contract before delivery."""
        require_opaque(idempotency_key, "idempotency_key")
        if int(requested_state_version) < 0:
            raise ValueError("requested_state_version must be non-negative")
        if payload is not None:
            reference = self.put_payload(payload)
            payload_ref = reference.ref
            payload_hash = reference.payload_hash
            payload_bytes = reference.payload_bytes
        self._validate_payload_reference(payload_ref, payload_hash, int(payload_bytes))
        now = utc_now()
        with self._transaction() as conn:
            self._require_binding_identity(conn, session_binding_id, task_id=task_id)
            if expected_checkpoint_id:
                self._require_checkpoint_identity(
                    conn,
                    checkpoint_id=expected_checkpoint_id,
                    task_id=task_id,
                    session_binding_id=session_binding_id,
                )
            row = conn.execute(
                "SELECT * FROM worker_interactions "
                "WHERE task_id = ? AND idempotency_key = ?",
                (task_id, idempotency_key),
            ).fetchone()
            submitted_contract = {
                "session_binding_id": session_binding_id,
                "interaction_kind": interaction_kind.value,
                "payload_ref": payload_ref,
                "payload_hash": payload_hash,
                "payload_bytes": int(payload_bytes),
                "expected_checkpoint_id": expected_checkpoint_id,
                "requested_state_version": int(requested_state_version),
            }
            if row is not None:
                existing = self._row_to_interaction(row)
                existing_contract = {
                    "session_binding_id": existing.session_binding_id,
                    "interaction_kind": existing.interaction_kind.value,
                    "payload_ref": existing.payload_ref,
                    "payload_hash": existing.payload_hash,
                    "payload_bytes": existing.payload_bytes,
                    "expected_checkpoint_id": existing.expected_checkpoint_id,
                    "requested_state_version": existing.requested_state_version,
                }
                mismatches = tuple(
                    field for field, value in submitted_contract.items()
                    if existing_contract[field] != value
                )
                if mismatches:
                    raise InteractionConflict(existing, payload_hash, mismatches)
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
                    interaction_id, session_binding_id, task_id,
                    interaction_kind.value, idempotency_key, payload_ref,
                    payload_hash, int(payload_bytes), expected_checkpoint_id,
                    int(requested_state_version), InteractionDelivery.PENDING.value,
                    now, now,
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
        """Record monotonic delivery evidence without overriding task state."""
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
            terminal = {
                InteractionDelivery.ACKNOWLEDGED,
                InteractionDelivery.REJECTED,
            }
            if record.delivery in terminal:
                if effective is not record.delivery:
                    raise EvidenceConflict(
                        "interaction_delivery",
                        interaction_id,
                        f"terminal {record.delivery.value} cannot become {effective.value}",
                    )
                return record
            if effective is InteractionDelivery.PENDING:
                if record.delivery is InteractionDelivery.PENDING:
                    return record
                raise EvidenceConflict(
                    "interaction_delivery",
                    interaction_id,
                    f"{record.delivery.value} cannot return to pending",
                )
            delivered_at = now if effective in terminal else None
            conn.execute(
                "UPDATE worker_interactions "
                "SET delivery = ?, delivery_reason = ?, delivery_evidence_ref = ?, "
                "updated_at = ?, delivered_at = ? WHERE interaction_id = ?",
                (
                    effective.value, effective_reason, evidence_ref,
                    now, delivered_at, interaction_id,
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

    def set_checkpoint_deadline_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        checkpoint_id: str,
        task_id: str,
        deadline_policy: CheckpointDeadlinePolicy,
        deadline_at: str = "",
        policy_owner: str = "",
        session_binding_id: str = "",
        created_at: str | None = None,
    ) -> CheckpointDeadline:
        """Attach one immutable deadline inside an existing shared transaction."""
        if deadline_policy is CheckpointDeadlinePolicy.BOUNDED:
            self._parse_timestamp(deadline_at, "deadline_at")
        elif deadline_at:
            raise ValueError("explicit_none deadline policy cannot carry deadline_at")
        if deadline_policy is CheckpointDeadlinePolicy.EXPLICIT_NONE and not policy_owner:
            raise ValueError("explicit_none deadline policy requires policy_owner")
        submitted = {
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "session_binding_id": session_binding_id,
            "deadline_policy": deadline_policy.value,
            "deadline_at": deadline_at,
            "policy_owner": policy_owner,
        }
        self._require_checkpoint_identity(
            conn,
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            session_binding_id=session_binding_id,
        )
        row = conn.execute(
            "SELECT * FROM worker_checkpoint_deadlines WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if row is not None:
            existing = dict(row)
            mismatches = [
                field for field, value in submitted.items()
                if str(existing[field]) != str(value)
            ]
            if mismatches:
                raise EvidenceConflict(
                    "checkpoint_deadline",
                    checkpoint_id,
                    "conflicting fields: " + ", ".join(mismatches),
                )
            return CheckpointDeadline.model_validate(existing)
        now = created_at or utc_now()
        conn.execute(
            "INSERT INTO worker_checkpoint_deadlines "
            "(checkpoint_id, task_id, session_binding_id, deadline_policy, "
            "deadline_at, policy_owner, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                checkpoint_id,
                task_id,
                session_binding_id,
                deadline_policy.value,
                deadline_at,
                policy_owner,
                now,
            ),
        )
        created = conn.execute(
            "SELECT * FROM worker_checkpoint_deadlines WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        return CheckpointDeadline.model_validate(dict(created))

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
        """Attach one immutable deadline policy to an exact checkpoint."""
        with self._transaction() as conn:
            return self.set_checkpoint_deadline_in_connection(
                conn,
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                deadline_policy=deadline_policy,
                deadline_at=deadline_at,
                policy_owner=policy_owner,
                session_binding_id=session_binding_id,
            )


    def get_checkpoint_deadline(self, checkpoint_id: str) -> CheckpointDeadline | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_checkpoint_deadlines WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        return None if row is None else CheckpointDeadline.model_validate(dict(row))

    def record_checkpoint_expiry_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        checkpoint_id: str,
        task_id: str,
        idempotency_key: str,
        deadline_at: str,
        observed_at: str,
        disposition: CheckpointExpiryDisposition,
        quiescence_proof_ref: str = "",
        reason: str = "",
        created_at: str | None = None,
    ) -> tuple[CheckpointExpiryEvent, bool]:
        """Record immutable expiry evidence inside a shared transaction."""
        require_opaque(idempotency_key, "idempotency_key")
        observed = self._parse_timestamp(observed_at, "observed_at")
        deadline = self._parse_timestamp(deadline_at, "deadline_at")
        if observed < deadline:
            raise ValueError("observed_at cannot precede deadline_at")
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
        now = created_at or utc_now()
        self._require_checkpoint_identity(
            conn, checkpoint_id=checkpoint_id, task_id=task_id
        )
        deadline_row = conn.execute(
            "SELECT * FROM worker_checkpoint_deadlines WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if deadline_row is None:
            raise CanonicalBindingMismatch(
                "checkpoint expiry cannot exist without a durable deadline policy"
            )
        if str(deadline_row["deadline_at"]) != deadline_at:
            raise CanonicalBindingMismatch(
                "expiry deadline_at does not match the canonical deadline"
            )
        row = conn.execute(
            "SELECT * FROM worker_checkpoint_expiries "
            "WHERE checkpoint_id = ? AND idempotency_key = ?",
            (checkpoint_id, idempotency_key),
        ).fetchone()
        if row is not None:
            existing = CheckpointExpiryEvent.model_validate(dict(row))
            if existing.evidence_hash != evidence_hash:
                raise EvidenceConflict(
                    "checkpoint_expiry",
                    f"{checkpoint_id}:{idempotency_key}",
                    "same idempotency identity carries different evidence",
                )
            return existing, False
        conn.execute(
            "INSERT INTO worker_checkpoint_expiries "
            "(expiry_id, checkpoint_id, task_id, idempotency_key, deadline_at, "
            "observed_at, disposition, quiescence_proof_ref, reason, "
            "evidence_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        """Record exact immutable expiry evidence, idempotently and conflict-safe."""
        with self._transaction() as conn:
            return self.record_checkpoint_expiry_in_connection(
                conn,
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                idempotency_key=idempotency_key,
                deadline_at=deadline_at,
                observed_at=observed_at,
                disposition=disposition,
                quiescence_proof_ref=quiescence_proof_ref,
                reason=reason,
            )


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
        require_opaque(event_kind, "event_kind")
        if int(sequence) < 0:
            raise ValueError("sequence must be non-negative")
        for field, value in (
            ("input_tokens", input_tokens),
            ("cached_input_tokens", cached_input_tokens),
            ("output_tokens", output_tokens),
            ("total_tokens", total_tokens),
        ):
            if value is not None and int(value) < 0:
                raise ValueError(f"{field} must be non-negative when reported")
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
            self._require_binding_identity(
                conn,
                session_binding_id,
                task_id=task_id,
                run_id=run_id,
                provider=provider,
                native_session_id=native_session_id,
            )
            row = conn.execute(
                "SELECT * FROM worker_usage_events "
                "WHERE session_binding_id = ? AND dedupe_key = ?",
                (session_binding_id, dedupe),
            ).fetchone()
            if row is not None:
                existing = self._row_to_usage(row)
                submitted = {
                    "task_id": task_id,
                    "run_id": run_id,
                    "provider": provider,
                    "native_session_id": native_session_id,
                    "event_kind": event_kind,
                    "provider_event_id": provider_event_id,
                    "sequence": int(sequence),
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "provider_reported_cost_usd": provider_reported_cost_usd,
                    "raw_event_hash": raw_event_hash,
                }
                mismatches = [
                    field for field, value in submitted.items()
                    if getattr(existing, field) != value
                ]
                if mismatches:
                    raise EvidenceConflict(
                        "usage_event",
                        dedupe,
                        "conflicting fields: " + ", ".join(mismatches),
                    )
                return existing, False
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
                parsed = Decimal(value)
                if not parsed.is_finite():
                    raise InvalidOperation
                total += parsed
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
        if parent_pid is not None and int(parent_pid) <= 0:
            raise ValueError("parent_pid must be positive when supplied")
        observed = observed_at or utc_now()
        self._parse_timestamp(observed, "observed_at")
        with self._transaction() as conn:
            self._require_binding_identity(
                conn, session_binding_id, task_id=task_id, run_id=run_id
            )
            row = conn.execute(
                "SELECT * FROM worker_child_processes "
                "WHERE session_binding_id = ? AND pid = ? "
                "AND process_start_identity = ?",
                (session_binding_id, int(pid), process_start_identity),
            ).fetchone()
            if row is not None:
                existing = ProviderChildProcessRecord.model_validate(dict(row))
                submitted = {
                    "task_id": task_id,
                    "run_id": run_id,
                    "role": role,
                    "parent_pid": parent_pid,
                    "image_name": image_name,
                    "observation_source": observation_source,
                }
                mismatches = [
                    field for field, value in submitted.items()
                    if getattr(existing, field) != value
                ]
                if mismatches:
                    raise EvidenceConflict(
                        "provider_child_process",
                        f"{session_binding_id}:{pid}:{process_start_identity}",
                        "conflicting fields: " + ", ".join(mismatches),
                    )
                return existing, False
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
