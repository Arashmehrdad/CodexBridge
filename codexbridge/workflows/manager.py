from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from codexbridge.config import AppConfig, resolve_repo
from codexbridge.events import redact_and_truncate
from codexbridge.process_control import (
    process_group_popen_kwargs,
    process_is_running,
    process_matches_identity,
    terminate_process_tree,
)
from codexbridge.run_store import utc_now

from .models import (
    WorkflowDefinition,
    WorkflowRecord,
    WorkflowStatus,
)
from .reporter import generate_workflow_report, write_workflow_snapshot, workflow_run_dir
from .store import WorkflowStore


TERMINAL_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.NEEDS_APPROVAL,
    WorkflowStatus.NEEDS_INPUT,
    WorkflowStatus.REPORTED,
}
RECOVERABLE_STATUSES = {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}


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
    ):
        self.config = config
        self.config_path = config_path
        self.store = WorkflowStore(config.resolve_runs_dir())
        self.worker_launcher = worker_launcher or self._launch_worker_process
        self.process_checker = process_checker

    def start_workflow(
        self,
        repo_name: str,
        objective: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resolve_repo(self.config, repo_name)
        if self.config_path is None:
            return {
                "ok": False,
                "workflow_id": "",
                "status": WorkflowStatus.FAILED.value,
                "error": "Durable workflows require a config file path",
            }
        workflow = WorkflowDefinition.model_validate(
            {
                "repo_name": repo_name,
                "objective": objective,
                "steps": steps,
            }
        )
        workflow_id = make_workflow_id()
        lease_token = uuid4().hex
        persisted = self.store.create_workflow(
            workflow_id=workflow_id,
            repo_name=workflow.repo_name,
            objective=workflow.objective,
            steps=[
                {
                    "id": step.id,
                    "order_index": index,
                    "type": step.type.value,
                    "parameters": step.parameters,
                    "depends_on": list(step.depends_on),
                    "on_failure": step.on_failure.value,
                }
                for index, step in enumerate(workflow.steps)
            ],
            status=WorkflowStatus.QUEUED,
            worker_lease_token=lease_token,
            lease_generation=1,
            launch_attempts=1,
        )
        self._append_event(
            workflow_id,
            level="info",
            stage="queued",
            message="Workflow queued",
            data={"step_count": len(workflow.steps)},
        )
        launch_intent = self.store.get_workflow(workflow_id)
        try:
            launcher_pid = self.worker_launcher(
                self.config_path, workflow_id, lease_token, 1
            )
            launched = self.store.record_worker_launch(
                workflow_id,
                launcher_pid,
                expected_state_version=launch_intent.state_version,
                lease_token=lease_token,
                lease_generation=1,
            )
            current = launched or self.store.get_workflow(workflow_id)
            if not (
                current.worker_lease_token == lease_token
                and current.lease_generation == 1
                and current.status in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}
            ):
                terminate_process_tree(launcher_pid)
                raise RuntimeError("Initial workflow worker launch lost lease ownership")
            persisted = current
            self._append_event(
                workflow_id,
                level="info",
                stage="worker",
                message="Workflow worker process started",
                data={"launcher_pid": launcher_pid, "lease_generation": 1},
            )
        except Exception as exc:
            current = self.store.get_workflow(workflow_id)
            reason = f"Workflow worker launch failed after durable acceptance: {exc}"
            failed = self.store.conditional_update_workflow(
                workflow_id,
                fields={
                    "status": WorkflowStatus.FAILED,
                    "terminal_status": WorkflowStatus.FAILED,
                    "ended_at": utc_now(),
                    "failure_summary": reason,
                    "recommended_next_action": "Review worker startup and retry the workflow.",
                },
                expected_statuses=(current.status,),
                expected_state_version=current.state_version,
                expected_lease_token=current.worker_lease_token,
                expected_lease_generation=current.lease_generation,
                reject_terminal=True,
            )
            if failed is not None:
                self._append_event(
                    workflow_id,
                    level="error",
                    stage="launch_failed",
                    message=reason,
                )
                self._finalize_terminal_workflow(failed)
            return {
                "ok": False,
                "workflow_id": workflow_id,
                "repo_name": repo_name,
                "status": WorkflowStatus.FAILED.value,
                "step_count": len(persisted.steps),
                "error": reason,
            }
        return {
            "ok": True,
            "workflow_id": workflow_id,
            "repo_name": repo_name,
            "status": persisted.status.value,
            "step_count": len(persisted.steps),
            "error": "",
        }

    def get_status(self, workflow_id: str) -> dict[str, Any]:
        try:
            workflow = self.store.get_workflow(workflow_id)
        except KeyError as exc:
            return self._not_found(workflow_id, exc)
        return redact_and_truncate(
            {
                "ok": True,
                "workflow_id": workflow.workflow_id,
                "repo_name": workflow.repo_name,
                "objective": workflow.objective,
                "status": workflow.status.value,
                "terminal_status": workflow.terminal_status.value
                if workflow.terminal_status
                else "",
                "created_at": workflow.created_at,
                "updated_at": workflow.updated_at,
                "started_at": workflow.started_at,
                "ended_at": workflow.ended_at,
                "worker_pid": workflow.worker_pid,
                "worker_running": (
                    process_matches_identity(
                        workflow.worker_pid, workflow.worker_identity
                    )
                    if workflow.worker_identity
                    else self.process_checker(
                        workflow.launcher_pid or workflow.worker_pid
                    )
                ),
                "lease_generation": workflow.lease_generation,
                "state_version": workflow.state_version,
                "launch_attempts": workflow.launch_attempts,
                "active_child_run_id": workflow.active_child_run_id,
                "failure_summary": workflow.failure_summary,
                "recommended_next_action": workflow.recommended_next_action,
                "artifact_paths": [str(path) for path in workflow.artifact_paths],
                "steps": [
                    {
                        "id": step.id,
                        "type": step.type.value,
                        "status": step.status.value,
                        "depends_on": list(step.depends_on),
                        "child_run_id": step.child_run_id,
                        "summary": step.summary,
                        "error": step.error,
                    }
                    for step in workflow.steps
                ],
                "error": "",
            }
        )

    def get_events(self, workflow_id: str, limit: int = 100) -> list[dict[str, Any]]:
        try:
            events = self.store.get_events(workflow_id, limit)
        except KeyError as exc:
            raise exc
        return [event.to_dict() for event in events]

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
            return {
                "ok": True,
                "workflow_id": workflow_id,
                "status": workflow.status.value,
                "cancelled": False,
                "error": "",
            }

        cancelled = self.store.cancel_workflow(
            workflow_id,
            expected_statuses=(workflow.status,),
            expected_state_version=workflow.state_version,
            expected_lease_token=workflow.worker_lease_token,
            expected_lease_generation=workflow.lease_generation,
            result={
                "cancelled_by_request": True,
                "active_child_run_id": workflow.active_child_run_id,
            },
        )
        if cancelled is None:
            winner = self.store.get_workflow(workflow_id)
            return {
                "ok": winner.status in TERMINAL_STATUSES,
                "workflow_id": workflow_id,
                "status": winner.status.value,
                "cancelled": winner.terminal_status == WorkflowStatus.CANCELLED,
                "error": "Cancellation lost a concurrent workflow transition",
            }

        child_cancelled = None
        if workflow.active_child_run_id:
            try:
                from codexbridge.job_manager import JobManager

                child_cancelled = JobManager(
                    self.config, self.config_path
                ).cancel_run(workflow.active_child_run_id)
            except Exception as exc:
                child_cancelled = {"ok": False, "error": str(exc)}

        termination_reports: list[dict[str, Any]] = []
        for role, pid in (
            ("worker", workflow.worker_pid),
            ("launcher", workflow.launcher_pid),
        ):
            if pid and not any(report.get("pid") == pid for report in termination_reports):
                report = terminate_process_tree(pid)
                report["role"] = role
                termination_reports.append(report)

        current = self.store.get_workflow(workflow_id)
        enriched = self.store.conditional_update_workflow(
            workflow_id,
            fields={
                "result_json": {
                    "cancelled_by_request": True,
                    "child_cancelled": child_cancelled,
                    "termination_reports": termination_reports,
                }
            },
            expected_statuses=(WorkflowStatus.CANCELLED,),
            expected_state_version=current.state_version,
            expected_lease_token=current.worker_lease_token,
            expected_lease_generation=current.lease_generation,
        )
        updated = enriched or current
        self._append_event(
            workflow_id,
            level="warning",
            stage="cancelled",
            message="Workflow cancelled",
            data={
                "active_child_run_id": workflow.active_child_run_id,
                "termination_reports": termination_reports,
            },
        )
        self._finalize_terminal_workflow(updated)
        final = self.store.get_workflow(workflow_id)
        return {
            "ok": True,
            "workflow_id": workflow_id,
            "status": final.status.value,
            "cancelled": True,
            "child_run_id": workflow.active_child_run_id,
            "child_cancel_result": child_cancelled,
            "error": "",
        }

    def reconcile_startup(self) -> int:
        if self.config_path is None:
            return 0
        relaunched = 0
        now = datetime.now(timezone.utc)
        for workflow in self.store.iter_recoverable_workflows():
            heartbeat_age = None
            if workflow.heartbeat_at:
                heartbeat_age = (
                    now - datetime.fromisoformat(workflow.heartbeat_at)
                ).total_seconds()
            worker_verified = process_matches_identity(
                workflow.worker_pid, workflow.worker_identity
            )
            launcher_running = self.process_checker(workflow.launcher_pid)

            if worker_verified:
                adopted = self.store.adopt_worker(
                    workflow.workflow_id,
                    expected_state_version=workflow.state_version,
                    lease_token=workflow.worker_lease_token,
                    lease_generation=workflow.lease_generation,
                    expected_heartbeat_at=workflow.heartbeat_at,
                )
                if adopted is not None:
                    self._append_event(
                        workflow.workflow_id,
                        level="info",
                        stage="reconcile",
                        message="Active workflow worker identity verified after restart",
                        data={"worker_pid": workflow.worker_pid},
                    )
                continue

            if workflow.status == WorkflowStatus.QUEUED and launcher_running:
                continue

            if workflow.launch_attempts >= 2:
                reason = "Workflow exhausted its bounded worker launch attempts"
                failed = self.store.conditional_update_workflow(
                    workflow.workflow_id,
                    fields={
                        "status": WorkflowStatus.FAILED,
                        "terminal_status": WorkflowStatus.FAILED,
                        "ended_at": utc_now(),
                        "failure_summary": reason,
                        "recommended_next_action": "Review workflow worker startup before retrying.",
                    },
                    expected_statuses=(workflow.status,),
                    expected_state_version=workflow.state_version,
                    expected_lease_token=workflow.worker_lease_token,
                    expected_lease_generation=workflow.lease_generation,
                    expected_heartbeat_at=workflow.heartbeat_at,
                    reject_terminal=True,
                )
                if failed is not None:
                    self._append_event(
                        workflow.workflow_id,
                        level="error",
                        stage="reconcile",
                        message=reason,
                    )
                    self._finalize_terminal_workflow(failed)
                continue

            new_lease_token = uuid4().hex
            reservation = self.store.reserve_next_launch(
                workflow.workflow_id,
                expected_statuses=(workflow.status,),
                expected_state_version=workflow.state_version,
                expected_lease_token=workflow.worker_lease_token,
                expected_lease_generation=workflow.lease_generation,
                expected_heartbeat_at=workflow.heartbeat_at,
                new_lease_token=new_lease_token,
            )
            if reservation is None:
                continue
            try:
                launcher_pid = self.worker_launcher(
                    self.config_path,
                    workflow.workflow_id,
                    new_lease_token,
                    reservation.lease_generation,
                )
                launched = self.store.record_worker_launch(
                    workflow.workflow_id,
                    launcher_pid,
                    expected_state_version=reservation.state_version,
                    lease_token=new_lease_token,
                    lease_generation=reservation.lease_generation,
                )
                current = launched or self.store.get_workflow(workflow.workflow_id)
                if not (
                    current.worker_lease_token == new_lease_token
                    and current.lease_generation == reservation.lease_generation
                    and current.status in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}
                ):
                    terminate_process_tree(launcher_pid)
                    continue
                self._append_event(
                    workflow.workflow_id,
                    level="warning",
                    stage="reconcile",
                    message="Workflow worker relaunched with a new lease generation",
                    data={
                        "previous_worker_pid": workflow.worker_pid,
                        "launcher_pid": launcher_pid,
                        "previous_lease_generation": workflow.lease_generation,
                        "lease_generation": reservation.lease_generation,
                        "heartbeat_age_seconds": heartbeat_age,
                    },
                )
                relaunched += 1
            except Exception as exc:
                current = self.store.get_workflow(workflow.workflow_id)
                if (
                    current.worker_lease_token == new_lease_token
                    and current.lease_generation == reservation.lease_generation
                ):
                    reason = f"Workflow worker relaunch failed: {exc}"
                    failed = self.store.conditional_update_workflow(
                        workflow.workflow_id,
                        fields={
                            "status": WorkflowStatus.FAILED,
                            "terminal_status": WorkflowStatus.FAILED,
                            "ended_at": utc_now(),
                            "failure_summary": reason,
                            "recommended_next_action": "Review workflow worker startup before retrying.",
                        },
                        expected_statuses=(current.status,),
                        expected_state_version=current.state_version,
                        expected_lease_token=new_lease_token,
                        expected_lease_generation=reservation.lease_generation,
                        reject_terminal=True,
                    )
                    if failed is not None:
                        self._append_event(
                            workflow.workflow_id,
                            level="error",
                            stage="reconcile",
                            message=reason,
                        )
                        self._finalize_terminal_workflow(failed)
        return relaunched

    def _launch_worker_process(self, config_path: Path, workflow_id: str) -> int:
        command = [
            sys.executable,
            "-m",
            "codexbridge.workflows.worker",
            "--config",
            str(config_path),
            "--workflow-id",
            workflow_id,
        ]
        process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=os.name != "nt",
            **process_group_popen_kwargs(),
        )
        return int(process.pid)

    def _append_event(
        self,
        workflow_id: str,
        *,
        level: str,
        stage: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.store.append_event(
            workflow_id,
            level=level,
            stage=stage,
            message=message,
            data=redact_and_truncate(data or {}),
        )
        workflow = self.store.get_workflow(workflow_id)
        write_workflow_snapshot(
            self.config.resolve_runs_dir(),
            workflow,
            [event.to_dict() for event in self.store.get_events(workflow_id, 500)],
        )

    def _finalize_terminal_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        report = generate_workflow_report(self.config.resolve_runs_dir(), workflow)
        artifact_paths = [
            *[str(path) for path in workflow.artifact_paths],
            str(report.report_path),
            str(report.resume_prompt_path),
            str(report.manifest_path),
        ]
        updated = self.store.update_workflow(
            workflow.workflow_id,
            status=WorkflowStatus.REPORTED,
            terminal_status=workflow.terminal_status or workflow.status,
            artifact_paths_json=artifact_paths,
        )
        self._append_event(
            workflow.workflow_id,
            level="info",
            stage="reported",
            message="Workflow report artifacts written",
            data={"manifest_path": str(report.manifest_path)},
        )
        return updated

    @staticmethod
    def _not_found(workflow_id: str, exc: Exception) -> dict[str, Any]:
        return {
            "ok": False,
            "workflow_id": workflow_id,
            "status": "not_found",
            "error": str(exc),
        }


def get_workflow_run_dir(config: AppConfig, workflow_id: str) -> Path:
    return workflow_run_dir(config.resolve_runs_dir(), workflow_id)
