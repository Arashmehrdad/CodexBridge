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

import json
import sqlite3
from base64 import b64decode
from hashlib import sha256
from pathlib import Path
from typing import Any

from soma.config import AppConfig, resolve_repo_identity
from soma.job_manager import JobManager
from soma.project_scope import (
    ProjectScopeError,
    ProjectScopeMismatch,
    ProjectScopeStore,
)
from soma.project_scope.models import (
    ADJUDICATION_ID_DOMAIN,
    ADJUDICATION_REQUEST_DOMAIN,
    RepositoryBinding,
    path_is_within_repository,
    validate_opaque_id,
)
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
    normalize_scoped_durable_command_request,
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
    _envelope,
    finalize,
    compact_task_events,
    compact_task_links,
    compact_task_result,
    compact_task_status,
    task_capabilities,
    task_error,
)
from .store import TaskRequestConflict, TaskStore


class _ControllerRequestScopeConflict(Exception):
    """Internal signal for a non-enumerating cross-project replay response."""


class _StaleRecoveryResolution(Exception):
    def __init__(self, task: TaskRecord) -> None:
        self.task = task


class TaskManager:
    def __init__(
        self,
        config: AppConfig,
        config_path: Path | None = None,
        *,
        job_manager: JobManager | None = None,
        backend: Any | None = None,
        store: TaskStore | None = None,
        scope_store: ProjectScopeStore | None = None,
    ):
        self.config = config
        self.config_path = config_path
        self._job_manager = job_manager
        self._backend = backend
        self.store = store or TaskStore(config.resolve_runs_dir())
        self.scope_store = scope_store or ProjectScopeStore(config.resolve_runs_dir())

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
        schema = self.store.schema_state()
        schema["project_scope"] = self.scope_store.schema_state()
        return task_capabilities(schema_state=schema, budget=budget)

    def list_quarantine(
        self,
        project_id: str,
        *,
        limit: int = 50,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Project-scoped quarantine evidence with any recorded adjudication."""
        try:
            records = self.scope_store.list_quarantine(project_id, limit=limit)
        except ProjectScopeError as exc:
            return task_error(
                operation="quarantine",
                error_code="project_scope_quarantine_unavailable",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        return finalize(
            {
                "ok": True,
                "operation": "quarantine",
                "project_id": project_id,
                "records": records,
                "returned_count": len(records),
                "adjudicated_count": sum(1 for r in records if r["adjudicated"]),
                "error": "",
                **_envelope(budget),
            }
        )

    def adjudicate_quarantine(
        self,
        *,
        project_id: str,
        record_kind: str,
        record_id: str,
        disposition: str,
        reason: str,
        idempotency_key: str,
        successor_task_id: str = "",
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Record an owner disposition without mutating preserved evidence."""
        try:
            result = self.scope_store.adjudicate_quarantine(
                project_id=project_id,
                record_kind=record_kind,
                record_id=record_id,
                disposition=disposition,
                reason=reason,
                idempotency_key=idempotency_key,
                successor_task_id=successor_task_id,
            )
        except ProjectScopeMismatch as exc:
            # Deliberately identical for "absent", "not quarantined", and
            # "other project" so the response cannot be used to enumerate.
            return task_error(
                operation="adjudicate_quarantine",
                error_code="project_scope_mismatch",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        except ProjectScopeError as exc:
            return task_error(
                operation="adjudicate_quarantine",
                error_code="project_scope_adjudication_rejected",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        return finalize(
            {**result, "operation": "adjudicate_quarantine", "error": "", **_envelope(budget)}
        )

    def resolve_recovery(
        self,
        *,
        project_id: str,
        task_id: str,
        if_state_version: int,
        successor_task_id: str,
        reason: str,
        idempotency_key: str,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Terminally resolve one missing-backend task as superseded.

        The task transition, scope quarantine, supersedes link, event, and
        immutable adjudication share one main-store transaction. No backend row
        or result evidence is invented.
        """
        trimmed_reason = str(reason or "").strip()[:512]
        if not trimmed_reason:
            return task_error(
                operation="resolve_recovery",
                error_code="task_recovery_resolution_rejected",
                error="reason is required",
                budget=budget,
            )
        try:
            for value, field in (
                (project_id, "project_id"),
                (task_id, "task_id"),
                (successor_task_id, "successor_task_id"),
                (idempotency_key, "idempotency_key"),
            ):
                validate_opaque_id(value, field)
            schema = self.scope_store.schema_state()
            if "project_scope_adjudications" not in schema.get("tables", []):
                raise ProjectScopeError(
                    "ProjectScope adjudication schema is unavailable"
                )

            with self.store.transaction() as conn:
                target = self.store.get_task_in_connection(conn, task_id)
                successor = self.store.get_task_in_connection(
                    conn, successor_task_id
                )
                target_scope = conn.execute(
                    "SELECT project_id, scope_generation, status "
                    "FROM project_task_reservations WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                attempt = conn.execute(
                    "SELECT attempt.run_id, attempt.project_id, "
                    "attempt.resource_id, attempt.scope_generation, "
                    "attempt.status, attempt.recovery_reason, "
                    "run.run_id AS stored_run_id "
                    "FROM project_run_attempts attempt "
                    "LEFT JOIN runs run ON run.run_id = attempt.run_id "
                    "WHERE attempt.task_id = ?",
                    (task_id,),
                ).fetchone()
                successor_scope = conn.execute(
                    "SELECT project_id, status FROM project_task_reservations "
                    "WHERE task_id = ?",
                    (successor_task_id,),
                ).fetchone()
                if (
                    target_scope is None
                    or attempt is None
                    or successor_scope is None
                    or str(target_scope["project_id"]) != project_id
                    or str(attempt["project_id"]) != project_id
                    or int(attempt["scope_generation"])
                    != int(target_scope["scope_generation"])
                    or str(successor_scope["project_id"]) != project_id
                ):
                    raise ProjectScopeMismatch(
                        "No recoverable task matches this project scope"
                    )

                adjudication_id = sha256(
                    "\0".join(
                        (
                            ADJUDICATION_ID_DOMAIN,
                            project_id,
                            "task_reservation",
                            task_id,
                            idempotency_key,
                        )
                    ).encode("utf-8")
                ).hexdigest()
                request_hash = sha256(
                    "\0".join(
                        (
                            ADJUDICATION_REQUEST_DOMAIN,
                            project_id,
                            "task_reservation",
                            task_id,
                            "superseded",
                            successor_task_id,
                            trimmed_reason,
                        )
                    ).encode("utf-8")
                ).hexdigest()
                existing = conn.execute(
                    "SELECT * FROM project_scope_adjudications "
                    "WHERE record_kind = 'task_reservation' AND record_id = ?",
                    (task_id,),
                ).fetchone()

                if existing is not None:
                    if str(existing["adjudication_id"]) != adjudication_id:
                        raise ProjectScopeError(
                            "Record is already adjudicated under a different "
                            "idempotency key; adjudication is single-shot"
                        )
                    if str(existing["request_hash"]) != request_hash:
                        raise ProjectScopeError(
                            "Idempotency key was already used for a different "
                            "recovery decision"
                        )
                    replayed = True
                    adjudication = existing
                else:
                    if int(if_state_version) != int(target.state_version):
                        raise _StaleRecoveryResolution(target)
                    if target.state not in {
                        TaskState.UNCERTAIN,
                        TaskState.RECOVERY_PENDING,
                    } or target.recovery_state not in {
                        TaskRecoveryState.UNRESOLVED,
                        TaskRecoveryState.PENDING,
                    }:
                        raise ProjectScopeError(
                            "Task is not in unresolved recovery"
                        )
                    if task_id == successor_task_id:
                        raise ProjectScopeError(
                            "successor_task_id must differ from task_id"
                        )
                    if successor.state is not TaskState.COMPLETED:
                        raise ProjectScopeError(
                            "Successor task must be completed"
                        )
                    if str(successor_scope["status"]) == "quarantined":
                        raise ProjectScopeMismatch(
                            "Successor task is not active in this project"
                        )
                    if attempt["stored_run_id"] is not None:
                        raise ProjectScopeError(
                            "Backend run exists; normal reconciliation owns this task"
                        )
                    if str(target_scope["status"]) == "quarantined":
                        raise ProjectScopeError(
                            "Task is already quarantined without an adjudication"
                        )

                    now = utc_now()
                    updated = conn.execute(
                        "UPDATE tasks SET state = 'failed', phase = 'recovery', "
                        "state_version = state_version + 1, "
                        "recovery_state = 'resolved', "
                        "recovery_reason = 'owner_superseded_unresolved_backend', "
                        "reconciled_at = ?, ended_at = ?, updated_at = ? "
                        "WHERE task_id = ? AND state_version = ? "
                        "AND state IN ('uncertain', 'recovery_pending')",
                        (
                            now,
                            now,
                            now,
                            task_id,
                            int(target.state_version),
                        ),
                    )
                    if updated.rowcount != 1:
                        raise _StaleRecoveryResolution(
                            self.store.get_task_in_connection(conn, task_id)
                        )
                    target = self.store.get_task_in_connection(conn, task_id)

                    reason_code = "owner_superseded_unresolved_backend"
                    conn.execute(
                        "UPDATE project_task_reservations "
                        "SET status = 'quarantined', updated_at = ? "
                        "WHERE task_id = ? AND status != 'quarantined'",
                        (now, task_id),
                    )
                    conn.execute(
                        "UPDATE project_run_attempts "
                        "SET status = 'quarantined', recovery_reason = ?, "
                        "updated_at = ? WHERE task_id = ? "
                        "AND status != 'quarantined'",
                        (reason_code, now, task_id),
                    )
                    evidence_hash = sha256(
                        json.dumps(
                            {
                                "record_kind": "task_reservation",
                                "record_id": task_id,
                                "reason_code": reason_code,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    conn.execute(
                        "INSERT OR IGNORE INTO project_scope_quarantine "
                        "(record_kind, record_id, reason_code, evidence_hash, "
                        "created_at) VALUES ('task_reservation', ?, ?, ?, ?)",
                        (task_id, reason_code, evidence_hash, now),
                    )
                    quarantine = conn.execute(
                        "SELECT evidence_hash FROM project_scope_quarantine "
                        "WHERE record_kind = 'task_reservation' AND record_id = ?",
                        (task_id,),
                    ).fetchone()
                    if (
                        quarantine is None
                        or str(quarantine["evidence_hash"]) != evidence_hash
                    ):
                        raise ProjectScopeError(
                            "Recovery quarantine evidence does not match"
                        )

                    conn.execute(
                        "INSERT INTO project_scope_adjudications "
                        "(adjudication_id, project_id, record_kind, record_id, "
                        "disposition, successor_task_id, reason, "
                        "idempotency_key, request_hash, "
                        "quarantine_evidence_hash, created_at) "
                        "VALUES (?, ?, 'task_reservation', ?, 'superseded', "
                        "?, ?, ?, ?, ?, ?)",
                        (
                            adjudication_id,
                            project_id,
                            task_id,
                            successor_task_id,
                            trimmed_reason,
                            idempotency_key,
                            request_hash,
                            evidence_hash,
                            now,
                        ),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO task_links "
                        "(task_id, link_type, target_kind, target_id, "
                        "created_at, metadata_json) "
                        "VALUES (?, 'supersedes', 'task', ?, ?, ?)",
                        (
                            successor_task_id,
                            task_id,
                            now,
                            json.dumps(
                                {
                                    "project_id": project_id,
                                    "reason": "recovery_disposition",
                                },
                                sort_keys=True,
                            ),
                        ),
                    )
                    conn.execute(
                        "INSERT INTO task_events "
                        "(task_id, timestamp, level, stage, message, state, "
                        "state_version, data_json) "
                        "VALUES (?, ?, 'warning', 'recovery_disposition', ?, "
                        "'failed', ?, ?)",
                        (
                            task_id,
                            now,
                            "Unresolved missing-backend task was terminally "
                            "quarantined and superseded",
                            target.state_version,
                            json.dumps(
                                {
                                    "project_id": project_id,
                                    "successor_task_id": successor_task_id,
                                    "backend_reference": target.backend_ref,
                                    "backend_run_fabricated": False,
                                    "adjudication_id": adjudication_id,
                                },
                                sort_keys=True,
                            ),
                        ),
                    )
                    adjudication = conn.execute(
                        "SELECT * FROM project_scope_adjudications "
                        "WHERE adjudication_id = ?",
                        (adjudication_id,),
                    ).fetchone()
                    replayed = False

                target = self.store.get_task_in_connection(conn, task_id)
                scope_after = conn.execute(
                    "SELECT status FROM project_task_reservations "
                    "WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                attempt_after = conn.execute(
                    "SELECT status FROM project_run_attempts WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                quarantine_after = conn.execute(
                    "SELECT evidence_hash FROM project_scope_quarantine "
                    "WHERE record_kind = 'task_reservation' AND record_id = ?",
                    (task_id,),
                ).fetchone()
                link_after = conn.execute(
                    "SELECT 1 FROM task_links WHERE task_id = ? "
                    "AND link_type = 'supersedes' AND target_kind = 'task' "
                    "AND target_id = ?",
                    (successor_task_id, task_id),
                ).fetchone()
                if (
                    target.state is not TaskState.FAILED
                    or target.recovery_state is not TaskRecoveryState.RESOLVED
                    or scope_after is None
                    or attempt_after is None
                    or str(scope_after["status"]) != "quarantined"
                    or str(attempt_after["status"]) != "quarantined"
                    or quarantine_after is None
                    or adjudication is None
                    or str(adjudication["quarantine_evidence_hash"])
                    != str(quarantine_after["evidence_hash"])
                    or link_after is None
                ):
                    raise ProjectScopeError(
                        "Stored recovery disposition is incomplete"
                    )

        except _StaleRecoveryResolution as exc:
            return task_error(
                operation="resolve_recovery",
                error_code="stale_state_version",
                error=(
                    "Task state version has advanced: expected "
                    f"{int(if_state_version)}, current {exc.task.state_version}"
                ),
                task_id=exc.task.task_id,
                state=exc.task.state.value,
                state_version=exc.task.state_version,
                budget=budget,
            )
        except ProjectScopeMismatch as exc:
            return task_error(
                operation="resolve_recovery",
                error_code="project_scope_mismatch",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        except KeyError as exc:
            return task_error(
                operation="resolve_recovery",
                error_code="project_scope_mismatch",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        except (ProjectScopeError, ValueError, sqlite3.IntegrityError) as exc:
            return task_error(
                operation="resolve_recovery",
                error_code="task_recovery_resolution_rejected",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )

        return finalize(
            {
                "ok": True,
                "operation": "resolve_recovery",
                "project_id": project_id,
                "task_id": target.task_id,
                "successor_task_id": successor_task_id,
                "disposition": "superseded",
                "state": target.state.value,
                "phase": target.phase.value,
                "state_version": target.state_version,
                "recovery_state": target.recovery_state.value,
                "recovery_reason": target.recovery_reason,
                "backend_reference": target.backend_ref,
                "backend_run_fabricated": False,
                "task_reservation_status": "quarantined",
                "run_attempt_status": "quarantined",
                "adjudication_id": str(adjudication["adjudication_id"]),
                "request_hash": str(adjudication["request_hash"]),
                "quarantine_evidence_hash": str(
                    adjudication["quarantine_evidence_hash"]
                ),
                "replayed": replayed,
                "error": "",
                **_envelope(budget),
            }
        )

    def get_status(
        self,
        task_id: str,
        *,
        project_id: str = "",
        reconcile: bool = True,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task, scope = self._load_task_scope(task_id, project_id)
        except (KeyError, ValueError, ProjectScopeError) as exc:
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
            project_scope=scope,
        )

    def get_result(
        self,
        task_id: str,
        *,
        project_id: str = "",
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task, scope = self._load_task_scope(task_id, project_id)
        except (KeyError, ValueError, ProjectScopeError) as exc:
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
            task,
            observation=observation,
            result_source=source,
            budget=budget,
            project_scope=scope,
        )

    def get_events(
        self,
        task_id: str,
        *,
        project_id: str = "",
        limit: int = TASK_EVENT_DEFAULT_LIMIT,
        after_id: int | None = None,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task, scope = self._load_task_scope(task_id, project_id)
        except (KeyError, ValueError, ProjectScopeError) as exc:
            return self._lookup_error("events", task_id, exc, budget)
        bounded = max(1, min(int(limit), TASK_EVENT_MAX_LIMIT))
        events = self.store.list_events(task.task_id, limit=bounded, after_id=after_id)
        return compact_task_events(
            task,
            events,
            limit=bounded,
            after_id=after_id,
            latest_event_id=self.store.latest_event_id(task.task_id),
            budget=budget,
            project_scope=scope,
        )

    def get_links(
        self,
        task_id: str,
        *,
        project_id: str = "",
        limit: int = TASK_LINK_DEFAULT_LIMIT,
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        try:
            task, scope = self._load_task_scope(task_id, project_id)
        except (KeyError, ValueError, ProjectScopeError) as exc:
            return self._lookup_error("links", task_id, exc, budget)
        bounded = max(1, min(int(limit), TASK_LINK_MAX_LIMIT))
        links = self.store.list_links(task.task_id, limit=bounded)
        return compact_task_links(
            task, links, limit=bounded, budget=budget, project_scope=scope
        )

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
        project_id: str = "",
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Idempotently create a canonical task backed by one durable run."""
        argv = list(argv or [])
        try:
            legacy_normalized = normalize_durable_command_request(
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
        legacy_hash = normalized_request_hash(legacy_normalized)
        enforcement_state = self.scope_store.enforcement_state()
        scope_active = enforcement_state == "enforced"
        binding: RepositoryBinding | None = None
        effective_repo_name = repo_name
        request_hash = legacy_hash

        existing = self.store.find_by_controller_request(controller_request_id)
        if existing is not None:
            existing_scope = self.scope_store.scope_for_task(existing.task_id)
            if existing_scope.project_id:
                if project_id and project_id != existing_scope.project_id:
                    return self._scope_conflict_response(budget=budget)
                try:
                    self.scope_store.require_task_attempt(
                        existing_scope.project_id,
                        existing.task_id,
                        existing.backend_ref,
                    )
                    binding, effective_repo_name = self._resolve_repository_binding(
                        project_id=project_id or existing_scope.project_id,
                        repo_name=repo_name,
                        working_directory=working_directory,
                    )
                    request_hash = self._scoped_request_hash(
                        binding=binding,
                        repo_name=effective_repo_name,
                        profile_id=profile_id,
                        argv=argv,
                        working_directory=working_directory,
                        environment=environment,
                        stdin_text=stdin_text,
                        stdin_base64=stdin_base64,
                        timeout_seconds=timeout_seconds,
                        parent_task_id=parent_task_id,
                    )
                except (ValueError, ProjectScopeError):
                    return self._scope_conflict_response(budget=budget)
            elif project_id:
                return self._scope_conflict_response(budget=budget)
            if existing.request_hash != request_hash:
                return self._request_conflict_response(
                    existing, request_hash, budget=budget
                )
            return self._replay_response(existing, budget=budget)

        if enforcement_state == "paused":
            return task_error(
                operation="start",
                error_code="project_scope_paused",
                error=(
                    "ProjectScope was previously activated and is now paused; "
                    "new task creation is disabled"
                ),
                budget=budget,
            )
        if project_id and not scope_active:
            return task_error(
                operation="start",
                error_code="project_scope_inactive",
                error=(
                    "ProjectScope writes are inactive; Gate B and Gate C "
                    "activation have not been completed"
                ),
                budget=budget,
            )
        if scope_active:
            try:
                binding, effective_repo_name = self._resolve_repository_binding(
                    project_id=project_id,
                    repo_name=repo_name,
                    working_directory=working_directory,
                )
                request_hash = self._scoped_request_hash(
                    binding=binding,
                    repo_name=effective_repo_name,
                    profile_id=profile_id,
                    argv=argv,
                    working_directory=working_directory,
                    environment=environment,
                    stdin_text=stdin_text,
                    stdin_base64=stdin_base64,
                    timeout_seconds=timeout_seconds,
                    parent_task_id=parent_task_id,
                )
            except (ValueError, ProjectScopeError) as exc:
                return task_error(
                    operation="start",
                    error_code="project_scope_resolution_failed",
                    error=redact_secret_values(str(exc)),
                    budget=budget,
                )

        # The backend reference is reserved before the task row is committed so
        # the durable run identity is owned by exactly one canonical task.
        backend_ref = self.backend.reserve()
        task_id = make_task_id()
        try:
            task_kwargs = {
                "task_id": task_id,
                "task_kind": TaskKind.DURABLE_COMMAND.value,
                "controller_request_id": controller_request_id,
                "request_hash": request_hash,
                "backend_kind": self.backend.kind,
                "backend_executor": self.backend.executor,
                "backend_ref": backend_ref,
                "backend_identity": {
                    "engine": self.backend.kind,
                    "run_tool": self.backend.executor,
                    "repo_name": effective_repo_name,
                    "profile_id": profile_id,
                },
                "objective_ref": run_input_reference(backend_ref),
                "constraints_ref": run_input_reference(backend_ref),
                "workspace_kind": "repository",
                "workspace_ref": effective_repo_name,
                "parent_task_id": parent_task_id,
            }
            if binding is None:
                task, created = self.store.reserve_task(**task_kwargs)
            else:
                with self.store.transaction() as conn:
                    concurrent = self.store.find_by_controller_request_in_connection(
                        conn, controller_request_id
                    )
                    if concurrent is not None:
                        concurrent_scope = self.scope_store.scope_for_task(
                            concurrent.task_id
                        )
                        if (
                            not concurrent_scope.project_id
                            or concurrent_scope.project_id != binding.project_id
                        ):
                            raise _ControllerRequestScopeConflict(
                                "Concurrent request belongs to another project"
                            )
                        self.scope_store.require_task_attempt(
                            binding.project_id,
                            concurrent.task_id,
                            concurrent.backend_ref,
                        )
                        if concurrent.request_hash != request_hash:
                            raise TaskRequestConflict(concurrent, request_hash)
                        task, created = concurrent, False
                    else:
                        self.scope_store.reserve_task_attempt(
                            conn,
                            binding=binding,
                            task_id=task_id,
                            run_id=backend_ref,
                            parent_task_id=parent_task_id,
                        )
                        task, created = self.store.reserve_task_in_connection(
                            conn, **task_kwargs
                        )
                        self.scope_store.attach_task(conn, task.task_id)
        except _ControllerRequestScopeConflict:
            return self._scope_conflict_response(budget=budget)
        except TaskRequestConflict as exc:
            return self._request_conflict_response(
                exc.task, exc.submitted_hash, budget=budget
            )
        except ProjectScopeError as exc:
            return task_error(
                operation="start",
                error_code="project_scope_reservation_failed",
                error=redact_secret_values(str(exc)),
                budget=budget,
            )
        except sqlite3.IntegrityError:
            # A concurrent identical request won the reservation. Never launch
            # a second backend run: return whatever the winner created.
            existing = self.store.find_by_controller_request(controller_request_id)
            if existing is None:
                raise
            existing_scope = self.scope_store.scope_for_task(existing.task_id)
            if binding is None:
                if existing_scope.project_id:
                    return self._scope_conflict_response(budget=budget)
            elif existing_scope.project_id != binding.project_id:
                return self._scope_conflict_response(budget=budget)
            else:
                try:
                    self.scope_store.require_task_attempt(
                        binding.project_id,
                        existing.task_id,
                        existing.backend_ref,
                    )
                except ProjectScopeError:
                    return self._scope_conflict_response(budget=budget)
            if existing.request_hash != request_hash:
                return self._request_conflict_response(
                    existing, request_hash, budget=budget
                )
            task, created = existing, False

        if not created:
            return self._replay_response(task, budget=budget)

        scope_projection = self.scope_store.scope_for_task(task.task_id).to_dict()
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
                **(
                    {
                        "project_id": binding.project_id,
                        "resource_id": binding.resource_id,
                        "scope_generation": binding.scope_generation,
                    }
                    if binding
                    else {}
                ),
            },
        )

        spec = DurableCommandSpec(
            repo_name=effective_repo_name,
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
        if binding is not None:
            try:
                self.scope_store.require_launchable_attempt(
                    binding=binding,
                    task_id=task.task_id,
                    run_id=task.backend_ref,
                )
            except ProjectScopeError as exc:
                launch_error = f"ProjectScopeError: {redact_secret_values(str(exc))}"
        if not launch_error:
            try:
                launch = self.backend.start(spec, task.backend_ref)
            except Exception as exc:  # noqa: BLE001 - recorded as durable evidence
                launch_error = f"{type(exc).__name__}: {redact_secret_values(str(exc))}"
        if launch_error:
            self.store.append_event(
                task.task_id,
                level=TaskEventLevel.ERROR,
                stage="backend_launch",
                message="Durable backend launch did not complete",
                state=task.state.value,
                state_version=task.state_version,
                data={"error": launch_error},
            )
        elif not launch.get("accepted", True):
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

        if binding is not None:
            try:
                self.scope_store.attach_attempt(task.backend_ref)
            except ProjectScopeError as exc:
                recovery_error = redact_secret_values(str(exc))
                self.scope_store.mark_attempt_recovery_pending(
                    task.backend_ref, "run_attachment_incomplete"
                )
                self.store.append_event(
                    task.task_id,
                    level=TaskEventLevel.WARNING,
                    stage="project_scope_attachment",
                    message="Project run-attempt attachment requires reconciliation",
                    state=task.state.value,
                    state_version=task.state_version,
                    data={"error": recovery_error},
                )
            scope_projection = self.scope_store.scope_for_task(task.task_id).to_dict()

        task = self.reconcile_task(task.task_id, stage="backend_attachment")
        polling_request: dict[str, Any] = {
            "operation": "status",
            "task_id": task.task_id,
        }
        if binding is not None:
            polling_request["project_id"] = binding.project_id
        response = compact_task_status(
            task,
            observation=self.backend.query(task.backend_ref),
            open_checkpoint_count=self.store.open_checkpoint_count(task.task_id),
            link_counts=self._link_counts(task.task_id),
            operation="start",
            budget=budget,
            project_scope=scope_projection,
            extra={
                "created": True,
                "idempotent_replay": False,
                "request_hash": task.request_hash,
                "backend_launch_accepted": bool(
                    launch.get("accepted", not launch_error)
                ),
                "backend_launch_error": launch_error,
                "polling": {
                    "tool": "task_query",
                    "request": polling_request,
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
        project_id: str = "",
        budget: int = TASK_RESPONSE_BUDGET_BYTES,
    ) -> dict[str, Any]:
        """Version-guarded cancellation delegated to the backend authority."""
        try:
            task, _scope = self._load_task_scope(task_id, project_id)
        except (KeyError, ValueError, ProjectScopeError) as exc:
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
        scope = self.scope_store.scope_for_task(task.task_id)
        if scope.project_id:
            self.scope_store.require_task_attempt(
                scope.project_id,
                task.task_id,
                task.backend_ref,
            )
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

    def _load_task_scope(
        self, task_id: str, project_id: str
    ) -> tuple[TaskRecord, dict[str, Any]]:
        """Load a task and prove its exact authoritative task-to-run binding."""
        task = self.store.get_task(task_id)
        scope = (
            self.scope_store.require_task(project_id, task.task_id)
            if project_id
            else self.scope_store.scope_for_task(task.task_id)
        )
        if scope.project_id:
            self.scope_store.require_task_attempt(
                scope.project_id,
                task.task_id,
                task.backend_ref,
            )
        return task, scope.to_dict()

    def _resolve_repository_binding(
        self,
        *,
        project_id: str,
        repo_name: str,
        working_directory: str,
    ) -> tuple[RepositoryBinding, str]:
        canonical_name, repo_root, _repo = resolve_repo_identity(self.config, repo_name)
        if working_directory and not path_is_within_repository(
            working_directory, repo_root
        ):
            raise ProjectScopeError(
                "working_directory is outside the bound repository root; "
                "external worktrees are excluded from SCOPE-FOUNDATION-1"
            )
        binding = self.scope_store.resolve_repository(
            project_id=project_id,
            repo_name=canonical_name,
            repository_root=repo_root,
        )
        return binding, canonical_name

    @staticmethod
    def _scoped_request_hash(
        *,
        binding: RepositoryBinding,
        repo_name: str,
        profile_id: str,
        argv: list[str],
        working_directory: str,
        environment: dict[str, str] | None,
        stdin_text: str | None,
        stdin_base64: str | None,
        timeout_seconds: int | None,
        parent_task_id: str,
    ) -> str:
        normalized = normalize_scoped_durable_command_request(
            project_id=binding.project_id,
            resource_id=binding.resource_id,
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
        return normalized_request_hash(normalized)

    @staticmethod
    def _request_conflict_response(
        task: TaskRecord, submitted_hash: str, *, budget: int
    ) -> dict[str, Any]:
        return task_error(
            operation="start",
            error_code="controller_request_hash_conflict",
            error=(
                "controller_request_id "
                f"{task.controller_request_id!r} is already bound to task "
                f"{task.task_id} with a different normalized request hash"
            ),
            task_id=task.task_id,
            state=task.state.value,
            state_version=task.state_version,
            budget=budget,
            extra={
                "existing_request_hash": task.request_hash,
                "submitted_request_hash": submitted_hash,
                "backend_reference": task.backend_ref,
            },
        )

    @staticmethod
    def _scope_conflict_response(*, budget: int) -> dict[str, Any]:
        """Return a non-enumerating cross-project idempotency conflict."""
        response = task_error(
            operation="start",
            error_code="controller_request_scope_conflict",
            error="controller_request_id is already owned by another project scope",
            budget=budget,
        )
        for key in ("task_id", "state", "state_version"):
            response.pop(key, None)
        return finalize(response)

    def _link_counts(self, task_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for link in self.store.list_links(task_id, limit=TASK_LINK_MAX_LIMIT):
            counts[link.link_type.value] = counts.get(link.link_type.value, 0) + 1
        return counts

    def _replay_response(self, task: TaskRecord, *, budget: int) -> dict[str, Any]:
        if not task.is_terminal:
            task = self.reconcile_task(task.task_id, stage="idempotent_replay")
        scope = self.scope_store.scope_for_task(task.task_id).to_dict()
        project_id = str(scope.get("project_id") or "")
        polling_request: dict[str, Any] = {
            "operation": "status",
            "task_id": task.task_id,
        }
        if project_id:
            polling_request["project_id"] = project_id
        return compact_task_status(
            task,
            observation=self.backend.query(task.backend_ref),
            open_checkpoint_count=self.store.open_checkpoint_count(task.task_id),
            link_counts=self._link_counts(task.task_id),
            operation="start",
            budget=budget,
            project_scope=scope,
            extra={
                "created": False,
                "idempotent_replay": True,
                "request_hash": task.request_hash,
                "backend_launch_accepted": bool(task.backend_ref),
                "backend_launch_error": "",
                "polling": {
                    "tool": "task_query",
                    "request": polling_request,
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
            project_scope=self.scope_store.scope_for_task(task.task_id).to_dict(),
            extra={
                "command_id": command_id,
                "already_terminal": already_terminal,
                "cancellation_claimed": task.state is TaskState.CANCELLED,
                "cancellation_pending": task.state is TaskState.CANCELLATION_PENDING,
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
        if isinstance(exc, ProjectScopeError):
            code = "project_scope_mismatch"
        else:
            code = "task_not_found" if isinstance(exc, KeyError) else "invalid_task_id"
        return task_error(
            operation=operation,
            error_code=code,
            error=redact_secret_values(str(exc)).strip("'"),
            task_id=task_id,
            budget=budget,
        )
