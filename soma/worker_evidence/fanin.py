"""Deterministic bounded FanInV1 over provider-neutral EvidenceSubmissionV1 records.

Fan-in owns exact structure only: expected-unit coverage, immutable submission
identity, assignment-provided fact-key checks, exact structured conflicts,
missing/partial/blocked/uncertain unit reporting, bounded retrieval pointers and
aggregate accounting. It never decides which contradictory claim is true and
never accepts a substantive WorkPackage outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any, Final, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import (
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
)

from .models import EvidenceSubmissionV1


FANIN_SCHEMA_VERSION: Final[str] = "fanin.v1"
FANIN_NORMAL_TARGET_BYTES: Final[int] = 48 * 1024
FANIN_HARD_CEILING_BYTES: Final[int] = 64 * 1024
MAX_FANIN_EXPECTED_UNITS: Final[int] = 32
MAX_FANIN_SUBMISSION_SUMMARIES: Final[int] = 32
MAX_FANIN_STRUCTURED_CONFLICTS: Final[int] = 64
MAX_FANIN_UNRESOLVED_UNCERTAINTIES: Final[int] = 64
MAX_FANIN_EXACT_DUPLICATES: Final[int] = 64
MAX_FANIN_RETRIEVAL_POINTERS: Final[int] = 256
SUBMISSION_HASH_DOMAIN: Final[str] = "soma.worker_evidence.submission.v1"


class FanInValidationError(ValueError):
    """Input evidence cannot be mechanically represented by FanInV1."""


class _FrozenFanInModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FanInSubmissionSummaryV1(_FrozenFanInModel):
    unit_ref: str = Field(min_length=1, max_length=256)
    submission_id: str = Field(min_length=1, max_length=128)
    submission_ref: str = Field(min_length=1, max_length=2048)
    submission_hash: str
    task_id: str = Field(min_length=1, max_length=128)
    work_package_id: str | None = None
    disposition: str = Field(min_length=1, max_length=32)
    backend_kind: str = Field(min_length=1, max_length=128)
    assignment_ref: str = Field(min_length=1, max_length=2048)
    assignment_hash: str
    executive_summary: str = Field(default="", max_length=1024)
    claim_refs: tuple[str, ...] = Field(default=(), max_length=12)
    evidence_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    uncertainty_count: int = Field(ge=0)
    blocker_count: int = Field(ge=0)
    serialized_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_summary(self):
        validate_opaque(self.unit_ref, "unit_ref", max_length=256)
        validate_opaque(self.submission_id, "submission_id", max_length=128)
        validate_opaque(self.submission_ref, "submission_ref", max_length=2048)
        validate_sha256(self.submission_hash, "submission_hash")
        validate_opaque(self.task_id, "task_id", max_length=128)
        if self.work_package_id is not None:
            validate_kernel_id(self.work_package_id, "work_package_id")
        validate_opaque(self.backend_kind, "backend_kind", max_length=128)
        validate_opaque(self.assignment_ref, "assignment_ref", max_length=2048)
        validate_sha256(self.assignment_hash, "assignment_hash")
        return self


class FanInFactVariantV1(_FrozenFanInModel):
    fact_value_json: str = Field(min_length=1, max_length=4096)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=128)


class FanInStructuredConflictV1(_FrozenFanInModel):
    fact_key: str = Field(min_length=1, max_length=256)
    variants: tuple[FanInFactVariantV1, ...] = Field(min_length=2, max_length=32)


class FanInExactDuplicateV1(_FrozenFanInModel):
    fact_key: str = Field(min_length=1, max_length=256)
    fact_value_json: str = Field(min_length=1, max_length=4096)
    evidence_refs: tuple[str, ...] = Field(min_length=2, max_length=128)


class FanInUncertaintyRefV1(_FrozenFanInModel):
    unit_ref: str = Field(min_length=1, max_length=256)
    submission_id: str = Field(min_length=1, max_length=128)
    uncertainty_id: str = Field(min_length=1, max_length=128)


class FanInRetrievalPointerV1(_FrozenFanInModel):
    unit_ref: str = Field(min_length=1, max_length=256)
    ref: str = Field(min_length=1, max_length=2048)
    hash: str
    kind: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_pointer(self):
        validate_sha256(self.hash, "hash")
        return self


class FanInAggregateUsageV1(_FrozenFanInModel):
    wall_time_seconds: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0, max_digits=14, decimal_places=6)
    submission_bytes: int = Field(ge=0)
    referenced_body_bytes: int = Field(ge=0)
    omitted_body_bytes: int = Field(ge=0)


class FanInExactCountsV1(_FrozenFanInModel):
    expected_units: int = Field(ge=0)
    collected_units: int = Field(ge=0)
    missing_units: int = Field(ge=0)
    complete_units: int = Field(ge=0)
    partial_units: int = Field(ge=0)
    blocked_units: int = Field(ge=0)
    uncertain_units: int = Field(ge=0)
    submissions: int = Field(ge=0)
    claims: int = Field(ge=0)
    evidence_records: int = Field(ge=0)
    artifacts: int = Field(ge=0)
    structured_conflicts: int = Field(ge=0)
    exact_duplicates: int = Field(ge=0)
    unresolved_uncertainties: int = Field(ge=0)
    blockers: int = Field(ge=0)
    retrieval_pointers: int = Field(ge=0)


class FanInV1(_FrozenFanInModel):
    schema_version: str = FANIN_SCHEMA_VERSION
    mission_id: str | None = None
    plan_revision_id: str | None = None
    synthesis_work_package_id: str | None = None
    expected_unit_refs: tuple[str, ...] = Field(
        min_length=1, max_length=MAX_FANIN_EXPECTED_UNITS
    )
    collected_unit_refs: tuple[str, ...] = Field(
        default=(), max_length=MAX_FANIN_EXPECTED_UNITS
    )
    missing_unit_refs: tuple[str, ...] = Field(
        default=(), max_length=MAX_FANIN_EXPECTED_UNITS
    )
    partial_unit_refs: tuple[str, ...] = Field(
        default=(), max_length=MAX_FANIN_EXPECTED_UNITS
    )
    blocked_unit_refs: tuple[str, ...] = Field(
        default=(), max_length=MAX_FANIN_EXPECTED_UNITS
    )
    uncertain_unit_refs: tuple[str, ...] = Field(
        default=(), max_length=MAX_FANIN_EXPECTED_UNITS
    )
    submission_summaries: tuple[FanInSubmissionSummaryV1, ...] = Field(
        default=(), max_length=MAX_FANIN_SUBMISSION_SUMMARIES
    )
    structured_conflicts: tuple[FanInStructuredConflictV1, ...] = Field(
        default=(), max_length=MAX_FANIN_STRUCTURED_CONFLICTS
    )
    exact_duplicates: tuple[FanInExactDuplicateV1, ...] = Field(
        default=(), max_length=MAX_FANIN_EXACT_DUPLICATES
    )
    unresolved_uncertainties: tuple[FanInUncertaintyRefV1, ...] = Field(
        default=(), max_length=MAX_FANIN_UNRESOLVED_UNCERTAINTIES
    )
    evidence_retrievals: tuple[FanInRetrievalPointerV1, ...] = Field(
        default=(), max_length=MAX_FANIN_RETRIEVAL_POINTERS
    )
    aggregate_usage: FanInAggregateUsageV1
    exact_counts: FanInExactCountsV1
    truncated: bool = False
    has_more: bool = False
    response_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_fanin(self):
        if self.schema_version != FANIN_SCHEMA_VERSION:
            raise ValueError("unsupported FanInV1 schema version")
        if self.mission_id is not None:
            validate_kernel_id(self.mission_id, "mission_id")
        if self.plan_revision_id is not None:
            validate_kernel_id(self.plan_revision_id, "plan_revision_id")
        if self.synthesis_work_package_id is not None:
            validate_kernel_id(self.synthesis_work_package_id, "work_package_id")

        for field_name in (
            "expected_unit_refs",
            "collected_unit_refs",
            "missing_unit_refs",
            "partial_unit_refs",
            "blocked_unit_refs",
            "uncertain_unit_refs",
        ):
            values = tuple(getattr(self, field_name))
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
            for value in values:
                validate_opaque(value, field_name, max_length=256)

        expected = set(self.expected_unit_refs)
        collected = set(self.collected_unit_refs)
        missing = set(self.missing_unit_refs)
        if collected & missing:
            raise ValueError("collected and missing unit sets must not overlap")
        if collected | missing != expected:
            raise ValueError(
                "collected + missing units must exactly cover expected units"
            )
        for field_name in (
            "partial_unit_refs",
            "blocked_unit_refs",
            "uncertain_unit_refs",
        ):
            if not set(getattr(self, field_name)).issubset(collected):
                raise ValueError(f"{field_name} must be a subset of collected units")

        summary_units = [item.unit_ref for item in self.submission_summaries]
        if len(summary_units) != len(set(summary_units)):
            raise ValueError("submission summaries must contain one row per unit")
        if set(summary_units) != collected:
            raise ValueError(
                "every collected unit must have exactly one submission summary"
            )
        if self.truncated and not self.has_more:
            raise ValueError("truncated FanInV1 must set has_more")
        return self

    @property
    def serialized_bytes(self) -> int:
        return _serialized_bytes(self.model_dump(mode="json"))

    @property
    def within_normal_target(self) -> bool:
        return self.serialized_bytes <= FANIN_NORMAL_TARGET_BYTES


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _serialized_bytes(value: Any) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def evidence_submission_hash(submission: EvidenceSubmissionV1) -> str:
    payload = submission.model_dump(mode="json")
    return hashlib.sha256(
        f"{SUBMISSION_HASH_DOMAIN}\0{_canonical_json(payload)}".encode("utf-8")
    ).hexdigest()


def _fact_value_json(value: Any) -> str:
    encoded = _canonical_json(value)
    if len(encoded) > 4096:
        raise FanInValidationError("structured fact value exceeds compact FanIn limit")
    return encoded


def _summary(
    unit_ref: str, submission: EvidenceSubmissionV1
) -> FanInSubmissionSummaryV1:
    work_package_id = submission.work_identity.work_package_id
    return FanInSubmissionSummaryV1(
        unit_ref=unit_ref,
        submission_id=submission.submission_id,
        submission_ref=f"evidence-submission:{submission.submission_id}",
        submission_hash=evidence_submission_hash(submission),
        task_id=submission.work_identity.task_id,
        work_package_id=work_package_id,
        disposition=submission.submission_disposition,
        backend_kind=submission.producer.backend_kind,
        assignment_ref=submission.assignment.contract_ref,
        assignment_hash=submission.assignment.contract_hash,
        executive_summary=submission.executive_summary,
        claim_refs=tuple(sorted(claim.claim_id for claim in submission.claims)),
        evidence_count=len(submission.evidence),
        artifact_count=len(submission.artifacts),
        uncertainty_count=len(submission.uncertainties),
        blocker_count=len(submission.blockers),
        serialized_bytes=submission.serialized_bytes,
    )


def _pointer_key(item: FanInRetrievalPointerV1) -> tuple[str, str, str, str]:
    return (item.unit_ref, item.ref, item.hash, item.kind)


def _response_bytes_fixed_point(fanin: FanInV1) -> FanInV1:
    current = fanin
    for _ in range(8):
        measured = _serialized_bytes(current.model_dump(mode="json"))
        if measured == current.response_bytes:
            return current
        current = current.model_copy(update={"response_bytes": measured})
    return current


def _compact_to_budget(fanin: FanInV1) -> FanInV1:
    current = _response_bytes_fixed_point(fanin)
    if current.response_bytes <= FANIN_NORMAL_TARGET_BYTES:
        return current

    # First remove repeated prose while preserving every unit/hash/count/fact identity.
    summaries = tuple(
        item.model_copy(update={"executive_summary": ""})
        for item in current.submission_summaries
    )
    current = _response_bytes_fixed_point(
        current.model_copy(
            update={
                "submission_summaries": summaries,
                "truncated": True,
                "has_more": True,
            }
        )
    )
    if current.response_bytes <= FANIN_HARD_CEILING_BYTES:
        return current

    # Then trim low-priority claim lists and excess retrieval shortcuts. The exact
    # submission refs/hashes, missing units, conflict counts and uncertainty counts remain.
    summaries = tuple(
        item.model_copy(update={"claim_refs": item.claim_refs[:4]})
        for item in current.submission_summaries
    )
    current = _response_bytes_fixed_point(
        current.model_copy(
            update={
                "submission_summaries": summaries,
                "evidence_retrievals": current.evidence_retrievals[:64],
                "truncated": True,
                "has_more": True,
            }
        )
    )
    if current.response_bytes > FANIN_HARD_CEILING_BYTES:
        raise FanInValidationError(
            f"FanInV1 exceeds hard serialized ceiling of {FANIN_HARD_CEILING_BYTES} bytes"
        )
    return current


def synthesize_fanin(
    *,
    expected_unit_refs: Sequence[str],
    submissions: Mapping[str, EvidenceSubmissionV1],
    assignment_fact_keys: Mapping[str, Sequence[str]] | None = None,
    mission_id: str | None = None,
    plan_revision_id: str | None = None,
    synthesis_work_package_id: str | None = None,
) -> FanInV1:
    """Build one deterministic compact fan-in from exact bounded submissions."""

    expected = tuple(sorted(str(value) for value in expected_unit_refs))
    if not expected or len(expected) > MAX_FANIN_EXPECTED_UNITS:
        raise FanInValidationError(
            f"expected_unit_refs must contain 1..{MAX_FANIN_EXPECTED_UNITS} units"
        )
    if len(expected) != len(set(expected)):
        raise FanInValidationError("expected_unit_refs must be unique")
    unexpected = sorted(set(submissions) - set(expected))
    if unexpected:
        raise FanInValidationError(
            f"submission supplied for unexpected unit: {unexpected}"
        )

    allowed_keys = {
        str(unit): frozenset(str(key) for key in keys)
        for unit, keys in (assignment_fact_keys or {}).items()
    }
    unknown_key_units = sorted(set(allowed_keys) - set(expected))
    if unknown_key_units:
        raise FanInValidationError(
            f"assignment fact-key policy supplied for unexpected unit: {unknown_key_units}"
        )

    collected = tuple(sorted(str(unit) for unit in submissions))
    missing = tuple(sorted(set(expected) - set(collected)))
    summaries: list[FanInSubmissionSummaryV1] = []
    partial: list[str] = []
    blocked: list[str] = []
    uncertain: list[str] = []
    uncertainty_refs: list[FanInUncertaintyRefV1] = []
    retrievals: dict[tuple[str, str, str, str], FanInRetrievalPointerV1] = {}
    facts: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    total_wall = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = Decimal("0")
    total_submission_bytes = 0
    total_referenced_body_bytes = 0
    total_omitted_body_bytes = 0
    total_claims = 0
    total_evidence = 0
    total_artifacts = 0
    total_uncertainties = 0
    total_blockers = 0

    for unit_ref in collected:
        submission = submissions[unit_ref]
        if not isinstance(submission, EvidenceSubmissionV1):
            submission = EvidenceSubmissionV1.model_validate(submission)
        summary = _summary(unit_ref, submission)
        summaries.append(summary)
        disposition = submission.submission_disposition
        if disposition == "partial":
            partial.append(unit_ref)
        elif disposition == "blocked":
            blocked.append(unit_ref)
        elif disposition == "uncertain":
            uncertain.append(unit_ref)

        total_wall += submission.usage.wall_time_seconds
        total_input_tokens += submission.usage.input_tokens
        total_output_tokens += submission.usage.output_tokens
        total_cost += submission.usage.cost_usd
        total_submission_bytes += submission.serialized_bytes
        total_referenced_body_bytes += submission.byte_accounting.referenced_body_bytes
        total_omitted_body_bytes += submission.byte_accounting.omitted_body_bytes
        total_claims += len(submission.claims)
        total_evidence += len(submission.evidence)
        total_artifacts += len(submission.artifacts)
        total_uncertainties += len(submission.uncertainties)
        total_blockers += len(submission.blockers)

        submission_pointer = FanInRetrievalPointerV1(
            unit_ref=unit_ref,
            ref=summary.submission_ref,
            hash=summary.submission_hash,
            kind="submission",
        )
        retrievals[_pointer_key(submission_pointer)] = submission_pointer

        for record in submission.evidence:
            if record.source_hash is None:
                raise FanInValidationError(
                    f"evidence {record.evidence_id!r} in unit {unit_ref!r} lacks exact source_hash"
                )
            pointer = FanInRetrievalPointerV1(
                unit_ref=unit_ref,
                ref=record.source_ref,
                hash=record.source_hash,
                kind="evidence",
            )
            retrievals[_pointer_key(pointer)] = pointer
            if record.fact_key is not None:
                if unit_ref not in allowed_keys:
                    raise FanInValidationError(
                        f"unit {unit_ref!r} emitted fact_key without assignment-provided key policy"
                    )
                if record.fact_key not in allowed_keys[unit_ref]:
                    raise FanInValidationError(
                        f"fact_key {record.fact_key!r} is not assignment-provided for unit {unit_ref!r}"
                    )
                fact_ref = f"{submission.submission_id}:{record.evidence_id}"
                facts[record.fact_key][_fact_value_json(record.fact_value)].append(
                    fact_ref
                )

        for artifact in submission.artifacts:
            pointer = FanInRetrievalPointerV1(
                unit_ref=unit_ref,
                ref=artifact.artifact_ref,
                hash=artifact.artifact_hash,
                kind="artifact",
            )
            retrievals[_pointer_key(pointer)] = pointer
        for record in submission.provenance:
            pointer = FanInRetrievalPointerV1(
                unit_ref=unit_ref,
                ref=record.ref,
                hash=record.hash,
                kind="provenance",
            )
            retrievals[_pointer_key(pointer)] = pointer
        for record in submission.full_evidence_retrieval:
            pointer = FanInRetrievalPointerV1(
                unit_ref=unit_ref,
                ref=record.ref,
                hash=record.hash,
                kind="full_evidence",
            )
            retrievals[_pointer_key(pointer)] = pointer
        for item in submission.uncertainties:
            uncertainty_refs.append(
                FanInUncertaintyRefV1(
                    unit_ref=unit_ref,
                    submission_id=submission.submission_id,
                    uncertainty_id=item.uncertainty_id,
                )
            )

    conflicts_all: list[FanInStructuredConflictV1] = []
    duplicates_all: list[FanInExactDuplicateV1] = []
    for fact_key in sorted(facts):
        values = facts[fact_key]
        variants = tuple(
            FanInFactVariantV1(
                fact_value_json=value,
                evidence_refs=tuple(sorted(refs)),
            )
            for value, refs in sorted(values.items())
        )
        if len(variants) > 1:
            conflicts_all.append(
                FanInStructuredConflictV1(fact_key=fact_key, variants=variants)
            )
        for value, refs in sorted(values.items()):
            if len(refs) > 1:
                duplicates_all.append(
                    FanInExactDuplicateV1(
                        fact_key=fact_key,
                        fact_value_json=value,
                        evidence_refs=tuple(sorted(refs)),
                    )
                )

    uncertainty_refs.sort(
        key=lambda item: (item.unit_ref, item.submission_id, item.uncertainty_id)
    )
    retrieval_list = sorted(retrievals.values(), key=_pointer_key)
    overflow = (
        len(conflicts_all) > MAX_FANIN_STRUCTURED_CONFLICTS
        or len(duplicates_all) > MAX_FANIN_EXACT_DUPLICATES
        or len(uncertainty_refs) > MAX_FANIN_UNRESOLVED_UNCERTAINTIES
        or len(retrieval_list) > MAX_FANIN_RETRIEVAL_POINTERS
    )

    exact_counts = FanInExactCountsV1(
        expected_units=len(expected),
        collected_units=len(collected),
        missing_units=len(missing),
        complete_units=sum(
            1
            for submission in submissions.values()
            if submission.submission_disposition == "complete"
        ),
        partial_units=len(partial),
        blocked_units=len(blocked),
        uncertain_units=len(uncertain),
        submissions=len(collected),
        claims=total_claims,
        evidence_records=total_evidence,
        artifacts=total_artifacts,
        structured_conflicts=len(conflicts_all),
        exact_duplicates=len(duplicates_all),
        unresolved_uncertainties=total_uncertainties,
        blockers=total_blockers,
        retrieval_pointers=len(retrieval_list),
    )
    aggregate_usage = FanInAggregateUsageV1(
        wall_time_seconds=total_wall,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_usd=total_cost,
        submission_bytes=total_submission_bytes,
        referenced_body_bytes=total_referenced_body_bytes,
        omitted_body_bytes=total_omitted_body_bytes,
    )
    has_external_detail = total_omitted_body_bytes > 0 or any(
        submission.full_evidence_retrieval for submission in submissions.values()
    )
    fanin = FanInV1(
        mission_id=mission_id,
        plan_revision_id=plan_revision_id,
        synthesis_work_package_id=synthesis_work_package_id,
        expected_unit_refs=expected,
        collected_unit_refs=collected,
        missing_unit_refs=missing,
        partial_unit_refs=tuple(sorted(partial)),
        blocked_unit_refs=tuple(sorted(blocked)),
        uncertain_unit_refs=tuple(sorted(uncertain)),
        submission_summaries=tuple(sorted(summaries, key=lambda item: item.unit_ref)),
        structured_conflicts=tuple(conflicts_all[:MAX_FANIN_STRUCTURED_CONFLICTS]),
        exact_duplicates=tuple(duplicates_all[:MAX_FANIN_EXACT_DUPLICATES]),
        unresolved_uncertainties=tuple(
            uncertainty_refs[:MAX_FANIN_UNRESOLVED_UNCERTAINTIES]
        ),
        evidence_retrievals=tuple(retrieval_list[:MAX_FANIN_RETRIEVAL_POINTERS]),
        aggregate_usage=aggregate_usage,
        exact_counts=exact_counts,
        truncated=overflow,
        has_more=overflow or has_external_detail,
        response_bytes=0,
    )
    return _compact_to_budget(fanin)
