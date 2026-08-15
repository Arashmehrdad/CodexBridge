"""Bounded deterministic admission of current-plan WorkPackageAttempts.

Admission computes/fixes exact dependency proofs, reserves one immutable
WorkPackageAttempt plus its canonical Task and ProjectScope ownership in one
SQLite transaction, then starts the already-reserved Task outside that
transaction. It is not a scheduler loop.
"""

from __future__ import annotations

import json
from base64 import b64decode
from datetime import datetime, timezone
from typing import Any, Final, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from soma.company_kernel.models import (
    ATTEMPT_ID_DOMAIN,
    AcceptanceCommit,
    canonical_hash,
    canonical_json,
    derive_identity,
    route_request_hash,
)
from soma.company_kernel.dependencies import (
    DependencyEdgeContextV1,
    DependencyProofEvaluationError,
    EvidenceAvailableCandidateV1,
    PersistedDependencyProofV1,
    PublishedSuccessCandidateV1,
    SettledAttemptFactV1,
    evaluate_accepted_outcome,
    evaluate_evidence_available,
    evaluate_published_success,
    evaluate_settled,
    persist_dependency_proof_in_connection,
)
from soma.reasoning.backends import reasoning_spec_hash, reasoning_spec_ref
from soma.reasoning.models import ReasoningHashedReferenceV1, ReasoningSpecV1
from soma.tasks.backends import DurableCommandSpec
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    make_task_id,
    normalize_scoped_durable_command_request,
    normalized_request_hash,
    run_input_reference,
)

from .task_routes import (
    CompanyTaskRequestV1,
    DurableCommandTaskRequestV1,
    ReasoningTaskRequestV1,
)


MAX_ADMISSION_BATCH: Final[int] = 8
LEGACY_ATTEMPT_ROUTE_SCHEMA: Final[str] = "work_package_attempt_route.v1"
ATTEMPT_ROUTE_SCHEMA: Final[str] = "work_package_attempt_route.v2"


class AdmissionError(ValueError):
    """Current facts do not authorize this bounded admission."""


class AdmissionNotReady(AdmissionError):
    """Current exact dependency evidence does not yet satisfy admission."""


class _FrozenAdmissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdmissionHashedReferenceV1(_FrozenAdmissionModel):
    ref: str = Field(min_length=1, max_length=2048)
    hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AdmissionRequestV1(_FrozenAdmissionModel):
    mission_id: str
    work_package_id: str
    controller_request_id: str = Field(min_length=1, max_length=128)
    expected_plan_revision_id: str | None = None
    expected_plan_state_version: int | None = Field(default=None, ge=0)
    repo_name: str = Field(min_length=1, max_length=128)
    task_request: CompanyTaskRequestV1
    supersedes_attempt_id: str | None = None
    evidence_candidates: Mapping[str, EvidenceAvailableCandidateV1] = Field(
        default_factory=dict
    )
    published_success_candidates: Mapping[str, PublishedSuccessCandidateV1] = Field(
        default_factory=dict
    )


class AdmissionResultV1(_FrozenAdmissionModel):
    mission_id: str
    plan_revision_id: str
    work_package_id: str
    attempt_id: str
    attempt_hash: str
    task_id: str
    proof_refs: tuple[AdmissionHashedReferenceV1, ...]
    created: bool
    task_start: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attempt_identity(
    *,
    work_package_id: str,
    outcome_id: str,
    route_hash: str,
    supersedes_attempt_id: str | None,
) -> tuple[str, str]:
    payload = {
        "schema": ATTEMPT_ID_DOMAIN,
        "work_package_id": work_package_id,
        "outcome_id": outcome_id,
        "route_request_hash": route_hash,
        "supersedes_attempt_id": supersedes_attempt_id,
    }
    return derive_identity(ATTEMPT_ID_DOMAIN, payload), canonical_hash(
        ATTEMPT_ID_DOMAIN, payload
    )


