"""Provider-neutral reasoning backend protocol and bounded evidence projections.

These types are subordinate backend evidence. They deliberately do not import or
expose canonical TaskState values; TaskManager may later reconcile this evidence
into canonical lifecycle state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import validate_opaque, validate_sha256

from .models import ReasoningSpecV1


StartDeliveryDisposition = Literal[
    "not_attempted",
    "claimed_not_sent",
    "accepted_bound",
    "rejected",
    "outcome_unknown",
]
ProviderBindingDisposition = Literal["unbound", "bound", "uncertain"]
ProviderTerminalClaim = Literal["none", "success", "failure", "cancelled", "incomplete"]
OutputContractDisposition = Literal["not_available", "valid", "invalid", "uncertain"]
CancellationDisposition = Literal["not_requested", "accepted", "rejected", "uncertain"]


class _FrozenBackendModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def reasoning_spec_hash(spec: ReasoningSpecV1) -> str:
    return content_hash(spec.model_dump(mode="json"))


def reasoning_spec_ref(spec: ReasoningSpecV1) -> str:
    return f"reasoning_spec:{reasoning_spec_hash(spec)}"


def make_backend_ref() -> str:
    return f"reasoning_{uuid4().hex}"


def make_start_attempt_id(backend_ref: str) -> str:
    validate_opaque(backend_ref, "backend_ref", max_length=256)
    return f"reasoning_start_{hashlib.sha256(backend_ref.encode('utf-8')).hexdigest()[:24]}"


def start_request_hash(spec: ReasoningSpecV1, backend_ref: str) -> str:
    validate_opaque(backend_ref, "backend_ref", max_length=256)
    return content_hash(
        {
            "schema": "soma.reasoning.backend_start.v1",
            "backend_ref": backend_ref,
            "reasoning_spec_ref": reasoning_spec_ref(spec),
            "reasoning_spec_hash": reasoning_spec_hash(spec),
            "provider_route_ref": spec.provider_route_ref,
            "provider_route_hash": spec.provider_route_hash,
        }
    )


class ReasoningBackendObservationV1(_FrozenBackendModel):
    backend_ref: str = Field(min_length=1, max_length=256)
    exists: bool
    start_delivery_disposition: StartDeliveryDisposition = "not_attempted"
    provider_binding_disposition: ProviderBindingDisposition = "unbound"
    provider_operation_ref: str | None = Field(default=None, max_length=2048)
    provider_status_raw: str | None = Field(default=None, max_length=512)
    provider_terminal_claim: ProviderTerminalClaim = "none"
    continuation_ref: str | None = Field(default=None, max_length=2048)
    last_event_cursor: str | None = Field(default=None, max_length=2048)
    output_contract_disposition: OutputContractDisposition = "not_available"
    result_ref: str | None = Field(default=None, max_length=2048)
    result_hash: str | None = None
    evidence_index_ref: str | None = Field(default=None, max_length=2048)
    evidence_index_hash: str | None = None
    raw_provider_evidence_root_ref: str | None = Field(default=None, max_length=2048)
    raw_provider_evidence_root_hash: str | None = None
    usage_summary: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=256)
    cancellation_disposition: CancellationDisposition = "not_requested"
    cancellation_evidence_ref: str | None = Field(default=None, max_length=2048)
    cancellation_evidence_hash: str | None = None

    @model_validator(mode="after")
    def _validate_observation(self):
        validate_opaque(self.backend_ref, "backend_ref", max_length=256)
        for field, ref in (
            ("provider_operation_ref", self.provider_operation_ref),
            ("continuation_ref", self.continuation_ref),
            ("last_event_cursor", self.last_event_cursor),
            ("result_ref", self.result_ref),
            ("evidence_index_ref", self.evidence_index_ref),
            ("raw_provider_evidence_root_ref", self.raw_provider_evidence_root_ref),
            ("cancellation_evidence_ref", self.cancellation_evidence_ref),
        ):
            if ref is not None:
                validate_opaque(ref, field, max_length=2048)
        for field, value in (
            ("result_hash", self.result_hash),
            ("evidence_index_hash", self.evidence_index_hash),
            ("raw_provider_evidence_root_hash", self.raw_provider_evidence_root_hash),
            ("cancellation_evidence_hash", self.cancellation_evidence_hash),
        ):
            if value is not None:
                validate_sha256(value, field)
        if bool(self.result_ref) != bool(self.result_hash):
            raise ValueError("result_ref and result_hash must appear together")
        if bool(self.evidence_index_ref) != bool(self.evidence_index_hash):
            raise ValueError(
                "evidence_index_ref and evidence_index_hash must appear together"
            )
        if bool(self.raw_provider_evidence_root_ref) != bool(
            self.raw_provider_evidence_root_hash
        ):
            raise ValueError(
                "raw_provider_evidence_root_ref and raw_provider_evidence_root_hash must appear together"
            )
        if bool(self.cancellation_evidence_ref) != bool(
            self.cancellation_evidence_hash
        ):
            raise ValueError(
                "cancellation_evidence_ref and cancellation_evidence_hash must appear together"
            )
        return self


class ReasoningResultReferenceV1(_FrozenBackendModel):
    backend_ref: str = Field(min_length=1, max_length=256)
    output_contract_version: str = Field(min_length=1, max_length=128)
    evidence_submission_ref: str = Field(min_length=1, max_length=2048)
    evidence_submission_hash: str
    provider_binding_ref: str = Field(min_length=1, max_length=2048)
    provider_binding_hash: str
    provider_provenance_index_ref: str = Field(min_length=1, max_length=2048)
    provider_provenance_index_hash: str
    raw_provider_evidence_root_ref: str = Field(min_length=1, max_length=2048)
    raw_provider_evidence_root_hash: str
    usage_ref: str | None = Field(default=None, max_length=2048)
    usage_hash: str | None = None
    published_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_result(self):
        validate_opaque(self.backend_ref, "backend_ref", max_length=256)
        for field, ref in (
            ("evidence_submission_ref", self.evidence_submission_ref),
            ("provider_binding_ref", self.provider_binding_ref),
            ("provider_provenance_index_ref", self.provider_provenance_index_ref),
            ("raw_provider_evidence_root_ref", self.raw_provider_evidence_root_ref),
        ):
            validate_opaque(ref, field, max_length=2048)
        for field, value in (
            ("evidence_submission_hash", self.evidence_submission_hash),
            ("provider_binding_hash", self.provider_binding_hash),
            ("provider_provenance_index_hash", self.provider_provenance_index_hash),
            ("raw_provider_evidence_root_hash", self.raw_provider_evidence_root_hash),
        ):
            validate_sha256(value, field)
        if self.usage_ref is not None:
            validate_opaque(self.usage_ref, "usage_ref", max_length=2048)
        if self.usage_hash is not None:
            validate_sha256(self.usage_hash, "usage_hash")
        if bool(self.usage_ref) != bool(self.usage_hash):
            raise ValueError("usage_ref and usage_hash must appear together")
        return self


class ReasoningBackend(Protocol):
    """Provider-neutral subordinate backend contract."""

    kind: str
    executor: str

    def reserve(self) -> str:
        """Allocate a Soma-owned backend reference without starting provider work."""

    def start(
        self, spec: ReasoningSpecV1, backend_ref: str
    ) -> ReasoningBackendObservationV1:
        """Persist start truth and invoke the provider adapter at most once."""

    def query(self, backend_ref: str) -> ReasoningBackendObservationV1:
        """Return subordinate provider/backend evidence only."""

    def cancel(self, backend_ref: str) -> ReasoningBackendObservationV1:
        """Request cancellation without fabricating canonical Task state."""

    def result_reference(self, backend_ref: str) -> ReasoningResultReferenceV1 | None:
        """Return bounded published result/evidence references, never transcript bodies."""
