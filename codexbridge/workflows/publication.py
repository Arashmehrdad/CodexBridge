from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codexbridge.return_loop.report_manifest import file_sha256

from .models import WorkflowRecord, WorkflowStatus
from .reporter import generate_workflow_report, write_workflow_snapshot
from .store import WorkflowStore


def workflow_publication_hash(workflow: WorkflowRecord) -> str:
    """Hash only the durable terminal winner, excluding publication bookkeeping."""
    source_status = workflow.terminal_status or workflow.status
    payload = {
        "workflow_id": workflow.workflow_id,
        "repo_name": workflow.repo_name,
        "objective": workflow.objective,
        "terminal_status": source_status.value,
        "created_at": workflow.created_at,
        "started_at": workflow.started_at,
        "ended_at": workflow.ended_at,
        "active_child_run_id": workflow.active_child_run_id,
        "failure_summary": workflow.failure_summary,
        "recommended_next_action": workflow.recommended_next_action,
        "result": workflow.result,
        "steps": [
            step.model_dump(mode="json", exclude_none=True) for step in workflow.steps
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def publish_workflow(
    store: WorkflowStore,
    runs_dir: Path,
    workflow_id: str,
) -> WorkflowRecord:
    """Publish the terminal state selected by SQLite, using an idempotent CAS."""
    winner = store.get_workflow(workflow_id)
    source_status = winner.terminal_status or winner.status
    if (
        winner.publication_status == "published"
        and winner.status == WorkflowStatus.REPORTED
        and _publication_artifacts_match(runs_dir, winner)
    ):
        return winner
    if source_status in {
        WorkflowStatus.CANCELLATION_PENDING,
        WorkflowStatus.RECOVERY_PENDING,
        WorkflowStatus.QUEUED,
        WorkflowStatus.RUNNING,
        WorkflowStatus.CREATED,
    }:
        return winner
    if winner.status == WorkflowStatus.REPORTED:
        expected_status = WorkflowStatus.REPORTED
    else:
        expected_status = winner.status
    publication_hash = workflow_publication_hash(winner)
    claimed = store.begin_publication(
        workflow_id,
        expected_status=expected_status,
        expected_state_version=winner.state_version,
        publication_hash=publication_hash,
    )
    if claimed is None:
        return store.get_workflow(workflow_id)
    try:
        store.append_event(
            workflow_id,
            level="info",
            stage="reported",
            message="Workflow report artifacts written",
            data={"publication_hash": publication_hash},
            update_workflow_metadata=False,
        )
        write_workflow_snapshot(
            runs_dir,
            claimed,
            [event.to_dict() for event in store.get_events(workflow_id, 500)],
        )
        report = generate_workflow_report(runs_dir, claimed)
        artifact_paths = list(
            dict.fromkeys(
                [
                    *[str(path) for path in claimed.artifact_paths],
                    str(report.report_path),
                    str(report.resume_prompt_path),
                    str(report.manifest_path),
                ]
            )
        )
        published = store.mark_publication_complete(
            workflow_id,
            expected_status=expected_status,
            expected_state_version=claimed.state_version,
            publication_hash=publication_hash,
            terminal_status=claimed.terminal_status or source_status,
            artifact_paths=artifact_paths,
        )
        return published or store.get_workflow(workflow_id)
    except Exception as exc:
        store.mark_publication_failed(
            workflow_id,
            expected_status=expected_status,
            expected_state_version=claimed.state_version,
            publication_hash=publication_hash,
            error=str(exc),
        )
        return store.get_workflow(workflow_id)


def _publication_artifacts_match(runs_dir: Path, workflow: WorkflowRecord) -> bool:
    run_dir = Path(runs_dir) / "workflows" / workflow.workflow_id
    result_path = run_dir / "result.json"
    report_path = run_dir / "workflow_report.md"
    resume_path = run_dir / "resume_prompt.txt"
    manifest_path = run_dir / "pulse_manifest.json"
    required = (result_path, report_path, resume_path, manifest_path)
    if not all(path.is_file() for path in required):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        actual_hashes = {
            "content_sha256": file_sha256(resume_path),
            "report_sha256": file_sha256(report_path),
            "result_sha256": file_sha256(result_path),
        }
    except (OSError, ValueError, TypeError):
        return False
    source_status = (workflow.terminal_status or workflow.status).value
    if any(str(manifest.get(key) or "") != value for key, value in actual_hashes.items()):
        return False
    return (
        str(manifest.get("artifact_id") or "") == workflow.workflow_id
        and str(manifest.get("source_kind") or "") == "workflow"
        and str(manifest.get("source_status") or "") == source_status
        and Path(str(manifest.get("result_json_path") or "")) == result_path
        and Path(str(manifest.get("report_path") or "")) == report_path
        and Path(str(manifest.get("resume_prompt_path") or "")) == resume_path
        and str(result.get("workflow_id") or "") == workflow.workflow_id
        and str(result.get("terminal_status") or result.get("status") or "")
        == source_status
        and str(result.get("publication_hash") or "") == workflow.publication_hash
    )