def _existing_controller_attempt(conn, controller_request_id: str):
    rows = conn.execute(
        "SELECT * FROM work_package_attempts WHERE controller_request_id = ? ORDER BY attempt_id",
        (controller_request_id,),
    ).fetchall()
    if len(rows) > 1:
        raise AdmissionError(
            "controller request is bound to multiple WorkPackageAttempts; durable state is inconsistent"
        )
    return rows[0] if rows else None


def _proof_refs_from_route(
    conn, route_descriptor: Mapping[str, Any]
) -> tuple[AdmissionHashedReferenceV1, ...]:
    raw_refs = route_descriptor.get("dependency_proof_refs", [])
    if not isinstance(raw_refs, list):
        raise AdmissionError(
            "stored WorkPackageAttempt dependency proof refs are invalid"
        )
    refs = tuple(
        sorted(
            (AdmissionHashedReferenceV1.model_validate(item) for item in raw_refs),
            key=lambda item: (item.ref, item.hash),
        )
    )
    if len(refs) != len({item.ref for item in refs}):
        raise AdmissionError(
            "stored WorkPackageAttempt dependency proof refs are duplicated"
        )
    for item in refs:
        prefix = "dependency-proof:"
        if not item.ref.startswith(prefix):
            raise AdmissionError(
                "stored WorkPackageAttempt contains an invalid proof ref"
            )
        proof_id = item.ref[len(prefix) :]
        durable = conn.execute(
            "SELECT proof_hash FROM dependency_satisfaction_proofs WHERE proof_id = ?",
            (proof_id,),
        ).fetchone()
        if durable is None or str(durable["proof_hash"]) != item.hash:
            raise AdmissionError(
                "stored WorkPackageAttempt dependency proof identity is unavailable"
            )
    return refs


def _reasoning_proof_refs(
    proof_refs: tuple[AdmissionHashedReferenceV1, ...],
) -> tuple[ReasoningHashedReferenceV1, ...]:
    return tuple(
        ReasoningHashedReferenceV1(ref=item.ref, hash=item.hash) for item in proof_refs
    )


def _prepare_task_route(
    request: AdmissionRequestV1,
    *,
    target,
    binding,
    effective_repo_name: str,
    proof_refs: tuple[AdmissionHashedReferenceV1, ...],
) -> tuple[dict[str, Any], DurableCommandSpec | ReasoningSpecV1]:
    task_request = request.task_request
    if isinstance(task_request, DurableCommandTaskRequestV1):
        normalized = normalize_scoped_durable_command_request(
            project_id=binding.project_id,
            resource_id=binding.resource_id,
            repo_name=effective_repo_name,
            profile_id=task_request.profile_id,
            argv=list(task_request.argv),
            working_directory=task_request.working_directory,
            environment=dict(task_request.environment),
            stdin_text=task_request.stdin_text,
            stdin_base64=task_request.stdin_base64,
            timeout_seconds=task_request.timeout_seconds,
            parent_task_id=task_request.parent_task_id,
        )
        route = {
            "task_kind": TaskKind.DURABLE_COMMAND.value,
            "backend_kind": BackendKind.SOMA_DURABLE_RUN.value,
            "request_hash": normalized_request_hash(normalized),
        }
        launch_spec = DurableCommandSpec(
            repo_name=effective_repo_name,
            profile_id=task_request.profile_id,
            argv=list(task_request.argv),
            working_directory=task_request.working_directory,
            environment=dict(task_request.environment),
            stdin_text=task_request.stdin_text,
            stdin_bytes=(
                b64decode(task_request.stdin_base64, validate=True)
                if task_request.stdin_base64 is not None
                else None
            ),
            timeout_seconds=task_request.timeout_seconds,
        )
        return route, launch_spec

    if isinstance(task_request, ReasoningTaskRequestV1):
        final_spec = task_request.reasoning_spec.model_copy(
            update={
                "assignment_ref": f"work-package:{request.work_package_id}",
                "assignment_hash": str(target["contract_hash"]),
                "dependency_proof_refs": _reasoning_proof_refs(proof_refs),
            }
        )
        spec_ref = reasoning_spec_ref(final_spec)
        spec_hash = reasoning_spec_hash(final_spec)
        route = {
            "task_kind": TaskKind.REASONING.value,
            "backend_kind": BackendKind.SOMA_REASONING.value,
            "request_hash": normalized_request_hash(
                {
                    "task_kind": TaskKind.REASONING.value,
                    "backend_kind": BackendKind.SOMA_REASONING.value,
                    "reasoning_spec_ref": spec_ref,
                    "reasoning_spec_hash": spec_hash,
                    "parent_task_id": task_request.parent_task_id,
                }
            ),
            "reasoning_spec": {"ref": spec_ref, "hash": spec_hash},
        }
        return route, final_spec

    raise AdmissionError("unsupported Company canonical Task request")


