"""Durable protected-tool request/effect idempotency store.

The store persists canonical request identity before any protected effect may
begin. The mutable delivery marker is deliberately separate from immutable call
and effect evidence so a crash after crossing the effect boundary cannot be
mistaken for a safe retry.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from soma.company_kernel.models import validate_opaque, validate_sha256

from .models import (
    ProtectedProviderProvenanceRefV1,
    ProtectedToolCallV1,
    ProtectedToolEffectV1,
)
from .schema import (
    apply_protected_tool_migrations,
    current_schema_version,
    schema_state,
    utc_now,
)


class ProtectedToolConflict(ValueError):
    """An idempotency/effect identity was replayed with different material."""


class ProtectedToolStateError(ValueError):
    """A protected-effect delivery transition is invalid or unsafe."""


class ProtectedToolStore:
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
        return apply_protected_tool_migrations(self.connect)

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
    def _canonical_json(payload: Any) -> str:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def _stored_call_json(cls, call: ProtectedToolCallV1) -> str:
        canonical = call.model_copy(update={"provider_provenance_refs": ()})
        return cls._canonical_json(canonical.model_dump(mode="json"))

    @classmethod
    def _stored_effect_json(cls, effect: ProtectedToolEffectV1) -> str:
        return cls._canonical_json(effect.model_dump(mode="json"))

    @staticmethod
    def _append_provenance_in_connection(
        conn: sqlite3.Connection,
        *,
        call_request_id: str,
        refs: Sequence[ProtectedProviderProvenanceRefV1],
        created_at: str,
    ) -> None:
        for item in refs:
            conn.execute(
                "INSERT OR IGNORE INTO protected_tool_provider_provenance("
                "call_request_id, provider_ref, provider_hash, created_at) "
                "VALUES (?, ?, ?, ?)",
                (call_request_id, item.ref, item.hash, created_at),
            )

    @staticmethod
    def _provenance_for(
        conn: sqlite3.Connection, call_request_id: str
    ) -> tuple[ProtectedProviderProvenanceRefV1, ...]:
        rows = conn.execute(
            "SELECT provider_ref, provider_hash FROM protected_tool_provider_provenance "
            "WHERE call_request_id = ? ORDER BY provider_ref, provider_hash",
            (call_request_id,),
        ).fetchall()
        return tuple(
            ProtectedProviderProvenanceRefV1(
                ref=str(row["provider_ref"]),
                hash=str(row["provider_hash"]),
            )
            for row in rows
        )

    @classmethod
    def _call_from_row(
        cls, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> ProtectedToolCallV1:
        payload = json.loads(str(row["call_json"]))
        payload["provider_provenance_refs"] = cls._provenance_for(
            conn, str(row["call_request_id"])
        )
        return ProtectedToolCallV1.model_validate(payload)

    @staticmethod
    def _effect_from_row(row: sqlite3.Row | None) -> ProtectedToolEffectV1 | None:
        if row is None:
            return None
        return ProtectedToolEffectV1.model_validate_json(str(row["effect_json"]))

    def reserve_call(
        self,
        call: ProtectedToolCallV1,
        *,
        now: str | None = None,
    ) -> tuple[ProtectedToolCallV1, bool]:
        """Reserve one canonical idempotency identity before any effect begins."""

        timestamp = now or utc_now()
        request_hash = call.request_hash
        stored_json = self._stored_call_json(call)
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM protected_tool_calls WHERE idempotency_key = ?",
                (call.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if str(existing["request_hash"]) != request_hash:
                    raise ProtectedToolConflict(
                        "idempotency key is already bound to different protected authority/effect material"
                    )
                self._append_provenance_in_connection(
                    conn,
                    call_request_id=str(existing["call_request_id"]),
                    refs=call.provider_provenance_refs,
                    created_at=timestamp,
                )
                return self._call_from_row(conn, existing), False

            by_id = conn.execute(
                "SELECT * FROM protected_tool_calls WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()
            if by_id is not None:
                raise ProtectedToolConflict(
                    "call_request_id is already bound to another protected request"
                )
            conn.execute(
                "INSERT INTO protected_tool_calls("
                "call_request_id, idempotency_key, request_hash, call_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    call.call_request_id,
                    call.idempotency_key,
                    request_hash,
                    stored_json,
                    timestamp,
                ),
            )
            conn.execute(
                "INSERT INTO protected_tool_delivery("
                "call_request_id, delivery_state, updated_at) VALUES (?, 'reserved', ?)",
                (call.call_request_id, timestamp),
            )
            self._append_provenance_in_connection(
                conn,
                call_request_id=call.call_request_id,
                refs=call.provider_provenance_refs,
                created_at=timestamp,
            )
            created = conn.execute(
                "SELECT * FROM protected_tool_calls WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()
            return self._call_from_row(conn, created), True

    def append_provider_provenance(
        self,
        *,
        call_request_id: str,
        refs: Sequence[ProtectedProviderProvenanceRefV1],
        now: str | None = None,
    ) -> ProtectedToolCallV1:
        validate_opaque(call_request_id, "call_request_id", max_length=128)
        timestamp = now or utc_now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM protected_tool_calls WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            if row is None:
                raise ProtectedToolStateError("protected call is not reserved")
            self._append_provenance_in_connection(
                conn,
                call_request_id=call_request_id,
                refs=refs,
                created_at=timestamp,
            )
            return self._call_from_row(conn, row)

    def claim_effect_boundary(
        self,
        *,
        call_request_id: str,
        request_hash: str,
        evidence_ref: str,
        evidence_hash: str,
        now: str | None = None,
    ) -> bool:
        """Let exactly one caller cross from safe reservation into effect uncertainty."""

        validate_opaque(call_request_id, "call_request_id", max_length=128)
        validate_sha256(request_hash, "request_hash")
        validate_opaque(evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(evidence_hash, "evidence_hash")
        timestamp = now or utc_now()
        with self._transaction() as conn:
            call = conn.execute(
                "SELECT request_hash FROM protected_tool_calls WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            if call is None:
                raise ProtectedToolStateError("protected call is not reserved")
            if str(call["request_hash"]) != request_hash:
                raise ProtectedToolConflict(
                    "request_hash does not match protected call"
                )
            delivery = conn.execute(
                "SELECT delivery_state FROM protected_tool_delivery WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            if delivery is None:
                raise ProtectedToolStateError("protected delivery record is missing")
            if str(delivery["delivery_state"]) != "reserved":
                return False
            cursor = conn.execute(
                "UPDATE protected_tool_delivery SET delivery_state = 'effect_begun', "
                "begin_evidence_ref = ?, begin_evidence_hash = ?, effect_begun_at = ?, "
                "updated_at = ? WHERE call_request_id = ? AND delivery_state = 'reserved'",
                (
                    evidence_ref,
                    evidence_hash,
                    timestamp,
                    timestamp,
                    call_request_id,
                ),
            )
            return cursor.rowcount == 1

    def record_effect(
        self,
        effect: ProtectedToolEffectV1,
        *,
        now: str | None = None,
    ) -> tuple[ProtectedToolEffectV1, bool]:
        """Persist the sole terminal effect record for a canonical protected request."""

        timestamp = now or utc_now()
        with self._transaction() as conn:
            call = conn.execute(
                "SELECT request_hash FROM protected_tool_calls WHERE call_request_id = ?",
                (effect.call_request_id,),
            ).fetchone()
            if call is None:
                raise ProtectedToolStateError("protected call is not reserved")
            if str(call["request_hash"]) != effect.request_hash:
                raise ProtectedToolConflict(
                    "effect request_hash does not match protected call"
                )
            existing = conn.execute(
                "SELECT * FROM protected_tool_effects WHERE call_request_id = ?",
                (effect.call_request_id,),
            ).fetchone()
            if existing is not None:
                durable = self._effect_from_row(existing)
                if durable is None or durable.effect_hash != effect.effect_hash:
                    raise ProtectedToolConflict(
                        "protected call already has a different terminal effect"
                    )
                return durable, False
            delivery = conn.execute(
                "SELECT delivery_state FROM protected_tool_delivery WHERE call_request_id = ?",
                (effect.call_request_id,),
            ).fetchone()
            if delivery is None:
                raise ProtectedToolStateError("protected delivery record is missing")
            state = str(delivery["delivery_state"])
            if state == "resolved":
                raise ProtectedToolStateError("protected delivery is already resolved")
            if (
                effect.disposition in {"acknowledged", "outcome_unknown"}
                and state != "effect_begun"
            ):
                raise ProtectedToolStateError(
                    f"{effect.disposition} requires the effect boundary to have begun"
                )
            if effect.disposition == "prevented" and state != "reserved":
                raise ProtectedToolStateError(
                    "prevented cannot be recorded after the external effect boundary begins"
                )
            conn.execute(
                "INSERT INTO protected_tool_effects("
                "call_request_id, request_hash, effect_hash, effect_json, disposition, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    effect.call_request_id,
                    effect.request_hash,
                    effect.effect_hash,
                    self._stored_effect_json(effect),
                    effect.disposition,
                    effect.completed_at.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE protected_tool_delivery SET delivery_state = 'resolved', updated_at = ? "
                "WHERE call_request_id = ?",
                (timestamp, effect.call_request_id),
            )
            return effect, True

    def get_observation(self, call_request_id: str) -> dict[str, Any]:
        validate_opaque(call_request_id, "call_request_id", max_length=128)
        with self._read() as conn:
            call_row = conn.execute(
                "SELECT * FROM protected_tool_calls WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            if call_row is None:
                raise ProtectedToolStateError("protected call is not reserved")
            delivery = conn.execute(
                "SELECT * FROM protected_tool_delivery WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            effect_row = conn.execute(
                "SELECT * FROM protected_tool_effects WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            effect = self._effect_from_row(effect_row)
            delivery_state = str(delivery["delivery_state"])
            if effect is not None:
                effective_disposition = effect.disposition
            elif delivery_state == "effect_begun":
                effective_disposition = "outcome_unknown"
            else:
                effective_disposition = None
            return {
                "call": self._call_from_row(conn, call_row),
                "request_hash": str(call_row["request_hash"]),
                "delivery_state": delivery_state,
                "begin_evidence_ref": str(delivery["begin_evidence_ref"]),
                "begin_evidence_hash": str(delivery["begin_evidence_hash"]),
                "effect_begun_at": delivery["effect_begun_at"],
                "effect": effect,
                "effective_disposition": effective_disposition,
            }
