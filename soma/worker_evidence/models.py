"""Pure bounded evidence-submission contracts for Soma workers.

The envelope separates producer claims from evidence/provenance identity and
from canonical Task lifecycle state. Full logs, documents, transcripts and
provider streams remain behind exact references.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import (
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
)


EVIDENCE_SUBMISSION_SCHEMA_VERSION: Final[str] = "evidence_submission.v1"
EVIDENCE_SUBMISSION_NORMAL_TARGET_BYTES: Final[int] = 12 * 1024
EVIDENCE_SUBMISSION_HARD_CEILING_BYTES: Final[int] = 32 * 1024
MAX_EXECUTIVE_SUMMARY_UTF8_BYTES: Final[int] = 1024
MAX_EVIDENCE_CLAIMS: Final[int] = 12
MAX_EVIDENCE_RECORDS: Final[int] = 24
MAX_EVIDENCE_ARTIFACTS: Final[int] = 12
MAX_EVIDENCE_UNCERTAINTIES: Final[int] = 12
MAX_EVIDENCE_BLOCKERS: Final[int] = 8
MAX_EVIDENCE_EXCERPT_CHARACTERS: Final[int] = 512
MAX_EVIDENCE_PROVENANCE_REFS: Final[int] = 64
MAX_EVIDENCE_RETRIEVAL_REFS: Final[int] = 64

ClaimClass = Literal[
    "observation",
    "inference",
    "recommendation",
    "negative_finding",
]
SubmissionDisposition = Literal["complete", "partial", "blocked", "uncertain"]


def _canonical_serialized_bytes(payload: Any) -> int:
    return len(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def _validate_utf8_bytes(value: str, field: str, maximum: int) -> str:
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{field} exceeds {maximum} UTF-8 bytes")
    return value


def _require_unique(values: list[str] | tuple[str, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must contain unique values")


class _FrozenEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceHashedReferenceV1(_FrozenEvidenceModel):
    ref: str = Field(min_length=1, max_length=2048)
    hash: str

    @model_validator(mode="after")
    def _validate_reference(self):
        validate_opaque(self.ref, "ref", max_length=2048)
        validate_sha256(self.hash, "hash")
        return self


class EvidenceWorkIdentityV1(_FrozenEvidenceModel):
    mission_id: str | None = None
    plan_revision_id: str | None = None
    work_package_id: str | None = None
    outcome_id: str | None = None
    attempt_id: str | None = None
    task_id: str = Field(min_length=1, max_length=128)
    backend_ref: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def _validate_identity(self):
        for field, value in (
            ("mission_id", self.mission_id),
            ("plan_revision_id", self.plan_revision_id),
            ("work_package_id", self.work_package_id),
            ("outcome_id", self.outcome_id),
            ("attempt_id", self.attempt_id),
        ):
            if value is not None:
                validate_kernel_id(value, field)
        validate_opaque(self.task_id, "task_id", max_length=128)
        if self.backend_ref is not None:
            validate_opaque(self.backend_ref, "backend_ref", max_length=2048)
        return self


class EvidenceAssignmentV1(_FrozenEvidenceModel):
    contract_ref: str = Field(min_length=1, max_length=2048)
    contract_hash: str

    @model_validator(mode="after")
    def _validate_assignment(self):
        validate_opaque(self.contract_ref, "contract_ref", max_length=2048)
        validate_sha256(self.contract_hash, "contract_hash")
        return self


class EvidenceProducerV1(_FrozenEvidenceModel):
    backend_kind: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=128)
    model_or_profile: str | None = Field(default=None, max_length=256)
    adapter_id: str | None = Field(default=None, max_length=256)
    native_session_ref: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def _validate_producer(self):
        validate_opaque(self.backend_kind, "backend_kind", max_length=128)
        for field, value, maximum in (
            ("provider", self.provider, 128),
            ("model_or_profile", self.model_or_profile, 256),
            ("adapter_id", self.adapter_id, 256),
            ("native_session_ref", self.native_session_ref, 2048),
        ):
            if value is not None:
                validate_opaque(value, field, max_length=maximum)
        return self


class EvidenceClaimV1(_FrozenEvidenceModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_class: ClaimClass
    subject_key: str | None = Field(default=None, max_length=256)
    statement: str = Field(min_length=1, max_length=4096)
    supports_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_RECORDS
    )
    opposes_evidence_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_RECORDS
    )
    uncertainty_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_UNCERTAINTIES
    )

    @model_validator(mode="after")
    def _validate_claim(self):
        validate_opaque(self.claim_id, "claim_id", max_length=128)
        if self.subject_key is not None:
            validate_opaque(self.subject_key, "subject_key", max_length=256)
        _require_unique(self.supports_evidence_ids, "supports_evidence_ids")
        _require_unique(self.opposes_evidence_ids, "opposes_evidence_ids")
        _require_unique(self.uncertainty_ids, "uncertainty_ids")
        if set(self.supports_evidence_ids) & set(self.opposes_evidence_ids):
            raise ValueError("one evidence ID cannot both support and oppose one claim")
        return self


class EvidenceRecordV1(_FrozenEvidenceModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    source_kind: str = Field(min_length=1, max_length=128)
    source_ref: str = Field(min_length=1, max_length=2048)
    source_hash: str | None = None
    locator: str | None = Field(default=None, max_length=2048)
    observed_at: str | None = Field(default=None, max_length=128)
    content_type: str | None = Field(default=None, max_length=256)
    excerpt: str | None = Field(
        default=None,
        max_length=MAX_EVIDENCE_EXCERPT_CHARACTERS,
    )
    fact_key: str | None = Field(default=None, max_length=256)
    fact_value: Any | None = None

    @model_validator(mode="after")
    def _validate_evidence(self):
        validate_opaque(self.evidence_id, "evidence_id", max_length=128)
        validate_opaque(self.source_kind, "source_kind", max_length=128)
        validate_opaque(self.source_ref, "source_ref", max_length=2048)
        if self.source_hash is not None:
            validate_sha256(self.source_hash, "source_hash")
        for field, value, maximum in (
            ("locator", self.locator, 2048),
            ("observed_at", self.observed_at, 128),
            ("content_type", self.content_type, 256),
            ("fact_key", self.fact_key, 256),
        ):
            if value is not None:
                validate_opaque(value, field, max_length=maximum)
        if (
            self.excerpt is not None
            and len(self.excerpt) > MAX_EVIDENCE_EXCERPT_CHARACTERS
        ):
            raise ValueError(
                f"excerpt exceeds {MAX_EVIDENCE_EXCERPT_CHARACTERS} characters"
            )
        return self


class EvidenceArtifactV1(_FrozenEvidenceModel):
    artifact_ref: str = Field(min_length=1, max_length=2048)
    artifact_hash: str
    media_type: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _validate_artifact(self):
        validate_opaque(self.artifact_ref, "artifact_ref", max_length=2048)
        validate_sha256(self.artifact_hash, "artifact_hash")
        return self


class EvidenceUncertaintyV1(_FrozenEvidenceModel):
    uncertainty_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)
    related_claim_ids: tuple[str, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_CLAIMS
    )
    required_resolution: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def _validate_uncertainty(self):
        validate_opaque(self.uncertainty_id, "uncertainty_id", max_length=128)
        validate_opaque(self.kind, "kind", max_length=128)
        _require_unique(self.related_claim_ids, "related_claim_ids")
        return self


class EvidenceBlockerV1(_FrozenEvidenceModel):
    blocker_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)
    related_dependency_ref: str | None = Field(default=None, max_length=2048)
    requested_input_ref: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def _validate_blocker(self):
        validate_opaque(self.blocker_id, "blocker_id", max_length=128)
        validate_opaque(self.kind, "kind", max_length=128)
        return self


class EvidenceUsageV1(_FrozenEvidenceModel):
    wall_time_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=12, decimal_places=6
    )


class EvidenceByteAccountingV1(_FrozenEvidenceModel):
    referenced_body_bytes: int = Field(default=0, ge=0)
    omitted_body_bytes: int = Field(default=0, ge=0)


class EvidenceSubmissionV1(_FrozenEvidenceModel):
    schema_version: Literal[EVIDENCE_SUBMISSION_SCHEMA_VERSION] = (
        EVIDENCE_SUBMISSION_SCHEMA_VERSION
    )
    submission_id: str = Field(min_length=1, max_length=128)
    work_identity: EvidenceWorkIdentityV1
    assignment: EvidenceAssignmentV1
    producer: EvidenceProducerV1
    submission_disposition: SubmissionDisposition
    executive_summary: str = Field(max_length=1024)
    claims: tuple[EvidenceClaimV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_CLAIMS
    )
    evidence: tuple[EvidenceRecordV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_RECORDS
    )
    artifacts: tuple[EvidenceArtifactV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_ARTIFACTS
    )
    uncertainties: tuple[EvidenceUncertaintyV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_UNCERTAINTIES
    )
    blockers: tuple[EvidenceBlockerV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_BLOCKERS
    )
    usage: EvidenceUsageV1 = Field(default_factory=EvidenceUsageV1)
    provenance: tuple[EvidenceHashedReferenceV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_PROVENANCE_REFS
    )
    full_evidence_retrieval: tuple[EvidenceHashedReferenceV1, ...] = Field(
        default=(), max_length=MAX_EVIDENCE_RETRIEVAL_REFS
    )
    byte_accounting: EvidenceByteAccountingV1 = Field(
        default_factory=EvidenceByteAccountingV1
    )

    @model_validator(mode="after")
    def _validate_submission(self):
        validate_opaque(self.submission_id, "submission_id", max_length=128)
        _validate_utf8_bytes(
            self.executive_summary,
            "executive_summary",
            MAX_EXECUTIVE_SUMMARY_UTF8_BYTES,
        )

        claim_ids = [claim.claim_id for claim in self.claims]
        evidence_ids = [record.evidence_id for record in self.evidence]
        uncertainty_ids = [item.uncertainty_id for item in self.uncertainties]
        blocker_ids = [item.blocker_id for item in self.blockers]
        artifact_refs = [artifact.artifact_ref for artifact in self.artifacts]
        provenance_refs = [record.ref for record in self.provenance]
        retrieval_refs = [record.ref for record in self.full_evidence_retrieval]
        _require_unique(claim_ids, "claim IDs")
        _require_unique(evidence_ids, "evidence IDs")
        _require_unique(uncertainty_ids, "uncertainty IDs")
        _require_unique(blocker_ids, "blocker IDs")
        _require_unique(artifact_refs, "artifact refs")
        _require_unique(provenance_refs, "provenance refs")
        _require_unique(retrieval_refs, "full evidence retrieval refs")

        evidence_set = set(evidence_ids)
        uncertainty_set = set(uncertainty_ids)
        claim_set = set(claim_ids)
        for claim in self.claims:
            missing_evidence = (
                set(claim.supports_evidence_ids) | set(claim.opposes_evidence_ids)
            ) - evidence_set
            if missing_evidence:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown evidence IDs: "
                    f"{sorted(missing_evidence)}"
                )
            missing_uncertainties = set(claim.uncertainty_ids) - uncertainty_set
            if missing_uncertainties:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown uncertainty IDs: "
                    f"{sorted(missing_uncertainties)}"
                )
        for uncertainty in self.uncertainties:
            missing_claims = set(uncertainty.related_claim_ids) - claim_set
            if missing_claims:
                raise ValueError(
                    f"uncertainty {uncertainty.uncertainty_id} references unknown claim IDs: "
                    f"{sorted(missing_claims)}"
                )

        try:
            serialized_bytes = _canonical_serialized_bytes(self.model_dump(mode="json"))
        except Exception as exc:
            raise ValueError("EvidenceSubmissionV1 must be JSON-serializable") from exc
        if serialized_bytes > EVIDENCE_SUBMISSION_HARD_CEILING_BYTES:
            raise ValueError(
                "EvidenceSubmissionV1 exceeds hard serialized ceiling of "
                f"{EVIDENCE_SUBMISSION_HARD_CEILING_BYTES} bytes"
            )
        return self

    @property
    def serialized_bytes(self) -> int:
        return _canonical_serialized_bytes(self.model_dump(mode="json"))

    @property
    def within_normal_target(self) -> bool:
        return self.serialized_bytes <= EVIDENCE_SUBMISSION_NORMAL_TARGET_BYTES
