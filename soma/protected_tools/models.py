"""Pure protected-mutation authority and effect contracts.

The contracts are deliberately provider-neutral. Provider-local call, trace,
thread, response and agent identifiers may be retained only as hashed evidence
correlation and never participate in the canonical protected-call request or
effect identity.
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import (
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
)


PROTECTED_TOOL_CALL_SCHEMA_VERSION: Final[str] = "protected_tool_call.v1"
PROTECTED_TOOL_EFFECT_SCHEMA_VERSION: Final[str] = "protected_tool_effect.v1"
PROTECTED_TOOL_CALL_HASH_DOMAIN: Final[str] = "soma.protected_tools.call.v1"
PROTECTED_TOOL_EFFECT_HASH_DOMAIN: Final[str] = "soma.protected_tools.effect.v1"
MAX_PROVIDER_PROVENANCE_REFS: Final[int] = 32

MutationClass = Literal[
    "repository",
    "external_system",
    "deployment",
    "communication",
    "financial",
    "generic",
]
EffectDisposition = Literal[
    "prevented",
    "rejected",
    "acknowledged",
    "outcome_unknown",
]


class _FrozenProtectedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProtectedProviderProvenanceRefV1(_FrozenProtectedModel):
    """Provider-local correlation retained as evidence only."""

    ref: str = Field(min_length=1, max_length=2048)
    hash: str

    @model_validator(mode="after")
    def _validate_reference(self):
        validate_opaque(self.ref, "provider_provenance_ref", max_length=2048)
        validate_sha256(self.hash, "provider_provenance_hash")
        return self


class ProtectedToolCallV1(_FrozenProtectedModel):
    schema_version: Literal[PROTECTED_TOOL_CALL_SCHEMA_VERSION] = (
        PROTECTED_TOOL_CALL_SCHEMA_VERSION
    )
    call_request_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    attempt_id: str
    backend_ref: str = Field(min_length=1, max_length=2048)
    mandate_ref: str = Field(min_length=1, max_length=2048)
    mandate_hash: str
    mandate_version: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    capability_ref: str = Field(min_length=1, max_length=2048)
    capability_hash: str
    tool_operation_ref: str = Field(min_length=1, max_length=2048)
    tool_operation_hash: str
    resource_key: str = Field(min_length=1, max_length=2048)
    idempotency_key: str = Field(min_length=1, max_length=256)
    payload_ref: str = Field(min_length=1, max_length=2048)
    payload_hash: str
    expected_task_state_version: int = Field(ge=0)
    expires_at: datetime
    mutation_class: MutationClass
    provider_provenance_refs: tuple[ProtectedProviderProvenanceRefV1, ...] = Field(
        default=(), max_length=MAX_PROVIDER_PROVENANCE_REFS
    )

    @model_validator(mode="after")
    def _validate_call(self):
        validate_opaque(self.call_request_id, "call_request_id", max_length=128)
        validate_opaque(self.task_id, "task_id", max_length=128)
        validate_kernel_id(self.attempt_id, "attempt_id")
        for field, value, maximum in (
            ("backend_ref", self.backend_ref, 2048),
            ("mandate_ref", self.mandate_ref, 2048),
            ("mandate_version", self.mandate_version, 128),
            ("project_id", self.project_id, 128),
            ("resource_id", self.resource_id, 128),
            ("capability_ref", self.capability_ref, 2048),
            ("tool_operation_ref", self.tool_operation_ref, 2048),
            ("resource_key", self.resource_key, 2048),
            ("idempotency_key", self.idempotency_key, 256),
            ("payload_ref", self.payload_ref, 2048),
        ):
            validate_opaque(value, field, max_length=maximum)
        for field, value in (
            ("mandate_hash", self.mandate_hash),
            ("capability_hash", self.capability_hash),
            ("tool_operation_hash", self.tool_operation_hash),
            ("payload_hash", self.payload_hash),
        ):
            validate_sha256(value, field)
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        refs = [(item.ref, item.hash) for item in self.provider_provenance_refs]
        if len(refs) != len(set(refs)):
            raise ValueError(
                "provider_provenance_refs must contain unique exact references"
            )
        return self

    def request_identity_payload(self) -> dict[str, Any]:
        """Return exact effect authority material; omit correlation-only fields."""

        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "backend_ref": self.backend_ref,
            "mandate_ref": self.mandate_ref,
            "mandate_hash": self.mandate_hash,
            "mandate_version": self.mandate_version,
            "project_id": self.project_id,
            "resource_id": self.resource_id,
            "scope_generation": self.scope_generation,
            "capability_ref": self.capability_ref,
            "capability_hash": self.capability_hash,
            "tool_operation_ref": self.tool_operation_ref,
            "tool_operation_hash": self.tool_operation_hash,
            "resource_key": self.resource_key,
            "idempotency_key": self.idempotency_key,
            "payload_ref": self.payload_ref,
            "payload_hash": self.payload_hash,
            "expected_task_state_version": self.expected_task_state_version,
            "expires_at": self.expires_at.isoformat(),
            "mutation_class": self.mutation_class,
        }

    @property
    def request_hash(self) -> str:
        return _domain_hash(
            PROTECTED_TOOL_CALL_HASH_DOMAIN, self.request_identity_payload()
        )


class ProtectedToolEffectV1(_FrozenProtectedModel):
    schema_version: Literal[PROTECTED_TOOL_EFFECT_SCHEMA_VERSION] = (
        PROTECTED_TOOL_EFFECT_SCHEMA_VERSION
    )
    call_request_id: str = Field(min_length=1, max_length=128)
    request_hash: str
    disposition: EffectDisposition
    external_effect_ref: str | None = Field(default=None, max_length=2048)
    external_effect_hash: str | None = None
    evidence_ref: str = Field(min_length=1, max_length=2048)
    evidence_hash: str
    completed_at: datetime

    @model_validator(mode="after")
    def _validate_effect(self):
        validate_opaque(self.call_request_id, "call_request_id", max_length=128)
        validate_sha256(self.request_hash, "request_hash")
        if bool(self.external_effect_ref) != bool(self.external_effect_hash):
            raise ValueError("external_effect_ref/hash must appear together")
        if self.external_effect_ref is not None:
            validate_opaque(
                self.external_effect_ref,
                "external_effect_ref",
                max_length=2048,
            )
            validate_sha256(self.external_effect_hash or "", "external_effect_hash")
        if self.disposition == "acknowledged" and self.external_effect_ref is None:
            raise ValueError(
                "acknowledged effect requires exact external effect identity"
            )
        if (
            self.disposition in {"prevented", "rejected"}
            and self.external_effect_ref is not None
        ):
            raise ValueError(
                f"{self.disposition} effect cannot claim an external effect identity"
            )
        validate_opaque(self.evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(self.evidence_hash, "evidence_hash")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        return self

    def effect_identity_payload(self) -> dict[str, Any]:
        """Return exact durable effect evidence; omit local record/time correlation."""

        return {
            "schema_version": self.schema_version,
            "request_hash": self.request_hash,
            "disposition": self.disposition,
            "external_effect_ref": self.external_effect_ref,
            "external_effect_hash": self.external_effect_hash,
            "evidence_ref": self.evidence_ref,
            "evidence_hash": self.evidence_hash,
        }

    @property
    def effect_hash(self) -> str:
        return _domain_hash(
            PROTECTED_TOOL_EFFECT_HASH_DOMAIN, self.effect_identity_payload()
        )


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _domain_hash(domain: str, payload: Any) -> str:
    return sha256(f"{domain}\0{_canonical_json(payload)}".encode("utf-8")).hexdigest()
