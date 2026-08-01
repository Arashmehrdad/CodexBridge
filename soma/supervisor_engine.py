from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from .config import AppConfig, ExternalCoderConfig
from .external_coder import (
    ExternalCoderHandoffGenerator,
    ExternalCoderHandoffRequest,
    ExternalCoderHandoffStatus,
)
from .job_manager import JobManager
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
    """Read/cancel access to historical child runs.

    The backend has no launch affordance and can only observe or cancel
    durable child runs that already exist.
    """

    def get_status(self, run_id: str) -> dict[str, Any]: ...

    def get_result(self, run_id: str) -> dict[str, Any]: ...

    def cancel(self, run_id: str) -> dict[str, Any]: ...


class JobManagerChildBackend:
    def __init__(self, config: AppConfig, config_path: Path | None):
        self.manager = JobManager(config, config_path)

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

    def seed(self, kind: str, *, run_id: str | None = None) -> FakeChildJob:
        """Register a historical child run for read/cancel tests."""
        self._counter += 1
        legacy_tool = "codex_plan_task" if kind == "plan" else "codex_implement_task"
        resolved = run_id or (
            f"20260428T1200{self._counter:02d}Z_{legacy_tool}_{self._counter:08x}"
        )
        job = FakeChildJob(run_id=resolved, kind=kind)
        self.jobs[resolved] = job
        return job

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


# Backward-compatible test alias from Batch 2.
FakeJobBackend = FakeChildJobBackend


