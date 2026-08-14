"""Exact internal OutcomeAcceptance authority for one WorkPackage outcome.

This module creates one immutable :class:`AcceptanceCommit` only after the
caller names the exact current Company/Mission/Plan/WorkPackage/Attempt/Task,
active ProjectScope binding, provider-neutral Task backend identity, publication
hashes, and the fixed Kernel-of-One acceptance authority.  It never launches,
reconciles, cancels, or mutates a Task/backend; the sole mutable company-domain
effect is the Mission kernel-state compare-and-set that records one accepted
outcome.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.config import AppConfig
from soma.project_scope.models import ProjectScopeError
from soma.project_scope.store import ProjectScopeStore

from .models import (
    ACCEPTANCE_ID_DOMAIN,
    COMPANY_KERNEL_SCHEMA_VERSION,
    AcceptanceCommit,
    canonical_json,
    derive_identity,
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
)
from .schema import schema_state
from .store import CompanyKernelStore


OUTCOME_ACCEPTANCE_REQUEST_DOMAIN: Final[str] = (
    "soma.company_kernel.outcome_acceptance_request.v1"
)
OUTCOME_ACCEPTANCE_IDENTITY_SCHEMA: Final[str] = (
    "soma.company_kernel.outcome_acceptance_identity.v1"
)


class OutcomeAcceptanceError(ValueError):
    """Current exact facts do not authorize this OutcomeAcceptance."""


class OutcomeAcceptanceConflict(OutcomeAcceptanceError):
    """Caller material conflicts with immutable or versioned durable truth."""


class OutcomeAcceptanceIntegrityError(OutcomeAcceptanceError):
    """Durable acceptance/execution evidence is internally inconsistent."""


class OutcomeAcceptanceRequestV1(BaseModel):
    """Exact owner assertion for one published WorkPackage outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    controller_request_id: str = Field(min_length=1, max_length=128)
    company_id: str
    mission_id: str
    plan_revision_id: str
    work_package_id: str
    outcome_id: str
    attempt_id: str
    task_id: str = Field(min_length=1, max_length=128)
    backend_kind: Literal["soma_durable_run", "soma_reasoning"]
    backend_ref: str = Field(min_length=1, max_length=256)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    expected_kernel_state_version: int = Field(ge=0)
    result_published_hash: str
    public_result_source_sha256: str
    acceptance_authority_ref: str = Field(min_length=1, max_length=128)
    acceptance_basis_ref: str = Field(min_length=1, max_length=2048)
    acceptance_basis_hash: str

    @model_validator(mode="after")
    def _validate_request(self):
        for field_name in (
            "company_id",
            "mission_id",
            "plan_revision_id",
            "work_package_id",
            "outcome_id",
            "attempt_id",
        ):
            validate_kernel_id(str(getattr(self, field_name)), field_name)
        for field_name, limit in (
            ("controller_request_id", 128),
            ("task_id", 128),
            ("backend_ref", 256),
            ("project_id", 128),
            ("resource_id", 128),
            ("acceptance_authority_ref", 128),
            ("acceptance_basis_ref", 2048),
        ):
            validate_opaque(str(getattr(self, field_name)), field_name, max_length=limit)
        validate_sha256(self.result_published_hash, "result_published_hash")
        validate_sha256(
            self.public_result_source_sha256,
            "public_result_source_sha256",
        )
        validate_sha256(self.acceptance_basis_hash, "acceptance_basis_hash")
        return self