def _company_task_request_hash(
    *,
    attempt_id: str,
    attempt_hash: str,
    task_route: Mapping[str, Any],
    proof_refs: tuple[AdmissionHashedReferenceV1, ...],
) -> str:
    return normalized_request_hash(
        {
            "hash_domain": "soma.company.work_package_task_request.v1",
            "work_package_attempt_ref": attempt_id,
            "work_package_attempt_hash": attempt_hash,
            "task_route": dict(task_route),
            "dependency_proof_refs": [
                {"ref": item.ref, "hash": item.hash} for item in proof_refs
            ],
        }
    )


def _replay_existing_attempt(
    task_manager,
    request: AdmissionRequestV1,
    *,
    binding,
    effective_repo_name: str,
    existing_attempt,
) -> AdmissionResultV1:
    if str(existing_attempt["work_package_id"]) != request.work_package_id:
        raise AdmissionError(
            "controller request already owns a different WorkPackageAttempt"
        )
    conn = task_manager.store.connect()
    try:
        target = conn.execute(
            "SELECT * FROM work_packages WHERE work_package_id = ? AND mission_id = ?",
            (request.work_package_id, request.mission_id),
        ).fetchone()
        if target is None:
            raise AdmissionError(
                "replayed WorkPackage no longer exists in Mission history"
            )
        route_descriptor = json.loads(str(existing_attempt["route_descriptor_json"]))
        if not isinstance(route_descriptor, dict):
            raise AdmissionError(
                "stored WorkPackageAttempt route descriptor is invalid"
            )
        proof_refs = _proof_refs_from_route(conn, route_descriptor)
    finally:
        conn.close()

    route_schema = str(route_descriptor.get("schema") or "")
    if route_schema == LEGACY_ATTEMPT_ROUTE_SCHEMA:
        raise AdmissionError(
            "legacy reasoning-coupled WorkPackageAttempt route v1 is frozen and non-replayable"
        )
    if route_schema != ATTEMPT_ROUTE_SCHEMA:
        raise AdmissionError(
            f"unsupported WorkPackageAttempt route schema: {route_schema}"
        )

    expected_task_route, launch_spec = _prepare_task_route(
        request,
        target=target,
        binding=binding,
        effective_repo_name=effective_repo_name,
        proof_refs=proof_refs,
    )
    if route_descriptor.get("task_route") != expected_task_route:
        raise AdmissionError(
            "controller replay canonical Task route differs from the frozen WorkPackageAttempt"
        )
    stored_scope = route_descriptor.get("project_scope")
    if stored_scope != {
        "project_id": binding.project_id,
        "resource_id": binding.resource_id,
        "scope_generation": binding.scope_generation,
    }:
        raise AdmissionError(
            "controller replay ProjectScope differs from the frozen WorkPackageAttempt"
        )
    route_hash = route_request_hash(route_descriptor)
    if route_hash != str(existing_attempt["route_request_hash"]):
        raise AdmissionError("stored WorkPackageAttempt route hash is inconsistent")
    attempt_id, attempt_hash = _attempt_identity(
        work_package_id=request.work_package_id,
        outcome_id=str(target["outcome_id"]),
        route_hash=route_hash,
        supersedes_attempt_id=(
            str(existing_attempt["supersedes_attempt_id"])
            if existing_attempt["supersedes_attempt_id"] is not None
            else None
        ),
    )
    if (
        attempt_id != str(existing_attempt["attempt_id"])
        or attempt_hash != str(existing_attempt["request_hash"])
        or request.supersedes_attempt_id
        != (
            str(existing_attempt["supersedes_attempt_id"])
            if existing_attempt["supersedes_attempt_id"] is not None
            else None
        )
    ):
        raise AdmissionError(
            "controller replay does not match the frozen WorkPackageAttempt identity"
        )
    task_id = str(existing_attempt["task_id"])
    expected_task_hash = _company_task_request_hash(
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        task_route=expected_task_route,
        proof_refs=proof_refs,
    )
    try:
        task = task_manager.store.get_task(task_id)
    except KeyError as exc:
        raise AdmissionError(
            "replayed WorkPackageAttempt canonical Task is missing"
        ) from exc
    if (
        task.request_hash != expected_task_hash
        or task.task_kind.value != str(expected_task_route["task_kind"])
        or task.backend_kind.value != str(expected_task_route["backend_kind"])
    ):
        raise AdmissionError(
            "replayed canonical Task differs from the frozen WorkPackageAttempt route"
        )
    task_start = task_manager.start_reserved_task(
        task_id=task_id,
        project_id=binding.project_id,
        expected_request_hash=expected_task_hash,
        launch_spec=launch_spec,
    )
    return AdmissionResultV1(
        mission_id=request.mission_id,
        plan_revision_id=str(target["plan_revision_id"]),
        work_package_id=request.work_package_id,
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        task_id=task_id,
        proof_refs=proof_refs,
        created=False,
        task_start=task_start,
    )


