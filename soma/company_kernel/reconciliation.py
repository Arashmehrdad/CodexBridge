"""One-shot internal Company Kernel reconciliation receipts.

`reconcile_one` is intentionally not a scheduler and does not dispatch Task,
Run, plan, package or acceptance mutations.  This bounded gate records only an
explicit owner-turn no-op or a package-completion observation that an exact
current WorkPackage is mechanically published and awaiting named acceptance.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.config import AppConfig

from .models import (
    COMPANY_KERNEL_SCHEMA_VERSION,
    RECONCILIATION_ID_DOMAIN,
    KernelReconciliationReceipt,
    canonical_json,
    derive_identity,
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
)
from .projections import (
    ProjectionError,
    project_mission_in_connection,
    project_work_package_in_connection,
)
from .schema import schema_state
from .store import CompanyKernelStore


RECONCILIATION_EFFECT_DOMAIN: Final[str] = (
    "soma.company_kernel.reconciliation_effect.v1"
)


class ReconciliationError(ValueError):
    """The requested bounded reconciliation cannot be recorded."""


class ReconciliationConflict(ReconciliationError):
    """Trigger/request material conflicts with durable or current truth."""


class ReconciliationIntegrityError(ReconciliationError):
    """Stored reconciliation evidence is internally inconsistent."""


class ReconcileOneRequestV1(BaseModel):
    """Exact request for one receipt-only reconciliation decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    company_id: str
    mission_id: str
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    executive_authority_ref: str = Field(min_length=1, max_length=128)
    trigger_kind: Literal["owner_turn", "package_completion"]
    trigger_ref: str = Field(min_length=1, max_length=2048)
    expected_kernel_state_version: int = Field(ge=0)
    selected_transition: Literal["no_op", "acceptance_candidate_ready"]
    target_ref: str = Field(default="", max_length=2048)
    target_hash: str = ""

    @model_validator(mode="after")
    def _validate_request(self):
        validate_kernel_id(self.company_id, "company_id")
        validate_kernel_id(self.mission_id, "mission_id")
        for field_name, limit in (
            ("project_id", 128),
            ("resource_id", 128),
            ("executive_authority_ref", 128),
            ("trigger_ref", 2048),
        ):
            validate_opaque(str(getattr(self, field_name)), field_name, max_length=limit)
        if self.selected_transition == "no_op":
            if self.trigger_kind != "owner_turn":
                raise ValueError("no_op reconciliation requires trigger_kind='owner_turn'")
            if self.target_ref or self.target_hash:
                raise ValueError("no_op reconciliation must not carry target material")
        else:
            if self.trigger_kind != "package_completion":
                raise ValueError(
                    "acceptance_candidate_ready requires trigger_kind='package_completion'"
                )
            validate_kernel_id(self.target_ref, "work_package_id")
            validate_sha256(self.target_hash, "target_hash")
        return self


class ReconcileOneResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created: bool
    replay_kind: Literal["none", "trigger"]
    receipt: KernelReconciliationReceipt


