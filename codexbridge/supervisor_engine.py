from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .config import AppConfig
from .job_manager import JobManager
from .policy import (
    BalancedAutonomyProfile,
    decide_implementation_task,
    decide_plan_task,
    evaluate_implementation_profile,
    evaluate_plan_profile,
    profile_snapshot,
)
from .supervisor_store import SupervisorStore, utc_now


TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"queued", "running"}


class ChildJobBackend(Protocol):
    def start_plan(self, repo_name: str, task: str, constraints: str) -> dict[str, Any]:
        ...

    def start_implementation(self, repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict[str, Any]:
        ...

    def get_status(self, run_id: str) -> dict[str, Any]:
        ...

    def get_result(self, run_id: str) -> dict[str, Any]:
        ...

    def cancel(self, run_id: str) -> dict[str, Any]:
        ...


class JobManagerChildBackend:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.manager = JobManager(config, config_path)

    def start_plan(self, repo_name: str, task: str, constraints: str) -> dict[str, Any]:
        return self.manager.start_plan(repo_name, task, constraints)

    def start_implementation(self, repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict[str, Any]:
        return self.manager.start_implementation(repo_name, approved_plan, allowed_files, tests)

    def get_status(self, run_id: str) -> dict[str, Any]:
        return self.manager.get_status(run_id)

    def get_result(self, run_id: str) -> dict[str, Any]:
        return self.manager.get_result(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        return self.manager.cancel_run(run_id)


@dataclass
class FakeChildJob:
    run_id: str
    kind: str
    status: str = "running"
    summary: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cancel_requested: bool = False


class FakeChildJobBackend:
    def __init__(self) -> None:
        self._counter = 0
        self.jobs: dict[str, FakeChildJob] = {}

    def start_plan(self, repo_name: str, task: str, constraints: str) -> dict[str, Any]:
        return self._start("plan", {"repo_name": repo_name, "task": task, "constraints": constraints})

    def start_implementation(self, repo_name: str, approved_plan: str, allowed_files: list[str], tests: list[str]) -> dict[str, Any]:
        return self._start(
            "implementation",
            {"repo_name": repo_name, "approved_plan": approved_plan, "allowed_files": list(allowed_files), "tests": list(tests)},
        )

    def get_status(self, run_id: str) -> dict[str, Any]:
        job = self.get(run_id)
        return {"run_id": run_id, "status": job.status, "summary": job.summary, "error": job.error}

    def get_result(self, run_id: str) -> dict[str, Any]:
        job = self.get(run_id)
        return {
            "run_id": run_id,
            "status": job.status,
            "summary": job.summary,
            "error": job.error,
            **job.result,
        }

    def cancel(self, run_id: str) -> dict[str, Any]:
        job = self.get(run_id)
        job.status = "cancelled"
        job.cancel_requested = True
        return {"run_id": run_id, "status": "cancelled", "cancelled": True}

    def get(self, run_id: str) -> FakeChildJob:
        if run_id not in self.jobs:
            raise KeyError(f"Fake child job not found: {run_id}")
        return self.jobs[run_id]

    def complete(self, run_id: str, *, summary: str = "completed", result: dict[str, Any] | None = None) -> FakeChildJob:
        job = self.get(run_id)
        job.status = "completed"
        job.summary = summary
        job.result = result or {}
        job.error = ""
        return job

    def fail(self, run_id: str, *, error: str = "failed") -> FakeChildJob:
        job = self.get(run_id)
        job.status = "failed"
        job.error = error
        return job

    def _start(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        run_id = f"20260428T1200{self._counter:02d}Z_codex_{kind}_task_{self._counter:08x}"
        self.jobs[run_id] = FakeChildJob(run_id=run_id, kind=kind, result={"payload": payload})
        return {
            "run_id": run_id,
            "accepted": True,
            "status": "queued",
            "estimated_duration_minutes": 1,
            "recommended_check_after_minutes": 1,
            "risk_level": "low",
            "requires_human": False,
            "reason": "",
        }


# Backward-compatible test alias from Batch 2.
FakeJobBackend = FakeChildJobBackend


class SupervisorEngine:
    def __init__(self, store: SupervisorStore, jobs: ChildJobBackend, autonomy_profile: Any | None = None, profile_name: str = "balanced"):
        self.store = store
        self.jobs = jobs
        self.autonomy_profile = autonomy_profile or BalancedAutonomyProfile()
        self.profile_name = profile_name

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
            "approval": None,
            "implementation_result": None,
            "implementation_lock": None,
            "blocked": None,
            "policy": {
                "profile": profile_snapshot(self.autonomy_profile, self.profile_name),
                "plan": None,
                "implementation": None,
            },
            "hard_stop": None,
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
        decision = decide_implementation_task(approved_plan, allowed_files, tests)
        policy_result = evaluate_implementation_profile(
            decision,
            self.autonomy_profile,
            allowed_files=allowed_files,
            tests=tests,
            profile_name=self.profile_name,
        )
        self._record_policy(metadata, "implementation", policy_result)
        if not policy_result.allowed:
            return self._hard_stop(supervisor, metadata, stage="implementation_policy", policy_result=policy_result)

        lock = self.store.acquire_repo_lock(
            supervisor["repo_name"],
            owner_id=supervisor_id,
            reason="supervisor implementation",
        )
        if lock is None:
            metadata["blocked"] = {"reason": "repo_write_lock_unavailable", "at": utc_now()}
            updated = self.store.update_supervisor(supervisor_id, metadata_json=metadata)
            self.store.append_event(
                supervisor_id,
                level="warning",
                stage="blocked",
                message="Implementation blocked by repo write lock",
                data={"repo_name": supervisor["repo_name"]},
            )
            self._notify(
                updated,
                event_stage="blocked",
                event_level="warning",
                kind="blocked_by_lock",
                title="CodexBridge supervisor blocked",
                message="Implementation is blocked by an active repo write lock.",
                payload={"repo_name": supervisor["repo_name"], "reason": "repo_write_lock_unavailable"},
                dedupe_key="blocked_by_lock",
            )
            return updated

        metadata["implementation_lock"] = lock
        metadata["blocked"] = None
        try:
            response = self.jobs.start_implementation(supervisor["repo_name"], approved_plan, allowed_files, tests)
            run_id = self._accepted_run_id(response)
            metadata["active_child"] = {"run_id": run_id, "kind": "implementation"}
            updated = self.store.update_supervisor(supervisor_id, status="implementing", metadata_json=metadata)
            self.store.add_run_link(supervisor_id, run_id, "implementation")
            self.store.append_event(
                supervisor_id,
                level="info",
                stage="implementing",
                message="Implementation child run started",
                data={"run_id": run_id, "lock_id": lock["lock_id"]},
            )
            return updated
        except Exception:
            self.store.release_repo_lock(lock["lock_id"])
            metadata["implementation_lock"] = None
            self.store.update_supervisor(supervisor_id, metadata_json=metadata)
            raise

    def cancel(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self.store.get_supervisor(supervisor_id)
        if supervisor["status"] in TERMINAL_STATES:
            return supervisor
        metadata = dict(supervisor["metadata"])
        active_child = metadata.get("active_child") or {}
        run_id = active_child.get("run_id")
        if run_id:
            self.jobs.cancel(run_id)
        self._release_implementation_lock(metadata)
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
            data={"run_id": run_id},
        )
        self._notify(
            updated,
            event_stage="cancelled",
            event_level="warning",
            kind="cancelled",
            title="CodexBridge supervisor cancelled",
            message="Supervisor was cancelled.",
            payload={"run_id": run_id},
            dedupe_key="cancelled",
        )
        return updated

    def _start_plan(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        plan = metadata["plan"]
        decision = decide_plan_task(plan["task"], plan.get("constraints", ""))
        policy_result = evaluate_plan_profile(decision, self.autonomy_profile, self.profile_name)
        self._record_policy(metadata, "plan", policy_result)
        if not policy_result.allowed:
            return self._hard_stop(supervisor, metadata, stage="plan_policy", policy_result=policy_result)

        response = self.jobs.start_plan(supervisor["repo_name"], metadata["plan"]["task"], metadata["plan"].get("constraints", ""))
        run_id = self._accepted_run_id(response)
        metadata["active_child"] = {"run_id": run_id, "kind": "plan"}
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="planning",
            started_at=supervisor["started_at"] or utc_now(),
            metadata_json=metadata,
        )
        self.store.add_run_link(supervisor["supervisor_id"], run_id, "plan")
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="planning",
            message="Plan child run started",
            data={"run_id": run_id},
        )
        return updated

    def _advance_plan(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        run_id = self._active_run_id(metadata, expected_kind="plan")
        status = self.jobs.get_status(run_id).get("status")
        if status in ACTIVE_STATES:
            return supervisor
        if status == "failed":
            result = self.jobs.get_result(run_id)
            return self._fail(supervisor, result.get("error") or result.get("summary") or "Plan child run failed", metadata=metadata)
        if status == "cancelled":
            return self._cancel_from_child(supervisor, metadata, run_id)
        if status != "completed":
            raise ValueError(f"Unsupported child run status: {status}")
        result = self.jobs.get_result(run_id)
        metadata["plan_result"] = result
        metadata["active_child"] = None
        summary = result.get("summary", "")
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="needs_input",
            summary=summary,
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="needs_input",
            message="Plan completed; approval required",
            data={"run_id": run_id},
        )
        return updated

    def _advance_implementation(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        run_id = self._active_run_id(metadata, expected_kind="implementation")
        status = self.jobs.get_status(run_id).get("status")
        if status in ACTIVE_STATES:
            return supervisor
        if status == "failed":
            result = self.jobs.get_result(run_id)
            self._release_implementation_lock(metadata)
            return self._fail(
                supervisor,
                result.get("error") or result.get("summary") or "Implementation child run failed",
                metadata=metadata,
            )
        if status == "cancelled":
            self._release_implementation_lock(metadata)
            return self._cancel_from_child(supervisor, metadata, run_id)
        if status != "completed":
            raise ValueError(f"Unsupported child run status: {status}")
        result = self.jobs.get_result(run_id)
        metadata["implementation_result"] = result
        metadata["active_child"] = None
        self._release_implementation_lock(metadata)
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="completed",
            ended_at=utc_now(),
            summary=result.get("summary", ""),
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="completed",
            message="Implementation completed",
            data={"run_id": run_id},
        )
        self._notify(
            updated,
            event_stage="completed",
            event_level="info",
            kind="completed",
            title="CodexBridge supervisor completed",
            message="Supervisor completed implementation.",
            payload={"run_id": run_id, "summary": result.get("summary", "")},
            dedupe_key="completed",
        )
        return updated

    def _fail(self, supervisor: dict[str, Any], error: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = dict(metadata or supervisor["metadata"])
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
        self._notify(
            updated,
            event_stage="failed",
            event_level="error",
            kind="failed",
            title="CodexBridge supervisor failed",
            message=error,
            payload={"error": error},
            dedupe_key="failed",
        )
        return updated

    def _record_policy(self, metadata: dict[str, Any], phase: str, policy_result) -> None:
        policy = dict(metadata.get("policy") or {})
        policy["profile"] = policy_result.profile_snapshot
        policy[phase] = policy_result.hard_stop["decision"]
        metadata["policy"] = policy

    def _hard_stop(self, supervisor: dict[str, Any], metadata: dict[str, Any], *, stage: str, policy_result) -> dict[str, Any]:
        hard_stop = dict(policy_result.hard_stop)
        hard_stop["stage"] = stage
        hard_stop["at"] = utc_now()
        metadata["hard_stop"] = hard_stop
        metadata["active_child"] = None
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="needs_input",
            policy_tier=policy_result.decision.tier,
            risk_level=policy_result.decision.risk_level,
            requires_human=policy_result.decision.requires_human,
            summary=policy_result.decision.reason or "Supervisor hard-stop requires input",
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="warning",
            stage=stage,
            message="Supervisor hard-stop requires input",
            data=hard_stop,
        )
        self._notify(
            updated,
            event_stage=stage,
            event_level="warning",
            kind="hard_stop",
            title="CodexBridge supervisor needs input",
            message=policy_result.decision.reason or "Supervisor requires input.",
            payload=hard_stop,
            dedupe_key=f"hard_stop:{stage}",
        )
        return updated

    def _cancel_from_child(self, supervisor: dict[str, Any], metadata: dict[str, Any], run_id: str) -> dict[str, Any]:
        metadata["active_child"] = None
        updated = self.store.update_supervisor(
            supervisor["supervisor_id"],
            status="cancelled",
            ended_at=utc_now(),
            summary="Child run cancelled",
            metadata_json=metadata,
        )
        self.store.append_event(
            supervisor["supervisor_id"],
            level="warning",
            stage="cancelled",
            message="Child run cancelled",
            data={"run_id": run_id},
        )
        self._notify(
            updated,
            event_stage="cancelled",
            event_level="warning",
            kind="cancelled",
            title="CodexBridge supervisor cancelled",
            message="Child run was cancelled.",
            payload={"run_id": run_id},
            dedupe_key="cancelled",
        )
        return updated

    def _notify(
        self,
        supervisor: dict[str, Any],
        *,
        event_stage: str,
        event_level: str,
        kind: str,
        title: str,
        message: str,
        payload: dict[str, Any],
        dedupe_key: str,
    ) -> dict[str, Any]:
        return self.store.create_notification(
            supervisor["supervisor_id"],
            event_stage=event_stage,
            event_level=event_level,
            kind=kind,
            title=title,
            message=message,
            payload=payload,
            dedupe_key=dedupe_key,
        )

    def _release_implementation_lock(self, metadata: dict[str, Any]) -> None:
        lock = metadata.get("implementation_lock")
        if lock and lock.get("lock_id"):
            self.store.release_repo_lock(lock["lock_id"])
        metadata["implementation_lock"] = None

    def _accepted_run_id(self, response: dict[str, Any]) -> str:
        if not response.get("accepted") or not response.get("run_id"):
            raise ValueError(response.get("reason") or "Child run was not accepted")
        return str(response["run_id"])

    def _active_run_id(self, metadata: dict[str, Any], *, expected_kind: str) -> str:
        active_child = metadata.get("active_child") or {}
        if active_child.get("kind") != expected_kind or not active_child.get("run_id"):
            raise ValueError(f"Supervisor is missing active {expected_kind} run metadata")
        return str(active_child["run_id"])
