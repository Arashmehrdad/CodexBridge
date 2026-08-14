"""Read-only Company Kernel projections derived from canonical durable facts.

The Company Kernel deliberately stores no WorkPackage lifecycle column.  This
module reconstructs bounded Company, Mission, PlanRevision, WorkPackage and
attempt views from immutable kernel facts plus ProjectScope, canonical Task and
backend publication evidence.  It creates no cache and performs no writes.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Final, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import validate_kernel_id, validate_sha256
from .store import CompanyKernelStore


WorkPackageLifecycle = Literal[
    "not_started",
    "attempt_admitted",
    "queued",
    "running",
    "awaiting_controller",
    "cancellation_pending",
    "recovery_pending",
    "uncertain",
    "terminal_unpublished",
    "published_awaiting_acceptance",
    "accepted",
    "failed_without_acceptance",
    "superseded_route",
    "scope_invalid",
]

_TERMINAL_FAILURE_TASK_STATES: Final[frozenset[str]] = frozenset(
    {"failed", "cancelled"}
)
MAX_PROJECTION_MISSIONS: Final[int] = 64
MAX_PROJECTION_ATTEMPTS: Final[int] = 64


class ProjectionError(ValueError):
    """Requested Company Kernel projection cannot be reconstructed exactly."""


class _ProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScopeValidityV1(_ProjectionModel):
    valid: bool
    reason: str = ""
    project_id: str
    resource_id: str
    stored_generation: int = Field(ge=0)
    current_generation: int = Field(ge=0)
    lifecycle_state: str = ""


class CompanyProjectionV1(_ProjectionModel):
    company_id: str
    company_key: str
    display_name: str
    executive_authority_ref: str
    mission_ids: tuple[str, ...]
    mission_count: int = Field(ge=0)
    mission_ids_truncated: bool = False


class MissionProjectionV1(_ProjectionModel):
    mission_id: str
    company_id: str
    mission_key: str
    project_id: str
    resource_id: str
    scope_generation: int = Field(ge=1)
    scope: ScopeValidityV1
    current_plan_revision_id: str | None
    plan_state_version: int = Field(ge=0)
    kernel_state_version: int = Field(ge=0)
    current_package_count: int = Field(ge=0)
    accepted_outcome_count: int = Field(ge=0)
    open_outcome_count: int = Field(ge=0)


class PlanRevisionProjectionV1(_ProjectionModel):
    plan_revision_id: str
    mission_id: str
    revision_number: int = Field(ge=1)
    parent_plan_revision_id: str | None
    plan_content_hash: str
    current: bool
    package_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    graph_manifest_hash: str = ""


class WorkPackageAttemptProjectionV1(_ProjectionModel):
    attempt_id: str
    task_id: str
    backend_kind: str = ""
    backend_ref: str = ""
    supersedes_attempt_id: str | None
    state: WorkPackageLifecycle
    task_state: str = ""
    task_phase: str = ""
    task_recovery_state: str = ""
    checkpoint_ref: str = ""
    result_ref: str = ""
    result_hash: str = ""
    published_result_hash: str = ""
    evidence_ref: str = ""
    project_task_status: str = ""
    project_attempt_status: str = ""


class WorkPackageProjectionV1(_ProjectionModel):
    work_package_id: str
    mission_id: str
    plan_revision_id: str
    current_plan: bool
    package_key: str
    outcome_id: str
    project_id: str
    target_resource_id: str
    scope_generation: int = Field(ge=1)
    scope: ScopeValidityV1
    state: WorkPackageLifecycle
    current_attempt_id: str | None
    attempt_count: int = Field(ge=0)
    attempts: tuple[WorkPackageAttemptProjectionV1, ...]
    attempts_truncated: bool = False
    acceptance_commit_id: str | None
    accepted_attempt_id: str | None
    published_result_hash: str = ""


@contextmanager
def _read_connection(store: CompanyKernelStore) -> Iterator[sqlite3.Connection]:
    if not store.db_path.exists():
        raise ProjectionError("Company Kernel database is not installed")
    uri = f"file:{store.db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _one(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...],
    *,
    label: str,
) -> sqlite3.Row:
    rows = conn.execute(sql, params).fetchall()
    if len(rows) != 1:
        if not rows:
            raise ProjectionError(f"{label} not found")
        raise ProjectionError(f"{label} identity is not unique")
    return rows[0]


def _scope_validity(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    resource_id: str,
    stored_generation: int,
) -> ScopeValidityV1:
    project = conn.execute(
        "SELECT lifecycle_state, scope_generation FROM projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if project is None:
        return ScopeValidityV1(
            valid=False,
            reason="project_missing",
            project_id=project_id,
            resource_id=resource_id,
            stored_generation=stored_generation,
            current_generation=0,
            lifecycle_state="",
        )
    lifecycle = str(project["lifecycle_state"])
    current_generation = int(project["scope_generation"])
    binding = conn.execute(
        "SELECT 1 FROM project_resource_bindings "
        "WHERE project_id = ? AND resource_id = ?",
        (project_id, resource_id),
    ).fetchone()
    reason = ""
    if lifecycle != "active":
        reason = f"project_{lifecycle}"
    elif current_generation != stored_generation:
        reason = "scope_generation_stale"
    elif binding is None:
        reason = "resource_binding_missing"
    return ScopeValidityV1(
        valid=not reason,
        reason=reason,
        project_id=project_id,
        resource_id=resource_id,
        stored_generation=stored_generation,
        current_generation=current_generation,
        lifecycle_state=lifecycle,
    )


def project_company_in_connection(
    conn: sqlite3.Connection,
    company_id: str,
) -> CompanyProjectionV1:
    validate_kernel_id(company_id, "company_id")
    company = _one(
        conn,
        "SELECT * FROM companies WHERE company_id = ?",
        (company_id,),
        label="Company",
    )
    mission_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM missions WHERE company_id = ?",
            (company_id,),
        ).fetchone()[0]
    )
    missions = conn.execute(
        "SELECT mission_id FROM missions WHERE company_id = ? ORDER BY mission_id "
        "LIMIT ?",
        (company_id, MAX_PROJECTION_MISSIONS),
    ).fetchall()
    mission_ids = tuple(str(row["mission_id"]) for row in missions)
    return CompanyProjectionV1(
        company_id=company_id,
        company_key=str(company["company_key"]),
        display_name=str(company["display_name"]),
        executive_authority_ref=str(company["executive_authority_ref"]),
        mission_ids=mission_ids,
        mission_count=mission_count,
        mission_ids_truncated=mission_count > len(mission_ids),
    )


def project_mission_in_connection(
    conn: sqlite3.Connection,
    mission_id: str,
) -> MissionProjectionV1:
    validate_kernel_id(mission_id, "mission_id")
    mission = _one(
        conn,
        "SELECT * FROM missions WHERE mission_id = ?",
        (mission_id,),
        label="Mission",
    )
    current_plan = (
        str(mission["current_plan_revision_id"])
        if mission["current_plan_revision_id"] is not None
        else None
    )
    scope = _scope_validity(
        conn,
        project_id=str(mission["project_id"]),
        resource_id=str(mission["resource_id"]),
        stored_generation=int(mission["scope_generation"]),
    )
    package_count = 0
    accepted_count = 0
    if current_plan:
        package_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM work_packages "
                "WHERE mission_id = ? AND plan_revision_id = ?",
                (mission_id, current_plan),
            ).fetchone()[0]
        )
        accepted_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM acceptance_commits acceptance "
                "JOIN work_packages package "
                "ON package.work_package_id = acceptance.work_package_id "
                "WHERE package.mission_id = ? AND package.plan_revision_id = ?",
                (mission_id, current_plan),
            ).fetchone()[0]
        )
    return MissionProjectionV1(
        mission_id=mission_id,
        company_id=str(mission["company_id"]),
        mission_key=str(mission["mission_key"]),
        project_id=str(mission["project_id"]),
        resource_id=str(mission["resource_id"]),
        scope_generation=int(mission["scope_generation"]),
        scope=scope,
        current_plan_revision_id=current_plan,
        plan_state_version=int(mission["plan_state_version"]),
        kernel_state_version=int(mission["kernel_state_version"]),
        current_package_count=package_count,
        accepted_outcome_count=accepted_count,
        open_outcome_count=max(0, package_count - accepted_count),
    )


def project_plan_revision_in_connection(
    conn: sqlite3.Connection,
    plan_revision_id: str,
) -> PlanRevisionProjectionV1:
    validate_kernel_id(plan_revision_id, "plan_revision_id")
    plan = _one(
        conn,
        "SELECT * FROM plan_revisions WHERE plan_revision_id = ?",
        (plan_revision_id,),
        label="PlanRevision",
    )
    mission = _one(
        conn,
        "SELECT current_plan_revision_id FROM missions WHERE mission_id = ?",
        (str(plan["mission_id"]),),
        label="PlanRevision Mission",
    )
    manifest = conn.execute(
        "SELECT manifest_hash, package_count, edge_count FROM plan_graph_manifests "
        "WHERE plan_revision_id = ?",
        (plan_revision_id,),
    ).fetchone()
    if manifest is None:
        package_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM work_packages WHERE plan_revision_id = ?",
                (plan_revision_id,),
            ).fetchone()[0]
        )
        edge_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM work_package_dependencies "
                "WHERE plan_revision_id = ?",
                (plan_revision_id,),
            ).fetchone()[0]
        )
        manifest_hash = ""
    else:
        package_count = int(manifest["package_count"])
        edge_count = int(manifest["edge_count"])
        manifest_hash = str(manifest["manifest_hash"])
    return PlanRevisionProjectionV1(
        plan_revision_id=plan_revision_id,
        mission_id=str(plan["mission_id"]),
        revision_number=int(plan["revision_number"]),
        parent_plan_revision_id=(
            str(plan["parent_plan_revision_id"])
            if plan["parent_plan_revision_id"] is not None
            else None
        ),
        plan_content_hash=str(plan["plan_content_hash"]),
        current=str(mission["current_plan_revision_id"] or "") == plan_revision_id,
        package_count=package_count,
        edge_count=edge_count,
        graph_manifest_hash=manifest_hash,
    )


def _attempt_scope_status(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    resource_id: str,
    scope_generation: int,
    task_id: str,
    backend_ref: str,
) -> tuple[bool, str, str]:
    if not backend_ref:
        return False, "", ""
    row = conn.execute(
        "SELECT task.status AS task_status, attempt.status AS attempt_status, "
        "attempt.project_id, attempt.resource_id, attempt.scope_generation "
        "FROM project_task_reservations task "
        "JOIN project_run_attempts attempt ON attempt.task_id = task.task_id "
        "AND attempt.run_id = ? "
        "WHERE task.task_id = ? AND task.project_id = ?",
        (backend_ref, task_id, project_id),
    ).fetchone()
    if row is None:
        return False, "", ""
    task_status = str(row["task_status"])
    attempt_status = str(row["attempt_status"])
    valid = (
        str(row["project_id"]) == project_id
        and str(row["resource_id"]) == resource_id
        and int(row["scope_generation"]) == scope_generation
        and task_status in {"reserved", "attached"}
        and attempt_status in {"reserved", "attached", "recovery_pending"}
    )
    return valid, task_status, attempt_status


def _is_sha256(value: str) -> bool:
    try:
        validate_sha256(value, "projection_hash")
    except ValueError:
        return False
    return True


def _durable_publication_state(
    conn: sqlite3.Connection,
    *,
    backend_ref: str,
    task_result_ref: str,
    task_result_hash: str,
    task_evidence_ref: str,
) -> tuple[WorkPackageLifecycle, str]:
    run = conn.execute(
        "SELECT status, exit_code, safety_failure, recovery_reason, "
        "result_publication_status, result_published_hash, result_published_at, "
        "result_publication_error, public_result_source_sha256 "
        "FROM runs WHERE run_id = ?",
        (backend_ref,),
    ).fetchone()
    if run is None:
        return "uncertain", ""
    if bool(run["safety_failure"]):
        return "uncertain", ""
    if str(run["recovery_reason"] or ""):
        return "recovery_pending", ""
    status = str(run["status"])
    if status in {"failed", "cancelled", "timed_out"}:
        return "failed_without_acceptance", ""
    if status != "completed":
        return "uncertain", ""
    if run["exit_code"] is None or int(run["exit_code"]) != 0:
        return "failed_without_acceptance", ""
    published_hash = str(run["result_published_hash"] or "")
    published = (
        str(run["result_publication_status"]) == "published"
        and not str(run["result_publication_error"] or "")
        and bool(run["result_published_at"])
        and bool(published_hash)
    )
    if not published:
        return "terminal_unpublished", ""
    source_hash = str(run["public_result_source_sha256"] or "")
    if (
        not _is_sha256(published_hash)
        or not _is_sha256(source_hash)
        or task_result_ref != backend_ref
        or task_result_hash != published_hash
        or task_evidence_ref != f"run_terminal:{backend_ref}"
    ):
        return "uncertain", ""
    return "published_awaiting_acceptance", published_hash


def _reasoning_publication_state(
    conn: sqlite3.Connection,
    *,
    backend_ref: str,
    task_result_ref: str,
    task_result_hash: str,
    task_evidence_ref: str,
) -> tuple[WorkPackageLifecycle, str]:
    if not _table_exists(conn, "reasoning_backend_runs"):
        return "uncertain", ""
    row = conn.execute(
        "SELECT * FROM reasoning_backend_runs WHERE backend_ref = ?",
        (backend_ref,),
    ).fetchone()
    if row is None:
        return "uncertain", ""
    if (
        str(row["start_delivery_disposition"]) == "outcome_unknown"
        or str(row["provider_binding_disposition"]) == "uncertain"
        or str(row["cancellation_disposition"]) == "uncertain"
    ):
        return "uncertain", ""
    if str(row["provider_terminal_claim"]) in {"failure", "cancelled"}:
        return "failed_without_acceptance", ""
    if str(row["provider_terminal_claim"]) == "incomplete":
        return "recovery_pending", ""
    if str(row["provider_terminal_claim"]) != "success":
        return "terminal_unpublished", ""
    if str(row["output_contract_disposition"]) == "invalid":
        return "failed_without_acceptance", ""
    if str(row["output_contract_disposition"]) == "uncertain":
        return "uncertain", ""
    if str(row["cancellation_disposition"]) not in {"not_requested", "rejected"}:
        return "uncertain", ""
    result_hash = str(row["result_hash"] or "")
    required_hashes = (
        result_hash,
        str(row["evidence_index_hash"] or ""),
        str(row["provider_binding_hash"] or ""),
        str(row["provider_provenance_index_hash"] or ""),
        str(row["raw_provider_evidence_root_hash"] or ""),
    )
    published = (
        str(row["start_delivery_disposition"]) == "accepted_bound"
        and str(row["provider_binding_disposition"]) == "bound"
        and str(row["output_contract_disposition"]) == "valid"
        and bool(row["provider_operation_ref"])
        and bool(row["output_contract_version"])
        and bool(row["result_ref"])
        and bool(result_hash)
        and bool(row["evidence_index_ref"])
        and bool(row["provider_binding_ref"])
        and bool(row["provider_provenance_index_ref"])
        and bool(row["raw_provider_evidence_root_ref"])
        and all(_is_sha256(value) for value in required_hashes)
        and bool(row["result_published_at"])
        and not str(row["error_code"] or "")
    )
    if not published:
        return "terminal_unpublished", ""
    if (
        task_result_ref != str(row["result_ref"])
        or task_result_hash != result_hash
        or task_evidence_ref != str(row["evidence_index_ref"])
    ):
        return "uncertain", ""
    return "published_awaiting_acceptance", result_hash


def _derive_attempt_state(
    conn: sqlite3.Connection,
    *,
    attempt: sqlite3.Row,
    package_scope: ScopeValidityV1,
    project_id: str,
    resource_id: str,
    scope_generation: int,
    accepted_attempt_id: str | None,
    superseded: bool,
) -> WorkPackageAttemptProjectionV1:
    attempt_id = str(attempt["attempt_id"])
    task_id = str(attempt["task_id"])
    task_state = str(attempt["task_state"] or "")
    task_phase = str(attempt["task_phase"] or "")
    recovery_state = str(attempt["task_recovery_state"] or "")
    backend_kind = str(attempt["backend_kind"] or "")
    backend_ref = str(attempt["backend_ref"] or "")
    task_result_ref = str(attempt["task_result_ref"] or "")
    task_result_hash = str(attempt["task_result_hash"] or "")
    task_evidence_ref = str(attempt["task_evidence_ref"] or "")
    scope_ok, project_task_status, project_attempt_status = _attempt_scope_status(
        conn,
        project_id=project_id,
        resource_id=resource_id,
        scope_generation=scope_generation,
        task_id=task_id,
        backend_ref=backend_ref,
    )

    published_hash = ""
    if accepted_attempt_id == attempt_id:
        state: WorkPackageLifecycle = "accepted"
    elif superseded:
        state = "superseded_route"
    elif not package_scope.valid or not scope_ok:
        state = "scope_invalid"
    elif project_attempt_status == "recovery_pending":
        state = "recovery_pending"
    elif not task_state:
        state = "uncertain"
    elif recovery_state not in {"", "none"}:
        state = "uncertain" if recovery_state == "unresolved" else "recovery_pending"
    elif task_state == "accepted":
        state = "attempt_admitted"
    elif task_state == "queued":
        state = "queued"
    elif task_state == "running":
        state = "running"
    elif task_state == "awaiting_controller":
        state = "awaiting_controller"
    elif task_state == "cancellation_pending":
        state = "cancellation_pending"
    elif task_state == "recovery_pending":
        state = "recovery_pending"
    elif task_state in {"uncertain", "paused"}:
        state = "uncertain"
    elif task_state in _TERMINAL_FAILURE_TASK_STATES:
        state = "failed_without_acceptance"
    elif task_state == "completed":
        if backend_kind == "soma_durable_run":
            state, published_hash = _durable_publication_state(
                conn,
                backend_ref=backend_ref,
                task_result_ref=task_result_ref,
                task_result_hash=task_result_hash,
                task_evidence_ref=task_evidence_ref,
            )
        elif backend_kind == "soma_reasoning":
            state, published_hash = _reasoning_publication_state(
                conn,
                backend_ref=backend_ref,
                task_result_ref=task_result_ref,
                task_result_hash=task_result_hash,
                task_evidence_ref=task_evidence_ref,
            )
        else:
            state = "uncertain"
    else:
        state = "uncertain"

    return WorkPackageAttemptProjectionV1(
        attempt_id=attempt_id,
        task_id=task_id,
        backend_kind=backend_kind,
        backend_ref=backend_ref,
        supersedes_attempt_id=(
            str(attempt["supersedes_attempt_id"])
            if attempt["supersedes_attempt_id"] is not None
            else None
        ),
        state=state,
        task_state=task_state,
        task_phase=task_phase,
        task_recovery_state=recovery_state,
        checkpoint_ref=str(attempt["checkpoint_ref"] or ""),
        result_ref=str(attempt["task_result_ref"] or ""),
        result_hash=task_result_hash,
        published_result_hash=published_hash,
        evidence_ref=str(attempt["task_evidence_ref"] or ""),
        project_task_status=project_task_status,
        project_attempt_status=project_attempt_status,
    )


def project_work_package_in_connection(
    conn: sqlite3.Connection,
    work_package_id: str,
) -> WorkPackageProjectionV1:
    validate_kernel_id(work_package_id, "work_package_id")
    package = _one(
        conn,
        "SELECT * FROM work_packages WHERE work_package_id = ?",
        (work_package_id,),
        label="WorkPackage",
    )
    mission = _one(
        conn,
        "SELECT current_plan_revision_id FROM missions WHERE mission_id = ?",
        (str(package["mission_id"]),),
        label="WorkPackage Mission",
    )
    current_plan = (
        str(mission["current_plan_revision_id"] or "")
        == str(package["plan_revision_id"])
    )
    scope = _scope_validity(
        conn,
        project_id=str(package["project_id"]),
        resource_id=str(package["target_resource_id"]),
        stored_generation=int(package["scope_generation"]),
    )
    acceptance = conn.execute(
        "SELECT acceptance_commit_id, attempt_id, result_published_hash "
        "FROM acceptance_commits WHERE outcome_id = ?",
        (str(package["outcome_id"]),),
    ).fetchone()
    accepted_attempt_id = (
        str(acceptance["attempt_id"]) if acceptance is not None else None
    )
    attempt_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM work_package_attempts WHERE work_package_id = ?",
            (work_package_id,),
        ).fetchone()[0]
    )
    attempts = conn.execute(
        "SELECT attempt.*, task.state AS task_state, task.phase AS task_phase, "
        "task.recovery_state AS task_recovery_state, task.backend_kind, "
        "task.backend_ref, task.checkpoint_ref, task.result_ref AS task_result_ref, "
        "task.result_hash AS task_result_hash, task.evidence_ref AS task_evidence_ref "
        "FROM work_package_attempts attempt "
        "LEFT JOIN tasks task ON task.task_id = attempt.task_id "
        "WHERE attempt.work_package_id = ? "
        "ORDER BY attempt.created_at DESC, attempt.attempt_id DESC LIMIT ?",
        (work_package_id, MAX_PROJECTION_ATTEMPTS),
    ).fetchall()
    attempts = list(reversed(attempts))
    head_rows = conn.execute(
        "SELECT attempt.attempt_id FROM work_package_attempts attempt "
        "WHERE attempt.work_package_id = ? AND NOT EXISTS ("
        "SELECT 1 FROM work_package_attempts child "
        "WHERE child.supersedes_attempt_id = attempt.attempt_id) "
        "ORDER BY attempt.created_at DESC, attempt.attempt_id DESC LIMIT 2",
        (work_package_id,),
    ).fetchall()
    head_ids = {str(row["attempt_id"]) for row in head_rows}
    attempt_views = tuple(
        _derive_attempt_state(
            conn,
            attempt=row,
            package_scope=scope,
            project_id=str(package["project_id"]),
            resource_id=str(package["target_resource_id"]),
            scope_generation=int(package["scope_generation"]),
            accepted_attempt_id=accepted_attempt_id,
            superseded=str(row["attempt_id"]) not in head_ids,
        )
        for row in attempts
    )

    head_attempts = [view for view in attempt_views if view.attempt_id in head_ids]
    published_hash = ""
    if acceptance is not None:
        state: WorkPackageLifecycle = "accepted"
        current_attempt_id = accepted_attempt_id
        published_hash = str(acceptance["result_published_hash"] or "")
    elif not scope.valid:
        state = "scope_invalid"
        current_attempt_id = head_attempts[0].attempt_id if len(head_attempts) == 1 else None
    elif not attempt_views:
        state = "not_started"
        current_attempt_id = None
    elif len(head_attempts) != 1:
        state = "uncertain"
        current_attempt_id = None
    else:
        head = head_attempts[0]
        state = head.state
        current_attempt_id = head.attempt_id
        published_hash = (
            head.published_result_hash
            if state == "published_awaiting_acceptance"
            else ""
        )

    return WorkPackageProjectionV1(
        work_package_id=work_package_id,
        mission_id=str(package["mission_id"]),
        plan_revision_id=str(package["plan_revision_id"]),
        current_plan=current_plan,
        package_key=str(package["package_key"]),
        outcome_id=str(package["outcome_id"]),
        project_id=str(package["project_id"]),
        target_resource_id=str(package["target_resource_id"]),
        scope_generation=int(package["scope_generation"]),
        scope=scope,
        state=state,
        current_attempt_id=current_attempt_id,
        attempt_count=attempt_count,
        attempts=attempt_views,
        attempts_truncated=attempt_count > len(attempt_views),
        acceptance_commit_id=(
            str(acceptance["acceptance_commit_id"]) if acceptance is not None else None
        ),
        accepted_attempt_id=accepted_attempt_id,
        published_result_hash=published_hash,
    )


class CompanyKernelProjectionService:
    """Read-only no-cache projection facade."""

    def __init__(self, store: CompanyKernelStore):
        self.store = store

    @classmethod
    def from_runs_dir(cls, runs_dir: Path) -> "CompanyKernelProjectionService":
        return cls(CompanyKernelStore(runs_dir))

    def company(self, company_id: str) -> CompanyProjectionV1:
        with _read_connection(self.store) as conn:
            return project_company_in_connection(conn, company_id)

    def mission(self, mission_id: str) -> MissionProjectionV1:
        with _read_connection(self.store) as conn:
            return project_mission_in_connection(conn, mission_id)

    def plan_revision(self, plan_revision_id: str) -> PlanRevisionProjectionV1:
        with _read_connection(self.store) as conn:
            return project_plan_revision_in_connection(conn, plan_revision_id)

    def work_package(self, work_package_id: str) -> WorkPackageProjectionV1:
        with _read_connection(self.store) as conn:
            return project_work_package_in_connection(conn, work_package_id)
