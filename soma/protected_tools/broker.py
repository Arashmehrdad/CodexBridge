"""Mechanical protected-mutation broker with fake-adapter-ready boundaries.

The broker revalidates durable Soma Task/WorkPackageAttempt/ProjectScope facts
it can prove directly from the shared database. Mandate, capability,
tool-operation, idempotency-slot and approval facts are supplied by a
Soma-controlled resolver protocol; provider text is never consulted as
authority.

G4.3 deliberately leaves resource-lease implementation behind a protocol. The
broker nevertheless requires an acquired exact lease before crossing the effect
boundary. G4.4 supplies/proves durable contention semantics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import validate_opaque, validate_sha256

from .models import ProtectedToolCallV1, ProtectedToolEffectV1
from .store import ProtectedToolStore


class ProtectedBrokerValidationError(ValueError):
    """One or more mechanical authority checks failed before effect start."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class ProtectedResourceUnavailable(RuntimeError):
    """Exact resource ownership is temporarily unavailable before effect start."""

    def __init__(self, lease: "ProtectedResourceLeaseV1") -> None:
        self.lease = lease
        super().__init__(
            lease.reason or "protected resource is temporarily unavailable"
        )


class _FrozenBrokerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProtectedAuthoritySnapshotV1(_FrozenBrokerModel):
    """Exact facts returned by a trusted Soma authority resolver."""

    mandate_ref: str = Field(min_length=1, max_length=2048)
    mandate_hash: str
    mandate_version: str = Field(min_length=1, max_length=128)
    mandate_active: bool
    capability_ref: str = Field(min_length=1, max_length=2048)
    capability_hash: str
    capability_possessed: bool
    tool_operation_ref: str = Field(min_length=1, max_length=2048)
    tool_operation_hash: str
    tool_operation_enabled: bool
    idempotency_key: str = Field(min_length=1, max_length=256)
    idempotency_authorized: bool
    approval_required: bool = False
    approval_valid: bool = False
    approval_evidence_ref: str = Field(default="", max_length=2048)
    approval_evidence_hash: str = ""

    @model_validator(mode="after")
    def _validate_snapshot(self):
        for field, value, maximum in (
            ("mandate_ref", self.mandate_ref, 2048),
            ("mandate_version", self.mandate_version, 128),
            ("capability_ref", self.capability_ref, 2048),
            ("tool_operation_ref", self.tool_operation_ref, 2048),
            ("idempotency_key", self.idempotency_key, 256),
        ):
            validate_opaque(value, field, max_length=maximum)
        for field, value in (
            ("mandate_hash", self.mandate_hash),
            ("capability_hash", self.capability_hash),
            ("tool_operation_hash", self.tool_operation_hash),
        ):
            validate_sha256(value, field)
        if bool(self.approval_evidence_ref) != bool(self.approval_evidence_hash):
            raise ValueError("approval evidence ref/hash must appear together")
        if self.approval_evidence_ref:
            validate_opaque(
                self.approval_evidence_ref,
                "approval_evidence_ref",
                max_length=2048,
            )
            validate_sha256(self.approval_evidence_hash, "approval_evidence_hash")
        if (
            self.approval_required
            and self.approval_valid
            and not self.approval_evidence_ref
        ):
            raise ValueError("valid required approval needs exact evidence ref/hash")
        return self


