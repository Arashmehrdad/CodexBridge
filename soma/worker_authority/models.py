"""Provider-neutral worker principal and positive capability-grant contracts.

Worker credentials authenticate a bounded principal. They do not create Task,
Run, ProjectScope, provider-session, role, or protected-effect authority. Those
identities remain owned by their existing canonical stores and are revalidated
at authorization time.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Final, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


WORKER_AUTHORITY_SCHEMA_COMPONENT: Final[str] = "worker_authority"
WORKER_AUTHORITY_SCHEMA_VERSION: Final[int] = 1
WORKER_AUTHORITY_MODEL_VERSION: Final[str] = "worker_authority.v1"
WORKER_CREDENTIAL_PREFIX: Final[str] = "wa1_"
WORKER_GRANT_CAPABILITY_PREFIX: Final[str] = "worker-grant:"
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{64}$")


class WorkerAuthorityError(ValueError):
    """Base worker-authority validation failure."""


class WorkerAuthorityConflict(WorkerAuthorityError):
    """An idempotent identity was replayed with different authority material."""


class WorkerAuthorizationDenied(WorkerAuthorityError):
    """A worker request is outside its exact active authority ceiling."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_authority_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:24]}"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def canonical_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_opaque(value: str, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{field} must be a non-empty opaque string")
    if "\x00" in value:
        raise ValueError(f"{field} contains an embedded NUL")
    return value


def validate_sha256(value: str, field: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


class WorkerPrincipalIssueV1(_FrozenModel):
    controller_request_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    session_binding_id: str = Field(default="", max_length=128)
    role_ref: str = Field(min_length=1, max_length=512)
    mandate_ref: str = Field(min_length=1, max_length=2048)
    mandate_hash: str
    mandate_version: str = Field(min_length=1, max_length=128)
    issuer_ref: str = Field(min_length=1, max_length=512)
    expires_at: datetime

    @model_validator(mode="after")
    def _validate_issue(self):
        for field, value, maximum in (
            ("controller_request_id", self.controller_request_id, 128),
            ("project_id", self.project_id, 128),
            ("resource_id", self.resource_id, 128),
            ("task_id", self.task_id, 128),
            ("run_id", self.run_id, 128),
            ("role_ref", self.role_ref, 512),
            ("mandate_ref", self.mandate_ref, 2048),
            ("mandate_version", self.mandate_version, 128),
            ("issuer_ref", self.issuer_ref, 512),
        ):
            validate_opaque(value, field, max_length=maximum)
        if self.session_binding_id:
            validate_opaque(self.session_binding_id, "session_binding_id", max_length=128)
        validate_sha256(self.mandate_hash, "mandate_hash")
        require_aware(self.expires_at, "expires_at")
        return self

    def authority_material(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"controller_request_id"})

    @property
    def request_hash(self) -> str:
        return canonical_hash(self.authority_material())


class WorkerPrincipalV1(_FrozenModel):
    principal_id: str
    verifier_hash: str
    project_id: str
    resource_id: str
    scope_generation: int
    task_id: str
    run_id: str
    session_binding_id: str = ""
    role_ref: str
    mandate_ref: str
    mandate_hash: str
    mandate_version: str
    issuer_ref: str
    expires_at: datetime
    controller_request_id: str
    request_hash: str
    content_hash: str
    created_at: datetime

    @model_validator(mode="after")
    def _validate_principal(self):
        validate_opaque(self.principal_id, "principal_id", max_length=128)
        for field in ("verifier_hash", "mandate_hash", "request_hash", "content_hash"):
            validate_sha256(getattr(self, field), field)
        require_aware(self.expires_at, "expires_at")
        require_aware(self.created_at, "created_at")
        return self

    def public_projection(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"verifier_hash"})


class WorkerPrincipalIssueResultV1(_FrozenModel):
    principal: WorkerPrincipalV1
    created: bool
    credential_once: str | None = None


class WorkerCapabilityGrantIssueV1(_FrozenModel):
    controller_request_id: str = Field(min_length=1, max_length=128)
    principal_id: str = Field(min_length=1, max_length=128)
    intent_ref: str = Field(min_length=1, max_length=2048)
    intent_hash: str
    operation_ref: str = Field(min_length=1, max_length=2048)
    operation_hash: str
    parameter_contract: dict[str, Any] = Field(default_factory=dict)
    issuer_ref: str = Field(min_length=1, max_length=512)
    expires_at: datetime

    @model_validator(mode="after")
    def _validate_grant_issue(self):
        for field, value, maximum in (
            ("controller_request_id", self.controller_request_id, 128),
            ("principal_id", self.principal_id, 128),
            ("intent_ref", self.intent_ref, 2048),
            ("operation_ref", self.operation_ref, 2048),
            ("issuer_ref", self.issuer_ref, 512),
        ):
            validate_opaque(value, field, max_length=maximum)
        validate_sha256(self.intent_hash, "intent_hash")
        validate_sha256(self.operation_hash, "operation_hash")
        require_aware(self.expires_at, "expires_at")
        canonical_json(self.parameter_contract)
        return self


