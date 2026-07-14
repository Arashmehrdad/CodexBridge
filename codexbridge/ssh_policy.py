"""Pure policy contracts for SSH execution modes.

This module only describes and evaluates the profile/mode policy matrix. It
does not resolve repositories, build commands, or execute transport work.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict

from .policy.profiles import BUILTIN_AUTONOMY_PROFILES


SSHExecutionMode = Literal["structured", "reviewed_script", "root_shell"]
AutonomyProfile = Literal[
    "readonly", "chatgpt_delegated", "permissive", "human_only"
]

CANONICAL_SSH_EXECUTION_MODES = frozenset(
    {"structured", "reviewed_script", "root_shell"}
)
CANONICAL_AUTONOMY_PROFILES = frozenset(BUILTIN_AUTONOMY_PROFILES)

SSH_EXECUTION_POLICY_MATRIX: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "structured": CANONICAL_AUTONOMY_PROFILES,
        "reviewed_script": frozenset({"chatgpt_delegated", "permissive"}),
        "root_shell": frozenset({"permissive"}),
    }
)

# Short aliases keep the canonical vocabulary convenient for callers without
# creating another policy definition.
SSH_EXECUTION_MODES = CANONICAL_SSH_EXECUTION_MODES
AUTONOMY_PROFILES = CANONICAL_AUTONOMY_PROFILES
SSH_POLICY_MATRIX = SSH_EXECUTION_POLICY_MATRIX


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


# Explicit descriptive aliases for consumers that prefer the full name.
SSHExecutionPolicyRequest = SSHPolicyRequest
SSHExecutionPolicyResult = SSHPolicyResult
evaluate_ssh_execution_policy = evaluate_ssh_policy
