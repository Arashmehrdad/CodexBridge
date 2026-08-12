"""Durable subordinate persistence for reasoning backend evidence.

This store writes only reasoning-backend evidence tables in the shared Soma
database. It never mutates canonical Task, Run, ProjectScope, or Company Kernel
lifecycle state.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from soma.company_kernel.models import validate_opaque, validate_sha256

from .backends import (
    ReasoningBackendObservationV1,
    ReasoningResultReferenceV1,
    make_start_attempt_id,
    reasoning_spec_hash,
    reasoning_spec_ref,
    start_request_hash,
)
from .models import ReasoningSpecV1
from .schema import (
    apply_reasoning_backend_migrations,
    current_schema_version,
    schema_state,
    utc_now,
)


class ReasoningBackendConflict(ValueError):
    """A durable backend/start identity was replayed with different material."""


class ReasoningBackendStateError(ValueError):
    """A subordinate transition is invalid from the stored backend evidence."""


class ReasoningBackendStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "soma.sqlite3"
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> list[int]:
        return apply_reasoning_backend_migrations(self.connect)

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

    @staticmethod
    def _optional(value: Any) -> str | None:
        text = str(value or "")
        return text or None

    @staticmethod
    def _usage(value: str) -> dict[str, Any] | None:
        try:
            decoded = json.loads(value or "{}")
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) and decoded else None

    def reserve_run(
        self,
        *,
        backend_ref: str,
        spec: ReasoningSpecV1,
        now: str | None = None,
    ) -> bool:
        validate_opaque(backend_ref, "backend_ref", max_length=256)
        spec_ref = reasoning_spec_ref(spec)
        spec_hash = reasoning_spec_hash(spec)
        timestamp = now or utc_now()
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if existing is not None:
                submitted = (
                    spec_ref,
                    spec_hash,
                    spec.provider_route_ref,
                    spec.provider_route_hash,
                )
                durable = (
                    str(existing["reasoning_spec_ref"]),
                    str(existing["reasoning_spec_hash"]),
                    str(existing["provider_route_ref"]),
                    str(existing["provider_route_hash"]),
                )
                if durable != submitted:
                    raise ReasoningBackendConflict(
                        f"backend_ref {backend_ref!r} is already bound to different reasoning material"
                    )
                return False
            conn.execute(
                """
                INSERT INTO reasoning_backend_runs(
                    backend_ref, reasoning_spec_ref, reasoning_spec_hash,
                    provider_route_ref, provider_route_hash,
                    start_delivery_disposition, provider_binding_disposition,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'not_attempted', 'unbound', ?, ?)
                """,
                (
                    backend_ref,
                    spec_ref,
                    spec_hash,
                    spec.provider_route_ref,
                    spec.provider_route_hash,
                    timestamp,
                    timestamp,
                ),
            )
        return True

    def claim_start_attempt(
        self,
        *,
        backend_ref: str,
        spec: ReasoningSpecV1,
        now: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        request_hash = start_request_hash(spec, backend_ref)
        attempt_id = make_start_attempt_id(backend_ref)
        timestamp = now or utc_now()
        with self._transaction() as conn:
            run = conn.execute(
                "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if run is None:
                raise ReasoningBackendStateError(
                    "backend_ref must be reserved before start"
                )
            if str(run["reasoning_spec_ref"]) != reasoning_spec_ref(spec) or str(
                run["reasoning_spec_hash"]
            ) != reasoning_spec_hash(spec):
                raise ReasoningBackendConflict(
                    "start spec does not match reserved backend"
                )
            existing = conn.execute(
                "SELECT * FROM reasoning_backend_start_attempts WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if existing is not None:
                if str(existing["start_request_hash"]) != request_hash:
                    raise ReasoningBackendConflict(
                        "backend start attempt was already claimed for a different request"
                    )
                return dict(existing), False
            conn.execute(
                """
                INSERT INTO reasoning_backend_start_attempts(
                    start_attempt_id, backend_ref, start_request_hash, disposition,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'claimed_not_sent', ?, ?)
                """,
                (attempt_id, backend_ref, request_hash, timestamp, timestamp),
            )
            conn.execute(
                """
                UPDATE reasoning_backend_runs
                SET start_delivery_disposition = 'claimed_not_sent',
                    provider_binding_disposition = 'unbound',
                    provider_status_raw = 'start_claimed_not_sent', updated_at = ?
                WHERE backend_ref = ?
                """,
                (timestamp, backend_ref),
            )
            created = conn.execute(
                "SELECT * FROM reasoning_backend_start_attempts WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            return dict(created), True

    def enter_send_boundary(
        self,
        *,
        backend_ref: str,
        request_hash: str,
        evidence_ref: str,
        evidence_hash: str,
        now: str | None = None,
    ) -> bool:
        """Let exactly one caller cross from safe claim to conservative uncertainty."""

        validate_sha256(request_hash, "request_hash")
        validate_opaque(evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(evidence_hash, "evidence_hash")
        timestamp = now or utc_now()
        with self._transaction() as conn:
            attempt = conn.execute(
                "SELECT * FROM reasoning_backend_start_attempts WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if attempt is None:
                raise ReasoningBackendStateError("start attempt has not been claimed")
            if str(attempt["start_request_hash"]) != request_hash:
                raise ReasoningBackendConflict(
                    "start request hash does not match durable claim"
                )
            if str(attempt["disposition"]) != "claimed_not_sent":
                return False
            cursor = conn.execute(
                """
                UPDATE reasoning_backend_start_attempts
                SET disposition = 'outcome_unknown',
                    outcome_unknown_evidence_ref = ?,
                    outcome_unknown_evidence_hash = ?, updated_at = ?
                WHERE backend_ref = ? AND disposition = 'claimed_not_sent'
                  AND start_request_hash = ?
                """,
                (evidence_ref, evidence_hash, timestamp, backend_ref, request_hash),
            )
            if cursor.rowcount != 1:
                return False
            conn.execute(
                """
                UPDATE reasoning_backend_runs
                SET start_delivery_disposition = 'outcome_unknown',
                    provider_binding_disposition = 'uncertain',
                    provider_status_raw = 'provider_send_boundary_entered',
                    output_contract_disposition = 'uncertain', updated_at = ?
                WHERE backend_ref = ?
                """,
                (timestamp, backend_ref),
            )
        return True

    def record_accepted_bound(
        self,
        *,
        backend_ref: str,
        provider_operation_ref: str,
        provider_binding_ref: str,
        provider_binding_hash: str,
        provider_status_raw: str,
        provider_terminal_claim: str = "none",
        output_contract_disposition: str = "not_available",
        continuation_ref: str = "",
        last_event_cursor: str = "",
        now: str | None = None,
    ) -> None:
        validate_opaque(
            provider_operation_ref, "provider_operation_ref", max_length=2048
        )
        validate_opaque(provider_binding_ref, "provider_binding_ref", max_length=2048)
        validate_sha256(provider_binding_hash, "provider_binding_hash")
        timestamp = now or utc_now()
        with self._transaction() as conn:
            attempt = conn.execute(
                "SELECT disposition FROM reasoning_backend_start_attempts WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if attempt is None:
                raise ReasoningBackendStateError("start attempt does not exist")
            if str(attempt["disposition"]) not in {"outcome_unknown", "accepted_bound"}:
                raise ReasoningBackendStateError(
                    "provider binding may only resolve an entered send boundary"
                )
            conn.execute(
                """
                UPDATE reasoning_backend_start_attempts
                SET disposition = 'accepted_bound', provider_operation_ref = ?, updated_at = ?
                WHERE backend_ref = ?
                """,
                (provider_operation_ref, timestamp, backend_ref),
            )
            conn.execute(
                """
                UPDATE reasoning_backend_runs
                SET start_delivery_disposition = 'accepted_bound',
                    provider_binding_disposition = 'bound',
                    provider_operation_ref = ?, provider_binding_ref = ?,
                    provider_binding_hash = ?, provider_status_raw = ?,
                    provider_terminal_claim = ?, continuation_ref = ?,
                    last_event_cursor = ?, output_contract_disposition = ?,
                    error_code = '', updated_at = ?
                WHERE backend_ref = ?
                """,
                (
                    provider_operation_ref,
                    provider_binding_ref,
                    provider_binding_hash,
                    provider_status_raw,
                    provider_terminal_claim,
                    continuation_ref,
                    last_event_cursor,
                    output_contract_disposition,
                    timestamp,
                    backend_ref,
                ),
            )

    def record_rejected(
        self,
        *,
        backend_ref: str,
        error_code: str,
        provider_status_raw: str = "rejected",
        now: str | None = None,
    ) -> None:
        validate_opaque(error_code, "error_code", max_length=256)
        timestamp = now or utc_now()
        with self._transaction() as conn:
            attempt = conn.execute(
                "SELECT disposition FROM reasoning_backend_start_attempts WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if attempt is None:
                raise ReasoningBackendStateError("start attempt does not exist")
            if str(attempt["disposition"]) not in {"outcome_unknown", "rejected"}:
                raise ReasoningBackendStateError(
                    "definite rejection may only resolve an entered send boundary"
                )
            conn.execute(
                "UPDATE reasoning_backend_start_attempts "
                "SET disposition = 'rejected', updated_at = ? WHERE backend_ref = ?",
                (timestamp, backend_ref),
            )
            conn.execute(
                """
                UPDATE reasoning_backend_runs
                SET start_delivery_disposition = 'rejected',
                    provider_binding_disposition = 'unbound',
                    provider_operation_ref = '', provider_binding_ref = '',
                    provider_binding_hash = '', provider_status_raw = ?,
                    provider_terminal_claim = 'failure',
                    output_contract_disposition = 'not_available',
                    error_code = ?, updated_at = ?
                WHERE backend_ref = ?
                """,
                (provider_status_raw, error_code, timestamp, backend_ref),
            )

    def record_invalid_output(
        self,
        *,
        backend_ref: str,
        provider_operation_ref: str,
        provider_binding_ref: str,
        provider_binding_hash: str,
        error_code: str = "invalid_output_contract",
        now: str | None = None,
    ) -> None:
        self.record_accepted_bound(
            backend_ref=backend_ref,
            provider_operation_ref=provider_operation_ref,
            provider_binding_ref=provider_binding_ref,
            provider_binding_hash=provider_binding_hash,
            provider_status_raw="completed",
            provider_terminal_claim="success",
            output_contract_disposition="invalid",
            now=now,
        )
        timestamp = now or utc_now()
        with self._transaction() as conn:
            conn.execute(
                "UPDATE reasoning_backend_runs SET error_code = ?, updated_at = ? "
                "WHERE backend_ref = ?",
                (error_code, timestamp, backend_ref),
            )

    def publish_result(
        self,
        *,
        backend_ref: str,
        output_contract_version: str,
        evidence_submission_ref: str,
        evidence_submission_hash: str,
        evidence_index_ref: str,
        evidence_index_hash: str,
        provider_provenance_index_ref: str,
        provider_provenance_index_hash: str,
        raw_provider_evidence_root_ref: str,
        raw_provider_evidence_root_hash: str,
        usage_ref: str = "",
        usage_hash: str = "",
        usage_summary: dict[str, Any] | None = None,
        published_at: str | None = None,
    ) -> None:
        validate_opaque(
            output_contract_version, "output_contract_version", max_length=128
        )
        for field, ref, digest in (
            ("evidence_submission", evidence_submission_ref, evidence_submission_hash),
            ("evidence_index", evidence_index_ref, evidence_index_hash),
            (
                "provider_provenance_index",
                provider_provenance_index_ref,
                provider_provenance_index_hash,
            ),
            (
                "raw_provider_evidence_root",
                raw_provider_evidence_root_ref,
                raw_provider_evidence_root_hash,
            ),
        ):
            validate_opaque(ref, f"{field}_ref", max_length=2048)
            validate_sha256(digest, f"{field}_hash")
        if bool(usage_ref) != bool(usage_hash):
            raise ValueError("usage_ref and usage_hash must appear together")
        if usage_ref:
            validate_opaque(usage_ref, "usage_ref", max_length=2048)
            validate_sha256(usage_hash, "usage_hash")
        timestamp = published_at or utc_now()
        usage_json = json.dumps(
            usage_summary or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        with self._transaction() as conn:
            run = conn.execute(
                "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
            if run is None:
                raise ReasoningBackendStateError("backend_ref does not exist")
            if str(run["start_delivery_disposition"]) != "accepted_bound":
                raise ReasoningBackendStateError(
                    "result publication requires accepted provider binding"
                )
            if str(run["provider_binding_disposition"]) != "bound":
                raise ReasoningBackendStateError(
                    "result publication requires exact provider binding"
                )
            if str(run["output_contract_disposition"]) not in {
                "valid",
                "not_available",
            }:
                raise ReasoningBackendStateError(
                    "invalid or uncertain output cannot be published as success"
                )
            conn.execute(
                """
                UPDATE reasoning_backend_runs
                SET provider_status_raw = 'completed', provider_terminal_claim = 'success',
                    output_contract_disposition = 'valid', output_contract_version = ?,
                    result_ref = ?, result_hash = ?,
                    evidence_index_ref = ?, evidence_index_hash = ?,
                    provider_provenance_index_ref = ?, provider_provenance_index_hash = ?,
                    raw_provider_evidence_root_ref = ?, raw_provider_evidence_root_hash = ?,
                    usage_ref = ?, usage_hash = ?, usage_summary_json = ?,
                    error_code = '', result_published_at = ?, updated_at = ?
                WHERE backend_ref = ?
                """,
                (
                    output_contract_version,
                    evidence_submission_ref,
                    evidence_submission_hash,
                    evidence_index_ref,
                    evidence_index_hash,
                    provider_provenance_index_ref,
                    provider_provenance_index_hash,
                    raw_provider_evidence_root_ref,
                    raw_provider_evidence_root_hash,
                    usage_ref,
                    usage_hash,
                    usage_json,
                    timestamp,
                    timestamp,
                    backend_ref,
                ),
            )

    def record_terminal_evidence(
        self,
        *,
        backend_ref: str,
        raw_provider_evidence_root_ref: str,
        raw_provider_evidence_root_hash: str,
        error_code: str,
        now: str | None = None,
    ) -> None:
        validate_opaque(
            raw_provider_evidence_root_ref,
            "raw_provider_evidence_root_ref",
            max_length=2048,
        )
        validate_sha256(
            raw_provider_evidence_root_hash, "raw_provider_evidence_root_hash"
        )
        validate_opaque(error_code, "error_code", max_length=256)
        timestamp = now or utc_now()
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE reasoning_backend_runs SET raw_provider_evidence_root_ref = ?, "
                "raw_provider_evidence_root_hash = ?, error_code = ?, updated_at = ? "
                "WHERE backend_ref = ?",
                (
                    raw_provider_evidence_root_ref,
                    raw_provider_evidence_root_hash,
                    error_code,
                    timestamp,
                    backend_ref,
                ),
            )
            if cursor.rowcount != 1:
                raise ReasoningBackendStateError("backend_ref does not exist")

    def record_cancelled(
        self,
        *,
        backend_ref: str,
        evidence_ref: str,
        evidence_hash: str,
        now: str | None = None,
    ) -> None:
        self._record_cancellation(
            backend_ref=backend_ref,
            disposition="accepted",
            evidence_ref=evidence_ref,
            evidence_hash=evidence_hash,
            provider_status_raw="cancelled",
            terminal_claim="cancelled",
            now=now,
        )

    def record_cancellation_rejected(
        self,
        *,
        backend_ref: str,
        evidence_ref: str,
        evidence_hash: str,
        now: str | None = None,
    ) -> None:
        self._record_cancellation(
            backend_ref=backend_ref,
            disposition="rejected",
            evidence_ref=evidence_ref,
            evidence_hash=evidence_hash,
            now=now,
        )

    def record_cancellation_uncertain(
        self,
        *,
        backend_ref: str,
        evidence_ref: str,
        evidence_hash: str,
        now: str | None = None,
    ) -> None:
        self._record_cancellation(
            backend_ref=backend_ref,
            disposition="uncertain",
            evidence_ref=evidence_ref,
            evidence_hash=evidence_hash,
            now=now,
        )

    def _record_cancellation(
        self,
        *,
        backend_ref: str,
        disposition: str,
        evidence_ref: str,
        evidence_hash: str,
        provider_status_raw: str | None = None,
        terminal_claim: str | None = None,
        now: str | None = None,
    ) -> None:
        validate_opaque(evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(evidence_hash, "evidence_hash")
        timestamp = now or utc_now()
        assignments = [
            "cancellation_disposition = ?",
            "cancellation_evidence_ref = ?",
            "cancellation_evidence_hash = ?",
            "cancellation_requested_at = ?",
            "updated_at = ?",
        ]
        values: list[Any] = [
            disposition,
            evidence_ref,
            evidence_hash,
            timestamp,
            timestamp,
        ]
        if provider_status_raw is not None:
            assignments.append("provider_status_raw = ?")
            values.append(provider_status_raw)
        if terminal_claim is not None:
            assignments.append("provider_terminal_claim = ?")
            values.append(terminal_claim)
        values.append(backend_ref)
        with self._transaction() as conn:
            cursor = conn.execute(
                f"UPDATE reasoning_backend_runs SET {', '.join(assignments)} "
                "WHERE backend_ref = ?",
                tuple(values),
            )
            if cursor.rowcount != 1:
                raise ReasoningBackendStateError("backend_ref does not exist")

    def query(self, backend_ref: str) -> ReasoningBackendObservationV1:
        if not backend_ref:
            return ReasoningBackendObservationV1(backend_ref="missing", exists=False)
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
        if row is None:
            return ReasoningBackendObservationV1(backend_ref=backend_ref, exists=False)
        return ReasoningBackendObservationV1(
            backend_ref=backend_ref,
            exists=True,
            start_delivery_disposition=str(row["start_delivery_disposition"]),
            provider_binding_disposition=str(row["provider_binding_disposition"]),
            provider_operation_ref=self._optional(row["provider_operation_ref"]),
            provider_status_raw=self._optional(row["provider_status_raw"]),
            provider_terminal_claim=str(row["provider_terminal_claim"]),
            continuation_ref=self._optional(row["continuation_ref"]),
            last_event_cursor=self._optional(row["last_event_cursor"]),
            output_contract_disposition=str(row["output_contract_disposition"]),
            result_ref=self._optional(row["result_ref"]),
            result_hash=self._optional(row["result_hash"]),
            evidence_index_ref=self._optional(row["evidence_index_ref"]),
            evidence_index_hash=self._optional(row["evidence_index_hash"]),
            raw_provider_evidence_root_ref=self._optional(
                row["raw_provider_evidence_root_ref"]
            ),
            raw_provider_evidence_root_hash=self._optional(
                row["raw_provider_evidence_root_hash"]
            ),
            usage_summary=self._usage(str(row["usage_summary_json"])),
            error_code=self._optional(row["error_code"]),
            cancellation_disposition=str(row["cancellation_disposition"]),
            cancellation_evidence_ref=self._optional(row["cancellation_evidence_ref"]),
            cancellation_evidence_hash=self._optional(
                row["cancellation_evidence_hash"]
            ),
        )

    def result_reference(self, backend_ref: str) -> ReasoningResultReferenceV1 | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
        if row is None or not str(row["result_ref"] or ""):
            return None
        return ReasoningResultReferenceV1(
            backend_ref=backend_ref,
            output_contract_version=str(row["output_contract_version"]),
            evidence_submission_ref=str(row["result_ref"]),
            evidence_submission_hash=str(row["result_hash"]),
            provider_binding_ref=str(row["provider_binding_ref"]),
            provider_binding_hash=str(row["provider_binding_hash"]),
            provider_provenance_index_ref=str(row["provider_provenance_index_ref"]),
            provider_provenance_index_hash=str(row["provider_provenance_index_hash"]),
            raw_provider_evidence_root_ref=str(row["raw_provider_evidence_root_ref"]),
            raw_provider_evidence_root_hash=str(row["raw_provider_evidence_root_hash"]),
            usage_ref=self._optional(row["usage_ref"]),
            usage_hash=self._optional(row["usage_hash"]),
            published_at=str(row["result_published_at"]),
        )

    def start_attempt(self, backend_ref: str) -> dict[str, Any] | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM reasoning_backend_start_attempts WHERE backend_ref = ?",
                (backend_ref,),
            ).fetchone()
        return dict(row) if row is not None else None

    def table_counts(self) -> dict[str, int]:
        with self._read() as conn:
            return {
                name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                for name in (
                    "reasoning_backend_runs",
                    "reasoning_backend_start_attempts",
                )
            }