def _assert_new_attempt_allowed(conn, target, request: AdmissionRequestV1) -> None:
    rows = conn.execute(
        """
        SELECT attempt.*, task.state AS task_state
        FROM work_package_attempts attempt
        JOIN tasks task ON task.task_id = attempt.task_id
        WHERE attempt.work_package_id = ?
        ORDER BY attempt.created_at, attempt.attempt_id
        """,
        (request.work_package_id,),
    ).fetchall()
    active = [
        row
        for row in rows
        if str(row["task_state"]) not in {"completed", "failed", "cancelled"}
        and not str(row["containment_evidence_ref"] or "")
    ]
    if active:
        raise AdmissionError(
            "single_active WorkPackage already has an active or uncontained Attempt"
        )
    if not rows:
        if request.supersedes_attempt_id is not None:
            raise AdmissionError(
                "first WorkPackageAttempt cannot supersede an unknown Attempt"
            )
        return
    if request.supersedes_attempt_id is None:
        raise AdmissionError(
            "a successor WorkPackageAttempt must explicitly supersede the current head Attempt"
        )
    attempt_ids = {str(row["attempt_id"]) for row in rows}
    superseded_ids = {
        str(row["supersedes_attempt_id"])
        for row in rows
        if row["supersedes_attempt_id"] is not None
    }
    heads = sorted(attempt_ids - superseded_ids)
    if len(heads) != 1 or request.supersedes_attempt_id != heads[0]:
        raise AdmissionError(
            "successor WorkPackageAttempt must supersede the exact current head Attempt"
        )
    parent = next(row for row in rows if str(row["attempt_id"]) == heads[0])
    if str(parent["task_state"]) not in {
        "completed",
        "failed",
        "cancelled",
    } and not str(parent["containment_evidence_ref"] or ""):
        raise AdmissionError(
            "superseded WorkPackageAttempt is not terminal or contained"
        )


def _context_from_edge(
    conn, edge, kernel_state_version: int
) -> DependencyEdgeContextV1:
    upstream = conn.execute(
        "SELECT outcome_id FROM work_packages WHERE work_package_id = ?",
        (str(edge["upstream_work_package_id"]),),
    ).fetchone()
    if upstream is None:
        raise AdmissionError("dependency upstream WorkPackage is missing")
    selector_ref = str(edge["evidence_selector_ref"] or "") or None
    selector_hash = str(edge["evidence_selector_hash"] or "") or None
    return DependencyEdgeContextV1(
        mission_id=str(edge["mission_id"]),
        plan_revision_id=str(edge["plan_revision_id"]),
        edge_id=str(edge["edge_id"]),
        edge_hash=str(edge["edge_hash"]),
        requirement=str(edge["requirement"]),
        upstream_work_package_id=str(edge["upstream_work_package_id"]),
        upstream_outcome_id=str(upstream["outcome_id"]),
        downstream_work_package_id=str(edge["downstream_work_package_id"]),
        evidence_selector_ref=selector_ref,
        evidence_selector_hash=selector_hash,
        observed_kernel_state_version=kernel_state_version,
    )


