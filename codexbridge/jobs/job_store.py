from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from codexbridge.events import append_jsonl, read_jsonl
from codexbridge.run_store import utc_now

from .models import JobEvent, JobResult, JobStatus


class JobStore:
    def __init__(self, runs_dir: Path):
        self.jobs_dir = runs_dir.resolve() / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def create_job(self, result: JobResult) -> JobResult:
        self.job_dir(result.job_id).mkdir(parents=True, exist_ok=True)
        result.stdout_path.touch(exist_ok=True)
        result.stderr_path.touch(exist_ok=True)
        self.write_result(result)
        self.append_event(result.job_id, stage="created", message="Job created", data={"status": result.status.value})
        return result

    def write_result(self, result: JobResult) -> JobResult:
        result.result_json_path.parent.mkdir(parents=True, exist_ok=True)
        result.result_json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    def get_job(self, job_id: str) -> JobResult:
        path = self.job_dir(job_id) / "result.json"
        if not path.exists():
            raise KeyError(f"Job not found: {job_id}")
        return JobResult.model_validate_json(path.read_text(encoding="utf-8"))

    def list_jobs(self, limit: int = 20) -> list[JobResult]:
        jobs: list[JobResult] = []
        for result_path in self.jobs_dir.glob("*/result.json"):
            try:
                jobs.append(JobResult.model_validate_json(result_path.read_text(encoding="utf-8")))
            except Exception:
                continue
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return jobs[: max(1, min(limit, 100))]

    def append_event(self, job_id: str, *, stage: str, message: str, level: str = "info", data: dict | None = None) -> JobEvent:
        event = JobEvent(
            event_id=f"job_event_{uuid4().hex}",
            job_id=job_id,
            timestamp=utc_now(),
            level=level,
            stage=stage,
            message=message,
            data=data or {},
        )
        append_jsonl(self.job_dir(job_id) / "events.jsonl", event.model_dump(mode="json"))
        return event

    def get_events(self, job_id: str, limit: int = 50) -> list[JobEvent]:
        return [JobEvent.model_validate(event) for event in read_jsonl(self.job_dir(job_id) / "events.jsonl", limit)]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        ended_at: str | None = None,
        duration_seconds: float | None = None,
        exit_code: int | None = None,
        error: str = "",
        failure_summary: str = "",
        artifact_paths: list[Path] | None = None,
        next_recommended_action: str = "",
    ) -> JobResult:
        result = self.get_job(job_id)
        result.status = status
        if ended_at is not None:
            result.ended_at = ended_at
        if duration_seconds is not None:
            result.duration_seconds = duration_seconds
        if exit_code is not None:
            result.exit_code = exit_code
        if error:
            result.error = error
        if failure_summary:
            result.failure_summary = failure_summary
        if artifact_paths is not None:
            result.artifact_paths = artifact_paths
        if next_recommended_action:
            result.next_recommended_action = next_recommended_action
        self.write_result(result)
        self.append_event(job_id, stage=status.value, message=f"Job status updated: {status.value}", data={"status": status.value})
        return result
