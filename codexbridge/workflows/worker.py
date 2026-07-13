from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from codexbridge.config import AppConfig, load_config
from codexbridge.events import redact_and_truncate
from codexbridge.job_manager import JobManager, make_run_id
from codexbridge.process_control import process_identity
from codexbridge.run_store import TERMINAL_STATUSES, utc_now

from .manager import WorkflowManager
from .models import (
    CodexImplementParameters,
    GitReadonlyParameters,
    LocalSummaryParameters,
    ProjectCommandParameters,
    PytestPathParameters,
    StepOnFailure,
    WorkflowStatus,
    WorkflowStepRecord,
    WorkflowStepStatus,
)
from .reporter import write_workflow_snapshot, workflow_run_dir
from .store import WorkflowStore


class WorkflowWorker:
    def __init__(
        self,
        config_path: Path,
        workflow_id: str,
        *,
        lease_token: str | None = None,
        lease_generation: int | None = None,
        poll_interval_seconds: float = 0.2,
        sleep_fn=time.sleep,
    ):
        self.config_path = config_path
        self.config: AppConfig = load_config(config_path)
        self.workflow_id = workflow_id
        self.store = WorkflowStore(self.config.resolve_runs_dir())
        initial = self.store.get_workflow(workflow_id)
        self.lease_token = (
            lease_token if lease_token is not None else initial.worker_lease_token
        )
        self.lease_generation = (
            int(lease_generation)
            if lease_generation is not None
            else int(initial.lease_generation)
        )
        self.job_manager = JobManager(self.config, config_path)
        self.workflow_manager = WorkflowManager(self.config, config_path)
        self.poll_interval_seconds = poll_interval_seconds
        self.sleep_fn = sleep_fn

    def execute(self) -> int:
        workflow = self.store.get_workflow(self.workflow_id)
        if workflow.status in {WorkflowStatus.REPORTED, WorkflowStatus.CANCELLED}:
            return 0
        if workflow.status == WorkflowStatus.QUEUED:
            worker_pid = os_getpid()
            worker_identity = process_identity(worker_pid)
            if not self.store.claim_worker(
                self.workflow_id,
                lease_token=self.lease_token,
                lease_generation=self.lease_generation,
                expected_state_version=workflow.state_version,
                worker_pid=worker_pid,
                worker_identity=worker_identity,
            ):
                return 1
            workflow = self.store.get_workflow(self.workflow_id)
            self._event(
                "info",
                "running",
                "Workflow worker claimed durable execution lease",
                {"worker_pid": worker_pid, "worker_identity_recorded": bool(worker_identity)},
            )
        elif workflow.status == WorkflowStatus.RUNNING:
            return 1
        while True:
            workflow = self.store.get_workflow(self.workflow_id)
            if workflow.status == WorkflowStatus.REPORTED:
                return 0
            if workflow.status in {
                WorkflowStatus.CANCELLED,
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.NEEDS_APPROVAL,
                WorkflowStatus.NEEDS_INPUT,
            }:
                self.workflow_manager._finalize_terminal_workflow(workflow)
                return 0
            if not self.store.heartbeat_worker(
                self.workflow_id,
                lease_token=self.lease_token,
                lease_generation=self.lease_generation,
                worker_pid=os_getpid(),
            ):
                return 1
            if workflow.active_child_run_id:
                if self._reconcile_active_child(workflow):
                    continue
            if self._skip_blocked_steps():
                continue
            next_step = self._next_pending_step()
            if next_step is None:
                if self._all_steps_terminal():
                    self._complete_workflow()
                    continue
                self.sleep_fn(self.poll_interval_seconds)
                continue
            self._start_step(next_step)

    def _reconcile_active_child(self, workflow) -> bool:
        active_step = next(
            (step for step in workflow.steps if step.child_run_id == workflow.active_child_run_id),
            None,
        )
        if active_step is None:
            self.store.update_workflow(self.workflow_id, active_child_run_id=None)
            return True
        status = self.job_manager.get_status(workflow.active_child_run_id)
        state = str(status.get("status") or "")
        if state not in TERMINAL_STATUSES:
            self.sleep_fn(self.poll_interval_seconds)
            return True
        result = self.job_manager.get_result(workflow.active_child_run_id)
        terminal_now = utc_now()
        if state == "completed":
            self.store.update_step(
                self.workflow_id,
                active_step.id,
                status=WorkflowStepStatus.PASSED,
                ended_at=terminal_now,
                summary=str(result.get("summary") or "Step completed"),
                error="",
                result_json=redact_and_truncate(result),
            )
            self.store.update_workflow(
                self.workflow_id,
                active_child_run_id=None,
            )
            self._event(
                "info",
                "step_completed",
                f"Workflow step {active_step.id} passed",
                {"child_run_id": active_step.child_run_id},
            )
            return True
        if state == "needs_input":
            self._fail_step(
                active_step,
                summary=str(result.get("summary") or "Child run needs input"),
                error=str(result.get("error") or "Child run needs input"),
                result=result,
                workflow_status=WorkflowStatus.NEEDS_INPUT,
                recommended_next_action="Review the child run result and provide the requested input before resuming.",
            )
            return True
        if state == "cancelled" and self.store.get_workflow(self.workflow_id).status == WorkflowStatus.CANCELLED:
            self.store.update_step(
                self.workflow_id,
                active_step.id,
                status=WorkflowStepStatus.CANCELLED,
                ended_at=terminal_now,
                summary="Cancelled with workflow",
                error="Workflow cancelled",
                result_json=redact_and_truncate(result),
            )
            self.store.update_workflow(self.workflow_id, active_child_run_id=None)
            return True
        self._fail_step(
            active_step,
            summary=str(result.get("summary") or f"Child run ended with status {state}"),
            error=str(result.get("error") or f"Child run status {state}"),
            result=result,
        )
        return True

    def _next_pending_step(self) -> WorkflowStepRecord | None:
        workflow = self.store.get_workflow(self.workflow_id)
        status_by_id = {step.id: step.status for step in workflow.steps}
        for step in workflow.steps:
            if step.status != WorkflowStepStatus.PENDING:
                continue
            if all(status_by_id.get(dep) == WorkflowStepStatus.PASSED for dep in step.depends_on):
                return step
        return None

    def _skip_blocked_steps(self) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        status_by_id = {step.id: step.status for step in workflow.steps}
        updated = False
        for step in workflow.steps:
            if step.status != WorkflowStepStatus.PENDING or not step.depends_on:
                continue
            dependency_states = [status_by_id.get(dep) for dep in step.depends_on]
            if all(
                state in {
                    WorkflowStepStatus.PASSED,
                    WorkflowStepStatus.FAILED,
                    WorkflowStepStatus.SKIPPED,
                    WorkflowStepStatus.CANCELLED,
                }
                for state in dependency_states
            ) and any(state != WorkflowStepStatus.PASSED for state in dependency_states):
                self.store.update_step(
                    self.workflow_id,
                    step.id,
                    status=WorkflowStepStatus.SKIPPED,
                    ended_at=utc_now(),
                    summary="Skipped because a dependency did not pass",
                    error="Blocked by failed dependency",
                )
                self._event(
                    "warning",
                    "step_skipped",
                    f"Workflow step {step.id} skipped due to dependency state",
                    {"depends_on": step.depends_on},
                )
                updated = True
        return updated

    def _start_step(self, step: WorkflowStepRecord) -> None:
        self.store.update_step(
            self.workflow_id,
            step.id,
            status=WorkflowStepStatus.RUNNING,
            started_at=utc_now(),
            summary="Step running",
            error="",
        )
        self._event("info", "step_running", f"Workflow step {step.id} started")
        if step.type.value == "local_summary":
            self._run_local_summary(step)
            return
        launch = self._start_child_run(step)
        if not bool(launch.get("accepted", launch.get("ok", False))):
            failure = str(launch.get("reason") or launch.get("error") or "Child run launch refused")
            required = bool(launch.get("requires_human"))
            self._fail_step(
                step,
                summary=failure,
                error=failure,
                result=launch,
                workflow_status=WorkflowStatus.NEEDS_APPROVAL if required else WorkflowStatus.FAILED,
                recommended_next_action="Approve or adjust the workflow input before retrying."
                if required
                else "Review the failed launch response and adjust the workflow definition.",
            )
            return
        child_run_id = str(launch.get("run_id") or "")
        self.store.update_step(
            self.workflow_id,
            step.id,
            child_run_id=child_run_id,
            result_json=redact_and_truncate(launch),
        )
        self.store.update_workflow(
            self.workflow_id,
            active_child_run_id=child_run_id,
        )
        self._event(
            "info",
            "child_run_started",
            f"Workflow step {step.id} launched child run",
            {"child_run_id": child_run_id},
        )

    def _start_child_run(self, step: WorkflowStepRecord) -> dict[str, Any]:
        workflow = self.store.get_workflow(self.workflow_id)
        if step.type.value == "codex_implement":
            params = CodexImplementParameters.model_validate(step.parameters)
            return self.job_manager.start_implementation(
                workflow.repo_name,
                params.approved_plan,
                params.allowed_files,
                params.tests,
            )
        if step.type.value == "project_command":
            params = ProjectCommandParameters.model_validate(step.parameters)
            return self.job_manager.start_project_command(
                workflow.repo_name, params.command_id
            )
        if step.type.value == "pytest_path":
            params = PytestPathParameters.model_validate(step.parameters)
            return self.job_manager.start_pytest_path(workflow.repo_name, params.path)
        if step.type.value == "git_readonly":
            params = GitReadonlyParameters.model_validate(step.parameters)
            return self.job_manager.start_git_readonly(
                workflow.repo_name, params.operation
            )
        raise ValueError(f"Unsupported workflow step type: {step.type.value}")

    def _run_local_summary(self, step: WorkflowStepRecord) -> None:
        params = LocalSummaryParameters.model_validate(step.parameters)
        workflow = self.store.get_workflow(self.workflow_id)
        prior_steps = [
            item for item in workflow.steps if item.order_index < step.order_index
        ]
        if params.include_step_ids:
            include = set(params.include_step_ids)
            prior_steps = [item for item in prior_steps if item.id in include]
        summary_payload = {
            "workflow_id": workflow.workflow_id,
            "repo_name": workflow.repo_name,
            "objective": workflow.objective,
            "steps": [
                {
                    "step_id": item.id,
                    "type": item.type.value,
                    "status": item.status.value,
                    "child_run_id": item.child_run_id,
                    "summary": item.summary,
                    "error": item.error,
                    "artifact_paths": [str(path) for path in item.artifact_paths],
                }
                for item in prior_steps
            ],
        }
        artifacts_dir = workflow_run_dir(self.config.resolve_runs_dir(), workflow.workflow_id) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        summary_path = artifacts_dir / f"{step.id}_summary.json"
        from codexbridge.return_loop.atomic_writer import atomic_write_json

        atomic_write_json(summary_path, redact_and_truncate(summary_payload))
        self.store.update_step(
            self.workflow_id,
            step.id,
            status=WorkflowStepStatus.PASSED,
            ended_at=utc_now(),
            summary="Structured local summary written",
            artifact_paths_json=[str(summary_path)],
            result_json=summary_payload,
        )
        workflow = self.store.get_workflow(self.workflow_id)
        artifact_paths = [*workflow.artifact_paths, summary_path]
        self.store.update_workflow(
            self.workflow_id,
            artifact_paths_json=[str(path) for path in artifact_paths],
        )
        self._event(
            "info",
            "local_summary",
            f"Workflow step {step.id} wrote local summary",
            {"artifact_path": str(summary_path)},
        )

    def _fail_step(
        self,
        step: WorkflowStepRecord,
        *,
        summary: str,
        error: str,
        result: dict[str, Any],
        workflow_status: WorkflowStatus | None = None,
        recommended_next_action: str = "",
    ) -> None:
        workflow = self.store.get_workflow(self.workflow_id)
        self.store.update_step(
            self.workflow_id,
            step.id,
            status=WorkflowStepStatus.FAILED,
            ended_at=utc_now(),
            summary=summary,
            error=error,
            result_json=redact_and_truncate(result),
        )
        self.store.update_workflow(
            self.workflow_id,
            active_child_run_id=None,
            failure_summary=summary,
        )
        self._event(
            "error",
            "step_failed",
            f"Workflow step {step.id} failed",
            {"error": error, "child_run_id": step.child_run_id},
        )
        target_status = workflow_status
        if target_status is None:
            target_status = (
                WorkflowStatus.FAILED
                if step.on_failure == StepOnFailure.STOP
                else None
            )
        if target_status is not None:
            self._transition_terminal(
                target_status,
                failure_summary=summary,
                recommended_next_action=recommended_next_action
                or "Inspect the failing step and adjust the workflow before retrying.",
            )

    def _complete_workflow(self) -> None:
        workflow = self.store.get_workflow(self.workflow_id)
        failed_steps = [step for step in workflow.steps if step.status == WorkflowStepStatus.FAILED]
        recommended = (
            "Review the failed step outputs captured in the workflow artifacts."
            if failed_steps
            else "No immediate action required."
        )
        self._transition_terminal(
            WorkflowStatus.COMPLETED,
            failure_summary="; ".join(step.summary for step in failed_steps if step.summary),
            recommended_next_action=recommended,
        )

    def _transition_terminal(
        self,
        status: WorkflowStatus,
        *,
        failure_summary: str,
        recommended_next_action: str,
    ) -> None:
        updated = self.store.update_workflow(
            self.workflow_id,
            status=status,
            terminal_status=status,
            ended_at=utc_now(),
            active_child_run_id=None,
            failure_summary=failure_summary,
            recommended_next_action=recommended_next_action,
        )
        self._event(
            "info" if status == WorkflowStatus.COMPLETED else "warning",
            "terminal",
            f"Workflow reached terminal status {status.value}",
            {"recommended_next_action": recommended_next_action},
        )
        self.workflow_manager._finalize_terminal_workflow(updated)

    def _all_steps_terminal(self) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        return all(
            step.status
            in {
                WorkflowStepStatus.PASSED,
                WorkflowStepStatus.FAILED,
                WorkflowStepStatus.SKIPPED,
                WorkflowStepStatus.CANCELLED,
            }
            for step in workflow.steps
        )

    def _event(
        self, level: str, stage: str, message: str, data: dict[str, Any] | None = None
    ) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        if (
            workflow.worker_lease_token != self.lease_token
            or workflow.lease_generation != self.lease_generation
        ):
            return False
        if workflow.status == WorkflowStatus.RUNNING and not self.store.heartbeat_worker(
            self.workflow_id,
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            worker_pid=os_getpid(),
        ):
            return False
        self.store.append_event(
            self.workflow_id,
            level=level,
            stage=stage,
            message=message,
            data=redact_and_truncate(data or {}),
            update_workflow_metadata=False,
        )
        workflow = self.store.get_workflow(self.workflow_id)
        write_workflow_snapshot(
            self.config.resolve_runs_dir(),
            workflow,
            [event.to_dict() for event in self.store.get_events(self.workflow_id, 500)],
        )
        return True


def os_getpid() -> int:
    import os

    return int(os.getpid())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the durable workflow worker.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--lease-token", required=True)
    parser.add_argument("--lease-generation", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    worker = WorkflowWorker(
        Path(args.config),
        args.workflow_id,
        lease_token=args.lease_token,
        lease_generation=args.lease_generation,
    )
    return worker.execute()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
