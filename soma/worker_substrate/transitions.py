"""Central canonical wait/resume transition policy for interactive work.

This module owns no durable table. It coordinates the existing canonical Task,
Run, ProjectScope, checkpoint, session, and subordinate deadline authorities in
one shared SQLite transaction. Ordinary callers must not reproduce these state
interpretations independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from soma.run_store import RunStore, TERMINAL_STATUSES
from soma.tasks.models import (
    TaskCheckpoint,
    TaskCheckpointStatus,
    TaskCommand,
    TaskCommandKind,
    TaskCommandStatus,
    TaskEventLevel,
    TaskPhase,
    TaskRecord,
    TaskRecoveryState,
    TaskState,
    checkpoint_id_for_request,
    utc_now,
)
from soma.tasks.store import TaskStore

from .models import (
    CheckpointDeadline,
    CheckpointDeadlinePolicy,
    CheckpointExpiryDisposition,
    CheckpointExpiryEvent,
    CheckpointRecoveryWindow,
    MessageClass,
    MessageDisposition,
    TransportAttemptState,
    canonical_json,
    require_opaque,
)
from .store import CanonicalBindingMismatch, EvidenceConflict, WorkerSubstrateStore


WAIT_CONTRACT_REFERENCE_PREFIX = "worker_wait_contract:"
WAIT_CONTRACT_VERSION = "worker_wait.v1"


class ResumeTransitionConflict(ValueError):
    """Acknowledged input cannot safely resume the canonical execution."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class WaitTransitionConflict(ValueError):
    """The requested wait transition conflicts with canonical durable state."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ExpiryTransitionConflict(ValueError):
    """An expired checkpoint cannot enter the canonical cancellation path."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ResumeTransitionResult:
    task: TaskRecord
    run: dict[str, Any]
    checkpoint: TaskCheckpoint
    message_id: str
    attempt_id: str
    acknowledgement_evidence_ref: str
    created: bool


@dataclass(frozen=True)
class WaitTransitionResult:
    task: TaskRecord
    run: dict[str, Any]
    checkpoint: TaskCheckpoint
    deadline: CheckpointDeadline
    contract_hash: str
    created: bool


@dataclass(frozen=True)
class ExpiryTransitionResult:
    task: TaskRecord
    run: dict[str, Any]
    checkpoint: TaskCheckpoint
    deadline: CheckpointDeadline
    expiry: CheckpointExpiryEvent
    command: TaskCommand
    recovery_window: CheckpointRecoveryWindow
    created: bool


