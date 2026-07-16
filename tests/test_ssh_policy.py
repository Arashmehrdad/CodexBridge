from __future__ import annotations

import pytest
from pydantic import ValidationError

from codexbridge.policy.models import CanonicalPermissionTier, PolicyDecisionValue
from codexbridge.ssh_policy import (
    AUTONOMY_PROFILES,
    CANONICAL_AUTONOMY_PROFILES,
    CANONICAL_SSH_EXECUTION_MODES,
    SSH_EXECUTION_POLICY_MATRIX,
    SSHActionPolicyRequest,
    SSHPolicyRequest,
    authorize_ssh_action_launch,
    authorize_ssh_launch,
    authorize_ssh_reviewed_script_launch,
    authorize_ssh_root_shell_launch,
    classify_ssh_permission_tier,
    evaluate_ssh_action_policy,
    evaluate_ssh_policy,
)


@pytest.mark.parametrize(
    "mode",
    ["structured", "reviewed_script", "root_shell"],
)
def test_permissive_is_the_only_ssh_policy_profile(mode: str) -> None:
    result = evaluate_ssh_policy(
        SSHPolicyRequest(execution_mode=mode, autonomy_profile="permissive")
    )
    assert result.allowed is True
    assert result.decision == "allowed"


@pytest.mark.parametrize(
    "payload",
    [
        {"execution_mode": "unknown", "autonomy_profile": "permissive"},
        {"execution_mode": "structured", "autonomy_profile": "unknown"},
        {"execution_mode": "structured", "autonomy_profile": "balanced"},
        {"execution_mode": "structured", "autonomy_profile": "conservative"},
        {"execution_mode": "structured", "autonomy_profile": "chatgpt_delegated"},
        {
            "execution_mode": "structured",
            "autonomy_profile": "permissive",
            "extra": True,
        },
    ],
)
def test_policy_request_rejects_removed_values_and_extra_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SSHPolicyRequest.model_validate(payload)


def test_canonical_profile_names_are_permissive_only() -> None:
    assert CANONICAL_AUTONOMY_PROFILES == frozenset({"permissive"})
    assert AUTONOMY_PROFILES == CANONICAL_AUTONOMY_PROFILES
    assert CANONICAL_SSH_EXECUTION_MODES == frozenset(SSH_EXECUTION_POLICY_MATRIX)
    assert all(
        allowed_profiles == CANONICAL_AUTONOMY_PROFILES
        for allowed_profiles in SSH_EXECUTION_POLICY_MATRIX.values()
    )


def test_policy_is_repository_independent() -> None:
    request = SSHPolicyRequest(
        execution_mode="structured", autonomy_profile="permissive"
    )
    assert request.autonomy_profile == "permissive"
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
    ("writes_remote", "monitored", "high_risk", "decision", "tier"),
    [
        (
            False,
            False,
            False,
            PolicyDecisionValue.ALLOWED,
            CanonicalPermissionTier.T0_READ_ONLY,
        ),
        (
            False,
            True,
            False,
            PolicyDecisionValue.ALLOWED,
            CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
        ),
        (
            True,
            False,
            False,
            PolicyDecisionValue.ALLOWED,
            CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        ),
        (
            True,
            False,
            True,
            PolicyDecisionValue.NEEDS_HUMAN_APPROVAL,
            CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
        ),
    ],
)
def test_action_policy_uses_permissive_profile_permissions(
    writes_remote: bool,
    monitored: bool,
    high_risk: bool,
    decision: PolicyDecisionValue,
    tier: CanonicalPermissionTier,
) -> None:
    result = evaluate_ssh_action_policy(
        SSHActionPolicyRequest(
            execution_mode="structured",
            autonomy_profile="permissive",
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
    assert result.chatgpt_delegated_allowed is False


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


def test_permissive_action_launch_needs_no_delegated_approval() -> None:
    result = authorize_ssh_action_launch(
        autonomy_profile="permissive",
        execution_mode="structured",
        writes_remote=True,
    )
    assert result.authorized is True
    assert result.approval_source == "none"
    assert result.decision == PolicyDecisionValue.ALLOWED

    with pytest.raises(ValueError, match="human approval"):
        authorize_ssh_action_launch(
            autonomy_profile="permissive",
            execution_mode="structured",
            writes_remote=True,
            high_risk=True,
            chatgpt_approval_granted=True,
        )


@pytest.mark.parametrize("profile", ["balanced", "conservative", "chatgpt_delegated"])
def test_removed_profiles_fail_before_action_authorization(profile: str) -> None:
    with pytest.raises(ValidationError):
        authorize_ssh_action_launch(
            autonomy_profile=profile,
            execution_mode="structured",
            writes_remote=False,
        )


def test_reviewed_script_authorization_is_permissive_without_approval() -> None:
    result = authorize_ssh_reviewed_script_launch(
        autonomy_profile="permissive",
        execution_mode="reviewed_script",
        writes_remote=False,
        high_risk=True,
    )
    assert result.permission_tier == CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED
    assert result.decision == PolicyDecisionValue.ALLOWED
    assert result.approval_source == "none"
    assert result.human_required is False

    with pytest.raises(ValueError, match="requires execution_mode"):
        authorize_ssh_reviewed_script_launch(
            autonomy_profile="permissive",
            execution_mode="root_shell",
            writes_remote=True,
            high_risk=True,
            model_approval_granted=True,
        )

    with pytest.raises(ValidationError):
        authorize_ssh_reviewed_script_launch(
            autonomy_profile="balanced",
            execution_mode="reviewed_script",
            writes_remote=True,
            high_risk=False,
        )


def test_root_shell_authorization_is_permissive_without_approval_gates() -> None:
    root = authorize_ssh_root_shell_launch(
        autonomy_profile="permissive",
        execution_mode="root_shell",
    )

    assert root.permission_tier == CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED
    assert root.decision == PolicyDecisionValue.ALLOWED
    assert root.authorized is True
    assert root.approval_required is False
    assert root.human_required is False
    assert root.approval_source == "none"

    for profile in ("balanced", "conservative"):
        with pytest.raises(ValueError, match="requires autonomy_profile='permissive'"):
            authorize_ssh_root_shell_launch(
                autonomy_profile=profile,
                execution_mode="root_shell",
            )

    for evidence in (
        {"model_approval_granted": True},
        {"human_approval_granted": True},
    ):
        with pytest.raises(ValueError, match="does not accept approval evidence"):
            authorize_ssh_root_shell_launch(
                autonomy_profile="permissive",
                execution_mode="root_shell",
                **evidence,
            )


def test_launch_authorization_accepts_only_permissive_and_supported_mode() -> None:
    assert authorize_ssh_launch(
        autonomy_profile="permissive", execution_mode="structured"
    ).allowed
    with pytest.raises(ValueError, match="not implemented"):
        authorize_ssh_launch(
            autonomy_profile="permissive", execution_mode="reviewed_script"
        )


@pytest.mark.parametrize(
    ("autonomy_profile", "execution_mode"),
    [
        ("unknown", "structured"),
        ("balanced", "structured"),
        ("conservative", "structured"),
        ("permissive", "unknown"),
        ("chatgpt_delegated", "structured"),
    ],
)
def test_launch_authorization_strictly_validates_policy_fields(
    autonomy_profile: str, execution_mode: str
) -> None:
    with pytest.raises(ValidationError):
        authorize_ssh_launch(
            autonomy_profile=autonomy_profile, execution_mode=execution_mode
        )
