from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ReviewState(StrEnum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    STRONGLY_SUPPORTED = "strongly_supported"
    CHALLENGED = "challenged"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"
    REPLICATED = "replicated"
    FAILED_REPLICATION = "failed_replication"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class EvidenceRole(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    QUALIFIES = "qualifies"
    CONTEXT = "context"
    REPLICATES = "replicates"
    FAILS_TO_REPLICATE = "fails_to_replicate"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    STORED = "stored"
    UPLOADED = "uploaded"
    PARSING = "parsing"
    INDEXED = "indexed"
    FAILED = "failed"
    ARCHIVED = "archived"
    RETRY = "retry"


class QuestionStatus(StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class CandidateStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    UNDER_REVIEW = "under_review"
    SUPERSEDED = "superseded"


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"


class ResearchModel(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)


class SourceDraft(ResearchModel):
    title: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(min_length=1, max_length=128)
    canonical_uri: str = Field(min_length=1, max_length=4096)
    authors: list[str] = Field(default_factory=list)
    published_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceVersionDraft(ResearchModel):
    source_id: str = Field(min_length=1)
    archive_sha256: str
    archive_relative_path: str = Field(min_length=1, max_length=2048)
    original_name: str = Field(min_length=1, max_length=1000)
    media_type: str = Field(min_length=1, max_length=256)
    size_bytes: int = Field(ge=0)
    retrieved_at: str | None = None
    origin_namespace: str = Field(default="manual", min_length=1, max_length=128)
    origin_key: str = Field(default="", max_length=4096)
    origin_version: int = Field(default=0, ge=0)
    etag: str | None = None
    last_modified: str | None = None
    supersedes_version_id: str | None = None
    ingestion_status: IngestionStatus = IngestionStatus.STORED
    ragflow_dataset_id: str | None = None
    ragflow_document_id: str | None = None
    last_error: str = ""

    @field_validator("archive_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        value = value.lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("archive_sha256 must be a SHA-256 digest")
        return value

    @field_validator("archive_relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            normalized.startswith("/")
            or ":" in normalized.split("/")[0]
            or ".." in normalized.split("/")
        ):
            raise ValueError("archive_relative_path must remain relative")
        return normalized


class SourceRecord(SourceDraft):
    source_id: str
    current_version_id: str | None
    created_at: str
    updated_at: str


class SourceVersionRecord(SourceVersionDraft):
    source_version_id: str
    last_indexed_at: str | None
    created_at: str
    updated_at: str


class ClaimDraft(ResearchModel):
    claim_key: str | None = Field(default=None, min_length=1, max_length=256)
    statement: str = Field(min_length=1, max_length=100_000)
    status: ClaimStatus = ClaimStatus.PROPOSED
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""
    review_state: ReviewState = ReviewState.UNREVIEWED
    supersedes_claim_id: str | None = None


class EvidenceDraft(ResearchModel):
    claim_ref: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    chunk_fingerprint: str
    role: EvidenceRole
    exact_quote: str = Field(min_length=1)
    ragflow_chunk_id: str | None = None
    locator: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    strength: float = Field(default=0.5, ge=0, le=1)
    directness: float = Field(default=0.5, ge=0, le=1)
    review_state: ReviewState = ReviewState.UNREVIEWED
    note: str = ""

    @field_validator("chunk_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        value = value.lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("chunk_fingerprint must be a SHA-256 digest")
        return value

    @model_validator(mode="after")
    def validate_pages(self) -> EvidenceDraft:
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("page_end must not precede page_start")
        return self


class QuestionDraft(ResearchModel):
    question_key: str | None = Field(default=None, min_length=1, max_length=256)
    question: str = Field(min_length=1)
    motivation: str = ""
    current_answer: str = ""
    evidence_strength: float = Field(default=0, ge=0, le=1)
    missing_evidence: str = ""
    recommended_search_terms: list[str] = Field(default_factory=list)
    next_action: str = ""
    priority: int = Field(default=0, ge=0)
    closure_criteria: str = ""
    status: QuestionStatus = QuestionStatus.OPEN
    supersedes_question_id: str | None = None
    linked_claim_refs: list[str] = Field(default_factory=list)


class CandidateDraft(ResearchModel):
    candidate_key: str | None = Field(default=None, min_length=1, max_length=256)
    name: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    target_capability: str = ""
    mechanism: str = ""
    description: str = ""
    supporting_claim_refs: list[str] = Field(default_factory=list)
    opposing_claim_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    expected_benefits: list[str] = Field(default_factory=list)
    expected_costs: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    rejection_criteria: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0)
    status: CandidateStatus = CandidateStatus.PROPOSED
    review_state: ReviewState = ReviewState.UNREVIEWED
    supersedes_candidate_id: str | None = None


class DecisionDraft(ResearchModel):
    decision_key: str | None = Field(default=None, min_length=1, max_length=256)
    title: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    status: DecisionStatus = DecisionStatus.PROPOSED
    selected_option: str = ""
    alternatives: list[str] = Field(default_factory=list)
    supporting_claim_refs: list[str] = Field(default_factory=list)
    opposing_claim_refs: list[str] = Field(default_factory=list)
    rationale: str = ""
    assumptions: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    revisit_trigger: str = ""
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    supersedes_decision_id: str | None = None


class ExperimentDraft(ResearchModel):
    title: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    research_question_ref: str | None = None
    candidate_ref: str | None = None
    baseline_configuration: str = ""
    treatment_configuration: str = ""
    environment: str = ""
    protocol: str = ""
    metrics: list[str] = Field(default_factory=list)
    success_thresholds: list[str] = Field(default_factory=list)
    failure_thresholds: list[str] = Field(default_factory=list)
    safety_bounds: list[str] = Field(default_factory=list)
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    review_state: ReviewState = ReviewState.UNREVIEWED
    supersedes_experiment_id: str | None = None


class SummaryDraft(ResearchModel):
    scope_type: str = Field(min_length=1)
    scope_ref: str = Field(min_length=1)
    summary_kind: str = Field(min_length=1)
    content: str = Field(min_length=1)
    model_name: str | None = None
    review_state: ReviewState = ReviewState.UNREVIEWED
    supersedes_summary_id: str | None = None


class RelationshipDraft(ResearchModel):
    subject_type: str = Field(min_length=1)
    subject_ref: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    note: str = ""
    review_state: ReviewState = ReviewState.UNREVIEWED


class AnalysisRunDraft(ResearchModel):
    tool_name: str = Field(min_length=1)
    analysis_type: str = Field(min_length=1)
    input_hash: str
    started_at: str = Field(min_length=1)
    tool_version: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    prompt_hash: str | None = None
    configuration_hash: str | None = None
    input_item_ids: list[str] = Field(default_factory=list)
    output_hash: str | None = None
    completed_at: str | None = None
    status: AnalysisStatus = AnalysisStatus.PENDING
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    review_state: ReviewState = ReviewState.UNREVIEWED
    reviewed_by: str | None = None
    reviewed_at: str | None = None

    @field_validator("input_hash", "prompt_hash", "configuration_hash", "output_hash")
    @classmethod
    def validate_optional_hash(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("hash fields must be SHA-256 digests")
        return value


class ResearchPacketDraft(ResearchModel):
    idempotency_key: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1)
    research_question: str = ""
    synthesis: str = ""
    submitted_by: str = Field(min_length=1)
    review_state: ReviewState = ReviewState.UNREVIEWED
    analysis_run: AnalysisRunDraft | None = None
    claims: list[ClaimDraft] = Field(default_factory=list)
    evidence: list[EvidenceDraft] = Field(default_factory=list)
    questions: list[QuestionDraft] = Field(default_factory=list)
    candidates: list[CandidateDraft] = Field(default_factory=list)
    decisions: list[DecisionDraft] = Field(default_factory=list)
    experiments: list[ExperimentDraft] = Field(default_factory=list)
    summaries: list[SummaryDraft] = Field(default_factory=list)
    relationships: list[RelationshipDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def same_project(self) -> ResearchPacketDraft:
        nested = [
            self.analysis_run,
            *self.claims,
            *self.evidence,
            *self.questions,
            *self.candidates,
            *self.decisions,
            *self.experiments,
            *self.summaries,
            *self.relationships,
        ]
        if any(
            item is not None and item.project_id != self.project_id for item in nested
        ):
            raise ValueError("all packet records must use the packet project_id")
        return self


class PreservedPacket(BaseModel):
    project_id: str
    packet_id: str
    idempotent_replay: bool
    entity_ids: dict[str, list[str]]


class OverlayHealth(BaseModel):
    project_id: str
    status: str
    counts: dict[str, int]
    ingestion_counts: dict[str, int]


class ContextPacket(BaseModel):
    project_id: str
    query: str
    retrieved_passages: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    entity_ids: list[str]
    content_sha256: str