class ProtectedResourceLeaseV1(_FrozenBrokerModel):
    acquired: bool
    resource_key: str = Field(min_length=1, max_length=2048)
    owner_ref: str = Field(min_length=1, max_length=512)
    lease_ref: str = Field(default="", max_length=2048)
    evidence_ref: str = Field(min_length=1, max_length=2048)
    evidence_hash: str
    reason: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def _validate_lease(self):
        validate_opaque(self.resource_key, "resource_key", max_length=2048)
        validate_opaque(self.owner_ref, "owner_ref", max_length=512)
        if self.lease_ref:
            validate_opaque(self.lease_ref, "lease_ref", max_length=2048)
        validate_opaque(self.evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(self.evidence_hash, "evidence_hash")
        if self.acquired and not self.lease_ref:
            raise ValueError("acquired resource lease requires lease_ref")
        return self


class ProtectedAdapterResultV1(_FrozenBrokerModel):
    disposition: Literal["rejected", "acknowledged", "outcome_unknown"]
    external_effect_ref: str | None = Field(default=None, max_length=2048)
    external_effect_hash: str | None = None
    evidence_ref: str = Field(min_length=1, max_length=2048)
    evidence_hash: str

    @model_validator(mode="after")
    def _validate_result(self):
        if bool(self.external_effect_ref) != bool(self.external_effect_hash):
            raise ValueError("external effect ref/hash must appear together")
        if self.external_effect_ref is not None:
            validate_opaque(
                self.external_effect_ref,
                "external_effect_ref",
                max_length=2048,
            )
            validate_sha256(self.external_effect_hash or "", "external_effect_hash")
        if self.disposition == "acknowledged" and self.external_effect_ref is None:
            raise ValueError(
                "acknowledged adapter result requires exact external effect"
            )
        validate_opaque(self.evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(self.evidence_hash, "evidence_hash")
        return self


class ProtectedBrokerResultV1(_FrozenBrokerModel):
    call: ProtectedToolCallV1
    effect: ProtectedToolEffectV1
    call_created: bool
    replayed: bool
    adapter_called: bool
    resource_lease_ref: str = ""


class ProtectedAuthorityResolver(Protocol):
    def resolve(self, call: ProtectedToolCallV1) -> ProtectedAuthoritySnapshotV1: ...


class ProtectedResourceGuard(Protocol):
    def acquire(self, call: ProtectedToolCallV1) -> ProtectedResourceLeaseV1: ...

    def release(self, lease: ProtectedResourceLeaseV1) -> None: ...


class ProtectedToolAdapter(Protocol):
    def execute(
        self, call: ProtectedToolCallV1, payload: bytes
    ) -> ProtectedAdapterResultV1: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _evidence_hash(code: str, request_hash: str, detail: str = "") -> str:
    return sha256(f"{code}\0{request_hash}\0{detail}".encode("utf-8")).hexdigest()


def _prevented_effect(
    call: ProtectedToolCallV1,
    *,
    code: str,
    detail: str,
    completed_at: datetime,
) -> ProtectedToolEffectV1:
    return ProtectedToolEffectV1(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        disposition="prevented",
        evidence_ref=f"broker-prevented:{code}",
        evidence_hash=_evidence_hash(code, call.request_hash, detail),
        completed_at=completed_at,
    )


def _outcome_unknown_effect(
    call: ProtectedToolCallV1,
    *,
    evidence_ref: str,
    evidence_hash: str,
    completed_at: datetime,
) -> ProtectedToolEffectV1:
    return ProtectedToolEffectV1(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        disposition="outcome_unknown",
        evidence_ref=evidence_ref,
        evidence_hash=evidence_hash,
        completed_at=completed_at,
    )


class ProtectedToolBroker:
    def __init__(
        self,
        *,
        store: ProtectedToolStore,
        authority_resolver: ProtectedAuthorityResolver,
        resource_guard: ProtectedResourceGuard,
        adapter: ProtectedToolAdapter,
        clock=_utc_now,
    ) -> None:
        self.store = store
        self.authority_resolver = authority_resolver
        self.resource_guard = resource_guard
        self.adapter = adapter
        self.clock = clock

    def _validate_task_attempt_scope(self, call: ProtectedToolCallV1) -> None:
        with self.store.connect() as conn:
            task = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (call.task_id,),
            ).fetchone()
            if task is None:
                raise ProtectedBrokerValidationError(
                    "task_missing", "canonical Task does not exist"
                )
            if int(task["state_version"]) != call.expected_task_state_version:
                raise ProtectedBrokerValidationError(
                    "stale_task_state_version",
                    "Task state version differs from protected call expectation",
                )
            if str(task["state"]) != "running":
                raise ProtectedBrokerValidationError(
                    "task_not_running",
                    f"protected mutation requires running Task, got {task['state']!r}",
                )
            if str(task["backend_ref"]) != call.backend_ref:
                raise ProtectedBrokerValidationError(
                    "backend_binding_mismatch",
                    "Task backend_ref differs from protected call",
                )
            cancellation = conn.execute(
                "SELECT 1 FROM task_commands WHERE task_id = ? AND command_kind = 'cancel' "
                "AND status != 'rejected_stale_version' LIMIT 1",
                (call.task_id,),
            ).fetchone()
            if cancellation is not None:
                raise ProtectedBrokerValidationError(
                    "cancellation_precedence",
                    "accepted cancellation intent forbids a new protected effect",
                )

            attempt = conn.execute(
                """
                SELECT attempt.*, package.plan_revision_id, package.project_id,
                       package.target_resource_id, package.scope_generation,
                       mission.current_plan_revision_id
                FROM work_package_attempts attempt
                JOIN work_packages package
                  ON package.work_package_id = attempt.work_package_id
                JOIN missions mission ON mission.mission_id = package.mission_id
                WHERE attempt.attempt_id = ? AND attempt.task_id = ?
                """,
                (call.attempt_id, call.task_id),
            ).fetchone()
            if attempt is None:
                raise ProtectedBrokerValidationError(
                    "attempt_binding_mismatch",
                    "WorkPackageAttempt is not exactly bound to Task",
                )
            if str(attempt["plan_revision_id"]) != str(
                attempt["current_plan_revision_id"] or ""
            ):
                raise ProtectedBrokerValidationError(
                    "attempt_not_current_plan",
                    "WorkPackageAttempt is not in the Mission current PlanRevision",
                )
            successor = conn.execute(
                "SELECT 1 FROM work_package_attempts WHERE supersedes_attempt_id = ? LIMIT 1",
                (call.attempt_id,),
            ).fetchone()
            if successor is not None:
                raise ProtectedBrokerValidationError(
                    "attempt_superseded",
                    "WorkPackageAttempt has a durable successor",
                )
            if (
                str(attempt["project_id"]) != call.project_id
                or str(attempt["target_resource_id"]) != call.resource_id
                or int(attempt["scope_generation"]) != call.scope_generation
            ):
                raise ProtectedBrokerValidationError(
                    "attempt_scope_mismatch",
                    "WorkPackageAttempt ProjectScope identity differs from protected call",
                )
            try:
                route = json.loads(str(attempt["route_descriptor_json"]))
            except json.JSONDecodeError as exc:
                raise ProtectedBrokerValidationError(
                    "attempt_route_invalid",
                    "WorkPackageAttempt route descriptor is invalid",
                ) from exc
            route_scope = (
                route.get("project_scope") if isinstance(route, dict) else None
            )
            if route_scope != {
                "project_id": call.project_id,
                "resource_id": call.resource_id,
                "scope_generation": call.scope_generation,
            }:
                raise ProtectedBrokerValidationError(
                    "attempt_route_scope_mismatch",
                    "frozen Attempt route ProjectScope differs from protected call",
                )

            scope = conn.execute(
                """
                SELECT task.project_id, task.scope_generation, task.status,
                       attempt.resource_id, attempt.status AS attempt_status,
                       project.lifecycle_state, project.scope_generation AS current_generation
                FROM project_task_reservations task
                JOIN project_run_attempts attempt ON attempt.task_id = task.task_id
                JOIN projects project ON project.project_id = task.project_id
                WHERE task.task_id = ?
                """,
                (call.task_id,),
            ).fetchone()
            if scope is None:
                raise ProtectedBrokerValidationError(
                    "project_scope_missing",
                    "Task has no authoritative ProjectScope reservation",
                )
            if (
                str(scope["project_id"]) != call.project_id
                or str(scope["resource_id"]) != call.resource_id
                or int(scope["scope_generation"]) != call.scope_generation
                or int(scope["current_generation"]) != call.scope_generation
            ):
                raise ProtectedBrokerValidationError(
                    "project_scope_mismatch",
                    "current ProjectScope project/resource/generation differs from protected call",
                )
            if str(scope["lifecycle_state"]) != "active":
                raise ProtectedBrokerValidationError(
                    "project_scope_inactive", "ProjectScope project is not active"
                )
            if (
                str(scope["status"]) != "attached"
                or str(scope["attempt_status"]) != "attached"
            ):
                raise ProtectedBrokerValidationError(
                    "project_scope_not_attached",
                    "Task/backend ProjectScope reservation is not attached",
                )

    @staticmethod
    def _validate_authority_snapshot(
        call: ProtectedToolCallV1, snapshot: ProtectedAuthoritySnapshotV1
    ) -> None:
        if (
            snapshot.mandate_ref != call.mandate_ref
            or snapshot.mandate_hash != call.mandate_hash
            or snapshot.mandate_version != call.mandate_version
            or not snapshot.mandate_active
        ):
            raise ProtectedBrokerValidationError(
                "mandate_mismatch", "active mandate ref/hash/version is not exact"
            )
        if (
            snapshot.capability_ref != call.capability_ref
            or snapshot.capability_hash != call.capability_hash
            or not snapshot.capability_possessed
        ):
            raise ProtectedBrokerValidationError(
                "capability_mismatch", "concrete capability possession is not exact"
            )
        if (
            snapshot.tool_operation_ref != call.tool_operation_ref
            or snapshot.tool_operation_hash != call.tool_operation_hash
            or not snapshot.tool_operation_enabled
        ):
            raise ProtectedBrokerValidationError(
                "tool_operation_mismatch",
                "tool-operation contract is not exact/enabled",
            )
        if (
            snapshot.idempotency_key != call.idempotency_key
            or not snapshot.idempotency_authorized
        ):
            raise ProtectedBrokerValidationError(
                "idempotency_unauthorized",
                "idempotency key is not issued/validated by Soma authority",
            )
        if snapshot.approval_required and (
            not snapshot.approval_valid or not snapshot.approval_evidence_ref
        ):
            raise ProtectedBrokerValidationError(
                "approval_missing",
                "required approval/authority evidence is absent or invalid",
            )

    def _validate_before_effect(
        self, call: ProtectedToolCallV1, payload: bytes
    ) -> None:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("protected broker clock must be timezone-aware")
        if now >= call.expires_at:
            raise ProtectedBrokerValidationError(
                "call_expired", "protected call has expired"
            )
        payload_hash = sha256(payload).hexdigest()
        if payload_hash != call.payload_hash:
            raise ProtectedBrokerValidationError(
                "payload_hash_mismatch",
                "supplied protected payload differs from payload_hash",
            )
        self._validate_task_attempt_scope(call)
        snapshot = self.authority_resolver.resolve(call)
        self._validate_authority_snapshot(call, snapshot)

    def _materialize_unknown_after_restart(
        self, call: ProtectedToolCallV1, observation: dict
    ) -> ProtectedToolEffectV1:
        evidence_ref = str(
            observation.get("begin_evidence_ref") or "broker:effect-begun"
        )
        evidence_hash = str(observation.get("begin_evidence_hash") or "")
        if len(evidence_hash) != 64:
            evidence_hash = _evidence_hash(
                "effect_begun_without_terminal_evidence",
                call.request_hash,
                evidence_ref,
            )
        effect = _outcome_unknown_effect(
            call,
            evidence_ref=evidence_ref,
            evidence_hash=evidence_hash,
            completed_at=self.clock(),
        )
        stored, _created = self.store.record_effect(effect)
        return stored

    def execute(
        self, call: ProtectedToolCallV1, payload: bytes
    ) -> ProtectedBrokerResultV1:
        canonical_call, call_created = self.store.reserve_call(call)
        observation = self.store.get_observation(canonical_call.call_request_id)
        existing = observation["effect"]
        if existing is not None:
            return ProtectedBrokerResultV1(
                call=canonical_call,
                effect=existing,
                call_created=call_created,
                replayed=True,
                adapter_called=False,
            )
        if observation["delivery_state"] == "effect_begun":
            unknown = self._materialize_unknown_after_restart(
                canonical_call, observation
            )
            return ProtectedBrokerResultV1(
                call=canonical_call,
                effect=unknown,
                call_created=call_created,
                replayed=True,
                adapter_called=False,
            )

        try:
            self._validate_before_effect(canonical_call, payload)
        except ProtectedBrokerValidationError as exc:
            prevented = _prevented_effect(
                canonical_call,
                code=exc.code,
                detail=exc.detail,
                completed_at=self.clock(),
            )
            stored, _created = self.store.record_effect(prevented)
            return ProtectedBrokerResultV1(
                call=canonical_call,
                effect=stored,
                call_created=call_created,
                replayed=False,
                adapter_called=False,
            )

        lease = self.resource_guard.acquire(canonical_call)
        expected_owner = (
            f"task:{canonical_call.task_id}/attempt:{canonical_call.attempt_id}"
        )
        if not lease.acquired:
            raise ProtectedResourceUnavailable(lease)
        if (
            lease.resource_key != canonical_call.resource_key
            or lease.owner_ref != expected_owner
        ):
            raise RuntimeError(
                "resource guard returned an acquired lease for the wrong owner/resource"
            )

        crossed = self.store.claim_effect_boundary(
            call_request_id=canonical_call.call_request_id,
            request_hash=canonical_call.request_hash,
            evidence_ref=lease.evidence_ref,
            evidence_hash=lease.evidence_hash,
        )
        if not crossed:
            observation = self.store.get_observation(canonical_call.call_request_id)
            effect = observation["effect"]
            if effect is None:
                effect = self._materialize_unknown_after_restart(
                    canonical_call, observation
                )
            return ProtectedBrokerResultV1(
                call=canonical_call,
                effect=effect,
                call_created=call_created,
                replayed=True,
                adapter_called=False,
                resource_lease_ref=lease.lease_ref,
            )

        try:
            adapter_result = self.adapter.execute(canonical_call, payload)
        except Exception as exc:  # the external effect may already have happened
            evidence_ref = f"broker-adapter-exception:{type(exc).__name__}"
            evidence_hash = _evidence_hash(
                "adapter_exception_after_effect_boundary",
                canonical_call.request_hash,
                type(exc).__name__,
            )
            effect = _outcome_unknown_effect(
                canonical_call,
                evidence_ref=evidence_ref,
                evidence_hash=evidence_hash,
                completed_at=self.clock(),
            )
            stored, _created = self.store.record_effect(effect)
            return ProtectedBrokerResultV1(
                call=canonical_call,
                effect=stored,
                call_created=call_created,
                replayed=False,
                adapter_called=True,
                resource_lease_ref=lease.lease_ref,
            )

        effect = ProtectedToolEffectV1(
            call_request_id=canonical_call.call_request_id,
            request_hash=canonical_call.request_hash,
            disposition=adapter_result.disposition,
            external_effect_ref=adapter_result.external_effect_ref,
            external_effect_hash=adapter_result.external_effect_hash,
            evidence_ref=adapter_result.evidence_ref,
            evidence_hash=adapter_result.evidence_hash,
            completed_at=self.clock(),
        )
        stored, _created = self.store.record_effect(effect)
        if stored.disposition != "outcome_unknown":
            self.resource_guard.release(lease)
        return ProtectedBrokerResultV1(
            call=canonical_call,
            effect=stored,
            call_created=call_created,
            replayed=False,
            adapter_called=True,
            resource_lease_ref=lease.lease_ref,
        )
