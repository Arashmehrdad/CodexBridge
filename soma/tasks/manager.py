"""Canonical task manager.

Boundaries this manager keeps:

* the existing durable run store remains authoritative for worker/process
  lifecycle, locks, leases, evidence, and results;
* the task store remains authoritative for canonical public task identity,
  typed links, and task commands;
* backend mappings are explicit and persisted at task creation;
* one active task never silently switches backend;
* every task update is a compare-and-set on ``state_version``;
* reconciliation never guesses: a missing or inconsistent backend identity
  becomes ``recovery_pending`` or ``uncertain``, never an invented success.
"""

from __future__ import annotations

import sqlite3
from base64 import b64decode

from pathlib import Path
from typing import Any

from soma.config import AppConfig
from soma.job_manager import JobManager
from soma.safety import redact_secret_values

from .backends import BackendObservation, DurableCommandSpec, DurableRunBackend
from .models import (
    BackendKind,
    TaskCommandKind,
    TaskCommandStatus,
    TaskEventLevel,
    TaskKind,
    TaskPhase,
    TaskRecord,
    TaskRecoveryState,
    TaskState,
    TERMINAL_TASK_STATES,
    make_task_id,
    map_backend_status,
    normalize_durable_command_request,
    normalized_request_hash,
    run_input_reference,
    run_terminal_reference,
    utc_now,
)
from .projections import (
    TASK_EVENT_DEFAULT_LIMIT,
    TASK_EVENT_MAX_LIMIT,
    TASK_LINK_DEFAULT_LIMIT,
    TASK_LINK_MAX_LIMIT,
    TASK_RESPONSE_BUDGET_BYTES,
    finalize,
    compact_task_events,
    compact_task_links,
    compact_task_result,
    compact_task_status,
    task_capabilities,
    task_error,
)
from .store import TaskRequestConflict, TaskStore