class OutcomeAcceptanceResultV1(BaseModel):
    """Deterministic internal acceptance/replay receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    created: bool
    replay_kind: Literal["none", "request"]
    request_hash: str
    acceptance: AcceptanceCommit


FaultInjector = Callable[[str, sqlite3.Connection], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_hash(domain: str, payload: Any) -> str:
    material = f"{domain}\0{canonical_json(payload)}".encode("utf-8")
    return sha256(material).hexdigest()


def _request_material(request: OutcomeAcceptanceRequestV1) -> dict[str, Any]:
    return {
        "controller_request_id": request.controller_request_id,
        "company_id": request.company_id,
        "mission_id": request.mission_id,
        "plan_revision_id": request.plan_revision_id,
        "work_package_id": request.work_package_id,
        "outcome_id": request.outcome_id,
        "attempt_id": request.attempt_id,
        "task_id": request.task_id,
        "backend_kind": request.backend_kind,
        "backend_ref": request.backend_ref,
        "project_id": request.project_id,
        "resource_id": request.resource_id,
        "scope_generation": request.scope_generation,
        "expected_kernel_state_version": request.expected_kernel_state_version,
        "result_published_hash": request.result_published_hash,
        "public_result_source_sha256": request.public_result_source_sha256,
        "acceptance_authority_ref": request.acceptance_authority_ref,
        "acceptance_basis_ref": request.acceptance_basis_ref,
        "acceptance_basis_hash": request.acceptance_basis_hash,
    }


def _acceptance_identity_material(
    request: OutcomeAcceptanceRequestV1,
) -> dict[str, Any]:
    return {
        "schema": OUTCOME_ACCEPTANCE_IDENTITY_SCHEMA,
        "company_id": request.company_id,
        "mission_id": request.mission_id,
        "plan_revision_id": request.plan_revision_id,
        "work_package_id": request.work_package_id,
        "outcome_id": request.outcome_id,
        "attempt_id": request.attempt_id,
        "task_id": request.task_id,
        "backend_kind": request.backend_kind,
        "backend_ref": request.backend_ref,
        "result_published_hash": request.result_published_hash,
        "public_result_source_sha256": request.public_result_source_sha256,
        "acceptance_authority_ref": request.acceptance_authority_ref,
        "acceptance_basis_ref": request.acceptance_basis_ref,
        "acceptance_basis_hash": request.acceptance_basis_hash,
    }


def _expected_acceptance(
    request: OutcomeAcceptanceRequestV1,
    *,
    request_hash: str,
    accepted_at: str,
) -> AcceptanceCommit:
    return AcceptanceCommit(
        acceptance_commit_id=derive_identity(
            ACCEPTANCE_ID_DOMAIN,
            _acceptance_identity_material(request),
        ),
        company_id=request.company_id,
        mission_id=request.mission_id,
        work_package_id=request.work_package_id,
        outcome_id=request.outcome_id,
        attempt_id=request.attempt_id,
        task_id=request.task_id,
        backend_kind=request.backend_kind,
        backend_ref=request.backend_ref,
        run_id=(
            request.backend_ref
            if request.backend_kind == "soma_durable_run"
            else None
        ),
        result_published_hash=request.result_published_hash,
        public_result_source_sha256=request.public_result_source_sha256,
        acceptance_authority_ref=request.acceptance_authority_ref,
        acceptance_basis_ref=request.acceptance_basis_ref,
        acceptance_basis_hash=request.acceptance_basis_hash,
        controller_request_id=request.controller_request_id,
        request_hash=request_hash,
        accepted_at=accepted_at,
    )


def _row_acceptance(row: sqlite3.Row) -> AcceptanceCommit:
    try:
        return AcceptanceCommit.model_validate(dict(row))
    except Exception as exc:
        raise OutcomeAcceptanceIntegrityError(
            f"stored AcceptanceCommit is invalid: {exc}"
        ) from exc


def _assert_exact_replay(
    actual: AcceptanceCommit,
    expected: AcceptanceCommit,
) -> None:
    fields = (
        "acceptance_commit_id",
        "company_id",
        "mission_id",
        "work_package_id",
        "outcome_id",
        "attempt_id",
        "task_id",
        "backend_kind",
        "backend_ref",
        "run_id",
        "result_published_hash",
        "public_result_source_sha256",
        "acceptance_authority_ref",
        "acceptance_basis_ref",
        "acceptance_basis_hash",
        "controller_request_id",
        "request_hash",
    )
    if any(getattr(actual, field) != getattr(expected, field) for field in fields):
        raise OutcomeAcceptanceConflict(
            "controller request conflicts with the immutable AcceptanceCommit"
        )


def _request_replay(
    conn: sqlite3.Connection,
    expected: AcceptanceCommit,
) -> AcceptanceCommit | None:
    row = conn.execute(
        "SELECT * FROM acceptance_commits WHERE controller_request_id = ?",
        (expected.controller_request_id,),
    ).fetchone()
    if row is None:
        return None
    actual = _row_acceptance(row)
    _assert_exact_replay(actual, expected)
    return actual


def _require_single_row(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...],
    *,
    label: str,
) -> sqlite3.Row:
    rows = conn.execute(sql, params).fetchall()
    if len(rows) != 1:
        raise OutcomeAcceptanceConflict(
            f"exact {label} identity is unavailable"
            if not rows
            else f"exact {label} identity is not unique"
        )
    return rows[0]


def _require_authority_chain(
    conn: sqlite3.Connection,
    request: OutcomeAcceptanceRequestV1,
) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row]:
    company = _require_single_row(
        conn,
        "SELECT * FROM companies WHERE company_id = ?",
        (request.company_id,),
        label="Company",
    )
    mission = _require_single_row(
        conn,
        "SELECT * FROM missions WHERE mission_id = ? AND company_id = ?",
        (request.mission_id, request.company_id),
        label="Mission",
    )
    package = _require_single_row(
        conn,
        "SELECT * FROM work_packages WHERE work_package_id = ? AND mission_id = ? "
        "AND outcome_id = ?",
        (request.work_package_id, request.mission_id, request.outcome_id),
        label="WorkPackage/outcome",
    )
    attempt = _require_single_row(
        conn,
        "SELECT * FROM work_package_attempts WHERE attempt_id = ? "
        "AND work_package_id = ? AND outcome_id = ? AND task_id = ?",
        (
            request.attempt_id,
            request.work_package_id,
            request.outcome_id,
            request.task_id,
        ),
        label="WorkPackageAttempt",
    )
    task = _require_single_row(
        conn,
        "SELECT * FROM tasks WHERE task_id = ?",
        (request.task_id,),
        label="canonical Task",
    )

    authority = request.acceptance_authority_ref
    if (
        str(company["executive_authority_ref"]) != authority
        or str(mission["accountable_owner_ref"]) != authority
        or str(mission["acceptance_authority_ref"]) != authority
        or str(package["accountable_owner_ref"]) != authority
        or str(package["acceptance_authority_ref"]) != authority
    ):
        raise OutcomeAcceptanceConflict(
            "acceptance authority does not match the fixed Kernel-of-One authority chain"
        )
    if (
        str(mission["current_plan_revision_id"] or "") != request.plan_revision_id
        or str(package["plan_revision_id"]) != request.plan_revision_id
    ):
        raise OutcomeAcceptanceConflict(
            "WorkPackage is not part of the exact asserted current PlanRevision"
        )
    if int(mission["kernel_state_version"]) != request.expected_kernel_state_version:
        raise OutcomeAcceptanceConflict(
            "Mission kernel_state_version changed before OutcomeAcceptance"
        )
    if (
        str(mission["project_id"]) != request.project_id
        or str(package["project_id"]) != request.project_id
        or str(mission["resource_id"]) != request.resource_id
        or str(package["target_resource_id"]) != request.resource_id
        or int(mission["scope_generation"]) != request.scope_generation
        or int(package["scope_generation"]) != request.scope_generation
    ):
        raise OutcomeAcceptanceConflict(
            "OutcomeAcceptance ProjectScope assertion does not match Mission/WorkPackage"
        )
    if (
        str(task["backend_kind"]) != request.backend_kind
        or str(task["backend_ref"] or "") != request.backend_ref
    ):
        raise OutcomeAcceptanceConflict(
            "canonical Task backend identity does not match OutcomeAcceptance"
        )
    expected_task_kind, expected_executor = {
        "soma_durable_run": ("durable_command", "executable_profile"),
        "soma_reasoning": ("reasoning", "reasoning_backend"),
    }[request.backend_kind]
    if (
        str(task["task_kind"]) != expected_task_kind
        or str(task["backend_executor"] or "") != expected_executor
    ):
        raise OutcomeAcceptanceConflict(
            "canonical Task kind/executor does not match its selected backend"
        )
    if str(task["state"]) != "completed":
        raise OutcomeAcceptanceConflict(
            "canonical Task is not terminal successful"
        )
    if str(task["recovery_state"] or "none") != "none":
        raise OutcomeAcceptanceConflict(
            "canonical Task still carries recovery or uncertainty state"
        )
    if str(task["phase"] or "") != "result_published":
        raise OutcomeAcceptanceConflict(
            "canonical Task has not reconciled a published terminal result"
        )
    if str(task["result_hash"] or "") != request.result_published_hash:
        raise OutcomeAcceptanceConflict(
            "canonical Task result hash does not match reviewed publication"
        )
    return company, mission, package, attempt, task


def _require_scope_binding(
    conn: sqlite3.Connection,
    scope_store: ProjectScopeStore,
    request: OutcomeAcceptanceRequestV1,
) -> None:
    try:
        scope = scope_store.require_task_attempt_in_connection(
            conn,
            request.project_id,
            request.task_id,
            request.backend_ref,
        )
    except ProjectScopeError as exc:
        raise OutcomeAcceptanceConflict(str(exc)) from exc
    if (
        scope.project_id != request.project_id
        or scope.resource_id != request.resource_id
        or scope.scope_generation != request.scope_generation
        or scope.binding_status != "attached"
        or scope.attempt_status != "attached"
    ):
        raise OutcomeAcceptanceConflict(
            "Task backend attempt is not exactly attached to the active ProjectScope"
        )


def _require_durable_run_publication(
    conn: sqlite3.Connection,
    request: OutcomeAcceptanceRequestV1,
    task: sqlite3.Row,
) -> None:
    run = _require_single_row(
        conn,
        "SELECT * FROM runs WHERE run_id = ?",
        (request.backend_ref,),
        label="durable Run backend",
    )
    if (
        str(run["status"]) != "completed"
        or run["exit_code"] is None
        or int(run["exit_code"]) != 0
    ):
        raise OutcomeAcceptanceConflict("durable Run is not terminal successful")
    if bool(run["safety_failure"]):
        raise OutcomeAcceptanceConflict("durable Run carries safety_failure")
    if str(run["recovery_reason"] or ""):
        raise OutcomeAcceptanceConflict("durable Run carries unresolved recovery evidence")
    if str(run["result_publication_status"]) != "published":
        raise OutcomeAcceptanceConflict("durable Run result is not published")
    if str(run["result_publication_error"] or ""):
        raise OutcomeAcceptanceConflict("durable Run publication carries an error")
    if str(run["result_published_hash"] or "") != request.result_published_hash:
        raise OutcomeAcceptanceConflict("durable Run publication hash mismatch")
    if (
        str(run["public_result_source_sha256"] or "")
        != request.public_result_source_sha256
    ):
        raise OutcomeAcceptanceConflict("durable Run public-result source hash mismatch")
    if not str(run["result_published_at"] or ""):
        raise OutcomeAcceptanceConflict("durable Run publication timestamp is missing")
    if str(task["result_ref"] or "") != request.backend_ref:
        raise OutcomeAcceptanceConflict(
            "canonical Task result reference does not identify the durable Run"
        )
    if str(task["evidence_ref"] or "") != f"run_terminal:{request.backend_ref}":
        raise OutcomeAcceptanceConflict(
            "canonical Task evidence reference does not identify the durable Run terminal record"
        )


def _require_reasoning_publication(
    conn: sqlite3.Connection,
    request: OutcomeAcceptanceRequestV1,
    task: sqlite3.Row,
) -> None:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
        "AND name = 'reasoning_backend_runs'"
    ).fetchone()
    if table is None:
        raise OutcomeAcceptanceConflict("reasoning backend evidence table is unavailable")
    backend = _require_single_row(
        conn,
        "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
        (request.backend_ref,),
        label="reasoning backend",
    )
    if str(backend["start_delivery_disposition"]) != "accepted_bound":
        raise OutcomeAcceptanceConflict("reasoning backend start is not definitely bound")
    if str(backend["provider_binding_disposition"]) != "bound":
        raise OutcomeAcceptanceConflict("reasoning provider binding is not definite")
    if not str(backend["provider_operation_ref"] or ""):
        raise OutcomeAcceptanceConflict("reasoning provider operation identity is missing")
    if str(backend["provider_terminal_claim"]) != "success":
        raise OutcomeAcceptanceConflict("reasoning backend is not terminal successful")
    if str(backend["output_contract_disposition"]) != "valid":
        raise OutcomeAcceptanceConflict("reasoning output contract is not valid")
    if not str(backend["output_contract_version"] or ""):
        raise OutcomeAcceptanceConflict("reasoning output contract version is missing")
    if str(backend["error_code"] or ""):
        raise OutcomeAcceptanceConflict("reasoning backend carries an error code")
    if str(backend["cancellation_disposition"]) not in {"not_requested", "rejected"}:
        raise OutcomeAcceptanceConflict(
            "reasoning backend cancellation state is incompatible with acceptance"
        )
    result_ref = str(backend["result_ref"] or "")
    result_hash = str(backend["result_hash"] or "")
    if not result_ref or not str(backend["result_published_at"] or ""):
        raise OutcomeAcceptanceConflict("reasoning result is not durably published")
    if result_hash != request.result_published_hash:
        raise OutcomeAcceptanceConflict("reasoning EvidenceSubmission hash mismatch")
    # The historical field name is retained in AcceptanceCommit for compatibility.
    # For a reasoning Task, the published EvidenceSubmission content hash is the
    # authoritative publication-source SHA rather than a synthetic Run projection.
    if request.public_result_source_sha256 != result_hash:
        raise OutcomeAcceptanceConflict(
            "reasoning publication-source SHA must equal the EvidenceSubmission hash"
        )
    if str(task["result_ref"] or "") != result_ref:
        raise OutcomeAcceptanceConflict(
            "canonical Task result reference does not match reasoning publication"
        )
    for ref_field, hash_field in (
        ("provider_binding_ref", "provider_binding_hash"),
        ("evidence_index_ref", "evidence_index_hash"),
        ("provider_provenance_index_ref", "provider_provenance_index_hash"),
        ("raw_provider_evidence_root_ref", "raw_provider_evidence_root_hash"),
    ):
        if not str(backend[ref_field] or ""):
            raise OutcomeAcceptanceConflict(
                f"reasoning publication is missing {ref_field}"
            )
        try:
            validate_sha256(str(backend[hash_field] or ""), hash_field)
        except ValueError as exc:
            raise OutcomeAcceptanceConflict(
                f"reasoning publication has invalid {hash_field}"
            ) from exc
    if str(task["evidence_ref"] or "") != str(backend["evidence_index_ref"]):
        raise OutcomeAcceptanceConflict(
            "canonical Task evidence reference does not match reasoning evidence index"
        )


def _require_backend_publication(
    conn: sqlite3.Connection,
    request: OutcomeAcceptanceRequestV1,
    task: sqlite3.Row,
) -> None:
    if request.backend_kind == "soma_durable_run":
        _require_durable_run_publication(conn, request, task)
        return
    _require_reasoning_publication(conn, request, task)


def _insert_acceptance(conn: sqlite3.Connection, acceptance: AcceptanceCommit) -> None:
    conn.execute(
        """
        INSERT INTO acceptance_commits(
            acceptance_commit_id, company_id, mission_id, work_package_id,
            outcome_id, attempt_id, task_id, backend_kind, backend_ref, run_id,
            result_published_hash, public_result_source_sha256,
            acceptance_authority_ref, acceptance_basis_ref, acceptance_basis_hash,
            controller_request_id, request_hash, accepted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            acceptance.acceptance_commit_id,
            acceptance.company_id,
            acceptance.mission_id,
            acceptance.work_package_id,
            acceptance.outcome_id,
            acceptance.attempt_id,
            acceptance.task_id,
            acceptance.backend_kind,
            acceptance.backend_ref,
            acceptance.run_id,
            acceptance.result_published_hash,
            acceptance.public_result_source_sha256,
            acceptance.acceptance_authority_ref,
            acceptance.acceptance_basis_ref,
            acceptance.acceptance_basis_hash,
            acceptance.controller_request_id,
            acceptance.request_hash,
            acceptance.accepted_at,
        ),
    )


