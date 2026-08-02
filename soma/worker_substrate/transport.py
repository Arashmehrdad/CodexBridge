"""Provider-neutral interaction transport port and deterministic stand-ins.

The production default is deliberately unavailable. V3-1A proves interaction
semantics with injected deterministic stand-ins; it does not pretend that a
Claude or Codex prompt was delivered before a real provider transport exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Callable, Protocol

from soma.safety import redact_secret_values

from .models import (
    ProviderSessionBinding,
    TransportAttemptRecord,
    TransportAttemptState,
    WorkerMessageRecord,
)
from .store import WorkerSubstrateStore


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
        self.supported_providers = frozenset(supported_providers or {"claude_code"})
        self.supported_command_kinds = frozenset(
            supported_command_kinds or {"steer", "supply_input"}
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


@dataclass(frozen=True)
class InteractionDispatchResult:
    """Durable evidence from one dispatch decision.

    ``dispatched`` says this invocation called the transport. ``replayed`` says
    the attempt already existed, in which case dispatch is never repeated.
    """

    message: WorkerMessageRecord
    attempt: TransportAttemptRecord
    dispatched: bool
    replayed: bool


class InteractionDispatcher:
    """Single-claimer provider-neutral dispatch with zero blind resend."""

    _registry_guard = Lock()
    _message_locks: dict[str, Lock] = {}

    def __init__(
        self,
        runs_dir: Path,
        *,
        transport: InteractionTransport | None = None,
    ) -> None:
        self.store = WorkerSubstrateStore(runs_dir)
        self.transport = transport or UnavailableInteractionTransport()

    @classmethod
    def _message_lock(cls, message_id: str) -> Lock:
        with cls._registry_guard:
            return cls._message_locks.setdefault(message_id, Lock())

    @staticmethod
    def _request(
        message: WorkerMessageRecord,
        binding: ProviderSessionBinding,
        attempt: TransportAttemptRecord,
    ) -> InteractionTransportRequest:
        if (
            binding.session_binding_id != message.session_binding_id
            or binding.task_id != message.task_id
            or binding.run_id != message.run_id
        ):
            raise ValueError(
                "message and provider-session binding identities do not match"
            )
        return InteractionTransportRequest(
            message_id=message.message_id,
            attempt_id=attempt.attempt_id,
            command_kind=message.command_kind,
            message_class=message.message_class.value,
            session_binding_id=binding.session_binding_id,
            provider=binding.provider,
            native_session_id=binding.native_session_id,
            payload_ref=message.payload_ref,
            payload_hash=message.payload_hash,
            payload_bytes=message.payload_bytes,
            checkpoint_id=message.checkpoint_id,
        )

    @staticmethod
    def _state_for_result(
        result: InteractionTransportResult,
    ) -> TransportAttemptState:
        return {
            TransportDispatchDisposition.ACKNOWLEDGED: (
                TransportAttemptState.ACKNOWLEDGED
            ),
            TransportDispatchDisposition.REJECTED: TransportAttemptState.REJECTED,
            TransportDispatchDisposition.OUTCOME_UNKNOWN: (
                TransportAttemptState.OUTCOME_UNKNOWN
            ),
        }[result.disposition]

    def dispatch_message(self, message_id: str) -> InteractionDispatchResult:
        """Dispatch a newly claimed message once, or return prior evidence.

        A pre-existing claim is never sent again. It may represent an active
        concurrent sender or a crash after claim; both cases require preserving
        the claim until evidence or recovery adjudication resolves it.
        """
        with self._message_lock(message_id):
            message = self.store.get_message(message_id)
            binding = self.store.get_binding(message.session_binding_id)
            attempt, created = self.store.claim_transport_attempt(
                message_id,
                claimer_id=self.transport.claimer_id,
            )
            if not created:
                return InteractionDispatchResult(
                    message=self.store.get_message(message_id),
                    attempt=attempt,
                    dispatched=False,
                    replayed=True,
                )

            if not self.transport.supports(
                binding,
                command_kind=message.command_kind,
            ):
                prevented = self.store.record_transport_attempt(
                    attempt.attempt_id,
                    state=TransportAttemptState.PREVENTED,
                    reason=(
                        "transport does not support this provider and command contract"
                    ),
                )
                return InteractionDispatchResult(
                    message=self.store.get_message(message_id),
                    attempt=prevented,
                    dispatched=False,
                    replayed=False,
                )

            request = self._request(message, binding, attempt)
            try:
                result = self.transport.dispatch(request)
            except InteractionTransportUnavailable:
                recorded = self.store.record_transport_attempt(
                    attempt.attempt_id,
                    state=TransportAttemptState.PREVENTED,
                    reason="reviewed interaction transport became unavailable",
                )
            except InteractionTransportOutcomeUnknown:
                recorded = self.store.record_transport_attempt(
                    attempt.attempt_id,
                    state=TransportAttemptState.OUTCOME_UNKNOWN,
                    reason="transport outcome cannot be proven; resend forbidden",
                )
            except Exception as exc:  # noqa: BLE001 - outcome is deliberately unknown
                recorded = self.store.record_transport_attempt(
                    attempt.attempt_id,
                    state=TransportAttemptState.OUTCOME_UNKNOWN,
                    reason=(
                        "transport raised after claim; outcome cannot be proven "
                        f"({redact_secret_values(type(exc).__name__)})"
                    ),
                )
            else:
                state = self._state_for_result(result)
                reason = redact_secret_values(result.reason)[:512]
                evidence_ref = redact_secret_values(result.evidence_ref)[:2048]
                if (
                    state is TransportAttemptState.ACKNOWLEDGED
                    and not evidence_ref
                ):
                    state = TransportAttemptState.OUTCOME_UNKNOWN
                    reason = (
                        "transport reported acknowledgement without durable evidence; "
                        "resend forbidden"
                    )
                recorded = self.store.record_transport_attempt(
                    attempt.attempt_id,
                    state=state,
                    reason=reason,
                    evidence_ref=evidence_ref,
                )

            return InteractionDispatchResult(
                message=self.store.get_message(message_id),
                attempt=recorded,
                dispatched=True,
                replayed=False,
            )
