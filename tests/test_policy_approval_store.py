from __future__ import annotations

from pathlib import Path

import pytest

from soma.policy import PolicyEngine, PolicyEvaluationRequest
from soma.policy.models import ApprovalStatus, CanonicalPermissionTier


def test_approval_request_lifecycle_and_reload(tmp_path: Path) -> None:
    approvals_dir = tmp_path / "runs" / "approvals"
    engine = PolicyEngine(approvals_dir=approvals_dir)
    result = engine.evaluate(
        PolicyEvaluationRequest(
            action="fix bug",
            action_type="write",
            permission_tier=CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        )
    )

    assert result.approval_request_id
    reloaded = PolicyEngine(approvals_dir=approvals_dir)
    pending = reloaded.approval_store.list_pending()
    assert [item.approval_request_id for item in pending] == [
        result.approval_request_id
    ]
    decision = reloaded.approval_store.record_decision(
        result.approval_request_id, decided_by="chatgpt", approved=True, notes="ok"
    )
    assert decision.status == ApprovalStatus.APPROVED
    assert (
        reloaded.approval_store.get(result.approval_request_id).decided_by == "chatgpt"
    )


def test_chatgpt_cannot_approve_human_only_request(tmp_path: Path) -> None:
    engine = PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
    result = engine.evaluate(
        PolicyEvaluationRequest(action="production deploy", action_type="deploy")
    )

    assert result.approval_request_id
    with pytest.raises(PermissionError):
        engine.approval_store.record_decision(
            result.approval_request_id, decided_by="chatgpt", approved=True
        )


def test_approval_request_can_be_denied_and_expired(tmp_path: Path) -> None:
    engine = PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
    first = engine.evaluate(
        PolicyEvaluationRequest(
            action="edit file",
            permission_tier=CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        )
    )
    second = engine.evaluate(
        PolicyEvaluationRequest(
            action="dry run write",
            permission_tier=CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN,
        )
    )

    denied = engine.approval_store.record_decision(
        first.approval_request_id, decided_by="chatgpt", approved=False
    )
    assert denied.status == ApprovalStatus.DENIED
    assert engine.approval_store.expire_stale() == 1
    assert (
        engine.approval_store.get(second.approval_request_id).status
        == ApprovalStatus.EXPIRED
    )
