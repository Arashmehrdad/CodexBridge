"""Pure provider-neutral reasoning specification contracts.

ReasoningSpecV1 is execution routing beneath canonical Task authority. Provider
identity belongs here and in later backend bindings, never in WorkPackage
identity. Prompt bodies, repositories, transcripts and secrets remain refs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import validate_opaque, validate_sha256


REASONING_SPEC_SCHEMA_VERSION: Final[str] = "reasoning_spec.v1"
MAX_REASONING_CONTEXT_REFS: Final[int] = 64
MAX_REASONING_DEPENDENCY_PROOF_REFS: Final[int] = 64
MIN_REASONING_WALL_TIME_SECONDS: Final[int] = 1
MAX_REASONING_WALL_TIME_SECONDS: Final[int] = 86_400
MIN_REASONING_OUTPUT_BYTES: Final[int] = 1024
MAX_REASONING_OUTPUT_BYTES: Final[int] = 262_144
MIN_PROVIDER_INTERNAL_CONCURRENCY: Final[int] = 1
MAX_PROVIDER_INTERNAL_CONCURRENCY: Final[int] = 8
MAX_REASONING_TOKEN_LIMIT: Final[int] = 9_223_372_036_854_775_807

ContinuationPolicy = Literal[
    "none",
    "explicit_provider_identity",
    "provider_managed",
]
MutationPolicy = Literal["read_only", "protected_broker_only"]


class _FrozenReasoningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReasoningHashedReferenceV1(_FrozenReasoningModel):
    ref: str = Field(min_length=1, max_length=2048)
    hash: str

    @model_validator(mode="after")
    def _validate_reference(self):
        validate_opaque(self.ref, "ref", max_length=2048)
        validate_sha256(self.hash, "hash")
        return self


class ReasoningBudgetsV1(_FrozenReasoningModel):
    wall_time_seconds: int = Field(
        ge=MIN_REASONING_WALL_TIME_SECONDS,
        le=MAX_REASONING_WALL_TIME_SECONDS,
    )
    output_bytes: int = Field(
        ge=MIN_REASONING_OUTPUT_BYTES,
        le=MAX_REASONING_OUTPUT_BYTES,
    )
    input_token_limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_REASONING_TOKEN_LIMIT,
    )
    output_token_limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_REASONING_TOKEN_LIMIT,
    )
    cost_limit_usd: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=6,
    )
    provider_internal_concurrency_limit: int = Field(
        ge=MIN_PROVIDER_INTERNAL_CONCURRENCY,
        le=MAX_PROVIDER_INTERNAL_CONCURRENCY,
    )


class ReasoningSpecV1(_FrozenReasoningModel):
    schema_version: Literal[REASONING_SPEC_SCHEMA_VERSION] = (
        REASONING_SPEC_SCHEMA_VERSION
    )
    assignment_ref: str = Field(min_length=1, max_length=2048)
    assignment_hash: str
    context_refs: tuple[ReasoningHashedReferenceV1, ...] = Field(
        default=(), max_length=MAX_REASONING_CONTEXT_REFS
    )
    dependency_proof_refs: tuple[ReasoningHashedReferenceV1, ...] = Field(
        default=(), max_length=MAX_REASONING_DEPENDENCY_PROOF_REFS
    )
    output_contract_ref: str = Field(min_length=1, max_length=2048)
    output_contract_hash: str
    tool_policy_ref: str = Field(min_length=1, max_length=2048)
    tool_policy_hash: str
    authority_ref: str = Field(min_length=1, max_length=2048)
    authority_hash: str
    provider_route_ref: str = Field(min_length=1, max_length=2048)
    provider_route_hash: str
    budgets: ReasoningBudgetsV1
    continuation_policy: ContinuationPolicy
    mutation_policy: MutationPolicy

    @model_validator(mode="after")
    def _validate_spec(self):
        for field, value in (
            ("assignment_ref", self.assignment_ref),
            ("output_contract_ref", self.output_contract_ref),
            ("tool_policy_ref", self.tool_policy_ref),
            ("authority_ref", self.authority_ref),
            ("provider_route_ref", self.provider_route_ref),
        ):
            validate_opaque(value, field, max_length=2048)
        for field, value in (
            ("assignment_hash", self.assignment_hash),
            ("output_contract_hash", self.output_contract_hash),
            ("tool_policy_hash", self.tool_policy_hash),
            ("authority_hash", self.authority_hash),
            ("provider_route_hash", self.provider_route_hash),
        ):
            validate_sha256(value, field)

        context_refs = [reference.ref for reference in self.context_refs]
        proof_refs = [reference.ref for reference in self.dependency_proof_refs]
        if len(context_refs) != len(set(context_refs)):
            raise ValueError("context_refs must contain unique refs")
        if len(proof_refs) != len(set(proof_refs)):
            raise ValueError("dependency_proof_refs must contain unique refs")
        return self
