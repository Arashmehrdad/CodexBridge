"""Pure policy contracts for SSH execution modes.

This module only describes and evaluates the profile/mode policy matrix. It
does not resolve repositories, build commands, or execute transport work.
"""
from __future__ import annotations

from collections.abc import Collection
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict

from .policy.models import CanonicalPermissionTier, PolicyDecisionValue
from .policy.profiles import BUILTIN_AUTONOMY_PROFILES


SSHExecutionMode = Literal["structured", "reviewed_script", "root_shell"]
AutonomyProfile = Literal["conservative", "balanced", "permissive"]

CANONICAL_SSH_EXECUTION_MODES = frozenset(
    {"structured", "reviewed_script", "root_shell"}
)
CANONICAL_AUTONOMY_PROFILES = frozenset(BUILTIN_AUTONOMY_PROFILES)

SSH_EXECUTION_POLICY_MATRIX: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "structured": CANONICAL_AUTONOMY_PROFILES,
        "reviewed_script": frozenset({"balanced", "permissive"}),
        "root_shell": frozenset({"permissive"}),
    }
)

# Short aliases keep the canonical vocabulary convenient for callers without
# creating another policy definition.
SSH_EXECUTION_MODES = CANONICAL_SSH_EXECUTION_MODES
AUTONOMY_PROFILES = CANONICAL_AUTONOMY_PROFILES
SSH_POLICY_MATRIX = SSH_EXECUTION_POLICY_MATRIX

IMPLEMENTED_SSH_EXECUTION_MODES = frozenset({"structured"})
REVIEWED_SCRIPT_SCAFFOLD_MODES = frozenset({"reviewed_script"})


class SSHPolicyRequest(BaseModel):
    """Strict input to the SSH execution-mode policy evaluator."""

    model_config = ConfigDict(extra="forbid", strict=True)

    execution_mode: SSHExecutionMode
    autonomy_profile: AutonomyProfile


class SSHPolicyResult(BaseModel):
    """Structured policy outcome; no execution is performed by this module."""

    model_config = ConfigDict(extra="forbid", strict=True)

    execution_mode: SSHExecutionMode
    autonomy_profile: AutonomyProfile
    allowed: bool
    decision: Literal["allowed", "denied"]
    reason: str


def evaluate_ssh_policy(request: SSHPolicyRequest) -> SSHPolicyResult:
    """Evaluate one canonical SSH profile/mode combination."""

    allowed_profiles = SSH_EXECUTION_POLICY_MATRIX[request.execution_mode]
    allowed = request.autonomy_profile in allowed_profiles
    return SSHPolicyResult(
        execution_mode=request.execution_mode,
        autonomy_profile=request.autonomy_profile,
        allowed=allowed,
        decision="allowed" if allowed else "denied",
        reason=(
            "execution_mode_allowed"
            if allowed
            else "execution_mode_not_allowed_for_autonomy_profile"
        ),
    )


class SSHActionPolicyRequest(SSHPolicyRequest):
    """Strict repository-independent context for one SSH action decision."""

    writes_remote: bool = False
    monitored: bool = False
    high_risk: bool = False


class SSHActionPolicyResult(BaseModel):
    """Canonical autonomy decision for one SSH mode and action tier."""

    model_config = ConfigDict(extra="forbid", strict=True)

    execution_mode: SSHExecutionMode
    autonomy_profile: AutonomyProfile
    mode_allowed: bool
    permission_tier: CanonicalPermissionTier
    decision: PolicyDecisionValue
    allowed: bool
    blocked: bool
    approval_required: bool
    human_required: bool
    chatgpt_delegated_allowed: bool
    reason: str


class SSHActionAuthorizationResult(SSHActionPolicyResult):
    """Policy decision plus the approval evidence that authorized a launch."""

    authorized: bool
    approval_source: Literal["none", "chatgpt", "human"]


def classify_ssh_permission_tier(
    *,
    writes_remote: bool,
    monitored: bool = False,
    high_risk: bool = False,
) -> CanonicalPermissionTier:
    """Map bounded SSH execution metadata to the canonical permission tiers."""

    if high_risk:
        return CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION
    if writes_remote:
        return CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED
    if monitored:
        return CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB
    return CanonicalPermissionTier.T0_READ_ONLY


def evaluate_ssh_action_policy(
    request: SSHActionPolicyRequest,
) -> SSHActionPolicyResult:
    """Evaluate mode eligibility and canonical profile permissions without side effects."""

    mode_result = evaluate_ssh_policy(request)
    permission_tier = classify_ssh_permission_tier(
        writes_remote=request.writes_remote,
        monitored=request.monitored,
        high_risk=request.high_risk,
    )
    if not mode_result.allowed:
        return SSHActionPolicyResult(
            execution_mode=request.execution_mode,
            autonomy_profile=request.autonomy_profile,
            mode_allowed=False,
            permission_tier=permission_tier,
            decision=PolicyDecisionValue.DENIED,
            allowed=False,
            blocked=True,
            approval_required=False,
            human_required=False,
            chatgpt_delegated_allowed=False,
            reason="execution_mode_not_allowed_for_autonomy_profile",
        )

    profile = BUILTIN_AUTONOMY_PROFILES[request.autonomy_profile]
    if permission_tier in profile.allow_tiers:
        decision = PolicyDecisionValue.ALLOWED
        allowed = True
        approval_required = False
        human_required = False
        chatgpt_allowed = False
        reason = "permission_tier_allowed_by_profile"
    elif permission_tier in profile.chatgpt_approval_tiers:
        decision = PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL
        allowed = False
        approval_required = True
        human_required = False
        chatgpt_allowed = True
        reason = "permission_tier_requires_chatgpt_approval"
    elif (
        permission_tier in profile.human_approval_tiers
        or permission_tier == CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION
    ):
        decision = PolicyDecisionValue.NEEDS_HUMAN_APPROVAL
        allowed = False
        approval_required = True
        human_required = True
        chatgpt_allowed = False
        reason = "permission_tier_requires_human_approval"
    else:
        decision = PolicyDecisionValue.BLOCKED
        allowed = False
        approval_required = False
        human_required = False
        chatgpt_allowed = False
        reason = "permission_tier_not_allowed_by_profile"

    return SSHActionPolicyResult(
        execution_mode=request.execution_mode,
        autonomy_profile=request.autonomy_profile,
        mode_allowed=True,
        permission_tier=permission_tier,
        decision=decision,
        allowed=allowed,
        blocked=decision == PolicyDecisionValue.BLOCKED,
        approval_required=approval_required,
        human_required=human_required,
        chatgpt_delegated_allowed=chatgpt_allowed,
        reason=reason,
    )


