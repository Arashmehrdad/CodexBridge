from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from soma.config import AppConfig, resolve_repo
from soma.events import redact_and_truncate
from soma.process_control import (
    process_group_popen_kwargs,
    process_identity,
    process_is_running,
    process_matches_identity,
    terminate_process_tree,
)
from soma.run_store import TERMINAL_STATUSES as CHILD_TERMINAL_STATUSES
from soma.run_store import utc_now

from .models import WorkflowDefinition, WorkflowRecord, WorkflowStatus, WorkflowStepStatus
from .publication import publish_workflow
from .reporter import workflow_run_dir, write_workflow_snapshot
from .store import WorkflowStore


TERMINAL_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.NEEDS_APPROVAL,
    WorkflowStatus.NEEDS_INPUT,
    WorkflowStatus.REPORTED,
}
RECOVERABLE_STATUSES = {
    WorkflowStatus.QUEUED,
    WorkflowStatus.RUNNING,
    WorkflowStatus.CANCELLATION_PENDING,
    WorkflowStatus.RECOVERY_PENDING,
}


def make_workflow_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_workflow_{uuid4().hex[:8]}"


class WorkflowManager:
    def __init__(
        self,
        config: AppConfig,
        config_path: Path | None,
        *,
        worker_launcher: Callable[[Path, str, str, int], int] | None = None,
        process_checker: Callable[[int | None], bool] = process_is_running,
        identity_checker: Callable[[int | None, str | None], bool] = process_matches_identity,
        identity_reader: Callable[[int | None], str] = process_identity,
        termination_fn: Callable[[int | None], dict[str, Any]] = terminate_process_tree,
        job_manager_factory: Callable[[], Any] | None = None,
    ):
        self.config = config
        self.config_path = config_path
        self.store = WorkflowStore(config.resolve_runs_dir())
        self.worker_launcher = worker_launcher or self._launch_worker_process
        self.process_checker = process_checker
        self.identity_checker = identity_checker
        self.identity_reader = identity_reader
        self.termination_fn = termination_fn
        self.job_manager_factory = job_manager_factory

    def start_workflow(self, repo_name: str, objective: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        resolve_repo(self.config, repo_name)
        if self.config_path is None:
            return {"ok": False, "workflow_id": "", "status": WorkflowStatus.FAILED.value, "error": "Durable workflows require a config file path"}
        workflow = WorkflowDefinition.model_validate({"repo_name": repo_name, "objective": objective, "steps": steps})
        workflow_id = make_workflow_id()
        lease_token = uuid4().hex
        persisted = self.store.create_workflow(
            workflow_id=workflow_id,
            repo_name=workflow.repo_name,
            objective=workflow.objective,
            steps=[
                {"id": step.id, "order_index": index, "type": step.type.value, "parameters": step.parameters, "depends_on": list(step.depends_on), "on_failure": step.on_failure.value}
                for index, step in enumerate(workflow.steps)
            ],
            status=WorkflowStatus.QUEUED,
            worker_lease_token=lease_token,
            lease_generation=1,
            launch_attempts=1,
        )
        self._append_event(workflow_id, level="info", stage="queued", message="Workflow queued", data={"step_count": len(workflow.steps)})
        launch_intent = self.store.get_workflow(workflow_id)
        try:
            launcher_pid = self.worker_launcher(self.config_path, workflow_id, lease_token, 1)
            current = self.store.get_workflow(workflow_id)
            launched = self.store.record_worker_launch(
                workflow_id,
                launcher_pid,
                expected_state_version=launch_intent.state_version,
                lease_token=lease_token,
                lease_generation=1,
                launcher_identity=self.identity_reader(launcher_pid),
            )
            if launched is None:
                current = self.store.get_workflow(workflow_id)
            if launched is None and current.worker_lease_token == lease_token and current.lease_generation == 1 and current.status in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}:
                launched = self.store.record_worker_launch(
                    workflow_id,
                    launcher_pid,
                    expected_state_version=current.state_version,
                    lease_token=lease_token,
                    lease_generation=1,
                    launcher_identity=self.identity_reader(launcher_pid),
                )
            current = launched or self.store.get_workflow(workflow_id)
            if not self._owns_generation(current, lease_token, 1) or current.status not in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}:
                self._terminate_if_verified(launcher_pid, self.identity_reader(launcher_pid))
                raise RuntimeError("Initial workflow worker launch lost lease ownership")
            persisted = current
            self._append_event(workflow_id, level="info", stage="worker", message="Workflow worker process started", data={"launcher_pid": launcher_pid, "lease_generation": 1})
        except Exception as exc:
            current = self.store.get_workflow(workflow_id)
            reason = f"Workflow worker launch failed after durable acceptance: {exc}"
            failed = self.store.conditional_update_workflow(
                workflow_id,
                fields={"status": WorkflowStatus.FAILED, "terminal_status": WorkflowStatus.FAILED, "ended_at": utc_now(), "failure_summary": reason, "recommended_next_action": "Review worker startup and retry the workflow."},
                expected_statuses=(current.status,),
                expected_state_version=current.state_version,
                expected_lease_token=current.worker_lease_token,
                expected_lease_generation=current.lease_generation,
                reject_terminal=True,
            )
            if failed is not None:
                self._append_event(workflow_id, level="error", stage="launch_failed", message=reason)
                self._finalize_terminal_workflow(failed)
            return {"ok": False, "workflow_id": workflow_id, "repo_name": repo_name, "status": WorkflowStatus.FAILED.value, "step_count": len(persisted.steps), "error": reason}
        return {"ok": True, "workflow_id": workflow_id, "repo_name": repo_name, "status": persisted.status.value, "step_count": len(persisted.steps), "error": ""}

    def get_status(self, workflow_id: str) -> dict[str, Any]:
        try:
            workflow = self.store.get_workflow(workflow_id)
        except KeyError as exc:
            return self._not_found(workflow_id, exc)
        worker_running = self._identity_state(workflow.worker_pid, workflow.worker_identity) == "active" if workflow.worker_identity else self.process_checker(workflow.worker_pid or workflow.launcher_pid)
        return redact_and_truncate({
            "ok": True,
            "workflow_id": workflow.workflow_id,
            "repo_name": workflow.repo_name,
            "objective": workflow.objective,
            "status": workflow.status.value,
            "terminal_status": workflow.terminal_status.value if workflow.terminal_status else "",
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
            "started_at": workflow.started_at,
            "ended_at": workflow.ended_at,
            "worker_pid": workflow.worker_pid,
            "worker_running": worker_running,
            "launcher_identity_recorded": bool(workflow.launcher_identity),
            "worker_identity_recorded": bool(workflow.worker_identity),
            "lease_generation": workflow.lease_generation,
            "state_version": workflow.state_version,
            "launch_attempts": workflow.launch_attempts,
            "active_child_run_id": workflow.active_child_run_id,
            "failure_summary": workflow.failure_summary,
            "recommended_next_action": workflow.recommended_next_action,
            "artifact_paths": [str(path) for path in workflow.artifact_paths],
            "publication_status": workflow.publication_status,
            "publication_hash": workflow.publication_hash,
            "published_at": workflow.published_at,
            "publication_error": workflow.publication_error,
            "steps": [{"id": step.id, "type": step.type.value, "status": step.status.value, "depends_on": list(step.depends_on), "child_run_id": step.child_run_id, "summary": step.summary, "error": step.error} for step in workflow.steps],
            "error": "",
        })

    def get_events(self, workflow_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.store.get_events(workflow_id, limit)]

    def get_result(self, workflow_id: str) -> dict[str, Any]:
        try:
            workflow = self.store.get_workflow(workflow_id)
        except KeyError as exc:
            return self._not_found(workflow_id, exc)
        snapshot = workflow.to_dict()
        snapshot["ok"] = True
        snapshot["error"] = ""
        return redact_and_truncate(snapshot)

    def cancel_workflow(self, workflow_id: str) -> dict[str, Any]:
        try:
            workflow = self.store.get_workflow(workflow_id)
        except KeyError as exc:
            return self._not_found(workflow_id, exc)
        if workflow.status in TERMINAL_STATUSES:
            return {"ok": True, "workflow_id": workflow_id, "status": workflow.status.value, "cancelled": False, "error": ""}
        if workflow.status != WorkflowStatus.CANCELLATION_PENDING:
            requested = self.store.request_cancellation(
                workflow_id,
                expected_statuses=(workflow.status,),
                expected_state_version=workflow.state_version,
                expected_lease_token=workflow.worker_lease_token,
                expected_lease_generation=workflow.lease_generation,
                result={"cancelled_by_request": True, "active_child_run_id": workflow.active_child_run_id},
            )
            if requested is None:
                workflow = self.store.get_workflow(workflow_id)
            else:
                workflow = requested
        final = self._reconcile_cancellation(workflow)
        cancelled = final.terminal_status == WorkflowStatus.CANCELLED
        return {
            "ok": cancelled,
            "workflow_id": workflow_id,
            "status": final.status.value,
            "cancelled": cancelled,
            "child_run_id": workflow.active_child_run_id,
            "child_cancel_result": final.result.get("child_cancel_result"),
            "error": "" if cancelled else final.failure_summary,
        }

    def reconcile_startup(self) -> int:
        if self.config_path is None:
            return 0
        relaunched = 0
        for workflow in self.store.iter_recoverable_workflows():
            if workflow.status in TERMINAL_STATUSES:
                self._finalize_terminal_workflow(workflow)
                continue
            if workflow.status == WorkflowStatus.CANCELLATION_PENDING:
                self._reconcile_cancellation(workflow)
                continue
            if workflow.status == WorkflowStatus.RECOVERY_PENDING:
                continue
            inconsistency = self._child_ownership_problem(workflow)
            if inconsistency:
                self._mark_recovery_pending(workflow, inconsistency)
                continue
            worker_state = self._identity_state(workflow.worker_pid, workflow.worker_identity)
            launcher_state = self._identity_state(workflow.launcher_pid, workflow.launcher_identity)
            if worker_state == "active" or launcher_state == "active":
                if worker_state == "active":
                    adopted = self.store.adopt_worker(workflow.workflow_id, expected_state_version=workflow.state_version, lease_token=workflow.worker_lease_token, lease_generation=workflow.lease_generation, expected_heartbeat_at=workflow.heartbeat_at)
                    if adopted is not None:
                        self._append_event(workflow.workflow_id, level="info", stage="reconcile", message="Active workflow worker identity verified after restart", data={"worker_pid": workflow.worker_pid})
                continue
            if worker_state == "uncertain" or launcher_state == "uncertain":
                self._mark_recovery_pending(workflow, "A recorded workflow PID is live but has no verifiable process-start identity; no relaunch or raw-PID termination was attempted.")
                continue
            if workflow.launch_attempts >= 2:
                reason = "Workflow exhausted its bounded worker launch attempts"
                failed = self.store.conditional_update_workflow(workflow.workflow_id, fields={"status": WorkflowStatus.FAILED, "terminal_status": WorkflowStatus.FAILED, "ended_at": utc_now(), "failure_summary": reason, "recommended_next_action": "Review workflow worker startup before retrying."}, expected_statuses=(workflow.status,), expected_state_version=workflow.state_version, expected_lease_token=workflow.worker_lease_token, expected_lease_generation=workflow.lease_generation, expected_heartbeat_at=workflow.heartbeat_at, reject_terminal=True)
                if failed is not None:
                    self._append_event(workflow.workflow_id, level="error", stage="reconcile", message=reason)
                    self._finalize_terminal_workflow(failed)
                continue
            new_lease_token = uuid4().hex
            reservation = self.store.reserve_next_launch(workflow.workflow_id, expected_statuses=(workflow.status,), expected_state_version=workflow.state_version, expected_lease_token=workflow.worker_lease_token, expected_lease_generation=workflow.lease_generation, expected_heartbeat_at=workflow.heartbeat_at, new_lease_token=new_lease_token)
            if reservation is None:
                continue
            try:
                launcher_pid = self.worker_launcher(self.config_path, workflow.workflow_id, new_lease_token, reservation.lease_generation)
                identity = self.identity_reader(launcher_pid)
                current = self.store.record_worker_launch(workflow.workflow_id, launcher_pid, expected_state_version=reservation.state_version, lease_token=new_lease_token, lease_generation=reservation.lease_generation, launcher_identity=identity)
                if current is None:
                    current = self.store.get_workflow(workflow.workflow_id)
                    if self._owns_generation(current, new_lease_token, reservation.lease_generation) and current.status in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}:
                        current = self.store.record_worker_launch(workflow.workflow_id, launcher_pid, expected_state_version=current.state_version, lease_token=new_lease_token, lease_generation=reservation.lease_generation, launcher_identity=identity) or current
                if not self._owns_generation(current, new_lease_token, reservation.lease_generation) or current.status not in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}:
                    self._terminate_if_verified(launcher_pid, identity)
                    continue
                self._append_event(workflow.workflow_id, level="warning", stage="reconcile", message="Workflow worker relaunched with a new lease generation", data={"previous_worker_pid": workflow.worker_pid, "launcher_pid": launcher_pid, "previous_lease_generation": workflow.lease_generation, "lease_generation": reservation.lease_generation})
                relaunched += 1
            except Exception as exc:
                current = self.store.get_workflow(workflow.workflow_id)
                if self._owns_generation(current, new_lease_token, reservation.lease_generation):
                    failed = self.store.conditional_update_workflow(workflow.workflow_id, fields={"status": WorkflowStatus.FAILED, "terminal_status": WorkflowStatus.FAILED, "ended_at": utc_now(), "failure_summary": f"Workflow worker relaunch failed: {exc}", "recommended_next_action": "Review workflow worker startup before retrying."}, expected_statuses=(current.status,), expected_state_version=current.state_version, expected_lease_token=new_lease_token, expected_lease_generation=reservation.lease_generation, reject_terminal=True)
                    if failed is not None:
                        self._finalize_terminal_workflow(failed)
        return relaunched

    def _reconcile_cancellation(self, workflow: WorkflowRecord) -> WorkflowRecord:
        details: dict[str, Any] = {"cancelled_by_request": True}
        reasons: list[str] = []
        child_id = workflow.active_child_run_id
        if child_id:
            details["child_run_id"] = child_id
            try:
                child_manager = self._job_manager()
                cancel_result = child_manager.cancel_run(child_id)
                details["child_cancel_result"] = cancel_result
                child_status = child_manager.get_status(child_id)
                if str(child_status.get("status") or "") not in CHILD_TERMINAL_STATUSES:
                    reasons.append("Child cancellation is pending confirmation.")
            except Exception as exc:
                reasons.append(f"Child cancellation confirmation failed: {exc}")
        for role, pid, identity in (("worker", workflow.worker_pid, workflow.worker_identity), ("launcher", workflow.launcher_pid, workflow.launcher_identity)):
            if not pid or any(item.get("pid") == pid for item in details.get("termination_reports", [])):
                continue
            state = self._identity_state(pid, identity)
            if state == "uncertain":
                reasons.append(f"{role} PID {pid} is live but has no verifiable identity; termination was not attempted.")
                continue
            if state == "active":
                report = self._terminate_if_verified(pid, identity)
                report["role"] = role
                details.setdefault("termination_reports", []).append(report)
                if not report.get("terminated"):
                    reasons.append(f"{role} process termination was not confirmed.")
        if reasons:
            updated = self.store.mark_cancellation_retry(workflow.workflow_id, expected_state_version=workflow.state_version, expected_lease_token=workflow.worker_lease_token, expected_lease_generation=workflow.lease_generation, result={**workflow.result, **details, "reasons": reasons}, reason=" ".join(reasons))
            return updated or self.store.get_workflow(workflow.workflow_id)
        current = self.store.get_workflow(workflow.workflow_id)
        final = self.store.finalize_cancellation(workflow.workflow_id, expected_state_version=current.state_version, expected_lease_token=current.worker_lease_token, expected_lease_generation=current.lease_generation, result={**current.result, **details, "confirmed": True})
        if final is None:
            return self.store.get_workflow(workflow.workflow_id)
        self._append_event(workflow.workflow_id, level="warning", stage="cancelled", message="Workflow cancellation confirmed", data=details)
        return self._finalize_terminal_workflow(final)

    def _child_ownership_problem(self, workflow: WorkflowRecord) -> str:
        running_steps = [
            step for step in workflow.steps if step.status == WorkflowStepStatus.RUNNING
        ]
        if len(running_steps) > 1:
            return "Workflow has multiple running steps and cannot safely choose child ownership."
        if not running_steps:
            if workflow.active_child_run_id:
                return "Workflow has an active child ID but no running step owns it."
            return ""
        step = running_steps[0]
        if step.type.value == "local_summary":
            if step.child_run_id or workflow.active_child_run_id:
                return "A local summary step has external child ownership and cannot be safely resumed."
            return ""
        if not step.child_run_id:
            return f"Running external step {step.id} has no durable child run ID."
        if workflow.active_child_run_id != step.child_run_id:
            return "Workflow active child ID does not match its running external step."
        return ""

    def _job_manager(self) -> Any:
        if self.job_manager_factory is not None:
            return self.job_manager_factory()
        from soma.job_manager import JobManager

        return JobManager(self.config, self.config_path)

    def _identity_state(self, pid: int | None, identity: str) -> str:
        if not pid:
            return "absent"
        if identity:
            return "active" if self.identity_checker(pid, identity) else "absent"
        return "uncertain" if self.process_checker(pid) else "absent"

    def _terminate_if_verified(self, pid: int | None, identity: str) -> dict[str, Any]:
        if not pid or not identity or not self.identity_checker(pid, identity):
            return {"pid": int(pid or 0), "terminated": False, "termination_attempted": False, "error": "Process identity was not verified."}
        report = self.termination_fn(pid)
        if report.get("terminated") and self.identity_checker(pid, identity):
            report["terminated"] = False
            report["error"] = "Process identity remains active after termination attempt."
        return report

    @staticmethod
    def _owns_generation(workflow: WorkflowRecord, lease_token: str, generation: int) -> bool:
        return workflow.worker_lease_token == lease_token and workflow.lease_generation == generation

    def _mark_recovery_pending(self, workflow: WorkflowRecord, reason: str) -> None:
        changed = self.store.mark_recovery_pending(workflow.workflow_id, expected_statuses=(workflow.status,), expected_state_version=workflow.state_version, expected_lease_token=workflow.worker_lease_token, expected_lease_generation=workflow.lease_generation, reason=reason)
        if changed is not None:
            self._append_event(workflow.workflow_id, level="error", stage="recovery_pending", message=reason)

    def _launch_worker_process(self, config_path: Path, workflow_id: str, lease_token: str, lease_generation: int) -> int:
        command = [sys.executable, "-m", "soma.workflows.worker", "--config", str(config_path), "--workflow-id", workflow_id, "--lease-token", lease_token, "--lease-generation", str(int(lease_generation))]
        process = subprocess.Popen(command, cwd=Path.cwd(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=os.name != "nt", **process_group_popen_kwargs())
        return int(process.pid)

    def _append_event(self, workflow_id: str, *, level: str, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.store.append_event(workflow_id, level=level, stage=stage, message=message, data=redact_and_truncate(data or {}), update_workflow_metadata=False)
        workflow = self.store.get_workflow(workflow_id)
        write_workflow_snapshot(self.config.resolve_runs_dir(), workflow, [event.to_dict() for event in self.store.get_events(workflow_id, 500)])

    def _finalize_terminal_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        return publish_workflow(self.store, self.config.resolve_runs_dir(), workflow.workflow_id)

    @staticmethod
    def _not_found(workflow_id: str, exc: Exception) -> dict[str, Any]:
        return {"ok": False, "workflow_id": workflow_id, "status": "not_found", "error": str(exc)}


def get_workflow_run_dir(config: AppConfig, workflow_id: str) -> Path:
    return workflow_run_dir(config.resolve_runs_dir(), workflow_id)
