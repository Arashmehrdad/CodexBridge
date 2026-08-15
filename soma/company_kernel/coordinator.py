"""Bounded deterministic current-plan admission coordinator.

The coordinator is intentionally stateless. It scans only the caller-supplied
prepared routes for the exact current PlanRevision, orders them by immutable
``package_key``, replays already-reserved controller identities without
consuming capacity, and admits at most the caller bound and canonical
concurrency capacity. Each actual reservation remains owned by the lower-level
Company Kernel admission transaction.

There is no scheduler loop, readiness table, provider/model inference, semantic
adjudication, or acceptance creation here.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.dependencies import (
    EvidenceAvailableCandidateV1,
    PublishedSuccessCandidateV1,
)
from soma.company_kernel.models import validate_kernel_id, validate_opaque

from .admission import (
    AdmissionError,
    AdmissionNotReady,
    AdmissionRequestV1,
    AdmissionResultV1,
    admit_work_package,
)
from .task_routes import CompanyTaskRequestV1


MAX_COORDINATOR_PACKAGES = 32
CANONICAL_CONCURRENCY_LIMITS = (1, 2, 4, 8)


class _FrozenCoordinatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreparedTaskAdmissionV1(_FrozenCoordinatorModel):
    work_package_id: str
    repo_name: str = Field(min_length=1, max_length=128)
    task_request: CompanyTaskRequestV1
    supersedes_attempt_id: str | None = None
    evidence_candidates: Mapping[str, EvidenceAvailableCandidateV1] = Field(
        default_factory=dict
    )
    published_success_candidates: Mapping[str, PublishedSuccessCandidateV1] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _validate_prepared_route(self):
        validate_kernel_id(self.work_package_id, "work_package_id")
        if self.supersedes_attempt_id is not None:
            validate_kernel_id(self.supersedes_attempt_id, "attempt_id")
        return self


class AdmitReadyWorkRequestV1(_FrozenCoordinatorModel):
    mission_id: str
    expected_plan_revision_id: str
    expected_plan_state_version: int = Field(ge=0)
    controller_request_id: str = Field(min_length=1, max_length=128)
    max_new_attempts: int = Field(ge=0, le=MAX_COORDINATOR_PACKAGES)
    canonical_concurrency_limit: Literal[1, 2, 4, 8]
    prepared_admissions: tuple[PreparedTaskAdmissionV1, ...] = Field(
        default=(), max_length=MAX_COORDINATOR_PACKAGES
    )

    @model_validator(mode="after")
    def _validate_request(self):
        validate_kernel_id(self.mission_id, "mission_id")
        validate_kernel_id(self.expected_plan_revision_id, "plan_revision_id")
        validate_opaque(
            self.controller_request_id,
            "controller_request_id",
            max_length=128,
        )
        package_ids = [item.work_package_id for item in self.prepared_admissions]
        if len(package_ids) != len(set(package_ids)):
            raise ValueError("prepared_admissions must contain unique WorkPackages")
        return self


class CoordinatorDeferredV1(_FrozenCoordinatorModel):
    work_package_id: str
    package_key: str = Field(min_length=1, max_length=128)
    reason: Literal["not_ready", "capacity"]
    detail: str = Field(default="", max_length=2048)


class AdmitReadyWorkResultV1(_FrozenCoordinatorModel):
    mission_id: str
    plan_revision_id: str
    plan_state_version: int
    controller_request_id: str
    canonical_concurrency_limit: Literal[1, 2, 4, 8]
    max_new_attempts: int
    active_attempts_before: int = Field(ge=0)
    active_attempts_after: int = Field(ge=0)
    considered_package_keys: tuple[str, ...]
    admitted: tuple[AdmissionResultV1, ...]
    replayed: tuple[AdmissionResultV1, ...]
    deferred: tuple[CoordinatorDeferredV1, ...]


class _PreparedRow:
    def __init__(self, package_key: str, prepared: PreparedTaskAdmissionV1):
        self.package_key = package_key
        self.prepared = prepared


def _derived_package_controller_request_id(
    root_request_id: str, package_id: str
) -> str:
    digest = sha256(f"{root_request_id}\0{package_id}".encode("utf-8")).hexdigest()
    return f"coordpkg_{digest[:32]}"


def _require_expected_plan(conn, request: AdmitReadyWorkRequestV1):
    mission = conn.execute(
        "SELECT * FROM missions WHERE mission_id = ?",
        (request.mission_id,),
    ).fetchone()
    if mission is None:
        raise AdmissionError("Mission does not exist")
    current_plan = str(mission["current_plan_revision_id"] or "")
    if current_plan != request.expected_plan_revision_id:
        raise AdmissionError(
            "Mission current PlanRevision differs from coordinator expectation"
        )
    if int(mission["plan_state_version"]) != request.expected_plan_state_version:
        raise AdmissionError(
            "Mission plan_state_version differs from coordinator expectation"
        )
    return mission


def _active_attempt_count(conn, mission_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM work_package_attempts attempt
        JOIN work_packages package ON package.work_package_id = attempt.work_package_id
        JOIN tasks task ON task.task_id = attempt.task_id
        WHERE package.mission_id = ?
          AND task.state NOT IN ('completed', 'failed', 'cancelled')
          AND COALESCE(attempt.containment_evidence_ref, '') = ''
        """,
        (mission_id,),
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def _existing_package_controller_attempt(conn, controller_request_id: str):
    rows = conn.execute(
        "SELECT attempt_id, work_package_id FROM work_package_attempts "
        "WHERE controller_request_id = ? ORDER BY attempt_id",
        (controller_request_id,),
    ).fetchall()
    if len(rows) > 1:
        raise AdmissionError(
            "derived package controller request owns multiple WorkPackageAttempts"
        )
    return rows[0] if rows else None