def _accepted_outcome_proof(conn, context: DependencyEdgeContextV1, observed_at: str):
    rows = conn.execute(
        "SELECT * FROM acceptance_commits WHERE mission_id = ? "
        "AND work_package_id = ? AND outcome_id = ? ORDER BY accepted_at, acceptance_commit_id",
        (
            context.mission_id,
            context.upstream_work_package_id,
            context.upstream_outcome_id,
        ),
    ).fetchall()
    if len(rows) != 1:
        raise AdmissionNotReady(
            "accepted_outcome requires exactly one authoritative AcceptanceCommit"
        )
    return evaluate_accepted_outcome(
        context,
        AcceptanceCommit.model_validate(dict(rows[0])),
        observed_at=observed_at,
    )


def _verify_published_success_candidate(conn, context, candidate) -> None:
    attempt = conn.execute(
        "SELECT * FROM work_package_attempts WHERE attempt_id = ?",
        (candidate.attempt_id,),
    ).fetchone()
    if attempt is None:
        raise AdmissionNotReady("published_success attempt does not exist")
    if (
        str(attempt["work_package_id"]) != context.upstream_work_package_id
        or str(attempt["outcome_id"]) != context.upstream_outcome_id
        or str(attempt["task_id"]) != candidate.task_id
    ):
        raise AdmissionNotReady("published_success attempt/task identity mismatch")
    task = conn.execute(
        "SELECT * FROM tasks WHERE task_id = ?", (candidate.task_id,)
    ).fetchone()
    if task is None:
        raise AdmissionNotReady("published_success canonical Task is missing")
    if (
        str(task["backend_kind"]) != BackendKind.SOMA_DURABLE_RUN.value
        or str(task["backend_ref"]) != candidate.run_id
        or str(task["state"]) != "completed"
    ):
        raise AdmissionNotReady(
            "published_success requires a completed durable-Run-backed canonical Task"
        )
    run_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs'"
    ).fetchone()
    if run_table is None:
        raise AdmissionError("published_success durable Run table is missing")
    run = conn.execute(
        "SELECT * FROM runs WHERE run_id = ?", (candidate.run_id,)
    ).fetchone()
    if run is None:
        raise AdmissionNotReady("published_success durable Run is missing")
    if (
        str(run["result_publication_status"] or "") != "published"
        or str(run["result_published_hash"] or "") != candidate.result_published_hash
    ):
        raise AdmissionNotReady("published_success Run publication identity mismatch")


def _settled_attempt_facts(conn, context: DependencyEdgeContextV1):
    rows = conn.execute(
        """
        SELECT attempt.attempt_id, attempt.task_id, attempt.supersedes_attempt_id,
               attempt.containment_evidence_ref, attempt.containment_evidence_hash,
               task.state AS task_state
        FROM work_package_attempts attempt
        JOIN tasks task ON task.task_id = attempt.task_id
        WHERE attempt.work_package_id = ?
        ORDER BY attempt.attempt_id
        """,
        (context.upstream_work_package_id,),
    ).fetchall()
    return tuple(
        SettledAttemptFactV1(
            attempt_id=str(row["attempt_id"]),
            task_id=str(row["task_id"]),
            supersedes_attempt_id=(
                str(row["supersedes_attempt_id"])
                if row["supersedes_attempt_id"] is not None
                else None
            ),
            task_state=str(row["task_state"]),
            containment_evidence_ref=(
                str(row["containment_evidence_ref"])
                if str(row["containment_evidence_ref"] or "")
                else None
            ),
            containment_evidence_hash=(
                str(row["containment_evidence_hash"])
                if str(row["containment_evidence_hash"] or "")
                else None
            ),
        )
        for row in rows
    )


