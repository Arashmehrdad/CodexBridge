from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .config import AppConfig
from .job_manager import JobManager, make_run_id
from .policy import (
    BalancedAutonomyProfile,
    decide_implementation_task,
    decide_plan_task,
    evaluate_implementation_profile,
    evaluate_plan_profile,
    profile_snapshot,
)
from .supervisor_resume_prompt import write_resume_prompt
from .supervisor_store import SupervisorStore, utc_now


TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"queued", "running"}


class ChildJobBackend(Protocol):
    def start_plan(
        self,
        repo_name: str,
        task: str,
        constraints: str,
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]: ...

    def start_implementation(
        self,
        repo_name: str,
        approved_plan: str,
        allowed_files: list[str],
        tests: list[str],
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]: ...

    def get_status(self, run_id: str) -> dict[str, Any]: ...

    def get_result(self, run_id: str) -> dict[str, Any]: ...

    def cancel(self, run_id: str) -> dict[str, Any]: ...


class JobManagerChildBackend:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.manager = JobManager(config, config_path)

    def start_plan(
        self,
        repo_name: str,
        task: str,
        constraints: str,
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]:
        return self.manager.start_plan(
            repo_name,
            task,
            constraints,
            reserved_run_id=reserved_run_id,
        )

    def start_implementation(
        self,
        repo_name: str,
        approved_plan: str,
        allowed_files: list[str],
        tests: list[str],
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]:
        return self.manager.start_implementation(
            repo_name,
            approved_plan,
            allowed_files,
            tests,
            reserved_run_id=reserved_run_id,
        )

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

    def start_plan(
        self,
        repo_name: str,
        task: str,
        constraints: str,
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]:
        return self._start(
            "plan",
            {"repo_name": repo_name, "task": task, "constraints": constraints},
            reserved_run_id=reserved_run_id,
        )

    def start_implementation(
        self,
        repo_name: str,
        approved_plan: str,
        allowed_files: list[str],
        tests: list[str],
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]:
        return self._start(
            "implementation",
            {
                "repo_name": repo_name,
                "approved_plan": approved_plan,
                "allowed_files": list(allowed_files),
                "tests": list(tests),
            },
            reserved_run_id=reserved_run_id,
        )

    def get_status(self, run_id: str) -> dict[str, Any]:
        job = self.get(run_id)
        return {
            "run_id": run_id,
            "status": job.status,
            "summary": job.summary,
            "error": job.error,
        }

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

    def complete(
        self,
        run_id: str,
        *,
        summary: str = "completed",
        result: dict[str, Any] | None = None,
    ) -> FakeChildJob:
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

    def _start(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        reserved_run_id: str | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        run_id = reserved_run_id or (
            f"20260428T1200{self._counter:02d}Z_codex_{kind}_task_{self._counter:08x}"
        )
        self.jobs[run_id] = FakeChildJob(
            run_id=run_id, kind=kind, result={"payload": payload}
        )
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
    def __init__(
        self,
        store: SupervisorStore,
        jobs: ChildJobBackend,
        autonomy_profile: Any | None = None,
        profile_name: str = "balanced",
    ):
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

    def approve_plan(
        self,
        supervisor_id: str,
        approved_plan: str,
        allowed_files: list[str],
        tests: list[str],
    ) -> dict[str, Any]:
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
            return self._hard_stop(
                supervisor,
                metadata,
                stage="implementation_policy",
                policy_result=policy_result,
            )

        metadata["blocked"] = None
        run_id = make_run_id("codex_implement_task")
        attached = self.store.attach_child(
            supervisor_id,
            run_id=run_id,
            link_type="implementation",
            child_kind="implementation",
            target_status="implementing",
            metadata=metadata,
            expected_statuses=("needs_input",),
            expected_state_version=int(supervisor["state_version"]),
        )
        if attached is None:
            return self.store.get_supervisor(supervisor_id)
        return self._ensure_child_launched(attached, expected_kind="implementation")

    def cancel(self, supervisor_id: str) -> dict[str, Any]:
        supervisor = self.store.get_supervisor(supervisor_id)
        if supervisor["status"] in TERMINAL_STATES:
            return supervisor
        metadata = dict(supervisor["metadata"])
        active_child = metadata.get("active_child") or {}
        run_id = active_child.get("run_id")
        if run_id:
            try:
                cancellation = self.jobs.cancel(run_id)
            except KeyError:
                cancellation = {}
            if cancellation.get("status") != "cancelled":
                blocked_metadata = dict(metadata)
                blocked_metadata["blocked"] = {
                    "reason": "child_cancellation_unverified",
                    "run_id": run_id,
                    "at": utc_now(),
                }
                updated = self.store.conditional_update_supervisor(
                    supervisor_id,
                    fields={
                        "status": "needs_input",
                        "summary": "Child cancellation could not be verified",
                        "metadata_json": blocked_metadata,
                    },
                    expected_statuses=(supervisor["status"],),
                    expected_state_version=int(supervisor["state_version"]),
                )
                if updated is None:
                    return self.store.get_supervisor(supervisor_id)
                self._write_resume_prompt(updated)
                self.store.append_event(
                    supervisor_id,
                    level="warning",
                    stage="cancellation_unverified",
                    message="Supervisor child cancellation could not be verified",
                    data={"run_id": run_id},
                )
                return updated
        metadata["cancelled_child"] = active_child or None
        metadata["active_child"] = None
        metadata["implementation_lock"] = None
        updated = self.store.conditional_update_supervisor(
            supervisor_id,
            fields={
                "status": "cancelled",
                "ended_at": utc_now(),
                "summary": "Supervisor cancelled",
                "metadata_json": metadata,
            },
            expected_statuses=(supervisor["status"],),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor_id)
        self._write_resume_prompt(updated)
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
        policy_result = evaluate_plan_profile(
            decision, self.autonomy_profile, self.profile_name
        )
        self._record_policy(metadata, "plan", policy_result)
        if not policy_result.allowed:
            return self._hard_stop(
                supervisor, metadata, stage="plan_policy", policy_result=policy_result
            )

        run_id = make_run_id("codex_plan_task")
        attached = self.store.attach_child(
            supervisor["supervisor_id"],
            run_id=run_id,
            link_type="plan",
            child_kind="plan",
            target_status="planning",
            metadata=metadata,
            expected_statuses=("queued",),
            expected_state_version=int(supervisor["state_version"]),
            started_at=supervisor["started_at"] or utc_now(),
        )
        if attached is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])

        return self._ensure_child_launched(attached, expected_kind="plan")

    def _advance_plan(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        supervisor = self._ensure_child_launched(supervisor, expected_kind="plan")
        if supervisor["status"] != "planning":
            return supervisor
        metadata = dict(supervisor["metadata"])
        run_id = self._active_run_id(metadata, expected_kind="plan")
        status = self.jobs.get_status(run_id).get("status")
        if status in ACTIVE_STATES:
            return supervisor
        if status == "failed":
            result = self.jobs.get_result(run_id)
            return self._fail(
                supervisor,
                result.get("error") or result.get("summary") or "Plan child run failed",
                metadata=metadata,
            )
        if status == "cancelled":
            return self._cancel_from_child(supervisor, metadata, run_id)
        if status != "completed":
            raise ValueError(f"Unsupported child run status: {status}")
        result = self.jobs.get_result(run_id)
        metadata["plan_result"] = result
        metadata["active_child"] = None
        summary = result.get("summary", "")
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": "needs_input",
                "summary": summary,
                "metadata_json": metadata,
            },
            expected_statuses=("planning",),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self._attach_links_and_write_prompt(updated)
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="needs_input",
            message="Plan completed; approval required",
            data={"run_id": run_id},
        )
        return updated

    def _advance_implementation(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        supervisor = self._ensure_child_launched(
            supervisor, expected_kind="implementation"
        )
        if supervisor["status"] != "implementing":
            return supervisor
        metadata = dict(supervisor["metadata"])
        run_id = self._active_run_id(metadata, expected_kind="implementation")
        status = self.jobs.get_status(run_id).get("status")
        if status in ACTIVE_STATES:
            return supervisor
        if status == "failed":
            result = self.jobs.get_result(run_id)
            metadata["implementation_lock"] = None
            updated = self._fail(
                supervisor,
                result.get("error")
                or result.get("summary")
                or "Implementation child run failed",
                metadata=metadata,
            )
            return updated
        if status == "cancelled":
            metadata["implementation_lock"] = None
            updated = self._cancel_from_child(supervisor, metadata, run_id)
            return updated
        if status != "completed":
            raise ValueError(f"Unsupported child run status: {status}")
        result = self.jobs.get_result(run_id)
        metadata["implementation_result"] = result
        metadata["active_child"] = None
        metadata["implementation_lock"] = None
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": "completed",
                "ended_at": utc_now(),
                "summary": result.get("summary", ""),
                "metadata_json": metadata,
            },
            expected_statuses=("implementing",),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self._attach_links_and_write_prompt(updated)
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

    def _fail(
        self,
        supervisor: dict[str, Any],
        error: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(metadata or supervisor["metadata"])
        metadata["active_child"] = None
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": "failed",
                "ended_at": utc_now(),
                "error": error,
                "summary": error,
                "metadata_json": metadata,
            },
            expected_statuses=(supervisor["status"],),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self._write_resume_prompt(updated)
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

    def _record_policy(
        self, metadata: dict[str, Any], phase: str, policy_result
    ) -> None:
        policy = dict(metadata.get("policy") or {})
        policy["profile"] = policy_result.profile_snapshot
        policy[phase] = policy_result.hard_stop["decision"]
        metadata["policy"] = policy

    def _hard_stop(
        self,
        supervisor: dict[str, Any],
        metadata: dict[str, Any],
        *,
        stage: str,
        policy_result,
    ) -> dict[str, Any]:
        hard_stop = dict(policy_result.hard_stop)
        hard_stop["stage"] = stage
        hard_stop["at"] = utc_now()
        metadata["hard_stop"] = hard_stop
        metadata["active_child"] = None
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": "needs_input",
                "policy_tier": policy_result.decision.tier,
                "risk_level": policy_result.decision.risk_level,
                "requires_human": policy_result.decision.requires_human,
                "summary": policy_result.decision.reason
                or "Supervisor hard-stop requires input",
                "metadata_json": metadata,
            },
            expected_statuses=(supervisor["status"],),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self._write_resume_prompt(updated)
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

    def _cancel_from_child(
        self, supervisor: dict[str, Any], metadata: dict[str, Any], run_id: str
    ) -> dict[str, Any]:
        metadata["active_child"] = None
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": "cancelled",
                "ended_at": utc_now(),
                "summary": "Child run cancelled",
                "metadata_json": metadata,
            },
            expected_statuses=(supervisor["status"],),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self._write_resume_prompt(updated)
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

    def _attach_links_and_write_prompt(self, supervisor: dict[str, Any]) -> None:
        enriched = dict(supervisor)
        enriched["run_links"] = self.store.list_run_links(supervisor["supervisor_id"])
        self._write_resume_prompt(enriched)

    def _write_resume_prompt(self, supervisor: dict[str, Any]) -> None:
        enriched = dict(supervisor)
        enriched.setdefault(
            "run_links", self.store.list_run_links(supervisor["supervisor_id"])
        )
        write_resume_prompt(self.store.runs_dir, enriched)

    def _block_implementation_launch(
        self,
        supervisor: dict[str, Any],
        metadata: dict[str, Any],
        run_id: str,
        launch_reason: str,
    ) -> dict[str, Any]:
        blocked_metadata = dict(metadata)
        blocked_metadata["active_child"] = None
        blocked_metadata["implementation_lock"] = None
        blocked_metadata["blocked"] = {
            "reason": "repository_operation_lock_unavailable",
            "launch_reason": launch_reason,
            "run_id": run_id,
            "at": utc_now(),
        }
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": "needs_input",
                "summary": "Implementation blocked by active repository ownership",
                "metadata_json": blocked_metadata,
            },
            expected_statuses=("implementing",),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self.store.append_event(
            supervisor["supervisor_id"],
            level="warning",
            stage="blocked",
            message="Implementation blocked by shared repository ownership",
            data={
                "repo_name": supervisor["repo_name"],
                "run_id": run_id,
                "launch_reason": launch_reason,
            },
        )
        self._write_resume_prompt(updated)
        self._notify(
            updated,
            event_stage="blocked",
            event_level="warning",
            kind="blocked_by_lock",
            title="CodexBridge supervisor blocked",
            message="Implementation is blocked by active repository ownership.",
            payload={
                "repo_name": supervisor["repo_name"],
                "reason": "repository_operation_lock_unavailable",
                "run_id": run_id,
            },
            dedupe_key="blocked_by_lock",
        )
        return updated

    def _ensure_child_launched(
        self,
        supervisor: dict[str, Any],
        *,
        expected_kind: str,
    ) -> dict[str, Any]:
        metadata = dict(supervisor["metadata"])
        active_child = dict(metadata.get("active_child") or {})
        run_id = self._active_run_id(metadata, expected_kind=expected_kind)
        if active_child.get("launch_state") == "launched":
            return supervisor

        child_status: dict[str, Any] | None = None
        try:
            child_status = self.jobs.get_status(run_id)
            child_exists = True
        except KeyError:
            child_exists = False

        if not child_exists:
            if expected_kind == "plan":
                plan = metadata["plan"]
                response = self.jobs.start_plan(
                    supervisor["repo_name"],
                    plan["task"],
                    plan.get("constraints", ""),
                    reserved_run_id=run_id,
                )
            elif expected_kind == "implementation":
                approval = metadata["approval"]
                response = self.jobs.start_implementation(
                    supervisor["repo_name"],
                    approval["approved_plan"],
                    list(approval["allowed_files"]),
                    list(approval["tests"]),
                    reserved_run_id=run_id,
                )
            else:
                raise ValueError(f"Unsupported child kind: {expected_kind}")

            if response.get("accepted"):
                accepted_run_id = self._accepted_run_id(response)
                if accepted_run_id != run_id:
                    self.jobs.cancel(accepted_run_id)
                    raise RuntimeError(
                        "Child launcher returned a different reserved run ID"
                    )
            else:
                launch_reason = str(
                    response.get("reason") or "Child run was not accepted"
                )
                try:
                    child_status = self.jobs.get_status(run_id)
                except KeyError as exc:
                    if expected_kind == "implementation" and launch_reason in {
                        "repository busy",
                        "duplicate active task",
                    }:
                        return self._block_implementation_launch(
                            supervisor, metadata, run_id, launch_reason
                        )
                    raise ValueError(launch_reason) from exc
            if child_status is None:
                child_status = self.jobs.get_status(run_id)

        launched_metadata = dict(metadata)
        launched_metadata["active_child"] = {
            "run_id": run_id,
            "kind": expected_kind,
            "launch_state": "launched",
        }
        if expected_kind == "implementation":
            launched_metadata["implementation_lock"] = {
                "authority": "operation_locks",
                "repo_name": supervisor["repo_name"],
                "run_id": run_id,
                "lease_generation": int(
                    (child_status or {}).get("lease_generation") or 1
                ),
            }
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={"metadata_json": launched_metadata},
            expected_statuses=(supervisor["status"],),
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            current = self.store.get_supervisor(supervisor["supervisor_id"])
            current_child = current["metadata"].get("active_child") or {}
            if current_child.get("run_id") != run_id:
                try:
                    self.jobs.cancel(run_id)
                except KeyError:
                    pass
            return current

        event_data = {"run_id": run_id}
        if expected_kind == "implementation":
            ownership = launched_metadata["implementation_lock"]
            event_data["lock_authority"] = ownership["authority"]
            event_data["lease_generation"] = ownership["lease_generation"]
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage="planning" if expected_kind == "plan" else "implementing",
            message=(
                "Plan child run started"
                if expected_kind == "plan"
                else "Implementation child run started"
            ),
            data=event_data,
        )
        return updated

    def _accepted_run_id(self, response: dict[str, Any]) -> str:
        if not response.get("accepted") or not response.get("run_id"):
            raise ValueError(response.get("reason") or "Child run was not accepted")
        return str(response["run_id"])

    def _active_run_id(self, metadata: dict[str, Any], *, expected_kind: str) -> str:
        active_child = metadata.get("active_child") or {}
        if active_child.get("kind") != expected_kind or not active_child.get("run_id"):
            raise ValueError(
                f"Supervisor is missing active {expected_kind} run metadata"
            )
        return str(active_child["run_id"])
