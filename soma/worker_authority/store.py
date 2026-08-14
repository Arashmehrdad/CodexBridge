"""Durable worker principal/grant/revocation authority store.

Construction is inert. ``init_db`` is explicit so source acceptance cannot
silently activate a live worker authority schema. The store persists only
immutable authority records and verifier hashes; reusable credentials are never
written to durable state.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import (
    WorkerAuthorityConflict,
    WorkerAuthorityRevocationV1,
    WorkerCapabilityGrantV1,
    WorkerPrincipalV1,
    canonical_hash,
    canonical_json,
    make_authority_id,
)
from .schema import (
    WORKER_AUTHORITY_TABLE_NAMES,
    apply_worker_authority_migrations,
    schema_state,
)


class WorkerAuthorityStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.db_path = self.runs_dir / "soma.sqlite3"

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

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

    def is_installed(self) -> bool:
        if not self.db_path.exists():
            return False
        try:
            with self._read() as conn:
                return bool(schema_state(conn)["up_to_date"])
        except sqlite3.Error:
            return False

    def schema_state(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {
                "component": "worker_authority",
                "schema_version": 0,
                "target_schema_version": 1,
                "up_to_date": False,
                "tables": [],
                "missing_tables": list(WORKER_AUTHORITY_TABLE_NAMES),
                "missing_triggers": [],
                "live_worker_surface": False,
            }
        try:
            with self._read() as conn:
                return dict(schema_state(conn))
        except sqlite3.Error:
            return {
                "component": "worker_authority",
                "schema_version": 0,
                "target_schema_version": 1,
                "up_to_date": False,
                "tables": [],
                "missing_tables": list(WORKER_AUTHORITY_TABLE_NAMES),
                "missing_triggers": [],
                "live_worker_surface": False,
            }

    def init_db(self) -> list[int]:
        """Explicitly install dependencies and the additive authority schema."""
        from soma.project_scope.store import ProjectScopeStore
        from soma.run_store import RunStore
        from soma.tasks.store import TaskStore
        from soma.worker_substrate.store import WorkerSubstrateStore

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        RunStore(self.runs_dir)
        TaskStore(self.runs_dir)
        ProjectScopeStore(self.runs_dir).init_db()
        WorkerSubstrateStore(self.runs_dir)
        return apply_worker_authority_migrations(self.connect)

    @staticmethod
    def _principal_from_row(row: sqlite3.Row) -> WorkerPrincipalV1:
        return WorkerPrincipalV1.model_validate_json(str(row["principal_json"]))

    @staticmethod
    def _grant_from_row(row: sqlite3.Row) -> WorkerCapabilityGrantV1:
        return WorkerCapabilityGrantV1.model_validate_json(str(row["grant_json"]))

    @staticmethod
    def _revocation_from_row(row: sqlite3.Row) -> WorkerAuthorityRevocationV1:
        return WorkerAuthorityRevocationV1(
            revocation_id=str(row["revocation_id"]),
            target_kind=str(row["target_kind"]),
            target_id=str(row["target_id"]),
            controller_request_id=str(row["controller_request_id"]),
            request_hash=str(row["request_hash"]),
            reason_ref=str(row["reason_ref"]),
            reason_hash=str(row["reason_hash"]),
            issuer_ref=str(row["issuer_ref"]),
            revoked_at=datetime.fromisoformat(str(row["revoked_at"])),
        )

    def get_principal(self, principal_id: str) -> WorkerPrincipalV1:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_principals WHERE principal_id = ?",
                (principal_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Worker principal not found: {principal_id}")
        return self._principal_from_row(row)

    def get_grant(self, grant_id: str) -> WorkerCapabilityGrantV1:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_capability_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Worker capability grant not found: {grant_id}")
        return self._grant_from_row(row)

    def principal_for_request(self, controller_request_id: str) -> WorkerPrincipalV1 | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_principals WHERE controller_request_id = ?",
                (controller_request_id,),
            ).fetchone()
        return None if row is None else self._principal_from_row(row)

    def grant_for_request(self, controller_request_id: str) -> WorkerCapabilityGrantV1 | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_capability_grants WHERE controller_request_id = ?",
                (controller_request_id,),
            ).fetchone()
        return None if row is None else self._grant_from_row(row)

    def revocation_for(
        self, target_kind: str, target_id: str
    ) -> WorkerAuthorityRevocationV1 | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM worker_authority_revocations "
                "WHERE target_kind = ? AND target_id = ?",
                (target_kind, target_id),
            ).fetchone()
        return None if row is None else self._revocation_from_row(row)

    def reserve_principal(
        self,
        principal: WorkerPrincipalV1,
    ) -> tuple[WorkerPrincipalV1, bool]:
        stored_json = canonical_json(principal.model_dump(mode="json"))
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM worker_principals WHERE controller_request_id = ?",
                (principal.controller_request_id,),
            ).fetchone()
            if existing is not None:
                durable = self._principal_from_row(existing)
                if durable.request_hash != principal.request_hash:
                    raise WorkerAuthorityConflict(
                        "controller_request_id is already bound to different worker principal authority"
                    )
                return durable, False
            by_id = conn.execute(
                "SELECT 1 FROM worker_principals WHERE principal_id = ?",
                (principal.principal_id,),
            ).fetchone()
            if by_id is not None:
                raise WorkerAuthorityConflict("principal_id is already reserved")
            conn.execute(
                "INSERT INTO worker_principals("
                "principal_id, controller_request_id, request_hash, verifier_hash, "
                "principal_json, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    principal.principal_id,
                    principal.controller_request_id,
                    principal.request_hash,
                    principal.verifier_hash,
                    stored_json,
                    principal.content_hash,
                    principal.created_at.isoformat(),
                ),
            )
        return principal, True

    def reserve_grant(
        self,
        grant: WorkerCapabilityGrantV1,
    ) -> tuple[WorkerCapabilityGrantV1, bool]:
        stored_json = canonical_json(grant.model_dump(mode="json"))
        with self._transaction() as conn:
            principal = conn.execute(
                "SELECT 1 FROM worker_principals WHERE principal_id = ?",
                (grant.principal_id,),
            ).fetchone()
            if principal is None:
                raise KeyError(f"Worker principal not found: {grant.principal_id}")
            existing = conn.execute(
                "SELECT * FROM worker_capability_grants WHERE controller_request_id = ?",
                (grant.controller_request_id,),
            ).fetchone()
            if existing is not None:
                durable = self._grant_from_row(existing)
                if durable.request_hash != grant.request_hash:
                    raise WorkerAuthorityConflict(
                        "controller_request_id is already bound to different worker grant authority"
                    )
                return durable, False
            by_id = conn.execute(
                "SELECT 1 FROM worker_capability_grants WHERE grant_id = ?",
                (grant.grant_id,),
            ).fetchone()
            if by_id is not None:
                raise WorkerAuthorityConflict("grant_id is already reserved")
            by_content = conn.execute(
                "SELECT controller_request_id FROM worker_capability_grants WHERE content_hash = ?",
                (grant.content_hash,),
            ).fetchone()
            if by_content is not None:
                raise WorkerAuthorityConflict(
                    "content-identical worker grant was issued under different request metadata"
                )
            conn.execute(
                "INSERT INTO worker_capability_grants("
                "grant_id, principal_id, controller_request_id, request_hash, "
                "grant_json, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    grant.grant_id,
                    grant.principal_id,
                    grant.controller_request_id,
                    grant.request_hash,
                    stored_json,
                    grant.content_hash,
                    grant.created_at.isoformat(),
                ),
            )
        return grant, True

    def revoke(
        self,
        *,
        target_kind: str,
        target_id: str,
        controller_request_id: str,
        reason_ref: str,
        reason_hash: str,
        issuer_ref: str,
        revoked_at: datetime | None = None,
    ) -> tuple[WorkerAuthorityRevocationV1, bool]:
        if target_kind not in {"principal", "grant"}:
            raise ValueError("target_kind must be principal or grant")
        timestamp = revoked_at or datetime.now(timezone.utc)
        material = {
            "target_kind": target_kind,
            "target_id": target_id,
            "reason_ref": reason_ref,
            "reason_hash": reason_hash,
            "issuer_ref": issuer_ref,
        }
        request_hash = canonical_hash(material)
        with self._transaction() as conn:
            target_table = (
                "worker_principals" if target_kind == "principal" else "worker_capability_grants"
            )
            target_column = "principal_id" if target_kind == "principal" else "grant_id"
            target = conn.execute(
                f"SELECT 1 FROM {target_table} WHERE {target_column} = ?",
                (target_id,),
            ).fetchone()
            if target is None:
                raise KeyError(f"Worker {target_kind} not found: {target_id}")
            by_request = conn.execute(
                "SELECT * FROM worker_authority_revocations WHERE controller_request_id = ?",
                (controller_request_id,),
            ).fetchone()
            if by_request is not None:
                durable = self._revocation_from_row(by_request)
                if durable.request_hash != request_hash:
                    raise WorkerAuthorityConflict(
                        "controller_request_id is already bound to a different revocation"
                    )
                return durable, False
            existing = conn.execute(
                "SELECT * FROM worker_authority_revocations WHERE target_kind = ? AND target_id = ?",
                (target_kind, target_id),
            ).fetchone()
            if existing is not None:
                raise WorkerAuthorityConflict(
                    f"worker {target_kind} is already revoked under different request metadata"
                )
            revocation = WorkerAuthorityRevocationV1(
                revocation_id=make_authority_id("wrevoke"),
                target_kind=target_kind,
                target_id=target_id,
                controller_request_id=controller_request_id,
                request_hash=request_hash,
                reason_ref=reason_ref,
                reason_hash=reason_hash,
                issuer_ref=issuer_ref,
                revoked_at=timestamp,
            )
            conn.execute(
                "INSERT INTO worker_authority_revocations("
                "revocation_id, target_kind, target_id, controller_request_id, "
                "request_hash, reason_ref, reason_hash, issuer_ref, revoked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    revocation.revocation_id,
                    revocation.target_kind,
                    revocation.target_id,
                    revocation.controller_request_id,
                    revocation.request_hash,
                    revocation.reason_ref,
                    revocation.reason_hash,
                    revocation.issuer_ref,
                    revocation.revoked_at.isoformat(),
                ),
            )
        return revocation, True

    def table_counts(self) -> dict[str, int]:
        if not self.is_installed():
            return {name: 0 for name in WORKER_AUTHORITY_TABLE_NAMES}
        with self._read() as conn:
            return {
                name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                for name in WORKER_AUTHORITY_TABLE_NAMES
            }
