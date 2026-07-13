from __future__ import annotations

from codexbridge.codex_router import CodexEscalationRouter
from codexbridge.local_agent import LocalAgentOrchestrator
from codexbridge.local_agent.models import LocalAgentTaskType, RoutingDecision
from codexbridge.policy import PolicyEngine


def test_local_agent_routes_explicit_codex_packet_request(tmp_path):
    router = CodexEscalationRouter(
        policy_engine=PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals"),
        packet_dir=tmp_path / "runs" / "codex_escalations",
    )
    result = LocalAgentOrchestrator(codex_router=router).handle_task(
        "prepare Codex packet: edit source file"
    )

    assert result.task_type == LocalAgentTaskType.CODEX_ROUTER
    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.codex_router_result["status"] == "approval_required"
    assert result.command_result is None
    assert result.job_result is None


def test_local_agent_normal_edit_stays_local_until_explicit_escalation(tmp_path):
    result = LocalAgentOrchestrator().handle_task("fix and refactor command runner")

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.codex_router_result is None
