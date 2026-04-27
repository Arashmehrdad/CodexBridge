from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .supervisor_store import SupervisorStore, utc_now


TERMINAL_STATES = {"completed", "failed", "cancelled"}


@dataclass
class FakeJob:
    job_id: str
    kind: str
    status: str = "running"
    summary: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class FakeJobBackend:
    def __init__(self) -> None:
        self._counter = 0
        self.jobs: dict[str, FakeJob] = {}

    def start_plan(self, supervisor_id: str, payload: dict[str, Any]) -> FakeJob:
        return self._start("plan", supervisor_id, payload)

    def start_implementation(self, supervisor_id: str, payload: dict[str, Any]) -> FakeJob:
        return self._start("implementation", supervisor_id, payload)

    def get(self, job_id: str) -> FakeJob:
        if job_id not in self.jobs:
            raise KeyError(f"Fake job not found: {job_id}")
        return self.jobs[job_id]

    def complete(self, job_id: str, *, summary: str = "completed", result: dict[str, Any] | None = None) -> FakeJob:
        job = self.get(job_id)
        job.status = "completed"
        job.summary = summary
        job.result = result or {}
        job.error = ""
        return job

    def fail(self, job_id: str, *, error: str = "failed") -> FakeJob:
        job = self.get(job_id)
        job.status = "failed"
        job.error = error
        return job

    def cancel(self, job_id: str) -> FakeJob:
        job = self.get(job_id)
        job.status = "cancelled"
        return job

    def _start(self, kind: str, supervisor_id: str, payload: dict[str, Any]) -> FakeJob:
        self._counter += 1
        job_id = f"fake_{kind}_{self._counter:04d}"
        job = FakeJob(job_id=job_id, kind=kind, result={"supervisor_id": supervisor_id, "payload": payload})
        self.jobs[job_id] = job
        return job


class SupervisorEngine:
    def __init__(self, store: SupervisorStore, jobs: FakeJobBackend | None = None):
        self.store = store
        self.jobs = jobs or FakeJobBackend()

    def create_plan_supervisor(
        self,
        *,
        repo_name: str,
        objective: str,
        task: str,
        constraints: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        supervisor_metadata = {
            "plan": {"task": task, "constraints": constraints},
            "active_child": None,
            "plan_result": None,
            "implementation_result": None,
        }
        if metadata:
            supervisor_metadata.update(metadata)
        supervisor = self.store.create_supervisor(
            repo_name=repo_name,
            objective=objective,
            status="queued",
            metadata=supervisor_metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="queued",
            message="Supervisor queued",
            data={"repo_name": repo_name},
        )
        return supervisor

    def tick(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self.store.get_supervisor(supervisor_id)
        status = supervisor["status"]
        if status in TERMINAL_STATES or status == "needs_input":
            return supervisor
        if status == "queued":
            return self._start_plan(supervisor)
        if status == "planning":
            return self._advance_plan(supervisor)
        if status == "implementing":
            return self._advance_implementation(supervisor)
        raise ValueError(f"Unsupported supervisor status: {status}")

    def approve_plan(self, supervisor_id: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict[str, Any]:
        supervisor = self.store.get_supervisor(supervisor_id)
        if supervisor["status"] != "needs_input":
            raise ValueError("Plan approval is only valid from needs_input")
        metadata = dict(supervisor["metadata"])
        metadata["approval"] = {
            "approved_plan": approved_plan,
            "allowed_files": list(allowed_files),
            "tests": list(tests),
        }
        job = self.jobs.start_implementation(supervisor_id, metadata["approval"])
        metadata["active_child"] = {"job_id": job.job_id, "kind": "implementation"}
        updated = self.store.update_supervisor(supervisor_id, status="implementing", metadata_json=metadata)
        self.store.append_event(
            supervisor_id,
            level="info",
            stage="implementing",
            message="Fake implementation job started",
            data={"job_id": job.job_id},
        )
        return updated

    def cancel(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self.store.get_supervisor(supervisor_id)
        if supervisor["status"] in TERMINAL_STATES:
            return supervisor
        metadata = dict(supervisor["metadata"])
        active_child = metadata.get("active_child") or {}
        job_id = active_child.get("job_id")
        if job_id:
            self.jobs.cancel(job_id)
        metadata["cancelled_child"] = active_child or None
        metadata["active_child"] = None
        updated = self.store.update_supervisor(
            supervisor_id,
            status="cancelled",
            ended_at=utc_now(),
            summary="Supervisor cancelled",
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor_id,
            level="warning",
            stage="cancelled",
            message="Supervisor cancelled",
            data={"job_id": job_id},
        )
        return updated

    def _start_plan(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        job = self.jobs.start_plan(supervisor["supervisor_id"], metadata["plan"])
        metadata["active_child"] = {"job_id": job.job_id, "kind": "plan"}
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="planning",
            started_at=supervisor["started_at"] or utc_now(),
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="planning",
            message="Fake plan job started",
            data={"job_id": job.job_id},
        )
        return updated

    def _advance_plan(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        job = self._active_job(metadata, expected_kind="plan")
        if job.status == "running":
            return supervisor
        if job.status == "failed":
            return self._fail(supervisor, job.error or "Fake plan job failed")
        if job.status == "cancelled":
            return self.cancel(supervisor["supervisor_id"])
        if job.status != "completed":
            raise ValueError(f"Unsupported fake job status: {job.status}")
        metadata["plan_result"] = {"summary": job.summary, "result": job.result}
        metadata["active_child"] = None
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="needs_input",
            summary=job.summary,
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="needs_input",
            message="Plan completed; approval required",
            data={"job_id": job.job_id},
        )
        return updated

    def _advance_implementation(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        job = self._active_job(metadata, expected_kind="implementation")
        if job.status == "running":
            return supervisor
        if job.status == "failed":
            return self._fail(supervisor, job.error or "Fake implementation job failed")
        if job.status == "cancelled":
            return self.cancel(supervisor["supervisor_id"])
        if job.status != "completed":
            raise ValueError(f"Unsupported fake job status: {job.status}")
        metadata["implementation_result"] = {"summary": job.summary, "result": job.result}
        metadata["active_child"] = None
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="completed",
            ended_at=utc_now(),
            summary=job.summary,
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="completed",
            message="Implementation completed",
            data={"job_id": job.job_id},
        )
        return updated

    def _fail(self, supervisor: dict[str, Any], error: str) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        metadata["active_child"] = None
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="failed",
            ended_at=utc_now(),
            error=error,
            summary=error,
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="error",
            stage="failed",
            message=error,
            data={},
        )
        return updated

    def _active_job(self, metadata: dict[str, Any], *, expected_kind: str) -> FakeJob:
        active_child = metadata.get("active_child") or {}
        if active_child.get("kind") != expected_kind or not active_child.get("job_id"):
            raise ValueError(f"Supervisor is missing active {expected_kind} job metadata")
        return self.jobs.get(active_child["job_id"])
