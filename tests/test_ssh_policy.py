from __future__ import annotations

import pytest
from pydantic import ValidationError

from codexbridge.policy.models import CanonicalPermissionTier, PolicyDecisionValue
from codexbridge.policy.profiles import BUILTIN_AUTONOMY_PROFILES
from codexbridge.ssh_policy import (
    AUTONOMY_PROFILES,
    CANONICAL_AUTONOMY_PROFILES,
    CANONICAL_SSH_EXECUTION_MODES,
    SSH_EXECUTION_POLICY_MATRIX,
    SSHActionPolicyRequest,
    SSHPolicyRequest,
    authorize_ssh_launch,
    classify_ssh_permission_tier,
    evaluate_ssh_action_policy,
    evaluate_ssh_policy,
)


@pytest.mark.parametrize(
    ("mode", "profile", "allowed"),
    [
        ("structured", profile, True)
        for profile in ("readonly", "chatgpt_delegated", "permissive", "human_only")
    ]
    + [
        ("reviewed_script", "readonly", False),
        ("reviewed_script", "chatgpt_delegated", True),
        ("reviewed_script", "permissive", True),
        ("reviewed_script", "human_only", False),
        ("root_shell", "readonly", False),
        ("root_shell", "chatgpt_delegated", False),
        ("root_shell", "permissive", True),
        ("root_shell", "human_only", False),
    ],
)
def test_full_ssh_policy_matrix(mode: str, profile: str, allowed: bool) -> None:
    result = evaluate_ssh_policy(
        SSHPolicyRequest(execution_mode=mode, autonomy_profile=profile)
    )
    assert result.allowed is allowed
    assert result.decision == ("allowed" if allowed else "denied")


@pytest.mark.parametrize(
    "payload",
    [
        {"execution_mode": "unknown", "autonomy_profile": "readonly"},
        {"execution_mode": "structured", "autonomy_profile": "unknown"},
        {
            "execution_mode": "structured",
            "autonomy_profile": "readonly",
            "extra": True,
        },
    ],
)
def test_policy_request_rejects_unknown_values_and_extra_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SSHPolicyRequest.model_validate(payload)


def test_canonical_profile_names_stay_synchronized() -> None:
    assert CANONICAL_AUTONOMY_PROFILES == frozenset(BUILTIN_AUTONOMY_PROFILES)
    assert AUTONOMY_PROFILES == CANONICAL_AUTONOMY_PROFILES
    assert CANONICAL_SSH_EXECUTION_MODES == frozenset(SSH_EXECUTION_POLICY_MATRIX)


def test_policy_is_repository_independent() -> None:
    request = SSHPolicyRequest(
        execution_mode="structured", autonomy_profile="readonly"
    )
    assert set(SSHPolicyRequest.model_fields) == {
        "execution_mode",
        "autonomy_profile",
    }
    assert "repo_name" not in SSHPolicyRequest.model_fields


@pytest.mark.parametrize(
    ("writes_remote", "monitored", "high_risk", "expected"),
    [
        (False, False, False, CanonicalPermissionTier.T0_READ_ONLY),
        (
            False,
            True,
            False,
            CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
        ),
        (
            True,
            False,
            False,
            CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        ),
        (
            True,
            True,
            True,
            CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
        ),
    ],
)
def test_structured_ssh_metadata_maps_to_canonical_tiers(
    writes_remote: bool,
    monitored: bool,
    high_risk: bool,
    expected: CanonicalPermissionTier,
) -> None:
    assert (
        classify_ssh_permission_tier(
            writes_remote=writes_remote,
            monitored=monitored,
            high_risk=high_risk,
        )
        == expected
    )


@pytest.mark.parametrize(
    (
        "autonomy_profile",
        "writes_remote",
        "monitored",
        "high_risk",
        "decision",
        "tier",
    ),
    [
        (
            "readonly",
            False,
            False,
            False,
            PolicyDecisionValue.ALLOWED,
            CanonicalPermissionTier.T0_READ_ONLY,
        ),
        (
            "readonly",
            False,
            True,
            False,
            PolicyDecisionValue.NEEDS_HUMAN_APPROVAL,
            CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
        ),
        (
            "chatgpt_delegated",
            False,
            True,
            False,
            PolicyDecisionValue.ALLOWED,
            CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
        ),
        (
            "chatgpt_delegated",
            True,
            False,
            False,
            PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL,
            CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        ),
        (
            "permissive",
            True,
            False,
            False,
            PolicyDecisionValue.ALLOWED,
            CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        ),
        (
            "human_only",
            True,
            False,
            False,
            PolicyDecisionValue.NEEDS_HUMAN_APPROVAL,
            CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        ),
        (
            "permissive",
            True,
            False,
            True,
            PolicyDecisionValue.NEEDS_HUMAN_APPROVAL,
            CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
        ),
    ],
)
def test_action_policy_uses_canonical_profile_permissions(
    autonomy_profile: str,
    writes_remote: bool,
    monitored: bool,
    high_risk: bool,
    decision: PolicyDecisionValue,
    tier: CanonicalPermissionTier,
) -> None:
    result = evaluate_ssh_action_policy(
        SSHActionPolicyRequest(
            execution_mode="structured",
            autonomy_profile=autonomy_profile,
            writes_remote=writes_remote,
            monitored=monitored,
            high_risk=high_risk,
        )
    )
    assert result.permission_tier == tier
    assert result.decision == decision
    assert result.allowed is (decision == PolicyDecisionValue.ALLOWED)
    assert result.human_required is (
        decision == PolicyDecisionValue.NEEDS_HUMAN_APPROVAL
    )
    assert result.chatgpt_delegated_allowed is (
        decision == PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL
    )


def test_action_policy_denies_disallowed_mode_before_tier_permission() -> None:
    result = evaluate_ssh_action_policy(
        SSHActionPolicyRequest(
            execution_mode="root_shell",
            autonomy_profile="chatgpt_delegated",
            writes_remote=False,
        )
    )
    assert result.mode_allowed is False
    assert result.decision == PolicyDecisionValue.DENIED
    assert result.blocked is True


def test_action_policy_contract_is_strict_and_repository_independent() -> None:
    assert "repo_name" not in SSHActionPolicyRequest.model_fields
    with pytest.raises(ValidationError):
        SSHActionPolicyRequest.model_validate(
            {
                "execution_mode": "structured",
                "autonomy_profile": "permissive",
                "writes_remote": False,
                "repo_name": "repo",
            }
        )


def test_launch_authorization_rejects_denied_and_unimplemented_modes() -> None:
    assert authorize_ssh_launch(
        autonomy_profile="chatgpt_delegated", execution_mode="structured"
    ).allowed
    with pytest.raises(ValueError, match="denied"):
        authorize_ssh_launch(
            autonomy_profile="readonly", execution_mode="reviewed_script"
        )
    with pytest.raises(ValueError, match="not implemented"):
        authorize_ssh_launch(
            autonomy_profile="chatgpt_delegated", execution_mode="reviewed_script"
        )


@pytest.mark.parametrize(
    ("autonomy_profile", "execution_mode"),
    [("unknown", "structured"), ("chatgpt_delegated", "unknown")],
)
def test_launch_authorization_strictly_validates_policy_fields(
    autonomy_profile: str, execution_mode: str
) -> None:
    with pytest.raises(ValidationError):
        authorize_ssh_launch(
            autonomy_profile=autonomy_profile, execution_mode=execution_mode
        )
