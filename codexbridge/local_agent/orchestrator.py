from __future__ import annotations

from codexbridge.jobs.long_run_manager import LongRunJobManager
from codexbridge.jobs.models import JobStatus

from .audit import create_audit_event
from .local_model import LocalModelClient
from .models import CommandRunStatus, LocalAgentResult, LocalAgentTask, LocalAgentTaskInput, LocalAgentTaskType, LocalModelStatus, TaskStatus
from .policies import apply_policy
from .runner import LocalAgentCommandRunner


def classify_task(objective: str) -> LocalAgentTaskType:
    text = objective.lower()

    if _contains_any(text, ("secret", "credential", "api key", "token", "password", "delete volume", "drop database", "rm -rf", "wipe")):
        return LocalAgentTaskType.RISKY_ACTION
    if _contains_any(text, ("production deploy", "deploy to production", "public release", "push main", "push to main", "force push")):
        return LocalAgentTaskType.RISKY_ACTION
    if _contains_any(text, ("fix", "bug", "edit", "refactor", "create module", "implement", "change source", "modify code")):
        return LocalAgentTaskType.SOURCE_EDIT
    if _job_action_for_objective(text)[0] is not None:
        return LocalAgentTaskType.LONG_RUN_JOB
    if _local_model_task_for_objective(text) is not None:
        return LocalAgentTaskType.LOCAL_MODEL_REASONING
    if _contains_any(text, ("run tests", "pytest", "test suite")):
        return LocalAgentTaskType.RUN_TESTS
    if _contains_any(text, ("run checks", "lint", "typecheck", "type check", "mypy", "ruff")):
        return LocalAgentTaskType.RUN_CHECKS
    if _contains_any(text, ("list tests", "what tests exist", "show tests", "find tests")):
        return LocalAgentTaskType.LIST_TESTS
    if _contains_any(text, ("list files", "show files", "find files")):
        return LocalAgentTaskType.LIST_FILES
    if _contains_any(text, ("inspect repo", "inspect project", "repo inspection", "project inspection", "look at repo", "look at project")):
        return LocalAgentTaskType.REPO_INSPECTION
    if _contains_any(text, ("run ", "command", "check ")):
        return LocalAgentTaskType.RISKY_ACTION
    return LocalAgentTaskType.UNKNOWN


