"""Provider-neutral interaction transport port and deterministic stand-ins.

The production default is deliberately unavailable. V3-1A proves interaction
semantics with injected deterministic stand-ins; it does not pretend that a
Claude or Codex prompt was delivered before a real provider transport exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Callable, Protocol

from .models import ProviderSessionBinding


class TransportDispatchDisposition(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True)
class InteractionTransportRequest:
    """Reference-only request; secret-bearing payload bytes are never inlined."""

    message_id: str
    attempt_id: str
    command_kind: str
    message_class: str
    session_binding_id: str
    provider: str
    native_session_id: str
    payload_ref: str
    payload_hash: str
    payload_bytes: int
    checkpoint_id: str = ""


@dataclass(frozen=True)
class InteractionTransportResult:
    disposition: TransportDispatchDisposition
    reason: str = ""
    evidence_ref: str = ""


class InteractionTransportUnavailable(RuntimeError):
    """No reviewed transport can deliver the requested provider interaction."""


class InteractionTransportOutcomeUnknown(RuntimeError):
    """Dispatch may have occurred, so automatic resend is forbidden."""


class InteractionTransport(Protocol):
    @property
    def claimer_id(self) -> str: ...

    def supports(
        self, binding: ProviderSessionBinding, *, command_kind: str
    ) -> bool: ...

    def dispatch(
        self, request: InteractionTransportRequest
    ) -> InteractionTransportResult: ...


class UnavailableInteractionTransport:
    """Honest production default until a reviewed real provider transport exists."""

    @property
    def claimer_id(self) -> str:
        return "transport:unavailable"

    def supports(
        self, binding: ProviderSessionBinding, *, command_kind: str
    ) -> bool:
        del binding, command_kind
        return False

    def dispatch(
        self, request: InteractionTransportRequest
    ) -> InteractionTransportResult:
        del request
        raise InteractionTransportUnavailable(
            "No reviewed interaction transport is active for this provider session"
        )


class DeterministicInteractionTransport:
    """Reference-only deterministic stand-in used for contract and crash tests."""

    def __init__(
        self,
        *,
        disposition: TransportDispatchDisposition = (
            TransportDispatchDisposition.ACKNOWLEDGED
        ),
        supported_providers: set[str] | frozenset[str] | None = None,
        supported_command_kinds: set[str] | frozenset[str] | None = None,
        reason: str = "deterministic stand-in disposition",
        claimer_id: str = "transport:deterministic-stand-in",
        before_dispatch: Callable[[InteractionTransportRequest], None] | None = None,
        raise_outcome_unknown: bool = False,
    ) -> None:
        self.disposition = disposition
        self.supported_providers = frozenset(
            {"claude_code"} if supported_providers is None else supported_providers
        )
        self.supported_command_kinds = frozenset(
            {"steer", "supply_input"}
            if supported_command_kinds is None
            else supported_command_kinds
        )
        self.reason = reason
        self._claimer_id = claimer_id
        self.before_dispatch = before_dispatch
        self.raise_outcome_unknown = bool(raise_outcome_unknown)
        self.requests: list[InteractionTransportRequest] = []

    @property
    def claimer_id(self) -> str:
        return self._claimer_id

    def supports(
        self, binding: ProviderSessionBinding, *, command_kind: str
    ) -> bool:
        return (
            binding.provider in self.supported_providers
            and command_kind in self.supported_command_kinds
        )

    @staticmethod
    def _evidence_ref(request: InteractionTransportRequest, suffix: str) -> str:
        digest = sha256(
            (
                request.message_id
                + "\0"
                + request.attempt_id
                + "\0"
                + request.payload_hash
                + "\0"
                + suffix
            ).encode("utf-8")
        ).hexdigest()
        return f"deterministic_transport:{suffix}:{digest}"

    def dispatch(
        self, request: InteractionTransportRequest
    ) -> InteractionTransportResult:
        if self.before_dispatch is not None:
            self.before_dispatch(request)
        self.requests.append(request)
        if self.raise_outcome_unknown:
            raise InteractionTransportOutcomeUnknown(
                "deterministic stand-in raised after transport claim"
            )
        return InteractionTransportResult(
            disposition=self.disposition,
            reason=self.reason,
            evidence_ref=self._evidence_ref(request, self.disposition.value),
        )