class TaskManager:
    def __init__(
        self,
        config: AppConfig,
        config_path: Path | None = None,
        *,
        job_manager: JobManager | None = None,
        backend: Any | None = None,
        store: TaskStore | None = None,
    ):
        self.config = config
        self.config_path = config_path
        self._job_manager = job_manager
        self._backend = backend
        self.store = store or TaskStore(config.resolve_runs_dir())

    # ------------------------------------------------------------------
    # wiring
    # ------------------------------------------------------------------

    @property
    def job_manager(self) -> JobManager:
        if self._job_manager is None:
            self._job_manager = JobManager(self.config, self.config_path)
        return self._job_manager

    @property
    def backend(self):
        if self._backend is None:
            self._backend = DurableRunBackend(self.job_manager)
        return self._backend

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def capabilities(self, budget: int = TASK_RESPONSE_BUDGET_BYTES) -> dict[str, Any]:
        return task_capabilities(
            schema_state=self.store.schema_state(), budget=budget
        )

    def get_status(
        self,
        task_id: str,
        *,
        reconcile: bool = True,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task = self.store.get_task(task_id)
        except (KeyError, ValueError) as exc:
            return self._lookup_error("status", task_id, exc, budget)
        if reconcile and not task.is_terminal:
            task = self.reconcile_task(task.task_id)
        observation = self.backend.query(task.backend_ref)
        return compact_task_status(
            task,
            observation=observation,
            open_checkpoint_count=self.store.open_checkpoint_count(task.task_id),
            link_counts=self._link_counts(task.task_id),
            budget=budget,
        )

    def get_result(
        self, task_id: str, *, budget: int = TASK_RESPONSE_BUDGET_BYTES
    ) -> dict[str, Any]:
        try:
            task = self.store.get_task(task_id)
        except (KeyError, ValueError) as exc:
            return self._lookup_error("result", task_id, exc, budget)
        if not task.is_terminal:
            task = self.reconcile_task(task.task_id)
        observation = self.backend.query(task.backend_ref)
        source = (
            self.backend.result_reference(task.backend_ref)
            if task.backend_ref
            else {"available": False, "authority": "durable_run", "run_id": ""}
        )
        source["result_publication_status"] = observation.result_publication_status
        source["result_published_hash"] = observation.result_published_hash
        source["result_published_at"] = observation.result_published_at
        return compact_task_result(
            task, observation=observation, result_source=source, budget=budget
        )

    def get_events(
        self,
        task_id: str,
        *,
        limit: int = TASK_EVENT_DEFAULT_LIMIT,
        after_id: int | None = None,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task = self.store.get_task(task_id)
        except (KeyError, ValueError) as exc:
            return self._lookup_error("events", task_id, exc, budget)
        bounded = max(1, min(int(limit), TASK_EVENT_MAX_LIMIT))
        events = self.store.list_events(
            task.task_id, limit=bounded, after_id=after_id
        )
        return compact_task_events(
            task,
            events,
            limit=bounded,
            after_id=after_id,
            latest_event_id=self.store.latest_event_id(task.task_id),
            budget=budget,
        )

    def get_links(
        self,
        task_id: str,
        *,
        limit: int = TASK_LINK_DEFAULT_LIMIT,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task = self.store.get_task(task_id)
        except (KeyError, ValueError) as exc:
            return self._lookup_error("links", task_id, exc, budget)
        bounded = max(1, min(int(limit), TASK_LINK_MAX_LIMIT))
        links = self.store.list_links(task.task_id, limit=bounded)
        return compact_task_links(task, links, limit=bounded, budget=budget)

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------

    def start_durable_command(
        self,
        *,
        controller_request_id: str,
        repo_name: str,
        profile_id: str = "powershell",
        argv: list[str] | None = None,
        working_directory: str = "",
        environment: dict[str, str] | None = None,
        stdin_text: str | None = None,
        stdin_base64: str | None = None,
        timeout_seconds: int | None = None,
        parent_task_id: str = "",
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Idempotently create a canonical task backed by one durable run."""
        argv = list(argv or [])
        try:
            normalized = normalize_durable_command_request(
                repo_name=repo_name,
                profile_id=profile_id,
                argv=argv,
                working_directory=working_directory,
                environment=environment,
                stdin_text=stdin_text,
                stdin_base64=stdin_base64,
                timeout_seconds=timeout_seconds,
                parent_task_id=parent_task_id,
            )
        except (ValueError, TypeError) as exc:
            return task_error(
                operation="start",
                error_code="invalid_request",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        request_hash = normalized_request_hash(normalized)

        # The backend reference is reserved before the task row is committed so
        # the durable run identity is owned by exactly one canonical task.
        backend_ref = self.backend.reserve()
        task_id = make_task_id()
        try:
            task, created = self.store.reserve_task(
                task_id=task_id,
                task_kind=TaskKind.DURABLE_COMMAND.value,
                controller_request_id=controller_request_id,
                request_hash=request_hash,
                backend_kind=self.backend.kind,
                backend_executor=self.backend.executor,
                backend_ref=backend_ref,
                backend_identity={
                    "engine": self.backend.kind,
                    "run_tool": self.backend.executor,
                    "repo_name": repo_name,
                    "profile_id": profile_id,
                },
                objective_ref=run_input_reference(backend_ref),
                constraints_ref=run_input_reference(backend_ref),
                workspace_kind="repository",
                workspace_ref=repo_name,
                parent_task_id=parent_task_id,
            )
        except TaskRequestConflict as exc:
            return task_error(
                operation="start",
                error_code="controller_request_hash_conflict",
                error=str(exc),
                task_id=exc.task.task_id,
                state=exc.task.state.value,
                state_version=exc.task.state_version,
                budget=budget,
                extra={
                    "existing_request_hash": exc.task.request_hash,
                    "submitted_request_hash": exc.submitted_hash,
                    "backend_reference": exc.task.backend_ref,
                },
            )
        except sqlite3.IntegrityError:
            # A concurrent identical request won the reservation. Never launch
            # a second backend run: return whatever the winner created.
            existing = self.store.find_by_controller_request(controller_request_id)
            if existing is None:
                raise
            task, created = existing, False

        if not created:
            return self._replay_response(task, budget=budget)

        self.store.append_event(
            task.task_id,
            level=TaskEventLevel.INFO,
            stage="reserved",
            message="Canonical task reserved its durable backend reference",
            state=task.state.value,
            state_version=task.state_version,
            data={
                "backend_kind": task.backend_kind.value,
                "backend_reference": task.backend_ref,
            },
        )

        spec = DurableCommandSpec(
            repo_name=repo_name,
            profile_id=profile_id,
            argv=argv,
            working_directory=working_directory,
            environment=dict(environment or {}),
            stdin_text=stdin_text,
            stdin_bytes=(
                b64decode(stdin_base64, validate=True)
                if stdin_base64 is not None
                else None
            ),
            timeout_seconds=timeout_seconds,
        )
        launch: dict[str, Any] = {}
        launch_error = ""
        try:
            launch = self.backend.start(spec, task.backend_ref)
        except Exception as exc:  # noqa: BLE001 - recorded as durable evidence
            launch_error = f"{type(exc).__name__}: {redact_secret_values(str(exc))}"
            self.store.append_event(
                task.task_id,
                level=TaskEventLevel.ERROR,
                stage="backend_launch",
                message="Durable backend launch raised before attachment",
                state=task.state.value,
                state_version=task.state_version,
                data={"error": launch_error},
            )
        else:
            if not launch.get("accepted", True):
                launch_error = redact_secret_values(str(launch.get("reason") or ""))
                self.store.append_event(
                    task.task_id,
                    level=TaskEventLevel.WARNING,
                    stage="backend_launch",
                    message="Durable backend refused the launch",
                    state=task.state.value,
                    state_version=task.state_version,
                    data={"reason": launch_error},
                )

        task = self.reconcile_task(task.task_id, stage="backend_attachment")
        response = compact_task_status(
            task,
            observation=self.backend.query(task.backend_ref),
            open_checkpoint_count=self.store.open_checkpoint_count(task.task_id),
            link_counts=self._link_counts(task.task_id),
            operation="start",
            budget=budget,
            extra={
                "created": True,
                "idempotent_replay": False,
                "request_hash": task.request_hash,
                "backend_launch_accepted": bool(launch.get("accepted", not launch_error)),
                "backend_launch_error": launch_error,
                "polling": {
                    "tool": "task_query",
                    "request": {"operation": "status", "task_id": task.task_id},
                },
            },
        )
        response["ok"] = not launch_error
        return response

    def cancel_task(
        self,
        task_id: str,
        *,
        if_state_version: int,
        reason: str = "",
        controller_request_id: str = "",
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Version-guarded cancellation delegated to the backend authority."""
        try:
            task = self.store.get_task(task_id)
        except (KeyError, ValueError) as exc:
            return self._lookup_error("cancel", task_id, exc, budget)

        if int(if_state_version) != int(task.state_version):
            self.store.record_command(
                task.task_id,
                command_kind=TaskCommandKind.CANCEL,
                requested_state_version=int(if_state_version),
                observed_state_version=task.state_version,
                status=TaskCommandStatus.REJECTED_STALE_VERSION,
                controller_request_id=controller_request_id,
                reason="state version guard did not match",
            )
            return task_error(
                operation="cancel",
                error_code="stale_state_version",
                error=(
                    "Task state version has advanced: expected "
                    f"{int(if_state_version)}, current {task.state_version}"
                ),
                task_id=task.task_id,
                state=task.state.value,
                state_version=task.state_version,
                budget=budget,
                extra={
                    "if_state_version": int(if_state_version),
                    "current_state_version": task.state_version,
                    "status_retrieval": {
                        "tool": "task_query",
                        "request": {"operation": "status", "task_id": task.task_id},
                    },
                },
            )

        command = self.store.record_command(
            task.task_id,
            command_kind=TaskCommandKind.CANCEL,
            requested_state_version=int(if_state_version),
            observed_state_version=task.state_version,
            status=TaskCommandStatus.ACCEPTED,
            controller_request_id=controller_request_id,
            reason=redact_secret_values(reason)[:512],
        )

        if task.is_terminal:
            # Repeated cancellation of a finished task is a no-op. Nothing is
            # signalled, so no unrelated process can be targeted.
            self.store.complete_command(
                command.command_id,
                status=TaskCommandStatus.COMPLETED,
                reason="task already terminal",
            )
            return self._cancel_response(
                task,
                command_id=command.command_id,
                backend_result={},
                already_terminal=True,
                budget=budget,
            )

        if not task.backend_ref:
            task = self.reconcile_task(task.task_id, stage="cancel")
            self.store.complete_command(
                command.command_id,
                status=TaskCommandStatus.FAILED,
                reason="task has no backend reference to cancel",
            )
            return self._cancel_response(
                task,
                command_id=command.command_id,
                backend_result={},
                already_terminal=False,
                budget=budget,
                ok=False,
                error_code="backend_reference_missing",
                error="Task has no backend reference; cancellation was not claimed",
            )

        observation = self.backend.query(task.backend_ref)
        if not observation.exists:
            task = self.reconcile_task(task.task_id, stage="cancel")
            self.store.complete_command(
                command.command_id,
                status=TaskCommandStatus.FAILED,
                reason="backend run record is not present",
            )
            return self._cancel_response(
                task,
                command_id=command.command_id,
                backend_result={},
                already_terminal=False,
                budget=budget,
                ok=False,
                error_code="backend_run_not_found",
                error=(
                    "Backend run record is not present; cancellation ownership "
                    "was not proven and no cancellation is claimed"
                ),
            )

        backend_result = self.backend.cancel(task.backend_ref)
        self.store.append_event(
            task.task_id,
            level=TaskEventLevel.WARNING,
            stage="cancel",
            message="Cancellation delegated to the durable backend authority",
            state=task.state.value,
            state_version=task.state_version,
            data={
                "backend_reference": task.backend_ref,
                "backend_ok": bool(backend_result.get("ok")),
                "backend_status": str(backend_result.get("status") or ""),
            },
        )
        task = self.reconcile_task(task.task_id, stage="cancel")
        self.store.complete_command(
            command.command_id,
            status=TaskCommandStatus.COMPLETED,
            reason=str(backend_result.get("reason") or ""),
        )
        return self._cancel_response(
            task,
            command_id=command.command_id,
            backend_result=backend_result,
            already_terminal=False,
            budget=budget,
        )

    # ------------------------------------------------------------------
    # reconciliation
    # ------------------------------------------------------------------

    def reconcile_task(self, task_id: str, *, stage: str = "reconcile") -> TaskRecord:
        """Bring one canonical task in line with its backend, or say it cannot.

        Duplicate execution is safe: an unchanged projection performs no write,
        and a concurrent writer simply wins the compare-and-set.
        """
        task = self.store.get_task(task_id)
        observation = self.backend.query(task.backend_ref)
        target = self._derive_target(task, observation)
        if not target:
            return task
        updated = self.store.conditional_update(
            task.task_id,
            fields=target["fields"],
            expected_state_version=task.state_version,
            expected_states=(task.state.value,),
        )
        if updated is None:
            # Another reconciler or command won. Its transition is equally
            # authoritative, so re-read rather than overwrite it.
            return self.store.get_task(task.task_id)
        self.store.append_event(
            updated.task_id,
            level=target["level"],
            stage=stage,
            message=target["message"],
            state=updated.state.value,
            state_version=updated.state_version,
            data=target["data"],
        )
        return updated

    def _derive_target(
        self, task: TaskRecord, observation: BackendObservation
    ) -> dict[str, Any] | None:
        fields: dict[str, Any] = {}
        level = TaskEventLevel.INFO
        message = "Canonical task projection reconciled with its backend"
        data: dict[str, Any] = {
            "backend_reference": task.backend_ref,
            "backend_status": observation.status,
        }

        if task.backend_kind is not BackendKind.SOMA_DURABLE_RUN:
            state, phase = TaskState.UNCERTAIN, TaskPhase.RECOVERY
            recovery = (TaskRecoveryState.UNRESOLVED, "unsupported_backend_kind")
        elif not task.backend_ref:
            state, phase = TaskState.RECOVERY_PENDING, TaskPhase.RECOVERY
            recovery = (TaskRecoveryState.PENDING, "backend_reference_missing")
        elif not observation.exists:
            if task.state in {TaskState.ACCEPTED, TaskState.QUEUED}:
                # Persist-before-launch means no durable run row implies no
                # worker was ever created for this reserved identity.
                state, phase = TaskState.RECOVERY_PENDING, TaskPhase.RECOVERY
                recovery = (TaskRecoveryState.PENDING, "backend_launch_incomplete")
            else:
                state, phase = TaskState.UNCERTAIN, TaskPhase.RECOVERY
                recovery = (TaskRecoveryState.UNRESOLVED, "backend_run_record_missing")
            level = TaskEventLevel.WARNING
            message = "Backend run record is not present for this canonical task"
        elif not self._backend_identity_matches(task, observation):
            state, phase = TaskState.UNCERTAIN, TaskPhase.RECOVERY
            recovery = (TaskRecoveryState.UNRESOLVED, "backend_identity_mismatch")
            level = TaskEventLevel.ERROR
            message = "Backend identity does not match the recorded task mapping"
            data["observed_executor"] = observation.executor
            data["observed_repo_name"] = observation.repo_name
        else:
            state, phase = map_backend_status(observation.status)
            if state is TaskState.UNCERTAIN:
                recovery = (TaskRecoveryState.UNRESOLVED, "unknown_backend_status")
                level = TaskEventLevel.ERROR
                message = "Backend reported an unmapped status"
            elif state is TaskState.RECOVERY_PENDING:
                recovery = (TaskRecoveryState.PENDING, "backend_recovery_pending")
                level = TaskEventLevel.WARNING
                message = "Backend is in conservative recovery"
            else:
                recovery = (TaskRecoveryState.NONE, "")
            if observation.started_at and not task.started_at:
                fields["started_at"] = observation.started_at
            if state in TERMINAL_TASK_STATES or state is TaskState.AWAITING_CONTROLLER:
                if observation.ended_at:
                    fields["ended_at"] = observation.ended_at
                # Publish the result linkage rather than the result body.
                fields["result_ref"] = task.backend_ref
                fields["result_hash"] = observation.result_published_hash
                fields["evidence_ref"] = run_terminal_reference(task.backend_ref)
                if state in TERMINAL_TASK_STATES:
                    phase = TaskPhase.RESULT_PUBLISHED

        fields["state"] = state.value
        fields["phase"] = phase.value
        fields["recovery_state"] = recovery[0].value
        fields["recovery_reason"] = recovery[1]
        fields["reconciled_at"] = utc_now()

        current = {
            "state": task.state.value,
            "phase": task.phase.value,
            "recovery_state": task.recovery_state.value,
            "recovery_reason": task.recovery_reason,
            "started_at": task.started_at,
            "ended_at": task.ended_at,
            "result_ref": task.result_ref,
            "result_hash": task.result_hash,
            "evidence_ref": task.evidence_ref,
        }
        material = {
            name: value
            for name, value in fields.items()
            if name != "reconciled_at" and current.get(name) != value
        }
        if not material:
            return None
        data["changed_fields"] = sorted(material)
        return {"fields": fields, "level": level, "message": message, "data": data}

    @staticmethod
    def _backend_identity_matches(
        task: TaskRecord, observation: BackendObservation
    ) -> bool:
        if task.backend_executor and observation.executor != task.backend_executor:
            return False
        recorded_repo = str(task.backend_identity.get("repo_name") or "")
        if not recorded_repo or not observation.repo_name:
            return True
        # The durable store canonicalises repository names, so compare
        # case-insensitively rather than declaring a false mismatch.
        return recorded_repo.lower() == observation.repo_name.lower()

    def reconcile_startup(self, limit: int = 500) -> dict[str, Any]:
        """Restart-safe reconciliation for every non-terminal canonical task."""
        examined = 0
        changed = 0
        failures: list[dict[str, str]] = []
        for task in self.store.list_active_tasks(limit=limit):
            examined += 1
            before = task.state_version
            try:
                updated = self.reconcile_task(task.task_id, stage="startup_recovery")
            except Exception as exc:  # noqa: BLE001 - never swallowed silently
                detail = f"{type(exc).__name__}: {redact_secret_values(str(exc))}"
                failures.append({"task_id": task.task_id, "error": detail})
                try:
                    self.store.append_event(
                        task.task_id,
                        level=TaskEventLevel.ERROR,
                        stage="startup_recovery",
                        message="Startup reconciliation failed for this task",
                        state=task.state.value,
                        state_version=task.state_version,
                        data={"error": detail},
                    )
                except Exception:  # noqa: BLE001 - store already reported
                    pass
                continue
            if updated.state_version != before:
                changed += 1
        return {
            "ok": not failures,
            "examined": examined,
            "changed": changed,
            "failures": failures,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _link_counts(self, task_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for link in self.store.list_links(task_id, limit=TASK_LINK_MAX_LIMIT):
            counts[link.link_type.value] = counts.get(link.link_type.value, 0) + 1
        return counts

    def _replay_response(
        self, task: TaskRecord, *, budget: int
    ) -> dict[str, Any]:
        if not task.is_terminal:
            task = self.reconcile_task(task.task_id, stage="idempotent_replay")
        return compact_task_status(
            task,
            observation=self.backend.query(task.backend_ref),
            open_checkpoint_count=self.store.open_checkpoint_count(task.task_id),
            link_counts=self._link_counts(task.task_id),
            operation="start",
            budget=budget,
            extra={
                "created": False,
                "idempotent_replay": True,
                "request_hash": task.request_hash,
                "backend_launch_accepted": bool(task.backend_ref),
                "backend_launch_error": "",
                "polling": {
                    "tool": "task_query",
                    "request": {"operation": "status", "task_id": task.task_id},
                },
            },
        )

    def _cancel_response(
        self,
        task: TaskRecord,
        *,
        command_id: str,
        backend_result: dict[str, Any],
        already_terminal: bool,
        budget: int,
        ok: bool = True,
        error_code: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        response = compact_task_status(
            task,
            observation=self.backend.query(task.backend_ref),
            open_checkpoint_count=self.store.open_checkpoint_count(task.task_id),
            link_counts=self._link_counts(task.task_id),
            operation="cancel",
            budget=budget,
            extra={
                "command_id": command_id,
                "already_terminal": already_terminal,
                "cancellation_claimed": task.state is TaskState.CANCELLED,
                "cancellation_pending": task.state
                is TaskState.CANCELLATION_PENDING,
                "backend_cancellation": {
                    "ok": bool(backend_result.get("ok", False)),
                    "status": str(backend_result.get("status") or ""),
                    "cancelled": bool(backend_result.get("cancelled", False)),
                    "termination_confirmed": bool(
                        backend_result.get("termination_confirmed", False)
                    ),
                    "reason": redact_secret_values(
                        str(backend_result.get("reason") or "")
                    )[:512],
                },
            },
        )
        response["ok"] = ok
        if error_code:
            response["error_code"] = error_code
        if error:
            response["error"] = error
        return finalize(response)

    @staticmethod
    def _lookup_error(
        operation: str, task_id: str, exc: Exception, budget: int
    ) -> dict[str, Any]:
        code = "task_not_found" if isinstance(exc, KeyError) else "invalid_task_id"
        return task_error(
            operation=operation,
            error_code=code,
            error=redact_secret_values(str(exc)).strip("'"),
            task_id=task_id,
            budget=budget,
        )
