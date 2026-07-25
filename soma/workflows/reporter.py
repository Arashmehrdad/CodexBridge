from __future__ import annotations

import json
from pathlib import Path

from soma.events import redact_and_truncate
from soma.return_loop.atomic_writer import atomic_write_json, atomic_write_text
from soma.return_loop.pulse_contract import build_report_manifest

from .models import WorkflowRecord, WorkflowReport, WorkflowStatus


TERMINAL_REPORTABLE_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.NEEDS_INPUT,
    WorkflowStatus.NEEDS_APPROVAL,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.REPORTED,
}


def workflow_run_dir(runs_dir: Path, workflow_id: str) -> Path:
    return Path(runs_dir) / "workflows" / workflow_id


def write_workflow_snapshot(
    runs_dir: Path,
    workflow: WorkflowRecord,
    events: list[dict],
) -> dict:
    run_dir = workflow_run_dir(runs_dir, workflow.workflow_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = redact_and_truncate(workflow.to_dict())
    events_text = "\n".join(
        json.dumps(redact_and_truncate(event), sort_keys=True) for event in events
    )
    if events_text:
        events_text += "\n"
    atomic_write_json(run_dir / "result.json", snapshot)
    atomic_write_text(run_dir / "events.jsonl", events_text)
    return snapshot


def generate_workflow_report(runs_dir: Path, workflow: WorkflowRecord) -> WorkflowReport:
    source_status = workflow.terminal_status or workflow.status
    if source_status not in TERMINAL_REPORTABLE_STATUSES:
        raise ValueError(f"Workflow is not reportable: {workflow.workflow_id}")
    run_dir = workflow_run_dir(runs_dir, workflow.workflow_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "workflow_report.md"
    resume_prompt_path = run_dir / "resume_prompt.txt"
    snapshot_path = run_dir / "result.json"
    generated_paths = {
        str(report_path),
        str(resume_prompt_path),
        str(snapshot_path),
        str(run_dir / "pulse_manifest.json"),
        str(run_dir / "events.jsonl"),
    }
    artifacts = _artifact_list(workflow, excluded_paths=generated_paths)
    ordered_outcomes = [
        f"- {step.order_index + 1}. {step.id} [{step.status.value}]"
        f" child_run_id={step.child_run_id or 'none'}"
        f" summary={step.summary or 'n/a'}"
        f" error={_display_error(step.error)}"
        for step in workflow.steps
    ]
    report = "\n".join(
        [
            f"# Workflow Report: {workflow.workflow_id}",
            "",
            f"- Repo: {workflow.repo_name}",
            f"- Objective: {workflow.objective}",
            f"- Status: {source_status.value}",
            f"- Terminal status: {source_status.value}",
            f"- Active child run: {workflow.active_child_run_id or 'none'}",
            f"- Failure summary: {workflow.failure_summary or 'none'}",
            f"- Recommended next action: {workflow.recommended_next_action or 'none'}",
            f"- Artifacts: {', '.join(artifacts) or 'None'}",
            "",
            "## Ordered step outcomes",
            *ordered_outcomes,
            "",
        ]
    )
    resume = "\n".join(
        [
            "Soma durable workflow update.",
            "",
            f"workflow_id: {workflow.workflow_id}",
            f"repo_name: {workflow.repo_name}",
            f"objective: {workflow.objective}",
            f"status: {source_status.value}",
            f"terminal_status: {source_status.value}",
            f"active_child_run_id: {workflow.active_child_run_id or ''}",
            "step_outcomes:",
            *[
                f"- step_id={step.id}; type={step.type.value}; status={step.status.value}; "
                f"child_run_id={step.child_run_id or ''}; error={_display_error(step.error)}; "
                f"artifacts={', '.join(str(path) for path in step.artifact_paths) or 'None'}"
                for step in workflow.steps
            ],
            f"errors: {workflow.failure_summary or ''}",
            f"artifacts: {', '.join(artifacts) or 'None'}",
            f"recommended_next_action: {workflow.recommended_next_action or ''}",
            f"result_json_path: {snapshot_path}",
            "",
        ]
    )
    atomic_write_text(report_path, redact_and_truncate(report))
    atomic_write_text(resume_prompt_path, redact_and_truncate(resume))
    build_report_manifest(
        artifact_type="combined",
        artifact_id=workflow.workflow_id,
        source_kind="workflow",
        source_status=source_status.value,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        result_json_path=snapshot_path,
        artifact_paths=[Path(path) for path in artifacts],
        recommended_next_action=workflow.recommended_next_action,
        question_for_chatgpt="",
    )
    return WorkflowReport(
        workflow_id=workflow.workflow_id,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        manifest_path=resume_prompt_path.parent / "pulse_manifest.json",
        source_status=source_status,
    )


def _artifact_list(
    workflow: WorkflowRecord, *, excluded_paths: set[str] | None = None
) -> list[str]:
    excluded = excluded_paths or set()
    seen: set[str] = set()
    ordered: list[str] = []
    for path in workflow.artifact_paths:
        text = str(path)
        if text not in excluded and text not in seen:
            seen.add(text)
            ordered.append(text)
    for step in workflow.steps:
        for path in step.artifact_paths:
            text = str(path)
            if text not in seen:
                seen.add(text)
                ordered.append(text)
    return ordered


def _display_error(value: str) -> str:
    if not value:
        return ""
    sanitized = str(redact_and_truncate(value))
    if sanitized != value:
        return sanitized
    return "[REDACTED]"
