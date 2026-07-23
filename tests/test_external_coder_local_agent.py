from __future__ import annotations

from soma.external_coder import ExternalCoderHandoffGenerator
from soma.local_agent import LocalAgentOrchestrator
from soma.local_agent.models import LocalAgentTaskType, RoutingDecision
from soma.policy import PolicyEngine


def test_local_agent_routes_explicit_handoff_request(tmp_path):
    generator = ExternalCoderHandoffGenerator(
        policy_engine=PolicyEngine(approvals_dir=tmp_path / "runs" / "approvals"),
        handoff_dir=tmp_path / "runs" / "external_coder_handoffs",
    )
    result = LocalAgentOrchestrator(handoff_generator=generator).handle_task(
        "prepare external coder handoff: edit source file"
    )

    assert result.task_type == LocalAgentTaskType.EXTERNAL_CODER
    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.external_coder_result["status"] == "approval_required"
    assert result.command_result is None
    assert result.job_result is None


def test_local_agent_normal_edit_stays_local_without_explicit_handoff(tmp_path):
    result = LocalAgentOrchestrator().handle_task("fix and refactor command runner")

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.external_coder_result is None