class InteractionTransitionPolicy:
    """Apply one central, atomic non-terminal controller-wait transition."""

    def __init__(self, runs_dir: Path):
        self.task_store = TaskStore(runs_dir)
        self.run_store = RunStore(runs_dir)
        self.substrate_store = WorkerSubstrateStore(runs_dir)

    @staticmethod
    def _parse_timestamp(value: str, field: str) -> datetime:
        if not value:
            raise ValueError(f"{field} is required")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{field} must include a timezone")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _contract_hash(contract: dict[str, Any]) -> str:
        return sha256(canonical_json(contract).encode("utf-8")).hexdigest()

    @staticmethod
    def _checkpoint_from_row(row: Any) -> TaskCheckpoint:
        data = dict(row)
        import json

        raw_schema = data.pop("expected_input_schema_json", "{}")
        decoded = json.loads(raw_schema or "{}")
        data["expected_input_schema"] = (
            decoded if isinstance(decoded, dict) else {}
        )
        return TaskCheckpoint.model_validate(data)

    def enter_waiting(
        self,
        *,
        project_id: str,
        resource_id: str,
        task_id: str,
        run_id: str,
        session_binding_id: str,
        idempotency_key: str,
        expected_task_state_version: int,
        expected_run_state_version: int,
        deadline_at: str,
        policy_owner: str,
        prompt: str = "",
        expected_input_schema: dict[str, Any] | None = None,
        context_ref: str = "",
    ) -> WaitTransitionResult:
        for value, field in (
            (project_id, "project_id"),
            (resource_id, "resource_id"),
            (task_id, "task_id"),
            (run_id, "run_id"),
            (session_binding_id, "session_binding_id"),
            (idempotency_key, "idempotency_key"),
            (policy_owner, "policy_owner"),
        ):
            require_opaque(value, field)
        if int(expected_task_state_version) < 0:
            raise ValueError("expected_task_state_version must be non-negative")
        if int(expected_run_state_version) < 0:
            raise ValueError("expected_run_state_version must be non-negative")

        parsed_deadline = self._parse_timestamp(deadline_at, "deadline_at")
        checkpoint_id = checkpoint_id_for_request(task_id, idempotency_key)
        schema = dict(expected_input_schema or {})
        contract = {
            "contract_version": WAIT_CONTRACT_VERSION,
            "project_id": project_id,
            "resource_id": resource_id,
            "task_id": task_id,
            "run_id": run_id,
            "session_binding_id": session_binding_id,
            "checkpoint_id": checkpoint_id,
            "idempotency_key": idempotency_key,
            "expected_task_state_version": int(expected_task_state_version),
            "expected_run_state_version": int(expected_run_state_version),
            "deadline_at": deadline_at,
            "policy_owner": policy_owner,
            "prompt": prompt,
            "expected_input_schema": schema,
            "context_ref": context_ref,
        }
        contract_hash = self._contract_hash(contract)
        evidence_ref = f"{WAIT_CONTRACT_REFERENCE_PREFIX}{contract_hash}"
        transition_at = utc_now()
        transition_time = self._parse_timestamp(transition_at, "transition_at")

        with self.task_store.transaction() as conn:
            self.substrate_store._require_canonical_task_run_scope(
                conn,
                project_id=project_id,
                resource_id=resource_id,
                task_id=task_id,
                run_id=run_id,
            )
            self.substrate_store._require_binding_identity(
                conn,
                session_binding_id,
                task_id=task_id,
                run_id=run_id,
            )

            task = self.task_store.get_task_in_connection(conn, task_id)
            run = self.run_store.get_run_in_connection(conn, run_id)
            checkpoint_row = conn.execute(
                "SELECT * FROM task_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()

            if checkpoint_row is not None:
                checkpoint = self._checkpoint_from_row(checkpoint_row)
                deadline_row = conn.execute(
                    "SELECT * FROM worker_checkpoint_deadlines "
                    "WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                ).fetchone()
                if deadline_row is None:
                    raise EvidenceConflict(
                        "controller_wait",
                        checkpoint_id,
                        "checkpoint exists without its durable deadline",
                    )
                deadline = CheckpointDeadline.model_validate(dict(deadline_row))
                replay_ok = all(
                    (
                        checkpoint.task_id == task_id,
                        checkpoint.kind == "controller_input",
                        checkpoint.prompt == prompt,
                        checkpoint.expected_input_schema == schema,
                        checkpoint.context_ref == context_ref,
                        checkpoint.evidence_ref == evidence_ref,
                        checkpoint.required_state_version
                        == int(expected_task_state_version) + 1,
                        checkpoint.status is TaskCheckpointStatus.OPEN,
                        deadline.task_id == task_id,
                        deadline.session_binding_id == session_binding_id,
                        deadline.deadline_policy
                        is CheckpointDeadlinePolicy.BOUNDED,
                        deadline.deadline_at == deadline_at,
                        deadline.policy_owner == policy_owner,
                        task.state is TaskState.AWAITING_CONTROLLER,
                        task.phase is TaskPhase.AWAITING_CONTROLLER,
                        task.checkpoint_ref == checkpoint_id,
                        run["status"] == "awaiting_controller",
                        run["current_phase"] == "awaiting_controller",
                        bool(run["requires_human"]),
                        run["ended_at"] is None,
                    )
                )
                if not replay_ok:
                    raise WaitTransitionConflict(
                        "idempotent wait replay conflicts with durable state"
                    )
                return WaitTransitionResult(
                    task=task,
                    run=run,
                    checkpoint=checkpoint,
                    deadline=deadline,
                    contract_hash=contract_hash,
                    created=False,
                )

            if parsed_deadline <= transition_time:
                raise WaitTransitionConflict(
                    "new controller wait deadline must be in the future"
                )
            if task.backend_ref != run_id:
                raise CanonicalBindingMismatch(
                    "canonical task backend does not match the requested run"
                )
            if task.state is not TaskState.RUNNING:
                raise WaitTransitionConflict(
                    f"task must be running, not {task.state.value}"
                )
            if int(task.state_version) != int(expected_task_state_version):
                raise WaitTransitionConflict(
                    "task state version changed before controller wait"
                )
            if run["status"] != "running":
                raise WaitTransitionConflict(
                    f"run must be running, not {run['status']}"
                )
            if run["status"] in TERMINAL_STATUSES:
                raise WaitTransitionConflict("terminal runs cannot enter controller wait")
            if int(run["state_version"]) != int(expected_run_state_version):
                raise WaitTransitionConflict(
                    "run state version changed before controller wait"
                )
            if run["ended_at"] is not None:
                raise WaitTransitionConflict(
                    "a run with ended_at cannot enter non-terminal waiting"
                )
            if run["result"]:
                raise WaitTransitionConflict(
                    "a run with terminal result evidence cannot enter waiting"
                )
            if run["result_publication_status"] != "not_published":
                raise WaitTransitionConflict(
                    "a run with result-publication state cannot enter waiting"
                )
            open_checkpoint = conn.execute(
                "SELECT checkpoint_id FROM task_checkpoints "
                "WHERE task_id = ? AND status = 'open' LIMIT 1",
                (task_id,),
            ).fetchone()
            if open_checkpoint is not None:
                raise WaitTransitionConflict(
                    "task already has a different open checkpoint"
                )

            checkpoint = self.task_store.create_checkpoint_in_connection(
                conn,
                task_id,
                checkpoint_id=checkpoint_id,
                kind="controller_input",
                required_state_version=int(expected_task_state_version) + 1,
                prompt=prompt,
                expected_input_schema=schema,
                context_ref=context_ref,
                evidence_ref=evidence_ref,
                created_at=transition_at,
            )
            deadline = self.substrate_store.set_checkpoint_deadline_in_connection(
                conn,
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                deadline_policy=CheckpointDeadlinePolicy.BOUNDED,
                deadline_at=deadline_at,
                policy_owner=policy_owner,
                session_binding_id=session_binding_id,
                created_at=transition_at,
            )

            updated_task = self.task_store.conditional_update_in_connection(
                conn,
                task_id,
                fields={
                    "state": TaskState.AWAITING_CONTROLLER.value,
                    "phase": TaskPhase.AWAITING_CONTROLLER.value,
                    "checkpoint_ref": checkpoint_id,
                },
                expected_state_version=int(expected_task_state_version),
                expected_states=(TaskState.RUNNING.value,),
            )
            if updated_task is None:
                raise WaitTransitionConflict(
                    "task changed during controller-wait transition"
                )

            updated_run = self.run_store.conditional_update_in_connection(
                conn,
                run_id,
                fields={
                    "status": "awaiting_controller",
                    "current_phase": "awaiting_controller",
                    "requires_human": True,
                    "heartbeat_at": transition_at,
                    "ended_at": None,
                },
                expected_statuses=("running",),
                expected_state_version=int(expected_run_state_version),
                reject_terminal=True,
            )
            if updated_run is None:
                raise WaitTransitionConflict(
                    "run changed during controller-wait transition"
                )

            event_data = {
                "checkpoint_id": checkpoint_id,
                "session_binding_id": session_binding_id,
                "deadline_at": deadline_at,
                "contract_hash": contract_hash,
            }
            self.task_store.append_event_in_connection(
                conn,
                task_id,
                level=TaskEventLevel.INFO,
                stage="awaiting_controller",
                message="Task entered non-terminal controller wait",
                state=TaskState.AWAITING_CONTROLLER.value,
                state_version=updated_task.state_version,
                data=event_data,
                timestamp=transition_at,
            )
            self.run_store.append_event_in_connection(
                conn,
                run_id,
                level="info",
                stage="awaiting_controller",
                message="Run entered non-terminal controller wait",
                data=event_data,
                timestamp=transition_at,
            )

        return WaitTransitionResult(
            task=updated_task,
            run=updated_run,
            checkpoint=checkpoint,
            deadline=deadline,
            contract_hash=contract_hash,
            created=True,
        )

    @staticmethod
    def _classify_expiry_window(
        conn: Any,
        *,
        checkpoint: TaskCheckpoint,
        run: dict[str, Any],
        expiry_exists: bool,
    ) -> CheckpointRecoveryWindow:
        if (
            checkpoint.status is TaskCheckpointStatus.RESOLVED
            and run["status"] == "awaiting_controller"
        ):
            return CheckpointRecoveryWindow.RESOLVED_BEFORE_RUN_RESUME

        rows = conn.execute(
            "SELECT m.disposition, a.attempt_state FROM worker_messages m "
            "LEFT JOIN worker_transport_attempts a ON a.message_id = m.message_id "
            "WHERE m.checkpoint_id = ? "
            "ORDER BY m.created_at ASC, m.message_id ASC",
            (checkpoint.checkpoint_id,),
        ).fetchall()
        if not rows:
            return CheckpointRecoveryWindow.NO_INPUT_RESERVED

        attempt_states = {
            str(row["attempt_state"])
            for row in rows
            if row["attempt_state"] is not None
        }
        if TransportAttemptState.OUTCOME_UNKNOWN.value in attempt_states:
            return CheckpointRecoveryWindow.OUTCOME_UNKNOWN
        if TransportAttemptState.CLAIMED.value in attempt_states:
            return (
                CheckpointRecoveryWindow.UNRESOLVED_CLAIM
                if expiry_exists
                else CheckpointRecoveryWindow.IN_FLIGHT_AT_EXPIRY
            )
        if TransportAttemptState.ACKNOWLEDGED.value in attempt_states:
            return CheckpointRecoveryWindow.ACKNOWLEDGED_BEFORE_RESUME

        dispositions = {str(row["disposition"]) for row in rows}
        if dispositions & {
            MessageDisposition.RESERVED.value,
            MessageDisposition.EXPIRED.value,
        }:
            return CheckpointRecoveryWindow.PENDING_NEVER_ATTEMPTED
        return CheckpointRecoveryWindow.REJECTED_BEFORE_EXPIRY

    def expire_checkpoint(
        self,
        *,
        project_id: str,
        resource_id: str,
        task_id: str,
        run_id: str,
        session_binding_id: str,
        checkpoint_id: str,
        idempotency_key: str,
        expected_task_state_version: int,
        expected_run_state_version: int,
        observed_at: str,
        reason: str = "",
        quiescence_proof_ref: str = "",
    ) -> ExpiryTransitionResult:
        """Atomically expire one checkpoint and reserve canonical cancellation."""
        for value, field in (
            (project_id, "project_id"),
            (resource_id, "resource_id"),
            (task_id, "task_id"),
            (run_id, "run_id"),
            (session_binding_id, "session_binding_id"),
            (checkpoint_id, "checkpoint_id"),
            (idempotency_key, "idempotency_key"),
        ):
            require_opaque(value, field)
        observed_time = self._parse_timestamp(observed_at, "observed_at")
        transition_at = utc_now()
        cancel_request_id = (
            f"checkpoint_expiry:{checkpoint_id}:{idempotency_key}"
        )

        with self.task_store.transaction() as conn:
            self.substrate_store._require_canonical_task_run_scope(
                conn,
                project_id=project_id,
                resource_id=resource_id,
                task_id=task_id,
                run_id=run_id,
            )
            binding = self.substrate_store._require_binding_identity(
                conn,
                session_binding_id,
                task_id=task_id,
                run_id=run_id,
            )
            if str(binding["disposition"]) != "bound":
                raise ExpiryTransitionConflict(
                    "provider session binding is not durably bound"
                )

            task = self.task_store.get_task_in_connection(conn, task_id)
            run = self.run_store.get_run_in_connection(conn, run_id)
            checkpoint = self.task_store.get_checkpoint_in_connection(
                conn, checkpoint_id
            )
            deadline_row = conn.execute(
                "SELECT * FROM worker_checkpoint_deadlines "
                "WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
            if deadline_row is None:
                raise EvidenceConflict(
                    "checkpoint_expiry",
                    checkpoint_id,
                    "checkpoint has no durable deadline",
                )
            deadline = CheckpointDeadline.model_validate(dict(deadline_row))
            if deadline.task_id != task_id:
                raise CanonicalBindingMismatch(
                    "checkpoint deadline does not belong to the submitted task"
                )
            if deadline.session_binding_id != session_binding_id:
                raise CanonicalBindingMismatch(
                    "checkpoint deadline session does not match the binding"
                )
            if deadline.deadline_policy is not CheckpointDeadlinePolicy.BOUNDED:
                raise ExpiryTransitionConflict(
                    "checkpoint has no bounded deadline to expire"
                )
            deadline_time = self._parse_timestamp(
                deadline.deadline_at, "deadline_at"
            )
            if observed_time < deadline_time:
                raise ExpiryTransitionConflict(
                    "checkpoint deadline has not elapsed"
                )

            expiry_row = conn.execute(
                "SELECT * FROM worker_checkpoint_expiries "
                "WHERE checkpoint_id = ? AND idempotency_key = ?",
                (checkpoint_id, idempotency_key),
            ).fetchone()
            expiry_exists = expiry_row is not None
            recovery_window = self._classify_expiry_window(
                conn,
                checkpoint=checkpoint,
                run=run,
                expiry_exists=expiry_exists,
            )

            if expiry_exists:
                expiry = CheckpointExpiryEvent.model_validate(dict(expiry_row))
                command = self.task_store.find_command_by_controller_request_in_connection(
                    conn,
                    task_id=task_id,
                    command_kind=TaskCommandKind.CANCEL,
                    controller_request_id=cancel_request_id,
                )
                if command is None:
                    raise EvidenceConflict(
                        "checkpoint_expiry",
                        checkpoint_id,
                        "expiry exists without its canonical cancel command",
                    )
                return ExpiryTransitionResult(
                    task=task,
                    run=run,
                    checkpoint=checkpoint,
                    deadline=deadline,
                    expiry=expiry,
                    command=command,
                    recovery_window=recovery_window,
                    created=False,
                )

            if task.backend_ref != run_id:
                raise CanonicalBindingMismatch(
                    "canonical task backend does not match the requested run"
                )
            if task.state is not TaskState.AWAITING_CONTROLLER:
                raise ExpiryTransitionConflict(
                    f"task is {task.state.value}, not awaiting_controller"
                )
            if task.phase is not TaskPhase.AWAITING_CONTROLLER:
                raise ExpiryTransitionConflict(
                    "task phase is not awaiting_controller"
                )
            if int(task.state_version) != int(expected_task_state_version):
                raise ExpiryTransitionConflict(
                    "task state version changed before checkpoint expiry"
                )
            if task.checkpoint_ref != checkpoint_id:
                raise ExpiryTransitionConflict(
                    "task checkpoint does not match the expiry request"
                )
            if checkpoint.task_id != task_id:
                raise CanonicalBindingMismatch(
                    "checkpoint does not belong to the submitted task"
                )
            if checkpoint.status not in {
                TaskCheckpointStatus.OPEN,
                TaskCheckpointStatus.RESOLVED,
            }:
                raise ExpiryTransitionConflict(
                    f"checkpoint is {checkpoint.status.value}, not expirable"
                )
            if checkpoint.required_state_version != task.state_version:
                raise ExpiryTransitionConflict(
                    "checkpoint required state version is stale"
                )
            if run["status"] != "awaiting_controller":
                raise ExpiryTransitionConflict(
                    f"run is {run['status']}, not awaiting_controller"
                )
            if run["current_phase"] != "awaiting_controller":
                raise ExpiryTransitionConflict(
                    "run phase is not awaiting_controller"
                )
            if int(run["state_version"]) != int(expected_run_state_version):
                raise ExpiryTransitionConflict(
                    "run state version changed before checkpoint expiry"
                )
            if run["ended_at"] is not None or run["result"]:
                raise ExpiryTransitionConflict(
                    "terminal run evidence forbids checkpoint expiry transition"
                )
            if run["result_publication_status"] != "not_published":
                raise ExpiryTransitionConflict(
                    "result publication state forbids checkpoint expiry transition"
                )

            uncertain_windows = {
                CheckpointRecoveryWindow.IN_FLIGHT_AT_EXPIRY,
                CheckpointRecoveryWindow.OUTCOME_UNKNOWN,
                CheckpointRecoveryWindow.ACKNOWLEDGED_BEFORE_RESUME,
                CheckpointRecoveryWindow.RESOLVED_BEFORE_RUN_RESUME,
            }
            disposition = (
                CheckpointExpiryDisposition.QUIESCENT_CONFIRMED
                if quiescence_proof_ref
                else (
                    CheckpointExpiryDisposition.UNCERTAIN
                    if recovery_window in uncertain_windows
                    else CheckpointExpiryDisposition.RECORDED
                )
            )
            expiry, created = self.substrate_store.record_checkpoint_expiry_in_connection(
                conn,
                checkpoint_id=checkpoint_id,
                task_id=task_id,
                idempotency_key=idempotency_key,
                deadline_at=deadline.deadline_at,
                observed_at=observed_at,
                disposition=disposition,
                quiescence_proof_ref=quiescence_proof_ref,
                reason=reason or "controller-input checkpoint deadline expired",
                created_at=transition_at,
            )
            if not created:
                raise EvidenceConflict(
                    "checkpoint_expiry",
                    checkpoint_id,
                    "expiry appeared during its atomic transition",
                )

            if checkpoint.status is TaskCheckpointStatus.OPEN:
                checkpoint = self.task_store.cancel_checkpoint_in_connection(
                    conn,
                    checkpoint_id,
                    task_id=task_id,
                    required_state_version=task.state_version,
                    cancelled_at=transition_at,
                )
            conn.execute(
                "UPDATE worker_messages SET disposition = ?, "
                "disposition_reason = ?, updated_at = ? "
                "WHERE checkpoint_id = ? AND disposition = ?",
                (
                    MessageDisposition.EXPIRED.value,
                    "checkpoint expired before terminal transport evidence",
                    transition_at,
                    checkpoint_id,
                    MessageDisposition.RESERVED.value,
                ),
            )

            command, command_created = self.task_store.reserve_command_in_connection(
                conn,
                task_id=task_id,
                command_kind=TaskCommandKind.CANCEL,
                requested_state_version=task.state_version,
                observed_state_version=task.state_version,
                status=TaskCommandStatus.ACCEPTED,
                controller_request_id=cancel_request_id,
                reason=(
                    "checkpoint expired; canonical backend cancellation required "
                    f"({recovery_window.value})"
                ),
            )
            if not command_created:
                raise EvidenceConflict(
                    "checkpoint_expiry",
                    checkpoint_id,
                    "cancel command appeared during its atomic transition",
                )

            updated_task = self.task_store.conditional_update_in_connection(
                conn,
                task_id,
                fields={
                    "state": TaskState.CANCELLATION_PENDING.value,
                    "phase": TaskPhase.CANCELLATION_REQUESTED.value,
                    "recovery_state": TaskRecoveryState.PENDING.value,
                    "recovery_reason": (
                        f"checkpoint_expired:{recovery_window.value}"
                    ),
                },
                expected_state_version=task.state_version,
                expected_states=(TaskState.AWAITING_CONTROLLER.value,),
            )
            if updated_task is None:
                raise ExpiryTransitionConflict(
                    "task changed during checkpoint expiry transition"
                )

            event_data = {
                "checkpoint_id": checkpoint_id,
                "expiry_id": expiry.expiry_id,
                "command_id": command.command_id,
                "deadline_at": deadline.deadline_at,
                "observed_at": observed_at,
                "recovery_window": recovery_window.value,
                "quiescence_proof_ref": quiescence_proof_ref,
            }
            self.task_store.append_event_in_connection(
                conn,
                task_id,
                level=TaskEventLevel.WARNING,
                stage="checkpoint_expired",
                message="Controller checkpoint expired; cancellation reserved",
                state=updated_task.state.value,
                state_version=updated_task.state_version,
                data=event_data,
                timestamp=transition_at,
            )
            self.run_store.append_event_in_connection(
                conn,
                run_id,
                level="warning",
                stage="checkpoint_expired",
                message="Controller checkpoint expired; awaiting backend cancellation",
                data=event_data,
                timestamp=transition_at,
            )

        return ExpiryTransitionResult(
            task=updated_task,
            run=run,
            checkpoint=checkpoint,
            deadline=deadline,
            expiry=expiry,
            command=command,
            recovery_window=recovery_window,
            created=True,
        )

    def resume_after_acknowledgement(
        self,
        *,
        message_id: str,
        expected_task_state_version: int,
        expected_run_state_version: int,
    ) -> ResumeTransitionResult:
        """Resume one exact wait after durable, evidence-bearing input acceptance."""
        require_opaque(message_id, "message_id")
        if int(expected_task_state_version) < 0:
            raise ValueError("expected_task_state_version must be non-negative")
        if int(expected_run_state_version) < 0:
            raise ValueError("expected_run_state_version must be non-negative")
        transition_at = utc_now()
        transition_time = self._parse_timestamp(transition_at, "transition_at")

        with self.task_store.transaction() as conn:
            message_row = conn.execute(
                "SELECT * FROM worker_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            if message_row is None:
                raise KeyError(f"Worker message not found: {message_id}")
            message = self.substrate_store._row_to_message(message_row)
            if message.command_kind != "supply_input":
                raise ResumeTransitionConflict(
                    "only an acknowledged supply_input command may resolve a checkpoint"
                )
            if message.message_class not in {
                MessageClass.COMMAND,
                MessageClass.DECISION,
            }:
                raise ResumeTransitionConflict(
                    "informational message classes cannot resume canonical work"
                )
            if not message.checkpoint_id:
                raise ResumeTransitionConflict(
                    "supply_input message has no exact checkpoint identity"
                )
            if message.disposition is not MessageDisposition.ACKNOWLEDGED:
                raise ResumeTransitionConflict(
                    f"message is {message.disposition.value}, not acknowledged"
                )

            attempt_row = conn.execute(
                "SELECT * FROM worker_transport_attempts WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            if attempt_row is None:
                raise ResumeTransitionConflict(
                    "acknowledged message has no durable transport attempt"
                )
            attempt = self.substrate_store._row_to_attempt(attempt_row)
            if attempt.state is not TransportAttemptState.ACKNOWLEDGED:
                raise ResumeTransitionConflict(
                    f"transport attempt is {attempt.state.value}, not acknowledged"
                )
            if not attempt.evidence_ref:
                raise ResumeTransitionConflict(
                    "acknowledgement has no durable evidence reference"
                )

            self.substrate_store._require_canonical_task_run_scope(
                conn,
                project_id=message.project_id,
                resource_id=message.resource_id,
                task_id=message.task_id,
                run_id=message.run_id,
            )
            binding = self.substrate_store._require_binding_identity(
                conn,
                message.session_binding_id,
                task_id=message.task_id,
                run_id=message.run_id,
            )
            if str(binding["disposition"]) != "bound":
                raise ResumeTransitionConflict(
                    "provider session binding is not durably bound"
                )

            task = self.task_store.get_task_in_connection(conn, message.task_id)
            run = self.run_store.get_run_in_connection(conn, message.run_id)
            checkpoint = self.task_store.get_checkpoint_in_connection(
                conn, message.checkpoint_id
            )
            command_row = conn.execute(
                "SELECT * FROM task_commands WHERE command_id = ?",
                (message.command_id,),
            ).fetchone()
            if command_row is None:
                raise CanonicalBindingMismatch(
                    f"canonical command not found: {message.command_id}"
                )
            command_status = str(command_row["status"])

            if (
                checkpoint.status is TaskCheckpointStatus.RESOLVED
                and task.state is TaskState.RUNNING
                and task.phase is TaskPhase.BACKEND_RUNNING
                and not task.checkpoint_ref
                and run["status"] == "running"
                and run["current_phase"] == "backend_running"
                and not bool(run["requires_human"])
                and command_status == TaskCommandStatus.COMPLETED.value
            ):
                event_row = conn.execute(
                    "SELECT 1 FROM task_events WHERE task_id = ? "
                    "AND stage = 'controller_resumed' "
                    "AND json_extract(data_json, '$.message_id') = ? LIMIT 1",
                    (message.task_id, message_id),
                ).fetchone()
                if event_row is None:
                    raise EvidenceConflict(
                        "controller_resume",
                        message_id,
                        "canonical state is resumed without its exact event evidence",
                    )
                return ResumeTransitionResult(
                    task=task,
                    run=run,
                    checkpoint=checkpoint,
                    message_id=message_id,
                    attempt_id=attempt.attempt_id,
                    acknowledgement_evidence_ref=attempt.evidence_ref,
                    created=False,
                )

            if task.state is not TaskState.AWAITING_CONTROLLER:
                raise ResumeTransitionConflict(
                    f"task is {task.state.value}, not awaiting_controller"
                )
            if task.phase is not TaskPhase.AWAITING_CONTROLLER:
                raise ResumeTransitionConflict(
                    "task phase is not awaiting_controller"
                )
            if int(task.state_version) != int(expected_task_state_version):
                raise ResumeTransitionConflict(
                    "task state version changed before acknowledged resume"
                )
            if task.checkpoint_ref != message.checkpoint_id:
                raise ResumeTransitionConflict(
                    "task checkpoint does not match acknowledged input"
                )
            if run["status"] != "awaiting_controller":
                raise ResumeTransitionConflict(
                    f"run is {run['status']}, not awaiting_controller"
                )
            if run["current_phase"] != "awaiting_controller":
                raise ResumeTransitionConflict(
                    "run phase is not awaiting_controller"
                )
            if int(run["state_version"]) != int(expected_run_state_version):
                raise ResumeTransitionConflict(
                    "run state version changed before acknowledged resume"
                )
            if not bool(run["requires_human"]):
                raise ResumeTransitionConflict(
                    "run no longer projects a controller-input wait"
                )
            if run["ended_at"] is not None or run["result"]:
                raise ResumeTransitionConflict(
                    "terminal run evidence forbids non-terminal resume"
                )
            if run["result_publication_status"] != "not_published":
                raise ResumeTransitionConflict(
                    "result publication state forbids non-terminal resume"
                )
            if not str(run["worker_lease_token"] or ""):
                raise ResumeTransitionConflict(
                    "run has no canonical worker lease token"
                )
            if int(run["lease_generation"] or 0) < 1:
                raise ResumeTransitionConflict(
                    "run has no canonical worker lease generation"
                )
            if int(run["worker_pid"] or 0) <= 0 or not str(
                run["worker_identity"] or ""
            ):
                raise ResumeTransitionConflict(
                    "run has no PID-reuse-resistant worker identity"
                )
            if checkpoint.task_id != message.task_id:
                raise CanonicalBindingMismatch(
                    "checkpoint does not belong to acknowledged task"
                )
            if checkpoint.status is not TaskCheckpointStatus.OPEN:
                raise ResumeTransitionConflict(
                    f"checkpoint is {checkpoint.status.value}, not open"
                )
            if checkpoint.required_state_version != task.state_version:
                raise ResumeTransitionConflict(
                    "checkpoint required state version is stale"
                )
            if message.requested_state_version != task.state_version:
                raise ResumeTransitionConflict(
                    "input command targeted a different task state version"
                )

            deadline_row = conn.execute(
                "SELECT * FROM worker_checkpoint_deadlines "
                "WHERE checkpoint_id = ?",
                (message.checkpoint_id,),
            ).fetchone()
            if deadline_row is None:
                raise EvidenceConflict(
                    "controller_resume",
                    message.checkpoint_id,
                    "checkpoint has no durable deadline",
                )
            deadline = CheckpointDeadline.model_validate(dict(deadline_row))
            if deadline.session_binding_id != message.session_binding_id:
                raise CanonicalBindingMismatch(
                    "checkpoint deadline session does not match acknowledged input"
                )
            if deadline.deadline_policy is CheckpointDeadlinePolicy.BOUNDED:
                deadline_time = self._parse_timestamp(
                    deadline.deadline_at, "deadline_at"
                )
                if transition_time >= deadline_time:
                    raise ResumeTransitionConflict(
                        "checkpoint deadline expired before canonical resume"
                    )
            expiry = conn.execute(
                "SELECT 1 FROM worker_checkpoint_expiries "
                "WHERE checkpoint_id = ? LIMIT 1",
                (message.checkpoint_id,),
            ).fetchone()
            if expiry is not None:
                raise ResumeTransitionConflict(
                    "checkpoint expiry evidence outranks acknowledgement"
                )
            superseded = conn.execute(
                "SELECT 1 FROM task_links WHERE link_type = 'supersedes' "
                "AND target_kind = 'task' AND target_id = ? LIMIT 1",
                (message.task_id,),
            ).fetchone()
            if superseded is not None:
                raise ResumeTransitionConflict(
                    "task supersession outranks acknowledged input"
                )

            resolved_checkpoint = self.task_store.resolve_checkpoint_in_connection(
                conn,
                message.checkpoint_id,
                task_id=message.task_id,
                required_state_version=task.state_version,
                resolved_at=transition_at,
            )
            completed_command = self.task_store.complete_command_in_connection(
                conn,
                message.command_id,
                status=TaskCommandStatus.COMPLETED,
                reason="acknowledged input resumed the exact checkpoint",
                completed_at=transition_at,
            )
            if completed_command.task_id != message.task_id:
                raise CanonicalBindingMismatch(
                    "completed command does not belong to acknowledged task"
                )

            updated_task = self.task_store.conditional_update_in_connection(
                conn,
                message.task_id,
                fields={
                    "state": TaskState.RUNNING.value,
                    "phase": TaskPhase.BACKEND_RUNNING.value,
                    "checkpoint_ref": "",
                },
                expected_state_version=int(expected_task_state_version),
                expected_states=(TaskState.AWAITING_CONTROLLER.value,),
            )
            if updated_task is None:
                raise ResumeTransitionConflict(
                    "task changed during acknowledged resume"
                )
            updated_run = self.run_store.conditional_update_in_connection(
                conn,
                message.run_id,
                fields={
                    "status": "running",
                    "current_phase": "backend_running",
                    "requires_human": False,
                    "heartbeat_at": transition_at,
                    "ended_at": None,
                },
                expected_statuses=("awaiting_controller",),
                expected_state_version=int(expected_run_state_version),
                reject_terminal=True,
            )
            if updated_run is None:
                raise ResumeTransitionConflict(
                    "run changed during acknowledged resume"
                )

            event_data = {
                "checkpoint_id": message.checkpoint_id,
                "message_id": message_id,
                "attempt_id": attempt.attempt_id,
                "session_binding_id": message.session_binding_id,
                "acknowledgement_evidence_ref": attempt.evidence_ref,
            }
            self.task_store.append_event_in_connection(
                conn,
                message.task_id,
                level=TaskEventLevel.INFO,
                stage="controller_resumed",
                message="Task resumed from acknowledged controller input",
                state=TaskState.RUNNING.value,
                state_version=updated_task.state_version,
                data=event_data,
                timestamp=transition_at,
            )
            self.run_store.append_event_in_connection(
                conn,
                message.run_id,
                level="info",
                stage="controller_resumed",
                message="Run resumed from acknowledged controller input",
                data=event_data,
                timestamp=transition_at,
            )

        return ResumeTransitionResult(
            task=updated_task,
            run=updated_run,
            checkpoint=resolved_checkpoint,
            message_id=message_id,
            attempt_id=attempt.attempt_id,
            acknowledgement_evidence_ref=attempt.evidence_ref,
            created=True,
        )