class WorkerCapabilityGrantV1(_FrozenModel):
    grant_id: str
    principal_id: str
    project_id: str
    resource_id: str
    scope_generation: int
    task_id: str
    run_id: str
    session_binding_id: str
    role_ref: str
    mandate_ref: str
    mandate_hash: str
    mandate_version: str
    intent_ref: str
    intent_hash: str
    operation_ref: str
    operation_hash: str
    parameter_contract: dict[str, Any]
    parameter_contract_hash: str
    issuer_ref: str
    expires_at: datetime
    controller_request_id: str
    request_hash: str
    content_hash: str
    created_at: datetime

    @model_validator(mode="after")
    def _validate_grant(self):
        for field in (
            "mandate_hash",
            "intent_hash",
            "operation_hash",
            "parameter_contract_hash",
            "request_hash",
            "content_hash",
        ):
            validate_sha256(getattr(self, field), field)
        if canonical_hash(self.parameter_contract) != self.parameter_contract_hash:
            raise ValueError("parameter_contract_hash does not match parameter_contract")
        require_aware(self.expires_at, "expires_at")
        require_aware(self.created_at, "created_at")
        return self

    @property
    def capability_ref(self) -> str:
        return f"{WORKER_GRANT_CAPABILITY_PREFIX}{self.grant_id}"

    @property
    def capability_hash(self) -> str:
        return self.content_hash


RevocationTargetKind = Literal["principal", "grant"]


class WorkerAuthorityRevocationV1(_FrozenModel):
    revocation_id: str
    target_kind: RevocationTargetKind
    target_id: str
    controller_request_id: str
    request_hash: str
    reason_ref: str
    reason_hash: str
    issuer_ref: str
    revoked_at: datetime

    @model_validator(mode="after")
    def _validate_revocation(self):
        for field in ("request_hash", "reason_hash"):
            validate_sha256(getattr(self, field), field)
        require_aware(self.revoked_at, "revoked_at")
        return self


class WorkerOperationSpecV1(_FrozenModel):
    operation_ref: str = Field(min_length=1, max_length=2048)
    operation_kind: Literal["query", "action", "protected_mutation"]
    requires_session: bool = True
    allowed_task_states: tuple[str, ...] = ("running",)
    approval_required: bool = False
    description: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def _validate_operation(self):
        validate_opaque(self.operation_ref, "operation_ref", max_length=2048)
        if not self.allowed_task_states:
            raise ValueError("allowed_task_states must not be empty")
        if len(set(self.allowed_task_states)) != len(self.allowed_task_states):
            raise ValueError("allowed_task_states must be unique")
        return self

    def authority_material(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"description"})

    @property
    def operation_hash(self) -> str:
        return canonical_hash(self.authority_material())


class WorkerAuthorizationRequestV1(_FrozenModel):
    principal_id: str = Field(min_length=1, max_length=128)
    credential: str = Field(min_length=1, max_length=512)
    grant_id: str = Field(min_length=1, max_length=128)
    role_ref: str = Field(min_length=1, max_length=512)
    mandate_ref: str = Field(min_length=1, max_length=2048)
    mandate_hash: str
    mandate_version: str = Field(min_length=1, max_length=128)
    intent_ref: str = Field(min_length=1, max_length=2048)
    intent_hash: str
    operation_ref: str = Field(min_length=1, max_length=2048)
    operation_hash: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_task_state_version: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_authorization(self):
        for field in ("mandate_hash", "intent_hash", "operation_hash"):
            validate_sha256(getattr(self, field), field)
        canonical_json(self.parameters)
        return self


class WorkerAuthorizationDecisionV1(_FrozenModel):
    authorized: Literal[True] = True
    principal_id: str
    grant_id: str
    project_id: str
    resource_id: str
    scope_generation: int
    task_id: str
    run_id: str
    session_binding_id: str
    role_ref: str
    mandate_ref: str
    mandate_hash: str
    mandate_version: str
    intent_ref: str
    intent_hash: str
    operation_ref: str
    operation_hash: str
    parameter_contract_hash: str
    task_state: str
    task_state_version: int
