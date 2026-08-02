"""Persist-before-send interaction dispatch and recovery interpretation.

This dispatcher owns no durable lifecycle table. It coordinates the canonical
command/message reservation, one durable transport-attempt claim, an injected
provider-neutral transport, and the central acknowledgement-to-resume policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from soma.safety import redact_secret_values
from soma.tasks.models import TaskCommandKind, TaskCommandStatus
from soma.worker_adapters import Capability as ProviderCapability
from soma.worker_adapters import get_adapter

from .coordinator import InteractionCoordinator, InteractionReservation
from .models import (
    MessageClass,
    ProviderSessionBinding,
    TransportAttemptRecord,
    TransportAttemptState,
)
from .store import WorkerSubstrateStore
from .transitions import InteractionTransitionPolicy, ResumeTransitionResult
from .transport import (
    InteractionTransport,
    InteractionTransportOutcomeUnknown,
    InteractionTransportRequest,
    InteractionTransportUnavailable,
    TransportDispatchDisposition,
)


class InteractionCapabilityUnsupported(ValueError):
    """The bound provider adapter does not declare the requested capability."""


class InteractionDispatchUnavailable(ValueError):
    """No reviewed transport can dispatch this exact provider interaction."""


@dataclass(frozen=True)
class InteractionDispatchResult:
    reservation: InteractionReservation
    attempt: TransportAttemptRecord | None
    delivery: str
    reason: str
    evidence_ref: str
    transport_called: bool
    resumed: ResumeTransitionResult | None = None

    @property
    def acknowledged(self) -> bool:
        return self.delivery == TransportAttemptState.ACKNOWLEDGED.value

    @property
    def uncertain(self) -> bool:
        return self.delivery == TransportAttemptState.OUTCOME_UNKNOWN.value


class InteractionDispatcher:
    """Dispatch one exact interaction at most once, with honest crash recovery."""

    def __init__(
        self,
        runs_dir: Path,
        *,
        transport: InteractionTransport,
    ) -> None:
        self.coordinator = InteractionCoordinator(runs_dir)
        self.policy = InteractionTransitionPolicy(runs_dir)
        self.store = WorkerSubstrateStore(runs_dir)
        self.transport = transport

    @staticmethod
    def _required_capability(command_kind: TaskCommandKind) -> ProviderCapability:
        if command_kind is TaskCommandKind.STEER:
            return ProviderCapability.MID_TURN_STEERING
        if command_kind is TaskCommandKind.SUPPLY_INPUT:
            return ProviderCapability.STDIN_PROMPT
        raise ValueError("dispatcher accepts only steer or supply_input")

    def _binding(
        self,
        *,
        session_binding_id: str,
        task_id: str,
        run_id: str,
    ) -> ProviderSessionBinding:
        binding = self.store.get_binding(session_binding_id)
        if binding.task_id != task_id or binding.run_id != run_id:
            raise InteractionDispatchUnavailable(
                "provider-session binding does not match the canonical Task and Run"
            )
        if binding.disposition.value != "bound":
            raise InteractionDispatchUnavailable(
                "provider-session binding is not durably bound"
            )
        return binding

    def _require_capability(
        self,
        binding: ProviderSessionBinding,
        *,
        command_kind: TaskCommandKind,
    ) -> None:
        try:
            adapter = get_adapter(binding.provider)
        except KeyError as exc:
            raise InteractionCapabilityUnsupported(str(exc)) from exc
        capability = self._required_capability(command_kind)
        if not adapter.capabilities.is_supported(capability):
            declaration = adapter.capabilities.declarations[capability]
            raise InteractionCapabilityUnsupported(
                f"provider {binding.provider!r} does not support "
                f"{capability.value}: {declaration.support.value}; "
                f"{declaration.evidence}"
            )
        if not self.transport.supports(binding, command_kind=command_kind.value):
            raise InteractionDispatchUnavailable(
                "No reviewed interaction transport is active for the bound provider "
                f"and command {command_kind.value!r}"
            )

    def _repair_existing_attempt(
        self,
        reservation: InteractionReservation,
        attempt: TransportAttemptRecord,
        *,
        expected_task_state_version: int,
        expected_run_state_version: int,
    ) -> InteractionDispatchResult:
        if attempt.state is TransportAttemptState.CLAIMED:
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=(
                    "prior transport claim is unresolved; automatic resend is "
                    "forbidden until evidence or recovery adjudication resolves it"
                ),
                evidence_ref=attempt.evidence_ref,
                transport_called=False,
            )
        if attempt.state is TransportAttemptState.OUTCOME_UNKNOWN:
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=False,
            )
        if attempt.state is TransportAttemptState.ACKNOWLEDGED:
            resumed = None
            if reservation.command.command_kind is TaskCommandKind.SUPPLY_INPUT:
                resumed = self.policy.resume_after_acknowledgement(
                    message_id=reservation.message.message_id,
                    expected_task_state_version=expected_task_state_version,
                    expected_run_state_version=expected_run_state_version,
                )
            else:
                self.coordinator.task_store.complete_command(
                    reservation.command.command_id,
                    status=TaskCommandStatus.COMPLETED,
                    reason="steering acknowledgement already durable",
                )
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=False,
                resumed=resumed,
            )
        if attempt.state in {
            TransportAttemptState.REJECTED,
            TransportAttemptState.PREVENTED,
        }:
            self.coordinator.task_store.complete_command(
                reservation.command.command_id,
                status=TaskCommandStatus.FAILED,
                reason=attempt.reason or attempt.state.value,
            )
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=False,
            )
        raise RuntimeError(f"Unhandled transport attempt state: {attempt.state.value}")

    def dispatch(
        self,
        *,
        project_id: str,
        resource_id: str,
        task_id: str,
        run_id: str,
        session_binding_id: str,
        command_kind: TaskCommandKind,
        idempotency_key: str,
        sender_ref: str,
        recipient_ref: str,
        payload: bytes | str,
        requested_task_state_version: int,
        expected_run_state_version: int,
        message_class: MessageClass = MessageClass.COMMAND,
        checkpoint_id: str = "",
        mandate_ref: str = "",
        mandate_version: str = "",
    ) -> InteractionDispatchResult:
        binding = self._binding(
            session_binding_id=session_binding_id,
            task_id=task_id,
            run_id=run_id,
        )
        self._require_capability(binding, command_kind=command_kind)

        reservation = self.coordinator.reserve(
            project_id=project_id,
            resource_id=resource_id,
            task_id=task_id,
            run_id=run_id,
            session_binding_id=session_binding_id,
            command_kind=command_kind,
            idempotency_key=idempotency_key,
            sender_ref=sender_ref,
            recipient_ref=recipient_ref,
            payload=payload,
            requested_state_version=requested_task_state_version,
            message_class=message_class,
            checkpoint_id=checkpoint_id,
            mandate_ref=mandate_ref,
            mandate_version=mandate_version,
        )

        attempt, attempt_created = self.store.claim_transport_attempt(
            reservation.message.message_id,
            claimer_id=self.transport.claimer_id,
        )
        if not attempt_created:
            return self._repair_existing_attempt(
                reservation,
                attempt,
                expected_task_state_version=requested_task_state_version,
                expected_run_state_version=expected_run_state_version,
            )

        request = InteractionTransportRequest(
            message_id=reservation.message.message_id,
            attempt_id=attempt.attempt_id,
            command_kind=reservation.message.command_kind,
            message_class=reservation.message.message_class.value,
            session_binding_id=binding.session_binding_id,
            provider=binding.provider,
            native_session_id=binding.native_session_id,
            payload_ref=reservation.message.payload_ref,
            payload_hash=reservation.message.payload_hash,
            payload_bytes=reservation.message.payload_bytes,
            checkpoint_id=reservation.message.checkpoint_id,
        )

        try:
            result = self.transport.dispatch(request)
        except (InteractionTransportOutcomeUnknown, InteractionTransportUnavailable):
            attempt = self.store.record_transport_attempt(
                attempt.attempt_id,
                state=TransportAttemptState.OUTCOME_UNKNOWN,
                reason="transport outcome cannot be proven; resend forbidden",
            )
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=True,
            )
        except Exception as exc:  # noqa: BLE001 - uncertainty is the safe outcome
            attempt = self.store.record_transport_attempt(
                attempt.attempt_id,
                state=TransportAttemptState.OUTCOME_UNKNOWN,
                reason=(
                    "transport raised after durable claim; outcome cannot be proven "
                    f"({redact_secret_values(type(exc).__name__)})"
                ),
            )
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=True,
            )

        reason = redact_secret_values(result.reason)[:512]
        evidence_ref = redact_secret_values(result.evidence_ref)[:2048]

        if result.disposition is TransportDispatchDisposition.ACKNOWLEDGED:
            if not evidence_ref:
                attempt = self.store.record_transport_attempt(
                    attempt.attempt_id,
                    state=TransportAttemptState.OUTCOME_UNKNOWN,
                    reason="transport acknowledgement omitted durable evidence identity",
                )
                return InteractionDispatchResult(
                    reservation=reservation,
                    attempt=attempt,
                    delivery=attempt.state.value,
                    reason=attempt.reason,
                    evidence_ref="",
                    transport_called=True,
                )
            attempt = self.store.record_transport_attempt(
                attempt.attempt_id,
                state=TransportAttemptState.ACKNOWLEDGED,
                reason=reason,
                evidence_ref=evidence_ref,
            )
            resumed = None
            if command_kind is TaskCommandKind.SUPPLY_INPUT:
                resumed = self.policy.resume_after_acknowledgement(
                    message_id=reservation.message.message_id,
                    expected_task_state_version=requested_task_state_version,
                    expected_run_state_version=expected_run_state_version,
                )
            else:
                self.coordinator.task_store.complete_command(
                    reservation.command.command_id,
                    status=TaskCommandStatus.COMPLETED,
                    reason=reason or "steering acknowledged",
                )
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=True,
                resumed=resumed,
            )

        if result.disposition is TransportDispatchDisposition.REJECTED:
            attempt = self.store.record_transport_attempt(
                attempt.attempt_id,
                state=TransportAttemptState.REJECTED,
                reason=reason,
                evidence_ref=evidence_ref,
            )
            self.coordinator.task_store.complete_command(
                reservation.command.command_id,
                status=TaskCommandStatus.FAILED,
                reason=reason or "interaction rejected",
            )
            return InteractionDispatchResult(
                reservation=reservation,
                attempt=attempt,
                delivery=attempt.state.value,
                reason=attempt.reason,
                evidence_ref=attempt.evidence_ref,
                transport_called=True,
            )

        attempt = self.store.record_transport_attempt(
            attempt.attempt_id,
            state=TransportAttemptState.OUTCOME_UNKNOWN,
            reason=reason or "transport outcome cannot be proven",
            evidence_ref=evidence_ref,
        )
        return InteractionDispatchResult(
            reservation=reservation,
            attempt=attempt,
            delivery=attempt.state.value,
            reason=attempt.reason,
            evidence_ref=attempt.evidence_ref,
            transport_called=True,
        )
