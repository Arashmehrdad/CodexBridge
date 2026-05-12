from __future__ import annotations

from codexbridge.return_loop.atomic_writer import atomic_write_text
from codexbridge.return_loop.pulse_contract import build_job_report_manifest

from .models import JobReport, JobResult, JobStatus


def generate_job_report(result: JobResult) -> JobReport:
    report_path = result.result_json_path.parent / "job_report.md"
    resume_prompt_path = result.result_json_path.parent / "resume_prompt.txt"
    summary = _summary(result)
    question = _question_for_chatgpt(result)
    report = "\n".join(
        [
            f"# Job Report: {result.job_id}",
            "",
            f"- Status: {result.status.value}",
            f"- Profile: {result.job_profile}",
            f"- Repo: {result.repo_name or result.repo_path or ''}",
            f"- Exit code: {result.exit_code}",
            f"- Duration seconds: {result.duration_seconds}",
            f"- Stdout: {result.stdout_path}",
            f"- Stderr: {result.stderr_path}",
            f"- Artifacts: {', '.join(str(path) for path in result.artifact_paths) or 'None'}",
            f"- Summary: {summary}",
            f"- Failure summary: {result.failure_summary}",
            f"- Recommended next action: {result.next_recommended_action}",
            f"- Question for ChatGPT: {question}",
            "- Codex called: false",
            "- PulseSender sent: false/unknown",
            "",
        ]
    )
    resume = "\n".join(
        [
            "CodexBridge job completed.",
            "",
            f"job_id: {result.job_id}",
            f"repo_name: {result.repo_name or ''}",
            f"repo_path: {result.repo_path or ''}",
            f"job_profile: {result.job_profile}",
            f"status: {result.status.value}",
            f"exit_code: {result.exit_code}",
            f"duration: {result.duration_seconds}",
            f"artifacts: {', '.join(str(path) for path in result.artifact_paths) or 'None'}",
            f"stdout_path: {result.stdout_path}",
            f"stderr_path: {result.stderr_path}",
            f"result_json_path: {result.result_json_path}",
            f"summary: {summary}",
            f"metrics: {result.metrics_summary}",
            f"errors: {result.failure_summary or result.error}",
            f"failure_summary: {result.failure_summary}",
            f"recommended_next_action: {result.next_recommended_action}",
            f"question_for_chatgpt: {question}",
            "codex_called: false",
            "pulsesender_sent: false/unknown",
            "",
        ]
    )
    atomic_write_text(report_path, report)
    atomic_write_text(resume_prompt_path, resume)
    manifest = build_job_report_manifest(
        job_id=result.job_id,
        source_status=result.status.value,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        result_json_path=result.result_json_path,
        stdout_path=result.stdout_path,
        stderr_path=result.stderr_path,
        artifact_paths=result.artifact_paths,
        recommended_next_action=result.next_recommended_action,
        question_for_chatgpt=question,
    )
    return JobReport(
        job_id=result.job_id,
        status=JobStatus.REPORTED if result.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.CANCELLED} else result.status,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
        manifest_path=resume_prompt_path.parent / "pulse_manifest.json" if manifest else None,
        summary=summary,
        question_for_chatgpt=question,
    )


def _summary(result: JobResult) -> str:
    if result.status == JobStatus.COMPLETED:
        return "Job completed successfully."
    if result.status == JobStatus.FAILED:
        return "Job failed. Review stderr and result metadata."
    if result.status == JobStatus.TIMEOUT:
        return "Job timed out. Review partial output and consider a smaller workload or higher approved timeout."
    if result.status == JobStatus.CANCELLED:
        return "Job was cancelled."
    return f"Job is {result.status.value}."


def _question_for_chatgpt(result: JobResult) -> str:
    if result.status in {JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.NEEDS_INPUT}:
        return "What should CodexBridge do next with this job result?"
    return ""
