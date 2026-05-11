from __future__ import annotations

from pathlib import Path

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
            "",
        ]
    )
    resume = "\n".join(
        [
            "Resume CodexBridge job follow-up.",
            f"job_id: {result.job_id}",
            f"status: {result.status.value}",
            f"profile: {result.job_profile}",
            f"stdout_path: {result.stdout_path}",
            f"stderr_path: {result.stderr_path}",
            f"result_json_path: {result.result_json_path}",
            f"summary: {summary}",
            f"failure_summary: {result.failure_summary}",
            f"recommended_next_action: {result.next_recommended_action}",
            f"question_for_chatgpt: {question}",
            "",
        ]
    )
    _atomic_write(report_path, report)
    _atomic_write(resume_prompt_path, resume)
    return JobReport(
        job_id=result.job_id,
        status=JobStatus.REPORTED if result.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.CANCELLED} else result.status,
        report_path=report_path,
        resume_prompt_path=resume_prompt_path,
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


def _atomic_write(path: Path, text: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)
