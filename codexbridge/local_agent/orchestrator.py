from __future__ import annotations

from pathlib import Path

from codexbridge.jobs.long_run_manager import LongRunJobManager
from codexbridge.jobs.models import JobStatus
from codexbridge.config import AppConfig
from codexbridge.job_manager import JobManager
from codexbridge.codex_router import CodexEscalationRequest, CodexEscalationRouter
from codexbridge.memory.importers import import_runs
from codexbridge.memory.repository import ProjectMemoryRepository
from codexbridge.policy import PolicyEngine, PolicyEvaluationRequest
from codexbridge.supervisor import LocalSupervisorManager, SupervisorTaskRequest
from codexbridge.local_coding import LocalCodingManager, LocalCodingRequest
from codexbridge.dashboard import get_dashboard_summary

from .audit import create_audit_event
from .local_model import LocalModelClient
from .models import (
    CommandRunStatus,
    LocalAgentResult,
    LocalAgentTask,
    LocalAgentTaskInput,
    LocalAgentTaskType,
    LocalModelStatus,
    TaskStatus,
)
from .policies import apply_policy
from .runner import LocalAgentCommandRunner


def classify_task(objective: str) -> LocalAgentTaskType:
    text = objective.lower()

    if _contains_any(
        text,
        (
            "secret",
            "credential",
            "api key",
            "token",
            "password",
            "delete volume",
            "drop database",
            "rm -rf",
            "wipe",
        ),
    ):
        return LocalAgentTaskType.RISKY_ACTION
    if _contains_any(
        text,
        (
            "production deploy",
            "deploy to production",
            "public release",
            "push main",
            "push to main",
            "force push",
        ),
    ):
        return LocalAgentTaskType.RISKY_ACTION
    if _policy_action_for_objective(objective)[0] is not None:
        return LocalAgentTaskType.POLICY
    if _codex_router_action_for_objective(objective)[0] is not None:
        return LocalAgentTaskType.CODEX_ROUTER
    if _supervisor_action_for_objective(objective)[0] is not None:
        return LocalAgentTaskType.SUPERVISOR
    if _local_coding_action_for_objective(objective)[0] is not None:
        return LocalAgentTaskType.LOCAL_CODING
    if _dashboard_action_for_objective(objective)[0] is not None:
        return LocalAgentTaskType.DASHBOARD
    if _contains_any(
        text,
        (
            "fix",
            "bug",
            "edit",
            "refactor",
            "create module",
            "implement",
            "change source",
            "modify code",
        ),
    ):
        return LocalAgentTaskType.SOURCE_EDIT
    if _job_action_for_objective(text)[0] is not None:
        return LocalAgentTaskType.LONG_RUN_JOB
    if _memory_action_for_objective(objective)[0] is not None:
        return LocalAgentTaskType.MEMORY
    if _local_model_task_for_objective(text) is not None:
        return LocalAgentTaskType.LOCAL_MODEL_REASONING
    if _contains_any(text, ("run tests", "pytest", "test suite")):
        return LocalAgentTaskType.RUN_TESTS
    if _contains_any(
        text, ("run checks", "lint", "typecheck", "type check", "mypy", "ruff")
    ):
        return LocalAgentTaskType.RUN_CHECKS
    if _contains_any(
        text, ("list tests", "what tests exist", "show tests", "find tests")
    ):
        return LocalAgentTaskType.LIST_TESTS
    if _contains_any(text, ("list files", "show files", "find files")):
        return LocalAgentTaskType.LIST_FILES
    if _contains_any(
        text,
        (
            "inspect repo",
            "inspect project",
            "repo inspection",
            "project inspection",
            "look at repo",
            "look at project",
        ),
    ):
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
        memory_repository: ProjectMemoryRepository | None = None,
        policy_engine: PolicyEngine | None = None,
        codex_router: CodexEscalationRouter | None = None,
        supervisor_manager: LocalSupervisorManager | None = None,
        local_coding_manager: LocalCodingManager | None = None,
        dashboard_runs_dir: Path | None = None,
        app_config: AppConfig | None = None,
        config_path: Path | None = None,
        durable_job_manager: JobManager | None = None,
    ):
        self.runner = runner or LocalAgentCommandRunner()
        self.local_model = local_model or LocalModelClient()
        self.job_manager = job_manager or LongRunJobManager()
        self.memory_repository = memory_repository
        self.policy_engine = policy_engine
        self.codex_router = codex_router
        self.supervisor_manager = supervisor_manager
        self.local_coding_manager = local_coding_manager
        self.dashboard_runs_dir = dashboard_runs_dir
        self.app_config = app_config
        self.config_path = config_path
        self.durable_job_manager = durable_job_manager

    def handle_task(
        self, task_input: LocalAgentTaskInput | dict | str
    ) -> LocalAgentResult:
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
        memory_result = None
        policy_result = None
        codex_router_result = None
        supervisor_result = None
        local_coding_result = None
        dashboard_result = None
        if command_id is not None and decision.accepted:
            command_result = self.runner.run_project_command(
                command_id=command_id,
                repo_name=task.repo_name,
                repo_path=task.repo_path,
                permission_tier=decision.permission_tier,
            )
        local_model_method = _local_model_task_for_objective(task.objective)
        if (
            local_model_method is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.LOCAL_MODEL_REASONING
        ):
            local_model_result = getattr(self.local_model, local_model_method)(
                task.objective
            )
        job_action, job_value = _job_action_for_objective(task.objective)
        if (
            job_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.LONG_RUN_JOB
        ):
            if job_action == "start":
                job_result = self.job_manager.start_job(
                    profile_id=job_value,
                    repo_name=task.repo_name,
                    repo_path=task.repo_path,
                )
            elif job_action == "status":
                job_result = self.job_manager.get_status(job_value)
            elif job_action == "cancel":
                job_result = self.job_manager.cancel_job(job_value)
            elif job_action == "report":
                job_result = self.job_manager.generate_report(job_value)
        memory_action, memory_value = _memory_action_for_objective(task.objective)
        if (
            memory_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.MEMORY
        ):
            memory_result = self._handle_memory_action(
                memory_action, memory_value, task
            )
        policy_action, policy_value = _policy_action_for_objective(task.objective)
        if (
            policy_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.POLICY
        ):
            policy_result = self._handle_policy_action(
                policy_action, policy_value, task
            )
        codex_action, codex_value = _codex_router_action_for_objective(task.objective)
        if (
            codex_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.CODEX_ROUTER
        ):
            codex_router_result = self._handle_codex_router_action(
                codex_action, codex_value, task
            )
        supervisor_action, supervisor_value = _supervisor_action_for_objective(
            task.objective
        )
        if (
            supervisor_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.SUPERVISOR
        ):
            supervisor_result = self._handle_supervisor_action(
                supervisor_action, supervisor_value, task
            )
        local_coding_action, local_coding_value = _local_coding_action_for_objective(
            task.objective
        )
        if (
            local_coding_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.LOCAL_CODING
        ):
            local_coding_result = self._handle_local_coding_action(
                local_coding_action, local_coding_value, task
            )
        dashboard_action, dashboard_value = _dashboard_action_for_objective(
            task.objective
        )
        if (
            dashboard_action is not None
            and decision.accepted
            and task.task_type == LocalAgentTaskType.DASHBOARD
        ):
            dashboard_result = self._handle_dashboard_action(
                dashboard_action, dashboard_value
            )
        audit_event = create_audit_event(
            task_id=task.task_id,
            action="classified",
            message=decision.reason,
            metadata={
                "task_type": task.task_type.value,
                "routing_decision": decision.routing_decision.value,
                "permission_tier": decision.permission_tier.value,
                "risk_level": decision.risk_level.value,
                "commands_executed": command_result is not None
                and command_result.status
                not in {
                    CommandRunStatus.BLOCKED,
                    CommandRunStatus.PROFILE_MISSING,
                    CommandRunStatus.PERMISSION_DENIED,
                    CommandRunStatus.REPO_MISSING,
                },
                "codex_called": False,
                "command_id": command_id,
                "command_run_id": command_result.run_id if command_result else None,
                "local_model_called": local_model_result is not None
                and local_model_result.status != LocalModelStatus.BLOCKED,
                "local_model_request_id": local_model_result.request_id
                if local_model_result
                else None,
                "job_action": job_action,
                "job_value": job_value,
                "job_manager_called": job_result is not None,
                "memory_action": memory_action,
                "memory_called": memory_result is not None,
                "policy_action": policy_action,
                "policy_called": policy_result is not None,
                "codex_router_action": codex_action,
                "codex_router_called": codex_router_result is not None,
                "supervisor_action": supervisor_action,
                "supervisor_called": supervisor_result is not None,
                "local_coding_action": local_coding_action,
                "local_coding_called": local_coding_result is not None,
                "dashboard_action": dashboard_action,
                "dashboard_called": dashboard_result is not None,
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
        if local_model_result and local_model_result.status in {
            LocalModelStatus.BLOCKED,
            LocalModelStatus.UNAVAILABLE,
            LocalModelStatus.TIMEOUT,
        }:
            status = TaskStatus.BLOCKED
        if job_result is not None:
            job_status = getattr(getattr(job_result, "job", job_result), "status", None)
            if job_status in {
                JobStatus.BLOCKED,
                JobStatus.PROFILE_MISSING,
                JobStatus.PERMISSION_DENIED,
                JobStatus.REPO_MISSING,
            }:
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
            message=local_model_result.content
            if local_model_result and local_model_result.content
            else decision.reason,
            errors=[]
            if decision.accepted and not result_error
            else [result_error or decision.reason],
            audit_event=audit_event,
            audit_metadata=audit_event.metadata,
            command_result=command_result,
            local_model_result=local_model_result,
            job_result=job_result,
            memory_result=memory_result,
            policy_result=policy_result,
            codex_router_result=codex_router_result,
            supervisor_result=supervisor_result,
            local_coding_result=local_coding_result,
            dashboard_result=dashboard_result,
        )

    def _normalize_input(
        self, task_input: LocalAgentTaskInput | dict | str
    ) -> LocalAgentTaskInput:
        if isinstance(task_input, LocalAgentTaskInput):
            return task_input
        if isinstance(task_input, str):
            return LocalAgentTaskInput(objective=task_input)
        return LocalAgentTaskInput(**task_input)

    def _handle_memory_action(self, action: str, value: str, task: LocalAgentTask):
        repository = self.memory_repository or ProjectMemoryRepository()
        if action == "remember_fact":
            return repository.remember_project_fact(
                value, repo_name=task.repo_name, repo_path=task.repo_path
            ).to_dict()
        if action == "remember_decision":
            return repository.remember_decision(
                value, repo_name=task.repo_name, repo_path=task.repo_path
            ).to_dict()
        if action == "remember_validation_recipe":
            return repository.remember_validation_recipe(
                value, repo_name=task.repo_name
            ).to_dict()
        if action == "search":
            return repository.search(value).model_dump(mode="json")
        if action == "latest_job":
            record = repository.latest_job_summary()
            return record.to_dict() if record else None
        if action == "latest_run":
            record = repository.latest_run_summary()
            return record.to_dict() if record else None
        if action == "continue_last":
            record = repository.continue_last_task()
            return record.to_dict() if record else None
        if action == "import_runs":
            return import_runs(
                repository, repository.store.db_path.parent.parent
            ).model_dump(mode="json")
        return None

    def _handle_policy_action(self, action: str, value: str, task: LocalAgentTask):
        engine = self.policy_engine or PolicyEngine()
        if action in {"evaluate", "classify", "explain_blocked"}:
            return engine.evaluate(
                PolicyEvaluationRequest(
                    action=value,
                    action_type="policy_query",
                    repo_name=task.repo_name,
                    repo_path=task.repo_path,
                )
            ).to_dict()
        if action == "list_pending":
            return [
                item.model_dump(mode="json")
                for item in engine.approval_store.list_pending()
            ]
        if action == "show":
            return engine.approval_store.get(value).model_dump(mode="json")
        if action == "approve_chatgpt":
            return engine.approval_store.record_decision(
                value, decided_by="chatgpt", approved=True
            ).model_dump(mode="json")
        if action == "deny":
            return engine.approval_store.record_decision(
                value, decided_by="chatgpt", approved=False
            ).model_dump(mode="json")
        return None

    def _handle_codex_router_action(
        self, action: str, value: str, task: LocalAgentTask
    ):
        router = self.codex_router or CodexEscalationRouter()
        if action in {"prepare", "escalate", "route", "explain"}:
            return router.route_escalation(
                CodexEscalationRequest(
                    objective=value,
                    task_type="codex_escalation",
                    repo_name=task.repo_name,
                    repo_path=task.repo_path,
                    invoke_codex=action == "escalate",
                )
            ).to_dict()
        return None

    def _handle_supervisor_action(self, action: str, value: str, task: LocalAgentTask):
        manager = self.supervisor_manager or LocalSupervisorManager(
            supervisors_dir=Path.cwd() / "runs" / "supervisors",
            app_config=self.app_config,
            config_path=self.config_path,
            job_manager=self.durable_job_manager,
        )
        if action == "start":
            return manager.start_supervised_task(
                SupervisorTaskRequest(
                    objective=value, repo_name=task.repo_name, repo_path=task.repo_path
                )
            ).model_dump(mode="json", exclude_none=True)
        if action == "show":
            return manager.get_status(value).model_dump(mode="json", exclude_none=True)
        if action == "list":
            return [
                run.model_dump(mode="json", exclude_none=True)
                for run in manager.list_runs()
            ]
        if action == "cancel":
            return manager.cancel(value).model_dump(mode="json", exclude_none=True)
        if action == "resume":
            return manager.resume(value).model_dump(mode="json", exclude_none=True)
        if action == "report":
            return manager.generate_report(value).model_dump(
                mode="json", exclude_none=True
            )
        return None

    def _handle_local_coding_action(
        self, action: str, value: str, task: LocalAgentTask
    ):
        manager = self.local_coding_manager or LocalCodingManager(
            app_config=self.app_config,
            config_path=self.config_path,
            job_manager=self.durable_job_manager,
        )
        if action == "prepare":
            repo_path = task.repo_path or Path.cwd()
            return manager.prepare_local_edit(
                LocalCodingRequest(
                    objective=value, repo_name=task.repo_name, repo_path=repo_path
                )
            ).model_dump(mode="json", exclude_none=True)
        if action in {"preview", "show"}:
            return manager.get(value).model_dump(mode="json", exclude_none=True)
        if action == "list":
            return [
                run.model_dump(mode="json", exclude_none=True) for run in manager.list()
            ]
        if action == "apply":
            edit = manager.get(value)
            if hasattr(edit, "approval_request_id"):
                approval_request_id = edit.approval_request_id or ""
            else:
                data = edit.model_dump(mode="json", exclude_none=True)
                approval_request_id = data.get("approval_request_id", "")
            return manager.apply_local_edit(value, approval_request_id).model_dump(
                mode="json", exclude_none=True
            )
        if action == "rollback":
            return manager.rollback_local_edit(value).model_dump(
                mode="json", exclude_none=True
            )
        if action == "cancel":
            return manager.cancel(value).model_dump(mode="json", exclude_none=True)
        return None

    def _handle_dashboard_action(self, action: str, value: str):
        runs_dir = self.dashboard_runs_dir or Path.cwd() / "runs"
        summary = get_dashboard_summary(runs_dir)
        if action == "health":
            return summary.health.model_dump(mode="json")
        if action in {"summary", "list"}:
            return summary.to_dict()
        return None


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _summary_for(task_type: LocalAgentTaskType, reason: str) -> str:
    return f"{task_type.value} classified. {reason}"


def _command_id_for_objective(
    objective: str, task_type: LocalAgentTaskType
) -> str | None:
    text = objective.lower()
    if _contains_any(text, ("git status", "inspect git status")):
        return "git_status"
    if "pip check" in text:
        return "pip_check"
    if task_type == LocalAgentTaskType.RUN_TESTS and _contains_any(
        text, ("run tests", "run pytest", "pytest", "test suite")
    ):
        return "pytest"
    return None


def _local_model_task_for_objective(objective: str) -> str | None:
    text = objective.lower()
    if _contains_any(
        text,
        (
            "summarize this pytest output",
            "summarise this pytest output",
            "summarize this log",
            "summarise this log",
        ),
    ):
        return "summarize_log"
    if _contains_any(text, ("classify this error", "classify error")):
        return "classify_error"
    if _contains_any(text, ("compress this context", "compress context")):
        return "compress_context"
    if _contains_any(
        text,
        ("explain this failure", "explain this test failure", "explain test failure"),
    ):
        return "explain_test_failure"
    if _contains_any(text, ("draft a codex prompt", "draft codex prompt")):
        return "draft_codex_prompt"
    if _contains_any(
        text,
        (
            "decide whether this needs codex",
            "decide if this needs codex",
            "whether codex needed",
        ),
    ):
        return "decide_whether_codex_needed"
    return None


def _job_action_for_objective(objective: str) -> tuple[str | None, str]:
    raw = objective.strip()
    text = raw.lower()
    words = raw.split()
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


def _memory_action_for_objective(objective: str) -> tuple[str | None, str]:
    text = objective.strip()
    lowered = text.lower()
    prefixes = {
        "remember project fact:": "remember_fact",
        "remember decision:": "remember_decision",
        "remember validation recipe:": "remember_validation_recipe",
        "search memory:": "search",
    }
    for prefix, action in prefixes.items():
        if lowered.startswith(prefix):
            return action, text[len(prefix) :].strip()
    if lowered == "show latest job memory":
        return "latest_job", ""
    if lowered == "show latest run memory":
        return "latest_run", ""
    if lowered == "continue last codexbridge task":
        return "continue_last", ""
    if lowered in {"import memory from recent job reports", "import memory from runs"}:
        return "import_runs", ""
    return None, ""


def _policy_action_for_objective(objective: str) -> tuple[str | None, str]:
    text = objective.strip()
    lowered = text.lower()
    prefixes = {
        "evaluate policy:": "evaluate",
        "classify risk:": "classify",
        "explain why action is blocked:": "explain_blocked",
        "show approval request ": "show",
        "approve request ": "approve_chatgpt",
        "deny request ": "deny",
    }
    for prefix, action in prefixes.items():
        if lowered.startswith(prefix):
            value = text[len(prefix) :].strip()
            if action == "approve_chatgpt" and value.lower().endswith(" as chatgpt"):
                value = value[: -len(" as chatgpt")].strip()
            return action, value
    if lowered == "list pending approvals":
        return "list_pending", ""
    return None, ""


def _codex_router_action_for_objective(objective: str) -> tuple[str | None, str]:
    text = objective.strip()
    lowered = text.lower()
    prefixes = {
        "prepare codex packet:": "prepare",
        "escalate to codex:": "escalate",
        "route task for codex:": "route",
        "explain why codex was/was not needed:": "explain",
    }
    for prefix, action in prefixes.items():
        if lowered.startswith(prefix):
            return action, text[len(prefix) :].strip()
    return None, ""


def _supervisor_action_for_objective(objective: str) -> tuple[str | None, str]:
    text = objective.strip()
    lowered = text.lower()
    prefixes = {
        "start supervised task:": "start",
        "supervise task:": "start",
        "show supervisor ": "show",
        "cancel supervisor ": "cancel",
        "resume supervisor ": "resume",
        "generate supervisor report ": "report",
    }
    for prefix, action in prefixes.items():
        if lowered.startswith(prefix):
            return action, text[len(prefix) :].strip()
    if lowered == "list supervisors":
        return "list", ""
    return None, ""


def _local_coding_action_for_objective(objective: str) -> tuple[str | None, str]:
    text = objective.strip()
    lowered = text.lower()
    prefixes = {
        "prepare local edit:": "prepare",
        "preview local edit ": "preview",
        "apply local edit ": "apply",
        "rollback local edit ": "rollback",
        "show local edit ": "show",
        "cancel local edit ": "cancel",
    }
    for prefix, action in prefixes.items():
        if lowered.startswith(prefix):
            return action, text[len(prefix) :].strip()
    if lowered == "list local edits":
        return "list", ""
    return None, ""


def _dashboard_action_for_objective(objective: str) -> tuple[str | None, str]:
    lowered = objective.strip().lower()
    if lowered in {
        "dashboard summary",
        "show dashboard summary",
        "list dashboard items",
    }:
        return "summary" if lowered != "list dashboard items" else "list", ""
    if lowered == "dashboard health":
        return "health", ""
    return None, ""