def _evaluate_and_persist_proofs(
    conn,
    *,
    mission,
    target,
    request: AdmissionRequestV1,
    observed_at: str,
) -> tuple[PersistedDependencyProofV1, ...]:
    edges = conn.execute(
        "SELECT * FROM work_package_dependencies "
        "WHERE mission_id = ? AND plan_revision_id = ? AND downstream_work_package_id = ? "
        "ORDER BY edge_id",
        (
            request.mission_id,
            str(mission["current_plan_revision_id"]),
            request.work_package_id,
        ),
    ).fetchall()
    persisted: list[PersistedDependencyProofV1] = []
    for edge in edges:
        context = _context_from_edge(
            conn,
            edge,
            int(mission["kernel_state_version"]),
        )
        try:
            if context.requirement == "accepted_outcome":
                proof = _accepted_outcome_proof(conn, context, observed_at)
            elif context.requirement == "published_success":
                candidate = request.published_success_candidates.get(context.edge_id)
                if candidate is None:
                    raise AdmissionNotReady(
                        f"published_success candidate is missing for edge {context.edge_id}"
                    )
                _verify_published_success_candidate(conn, context, candidate)
                proof = evaluate_published_success(
                    context,
                    candidate,
                    observed_at=observed_at,
                )
            elif context.requirement == "evidence_available":
                candidate = request.evidence_candidates.get(context.edge_id)
                if candidate is None:
                    raise AdmissionNotReady(
                        f"evidence candidate is missing for edge {context.edge_id}"
                    )
                proof = evaluate_evidence_available(
                    context,
                    candidate,
                    observed_at=observed_at,
                )
            elif context.requirement == "settled":
                proof = evaluate_settled(
                    context,
                    _settled_attempt_facts(conn, context),
                    observed_at=observed_at,
                )
            else:  # pragma: no cover - schema vocabulary is closed
                raise AdmissionError(
                    f"unsupported dependency requirement {context.requirement}"
                )
        except DependencyProofEvaluationError as exc:
            raise AdmissionNotReady(str(exc)) from exc
        persisted.append(
            persist_dependency_proof_in_connection(
                conn,
                context=context,
                proof=proof,
                created_at=observed_at,
            )
        )
    return tuple(persisted)