def _admission_request(
    request: AdmitReadyWorkRequestV1,
    prepared: PreparedTaskAdmissionV1,
) -> AdmissionRequestV1:
    return AdmissionRequestV1(
        mission_id=request.mission_id,
        work_package_id=prepared.work_package_id,
        controller_request_id=_derived_package_controller_request_id(
            request.controller_request_id,
            prepared.work_package_id,
        ),
        expected_plan_revision_id=request.expected_plan_revision_id,
        expected_plan_state_version=request.expected_plan_state_version,
        repo_name=prepared.repo_name,
        task_request=prepared.task_request,
        supersedes_attempt_id=prepared.supersedes_attempt_id,
        evidence_candidates=prepared.evidence_candidates,
        published_success_candidates=prepared.published_success_candidates,
    )


def admit_ready_work(
    task_manager, request: AdmitReadyWorkRequestV1
) -> AdmitReadyWorkResultV1:
    """Run one bounded deterministic admission pass over prepared current-plan routes."""

    conn = task_manager.store.connect()
    try:
        _require_expected_plan(conn, request)
        rows: list[_PreparedRow] = []
        for prepared in request.prepared_admissions:
            package = conn.execute(
                "SELECT package_key, plan_revision_id FROM work_packages "
                "WHERE work_package_id = ? AND mission_id = ?",
                (prepared.work_package_id, request.mission_id),
            ).fetchone()
            if package is None:
                raise AdmissionError(
                    f"prepared WorkPackage {prepared.work_package_id} does not exist in Mission"
                )
            if str(package["plan_revision_id"]) != request.expected_plan_revision_id:
                raise AdmissionError(
                    f"prepared WorkPackage {prepared.work_package_id} is not in expected PlanRevision"
                )
            rows.append(_PreparedRow(str(package["package_key"]), prepared))
        rows.sort(key=lambda item: (item.package_key, item.prepared.work_package_id))
        active_before = _active_attempt_count(conn, request.mission_id)
        existing_by_package: dict[str, bool] = {}
        for item in rows:
            controller_id = _derived_package_controller_request_id(
                request.controller_request_id,
                item.prepared.work_package_id,
            )
            existing = _existing_package_controller_attempt(conn, controller_id)
            if (
                existing is not None
                and str(existing["work_package_id"]) != item.prepared.work_package_id
            ):
                raise AdmissionError(
                    "derived package controller request belongs to another WorkPackage"
                )
            existing_by_package[item.prepared.work_package_id] = existing is not None
    finally:
        conn.close()

    available_capacity = max(0, request.canonical_concurrency_limit - active_before)
    new_limit = min(request.max_new_attempts, available_capacity)
    admitted: list[AdmissionResultV1] = []
    replayed: list[AdmissionResultV1] = []
    deferred: list[CoordinatorDeferredV1] = []

    for item in rows:
        prepared = item.prepared
        package_request = _admission_request(request, prepared)
        if existing_by_package[prepared.work_package_id]:
            replayed.append(admit_work_package(task_manager, package_request))
            continue
        if len(admitted) >= new_limit:
            deferred.append(
                CoordinatorDeferredV1(
                    work_package_id=prepared.work_package_id,
                    package_key=item.package_key,
                    reason="capacity",
                    detail="canonical concurrency/new-attempt capacity exhausted for this pass",
                )
            )
            continue
        try:
            result = admit_work_package(task_manager, package_request)
        except AdmissionNotReady as exc:
            deferred.append(
                CoordinatorDeferredV1(
                    work_package_id=prepared.work_package_id,
                    package_key=item.package_key,
                    reason="not_ready",
                    detail=str(exc),
                )
            )
            continue
        if result.created:
            admitted.append(result)
        else:
            replayed.append(result)

    conn = task_manager.store.connect()
    try:
        _require_expected_plan(conn, request)
        active_after = _active_attempt_count(conn, request.mission_id)
    finally:
        conn.close()

    return AdmitReadyWorkResultV1(
        mission_id=request.mission_id,
        plan_revision_id=request.expected_plan_revision_id,
        plan_state_version=request.expected_plan_state_version,
        controller_request_id=request.controller_request_id,
        canonical_concurrency_limit=request.canonical_concurrency_limit,
        max_new_attempts=request.max_new_attempts,
        active_attempts_before=active_before,
        active_attempts_after=active_after,
        considered_package_keys=tuple(item.package_key for item in rows),
        admitted=tuple(admitted),
        replayed=tuple(replayed),
        deferred=tuple(deferred),
    )