FaultInjector = Callable[[str, sqlite3.Connection], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _effect_material(request: ReconcileOneRequestV1) -> dict[str, Any]:
    return {
        "company_id": request.company_id,
        "mission_id": request.mission_id,
        "project_id": request.project_id,
        "resource_id": request.resource_id,
        "scope_generation": request.scope_generation,
        "executive_authority_ref": request.executive_authority_ref,
        "trigger_kind": request.trigger_kind,
        "trigger_ref": request.trigger_ref,
        "observed_kernel_state_version": request.expected_kernel_state_version,
        "selected_transition": request.selected_transition,
        "target_ref": request.target_ref,
        "target_hash": request.target_hash,
    }


def _effect_hash(request: ReconcileOneRequestV1) -> str:
    payload = f"{RECONCILIATION_EFFECT_DOMAIN}\0{canonical_json(_effect_material(request))}"
    return sha256(payload.encode("utf-8")).hexdigest()


def _reconciliation_identity(request: ReconcileOneRequestV1) -> str:
    return derive_identity(
        RECONCILIATION_ID_DOMAIN,
        {
            "mission_id": request.mission_id,
            "trigger_kind": request.trigger_kind,
            "trigger_ref": request.trigger_ref,
        },
    )


def _expected_receipt(
    request: ReconcileOneRequestV1,
    *,
    created_at: str,
) -> KernelReconciliationReceipt:
    return KernelReconciliationReceipt(
        reconciliation_id=_reconciliation_identity(request),
        mission_id=request.mission_id,
        trigger_kind=request.trigger_kind,
        trigger_ref=request.trigger_ref,
        observed_kernel_state_version=request.expected_kernel_state_version,
        selected_transition=request.selected_transition,
        target_ref=request.target_ref,
        effect_hash=_effect_hash(request),
        created_at=created_at,
    )


def _row_receipt(row: sqlite3.Row) -> KernelReconciliationReceipt:
    try:
        return KernelReconciliationReceipt.model_validate(dict(row))
    except Exception as exc:
        raise ReconciliationIntegrityError(
            f"stored reconciliation receipt is invalid: {exc}"
        ) from exc


def _exact_replay(
    actual: KernelReconciliationReceipt,
    expected: KernelReconciliationReceipt,
) -> None:
    fields = (
        "reconciliation_id",
        "mission_id",
        "trigger_kind",
        "trigger_ref",
        "observed_kernel_state_version",
        "selected_transition",
        "target_ref",
        "effect_hash",
    )
    if any(getattr(actual, field) != getattr(expected, field) for field in fields):
        raise ReconciliationConflict(
            "reconciliation trigger already exists with different transition/effect material"
        )


def _request_replay(
    conn: sqlite3.Connection,
    expected: KernelReconciliationReceipt,
) -> KernelReconciliationReceipt | None:
    row = conn.execute(
        "SELECT * FROM kernel_reconciliation_receipts "
        "WHERE mission_id = ? AND trigger_kind = ? AND trigger_ref = ?",
        (expected.mission_id, expected.trigger_kind, expected.trigger_ref),
    ).fetchone()
    if row is None:
        collision = conn.execute(
            "SELECT * FROM kernel_reconciliation_receipts WHERE reconciliation_id = ?",
            (expected.reconciliation_id,),
        ).fetchone()
        if collision is not None:
            raise ReconciliationIntegrityError(
                "derived reconciliation identity collides with another trigger"
            )
        return None
    actual = _row_receipt(row)
    _exact_replay(actual, expected)
    return actual


def _require_current_mission(
    conn: sqlite3.Connection,
    request: ReconcileOneRequestV1,
) -> None:
    company = conn.execute(
        "SELECT executive_authority_ref FROM companies WHERE company_id = ?",
        (request.company_id,),
    ).fetchone()
    if company is None:
        raise ReconciliationConflict("exact Company identity is unavailable")
    mission_row = conn.execute(
        "SELECT * FROM missions WHERE mission_id = ? AND company_id = ?",
        (request.mission_id, request.company_id),
    ).fetchone()
    if mission_row is None:
        raise ReconciliationConflict("exact Mission/Company identity is unavailable")
    if (
        str(company["executive_authority_ref"]) != request.executive_authority_ref
        or str(mission_row["accountable_owner_ref"]) != request.executive_authority_ref
        or str(mission_row["acceptance_authority_ref"])
        != request.executive_authority_ref
    ):
        raise ReconciliationConflict(
            "executive authority does not match the fixed Kernel-of-One authority chain"
        )
    if int(mission_row["kernel_state_version"]) != request.expected_kernel_state_version:
        raise ReconciliationConflict(
            "Mission kernel_state_version changed before reconciliation"
        )
    try:
        mission = project_mission_in_connection(conn, request.mission_id)
    except ProjectionError as exc:
        raise ReconciliationConflict(str(exc)) from exc
    if (
        mission.project_id != request.project_id
        or mission.resource_id != request.resource_id
        or mission.scope_generation != request.scope_generation
    ):
        raise ReconciliationConflict(
            "reconciliation ProjectScope assertion does not match Mission"
        )
    if not mission.scope.valid:
        raise ReconciliationConflict(
            f"Mission ProjectScope is invalid: {mission.scope.reason}"
        )


def _require_requested_effect(
    conn: sqlite3.Connection,
    request: ReconcileOneRequestV1,
) -> None:
    if request.selected_transition == "no_op":
        return
    try:
        package = project_work_package_in_connection(conn, request.target_ref)
    except ProjectionError as exc:
        raise ReconciliationConflict(str(exc)) from exc
    if package.mission_id != request.mission_id:
        raise ReconciliationConflict(
            "acceptance candidate WorkPackage belongs to another Mission"
        )
    if not package.current_plan:
        raise ReconciliationConflict(
            "acceptance candidate WorkPackage is not in the Mission current PlanRevision"
        )
    if package.state != "published_awaiting_acceptance":
        raise ReconciliationConflict(
            "acceptance_candidate_ready requires published_awaiting_acceptance"
        )
    if package.published_result_hash != request.target_hash:
        raise ReconciliationConflict(
            "acceptance candidate publication hash does not match target_hash"
        )


def _insert_receipt(
    conn: sqlite3.Connection,
    receipt: KernelReconciliationReceipt,
) -> None:
    conn.execute(
        """
        INSERT INTO kernel_reconciliation_receipts(
            reconciliation_id, mission_id, trigger_kind, trigger_ref,
            observed_kernel_state_version, selected_transition, target_ref,
            effect_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receipt.reconciliation_id,
            receipt.mission_id,
            receipt.trigger_kind,
            receipt.trigger_ref,
            receipt.observed_kernel_state_version,
            receipt.selected_transition,
            receipt.target_ref,
            receipt.effect_hash,
            receipt.created_at,
        ),
    )


def _invoke_fault(
    injector: FaultInjector | None,
    phase: str,
    conn: sqlite3.Connection,
) -> None:
    if injector is not None:
        injector(phase, conn)


def reconcile_one(
    config: AppConfig,
    request: ReconcileOneRequestV1,
    *,
    store: CompanyKernelStore | None = None,
    created_at: str | None = None,
    _fault_injector: FaultInjector | None = None,
) -> ReconcileOneResultV1:
    """Record one exact receipt-only reconciliation decision.

    Exact trigger replay is checked before current scope/version validation so a
    later plan/scope transition cannot erase acknowledgement of an immutable
    historical trigger.  New receipts perform no mutation beyond the receipt.
    """

    runtime = config.company_kernel
    if not runtime.enabled:
        raise ReconciliationError("Company Kernel runtime capability is disabled")
    if request.executive_authority_ref != runtime.executive_authority_ref:
        raise ReconciliationConflict(
            "executive authority assertion does not match trusted configuration"
        )
    kernel_store = store or CompanyKernelStore(config.resolve_runs_dir())
    expected = _expected_receipt(
        request,
        created_at=created_at or _utc_now(),
    )

    with kernel_store.transaction() as conn:
        state = schema_state(conn)
        if (
            not state["up_to_date"]
            or int(state["schema_version"]) != COMPANY_KERNEL_SCHEMA_VERSION
        ):
            raise ReconciliationError(
                f"Company Kernel schema v{COMPANY_KERNEL_SCHEMA_VERSION} must be installed"
            )
        if state["active_capability"] is not False:
            raise ReconciliationError(
                "reconciliation source gate requires the inactive internal Company Kernel"
            )

        replay = _request_replay(conn, expected)
        if replay is not None:
            return ReconcileOneResultV1(
                created=False,
                replay_kind="trigger",
                receipt=replay,
            )

        _require_current_mission(conn, request)
        _require_requested_effect(conn, request)
        _invoke_fault(_fault_injector, "before_receipt_insert", conn)
        try:
            _insert_receipt(conn, expected)
        except sqlite3.IntegrityError as exc:
            raise ReconciliationConflict(
                f"reconciliation receipt lost a durable identity race: {exc}"
            ) from exc
        _invoke_fault(_fault_injector, "after_receipt_insert", conn)

    return ReconcileOneResultV1(
        created=True,
        replay_kind="none",
        receipt=expected,
    )
