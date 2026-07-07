from __future__ import annotations

from pathlib import Path

from codexbridge.local_agent import LocalAgentOrchestrator
from codexbridge.local_agent.models import LocalAgentTaskType, RoutingDecision
from codexbridge.policy import PolicyEngine
from codexbridge.policy.models import (
    CanonicalPermissionTier,
    PolicyEvaluationRequest,
)


def test_local_agent_routes_policy_evaluation_and_pending_approvals(
    tmp_path: Path,
) -> None:
    policy_engine = PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
    orchestrator = LocalAgentOrchestrator(policy_engine=policy_engine)

    evaluation = orchestrator.handle_task("evaluate policy: edit source file")
    pending = orchestrator.handle_task("list pending approvals")

    assert evaluation.task_type == LocalAgentTaskType.POLICY
    assert evaluation.routing_decision == RoutingDecision.LOCAL_ONLY
    assert evaluation.policy_result["decision"] == "needs_chatgpt_approval"
    assert (
        pending.policy_result[0]["approval_request_id"]
        == evaluation.policy_result["approval_request_id"]
    )
    assert evaluation.command_result is None
    assert evaluation.job_result is None


def test_local_agent_can_show_approve_and_deny_without_execution(
    tmp_path: Path,
) -> None:
    policy_engine = PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
    result = policy_engine.evaluate(
        PolicyEvaluationRequest(
            action="edit source",
            permission_tier=CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
        )
    )
    orchestrator = LocalAgentOrchestrator(policy_engine=policy_engine)

    shown = orchestrator.handle_task(
        f"show approval request {result.approval_request_id}"
    )
    approved = orchestrator.handle_task(
        f"approve request {result.approval_request_id} as chatgpt"
    )

    assert shown.policy_result["approval_request_id"] == result.approval_request_id
    assert approved.policy_result["status"] == "approved"
    assert approved.command_result is None
    assert approved.audit_event.metadata["codex_called"] is False


def test_local_agent_does_not_route_edit_tasks_through_policy_execution(
    tmp_path: Path,
) -> None:
    result = LocalAgentOrchestrator(
        policy_engine=PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals")
    ).handle_task("fix and refactor policy engine")

    assert result.routing_decision == RoutingDecision.CODEX_REQUIRED
    assert result.policy_result is None


def test_policy_modules_do_not_call_forbidden_systems() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("codexbridge/policy").glob("*.py")
    )

    assert "subprocess" not in source
    assert "CodexRunner" not in source
    assert "PulseSender" not in source
    assert "playwright" not in source.lower()
    assert "selenium" not in source.lower()
