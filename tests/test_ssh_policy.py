from __future__ import annotations

import pytest
from pydantic import ValidationError

from codexbridge.policy.profiles import BUILTIN_AUTONOMY_PROFILES
from codexbridge.ssh_policy import (
    AUTONOMY_PROFILES,
    CANONICAL_AUTONOMY_PROFILES,
    CANONICAL_SSH_EXECUTION_MODES,
    SSH_EXECUTION_POLICY_MATRIX,
    SSHPolicyRequest,
    authorize_ssh_launch,
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
