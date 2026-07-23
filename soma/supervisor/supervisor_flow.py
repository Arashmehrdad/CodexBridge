from __future__ import annotations
from pathlib import Path
from uuid import uuid4

from soma.config import AppConfig, LocalSupervisorConfig
from soma.external_coder import (
    ExternalCoderHandoffGenerator,
    ExternalCoderHandoffRequest,
    ExternalCoderHandoffStatus,
)
from soma.job_manager import JobManager
from soma.local_agent.durable_command_runner import (
    DurableProjectCommandRunner,
    ProjectCommandRunner,
)
from soma.run_store import utc_now

from .models import (
    SupervisorPlan,
    SupervisorResult,
    SupervisorRun,
    SupervisorStatus,
    SupervisorTaskRequest,
)
from .supervisor_reporter import generate_supervisor_report
from .supervisor_store import LocalSupervisorStore


class SupervisorFlow:
    def __init__(
        self,
        *,
        store: LocalSupervisorStore,
        config: LocalSupervisorConfig | None = None,
        command_runner: ProjectCommandRunner | None = None,
        app_config: AppConfig | None = None,
        config_path: Path | None = None,
        job_manager: JobManager | None = None,
        handoff_generator: ExternalCoderHandoffGenerator | None = None,
        memory_repository=None,
        local_model=None,
    ):
        self.store = store
        self.config = config or LocalSupervisorConfig()
        self.command_runner = command_runner
        if self.command_runner is None and app_config is not None:
            self.command_runner = DurableProjectCommandRunner(
                config=app_config,
                config_path=config_path,
                job_manager=job_manager,
            )
        if self.command_runner is None:
            raise ValueError(
                "SupervisorFlow requires durable application context or an "
                "explicitly injected compatibility runner."
            )
        self.handoff_generator = handoff_generator or ExternalCoderHandoffGenerator(
            config=app_config,
            handoff_dir=store.supervisors_dir.parent / "external_coder_handoffs",
        )
        self.memory_repository = memory_repository
        self.local_model = local_model

    def start_supervised_task(self, request: SupervisorTaskRequest) -> SupervisorResult:
        now = utc_now()
        run_dir = self.store.run_dir(request.supervisor_id)
        run = SupervisorRun(
            supervisor_id=request.supervisor_id,
            objective=_redact_sensitive_text(request.objective),
            repo_name=request.repo_name,
            repo_path=request.repo_path,
            status=SupervisorStatus.CREATED,
            created_at=now,
            started_at=now,
            validation_commands=request.validation_commands
            or self.config.supervisor_default_validation_commands,
            audit_event_id=f"supervisor_{uuid4().hex}",
            artifact_paths=[run_dir / "result.json"],
        )
        self.store.create(run)
        run = self._inspect(run)
        plan = self._plan(run)
        run.local_plan_summary = plan.model_dump_json()
        self._write_json(run, "local_plan.json", plan.model_dump(mode="json"))
        self.store.append_event(
            run.supervisor_id, stage="local_plan_created", message="Local plan created"
        )
        if _human_only_risk(request.objective):
            run.status = SupervisorStatus.BLOCKED
            run.ended_at = utc_now()
            run.failure_summary = "Supervisor blocked a human-only or sensitive action."
            run.next_recommended_action = (
                "Request explicit human review before continuing."
            )
            run.question_for_chatgpt = (
                "This action crosses a human-only safety boundary."
            )
            self.store.write(run)
            self.store.append_event(
                run.supervisor_id,
                stage="blocked",
                message="Supervisor blocked a sensitive or human-only action",
            )
            return self._report(run)
        run = self._validate(run)
        if not plan.external_coder_required and _validation_success(
            run.validation_results
        ):
            run.status = SupervisorStatus.COMPLETED
            run.ended_at = utc_now()
            run.next_recommended_action = "Review supervisor report."
            run.question_for_chatgpt = ""
            self.store.write(run)
            return self._report(run)
        if not plan.external_coder_required:
            run.status = SupervisorStatus.NEEDS_INPUT
            run.ended_at = utc_now()
            run.failure_summary = (
                "Local validation did not pass and no code edit was requested."
            )
            run.next_recommended_action = (
                "Decide whether Soma should generate an external-coder handoff."
            )
            run.question_for_chatgpt = (
                "Should Soma prepare an external-coder handoff for manual use?"
            )
            self.store.write(run)
            return self._report(run)
        route = self.handoff_generator.generate_handoff(
            ExternalCoderHandoffRequest(
                objective=request.objective,
                task_type="supervisor_external_coder_handoff",
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                current_error=_validation_summary(run.validation_results),
                tests_already_run=[
                    item.get("command_id", "") for item in run.validation_results
                ],
                validation_commands=run.validation_commands,
            )
        )
        run.external_coder_handoff_id = route.handoff_id
        if route.artifacts:
            run.external_coder_handoff_path = route.artifacts.handoff_json_path
            run.external_coder_prompt_path = route.artifacts.prompt_path
            self._write_json(
                run,
                "external_coder_handoff_ref.json",
                route.artifacts.model_dump(mode="json"),
            )
        if route.status in {
            ExternalCoderHandoffStatus.BLOCKED,
            ExternalCoderHandoffStatus.HUMAN_REQUIRED,
        }:
            run.status = SupervisorStatus.BLOCKED
            run.failure_summary = "; ".join(route.reasons)
            run.next_recommended_action = "Resolve policy blocker before continuing."
        elif route.status == ExternalCoderHandoffStatus.APPROVAL_REQUIRED:
            run.status = SupervisorStatus.APPROVAL_REQUIRED
            run.next_recommended_action = (
                "Approve or deny the external-coder handoff request."
            )
            run.question_for_chatgpt = (
                "Should this external-coder handoff be approved?"
            )
        elif route.status == ExternalCoderHandoffStatus.HANDOFF_READY:
            run.status = SupervisorStatus.NEEDS_EXTERNAL_CODER
            run.next_recommended_action = (
                "Supply the generated handoff manually to an external coding "
                "agent (Claude Code, Codex, Gemini CLI, or another tool)."
            )
            run.question_for_chatgpt = (
                "An external-coder handoff is ready; Soma does not execute "
                "coding agents. Which agent should receive it manually?"
            )
        else:
            run.status = SupervisorStatus.NEEDS_INPUT
            run.next_recommended_action = "Review supervisor state."
        run.ended_at = utc_now()
        self.store.write(run)
        return self._report(run)

    def _inspect(self, run: SupervisorRun) -> SupervisorRun:
        run.status = SupervisorStatus.INSPECTING
        summary = f"repo_name={run.repo_name or ''}; repo_path={run.repo_path or ''}; validation_commands={run.validation_commands}"
        memory_ids = []
        if (
            self.config.supervisor_use_memory_context
            and self.memory_repository is not None
        ):
            try:
                memory = self.memory_repository.search(run.objective, limit=5)
                memory_ids = [record.memory_id for record in memory.records]
            except Exception:
                memory_ids = []
        run.local_inspection_summary = summary
        run.memory_context_ids = memory_ids
        self._write_json(
            run,
            "local_inspection.json",
            {"summary": summary, "memory_context_ids": memory_ids},
        )
        self.store.write(run)
        self.store.append_event(
            run.supervisor_id,
            stage="local_inspection_completed",
            message="Local inspection completed",
        )
        return run

    def _plan(self, run: SupervisorRun) -> SupervisorPlan:
        text = run.objective.lower()
        external_coder_required = any(
            marker in text
            for marker in ("edit", "fix", "refactor", "create module", "failing test")
        )
        summary = ""
        if self.config.supervisor_use_local_model_plan and self.local_model is not None:
            try:
                summary = getattr(
                    self.local_model.compress_context(run.objective), "content", ""
                )
            except Exception:
                summary = ""
        return SupervisorPlan(
            objective=run.objective,
            likely_task_type="external_coder_required"
            if external_coder_required
            else "local_only",
            external_coder_required=external_coder_required,
            validation_steps=run.validation_commands,
            policy_considerations=[
                "Generate an external-coder handoff for manual use; "
                "Soma never invokes a coding agent."
            ]
            if external_coder_required
            else [],
            risks=[],
            recommended_next_action=summary
            or (
                "Prepare external-coder handoff"
                if external_coder_required
                else "Complete locally if validation passes"
            ),
        )

    def _validate(self, run: SupervisorRun) -> SupervisorRun:
        run.status = SupervisorStatus.VALIDATING_LOCALLY
        results = []
        for command_id in run.validation_commands:
            if command_id not in {"git_status", "pytest", "pip_check"}:
                results.append(
                    {
                        "command_id": command_id,
                        "status": "blocked",
                        "error": "unknown_validation_command",
                    }
                )
                continue
            result = self.command_runner.run_project_command(
                command_id=command_id, repo_name=run.repo_name, repo_path=run.repo_path
            )
            results.append(result.to_dict())
        run.validation_results = results
        self._write_json(run, "validation_results.json", {"results": results})
        self.store.write(run)
        self.store.append_event(
            run.supervisor_id,
            stage="validation_completed",
            message="Validation completed",
        )
        return run

    def _report(self, run: SupervisorRun) -> SupervisorResult:
        report = generate_supervisor_report(run)
        run.artifact_paths = sorted(
            set(
                [
                    *run.artifact_paths,
                    report.report_path,
                    report.resume_prompt_path,
                    report.pulse_manifest_path,
                ]
            )
        )
        self.store.write(run)
        self.store.append_event(
            run.supervisor_id,
            stage="report_generated",
            message="Supervisor report generated",
        )
        return SupervisorResult(
            run=run,
            report_path=report.report_path,
            resume_prompt_path=report.resume_prompt_path,
            pulse_manifest_path=report.pulse_manifest_path,
        )

    def _write_json(self, run: SupervisorRun, name: str, data: dict) -> None:
        from soma.return_loop.atomic_writer import atomic_write_json

        path = self.store.run_dir(run.supervisor_id) / name
        atomic_write_json(path, data)
        if path not in run.artifact_paths:
            run.artifact_paths.append(path)


def _validation_success(results: list[dict]) -> bool:
    if not results:
        return True
    return all(
        item.get("status") in {"success", "completed"} or item.get("exit_code") == 0
        for item in results
    )


def _validation_summary(results: list[dict]) -> str:
    return "; ".join(
        f"{item.get('command_id')}={item.get('status')}" for item in results
    )


def _human_only_risk(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "secret",
        "credential",
        "api key",
        "token",
        "password",
        "private key",
        "authorization header",
        "bearer",
        "production deploy",
        "public release",
        "push main",
        "push to main",
        "push master",
        "push to master",
        "rm -rf",
        "external permission",
    )
    return any(marker in lowered for marker in markers)


def _redact_sensitive_text(text: str) -> str:
    return "[REDACTED_SENSITIVE_OBJECTIVE]" if _human_only_risk(text) else text