def admit_work_package(
    task_manager,
    request: AdmissionRequestV1,
    *,
    _after_commit_hook=None,
) -> AdmissionResultV1:
    """Admit one current-plan WorkPackageAttempt with one exact canonical Task route."""

    observed_at = _utc_now()

    # Resolve ProjectScope from the immutable target WorkPackage identity.
    conn = task_manager.store.connect()
    try:
        target_identity = conn.execute(
            "SELECT project_id FROM work_packages WHERE work_package_id = ? AND mission_id = ?",
            (request.work_package_id, request.mission_id),
        ).fetchone()
        existing_attempt = _existing_controller_attempt(
            conn, request.controller_request_id
        )
    finally:
        conn.close()
    if target_identity is None:
        raise AdmissionError("target WorkPackage does not exist in Mission")
    binding, effective_repo_name = task_manager._resolve_repository_binding(
        project_id=str(target_identity["project_id"]),
        repo_name=request.repo_name,
        working_directory="",
    )

    if existing_attempt is not None:
        return _replay_existing_attempt(
            task_manager,
            request,
            binding=binding,
            effective_repo_name=effective_repo_name,
            existing_attempt=existing_attempt,
        )

    selected_backend_kind = BackendKind(request.task_request.backend_kind)
    selected_backend = task_manager._backend_for_kind(selected_backend_kind)
    if selected_backend is None:
        raise AdmissionError(
            "selected canonical Task backend is not configured: "
            f"{selected_backend_kind.value}"
        )

    task_id = None
    attempt_id = ""
    attempt_hash = ""
    task_request_hash = ""
    launch_spec: DurableCommandSpec | ReasoningSpecV1 | None = None
    proof_refs: tuple[AdmissionHashedReferenceV1, ...] = ()

    conn = task_manager.store.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        mission = conn.execute(
            "SELECT * FROM missions WHERE mission_id = ?",
            (request.mission_id,),
        ).fetchone()
        if mission is None or not str(mission["current_plan_revision_id"] or ""):
            raise AdmissionError("Mission has no current PlanRevision")
        target = conn.execute(
            "SELECT * FROM work_packages WHERE work_package_id = ? AND mission_id = ?",
            (request.work_package_id, request.mission_id),
        ).fetchone()
        if target is None:
            raise AdmissionError("target WorkPackage does not exist in Mission")
        current_plan_revision_id = str(mission["current_plan_revision_id"])
        if (
            request.expected_plan_revision_id is not None
            and request.expected_plan_revision_id != current_plan_revision_id
        ):
            raise AdmissionError(
                "Mission current PlanRevision changed before admission"
            )
        if (
            request.expected_plan_state_version is not None
            and request.expected_plan_state_version
            != int(mission["plan_state_version"])
        ):
            raise AdmissionError("Mission plan_state_version changed before admission")
        if str(target["plan_revision_id"]) != current_plan_revision_id:
            raise AdmissionError(
                "target WorkPackage is not in the current PlanRevision"
            )
        if (
            str(target["project_id"]) != binding.project_id
            or str(target["target_resource_id"]) != binding.resource_id
            or int(target["scope_generation"]) != binding.scope_generation
        ):
            raise AdmissionError(
                "target WorkPackage ProjectScope identity is stale or mismatched"
            )

        _assert_new_attempt_allowed(conn, target, request)

        proofs = _evaluate_and_persist_proofs(
            conn,
            mission=mission,
            target=target,
            request=request,
            observed_at=observed_at,
        )
        proof_refs = tuple(
            sorted(
                (
                    AdmissionHashedReferenceV1(
                        ref=f"dependency-proof:{item.proof_id}",
                        hash=item.proof.proof_hash,
                    )
                    for item in proofs
                ),
                key=lambda item: (item.ref, item.hash),
            )
        )
        task_route, launch_spec = _prepare_task_route(
            request,
            target=target,
            binding=binding,
            effective_repo_name=effective_repo_name,
            proof_refs=proof_refs,
        )
        route_descriptor = {
            "schema": ATTEMPT_ROUTE_SCHEMA,
            "work_package_id": request.work_package_id,
            "outcome_id": str(target["outcome_id"]),
            "project_scope": {
                "project_id": binding.project_id,
                "resource_id": binding.resource_id,
                "scope_generation": binding.scope_generation,
            },
            "task_route": task_route,
            "dependency_proof_refs": [
                {"ref": item.ref, "hash": item.hash} for item in proof_refs
            ],
            "supersedes_attempt_id": request.supersedes_attempt_id,
        }
        route_hash = route_request_hash(route_descriptor)
        attempt_id, attempt_hash = _attempt_identity(
            work_package_id=request.work_package_id,
            outcome_id=str(target["outcome_id"]),
            route_hash=route_hash,
            supersedes_attempt_id=request.supersedes_attempt_id,
        )

        same_attempt = conn.execute(
            "SELECT * FROM work_package_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if same_attempt is not None:
            raise AdmissionError(
                "identical WorkPackageAttempt already exists under a different controller request"
            )

        backend_kind = BackendKind(str(task_route["backend_kind"]))
        if backend_kind is not selected_backend_kind:
            raise AdmissionError("prepared canonical Task route changed backend kind")
        backend = selected_backend
        backend_ref = backend.reserve()
        task_id = make_task_id()
        task_request_hash = _company_task_request_hash(
            attempt_id=attempt_id,
            attempt_hash=attempt_hash,
            task_route=task_route,
            proof_refs=proof_refs,
        )
        parent_task_id = request.task_request.parent_task_id
        task_manager.scope_store.reserve_task_attempt(
            conn,
            binding=binding,
            task_id=task_id,
            run_id=backend_ref,
            parent_task_id=parent_task_id,
        )

        backend_identity: dict[str, Any] = {
            "engine": backend_kind.value,
            "work_package_attempt_ref": attempt_id,
            "work_package_attempt_hash": attempt_hash,
            "project_id": binding.project_id,
            "resource_id": binding.resource_id,
            "scope_generation": binding.scope_generation,
        }
        if isinstance(request.task_request, DurableCommandTaskRequestV1):
            backend_identity.update(
                {
                    "run_tool": backend.executor,
                    "repo_name": effective_repo_name,
                    "profile_id": request.task_request.profile_id,
                }
            )
            objective_ref = run_input_reference(backend_ref)
            constraints_ref = run_input_reference(backend_ref)
        else:
            assert isinstance(launch_spec, ReasoningSpecV1)
            reasoning_identity = task_route.get("reasoning_spec") or {}
            backend_identity.update(
                {
                    "reasoning_spec_ref": str(reasoning_identity.get("ref") or ""),
                    "reasoning_spec_hash": str(reasoning_identity.get("hash") or ""),
                }
            )
            objective_ref = launch_spec.assignment_ref
            constraints_ref = launch_spec.authority_ref

        task_manager.store.reserve_task_in_connection(
            conn,
            task_id=task_id,
            task_kind=str(task_route["task_kind"]),
            controller_request_id=request.controller_request_id,
            request_hash=task_request_hash,
            backend_kind=backend_kind.value,
            backend_executor=backend.executor,
            backend_ref=backend_ref,
            backend_identity=backend_identity,
            objective_ref=objective_ref,
            constraints_ref=constraints_ref,
            workspace_kind="repository",
            workspace_ref=effective_repo_name,
            parent_task_id=parent_task_id,
        )
        task_manager.scope_store.attach_task(conn, task_id)
        conn.execute(
            """
                    INSERT INTO work_package_attempts(
                        attempt_id, work_package_id, outcome_id, task_id,
                        route_request_hash, route_descriptor_json,
                        supersedes_attempt_id, containment_evidence_ref,
                        containment_evidence_hash, controller_request_id,
                        request_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?)
                    """,
            (
                attempt_id,
                request.work_package_id,
                str(target["outcome_id"]),
                task_id,
                route_hash,
                canonical_json(route_descriptor),
                request.supersedes_attempt_id,
                request.controller_request_id,
                attempt_hash,
                observed_at,
            ),
        )
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()

    if task_id is None or launch_spec is None:
        raise AdmissionError("admission did not resolve a canonical Task route")
    if _after_commit_hook is not None:
        _after_commit_hook(attempt_id, task_id)

    # TaskManager, not Company, owns backend launch after the shared reservation commits.
    task_start = task_manager.start_reserved_task(
        task_id=task_id,
        project_id=binding.project_id,
        expected_request_hash=task_request_hash,
        launch_spec=launch_spec,
    )
    return AdmissionResultV1(
        mission_id=request.mission_id,
        plan_revision_id=str(mission["current_plan_revision_id"]),
        work_package_id=request.work_package_id,
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        task_id=task_id,
        proof_refs=proof_refs,
        created=True,
        task_start=task_start,
    )


def admit_work_package_batch(
    task_manager,
    requests: Sequence[AdmissionRequestV1],
    *,
    max_batch: int = MAX_ADMISSION_BATCH,
) -> tuple[AdmissionResultV1, ...]:
    """Run one bounded admission pass; never loop or wait for future readiness."""

    if max_batch < 1 or max_batch > MAX_ADMISSION_BATCH:
        raise AdmissionError(f"max_batch must be within 1..{MAX_ADMISSION_BATCH}")
    if len(requests) > max_batch:
        raise AdmissionError("requested admission set exceeds this bounded pass")
    ordered = sorted(
        requests,
        key=lambda item: (
            item.mission_id,
            item.work_package_id,
            item.controller_request_id,
        ),
    )
    return tuple(admit_work_package(task_manager, request) for request in ordered)