def authorize_ssh_action_launch(
    *,
    autonomy_profile: str,
    execution_mode: str,
    writes_remote: bool,
    monitored: bool = False,
    high_risk: bool = False,
    chatgpt_approval_granted: bool = False,
    human_approval_granted: bool = False,
    implemented_modes: Collection[str] = IMPLEMENTED_SSH_EXECUTION_MODES,
) -> SSHActionAuthorizationResult:
    """Authorize one SSH action after validating mode, tier, and approval evidence."""

    request = SSHActionPolicyRequest.model_validate(
        {
            "autonomy_profile": autonomy_profile,
            "execution_mode": execution_mode,
            "writes_remote": writes_remote,
            "monitored": monitored,
            "high_risk": high_risk,
        }
    )
    policy = evaluate_ssh_action_policy(request)
    if not policy.mode_allowed:
        raise ValueError(
            "SSH execution policy denied profile/mode combination: "
            f"{request.autonomy_profile}/{request.execution_mode}"
        )
    if request.execution_mode not in implemented_modes:
        raise ValueError(
            "SSH execution mode is not implemented by this launch path: "
            f"{request.execution_mode}"
        )

    approval_source: Literal["none", "chatgpt", "human"] = "none"
    if policy.decision == PolicyDecisionValue.ALLOWED:
        pass
    elif (
        policy.decision == PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL
        and chatgpt_approval_granted
    ):
        approval_source = "chatgpt"
    elif (
        policy.decision == PolicyDecisionValue.NEEDS_HUMAN_APPROVAL
        and human_approval_granted
    ):
        approval_source = "human"
    elif policy.decision == PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL:
        raise ValueError("SSH action requires ChatGPT delegated approval")
    elif policy.decision == PolicyDecisionValue.NEEDS_HUMAN_APPROVAL:
        raise ValueError("SSH action requires human approval")
    else:
        raise ValueError(
            f"SSH action is blocked by canonical policy: {policy.reason}"
        )

    return SSHActionAuthorizationResult.model_validate(
        {
            **policy.model_dump(mode="python"),
            "authorized": True,
            "approval_source": approval_source,
        }
    )


def authorize_ssh_reviewed_script_launch(
    *,
    autonomy_profile: str,
    execution_mode: str,
    writes_remote: bool,
    high_risk: bool,
    model_approval_granted: bool = False,
    implemented_modes: Collection[str] = REVIEWED_SCRIPT_SCAFFOLD_MODES,
) -> SSHActionAuthorizationResult:
    """Authorize reviewed-script scaffolding through model-driven policy only.

    The caller persists ``high_risk`` as classification metadata. For this
    launch path it escalates to the model-controlled T4 tier rather than the
    generic T6 human-only tier; no human approval evidence is accepted here.
    """

    if execution_mode != "reviewed_script":
        raise ValueError(
            "Reviewed SSH script launch requires execution_mode='reviewed_script'"
        )
    return authorize_ssh_action_launch(
        autonomy_profile=autonomy_profile,
        execution_mode=execution_mode,
        writes_remote=writes_remote or high_risk,
        high_risk=False,
        chatgpt_approval_granted=model_approval_granted,
        human_approval_granted=False,
        implemented_modes=implemented_modes,
    )


def authorize_ssh_launch(
    *,
    autonomy_profile: str,
    execution_mode: str,
    implemented_modes: Collection[str] = IMPLEMENTED_SSH_EXECUTION_MODES,
) -> SSHPolicyResult:
    """Validate and authorize one SSH launch for a caller's mode support."""

    request = SSHPolicyRequest.model_validate(
        {
            "autonomy_profile": autonomy_profile,
            "execution_mode": execution_mode,
        }
    )
    result = evaluate_ssh_policy(request)
    if not result.allowed:
        raise ValueError(
            "SSH execution policy denied profile/mode combination: "
            f"{request.autonomy_profile}/{request.execution_mode}"
        )
    if request.execution_mode not in implemented_modes:
        raise ValueError(
            "SSH execution mode is not implemented by this launch path: "
            f"{request.execution_mode}"
        )
    return result


# Explicit descriptive aliases for consumers that prefer the full name.
SSHExecutionPolicyRequest = SSHPolicyRequest
SSHExecutionPolicyResult = SSHPolicyResult
evaluate_ssh_execution_policy = evaluate_ssh_policy
