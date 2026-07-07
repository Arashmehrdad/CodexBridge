from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.policy import PolicyEngine, PolicyEvaluationRequest
from codexbridge.policy.models import CanonicalPermissionTier, PolicyDecisionValue


def engine(tmp_path: Path) -> PolicyEngine:
    return PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")


def evaluate(
    tmp_path: Path, action: str, profile: str = "chatgpt_delegated", tier=None
):
    return engine(tmp_path).evaluate(
        PolicyEvaluationRequest(
            action=action,
            action_type="test",
            autonomy_profile=profile,
            permission_tier=tier,
            repo_name="repo",
        )
    )


def test_readonly_profile_allows_read_only_and_requires_human_for_write(
    tmp_path: Path,
) -> None:
    read = evaluate(tmp_path, "git status", profile="readonly")
    write = evaluate(tmp_path, "edit source file", profile="readonly")

    assert read.decision == PolicyDecisionValue.ALLOWED
    assert write.decision == PolicyDecisionValue.NEEDS_HUMAN_APPROVAL
    assert write.human_required is True


def test_chatgpt_delegated_allows_t0_t1_t2(tmp_path: Path) -> None:
    assert (
        evaluate(tmp_path, "git status").permission_tier
        == CanonicalPermissionTier.T0_READ_ONLY
    )
    assert evaluate(tmp_path, "run pytest").decision == PolicyDecisionValue.ALLOWED
    assert (
        evaluate(tmp_path, "start long-running job profile dummy_success").decision
        == PolicyDecisionValue.ALLOWED
    )


def test_chatgpt_delegated_requires_approval_for_t4_and_t5(tmp_path: Path) -> None:
    write = evaluate(
        tmp_path,
        "fix bug in repo",
        tier=CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
    )
    push = evaluate(
        tmp_path,
        "push private feature branch",
        tier=CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED,
    )

    assert write.decision == PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL
    assert write.approval_request_id
    assert write.chatgpt_delegated_allowed is True
    assert push.decision == PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL
    assert push.approval_request_id


@pytest.mark.parametrize(
    "action",
    [
        "use API key",
        "production deploy",
        "push to main",
        "push to master",
        "create release tag",
        "public repo push",
        "deployment branch push",
        "rm -rf C:\\",
        "grant external access",
        "sudo install system package",
    ],
)
def test_human_only_or_blocked_boundaries(tmp_path: Path, action: str) -> None:
    result = evaluate(tmp_path, action)

    assert result.permission_tier == CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION
    assert result.human_required is True
    assert result.decision in {
        PolicyDecisionValue.NEEDS_HUMAN_APPROVAL,
        PolicyDecisionValue.BLOCKED,
    }


def test_human_only_profile_requires_human_for_writes(tmp_path: Path) -> None:
    result = evaluate(tmp_path, "edit source file", profile="human_only")

    assert result.decision == PolicyDecisionValue.NEEDS_HUMAN_APPROVAL
    assert result.human_required is True


def test_normal_commands_and_jobs_map_to_expected_tiers(tmp_path: Path) -> None:
    assert (
        evaluate(tmp_path, "git status").permission_tier
        == CanonicalPermissionTier.T0_READ_ONLY
    )
    assert (
        evaluate(tmp_path, "python -m pip check").permission_tier
        == CanonicalPermissionTier.T1_SAFE_LOCAL_TEST
    )
    assert (
        evaluate(
            tmp_path, "start allowlisted long-running job profile dummy_success"
        ).permission_tier
        == CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB
    )


def test_unknown_risky_action_not_allowed_by_default(tmp_path: Path) -> None:
    result = engine(tmp_path).evaluate(
        PolicyEvaluationRequest(action="do something unclear", action_type="unknown")
    )

    assert result.permission_tier == CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION
    assert result.decision == PolicyDecisionValue.NEEDS_HUMAN_APPROVAL


def test_policy_audit_metadata_present(tmp_path: Path) -> None:
    result = evaluate(tmp_path, "git status")

    assert result.audit_event_id.startswith("policy_")
    assert result.created_at
    assert result.matched_rules