class LocalAgentOrchestrator:
    def __init__(
        self,
        runner: LocalAgentCommandRunner | None = None,
        local_model: LocalModelClient | None = None,
        job_manager: LongRunJobManager | None = None,
    ):
        self.runner = runner or LocalAgentCommandRunner()
        self.local_model = local_model or LocalModelClient()
        self.job_manager = job_manager or LongRunJobManager()

    def handle_task(self, task_input: LocalAgentTaskInput | dict | str) -> LocalAgentResult:
        normalized = self._normalize_input(task_input)
        task_type = classify_task(normalized.objective)
        task = LocalAgentTask(
            task_id=normalized.task_id,
            objective=normalized.objective,
            task_type=task_type,
            repo_name=normalized.repo_name,
            repo_path=normalized.repo_path,
            metadata=normalized.metadata,
        )
        decision = apply_policy(task.task_type, task.objective)
        command_id = _command_id_for_objective(task.objective, task.task_type)
        command_result = None
        local_model_result = None
        job_result = None
        if command_id is not None and decision.accepted:
            command_result = self.runner.run_project_command(
                command_id=command_id,
                repo_name=task.repo_name,
                repo_path=task.repo_path,
                permission_tier=decision.permission_tier,
            )
        local_model_method = _local_model_task_for_objective(task.objective)
        if local_model_method is not None and decision.accepted and task.task_type == LocalAgentTaskType.LOCAL_MODEL_REASONING:
            local_model_result = getattr(self.local_model, local_model_method)(task.objective)
        job_action, job_value = _job_action_for_objective(task.objective)
        if job_action is not None and decision.accepted and task.task_type == LocalAgentTaskType.LONG_RUN_JOB:
            if job_action == "start":
                job_result = self.job_manager.start_job(profile_id=job_value, repo_name=task.repo_name, repo_path=task.repo_path)
            elif job_action == "status":
                job_result = self.job_manager.get_status(job_value)
            elif job_action == "cancel":
                job_result = self.job_manager.cancel_job(job_value)
            elif job_action == "report":
                job_result = self.job_manager.generate_report(job_value)
        audit_event = create_audit_event(
            task_id=task.task_id,
            action="classified",
            message=decision.reason,
            metadata={
                "task_type": task.task_type.value,
                "routing_decision": decision.routing_decision.value,
                "permission_tier": decision.permission_tier.value,
                "risk_level": decision.risk_level.value,
                "commands_executed": command_result is not None and command_result.status
                not in {
                    CommandRunStatus.BLOCKED,
                    CommandRunStatus.PROFILE_MISSING,
                    CommandRunStatus.PERMISSION_DENIED,
                    CommandRunStatus.REPO_MISSING,
                },
                "codex_called": False,
                "command_id": command_id,
                "command_run_id": command_result.run_id if command_result else None,
                "local_model_called": local_model_result is not None and local_model_result.status != LocalModelStatus.BLOCKED,
                "local_model_request_id": local_model_result.request_id if local_model_result else None,
                "job_action": job_action,
                "job_value": job_value,
                "job_manager_called": job_result is not None,
            },
        )
        status = decision.status
        if command_result and command_result.status in {
            CommandRunStatus.BLOCKED,
            CommandRunStatus.PROFILE_MISSING,
            CommandRunStatus.PERMISSION_DENIED,
            CommandRunStatus.REPO_MISSING,
        }:
            status = TaskStatus.BLOCKED
        if local_model_result and local_model_result.status in {LocalModelStatus.BLOCKED, LocalModelStatus.UNAVAILABLE, LocalModelStatus.TIMEOUT}:
            status = TaskStatus.BLOCKED
        if job_result is not None:
            job_status = getattr(getattr(job_result, "job", job_result), "status", None)
            if job_status in {JobStatus.BLOCKED, JobStatus.PROFILE_MISSING, JobStatus.PERMISSION_DENIED, JobStatus.REPO_MISSING}:
                status = TaskStatus.BLOCKED
        result_error = ""
        if command_result and command_result.error:
            result_error = command_result.error
        if local_model_result and local_model_result.error:
            result_error = local_model_result.error
        return LocalAgentResult(
            task_id=task.task_id,
            repo_name=task.repo_name,
            repo_path=task.repo_path,
            objective=task.objective,
            task_type=task.task_type,
            routing_decision=decision.routing_decision,
            permission_tier=decision.permission_tier,
            risk_level=decision.risk_level,
            status=status,
            summary=_summary_for(task.task_type, decision.reason),
            message=local_model_result.content if local_model_result and local_model_result.content else decision.reason,
            errors=[] if decision.accepted and not result_error else [result_error or decision.reason],
            audit_event=audit_event,
            audit_metadata=audit_event.metadata,
            command_result=command_result,
            local_model_result=local_model_result,
            job_result=job_result,
        )

    def _normalize_input(self, task_input: LocalAgentTaskInput | dict | str) -> LocalAgentTaskInput:
        if isinstance(task_input, LocalAgentTaskInput):
            return task_input
        if isinstance(task_input, str):
            return LocalAgentTaskInput(objective=task_input)
        return LocalAgentTaskInput(**task_input)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _summary_for(task_type: LocalAgentTaskType, reason: str) -> str:
    return f"{task_type.value} classified. {reason}"


def _command_id_for_objective(objective: str, task_type: LocalAgentTaskType) -> str | None:
    text = objective.lower()
    if _contains_any(text, ("git status", "inspect git status")):
        return "git_status"
    if "pip check" in text:
        return "pip_check"
    if task_type == LocalAgentTaskType.RUN_TESTS and _contains_any(text, ("run tests", "run pytest", "pytest", "test suite")):
        return "pytest"
    return None


def _local_model_task_for_objective(objective: str) -> str | None:
    text = objective.lower()
    if _contains_any(text, ("summarize this pytest output", "summarise this pytest output", "summarize this log", "summarise this log")):
        return "summarize_log"
    if _contains_any(text, ("classify this error", "classify error")):
        return "classify_error"
    if _contains_any(text, ("compress this context", "compress context")):
        return "compress_context"
    if _contains_any(text, ("explain this failure", "explain this test failure", "explain test failure")):
        return "explain_test_failure"
    if _contains_any(text, ("draft a codex prompt", "draft codex prompt")):
        return "draft_codex_prompt"
    if _contains_any(text, ("decide whether this needs codex", "decide if this needs codex", "whether codex needed")):
        return "decide_whether_codex_needed"
    return None


def _job_action_for_objective(objective: str) -> tuple[str | None, str]:
    text = objective.lower().strip()
    words = text.split()
    if text.startswith("start long job profile ") and len(words) >= 5:
        return "start", words[4]
    if text.startswith("run benchmark job profile ") and len(words) >= 5:
        return "start", words[4]
    if text.startswith("check job status ") and len(words) >= 4:
        return "status", words[3]
    if text.startswith("cancel job ") and len(words) >= 3:
        return "cancel", words[2]
    if text.startswith("generate job report ") and len(words) >= 4:
        return "report", words[3]
    return None, ""
