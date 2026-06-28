from __future__ import annotations

import time

from codexbridge.run_store import utc_now

from .job_profiles import get_job_profile
from .job_reporter import generate_job_report
from .job_store import JobStore
from .models import JobResult, JobStatus


TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.TIMEOUT,
    JobStatus.CANCELLED,
    JobStatus.REPORTED,
    JobStatus.BLOCKED,
    JobStatus.PROFILE_MISSING,
    JobStatus.PERMISSION_DENIED,
    JobStatus.REPO_MISSING,
}


class JobMonitor:
    def __init__(self, store: JobStore, processes: dict[str, object]):
        self.store = store
        self.processes = processes

    def refresh_status(self, job_id: str) -> JobResult:
        result = self.store.get_job(job_id)
        if result.status in TERMINAL_JOB_STATUSES:
            return result

        process = self.processes.get(job_id)
        if process is None:
            self.store.append_event(
                job_id,
                stage="status_refreshed",
                message="No live process handle for job",
                data={"status": result.status.value},
            )
            return result

        now = time.monotonic()
        started_monotonic = getattr(process, "_codexbridge_started_monotonic", now)
        if now - started_monotonic > result.timeout_seconds:
            _terminate(process)
            return self._finish(
                result, JobStatus.TIMEOUT, exit_code=None, error="Job timed out"
            )

        return_code = process.poll()
        if return_code is None:
            self.store.append_event(
                job_id,
                stage="status_refreshed",
                message="Job is still running",
                data={"status": JobStatus.RUNNING.value},
            )
            return result

        status = JobStatus.COMPLETED if return_code == 0 else JobStatus.FAILED
        return self._finish(
            result,
            status,
            exit_code=int(return_code),
            error="" if return_code == 0 else "Job exited with non-zero status",
        )

    def _finish(
        self, result: JobResult, status: JobStatus, *, exit_code: int | None, error: str
    ) -> JobResult:
        ended_at = utc_now()
        duration = _duration_seconds(result.started_at, ended_at)
        artifact_paths = _collect_artifacts(result)
        failure_summary = (
            error if status in {JobStatus.FAILED, JobStatus.TIMEOUT} else ""
        )
        next_action = _next_action(status)
        updated = self.store.update_status(
            result.job_id,
            status,
            ended_at=ended_at,
            duration_seconds=duration,
            exit_code=exit_code,
            error=error,
            failure_summary=failure_summary,
            artifact_paths=artifact_paths,
            next_recommended_action=next_action,
        )
        report = generate_job_report(updated)
        updated = self.store.get_job(result.job_id)
        self.store.append_event(
            result.job_id,
            stage="report_generated",
            message="Job report generated",
            data=report.model_dump(mode="json"),
        )
        _close_handles(self.processes.get(result.job_id))
        self.processes.pop(result.job_id, None)
        return updated


def _terminate(process: object) -> None:
    try:
        process.terminate()
    except Exception:
        pass


def _close_handles(process: object | None) -> None:
    if process is None:
        return
    for name in ("_codexbridge_stdout_handle", "_codexbridge_stderr_handle"):
        handle = getattr(process, name, None)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


def _duration_seconds(started_at: str | None, ended_at: str) -> float | None:
    if not started_at:
        return None
    from datetime import datetime

    start = datetime.fromisoformat(started_at)
    end = datetime.fromisoformat(ended_at)
    return max(0.0, (end - start).total_seconds())


def _collect_artifacts(result: JobResult) -> list:
    from codexbridge.safety import is_secret_like_file

    profile = get_job_profile(result.job_profile)
    if profile is None or result.working_directory is None:
        return []
    roots = [
        result.working_directory.resolve(),
        result.result_json_path.parent.resolve(),
    ]
    collected = []
    for pattern in profile.allowed_artifact_globs:
        for path in result.working_directory.glob(pattern):
            resolved = path.resolve()
            if not path.is_file():
                continue
            if is_secret_like_file(str(resolved)):
                continue
            if any(_is_relative_to(resolved, root) for root in roots):
                collected.append(resolved)
    return sorted(set(collected))


def _is_relative_to(path, root) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _next_action(status: JobStatus) -> str:
    if status == JobStatus.COMPLETED:
        return "Review generated report and artifacts."
    if status == JobStatus.FAILED:
        return "Review stderr and decide whether to adjust the job profile or inputs."
    if status == JobStatus.TIMEOUT:
        return "Review partial output and consider a smaller approved job or a longer approved timeout."
    if status == JobStatus.CANCELLED:
        return "Confirm whether the cancellation was expected."
    return ""
