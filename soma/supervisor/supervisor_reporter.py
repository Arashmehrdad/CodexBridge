from __future__ import annotations

from soma.config import ReturnLoopConfig
from soma.return_loop.atomic_writer import atomic_write_text
from soma.return_loop.pulse_contract import build_report_manifest

from .models import SupervisorReport, SupervisorRun


def generate_supervisor_report(run: SupervisorRun) -> SupervisorReport:
    run_dir = run.artifact_paths[0].parent if run.artifact_paths else None
    if run_dir is None:
        raise ValueError("Supervisor run is missing artifact directory")
    report_path = run_dir / "supervisor_report.md"
    resume_path = run_dir / "resume_prompt.txt"
    report = "\n".join(
        [
            f"# Supervisor Report: {run.supervisor_id}",
            "",
            f"- Status: {run.status.value}",
            f"- Objective: {run.objective}",
            f"- Repo: {run.repo_name or run.repo_path or ''}",
            f"- Codex needed: {bool(run.codex_escalation_id)}",
            f"- Codex invoked: {run.codex_invoked}",
            f"- Validation summary: {run.validation_results}",
            f"- Post-validation summary: {run.post_validation_results}",
            f"- Summary: {run.local_plan_summary or run.local_inspection_summary}",
            f"- Errors: {run.failure_summary}",
            f"- Recommended next action: {run.next_recommended_action}",
            f"- Question for ChatGPT: {run.question_for_chatgpt}",
            "",
        ]
    )
    resume = "\n".join(
        [
            "Soma supervisor completed.",
            "",
            f"supervisor_id: {run.supervisor_id}",
            f"repo_name: {run.repo_name or ''}",
            f"repo_path: {run.repo_path or ''}",
            f"objective: {run.objective}",
            f"status: {run.status.value}",
            f"codex_needed: {bool(run.codex_escalation_id)}",
            f"codex_invoked: {run.codex_invoked}",
            f"codex_invocation_disabled: {not run.codex_invoked}",
            f"codex_escalation_id: {run.codex_escalation_id or ''}",
            f"codex_packet_path: {run.codex_packet_path or ''}",
            f"validation_summary: {run.validation_results}",
            f"post_validation_summary: {run.post_validation_results}",
            f"artifacts: {', '.join(str(path) for path in run.artifact_paths)}",
            f"summary: {run.local_plan_summary or run.local_inspection_summary}",
            f"errors: {run.failure_summary}",
            f"recommended_next_action: {run.next_recommended_action}",
            f"question_for_chatgpt: {run.question_for_chatgpt}",
            "",
        ]
    )
    atomic_write_text(report_path, report)
    atomic_write_text(resume_path, resume)
    manifest = build_report_manifest(
        artifact_type="supervisor_report",
        artifact_id=run.supervisor_id,
        source_kind="supervisor",
        source_status=run.status.value,
        report_path=report_path,
        resume_prompt_path=resume_path,
        result_json_path=run_dir / "result.json",
        artifact_paths=run.artifact_paths,
        recommended_next_action=run.next_recommended_action,
        question_for_chatgpt=run.question_for_chatgpt,
        config=ReturnLoopConfig(max_resume_prompt_bytes=20000, max_report_bytes=100000),
    )
    return SupervisorReport(
        supervisor_id=run.supervisor_id,
        report_path=report_path,
        resume_prompt_path=resume_path,
        pulse_manifest_path=resume_path.parent / "pulse_manifest.json"
        if manifest
        else None,
    )
