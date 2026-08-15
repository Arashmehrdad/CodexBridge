"""Durable store for the minimal Sol semantic continuation kernel.

The store owns only mechanical continuation truth. It does not interpret handoff
semantics, recommend next actions, or copy Task/Run lifecycle state.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from .models import (
    ContinuationEffectKind,
    ContinuationEffectLinkRecord,
    ContinuationHandoffRecord,
    ContinuationLifecycle,
    ContinuationRecord,
    ContractRevisionRecord,
    content_sha256,
    make_continuation_id,
    make_contract_revision_id,
    make_effect_link_id,
    make_handoff_id,
    utc_now,
    validate_continuation_id,
    validate_contract_revision_id,
)
from .schema import apply_continuation_migrations, current_schema_version, schema_state


class ContinuationRequestConflict(ValueError):
    """One stable controller request identity was reused for different content."""

    def __init__(self, controller_request_id: str, existing_hash: str) -> None:
        super().__init__(
            f"controller_request_id {controller_request_id!r} is already bound "
            "to a different normalized continuation request"
        )
        self.controller_request_id = controller_request_id
        self.existing_hash = existing_hash


class StaleContinuationContract(ValueError):
    """A continuation-sensitive write supplied a non-current contract revision."""


class ContinuationClosed(ValueError):
    """A continuation-sensitive write targeted a completed/cancelled continuation."""


class ContinuationLifecycleConflict(ValueError):
    """A closed continuation was asked to adopt a different terminal lifecycle."""


class EffectOriginConflict(ValueError):
    """One canonical Task/Run already has a different continuation origin."""


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _require_request_id(controller_request_id: str) -> str:
    request_id = str(controller_request_id or "").strip()
    if not request_id:
        raise ValueError("controller_request_id must be non-empty")
    if len(request_id) > 128:
        raise ValueError("controller_request_id must be at most 128 characters")
    return request_id


def _instruction_payload(
    *, instruction_text: str = "", instruction_ref: str = ""
) -> dict[str, str]:
    text = str(instruction_text or "")
    ref = str(instruction_ref or "")
    if bool(text) == bool(ref):
        raise ValueError("Specify exactly one of instruction_text or instruction_ref")
    if len(text.encode("utf-8")) > 256 * 1024:
        raise ValueError("instruction_text exceeds the 256 KiB C1 persistence bound")
    if len(ref) > 32_768:
        raise ValueError("instruction_ref is too long")
    source = "text" if text else "ref"
    value = text if text else ref
    return {
        "instruction_text": text,
        "instruction_ref": ref,
        "content_hash": content_sha256(f"{source}\0{value}"),
    }


class ContinuationStore:
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
        return apply_continuation_migrations(self.connect)

    def schema_version(self) -> int:
        with self._read() as conn:
            return current_schema_version(conn)

    def schema_state(self) -> dict[str, object]:
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

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Expose a narrow caller-owned transaction for future Task/Run linking."""
        with self._transaction() as conn:
            yield conn

    @staticmethod
    def _continuation(row: sqlite3.Row) -> ContinuationRecord:
        return ContinuationRecord.model_validate(dict(row))

    @staticmethod
    def _revision(row: sqlite3.Row) -> ContractRevisionRecord:
        return ContractRevisionRecord.model_validate(dict(row))

    @staticmethod
    def _handoff(row: sqlite3.Row) -> ContinuationHandoffRecord:
        return ContinuationHandoffRecord.model_validate(dict(row))

    @staticmethod
    def _effect_link(row: sqlite3.Row) -> ContinuationEffectLinkRecord:
        return ContinuationEffectLinkRecord.model_validate(dict(row))

    def get_continuation(self, continuation_id: str) -> ContinuationRecord:
        with self._read() as conn:
            return self.get_continuation_in_connection(conn, continuation_id)

    def get_continuation_in_connection(
        self, conn: sqlite3.Connection, continuation_id: str
    ) -> ContinuationRecord:
        validate_continuation_id(continuation_id)
        row = conn.execute(
            "SELECT * FROM controller_continuations WHERE continuation_id = ?",
            (continuation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Continuation not found: {continuation_id}")
        return self._continuation(row)

    def get_contract_revision(
        self, contract_revision_id: str
    ) -> ContractRevisionRecord:
        with self._read() as conn:
            return self.get_contract_revision_in_connection(conn, contract_revision_id)

    def get_contract_revision_in_connection(
        self, conn: sqlite3.Connection, contract_revision_id: str
    ) -> ContractRevisionRecord:
        validate_contract_revision_id(contract_revision_id)
        row = conn.execute(
            "SELECT * FROM continuation_contract_revisions "
            "WHERE contract_revision_id = ?",
            (contract_revision_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Contract revision not found: {contract_revision_id}")
        return self._revision(row)

    def resolve_context_ref(
        self, continuation_context_ref: str
    ) -> tuple[ContinuationRecord, ContractRevisionRecord]:
        with self._read() as conn:
            revision = self.get_contract_revision_in_connection(
                conn, continuation_context_ref
            )
            continuation = self.get_continuation_in_connection(
                conn, revision.continuation_id
            )
            return continuation, revision

    def require_current_open_context(
        self, continuation_context_ref: str
    ) -> tuple[ContinuationRecord, ContractRevisionRecord]:
        with self._read() as conn:
            return self.require_current_open_context_in_connection(
                conn, continuation_context_ref
            )

    def require_current_open_context_in_connection(
        self, conn: sqlite3.Connection, continuation_context_ref: str
    ) -> tuple[ContinuationRecord, ContractRevisionRecord]:
        revision = self.get_contract_revision_in_connection(
            conn, continuation_context_ref
        )
        continuation = self.get_continuation_in_connection(
            conn, revision.continuation_id
        )
        if continuation.lifecycle != ContinuationLifecycle.OPEN:
            raise ContinuationClosed(
                f"Continuation {continuation.continuation_id} is {continuation.lifecycle.value}"
            )
        if continuation.current_contract_revision_id != revision.contract_revision_id:
            raise StaleContinuationContract(
                f"Expected current continuation_context_ref "
                f"{continuation.current_contract_revision_id}, got "
                f"{revision.contract_revision_id}"
            )
        return continuation, revision

    def open_continuation(
        self,
        *,
        label: str = "",
        instruction_text: str = "",
        instruction_ref: str = "",
        provenance_class: str,
        provenance_ref: str = "",
        controller_request_id: str,
    ) -> tuple[ContinuationRecord, ContractRevisionRecord, bool]:
        """Atomically create a continuation and its first governing revision."""
        request_id = _require_request_id(controller_request_id)
        label_value = str(label or "")
        if len(label_value) > 512:
            raise ValueError("label must be at most 512 characters")
        provenance = str(provenance_class or "").strip()
        if not provenance:
            raise ValueError("provenance_class must be non-empty")
        instruction = _instruction_payload(
            instruction_text=instruction_text,
            instruction_ref=instruction_ref,
        )
        normalized = {
            "operation": "open_continuation",
            "label": label_value,
            "instruction_text": instruction["instruction_text"],
            "instruction_ref": instruction["instruction_ref"],
            "provenance_class": provenance,
            "provenance_ref": str(provenance_ref or ""),
        }
        request_hash = _canonical_hash(normalized)
        continuation_id = make_continuation_id()
        revision_id = make_contract_revision_id()
        now = utc_now()

        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM controller_continuations "
                "WHERE creation_controller_request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                continuation = self._continuation(existing)
                if continuation.creation_request_hash != request_hash:
                    raise ContinuationRequestConflict(
                        request_id, continuation.creation_request_hash
                    )
                first = conn.execute(
                    "SELECT * FROM continuation_contract_revisions "
                    "WHERE continuation_id = ? AND revision_number = 1",
                    (continuation.continuation_id,),
                ).fetchone()
                if first is None:
                    raise RuntimeError("Continuation creation revision is missing")
                return continuation, self._revision(first), False

            conn.execute(
                """
                INSERT INTO controller_continuations (
                    continuation_id, label, lifecycle,
                    current_contract_revision_id,
                    creation_controller_request_id, creation_request_hash,
                    created_at, updated_at
                ) VALUES (?, ?, 'open', ?, ?, ?, ?, ?)
                """,
                (
                    continuation_id,
                    label_value,
                    revision_id,
                    request_id,
                    request_hash,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO continuation_contract_revisions (
                    contract_revision_id, continuation_id, parent_revision_id,
                    revision_number, instruction_text, instruction_ref,
                    content_hash, provenance_class, provenance_ref,
                    controller_request_id, request_hash, created_at
                ) VALUES (?, ?, NULL, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    continuation_id,
                    instruction["instruction_text"],
                    instruction["instruction_ref"],
                    instruction["content_hash"],
                    provenance,
                    str(provenance_ref or ""),
                    request_id,
                    request_hash,
                    now,
                ),
            )
            return (
                self.get_continuation_in_connection(conn, continuation_id),
                self.get_contract_revision_in_connection(conn, revision_id),
                True,
            )

    def append_contract_revision(
        self,
        *,
        continuation_context_ref: str,
        instruction_text: str = "",
        instruction_ref: str = "",
        provenance_class: str,
        provenance_ref: str = "",
        controller_request_id: str,
    ) -> tuple[ContractRevisionRecord, bool]:
        request_id = _require_request_id(controller_request_id)
        provenance = str(provenance_class or "").strip()
        if not provenance:
            raise ValueError("provenance_class must be non-empty")
        instruction = _instruction_payload(
            instruction_text=instruction_text,
            instruction_ref=instruction_ref,
        )
        request_hash = _canonical_hash(
            {
                "operation": "append_contract_revision",
                "continuation_context_ref": continuation_context_ref,
                "instruction_text": instruction["instruction_text"],
                "instruction_ref": instruction["instruction_ref"],
                "provenance_class": provenance,
                "provenance_ref": str(provenance_ref or ""),
            }
        )

        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM continuation_contract_revisions "
                "WHERE controller_request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                revision = self._revision(existing)
                if revision.request_hash != request_hash:
                    raise ContinuationRequestConflict(request_id, revision.request_hash)
                return revision, False

            continuation, current = self.require_current_open_context_in_connection(
                conn, continuation_context_ref
            )
            new_id = make_contract_revision_id()
            now = utc_now()
            conn.execute(
                """
                INSERT INTO continuation_contract_revisions (
                    contract_revision_id, continuation_id, parent_revision_id,
                    revision_number, instruction_text, instruction_ref,
                    content_hash, provenance_class, provenance_ref,
                    controller_request_id, request_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    continuation.continuation_id,
                    current.contract_revision_id,
                    current.revision_number + 1,
                    instruction["instruction_text"],
                    instruction["instruction_ref"],
                    instruction["content_hash"],
                    provenance,
                    str(provenance_ref or ""),
                    request_id,
                    request_hash,
                    now,
                ),
            )
            cursor = conn.execute(
                """
                UPDATE controller_continuations
                SET current_contract_revision_id = ?, updated_at = ?
                WHERE continuation_id = ? AND lifecycle = 'open'
                  AND current_contract_revision_id = ?
                """,
                (
                    new_id,
                    now,
                    continuation.continuation_id,
                    current.contract_revision_id,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise StaleContinuationContract(
                    "Continuation contract changed before compare-and-set update"
                )
            return self.get_contract_revision_in_connection(conn, new_id), True

    def append_handoff(
        self,
        *,
        continuation_context_ref: str,
        handoff_text: str,
        controller_request_id: str,
    ) -> tuple[ContinuationHandoffRecord, bool]:
        request_id = _require_request_id(controller_request_id)
        text = str(handoff_text or "")
        if not text:
            raise ValueError("handoff_text must be non-empty")
        if len(text.encode("utf-8")) > 256 * 1024:
            raise ValueError("handoff_text exceeds the 256 KiB C1 persistence bound")
        request_hash = _canonical_hash(
            {
                "operation": "append_handoff",
                "continuation_context_ref": continuation_context_ref,
                "handoff_text": text,
            }
        )

        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM continuation_handoffs "
                "WHERE controller_request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                handoff = self._handoff(existing)
                if handoff.request_hash != request_hash:
                    raise ContinuationRequestConflict(request_id, handoff.request_hash)
                return handoff, False

            continuation, revision = self.require_current_open_context_in_connection(
                conn, continuation_context_ref
            )
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_number), 0) + 1 "
                "FROM continuation_handoffs WHERE continuation_id = ?",
                (continuation.continuation_id,),
            ).fetchone()
            sequence = int(row[0])
            handoff_id = make_handoff_id()
            now = utc_now()
            conn.execute(
                """
                INSERT INTO continuation_handoffs (
                    handoff_id, continuation_id, contract_revision_id,
                    sequence_number, handoff_text, content_hash,
                    controller_request_id, request_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff_id,
                    continuation.continuation_id,
                    revision.contract_revision_id,
                    sequence,
                    text,
                    content_sha256(text),
                    request_id,
                    request_hash,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM continuation_handoffs WHERE handoff_id = ?",
                (handoff_id,),
            ).fetchone()
            assert row is not None
            return self._handoff(row), True

    def latest_handoff(
        self, continuation_id: str
    ) -> ContinuationHandoffRecord | None:
        validate_continuation_id(continuation_id)
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM continuation_handoffs WHERE continuation_id = ? "
                "ORDER BY sequence_number DESC LIMIT 1",
                (continuation_id,),
            ).fetchone()
        return None if row is None else self._handoff(row)

    def count_continuations(self) -> int:
        with self._read() as conn:
            row = conn.execute("SELECT COUNT(*) FROM controller_continuations").fetchone()
        return int(row[0])

    def page_continuations(
        self,
        *,
        before_updated_at: str = "",
        before_continuation_id: str = "",
        limit: int = 20,
    ) -> tuple[list[ContinuationRecord], bool]:
        bounded = max(1, min(int(limit), 100))
        if bool(before_updated_at) != bool(before_continuation_id):
            raise ValueError(
                "before_updated_at and before_continuation_id must appear together"
            )
        sql = "SELECT * FROM controller_continuations"
        params: list[Any] = []
        if before_updated_at:
            sql += (
                " WHERE updated_at < ? OR "
                "(updated_at = ? AND continuation_id < ?)"
            )
            params.extend(
                [before_updated_at, before_updated_at, before_continuation_id]
            )
        sql += " ORDER BY updated_at DESC, continuation_id DESC LIMIT ?"
        params.append(bounded + 1)
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        has_more = len(rows) > bounded
        return [self._continuation(row) for row in rows[:bounded]], has_more

    def list_contract_history(
        self, continuation_id: str, *, limit: int = 100
    ) -> list[ContractRevisionRecord]:
        validate_continuation_id(continuation_id)
        bounded = max(1, min(int(limit), 500))
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM continuation_contract_revisions "
                "WHERE continuation_id = ? ORDER BY revision_number ASC LIMIT ?",
                (continuation_id, bounded),
            ).fetchall()
        return [self._revision(row) for row in rows]

    def list_handoffs(
        self, continuation_id: str, *, limit: int = 100
    ) -> list[ContinuationHandoffRecord]:
        validate_continuation_id(continuation_id)
        bounded = max(1, min(int(limit), 500))
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM continuation_handoffs WHERE continuation_id = ? "
                "ORDER BY sequence_number ASC LIMIT ?",
                (continuation_id, bounded),
            ).fetchall()
        return [self._handoff(row) for row in rows]

    @classmethod
    def find_effect_link_in_connection(
        cls,
        conn: sqlite3.Connection,
        *,
        effect_kind: str,
        effect_id: str,
    ) -> ContinuationEffectLinkRecord | None:
        """Return immutable Task/Run origin without creating continuation state."""
        kind = ContinuationEffectKind(str(effect_kind))
        target_id = str(effect_id or "").strip()
        if not target_id:
            raise ValueError("effect_id must be non-empty")
        table_row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'continuation_effect_links'"
        ).fetchone()
        if table_row is None:
            return None
        row = conn.execute(
            "SELECT * FROM continuation_effect_links "
            "WHERE effect_kind = ? AND effect_id = ?",
            (kind.value, target_id),
        ).fetchone()
        return None if row is None else cls._effect_link(row)

    def insert_effect_link_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        continuation_context_ref: str,
        effect_kind: str,
        effect_id: str,
        controller_request_id: str,
    ) -> tuple[ContinuationEffectLinkRecord, bool]:
        request_id = _require_request_id(controller_request_id)
        kind = ContinuationEffectKind(str(effect_kind))
        target_id = str(effect_id or "").strip()
        if not target_id:
            raise ValueError("effect_id must be non-empty")
        request_hash = _canonical_hash(
            {
                "operation": "insert_effect_link",
                "continuation_context_ref": continuation_context_ref,
                "effect_kind": kind.value,
                "effect_id": target_id,
            }
        )

        existing_request = conn.execute(
            "SELECT * FROM continuation_effect_links "
            "WHERE controller_request_id = ?",
            (request_id,),
        ).fetchone()
        if existing_request is not None:
            link = self._effect_link(existing_request)
            if link.request_hash != request_hash:
                raise ContinuationRequestConflict(request_id, link.request_hash)
            return link, False

        continuation, revision = self.require_current_open_context_in_connection(
            conn, continuation_context_ref
        )
        if not self._effect_exists(conn, kind, target_id):
            raise KeyError(f"Canonical {kind.value} effect not found: {target_id}")

        existing_effect = conn.execute(
            "SELECT * FROM continuation_effect_links "
            "WHERE effect_kind = ? AND effect_id = ?",
            (kind.value, target_id),
        ).fetchone()
        if existing_effect is not None:
            link = self._effect_link(existing_effect)
            if (
                link.continuation_id != continuation.continuation_id
                or link.contract_revision_id != revision.contract_revision_id
            ):
                raise EffectOriginConflict(
                    f"{kind.value} {target_id} already has continuation origin "
                    f"{link.continuation_id}/{link.contract_revision_id}"
                )
            return link, False

        link_id = make_effect_link_id()
        now = utc_now()
        conn.execute(
            """
            INSERT INTO continuation_effect_links (
                link_id, continuation_id, contract_revision_id,
                effect_kind, effect_id, controller_request_id,
                request_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                continuation.continuation_id,
                revision.contract_revision_id,
                kind.value,
                target_id,
                request_id,
                request_hash,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM continuation_effect_links WHERE link_id = ?",
            (link_id,),
        ).fetchone()
        assert row is not None
        return self._effect_link(row), True

    def insert_effect_link(
        self,
        *,
        continuation_context_ref: str,
        effect_kind: str,
        effect_id: str,
        controller_request_id: str,
    ) -> tuple[ContinuationEffectLinkRecord, bool]:
        with self._transaction() as conn:
            return self.insert_effect_link_in_connection(
                conn,
                continuation_context_ref=continuation_context_ref,
                effect_kind=effect_kind,
                effect_id=effect_id,
                controller_request_id=controller_request_id,
            )

    @staticmethod
    def _effect_exists(
        conn: sqlite3.Connection, kind: ContinuationEffectKind, effect_id: str
    ) -> bool:
        table = "tasks" if kind == ContinuationEffectKind.TASK else "runs"
        id_column = "task_id" if kind == ContinuationEffectKind.TASK else "run_id"
        table_row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if table_row is None:
            return False
        return (
            conn.execute(
                f"SELECT 1 FROM {table} WHERE {id_column} = ?", (effect_id,)
            ).fetchone()
            is not None
        )

    def list_effect_links(
        self, continuation_id: str, *, limit: int = 100
    ) -> list[ContinuationEffectLinkRecord]:
        validate_continuation_id(continuation_id)
        bounded = max(1, min(int(limit), 500))
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM continuation_effect_links WHERE continuation_id = ? "
                "ORDER BY created_at ASC, link_id ASC LIMIT ?",
                (continuation_id, bounded),
            ).fetchall()
        return [self._effect_link(row) for row in rows]

    def count_handoffs(self, continuation_id: str) -> int:
        validate_continuation_id(continuation_id)
        with self._read() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM continuation_handoffs WHERE continuation_id = ?",
                (continuation_id,),
            ).fetchone()
        return int(row[0] or 0)

    def page_handoffs(
        self,
        continuation_id: str,
        *,
        before_sequence: int | None = None,
        limit: int = 20,
    ) -> tuple[list[ContinuationHandoffRecord], bool]:
        """Return one newest-first immutable handoff page and whether more exist."""
        validate_continuation_id(continuation_id)
        bounded = max(1, min(int(limit), 100))
        params: list[Any] = [continuation_id]
        sql = "SELECT * FROM continuation_handoffs WHERE continuation_id = ?"
        if before_sequence is not None:
            sequence = int(before_sequence)
            if sequence < 1:
                raise ValueError("before_sequence must be positive")
            sql += " AND sequence_number < ?"
            params.append(sequence)
        sql += " ORDER BY sequence_number DESC LIMIT ?"
        params.append(bounded + 1)
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        has_more = len(rows) > bounded
        return [self._handoff(row) for row in rows[:bounded]], has_more

    def count_effect_links(self, continuation_id: str) -> int:
        validate_continuation_id(continuation_id)
        with self._read() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM continuation_effect_links "
                "WHERE continuation_id = ?",
                (continuation_id,),
            ).fetchone()
        return int(row[0] or 0)

    def page_effect_links(
        self,
        continuation_id: str,
        *,
        before_created_at: str = "",
        before_link_id: str = "",
        limit: int = 20,
    ) -> tuple[list[ContinuationEffectLinkRecord], bool]:
        """Return one newest-first immutable origin-link page and whether more exist."""
        validate_continuation_id(continuation_id)
        bounded = max(1, min(int(limit), 100))
        created_at = str(before_created_at or "")
        link_id = str(before_link_id or "")
        if bool(created_at) != bool(link_id):
            raise ValueError(
                "before_created_at and before_link_id must be supplied together"
            )
        params: list[Any] = [continuation_id]
        sql = "SELECT * FROM continuation_effect_links WHERE continuation_id = ?"
        if created_at:
            sql += (
                " AND (created_at < ? OR (created_at = ? AND link_id < ?))"
            )
            params.extend([created_at, created_at, link_id])
        sql += " ORDER BY created_at DESC, link_id DESC LIMIT ?"
        params.append(bounded + 1)
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        has_more = len(rows) > bounded
        return [self._effect_link(row) for row in rows[:bounded]], has_more

    def close_continuation(
        self,
        *,
        continuation_id: str,
        lifecycle: str,
        controller_request_id: str,
    ) -> tuple[ContinuationRecord, bool]:
        validate_continuation_id(continuation_id)
        target = ContinuationLifecycle(str(lifecycle))
        if target == ContinuationLifecycle.OPEN:
            raise ValueError("close_continuation lifecycle must be completed or cancelled")
        request_id = _require_request_id(controller_request_id)
        request_hash = _canonical_hash(
            {
                "operation": "close_continuation",
                "continuation_id": continuation_id,
                "lifecycle": target.value,
            }
        )

        with self._transaction() as conn:
            continuation = self.get_continuation_in_connection(conn, continuation_id)
            if continuation.lifecycle != ContinuationLifecycle.OPEN:
                if continuation.lifecycle != target:
                    raise ContinuationLifecycleConflict(
                        f"Continuation is already {continuation.lifecycle.value}"
                    )
                if continuation.closure_controller_request_id == request_id:
                    if continuation.closure_request_hash != request_hash:
                        raise ContinuationRequestConflict(
                            request_id, continuation.closure_request_hash
                        )
                return continuation, False

            now = utc_now()
            conn.execute(
                """
                UPDATE controller_continuations
                SET lifecycle = ?, updated_at = ?, closed_at = ?,
                    closure_controller_request_id = ?, closure_request_hash = ?
                WHERE continuation_id = ? AND lifecycle = 'open'
                """,
                (
                    target.value,
                    now,
                    now,
                    request_id,
                    request_hash,
                    continuation_id,
                ),
            )
            return self.get_continuation_in_connection(conn, continuation_id), True