def _invoke_fault(
    injector: FaultInjector | None,
    phase: str,
    conn: sqlite3.Connection,
) -> None:
    if injector is not None:
        injector(phase, conn)


def accept_outcome(
    config: AppConfig,
    request: OutcomeAcceptanceRequestV1,
    *,
    store: CompanyKernelStore | None = None,
    scope_store: ProjectScopeStore | None = None,
    accepted_at: str | None = None,
    _fault_injector: FaultInjector | None = None,
) -> OutcomeAcceptanceResultV1:
    """Create or replay one exact immutable OutcomeAcceptance commit.

    New acceptance is one ``BEGIN IMMEDIATE`` transaction. Exact request replay
    is checked first so later ProjectScope archival/replanning cannot erase a
    historical acceptance acknowledgement. Any different request for an already
    accepted outcome fails closed.
    """

    runtime = config.company_kernel
    if not runtime.enabled:
        raise OutcomeAcceptanceError("Company Kernel runtime capability is disabled")
    if request.acceptance_authority_ref != runtime.executive_authority_ref:
        raise OutcomeAcceptanceConflict(
            "acceptance authority assertion does not match trusted configuration"
        )

    kernel_store = store or CompanyKernelStore(config.resolve_runs_dir())
    project_scope = scope_store or ProjectScopeStore(config.resolve_runs_dir())
    request_hash = _domain_hash(
        OUTCOME_ACCEPTANCE_REQUEST_DOMAIN,
        _request_material(request),
    )
    accepted_at_value = accepted_at or _utc_now()
    expected = _expected_acceptance(
        request,
        request_hash=request_hash,
        accepted_at=accepted_at_value,
    )

    with kernel_store.transaction() as conn:
        state = schema_state(conn)
        if (
            not state["up_to_date"]
            or int(state["schema_version"]) != COMPANY_KERNEL_SCHEMA_VERSION
        ):
            raise OutcomeAcceptanceError(
                f"Company Kernel schema v{COMPANY_KERNEL_SCHEMA_VERSION} must be installed"
            )
        if state["active_capability"] is not False:
            raise OutcomeAcceptanceError(
                "OutcomeAcceptance source gate requires the inactive internal Company Kernel"
            )

        replay = _request_replay(conn, expected)
        if replay is not None:
            return OutcomeAcceptanceResultV1(
                created=False,
                replay_kind="request",
                request_hash=request_hash,
                acceptance=replay,
            )

        existing_outcome = conn.execute(
            "SELECT acceptance_commit_id, controller_request_id "
            "FROM acceptance_commits WHERE outcome_id = ?",
            (request.outcome_id,),
        ).fetchone()
        if existing_outcome is not None:
            raise OutcomeAcceptanceConflict(
                "WorkPackage outcome already has an immutable AcceptanceCommit"
            )
        identity_collision = conn.execute(
            "SELECT outcome_id FROM acceptance_commits WHERE acceptance_commit_id = ?",
            (expected.acceptance_commit_id,),
        ).fetchone()
        if identity_collision is not None:
            raise OutcomeAcceptanceIntegrityError(
                "derived AcceptanceCommit identity collides with durable history"
            )

        _company, mission, _package, _attempt, task = _require_authority_chain(
            conn,
            request,
        )
        _require_scope_binding(conn, project_scope, request)
        _require_backend_publication(conn, request, task)

        _invoke_fault(_fault_injector, "before_acceptance_insert", conn)
        try:
            _insert_acceptance(conn, expected)
        except sqlite3.IntegrityError as exc:
            raise OutcomeAcceptanceConflict(
                f"AcceptanceCommit insert lost a durable uniqueness/identity race: {exc}"
            ) from exc
        _invoke_fault(_fault_injector, "after_acceptance_insert", conn)

        updated = conn.execute(
            "UPDATE missions SET kernel_state_version = kernel_state_version + 1, "
            "updated_at = ? WHERE mission_id = ? AND kernel_state_version = ? "
            "AND current_plan_revision_id = ?",
            (
                accepted_at_value,
                request.mission_id,
                request.expected_kernel_state_version,
                str(mission["current_plan_revision_id"]),
            ),
        )
        if updated.rowcount != 1:
            raise OutcomeAcceptanceConflict(
                "Mission kernel state changed during OutcomeAcceptance"
            )
        _invoke_fault(_fault_injector, "after_mission_cas", conn)

    return OutcomeAcceptanceResultV1(
        created=True,
        replay_kind="none",
        request_hash=request_hash,
        acceptance=expected,
    )
