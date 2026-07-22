"""Read-only local orchestration skeleton for Soma."""

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
]


def __getattr__(name: str):
    if name == "LocalAgentOrchestrator" or name == "classify_task":
        from .orchestrator import LocalAgentOrchestrator, classify_task

        return {
            "LocalAgentOrchestrator": LocalAgentOrchestrator,
            "classify_task": classify_task,
        }[name]
    if name == "LocalModelClient":
        from .local_model import LocalModelClient

        return LocalModelClient
    if name == "OllamaChatAdapter":
        from .ollama_adapter import OllamaChatAdapter

        return OllamaChatAdapter
    raise AttributeError(name)
