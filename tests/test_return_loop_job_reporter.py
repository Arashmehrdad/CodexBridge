from __future__ import annotations

import json
from pathlib import Path

from soma.jobs.job_reporter import generate_job_report
from soma.jobs.models import JobResult, JobStatus
from soma.local_agent.models import PermissionTier
from soma.run_store import utc_now


def make_job(tmp_path: Path, status: JobStatus) -> JobResult:
    job_dir = tmp_path / "runs" / "jobs" / f"job_{status.value}"
    job_dir.mkdir(parents=True)
    result = JobResult(
        job_id=f"job_{status.value}",
        repo_name="sample",
        repo_path=tmp_path,
        job_profile="dummy_success",
        argv=["python", "-c", "print('ok')"],
        permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
        status=status,
        created_at=utc_now(),
        started_at=utc_now(),
        ended_at=utc_now(),
        duration_seconds=1.2,
        timeout_seconds=30,
        exit_code=0 if status == JobStatus.COMPLETED else 2,
        stdout_path=job_dir / "stdout.txt",
        stderr_path=job_dir / "stderr.txt",
        events_path=job_dir / "events.jsonl",
        result_json_path=job_dir / "result.json",
        artifact_paths=[job_dir / "artifact.txt"],
        failure_summary="failed" if status == JobStatus.FAILED else "",
        next_recommended_action="review",
        audit_event_id="audit",
    )
    result.stdout_path.write_text("stdout", encoding="utf-8")
    result.stderr_path.write_text("stderr", encoding="utf-8")
    result.result_json_path.write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    return result


def test_job_reporter_writes_pulse_manifest_for_completed_job(tmp_path: Path) -> None:
    report = generate_job_report(make_job(tmp_path, JobStatus.COMPLETED))

    assert report.manifest_path is not None
    payload = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["ready"] is True
    resume = report.resume_prompt_path.read_text(encoding="utf-8")
    for field in (
        "job_id:",
        "repo_name:",
        "repo_path:",
        "job_profile:",
        "status:",
        "exit_code:",
        "duration:",
        "artifacts:",
        "recommended_next_action:",
        "question_for_chatgpt:",
    ):
        assert field in resume
    assert "external_coder_called: false" in resume
    assert "pulsesender_sent: false/unknown" in resume


def test_job_reporter_writes_pulse_manifest_for_failed_job(tmp_path: Path) -> None:
    report = generate_job_report(make_job(tmp_path, JobStatus.FAILED))
    payload = json.loads(report.manifest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "ready"
    assert payload["source_status"] == "failed"
    assert payload["question_for_chatgpt"]


def test_job_reporter_writes_pulse_manifest_for_timeout_job(tmp_path: Path) -> None:
    report = generate_job_report(make_job(tmp_path, JobStatus.TIMEOUT))
    payload = json.loads(report.manifest_path.read_text(encoding="utf-8"))

    assert payload["status"] == "ready"
    assert payload["source_status"] == "timeout"


def test_return_loop_modules_do_not_import_pulsesender_codex_browser_or_shell_execution() -> (
    None
):
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("soma/return_loop").glob("*.py")
    )

    assert "import PulseSender" not in source
    assert "from PulseSender" not in source
    assert "CodexRunner" not in source
    assert "playwright" not in source.lower()
    assert "selenium" not in source.lower()
    assert "subprocess" not in source
