from __future__ import annotations

from pydantic import BaseModel

from .models import (
    LocalAgentTaskType,
    PermissionTier,
    RiskLevel,
    RoutingDecision,
    TaskStatus,
)


class PolicyDecision(BaseModel):
    routing_decision: RoutingDecision
    permission_tier: PermissionTier
    risk_level: RiskLevel
    status: TaskStatus
    accepted: bool
    requires_human: bool = False
    reason: str = ""


def apply_policy(task_type: LocalAgentTaskType, objective: str) -> PolicyDecision:
    text = objective.lower()

    if task_type in {
        LocalAgentTaskType.REPO_INSPECTION,
        LocalAgentTaskType.LIST_TESTS,
        LocalAgentTaskType.LIST_FILES,
        LocalAgentTaskType.LOCAL_MODEL_REASONING,
        LocalAgentTaskType.LONG_RUN_JOB,
        LocalAgentTaskType.MEMORY,
        LocalAgentTaskType.POLICY,
        LocalAgentTaskType.CODEX_ROUTER,
        LocalAgentTaskType.SUPERVISOR,
        LocalAgentTaskType.LOCAL_CODING,
        LocalAgentTaskType.DASHBOARD,
        LocalAgentTaskType.UNKNOWN,
    }:
        return PolicyDecision(
            routing_decision=RoutingDecision.LOCAL_ONLY,
            permission_tier=PermissionTier.READ_ONLY,
            risk_level=RiskLevel.LOW,
            status=TaskStatus.CLASSIFIED,
            accepted=True,
            reason="Read-only local classification; no command execution is implemented.",
        )

    if task_type in {LocalAgentTaskType.RUN_TESTS, LocalAgentTaskType.RUN_CHECKS}:
        return PolicyDecision(
            routing_decision=RoutingDecision.LOCAL_ONLY,
            permission_tier=PermissionTier.SAFE_LOCAL_TEST,
            risk_level=RiskLevel.LOW,
            status=TaskStatus.CLASSIFIED,
            accepted=True,
            reason="Safe local test/check task is eligible for allowlisted local command routing.",
        )

    if task_type == LocalAgentTaskType.SOURCE_EDIT:
        return PolicyDecision(
            routing_decision=RoutingDecision.LOCAL_ONLY,
            permission_tier=PermissionTier.WRITE_APPLY_DELEGATED_APPROVAL,
            risk_level=RiskLevel.MEDIUM,
            status=TaskStatus.CLASSIFIED,
            accepted=True,
            reason="Source-changing work is handled locally first; Codex is used only after local options are insufficient.",
        )

    if _looks_blocked(text):
        return PolicyDecision(
            routing_decision=RoutingDecision.BLOCKED,
            permission_tier=PermissionTier.HUMAN_ONLY_RISKY_ACTION,
            risk_level=RiskLevel.HIGH,
            status=TaskStatus.BLOCKED,
            accepted=False,
            requires_human=True,
            reason="Request includes destructive or secret-handling language.",
        )

    return PolicyDecision(
        routing_decision=RoutingDecision.NEEDS_HUMAN_APPROVAL,
        permission_tier=PermissionTier.HUMAN_ONLY_RISKY_ACTION,
        risk_level=RiskLevel.HIGH,
        status=TaskStatus.NEEDS_HUMAN_APPROVAL,
        accepted=False,
        requires_human=True,
        reason="Request requires human approval before any local-agent handling.",
    )


def _looks_blocked(text: str) -> bool:
    blocked_phrases = (
        "delete volume",
        "drop database",
        "wipe",
        "rm -rf",
        "remove-item -recurse -force",
        "secret",
        "credential",
        "api key",
        "token",
        "password",
    )
    return any(phrase in text for phrase in blocked_phrases)
