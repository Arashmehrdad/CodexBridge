from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Protocol

from soma.safety import is_secret_like_file

from .approval_store import ApprovalStore
from .models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStoreRecord,
    AutonomyProfileModel,
    CanonicalPermissionTier,
    PolicyDecisionValue,
    PolicyEvaluationRequest,
    PolicyEvaluationResult,
    PolicyRule,
    RiskClassification,
    RiskLevel,
)
from .policy_engine import PolicyEngine
from .profiles import get_autonomy_profile, list_autonomy_profiles
from .risk_classifier import RiskClassifier


@dataclass(frozen=True)
class PolicyDecision:
    accepted: bool
    tier: int
    risk_level: str
    requires_human: bool
    reason: str = ""
    estimated_duration_minutes: int = 10
    recommended_check_after_minutes: int = 2

    def to_start_response(
        self, run_id: str | None = None, status: str = "queued"
    ) -> dict:
        return {
            "run_id": run_id,
            "accepted": self.accepted,
            "status": status,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "recommended_check_after_minutes": self.recommended_check_after_minutes,
            "risk_level": self.risk_level,
            "requires_human": self.requires_human,
            "reason": self.reason,
        }


class AutonomyProfile(Protocol):
    stop_on_requires_human: bool
    max_plan_tier: int
    max_implementation_tier: int
    require_tests_for_non_docs_changes: bool


@dataclass(frozen=True)
class ProfilePolicyResult:
    decision: PolicyDecision
    allowed: bool
    hard_stop: dict
    profile_snapshot: dict


@dataclass(frozen=True)
class BalancedAutonomyProfile:
    stop_on_requires_human: bool = True
    max_plan_tier: int = 1
    max_implementation_tier: int = 2
    require_tests_for_non_docs_changes: bool = False


def _looks_docs_only(paths: list[str]) -> bool:
    docs_suffixes = {".md", ".rst", ".txt"}
    docs_prefixes = ("docs/", "documentation/")
    if not paths:
        return False
    for path in paths:
        normalized = path.replace("\\", "/").lower()
        suffix = PureWindowsPath(normalized).suffix
        if suffix not in docs_suffixes and not normalized.startswith(docs_prefixes):
            return False
    return True


def profile_snapshot(profile: AutonomyProfile, name: str = "balanced") -> dict:
    return {
        "name": name,
        "stop_on_requires_human": bool(profile.stop_on_requires_human),
        "max_plan_tier": int(profile.max_plan_tier),
        "max_implementation_tier": int(profile.max_implementation_tier),
        "require_tests_for_non_docs_changes": bool(
            profile.require_tests_for_non_docs_changes
        ),
    }


def evaluate_plan_profile(
    decision: PolicyDecision, profile: AutonomyProfile, profile_name: str = "balanced"
) -> ProfilePolicyResult:
    reasons = []
    if not decision.accepted:
        reasons.append("policy_rejected")
    if profile.stop_on_requires_human and decision.requires_human:
        reasons.append("requires_human")
    if decision.tier > profile.max_plan_tier:
        reasons.append("plan_tier_exceeds_profile")
    return _profile_result(decision, profile, profile_name, reasons)


def evaluate_implementation_profile(
    decision: PolicyDecision,
    profile: AutonomyProfile,
    *,
    allowed_files: list[str],
    tests: list[str],
    profile_name: str = "balanced",
) -> ProfilePolicyResult:
    reasons = []
    if not decision.accepted:
        reasons.append("policy_rejected")
    if profile.stop_on_requires_human and decision.requires_human:
        reasons.append("requires_human")
    if decision.tier > profile.max_implementation_tier:
        reasons.append("implementation_tier_exceeds_profile")
    if (
        profile.require_tests_for_non_docs_changes
        and not _looks_docs_only(allowed_files)
        and not tests
    ):
        reasons.append("tests_required_for_non_docs_changes")
    return _profile_result(decision, profile, profile_name, reasons)


def _profile_result(
    decision: PolicyDecision,
    profile: AutonomyProfile,
    profile_name: str,
    reasons: list[str],
) -> ProfilePolicyResult:
    snapshot = profile_snapshot(profile, profile_name)
    hard_stop = {
        "blocked": bool(reasons),
        "reasons": reasons,
        "decision": {
            "accepted": decision.accepted,
            "tier": decision.tier,
            "risk_level": decision.risk_level,
            "requires_human": decision.requires_human,
            "reason": decision.reason,
        },
        "profile": snapshot,
    }
    return ProfilePolicyResult(
        decision=decision,
        allowed=not reasons,
        hard_stop=hard_stop,
        profile_snapshot=snapshot,
    )


def decide_plan_task(task: str, constraints: str | None = None) -> PolicyDecision:
    text = f"{task}\n{constraints or ''}".lower()
    if any(
        word in text
        for word in (
            "credential",
            "login",
            "secret",
            "token",
            "force push",
            "delete volume",
        )
    ):
        return PolicyDecision(
            False, 3, "high", True, "Plan request appears to require human-only action"
        )
    return PolicyDecision(True, 1, "low", False, "Plan-only jobs are auto-approved")


def decide_implementation_task(
    approved_plan: str, allowed_files: list[str], tests: list[str]
) -> PolicyDecision:
    text = f"{approved_plan}\n{' '.join(tests)}".lower()
    if any(
        word in text
        for word in (
            "force push",
            "credential",
            "browser login",
            "secret",
            "delete volume",
        )
    ):
        return PolicyDecision(
            False, 3, "high", True, "Request appears to require human-only action"
        )
    secret_files = [path for path in allowed_files if is_secret_like_file(path)]
    if secret_files:
        return PolicyDecision(
            False, 3, "high", True, f"Secret-like files are not allowed: {secret_files}"
        )
    if _looks_docs_only(allowed_files):
        return PolicyDecision(
            True,
            1,
            "low",
            False,
            "Docs-only allowed-file implementation is auto-approved",
        )
    return PolicyDecision(
        True,
        2,
        "medium",
        False,
        "Normal implementation requires ChatGPT approval before start",
    )


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalStore",
    "ApprovalStoreRecord",
    "AutonomyProfile",
    "AutonomyProfileModel",
    "BalancedAutonomyProfile",
    "CanonicalPermissionTier",
    "PolicyDecision",
    "PolicyDecisionValue",
    "PolicyEngine",
    "PolicyEvaluationRequest",
    "PolicyEvaluationResult",
    "PolicyRule",
    "ProfilePolicyResult",
    "RiskClassification",
    "RiskClassifier",
    "RiskLevel",
    "decide_implementation_task",
    "decide_plan_task",
    "evaluate_implementation_profile",
    "evaluate_plan_profile",
    "get_autonomy_profile",
    "list_autonomy_profiles",
    "profile_snapshot",
]