class SupervisorEngine:
    def __init__(
        self,
        store: SupervisorStore,
        jobs: ChildJobBackend,
        autonomy_profile: Any | None = None,
        profile_name: str = "balanced",
        handoff_generator: ExternalCoderHandoffGenerator | None = None,
        repo_path_resolver: Callable[[str], Path | None] | None = None,
    ):
        # The engine gates plan/implementation transitions through its own
        # autonomy-profile policy before any handoff is generated, so the
        # generator's separate approval pass is disabled to avoid
        # double-gating the same decision.
        self.handoff_generator = handoff_generator or ExternalCoderHandoffGenerator(
            handoff_config=ExternalCoderConfig(
                external_coder_require_policy_approval=False
            ),
            handoff_dir=store.runs_dir / "external_coder_handoffs",
        )
        self.repo_path_resolver = repo_path_resolver
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
        if (
            status in TERMINAL_STATES
            or status in {"needs_input", "needs_external_coder"}
        ):
            return supervisor
        if status == "queued":
            return self._generate_plan_handoff(supervisor)
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
        return self._handoff_transition(
            supervisor,
            metadata,
            kind="implementation",
            request=ExternalCoderHandoffRequest(
                handoff_id=f"handoff_{uuid4().hex}",
                objective=approved_plan,
                task_type="supervisor_implementation_handoff",
                repo_name=supervisor["repo_name"],
                repo_path=self._repo_path(supervisor["repo_name"]),
                validation_commands=list(tests),
                allowed_files=list(allowed_files),
                constraints=[
                    "Implement only the approved plan recorded in this handoff.",
                ],
            ),
            expected_statuses=("needs_input",),
        )

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
            title="Soma supervisor cancelled",
            message="Supervisor was cancelled.",
            payload={"run_id": run_id},
            dedupe_key="cancelled",
        )
        return updated

    def _generate_plan_handoff(self, supervisor: dict[str, Any]) -> dict[str, Any]:
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

        constraints = plan.get("constraints", "")
        return self._handoff_transition(
            supervisor,
            metadata,
            kind="plan",
            request=ExternalCoderHandoffRequest(
                handoff_id=f"handoff_{uuid4().hex}",
                objective=plan["task"],
                task_type="supervisor_plan_handoff",
                repo_name=supervisor["repo_name"],
                repo_path=self._repo_path(supervisor["repo_name"]),
                constraints=[constraints] if constraints else [],
            ),
            expected_statuses=("queued",),
        )

    def _handoff_transition(
        self,
        supervisor: dict[str, Any],
        metadata: dict[str, Any],
        *,
        kind: str,
        request: ExternalCoderHandoffRequest,
        expected_statuses: tuple[str, ...],
    ) -> dict[str, Any]:
        """Record an inert handoff artifact without launching anything.

        The supervisor parks in needs_external_coder so a human may archive or
        export the artifact outside Soma. No agent is selected or invoked, and
        unrestricted PowerShell is not an execution fallback.
        """
        route = self.handoff_generator.generate_handoff(request, force_handoff=True)
        handoff_metadata: dict[str, Any] = {
            "kind": kind,
            "handoff_id": route.handoff_id,
            "status": route.status.value,
            "reasons": route.reasons,
        }
        if route.artifacts:
            handoff_metadata["handoff_json_path"] = str(
                route.artifacts.handoff_json_path
            )
            handoff_metadata["prompt_path"] = str(route.artifacts.prompt_path)
        metadata["external_coder_handoff"] = handoff_metadata
        metadata["active_child"] = None
        if route.status == ExternalCoderHandoffStatus.HANDOFF_READY:
            target_status = "needs_external_coder"
            summary = (
                "External-coder handoff is ready; supply it manually to a "
                "coding agent of your choice."
            )
        else:
            target_status = "needs_input"
            summary = (
                "External-coder handoff was not generated: "
                + ("; ".join(route.reasons) or route.status.value)
            )
        updated = self.store.conditional_update_supervisor(
            supervisor["supervisor_id"],
            fields={
                "status": target_status,
                "summary": summary,
                "metadata_json": metadata,
            },
            expected_statuses=expected_statuses,
            expected_state_version=int(supervisor["state_version"]),
        )
        if updated is None:
            return self.store.get_supervisor(supervisor["supervisor_id"])
        self._attach_links_and_write_prompt(updated)
        self.store.append_event(
            supervisor["supervisor_id"],
            level="info",
            stage=target_status,
            message=summary,
            data=handoff_metadata,
        )
        self._notify(
            updated,
            event_stage=target_status,
            event_level="info",
            kind=f"external_coder_handoff_{kind}",
            title="Soma supervisor needs an external coder"
            if target_status == "needs_external_coder"
            else "Soma supervisor needs input",
            message=summary,
            payload=handoff_metadata,
            dedupe_key=f"external_coder_handoff:{kind}:{route.handoff_id}",
        )
        return updated

    def _repo_path(self, repo_name: str) -> Path | None:
        if self.repo_path_resolver is None:
            return None
        try:
            return self.repo_path_resolver(repo_name)
        except Exception:
            return None

    def _advance_plan(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        # Historical read-only path: 'planning' supervisors predate the
        # Codex-execution removal; their children can be observed but a
        # missing child can never be (re)launched.
        metadata = dict(supervisor["metadata"])
        run_id = self._active_run_id(metadata, expected_kind="plan")
        try:
            status = self.jobs.get_status(run_id).get("status")
        except KeyError:
            return self._fail(
                supervisor,
                "Historical plan child run is missing and Codex execution "
                "has been removed; generate an external-coder handoff instead.",
                metadata=metadata,
            )
        if status in ACTIVE_STATES:
            return supervisor
        if status == "failed":
            result = self.jobs.get_result(run_id)
            if result.get("blocked") or result.get("blockers"):
                return self._needs_input_from_blocked_plan(
                    supervisor,
                    metadata,
                    run_id=run_id,
                    result=result,
                )
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

    def _needs_input_from_blocked_plan(
        self,
        supervisor: dict[str, Any],
        metadata: dict[str, Any],
        *,
        run_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        metadata["plan_result"] = result
        metadata["active_child"] = None
        metadata["blocked"] = {
            "reason": "plan_child_blocked",
            "run_id": run_id,
            "blockers": list(result.get("blockers") or []),
            "at": utc_now(),
        }
        summary = (
            result.get("summary")
            or result.get("error")
            or "Plan child requires additional input"
        )
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
            level="warning",
            stage="needs_input",
            message="Plan child blocked; input required",
            data={
                "run_id": run_id,
                "blockers": list(result.get("blockers") or []),
            },
        )
        self._notify(
            updated,
            event_stage="needs_input",
            event_level="warning",
            kind="plan_child_blocked",
            title="Soma supervisor needs input",
            message=summary,
            payload={
                "run_id": run_id,
                "blockers": list(result.get("blockers") or []),
            },
            dedupe_key=f"plan_child_blocked:{run_id}",
        )
        return updated

    def _advance_implementation(self, supervisor: dict[str, Any]) -> dict[str, Any]:
        # Historical read-only path, as in _advance_plan.
        metadata = dict(supervisor["metadata"])
        run_id = self._active_run_id(metadata, expected_kind="implementation")
        try:
            status = self.jobs.get_status(run_id).get("status")
        except KeyError:
            metadata["implementation_lock"] = None
            return self._fail(
                supervisor,
                "Historical implementation child run is missing and Codex "
                "execution has been removed; generate an external-coder "
                "handoff instead.",
                metadata=metadata,
            )
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
            title="Soma supervisor completed",
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
            title="Soma supervisor failed",
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
            title="Soma supervisor needs input",
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
            title="Soma supervisor cancelled",
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

    def _active_run_id(self, metadata: dict[str, Any], *, expected_kind: str) -> str:
        active_child = metadata.get("active_child") or {}
        if active_child.get("kind") != expected_kind or not active_child.get("run_id"):
            raise ValueError(
                f"Supervisor is missing active {expected_kind} run metadata"
            )
        return str(active_child["run_id"])
