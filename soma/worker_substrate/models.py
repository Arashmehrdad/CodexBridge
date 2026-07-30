"""Provider-neutral contracts for the interactive worker substrate.

Deliberate omissions, each one an authority decision:

- no provider enum. A closed provider vocabulary would make a substrate that
  claims to be provider-neutral provider-specific, and every new provider would
  become a schema migration. Providers are validated opaque identifiers.
- no queued/running/waiting/terminal vocabulary. A provider session is a
  *binding fact* about a canonical run, not a second thing that can be running.
  The dispositions below describe what Soma can prove about a record, never what
  phase of work it is in.
- no ``TaskKind``, ``BackendKind``, or ``TaskCommandKind`` additions. This
  package launches nothing and delivers nothing; it only persists. Adding a task
  command kind before the command semantics exist would publish a contract that
  no code honours.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


WORKER_SUBSTRATE_SCHEMA_COMPONENT: Final[str] = "interactive_worker_substrate"
WORKER_SUBSTRATE_SCHEMA_VERSION: Final[int] = 1
WORKER_SUBSTRATE_MODEL_VERSION: Final[str] = "worker_substrate.v1"

SESSION_BINDING_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^wsession_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)
INTERACTION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^wmsg_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)


class SessionBindingDisposition(str, Enum):
    """What Soma can currently prove about one provider-session binding.

    None of these is a lifecycle state. ``UNVERIFIED`` and ``MISMATCH_DETECTED``
    deliberately avoid reusing any ``TaskState`` spelling so that a binding
    disposition can never be mistaken for, or projected as, task state.
    """

    BOUND = "bound"
    MISMATCH_DETECTED = "mismatch_detected"
    UNVERIFIED = "unverified"


class InteractionKind(str, Enum):
    STEER = "steer"
    SUPPLY_INPUT = "supply_input"


class InteractionDelivery(str, Enum):
    """Durable delivery disposition for one persisted-before-send message."""

    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class CheckpointDeadlinePolicy(str, Enum):
    BOUNDED = "bounded"
    EXPLICIT_NONE = "explicit_none"


class CheckpointExpiryDisposition(str, Enum):
    """Expiry evidence disposition.

    ``QUIESCENT_CONFIRMED`` is the only value that may later authorise releasing
    repository or resource ownership, and the schema refuses to store it without
    a quiescence proof reference. Everything else is uncertainty that retains
    ownership. This package records the evidence; it performs no pause,
    cancellation, or release.
    """

    RECORDED = "recorded"
    QUIESCENT_CONFIRMED = "quiescent_confirmed"
    UNCERTAIN = "uncertain"


class ProviderChildRole(str, Enum):
    PROVIDER_ROOT = "provider_root"
    OWNED_DESCENDANT = "owned_descendant"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opaque_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:12]}"


def make_session_binding_id() -> str:
    return _opaque_id("wsession")


def make_interaction_id() -> str:
    return _opaque_id("wmsg")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def require_opaque(value: str, field: str) -> str:
    """Validate a provider-supplied identifier without altering a single byte.

    Opaque identifiers are never trimmed, cased, or normalised here. The only
    rejected forms are empty and whitespace-only, which cannot identify anything.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty opaque identifier")
    return value


def usage_dedupe_key(
    *,
    provider: str,
    native_session_id: str,
    provider_event_id: str,
    sequence: int,
    raw_event_hash: str,
) -> str:
    """Deterministic dedupe identity for one provider usage event.

    Resume replays the same provider events, so the key must be derivable purely
    from the event itself. ``provider_event_id`` is empty for providers that do
    not identify usage events (Codex ``turn.completed``); the sequence and the
    exact raw-event hash carry identity in that case.
    """
    return sha256(
        canonical_json(
            {
                "provider": provider,
                "native_session_id": native_session_id,
                "provider_event_id": provider_event_id,
                "sequence": int(sequence),
                "raw_event_hash": raw_event_hash,
            }
        ).encode("utf-8")
    ).hexdigest()


class ProviderSessionBinding(BaseModel):
    """One canonical run bound to exactly one provider-native session."""

    model_config = ConfigDict(extra="forbid")

    session_binding_id: str
    project_id: str
    resource_id: str
    task_id: str
    run_id: str
    provider: str
    native_session_id: str
    adapter_id: str
    adapter_version: str
    protocol_id: str
    protocol_version: str
    disposition: SessionBindingDisposition = SessionBindingDisposition.BOUND
    disposition_reason: str = ""
    resume_cursor: str = ""
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class InteractionRecord(BaseModel):
    """A message committed before delivery, with durable delivery evidence."""

    model_config = ConfigDict(extra="forbid")

    interaction_id: str
    session_binding_id: str
    task_id: str
    interaction_kind: InteractionKind
    idempotency_key: str
    payload_ref: str
    payload_hash: str
    payload_bytes: int
    expected_checkpoint_id: str = ""
    requested_state_version: int = 0
    delivery: InteractionDelivery = InteractionDelivery.PENDING
    delivery_reason: str = ""
    delivery_evidence_ref: str = ""
    created_at: str
    updated_at: str
    delivered_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CheckpointDeadline(BaseModel):
    """A durable deadline complementing one existing ``task_checkpoints`` row."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str
    task_id: str
    session_binding_id: str = ""
    deadline_policy: CheckpointDeadlinePolicy
    deadline_at: str = ""
    policy_owner: str = ""
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CheckpointExpiryEvent(BaseModel):
    """Immutable evidence that one checkpoint deadline was observed expired."""

    model_config = ConfigDict(extra="forbid")

    expiry_id: str
    checkpoint_id: str
    task_id: str
    idempotency_key: str
    deadline_at: str
    observed_at: str
    disposition: CheckpointExpiryDisposition
    quiescence_proof_ref: str = ""
    reason: str = ""
    evidence_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class UsageEvent(BaseModel):
    """One raw provider-native usage event.

    Every count is optional and no value is ever invented. A provider that does
    not report a figure stores ``None``, which is distinguishable from a reported
    zero. ``provider_reported_cost_usd`` is a raw provider string, not a Soma
    currency computation, and Codex token counts are never converted to USD.
    """

    model_config = ConfigDict(extra="forbid")

    usage_event_id: int = 0
    session_binding_id: str
    task_id: str
    run_id: str
    provider: str
    native_session_id: str
    event_kind: str
    provider_event_id: str = ""
    sequence: int
    dedupe_key: str
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    provider_reported_cost_usd: str | None = None
    raw_event_hash: str
    raw_event: dict[str, Any] = Field(default_factory=dict)
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProviderChildProcessRecord(BaseModel):
    """PID plus PID-reuse-resistant start identity for one provider process.

    ``RunStore`` owns the canonical Soma worker process for a run. A provider
    session is a *tree* below that worker, so this records observations of that
    tree. It performs no launch, no termination, and no ownership transfer.
    """

    model_config = ConfigDict(extra="forbid")

    record_id: int = 0
    session_binding_id: str
    task_id: str
    run_id: str
    role: ProviderChildRole
    pid: int
    process_start_identity: str
    parent_pid: int | None = None
    image_name: str = ""
    observed_at: str
    observation_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
