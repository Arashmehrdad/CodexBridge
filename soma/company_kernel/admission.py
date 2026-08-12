"""Bounded deterministic admission of current-plan WorkPackageAttempts.

Admission computes/fixes exact dependency proofs, reserves one immutable
WorkPackageAttempt plus its canonical Task and ProjectScope ownership in one
SQLite transaction, then starts the already-reserved Task outside that
transaction. It is not a scheduler loop.
"""

from __future__ import annotations

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
from soma.fanin.proofs import (
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
from soma.tasks.models import (
    BackendKind,
    REASONING_EXECUTOR,
    TaskKind,
    make_task_id,
    normalize_reasoning_request,
    normalized_request_hash,
)


MAX_ADMISSION_BATCH: Final[int] = 8
ATTEMPT_ROUTE_SCHEMA: Final[str] = "work_package_attempt_route.v1"


class AdmissionError(ValueError):
    """Current facts do not authorize this bounded admission."""


class _FrozenAdmissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdmissionRequestV1(_FrozenAdmissionModel):
    mission_id: str
    work_package_id: str
    controller_request_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    reasoning_spec: ReasoningSpecV1
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
    proof_refs: tuple[ReasoningHashedReferenceV1, ...]
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
        raise AdmissionError(
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
        raise AdmissionError("published_success attempt does not exist")
    if (
        str(attempt["work_package_id"]) != context.upstream_work_package_id
        or str(attempt["outcome_id"]) != context.upstream_outcome_id
        or str(attempt["task_id"]) != candidate.task_id
    ):
        raise AdmissionError("published_success attempt/task identity mismatch")
    task = conn.execute(
        "SELECT * FROM tasks WHERE task_id = ?", (candidate.task_id,)
    ).fetchone()
    if task is None:
        raise AdmissionError("published_success canonical Task is missing")
    if (
        str(task["backend_kind"]) != BackendKind.SOMA_DURABLE_RUN.value
        or str(task["backend_ref"]) != candidate.run_id
        or str(task["state"]) != "completed"
    ):
        raise AdmissionError(
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
        raise AdmissionError("published_success durable Run is missing")
    if (
        str(run["result_publication_status"] or "") != "published"
        or str(run["result_published_hash"] or "") != candidate.result_published_hash
    ):
        raise AdmissionError("published_success Run publication identity mismatch")


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
                    raise AdmissionError(
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
                    raise AdmissionError(
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
            raise AdmissionError(str(exc)) from exc
        persisted.append(
            persist_dependency_proof_in_connection(
                conn,
                context=context,
                proof=proof,
                created_at=observed_at,
            )
        )
    return tuple(persisted)


def admit_reasoning_work_package(
    task_manager,
    request: AdmissionRequestV1,
    *,
    _after_commit_hook=None,
) -> AdmissionResultV1:
    """Admit one current-plan reasoning WorkPackageAttempt, then start outside tx."""

    backend = task_manager._reasoning_backend
    if backend is None:
        raise AdmissionError("reasoning backend is not configured")
    observed_at = _utc_now()

    # Resolve ProjectScope from the immutable target WorkPackage identity.
    conn = task_manager.store.connect()
    try:
        target_identity = conn.execute(
            "SELECT project_id FROM work_packages WHERE work_package_id = ? AND mission_id = ?",
            (request.work_package_id, request.mission_id),
        ).fetchone()
        existing_attempt = conn.execute(
            "SELECT * FROM work_package_attempts WHERE controller_request_id = ?",
            (request.controller_request_id,),
        ).fetchone()
    finally:
        conn.close()
    if target_identity is None:
        raise AdmissionError("target WorkPackage does not exist in Mission")
    binding, effective_repo_name = task_manager._resolve_repository_binding(
        project_id=str(target_identity["project_id"]),
        repo_name=request.repo_name,
        working_directory="",
    )

    backend_ref = None
    task_id = None
    created = False
    final_spec = request.reasoning_spec
    attempt_id = ""
    attempt_hash = ""
    proof_refs: tuple[ReasoningHashedReferenceV1, ...] = ()

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
        if str(target["plan_revision_id"]) != str(mission["current_plan_revision_id"]):
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
                    ReasoningHashedReferenceV1(
                        ref=f"dependency-proof:{item.proof_id}",
                        hash=item.proof.proof_hash,
                    )
                    for item in proofs
                ),
                key=lambda item: (item.ref, item.hash),
            )
        )
        final_spec = request.reasoning_spec.model_copy(
            update={
                "assignment_ref": f"work-package:{request.work_package_id}",
                "assignment_hash": str(target["contract_hash"]),
                "dependency_proof_refs": proof_refs,
            }
        )
        spec_ref = reasoning_spec_ref(final_spec)
        spec_hash = reasoning_spec_hash(final_spec)
        route_descriptor = {
            "schema": ATTEMPT_ROUTE_SCHEMA,
            "work_package_id": request.work_package_id,
            "outcome_id": str(target["outcome_id"]),
            "project_scope": {
                "project_id": binding.project_id,
                "resource_id": binding.resource_id,
                "scope_generation": binding.scope_generation,
            },
            "reasoning_spec": {"ref": spec_ref, "hash": spec_hash},
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

        if existing_attempt is not None:
            if (
                str(existing_attempt["attempt_id"]) != attempt_id
                or str(existing_attempt["request_hash"]) != attempt_hash
                or str(existing_attempt["work_package_id"]) != request.work_package_id
            ):
                raise AdmissionError(
                    "controller request already owns a different WorkPackageAttempt"
                )
            task_id = str(existing_attempt["task_id"])
            conn.rollback()
        else:
            same_attempt = conn.execute(
                "SELECT * FROM work_package_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if same_attempt is not None:
                raise AdmissionError(
                    "identical WorkPackageAttempt already exists under a different controller request"
                )
            else:
                backend_ref = backend.reserve()
                task_id = make_task_id()
                normalized = normalize_reasoning_request(
                    reasoning_spec_ref=spec_ref,
                    reasoning_spec_hash=spec_hash,
                    project_id=binding.project_id,
                    resource_id=binding.resource_id,
                    scope_generation=binding.scope_generation,
                    work_package_attempt_ref=attempt_id,
                    work_package_attempt_hash=attempt_hash,
                    dependency_proof_refs=[
                        {"ref": item.ref, "hash": item.hash} for item in proof_refs
                    ],
                )
                task_request_hash = normalized_request_hash(normalized)
                task_manager.scope_store.reserve_task_attempt(
                    conn,
                    binding=binding,
                    task_id=task_id,
                    run_id=backend_ref,
                    parent_task_id="",
                )
                task_manager.store.reserve_task_in_connection(
                    conn,
                    task_id=task_id,
                    task_kind=TaskKind.REASONING.value,
                    controller_request_id=request.controller_request_id,
                    request_hash=task_request_hash,
                    backend_kind=BackendKind.SOMA_REASONING.value,
                    backend_executor=REASONING_EXECUTOR,
                    backend_ref=backend_ref,
                    backend_identity={
                        "engine": BackendKind.SOMA_REASONING.value,
                        "reasoning_spec_ref": spec_ref,
                        "reasoning_spec_hash": spec_hash,
                        "work_package_attempt_ref": attempt_id,
                        "work_package_attempt_hash": attempt_hash,
                        "project_id": binding.project_id,
                        "resource_id": binding.resource_id,
                        "scope_generation": binding.scope_generation,
                    },
                    objective_ref=final_spec.assignment_ref,
                    constraints_ref=final_spec.authority_ref,
                    workspace_kind="repository",
                    workspace_ref=effective_repo_name,
                    parent_task_id="",
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
                created = True
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()

    if task_id is None:
        raise AdmissionError("admission did not resolve a canonical Task identity")
    if _after_commit_hook is not None:
        _after_commit_hook(attempt_id, task_id)

    # Provider/backend start occurs only after the bounded reservation transaction.
    task_start = task_manager.start_reasoning_task(
        controller_request_id=request.controller_request_id,
        repo_name=request.repo_name,
        project_id=binding.project_id,
        spec=final_spec,
        work_package_attempt_ref=attempt_id,
        work_package_attempt_hash=attempt_hash,
    )
    return AdmissionResultV1(
        mission_id=request.mission_id,
        plan_revision_id=str(mission["current_plan_revision_id"]),
        work_package_id=request.work_package_id,
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        task_id=task_id,
        proof_refs=proof_refs,
        created=created,
        task_start=task_start,
    )


def admit_reasoning_batch(
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
    return tuple(
        admit_reasoning_work_package(task_manager, request) for request in ordered
    )
