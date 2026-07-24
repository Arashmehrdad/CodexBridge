from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from soma.config import AppConfig, load_config
from soma.events import redact_and_truncate
from soma.job_manager import JobManager, make_run_id
from soma.process_control import process_identity
from soma.run_store import TERMINAL_STATUSES, utc_now

from .models import (
    GitReadonlyParameters,
    LocalSummaryParameters,
    ProjectCommandParameters,
    PytestPathParameters,
    StepOnFailure,
    WorkflowStatus,
    WorkflowStepRecord,
    WorkflowStepStatus,
)
from .publication import publish_workflow
from .reporter import workflow_run_dir, write_workflow_snapshot
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
        self.lease_token = lease_token if lease_token is not None else initial.worker_lease_token
        self.lease_generation = int(
            lease_generation if lease_generation is not None else initial.lease_generation
        )
        self.job_manager = JobManager(self.config, config_path)
        self.poll_interval_seconds = poll_interval_seconds
        self.sleep_fn = sleep_fn

    def execute(self) -> int:
        workflow = self.store.get_workflow(self.workflow_id)
        if workflow.status in {
            WorkflowStatus.CANCELLATION_PENDING,
            WorkflowStatus.RECOVERY_PENDING,
        }:
            return 1
        if workflow.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.NEEDS_APPROVAL,
            WorkflowStatus.NEEDS_INPUT,
            WorkflowStatus.REPORTED,
        }:
            publish_workflow(self.store, self.config.resolve_runs_dir(), self.workflow_id)
            return 0
        if workflow.status == WorkflowStatus.QUEUED:
            worker_pid = os_getpid()
            if not self.store.claim_worker(
                self.workflow_id,
                lease_token=self.lease_token,
                lease_generation=self.lease_generation,
                expected_state_version=workflow.state_version,
                worker_pid=worker_pid,
                worker_identity=process_identity(worker_pid),
            ):
                return 1
        elif workflow.status != WorkflowStatus.RUNNING:
            return 1

        while True:
            workflow = self.store.get_workflow(self.workflow_id)
            if workflow.status in {
                WorkflowStatus.CANCELLATION_PENDING,
                WorkflowStatus.RECOVERY_PENDING,
            }:
                return 1
            if workflow.status in {
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED,
                WorkflowStatus.NEEDS_APPROVAL,
                WorkflowStatus.NEEDS_INPUT,
                WorkflowStatus.REPORTED,
            }:
                publish_workflow(self.store, self.config.resolve_runs_dir(), self.workflow_id)
                return 0
            if not self.store.heartbeat_worker(
                self.workflow_id,
                lease_token=self.lease_token,
                lease_generation=self.lease_generation,
                worker_pid=os_getpid(),
            ):
                return 1
            if self._replay_local_summaries(workflow):
                continue
            if workflow.active_child_run_id and self._reconcile_active_child(workflow):
                continue
            if workflow.active_child_run_id:
                return 1
            if self._skip_blocked_steps():
                continue
            next_step = self._next_pending_step()
            if next_step is None:
                if self._all_steps_terminal():
                    self._complete_workflow()
                    continue
                self.sleep_fn(self.poll_interval_seconds)
                continue
            if not self._start_step(next_step):
                return 1

    def _reconcile_active_child(self, workflow: Any) -> bool:
        child_id = workflow.active_child_run_id
        active_step = next((step for step in workflow.steps if step.child_run_id == child_id), None)
        if active_step is None or active_step.status != WorkflowStepStatus.RUNNING:
            self._mark_recovery("Active child ownership does not match a running workflow step.")
            return False
        try:
            status = self.job_manager.get_status(child_id)
            state = str(status.get("status") or "")
            if state not in TERMINAL_STATUSES:
                self.sleep_fn(self.poll_interval_seconds)
                return True
            result = self.job_manager.get_result(child_id)
        except Exception as exc:
            self._mark_recovery(f"Unable to reconcile durable child {child_id}: {exc}")
            return False
        terminal_now = utc_now()
        if state == "completed":
            return self._finish_step(
                active_step,
                status=WorkflowStepStatus.PASSED,
                ended_at=terminal_now,
                summary=str(result.get("summary") or "Step completed"),
                error="",
                result=result,
                clear_child=True,
            )
        if state == "needs_input":
            return self._fail_step(
                active_step,
                summary=str(result.get("summary") or "Child run needs input"),
                error=str(result.get("error") or "Child run needs input"),
                result=result,
                workflow_status=WorkflowStatus.NEEDS_INPUT,
                recommended_next_action="Review the child run result and provide the requested input before resuming.",
            )
        if state == "cancelled" and workflow.status == WorkflowStatus.CANCELLATION_PENDING:
            return False
        return self._fail_step(
            active_step,
            summary=str(result.get("summary") or f"Child run ended with status {state}"),
            error=str(result.get("error") or f"Child run status {state}"),
            result=result,
        )

    def _replay_local_summaries(self, workflow: Any) -> bool:
        for step in workflow.steps:
            if step.type.value == "local_summary" and step.status == WorkflowStepStatus.RUNNING:
                reset = self.store.reset_local_summary(
                    self.workflow_id,
                    step.id,
                    expected_workflow_state_version=workflow.state_version,
                    expected_step_state_version=step.state_version,
                    lease_token=self.lease_token,
                    lease_generation=self.lease_generation,
                )
                if reset is None:
                    return True
                return True
        return False

    def _next_pending_step(self) -> WorkflowStepRecord | None:
        workflow = self.store.get_workflow(self.workflow_id)
        status_by_id = {step.id: step.status for step in workflow.steps}
        for step in workflow.steps:
            if step.status == WorkflowStepStatus.PENDING and all(
                status_by_id.get(dep) == WorkflowStepStatus.PASSED for dep in step.depends_on
            ):
                return step
        return None

    def _skip_blocked_steps(self) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        status_by_id = {step.id: step.status for step in workflow.steps}
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
                updated = self.store.conditional_update_step(
                    self.workflow_id,
                    step.id,
                    fields={
                        "status": WorkflowStepStatus.SKIPPED,
                        "ended_at": utc_now(),
                        "summary": "Skipped because a dependency did not pass",
                        "error": "Blocked by failed dependency",
                    },
                    expected_statuses=(WorkflowStepStatus.PENDING,),
                    lease_token=self.lease_token,
                    lease_generation=self.lease_generation,
                    expected_state_version=step.state_version,
                    expected_child_run_id=None,
                    expected_workflow_state_version=workflow.state_version,
                )
                if updated is None:
                    return True
                self._event("warning", "step_skipped", f"Workflow step {step.id} skipped due to dependency state", {"depends_on": step.depends_on})
                return True
        return False

    def _start_step(self, step: WorkflowStepRecord) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        child_run_id = None if step.type.value == "local_summary" else make_run_id(
            "codex_implement_task" if step.type.value == "codex_implement" else "project_command"
        )
        claimed = self.store.claim_step(
            self.workflow_id,
            step.id,
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            child_run_id=child_run_id,
            expected_workflow_state_version=workflow.state_version,
            expected_step_state_version=step.state_version,
        )
        if claimed is None:
            return False
        claimed_step = next(item for item in claimed.steps if item.id == step.id)
        if not self._event("info", "step_running", f"Workflow step {step.id} claimed", {"child_run_id": child_run_id}):
            return False
        if child_run_id is None:
            return self._run_local_summary(claimed_step)
        try:
            launch = self._start_child_run(claimed_step, child_run_id)
        except Exception as exc:
            return self._fail_step(claimed_step, summary="Child run launch failed", error=str(exc), result={"error": str(exc)})
        if not bool(launch.get("accepted", launch.get("ok", False))):
            failure = str(launch.get("reason") or launch.get("error") or "Child run launch refused")
            return self._fail_step(
                claimed_step,
                summary=failure,
                error=failure,
                result=launch,
                workflow_status=WorkflowStatus.NEEDS_APPROVAL if launch.get("requires_human") else WorkflowStatus.FAILED,
                recommended_next_action="Approve or adjust the workflow input before retrying." if launch.get("requires_human") else "Review the failed launch response and adjust the workflow definition.",
            )
        launched_run_id = str(launch.get("run_id") or "")
        if launched_run_id != child_run_id:
            return self._fail_step(
                claimed_step,
                summary="Child launch returned an unexpected run ID",
                error=f"Expected {child_run_id}, received {launched_run_id or '<empty>'}",
                result=launch,
            )
        current = self.store.get_workflow(self.workflow_id)
        active_step = next(item for item in current.steps if item.id == step.id)
        recorded = self.store.conditional_update_step(
            self.workflow_id,
            step.id,
            fields={"result_json": redact_and_truncate(launch)},
            expected_statuses=(WorkflowStepStatus.RUNNING,),
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            expected_state_version=active_step.state_version,
            expected_child_run_id=child_run_id,
            expected_workflow_state_version=current.state_version,
        )
        if recorded is None:
            return False
        self._event("info", "child_run_started", f"Workflow step {step.id} launched child run", {"child_run_id": child_run_id})
        return True

    def _start_child_run(self, step: WorkflowStepRecord, reserved_run_id: str) -> dict[str, Any]:
        workflow = self.store.get_workflow(self.workflow_id)
        if step.type.value == "codex_implement":
            raise ValueError(
                "codex_implement workflow steps are removed compatibility "
                "values and have no worker or launch implementation."
            )
        if step.type.value == "project_command":
            params = ProjectCommandParameters.model_validate(step.parameters)
            return self.job_manager.start_project_command(workflow.repo_name, params.command_id, reserved_run_id=reserved_run_id)
        if step.type.value == "pytest_path":
            params = PytestPathParameters.model_validate(step.parameters)
            return self.job_manager.start_pytest_path(workflow.repo_name, params.path, reserved_run_id=reserved_run_id)
        if step.type.value == "git_readonly":
            params = GitReadonlyParameters.model_validate(step.parameters)
            return self.job_manager.start_git_readonly(workflow.repo_name, params.operation, reserved_run_id=reserved_run_id)
        raise ValueError(f"Unsupported workflow step type: {step.type.value}")

    def _run_local_summary(self, step: WorkflowStepRecord) -> bool:
        params = LocalSummaryParameters.model_validate(step.parameters)
        workflow = self.store.get_workflow(self.workflow_id)
        prior_steps = [item for item in workflow.steps if item.order_index < step.order_index]
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
        from soma.return_loop.atomic_writer import atomic_write_json

        atomic_write_json(summary_path, redact_and_truncate(summary_payload))
        current = self.store.get_workflow(self.workflow_id)
        current_step = next(item for item in current.steps if item.id == step.id)
        artifact_paths = list(dict.fromkeys([str(path) for path in current.artifact_paths] + [str(summary_path)]))
        updated = self.store.conditional_update_step(
            self.workflow_id,
            step.id,
            fields={
                "status": WorkflowStepStatus.PASSED,
                "ended_at": utc_now(),
                "summary": "Structured local summary written",
                "artifact_paths_json": [str(summary_path)],
                "result_json": summary_payload,
            },
            expected_statuses=(WorkflowStepStatus.RUNNING,),
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            expected_state_version=current_step.state_version,
            expected_child_run_id=None,
            expected_workflow_state_version=current.state_version,
            workflow_fields={"artifact_paths_json": artifact_paths},
        )
        if updated is None:
            return False
        self._event("info", "local_summary", f"Workflow step {step.id} wrote local summary", {"artifact_path": str(summary_path)})
        return True

    def _finish_step(self, step: WorkflowStepRecord, *, status: WorkflowStepStatus, ended_at: str, summary: str, error: str, result: dict[str, Any], clear_child: bool) -> bool:
        current = self.store.get_workflow(self.workflow_id)
        current_step = next((item for item in current.steps if item.id == step.id), None)
        if current_step is None:
            return False
        return self.store.conditional_update_step(
            self.workflow_id,
            step.id,
            fields={"status": status, "ended_at": ended_at, "summary": summary, "error": error, "result_json": redact_and_truncate(result)},
            expected_statuses=(WorkflowStepStatus.RUNNING,),
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            expected_state_version=current_step.state_version,
            expected_child_run_id=step.child_run_id,
            expected_workflow_state_version=current.state_version,
            clear_active_child=clear_child,
        ) is not None

    def _fail_step(self, step: WorkflowStepRecord, *, summary: str, error: str, result: dict[str, Any], workflow_status: WorkflowStatus | None = None, recommended_next_action: str = "") -> bool:
        current = self.store.get_workflow(self.workflow_id)
        current_step = next((item for item in current.steps if item.id == step.id), None)
        if current_step is None or current_step.status != WorkflowStepStatus.RUNNING:
            return False
        updated = self.store.conditional_update_step(
            self.workflow_id,
            step.id,
            fields={"status": WorkflowStepStatus.FAILED, "ended_at": utc_now(), "summary": summary, "error": error, "result_json": redact_and_truncate(result)},
            expected_statuses=(WorkflowStepStatus.RUNNING,),
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            expected_state_version=current_step.state_version,
            expected_child_run_id=current_step.child_run_id,
            expected_workflow_state_version=current.state_version,
            clear_active_child=bool(current_step.child_run_id),
            workflow_fields={"failure_summary": summary},
        )
        if updated is None:
            return False
        self._event("error", "step_failed", f"Workflow step {step.id} failed", {"error": error, "child_run_id": step.child_run_id})
        target_status = workflow_status or (WorkflowStatus.FAILED if step.on_failure == StepOnFailure.STOP else None)
        if target_status is not None:
            self._transition_terminal(target_status, failure_summary=summary, recommended_next_action=recommended_next_action or "Inspect the failing step and adjust the workflow before retrying.")
        return True

    def _complete_workflow(self) -> None:
        workflow = self.store.get_workflow(self.workflow_id)
        failed_steps = [step for step in workflow.steps if step.status == WorkflowStepStatus.FAILED]
        self._transition_terminal(
            WorkflowStatus.COMPLETED,
            failure_summary="; ".join(step.summary for step in failed_steps if step.summary),
            recommended_next_action="Review the failed step outputs captured in the workflow artifacts." if failed_steps else "No immediate action required.",
        )

    def _transition_terminal(self, status: WorkflowStatus, *, failure_summary: str, recommended_next_action: str) -> None:
        current = self.store.get_workflow(self.workflow_id)
        updated = self.store.transition_terminal(
            self.workflow_id,
            status=status,
            expected_state_version=current.state_version,
            lease_token=self.lease_token,
            lease_generation=self.lease_generation,
            failure_summary=failure_summary,
            recommended_next_action=recommended_next_action,
        )
        if updated is None:
            return
        self._event("info" if status == WorkflowStatus.COMPLETED else "warning", "terminal", f"Workflow reached terminal status {status.value}", {"recommended_next_action": recommended_next_action})
        publish_workflow(self.store, self.config.resolve_runs_dir(), self.workflow_id)

    def _all_steps_terminal(self) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        return all(step.status in {WorkflowStepStatus.PASSED, WorkflowStepStatus.FAILED, WorkflowStepStatus.SKIPPED, WorkflowStepStatus.CANCELLED} for step in workflow.steps)

    def _mark_recovery(self, reason: str) -> None:
        current = self.store.get_workflow(self.workflow_id)
        changed = self.store.mark_recovery_pending(
            self.workflow_id,
            expected_statuses=(WorkflowStatus.RUNNING,),
            expected_state_version=current.state_version,
            expected_lease_token=self.lease_token,
            expected_lease_generation=self.lease_generation,
            reason=reason,
        )
        if changed is not None:
            self._event("error", "recovery_pending", reason)

    def _event(self, level: str, stage: str, message: str, data: dict[str, Any] | None = None) -> bool:
        workflow = self.store.get_workflow(self.workflow_id)
        if workflow.worker_lease_token != self.lease_token or workflow.lease_generation != self.lease_generation:
            return False
        event = self.store.append_event(
            self.workflow_id,
            level=level,
            stage=stage,
            message=message,
            data=redact_and_truncate(data or {}),
            update_workflow_metadata=False,
            expected_lease_token=self.lease_token,
            expected_lease_generation=self.lease_generation,
            expected_statuses=(workflow.status,),
            expected_state_version=workflow.state_version,
        )
        if event is None:
            return False
        current = self.store.get_workflow(self.workflow_id)
        write_workflow_snapshot(self.config.resolve_runs_dir(), current, [item.to_dict() for item in self.store.get_events(self.workflow_id, 500)])
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
    worker = WorkflowWorker(Path(args.config), args.workflow_id, lease_token=args.lease_token, lease_generation=args.lease_generation)
    return worker.execute()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
