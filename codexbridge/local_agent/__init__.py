"""Read-only local orchestration skeleton for CodexBridge."""

from .models import (
    AuditEvent,
    CommandRunResult,
    CommandRunStatus,
    LocalAgentResult,
    LocalAgentTask,
    LocalAgentTaskInput,
    LocalAgentTaskType,
    LocalModelRequest,
    LocalModelResult,
    LocalModelStatus,
    PermissionTier,
    RiskLevel,
    RoutingDecision,
    TaskStatus,
)
from .policies import PolicyDecision, apply_policy

__all__ = [
    "AuditEvent",
    "CommandRunResult",
    "CommandRunStatus",
    "LocalAgentCommandRunner",
    "LocalAgentOrchestrator",
    "LocalAgentResult",
    "LocalAgentTask",
    "LocalAgentTaskInput",
    "LocalAgentTaskType",
    "LocalModelClient",
    "LocalModelRequest",
    "LocalModelResult",
    "LocalModelStatus",
    "OllamaChatAdapter",
    "PermissionTier",
    "PolicyDecision",
    "RiskLevel",
    "RoutingDecision",
    "TaskStatus",
    "apply_policy",
    "classify_task",
    "run_project_command",
]


def __getattr__(name: str):
    if name == "LocalAgentOrchestrator" or name == "classify_task":
        from .orchestrator import LocalAgentOrchestrator, classify_task

        return {"LocalAgentOrchestrator": LocalAgentOrchestrator, "classify_task": classify_task}[name]
    if name == "LocalAgentCommandRunner" or name == "run_project_command":
        from .runner import LocalAgentCommandRunner, run_project_command

        return {"LocalAgentCommandRunner": LocalAgentCommandRunner, "run_project_command": run_project_command}[name]
    if name == "LocalModelClient":
        from .local_model import LocalModelClient

        return LocalModelClient
    if name == "OllamaChatAdapter":
        from .ollama_adapter import OllamaChatAdapter

        return OllamaChatAdapter
    raise AttributeError(name)
