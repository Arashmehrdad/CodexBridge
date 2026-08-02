"""Atomic coordination for canonical commands and subordinate worker messages.

The coordinator owns no lifecycle state. It opens the shared SQLite transaction,
asks :class:`TaskStore` to reserve the canonical command, and asks
:class:`WorkerSubstrateStore` to reserve the subordinate message envelope on the
same connection. A crash therefore leaves both records or neither record.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..tasks.models import (
    TERMINAL_TASK_STATES,
    TaskCommand,
    TaskCommandKind,
    TaskCommandStatus,
)
from ..tasks.store import TaskStore
from .models import (
    MessageClass,
    WorkerMessageRecord,
    message_contract_hash,
    normalize_message_contract,
)
from .store import EvidenceConflict, WorkerSubstrateStore


class InteractionStateConflict(ValueError):
    """The requested canonical task state version is no longer current."""


@dataclass(frozen=True)
class InteractionReservation:
    command: TaskCommand
    message: WorkerMessageRecord
    created: bool


class InteractionCoordinator:
    """Reserve one canonical command and one subordinate message atomically."""

    def __init__(self, runs_dir: Path):
        self.task_store = TaskStore(runs_dir)
        self.substrate_store = WorkerSubstrateStore(runs_dir)

    def reserve(
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
        requested_state_version: int,
        message_class: MessageClass = MessageClass.COMMAND,
        checkpoint_id: str = "",
        mandate_ref: str = "",
        mandate_version: str = "",
    ) -> InteractionReservation:
        if command_kind not in {
            TaskCommandKind.STEER,
            TaskCommandKind.SUPPLY_INPUT,
        }:
            raise ValueError("interaction coordinator accepts only steer or supply_input")

        payload_reference = self.substrate_store.put_payload(payload)
        contract = normalize_message_contract(
            project_id=project_id,
            resource_id=resource_id,
            task_id=task_id,
            run_id=run_id,
            session_binding_id=session_binding_id,
            checkpoint_id=checkpoint_id,
            sender_ref=sender_ref,
            recipient_ref=recipient_ref,
            mandate_ref=mandate_ref,
            mandate_version=mandate_version,
            message_class=message_class,
            command_kind=command_kind.value,
            idempotency_key=idempotency_key,
            payload_ref=payload_reference.ref,
            payload_hash=payload_reference.payload_hash,
            payload_bytes=payload_reference.payload_bytes,
            requested_state_version=int(requested_state_version),
        )
        contract_hash = message_contract_hash(contract)

        with self.task_store.transaction() as conn:
            task = self.task_store.get_task_in_connection(conn, task_id)
            if task.state_version != int(requested_state_version):
                raise InteractionStateConflict(
                    f"task {task_id} state version is {task.state_version}, "
                    f"not {requested_state_version}"
                )
            if task.state in TERMINAL_TASK_STATES:
                raise InteractionStateConflict(
                    f"task {task_id} is terminal: {task.state.value}"
                )

            command, command_created = self.task_store.reserve_command_in_connection(
                conn,
                task_id=task_id,
                command_kind=command_kind,
                requested_state_version=int(requested_state_version),
                observed_state_version=task.state_version,
                status=TaskCommandStatus.ACCEPTED,
                controller_request_id=idempotency_key,
            )
            message, message_created = (
                self.substrate_store.reserve_message_in_connection(
                    conn,
                    command_id=command.command_id,
                    project_id=project_id,
                    resource_id=resource_id,
                    task_id=task_id,
                    run_id=run_id,
                    session_binding_id=session_binding_id,
                    checkpoint_id=checkpoint_id,
                    sender_ref=sender_ref,
                    recipient_ref=recipient_ref,
                    mandate_ref=mandate_ref,
                    mandate_version=mandate_version,
                    message_class=message_class,
                    command_kind=command_kind.value,
                    idempotency_key=idempotency_key,
                    payload_ref=payload_reference.ref,
                    payload_hash=payload_reference.payload_hash,
                    payload_bytes=payload_reference.payload_bytes,
                    requested_state_version=int(requested_state_version),
                    contract_hash=contract_hash,
                )
            )
            if command_created != message_created:
                raise EvidenceConflict(
                    "command_message_reservation",
                    idempotency_key,
                    "canonical command and subordinate message existence disagree",
                )

        return InteractionReservation(
            command=command,
            message=message,
            created=command_created,
        )
