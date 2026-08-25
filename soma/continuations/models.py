"""Mechanical persistence models for Sol semantic continuation.

These records preserve identity, governing contract revisions, free-form handoffs,
and Task/Run origin links. They deliberately do not model reasoning phases,
next actions, evidence frontiers, or any other model-cognition state.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


CONTINUATION_SCHEMA_COMPONENT: Final[str] = "sol_semantic_continuation"
CONTINUATION_SCHEMA_VERSION: Final[int] = 2
CONTINUATION_MODEL_VERSION: Final[str] = "continuation.v1"

CONTINUATION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^cont_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)
CONTRACT_REVISION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^contrev_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)
HANDOFF_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^conthandoff_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)
EFFECT_LINK_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^conteffect_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)


class ContinuationLifecycle(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ContinuationEffectKind(str, Enum):
    TASK = "task"
    RUN = "run"


class ContinuationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    continuation_id: str
    label: str = ""
    lifecycle: ContinuationLifecycle
    current_contract_revision_id: str
    creation_controller_request_id: str
    creation_request_hash: str
    created_at: str
    updated_at: str
    closed_at: str | None = None
    closure_controller_request_id: str = ""
    closure_request_hash: str = ""

    @property
    def continuation_context_ref(self) -> str:
        return self.current_contract_revision_id


class ContractRevisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_revision_id: str
    continuation_id: str
    parent_revision_id: str | None = None
    revision_number: int = Field(ge=1)
    instruction_text: str = ""
    instruction_ref: str = ""
    content_hash: str
    provenance_class: str
    provenance_ref: str = ""
    controller_request_id: str
    request_hash: str
    created_at: str

    @property
    def continuation_context_ref(self) -> str:
        return self.contract_revision_id


class ContinuationHandoffRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    continuation_id: str
    contract_revision_id: str
    sequence_number: int = Field(ge=1)
    handoff_text: str
    content_hash: str
    controller_request_id: str
    request_hash: str
    created_at: str


class ContinuationEffectLinkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str
    continuation_id: str
    contract_revision_id: str
    effect_kind: ContinuationEffectKind
    effect_id: str
    controller_request_id: str
    request_hash: str
    created_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opaque_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:12]}"


def make_continuation_id() -> str:
    return _opaque_id("cont")


def make_contract_revision_id() -> str:
    return _opaque_id("contrev")


def make_handoff_id() -> str:
    return _opaque_id("conthandoff")


def make_effect_link_id() -> str:
    return _opaque_id("conteffect")


def _validate_id(value: str, pattern: re.Pattern[str], kind: str) -> None:
    if not pattern.match(value):
        raise ValueError(f"Invalid {kind}: {value}")


def validate_continuation_id(continuation_id: str) -> None:
    _validate_id(continuation_id, CONTINUATION_ID_PATTERN, "continuation_id")


def validate_contract_revision_id(contract_revision_id: str) -> None:
    _validate_id(
        contract_revision_id,
        CONTRACT_REVISION_ID_PATTERN,
        "contract_revision_id",
    )


def validate_handoff_id(handoff_id: str) -> None:
    _validate_id(handoff_id, HANDOFF_ID_PATTERN, "handoff_id")


def validate_effect_link_id(link_id: str) -> None:
    _validate_id(link_id, EFFECT_LINK_ID_PATTERN, "link_id")


def content_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
