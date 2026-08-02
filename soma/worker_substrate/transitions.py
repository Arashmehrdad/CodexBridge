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
    TaskEventLevel,
    TaskPhase,
    TaskRecord,
    TaskState,
    checkpoint_id_for_request,
    utc_now,
)
from soma.tasks.store import TaskStore

from .models import (
    CheckpointDeadline,
    CheckpointDeadlinePolicy,
    canonical_json,
    require_opaque,
)
from .store import CanonicalBindingMismatch, EvidenceConflict, WorkerSubstrateStore


WAIT_CONTRACT_REFERENCE_PREFIX = "worker_wait_contract:"
WAIT_CONTRACT_VERSION = "worker_wait.v1"


class WaitTransitionConflict(ValueError):
    """The requested wait transition conflicts with canonical durable state."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class WaitTransitionResult:
    task: TaskRecord
    run: dict[str, Any]
    checkpoint: TaskCheckpoint
    deadline: CheckpointDeadline
    contract_hash: str
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
