"""Durable protected resource serialization and uncertainty containment."""

from __future__ import annotations

import sqlite3
from hashlib import sha256

from soma.company_kernel.models import validate_opaque, validate_sha256

from .broker import ProtectedResourceLeaseV1
from .models import ProtectedToolCallV1, ProtectedToolEffectV1
from .schema import utc_now
from .store import ProtectedToolConflict, ProtectedToolStateError, ProtectedToolStore


RESOURCE_LEASE_ID_DOMAIN = "soma.protected_tools.resource_lease.v1"
RESOURCE_CONTAINMENT_DOMAIN = "soma.protected_tools.resource_containment.v1"


class ProtectedResourceContainmentError(ValueError):
    """An uncertain protected resource lease cannot be mechanically contained."""


class DurableProtectedResourceGuard:
    """Serialize protected effects by exact resource key across tasks/restarts."""

    def __init__(self, store: ProtectedToolStore) -> None:
        self.store = store

    @staticmethod
    def _owner_ref(call: ProtectedToolCallV1) -> str:
        return f"task:{call.task_id}/attempt:{call.attempt_id}"

    @classmethod
    def _lease_ref(cls, call: ProtectedToolCallV1) -> str:
        material = (
            f"{RESOURCE_LEASE_ID_DOMAIN}\0{call.resource_key}\0"
            f"{call.request_hash}\0{cls._owner_ref(call)}"
        )
        digest = sha256(material.encode("utf-8")).hexdigest()
        return f"protected-lease_{digest[:24]}"

    @classmethod
    def _lease_evidence_hash(cls, call: ProtectedToolCallV1, lease_ref: str) -> str:
        material = (
            f"{RESOURCE_LEASE_ID_DOMAIN}\0{lease_ref}\0{call.resource_key}\0"
            f"{call.call_request_id}\0{call.request_hash}\0{cls._owner_ref(call)}"
        )
        return sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _busy_evidence_hash(row: sqlite3.Row) -> str:
        material = (
            f"busy\0{row['lease_ref']}\0{row['resource_key']}\0"
            f"{row['call_request_id']}\0{row['request_hash']}\0{row['state']}"
        )
        return sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _lease_from_row(
        row: sqlite3.Row, *, acquired: bool, reason: str = ""
    ) -> ProtectedResourceLeaseV1:
        return ProtectedResourceLeaseV1(
            acquired=acquired,
            resource_key=str(row["resource_key"]),
            owner_ref=str(row["owner_ref"]),
            lease_ref=str(row["lease_ref"]) if acquired else "",
            evidence_ref=(
                f"protected-resource-lease:{row['lease_ref']}"
                if acquired
                else f"protected-resource-busy:{row['lease_ref']}"
            ),
            evidence_hash=(
                sha256(
                    (
                        f"{RESOURCE_LEASE_ID_DOMAIN}\0{row['lease_ref']}\0"
                        f"{row['resource_key']}\0{row['call_request_id']}\0"
                        f"{row['request_hash']}\0{row['owner_ref']}"
                    ).encode("utf-8")
                ).hexdigest()
                if acquired
                else DurableProtectedResourceGuard._busy_evidence_hash(row)
            ),
            reason=reason,
        )

    def acquire(self, call: ProtectedToolCallV1) -> ProtectedResourceLeaseV1:
        """Acquire or replay the exact durable lease before the effect boundary."""

        now = utc_now()
        owner_ref = self._owner_ref(call)
        lease_ref = self._lease_ref(call)
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            durable_call = conn.execute(
                "SELECT request_hash FROM protected_tool_calls WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()
            if durable_call is None:
                raise ProtectedToolStateError(
                    "protected call must be reserved before resource acquisition"
                )
            if str(durable_call["request_hash"]) != call.request_hash:
                raise ProtectedToolConflict(
                    "protected call request_hash changed before resource acquisition"
                )

            own = conn.execute(
                "SELECT * FROM protected_resource_leases WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()
            if own is not None:
                exact = (
                    str(own["lease_ref"]) == lease_ref
                    and str(own["resource_key"]) == call.resource_key
                    and str(own["request_hash"]) == call.request_hash
                    and str(own["task_id"]) == call.task_id
                    and str(own["attempt_id"]) == call.attempt_id
                    and str(own["owner_ref"]) == owner_ref
                )
                if not exact:
                    raise ProtectedToolConflict(
                        "durable resource lease identity differs from protected call"
                    )
                state = str(own["state"])
                conn.commit()
                if state == "held":
                    return self._lease_from_row(own, acquired=True)
                if state == "uncertain":
                    return self._lease_from_row(
                        own,
                        acquired=False,
                        reason="resource remains blocked by unresolved protected-effect uncertainty",
                    )
                return self._lease_from_row(
                    own,
                    acquired=False,
                    reason=f"protected call resource lease is already {state}",
                )

            active = conn.execute(
                "SELECT * FROM protected_resource_leases "
                "WHERE resource_key = ? AND state IN ('held', 'uncertain')",
                (call.resource_key,),
            ).fetchone()
            if active is not None:
                conn.commit()
                return self._lease_from_row(
                    active,
                    acquired=False,
                    reason=(
                        "resource is held by another protected writer"
                        if str(active["state"]) == "held"
                        else "resource is blocked by another protected writer's unresolved effect"
                    ),
                )

            conn.execute(
                """
                INSERT INTO protected_resource_leases(
                    lease_ref, resource_key, call_request_id, request_hash,
                    task_id, attempt_id, owner_ref, state, acquired_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'held', ?, ?)
                """,
                (
                    lease_ref,
                    call.resource_key,
                    call.call_request_id,
                    call.request_hash,
                    call.task_id,
                    call.attempt_id,
                    owner_ref,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM protected_resource_leases WHERE lease_ref = ?",
                (lease_ref,),
            ).fetchone()
            conn.commit()
            return self._lease_from_row(row, acquired=True)
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def reconcile(
        self, call: ProtectedToolCallV1, effect: ProtectedToolEffectV1
    ) -> None:
        """Bring durable lease state into exact agreement with terminal effect evidence."""

        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM protected_resource_leases WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return
            if (
                str(row["request_hash"]) != call.request_hash
                or str(row["resource_key"]) != call.resource_key
                or str(row["task_id"]) != call.task_id
                or str(row["attempt_id"]) != call.attempt_id
            ):
                raise ProtectedToolConflict(
                    "resource lease does not match terminal protected effect owner"
                )
            durable_effect = conn.execute(
                "SELECT effect_hash, disposition FROM protected_tool_effects "
                "WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()
            if durable_effect is None:
                raise ProtectedToolStateError(
                    "resource lease cannot reconcile without durable protected effect evidence"
                )
            if (
                str(durable_effect["effect_hash"]) != effect.effect_hash
                or str(durable_effect["disposition"]) != effect.disposition
            ):
                raise ProtectedToolConflict(
                    "resource lease reconciliation effect differs from durable protected effect"
                )
            state = str(row["state"])
            now = utc_now()
            if effect.disposition == "outcome_unknown":
                if state == "held":
                    conn.execute(
                        "UPDATE protected_resource_leases SET state = 'uncertain', "
                        "resolution_evidence_ref = ?, resolution_evidence_hash = ?, updated_at = ? "
                        "WHERE lease_ref = ? AND state = 'held'",
                        (
                            effect.evidence_ref,
                            effect.evidence_hash,
                            now,
                            str(row["lease_ref"]),
                        ),
                    )
            elif effect.disposition in {"acknowledged", "rejected"}:
                if state == "held":
                    conn.execute(
                        "UPDATE protected_resource_leases SET state = 'released', "
                        "resolution_evidence_ref = ?, resolution_evidence_hash = ?, updated_at = ? "
                        "WHERE lease_ref = ? AND state = 'held'",
                        (
                            effect.evidence_ref,
                            effect.evidence_hash,
                            now,
                            str(row["lease_ref"]),
                        ),
                    )
            elif effect.disposition == "prevented" and state in {"held", "uncertain"}:
                raise ProtectedToolStateError(
                    "a prevented effect cannot resolve an already-acquired protected resource lease"
                )
            conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def contain_uncertainty(
        self,
        *,
        call_request_id: str,
        request_hash: str,
        evidence_ref: str,
        evidence_hash: str,
    ) -> dict[str, str]:
        """Explicitly contain an outcome-unknown lease using exact mechanical evidence."""

        validate_opaque(call_request_id, "call_request_id", max_length=128)
        validate_sha256(request_hash, "request_hash")
        validate_opaque(evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(evidence_hash, "evidence_hash")
        now = utc_now()
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM protected_resource_leases WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            if row is None:
                raise ProtectedResourceContainmentError(
                    "protected resource lease does not exist"
                )
            if str(row["request_hash"]) != request_hash:
                raise ProtectedResourceContainmentError(
                    "request_hash does not match uncertain lease"
                )
            if str(row["state"]) != "uncertain":
                raise ProtectedResourceContainmentError(
                    f"only uncertain leases may be contained; current state is {row['state']}"
                )
            effect = conn.execute(
                "SELECT disposition FROM protected_tool_effects WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
            if effect is None or str(effect["disposition"]) != "outcome_unknown":
                raise ProtectedResourceContainmentError(
                    "uncertain lease lacks durable outcome_unknown effect evidence"
                )
            containment_hash = sha256(
                (
                    f"{RESOURCE_CONTAINMENT_DOMAIN}\0{call_request_id}\0{request_hash}\0"
                    f"{evidence_ref}\0{evidence_hash}"
                ).encode("utf-8")
            ).hexdigest()
            conn.execute(
                "UPDATE protected_resource_leases SET state = 'contained', "
                "resolution_evidence_ref = ?, resolution_evidence_hash = ?, updated_at = ? "
                "WHERE lease_ref = ? AND state = 'uncertain'",
                (evidence_ref, evidence_hash, now, str(row["lease_ref"])),
            )
            conn.commit()
            return {
                "lease_ref": str(row["lease_ref"]),
                "resource_key": str(row["resource_key"]),
                "state": "contained",
                "containment_hash": containment_hash,
                "evidence_ref": evidence_ref,
                "evidence_hash": evidence_hash,
            }
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def get_lease(self, call_request_id: str) -> dict[str, str]:
        validate_opaque(call_request_id, "call_request_id", max_length=128)
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM protected_resource_leases WHERE call_request_id = ?",
                (call_request_id,),
            ).fetchone()
        if row is None:
            raise ProtectedToolStateError("protected resource lease does not exist")
        return {key: str(row[key] or "") for key in row.keys()}
