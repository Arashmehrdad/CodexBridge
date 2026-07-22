from __future__ import annotations

import subprocess
import time
from pathlib import Path
from uuid import uuid4

from soma.config import AppConfig, resolve_repo
from soma.local_agent.audit import create_audit_event
from soma.local_agent.models import PermissionTier
from soma.run_store import utc_now

from .job_monitor import JobMonitor
from .job_profiles import get_job_profile
from .job_reporter import generate_job_report
from .job_store import JobStore
from .models import JobCancelResult, JobResult, JobStatus, JobStatusResult


class LongRunJobManager:
    def __init__(
        self,
        config: AppConfig | None = None,
        runs_dir: Path | None = None,
        popen_factory=None,
        *,
        allow_legacy_execution: bool = False,
    ):
        self.config = config
        self.runs_dir = (
            runs_dir or (config.resolve_runs_dir() if config else Path.cwd() / "runs")
        ).resolve()
        self.store = JobStore(self.runs_dir)
        self.processes: dict[str, object] = {}
        self.popen_factory = popen_factory or subprocess.Popen
        self.allow_legacy_execution = bool(allow_legacy_execution)
        self.monitor = JobMonitor(self.store, self.processes)
        self._contain_unowned_jobs()

    def _contain_unowned_jobs(self) -> None:
        for job in self.store.list_jobs(limit=100):
            if job.status in {
                JobStatus.CREATED,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
            } and job.job_id not in self.processes:
                self.monitor.contain_unowned(job.job_id)

    def start_job(
        self,
        *,
        profile_id: str,
        repo_name: str | None = None,
        repo_path: str | Path | None = None,
        timeout_seconds: int | None = None,
    ) -> JobStatusResult:
        created_at = utc_now()
        job_id = f"{created_at.replace('-', '').replace(':', '').split('.')[0]}_job_{uuid4().hex[:8]}"
        job_dir = self.store.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        audit = create_audit_event(
            task_id=job_id,
            action="job_requested",
            message=f"Job requested: {profile_id}",
            metadata={"profile_id": profile_id},
        )
        profile = get_job_profile(profile_id)
        if profile is None:
            return self._blocked(
                job_id,
                profile_id,
                repo_name,
                repo_path,
                JobStatus.PROFILE_MISSING,
                "Unknown job profile",
                created_at,
                audit.event_id,
            )
        if not profile.enabled:
            return self._blocked(
                job_id,
                profile_id,
                repo_name,
                repo_path,
                JobStatus.BLOCKED,
                "Job profile is disabled",
                created_at,
                audit.event_id,
                argv=profile.argv,
            )
        if _looks_shell_like(profile_id):
            return self._blocked(
                job_id,
                profile_id,
                repo_name,
                repo_path,
                JobStatus.BLOCKED,
                "Shell-like job profile IDs are not allowed",
                created_at,
                audit.event_id,
            )
        effective_timeout = (
            timeout_seconds if timeout_seconds is not None else profile.timeout_seconds
        )
        if effective_timeout > profile.timeout_seconds:
            return self._blocked(
                job_id,
                profile_id,
                repo_name,
                repo_path,
                JobStatus.PERMISSION_DENIED,
                "Requested timeout exceeds job profile maximum",
                created_at,
                audit.event_id,
                argv=profile.argv,
            )
        working_directory, repo_error = self._resolve_working_directory(
            repo_name, repo_path
        )
        if repo_error:
            return self._blocked(
                job_id,
                profile_id,
                repo_name,
                repo_path,
                JobStatus.REPO_MISSING,
                repo_error,
                created_at,
                audit.event_id,
                argv=profile.argv,
            )
        if not self.allow_legacy_execution:
            return self._blocked(
                job_id,
                profile_id,
                repo_name,
                repo_path,
                JobStatus.BLOCKED,
                "Legacy in-memory long-run execution is disabled because process ownership cannot survive manager recreation.",
                created_at,
                audit.event_id,
                argv=profile.argv,
                next_recommended_action=(
                    "Route unattended work through the durable JobManager and RunStore path."
                ),
            )

        result = self._new_result(
            job_id=job_id,
            profile_id=profile_id,
            repo_name=repo_name,
            repo_path=Path(repo_path).resolve() if repo_path else None,
            argv=profile.argv,
            permission_tier=profile.permission_tier,
            status=JobStatus.CREATED,
            created_at=created_at,
            timeout_seconds=effective_timeout,
            audit_event_id=audit.event_id,
            working_directory=working_directory,
        )
        self.store.create_job(result)
        self.store.append_event(
            job_id,
            stage="job_allowed",
            message="Job profile allowed",
            data={"profile_id": profile_id},
        )
        stdout_handle = result.stdout_path.open("w", encoding="utf-8")
        stderr_handle = result.stderr_path.open("w", encoding="utf-8")
        try:
            process = self.popen_factory(
                list(profile.argv),
                cwd=working_directory,
                shell=False,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
            )
        except Exception as exc:
            stdout_handle.close()
            stderr_handle.close()
            failed = self.store.update_status(
                job_id,
                JobStatus.FAILED,
                ended_at=utc_now(),
                error=str(exc),
                failure_summary=str(exc),
                next_recommended_action="Review job profile command availability.",
            )
            return JobStatusResult(job=failed, events=self.store.get_events(job_id))
        setattr(process, "_soma_stdout_handle", stdout_handle)
        setattr(process, "_soma_stderr_handle", stderr_handle)
        setattr(process, "_soma_started_monotonic", time.monotonic())
        self.processes[job_id] = process
        result.status = JobStatus.RUNNING
        result.started_at = utc_now()
        result.pid = getattr(process, "pid", None)
        self.store.write_result(result)
        self.store.append_event(
            job_id,
            stage="job_started",
            message="Job started",
            data={"pid": result.pid, "profile_id": profile_id},
        )
        return JobStatusResult(job=result, events=self.store.get_events(job_id))

    def get_status(self, job_id: str) -> JobStatusResult:
        job = self.store.get_job(job_id)
        return JobStatusResult(job=job, events=self.store.get_events(job_id))

    def list_jobs(self, limit: int = 20) -> list[JobResult]:
        return self.store.list_jobs(limit)

    def refresh_status(self, job_id: str) -> JobStatusResult:
        job = self.monitor.refresh_status(job_id)
        _close_handles(self.processes.get(job_id))
        return JobStatusResult(job=job, events=self.store.get_events(job_id))

    def collect_result(self, job_id: str) -> JobStatusResult:
        return self.refresh_status(job_id)

    def cancel_job(self, job_id: str) -> JobCancelResult:
        job = self.store.get_job(job_id)
        process = self.processes.get(job_id)
        audit = create_audit_event(
            task_id=job_id,
            action="job_cancel_requested",
            message="Job cancellation requested",
        )
        if process is None and job.status in {
            JobStatus.CREATED,
            JobStatus.QUEUED,
            JobStatus.RUNNING,
        }:
            updated = self.monitor.contain_unowned(
                job_id,
                reason=(
                    "Legacy job cancellation cannot be confirmed because the owning process handle is unavailable."
                ),
            )
            return JobCancelResult(
                job_id=job_id,
                status=updated.status,
                message="Cancellation requires manual process verification",
                audit_event_id=audit.event_id,
            )
        if process is None or job.status != JobStatus.RUNNING:
            return JobCancelResult(
                job_id=job_id,
                status=job.status,
                message=f"Job is already {job.status.value}",
                audit_event_id=audit.event_id,
            )
        try:
            process.terminate()
        except Exception:
            pass
        _close_handles(process)
        updated = self.store.update_status(
            job_id,
            JobStatus.CANCELLED,
            ended_at=utc_now(),
            duration_seconds=_duration_from_process(process),
            next_recommended_action="Confirm whether the cancellation was expected.",
        )
        generate_job_report(updated)
        self.store.append_event(job_id, stage="job_cancelled", message="Job cancelled")
        self.store.append_event(
            job_id, stage="report_generated", message="Job report generated"
        )
        self.processes.pop(job_id, None)
        return JobCancelResult(
            job_id=job_id,
            status=JobStatus.CANCELLED,
            message="Job cancelled",
            audit_event_id=audit.event_id,
        )

    def generate_report(self, job_id: str):
        job = self.store.get_job(job_id)
        report = generate_job_report(job)
        self.store.append_event(
            job_id,
            stage="report_generated",
            message="Job report generated",
            data=report.model_dump(mode="json"),
        )
        return report

    def _resolve_working_directory(
        self, repo_name: str | None, repo_path: str | Path | None
    ) -> tuple[Path | None, str]:
        if repo_name:
            if self.config is None:
                return None, "repo_name requires an AppConfig for resolution."
            try:
                return resolve_repo(self.config, repo_name), ""
            except Exception as exc:
                return None, str(exc)
        if repo_path:
            path = Path(repo_path).resolve()
            if not path.exists() or not path.is_dir():
                return None, f"Repo path does not exist or is not a directory: {path}"
            return path, ""
        return Path.cwd().resolve(), ""

    def _blocked(
        self,
        job_id,
        profile_id,
        repo_name,
        repo_path,
        status,
        error,
        created_at,
        audit_event_id,
        argv=None,
        next_recommended_action="Use an enabled allowlisted job profile.",
    ) -> JobStatusResult:
        result = self._new_result(
            job_id=job_id,
            profile_id=profile_id,
            repo_name=repo_name,
            repo_path=Path(repo_path).resolve() if repo_path else None,
            argv=argv or [],
            permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            status=status,
            created_at=created_at,
            timeout_seconds=0,
            audit_event_id=audit_event_id,
            working_directory=None,
            error=error,
            failure_summary=error,
            next_recommended_action=next_recommended_action,
        )
        self.store.create_job(result)
        self.store.append_event(
            job_id,
            stage="job_blocked",
            message=error,
            level="warning",
            data={"status": status.value, "profile_id": profile_id},
        )
        return JobStatusResult(job=result, events=self.store.get_events(job_id))

    def _new_result(
        self,
        *,
        job_id: str,
        profile_id: str,
        repo_name: str | None,
        repo_path: Path | None,
        argv: list[str],
        permission_tier: PermissionTier,
        status: JobStatus,
        created_at: str,
        timeout_seconds: int,
        audit_event_id: str,
        working_directory: Path | None,
        error: str = "",
        failure_summary: str = "",
        next_recommended_action: str = "",
    ) -> JobResult:
        job_dir = self.store.job_dir(job_id)
        return JobResult(
            job_id=job_id,
            repo_name=repo_name,
            repo_path=repo_path,
            job_profile=profile_id,
            argv=list(argv),
            permission_tier=permission_tier,
            status=status,
            created_at=created_at,
            timeout_seconds=timeout_seconds,
            working_directory=working_directory,
            stdout_path=job_dir / "stdout.txt",
            stderr_path=job_dir / "stderr.txt",
            events_path=job_dir / "events.jsonl",
            result_json_path=job_dir / "result.json",
            audit_event_id=audit_event_id,
            error=error,
            failure_summary=failure_summary,
            next_recommended_action=next_recommended_action,
        )


def _looks_shell_like(value: str) -> bool:
    return any(token in value for token in (" ", ";", "&", "|", ">", "<", "\n", "\r"))


def _close_handles(process: object | None) -> None:
    if process is None:
        return
    for name in ("_soma_stdout_handle", "_soma_stderr_handle"):
        handle = getattr(process, name, None)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


def _duration_from_process(process: object | None) -> float | None:
    if process is None:
        return None
    started = getattr(process, "_soma_started_monotonic", None)
    if started is None:
        return None
    return max(0.0, time.monotonic() - started)
