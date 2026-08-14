"""Mechanical Company Kernel dependency evaluation and immutable proof persistence.

This module performs only deterministic predicate checks for the four frozen
PlanGraph dependency requirements. It never performs semantic evidence
adjudication, scheduling, provider selection, or Task lifecycle inference.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from typing import Final, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .graph_models import (
    AcceptedOutcomeSatisfactionV1,
    DependencyRequirement,
    DependencySatisfactionProofV1,
    EvidenceAvailableSatisfactionV1,
    PublishedSuccessSatisfactionV1,
    SettledSatisfactionV1,
)
from .models import (
    AcceptanceCommit,
    canonical_json,
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
)
from .store import CompanyKernelStore


ACCEPTANCE_COMMIT_HASH_DOMAIN: Final[str] = "soma.company_kernel.acceptance_commit.v1"
ACCEPTANCE_COMMIT_HASH_DOMAIN_V2: Final[str] = "soma.company_kernel.acceptance_commit.v2"
ATTEMPT_SET_HASH_DOMAIN: Final[str] = "soma.company_kernel.attempt_set.v1"
SETTLEMENT_HASH_DOMAIN: Final[str] = "soma.company_kernel.settlement.v1"
DEPENDENCY_PROOF_RECORD_PREFIX: Final[str] = "depproof"

_TERMINAL_TASK_STATES: Final[frozenset[str]] = frozenset(
    {"completed", "failed", "cancelled"}
)


class DependencyProofEvaluationError(ValueError):
    """Current deterministic facts do not satisfy the requested dependency."""


class DependencyProofPersistenceError(ValueError):
    """A proof cannot be durably bound to the exact dependency edge identity."""


class _FrozenDependencyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DependencyEdgeContextV1(_FrozenDependencyModel):
    mission_id: str
    plan_revision_id: str
    edge_id: str = Field(min_length=1, max_length=128)
    edge_hash: str
    requirement: DependencyRequirement
    upstream_work_package_id: str
    upstream_outcome_id: str
    downstream_work_package_id: str
    evidence_selector_ref: str | None = Field(default=None, max_length=2048)
    evidence_selector_hash: str | None = None
    observed_kernel_state_version: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_context(self):
        validate_kernel_id(self.mission_id, "mission_id")
        validate_kernel_id(self.plan_revision_id, "plan_revision_id")
        validate_opaque(self.edge_id, "edge_id", max_length=128)
        validate_sha256(self.edge_hash, "edge_hash")
        validate_kernel_id(self.upstream_work_package_id, "work_package_id")
        validate_kernel_id(self.upstream_outcome_id, "outcome_id")
        validate_kernel_id(self.downstream_work_package_id, "work_package_id")
        if self.requirement == "evidence_available":
            if (
                self.evidence_selector_ref is None
                or self.evidence_selector_hash is None
            ):
                raise ValueError(
                    "evidence_available context requires selector ref/hash"
                )
            validate_opaque(
                self.evidence_selector_ref,
                "evidence_selector_ref",
                max_length=2048,
            )
            validate_sha256(self.evidence_selector_hash, "evidence_selector_hash")
        elif (
            self.evidence_selector_ref is not None
            or self.evidence_selector_hash is not None
        ):
            raise ValueError("only evidence_available context may carry a selector")
        return self


class PublishedSuccessCandidateV1(_FrozenDependencyModel):
    work_package_id: str
    outcome_id: str
    attempt_id: str
    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    result_published_hash: str
    public_result_source_sha256: str

    @model_validator(mode="after")
    def _validate_candidate(self):
        validate_kernel_id(self.work_package_id, "work_package_id")
        validate_kernel_id(self.outcome_id, "outcome_id")
        validate_kernel_id(self.attempt_id, "attempt_id")
        validate_opaque(self.task_id, "task_id", max_length=128)
        validate_opaque(self.run_id, "run_id", max_length=128)
        validate_sha256(self.result_published_hash, "result_published_hash")
        validate_sha256(
            self.public_result_source_sha256,
            "public_result_source_sha256",
        )
        return self


class EvidenceAvailableCandidateV1(_FrozenDependencyModel):
    selector_ref: str = Field(min_length=1, max_length=2048)
    selector_hash: str
    evidence_ref: str = Field(min_length=1, max_length=2048)
    evidence_hash: str

    @model_validator(mode="after")
    def _validate_candidate(self):
        validate_opaque(self.selector_ref, "selector_ref", max_length=2048)
        validate_sha256(self.selector_hash, "selector_hash")
        validate_opaque(self.evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(self.evidence_hash, "evidence_hash")
        return self


class SettledAttemptFactV1(_FrozenDependencyModel):
    attempt_id: str
    task_id: str = Field(min_length=1, max_length=128)
    supersedes_attempt_id: str | None = None
    task_state: Literal[
        "accepted",
        "queued",
        "running",
        "awaiting_controller",
        "paused",
        "cancellation_pending",
        "recovery_pending",
        "completed",
        "failed",
        "cancelled",
        "uncertain",
    ]
    containment_evidence_ref: str | None = Field(default=None, max_length=2048)
    containment_evidence_hash: str | None = None

    @model_validator(mode="after")
    def _validate_fact(self):
        validate_kernel_id(self.attempt_id, "attempt_id")
        validate_opaque(self.task_id, "task_id", max_length=128)
        if self.supersedes_attempt_id is not None:
            validate_kernel_id(self.supersedes_attempt_id, "attempt_id")
            if self.supersedes_attempt_id == self.attempt_id:
                raise ValueError("an attempt cannot supersede itself")
        if bool(self.containment_evidence_ref) != bool(self.containment_evidence_hash):
            raise ValueError("containment evidence ref/hash must appear together")
        if self.containment_evidence_ref is not None:
            validate_opaque(
                self.containment_evidence_ref,
                "containment_evidence_ref",
                max_length=2048,
            )
            validate_sha256(
                self.containment_evidence_hash or "",
                "containment_evidence_hash",
            )
        return self

    def stable_payload(self) -> dict[str, str | None]:
        return {
            "attempt_id": self.attempt_id,
            "task_id": self.task_id,
            "supersedes_attempt_id": self.supersedes_attempt_id,
            "task_state": self.task_state,
            "containment_evidence_ref": self.containment_evidence_ref,
            "containment_evidence_hash": self.containment_evidence_hash,
        }


class PersistedDependencyProofV1(_FrozenDependencyModel):
    proof_id: str = Field(min_length=1, max_length=128)
    created: bool
    proof: DependencySatisfactionProofV1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_hash(domain: str, payload) -> str:
    return sha256(f"{domain}\0{canonical_json(payload)}".encode("utf-8")).hexdigest()


def _require_requirement(context: DependencyEdgeContextV1, expected: str) -> None:
    if context.requirement != expected:
        raise DependencyProofEvaluationError(
            f"dependency requirement {context.requirement!r} does not match evaluator {expected!r}"
        )


def _proof(
    context: DependencyEdgeContextV1,
    satisfaction,
    *,
    observed_at: str | None,
) -> DependencySatisfactionProofV1:
    return DependencySatisfactionProofV1(
        edge_id=context.edge_id,
        edge_hash=context.edge_hash,
        requirement=context.requirement,
        upstream_work_package_id=context.upstream_work_package_id,
        upstream_outcome_id=context.upstream_outcome_id,
        downstream_work_package_id=context.downstream_work_package_id,
        satisfaction=satisfaction,
        observed_kernel_state_version=context.observed_kernel_state_version,
        observed_at=observed_at or _utc_now(),
    )


def _acceptance_commit_hash(commit: AcceptanceCommit) -> str:
    if commit.backend_kind == "soma_durable_run":
        # Preserve the exact v1 content-hash contract for migrated and new
        # durable-Run acceptances. Provider-neutral v4 added backend_kind/ref to
        # the record, but changing this derived hash would invalidate immutable
        # accepted_outcome proofs that already cite the historical v1 digest.
        legacy_payload = {
            "acceptance_commit_id": commit.acceptance_commit_id,
            "company_id": commit.company_id,
            "mission_id": commit.mission_id,
            "work_package_id": commit.work_package_id,
            "outcome_id": commit.outcome_id,
            "attempt_id": commit.attempt_id,
            "task_id": commit.task_id,
            "run_id": commit.run_id,
            "result_published_hash": commit.result_published_hash,
            "public_result_source_sha256": commit.public_result_source_sha256,
            "acceptance_authority_ref": commit.acceptance_authority_ref,
            "acceptance_basis_ref": commit.acceptance_basis_ref,
            "acceptance_basis_hash": commit.acceptance_basis_hash,
            "controller_request_id": commit.controller_request_id,
            "request_hash": commit.request_hash,
            "accepted_at": commit.accepted_at,
        }
        return _domain_hash(ACCEPTANCE_COMMIT_HASH_DOMAIN, legacy_payload)
    return _domain_hash(
        ACCEPTANCE_COMMIT_HASH_DOMAIN_V2,
        commit.model_dump(mode="json"),
    )


def evaluate_accepted_outcome(
    context: DependencyEdgeContextV1,
    acceptance: AcceptanceCommit,
    *,
    observed_at: str | None = None,
) -> DependencySatisfactionProofV1:
    _require_requirement(context, "accepted_outcome")
    if (
        acceptance.mission_id != context.mission_id
        or acceptance.work_package_id != context.upstream_work_package_id
        or acceptance.outcome_id != context.upstream_outcome_id
    ):
        raise DependencyProofEvaluationError(
            "AcceptanceCommit does not match the exact upstream outcome"
        )
    return _proof(
        context,
        AcceptedOutcomeSatisfactionV1(
            acceptance_commit_id=acceptance.acceptance_commit_id,
            acceptance_commit_hash=_acceptance_commit_hash(acceptance),
        ),
        observed_at=observed_at,
    )


def evaluate_published_success(
    context: DependencyEdgeContextV1,
    candidate: PublishedSuccessCandidateV1,
    *,
    observed_at: str | None = None,
) -> DependencySatisfactionProofV1:
    _require_requirement(context, "published_success")
    if (
        candidate.work_package_id != context.upstream_work_package_id
        or candidate.outcome_id != context.upstream_outcome_id
    ):
        raise DependencyProofEvaluationError(
            "published_success candidate does not match the exact upstream outcome"
        )
    return _proof(
        context,
        PublishedSuccessSatisfactionV1(
            attempt_id=candidate.attempt_id,
            task_id=candidate.task_id,
            run_id=candidate.run_id,
            result_published_hash=candidate.result_published_hash,
            public_result_source_sha256=candidate.public_result_source_sha256,
        ),
        observed_at=observed_at,
    )


def evaluate_evidence_available(
    context: DependencyEdgeContextV1,
    candidate: EvidenceAvailableCandidateV1,
    *,
    observed_at: str | None = None,
) -> DependencySatisfactionProofV1:
    _require_requirement(context, "evidence_available")
    if (
        context.evidence_selector_ref is None
        or context.evidence_selector_hash is None
        or candidate.selector_ref != context.evidence_selector_ref
        or candidate.selector_hash != context.evidence_selector_hash
    ):
        raise DependencyProofEvaluationError(
            "evidence candidate does not match the exact dependency selector"
        )
    return _proof(
        context,
        EvidenceAvailableSatisfactionV1(
            evidence_ref=candidate.evidence_ref,
            evidence_hash=candidate.evidence_hash,
            evidence_selector_hash=candidate.selector_hash,
        ),
        observed_at=observed_at,
    )


def _attempt_set_material(
    attempts: Sequence[SettledAttemptFactV1],
) -> tuple[list[dict[str, str | None]], str | None]:
    if not attempts:
        raise DependencyProofEvaluationError(
            "settled requires a non-empty known attempt set"
        )
    ordered = sorted(attempts, key=lambda item: item.attempt_id)
    ids = [item.attempt_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise DependencyProofEvaluationError(
            "settled attempt set contains duplicate attempt IDs"
        )
    superseded = {
        item.supersedes_attempt_id for item in ordered if item.supersedes_attempt_id
    }
    unknown_superseded = superseded - set(ids)
    if unknown_superseded:
        raise DependencyProofEvaluationError(
            "settled attempt set references an unknown superseded attempt"
        )
    heads = [item.attempt_id for item in ordered if item.attempt_id not in superseded]
    if len(heads) != 1:
        raise DependencyProofEvaluationError(
            "settled attempt set must have exactly one known head attempt"
        )
    return [item.stable_payload() for item in ordered], heads[0]


def evaluate_settled(
    context: DependencyEdgeContextV1,
    attempts: Sequence[SettledAttemptFactV1],
    *,
    observed_at: str | None = None,
) -> DependencySatisfactionProofV1:
    _require_requirement(context, "settled")
    material, head_attempt_id = _attempt_set_material(attempts)
    ordered = sorted(attempts, key=lambda item: item.attempt_id)
    for item in ordered:
        if (
            item.task_state not in _TERMINAL_TASK_STATES
            and not item.containment_evidence_ref
        ):
            raise DependencyProofEvaluationError(
                f"known attempt {item.attempt_id} is not terminal and has no containment evidence"
            )
    attempt_set_hash = _domain_hash(ATTEMPT_SET_HASH_DOMAIN, material)
    if any(item.task_state == "uncertain" for item in ordered):
        settlement_class = "uncertain_contained"
    elif any(item.task_state not in _TERMINAL_TASK_STATES for item in ordered):
        settlement_class = "contained"
    elif all(item.task_state == "cancelled" for item in ordered):
        settlement_class = "cancelled"
    else:
        settlement_class = "terminal"
    settlement_payload = {
        "attempt_set_hash": attempt_set_hash,
        "head_attempt_id": head_attempt_id,
        "settlement_class": settlement_class,
        "attempts": material,
    }
    settlement_hash = _domain_hash(SETTLEMENT_HASH_DOMAIN, settlement_payload)
    return _proof(
        context,
        SettledSatisfactionV1(
            attempt_set_hash=attempt_set_hash,
            head_attempt_id=head_attempt_id,
            settlement_ref=f"attempt-set:{attempt_set_hash}",
            settlement_hash=settlement_hash,
            settlement_class=settlement_class,
        ),
        observed_at=observed_at,
    )


def proof_id_for(proof_hash: str) -> str:
    validate_sha256(proof_hash, "proof_hash")
    return f"{DEPENDENCY_PROOF_RECORD_PREFIX}_{proof_hash[:24]}"


def _proof_from_row(row: sqlite3.Row) -> DependencySatisfactionProofV1:
    satisfaction = json.loads(str(row["satisfaction_json"]))
    return DependencySatisfactionProofV1(
        edge_id=str(row["edge_id"]),
        edge_hash=str(row["edge_hash"]),
        requirement=str(row["requirement"]),
        upstream_work_package_id=str(row["upstream_work_package_id"]),
        upstream_outcome_id=str(row["upstream_outcome_id"]),
        downstream_work_package_id=str(row["downstream_work_package_id"]),
        satisfaction=satisfaction,
        observed_kernel_state_version=int(row["observed_kernel_state_version"]),
        observed_at=str(row["observed_at"]),
        proof_hash=str(row["proof_hash"]),
    )


def _verify_proof_context(
    context: DependencyEdgeContextV1,
    proof: DependencySatisfactionProofV1,
) -> None:
    if (
        proof.edge_id != context.edge_id
        or proof.edge_hash != context.edge_hash
        or proof.requirement != context.requirement
        or proof.upstream_work_package_id != context.upstream_work_package_id
        or proof.upstream_outcome_id != context.upstream_outcome_id
        or proof.downstream_work_package_id != context.downstream_work_package_id
    ):
        raise DependencyProofPersistenceError(
            "proof envelope does not match exact dependency edge context"
        )


def persist_dependency_proof_in_connection(
    conn: sqlite3.Connection,
    *,
    context: DependencyEdgeContextV1,
    proof: DependencySatisfactionProofV1,
    created_at: str | None = None,
) -> PersistedDependencyProofV1:
    """Persist one immutable proof inside an already-open Company Kernel transaction."""

    _verify_proof_context(context, proof)
    proof_id = proof_id_for(proof.proof_hash)
    satisfaction_json = canonical_json(proof.satisfaction.model_dump(mode="json"))
    edge = conn.execute(
        "SELECT * FROM work_package_dependencies "
        "WHERE edge_id = ? AND mission_id = ? AND plan_revision_id = ?",
        (context.edge_id, context.mission_id, context.plan_revision_id),
    ).fetchone()
    if edge is None:
        raise DependencyProofPersistenceError("dependency edge does not exist")
    durable = (
        str(edge["edge_hash"]),
        str(edge["requirement"]),
        str(edge["upstream_work_package_id"]),
        str(edge["downstream_work_package_id"]),
        str(edge["evidence_selector_ref"] or "") or None,
        str(edge["evidence_selector_hash"] or "") or None,
    )
    submitted = (
        context.edge_hash,
        context.requirement,
        context.upstream_work_package_id,
        context.downstream_work_package_id,
        context.evidence_selector_ref,
        context.evidence_selector_hash,
    )
    if durable != submitted:
        raise DependencyProofPersistenceError(
            "dependency edge durable identity differs from proof context"
        )
    existing = conn.execute(
        "SELECT * FROM dependency_satisfaction_proofs WHERE proof_id = ?",
        (proof_id,),
    ).fetchone()
    if existing is not None:
        if (
            str(existing["proof_hash"]) != proof.proof_hash
            or str(existing["satisfaction_json"]) != satisfaction_json
        ):
            raise DependencyProofPersistenceError(
                "proof identity already exists with different immutable material"
            )
        return PersistedDependencyProofV1(
            proof_id=proof_id,
            created=False,
            proof=_proof_from_row(existing),
        )
    conn.execute(
        "INSERT INTO dependency_satisfaction_proofs("
        "proof_id, proof_hash, mission_id, plan_revision_id, edge_id, edge_hash, "
        "requirement, upstream_work_package_id, upstream_outcome_id, "
        "downstream_work_package_id, satisfaction_json, observed_kernel_state_version, "
        "observed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            proof_id,
            proof.proof_hash,
            context.mission_id,
            context.plan_revision_id,
            context.edge_id,
            context.edge_hash,
            context.requirement,
            context.upstream_work_package_id,
            context.upstream_outcome_id,
            context.downstream_work_package_id,
            satisfaction_json,
            proof.observed_kernel_state_version,
            proof.observed_at,
            created_at or _utc_now(),
        ),
    )
    return PersistedDependencyProofV1(proof_id=proof_id, created=True, proof=proof)


def persist_dependency_proof(
    store: CompanyKernelStore,
    *,
    context: DependencyEdgeContextV1,
    proof: DependencySatisfactionProofV1,
    created_at: str | None = None,
) -> PersistedDependencyProofV1:
    with store.transaction() as conn:
        return persist_dependency_proof_in_connection(
            conn,
            context=context,
            proof=proof,
            created_at=created_at,
        )
