from __future__ import annotations

import json
from pathlib import Path

from codexbridge.local_agent import (
    LocalAgentOrchestrator,
    LocalAgentTaskInput,
    LocalAgentTaskType,
    PermissionTier,
    RiskLevel,
    RoutingDecision,
    TaskStatus,
    classify_task,
)


def test_repo_inspection_is_local_only_read_only() -> None:
    result = LocalAgentOrchestrator().handle_task("inspect repo and list files")

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.permission_tier == PermissionTier.READ_ONLY
    assert result.risk_level == RiskLevel.LOW
    assert result.status == TaskStatus.CLASSIFIED
    assert result.audit_event.metadata["commands_executed"] is False
    assert result.audit_event.metadata["codex_called"] is False


def test_inspect_project_tests_returns_structured_local_only_result_without_codex(
    tmp_path: Path,
) -> None:
    result = LocalAgentOrchestrator().handle_task(
        LocalAgentTaskInput(
            repo_name="sample",
            repo_path=tmp_path,
            objective="inspect project and tell me what tests exist",
        )
    )

    payload = result.to_dict()
    assert payload["repo_name"] == "sample"
    assert payload["repo_path"] == str(tmp_path)
    assert payload["task_type"] == LocalAgentTaskType.LIST_TESTS.value
    assert payload["routing_decision"] == RoutingDecision.LOCAL_ONLY.value
    assert payload["permission_tier"] == PermissionTier.READ_ONLY.value
    assert payload["audit_metadata"]["codex_called"] is False


def test_edit_refactor_fix_task_is_local_first() -> None:
    assert (
        classify_task("refactor the runner and fix the bug")
        == LocalAgentTaskType.SOURCE_EDIT
    )

    result = LocalAgentOrchestrator().handle_task("refactor the runner and fix the bug")
    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.permission_tier == PermissionTier.WRITE_APPLY_DELEGATED_APPROVAL
    assert result.status == TaskStatus.CLASSIFIED


def test_secret_credential_destructive_or_production_task_is_blocked_or_human_only() -> (
    None
):
    objectives = [
        "read the API key from .env",
        "use credentials to deploy to production",
        "delete volume and wipe generated data",
        "public release and push main",
    ]

    for objective in objectives:
        result = LocalAgentOrchestrator().handle_task(objective)
        assert result.routing_decision in {
            RoutingDecision.BLOCKED,
            RoutingDecision.NEEDS_HUMAN_APPROVAL,
        }
        assert result.permission_tier == PermissionTier.HUMAN_ONLY_RISKY_ACTION
        assert result.risk_level == RiskLevel.HIGH
        assert result.status in {TaskStatus.BLOCKED, TaskStatus.NEEDS_HUMAN_APPROVAL}
        assert result.errors


def test_result_schema_is_stable_and_serializable(tmp_path: Path) -> None:
    result = LocalAgentOrchestrator().handle_task(
        {
            "task_id": "local_task_test",
            "repo_name": "sample",
            "repo_path": tmp_path,
            "objective": "list files in the repo",
        }
    )

    payload = result.to_dict()
    json.dumps(payload, sort_keys=True)
    assert set(payload) == {
        "task_id",
        "repo_name",
        "repo_path",
        "objective",
        "task_type",
        "routing_decision",
        "permission_tier",
        "risk_level",
        "status",
        "summary",
        "message",
        "errors",
        "audit_event",
        "audit_metadata",
    }


def test_no_arbitrary_command_runner_behavior_is_exposed() -> None:
    orchestrator = LocalAgentOrchestrator()

    assert not hasattr(orchestrator, "run_command")
    assert not hasattr(orchestrator, "execute")
