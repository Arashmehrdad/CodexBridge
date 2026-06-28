from __future__ import annotations

import json
from pathlib import Path

from codexbridge.local_agent import LocalAgentOrchestrator, LocalAgentTaskType


def test_local_agent_routes_dashboard_summary_read_only(tmp_path: Path) -> None:
    result_path = (
        tmp_path / "runs" / "local_agent" / "commands" / "cmd1" / "result.json"
    )
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps({"run_id": "cmd1", "command_id": "git_status", "status": "success"}),
        encoding="utf-8",
    )
    orchestrator = LocalAgentOrchestrator(dashboard_runs_dir=tmp_path / "runs")

    result = orchestrator.handle_task("dashboard summary")

    assert result.task_type == LocalAgentTaskType.DASHBOARD
    assert result.dashboard_result["commands"][0]["id"] == "cmd1"
    assert result.audit_metadata["commands_executed"] is False


def test_local_agent_dashboard_health_does_not_start_server_or_execute_actions(
    tmp_path: Path,
) -> None:
    orchestrator = LocalAgentOrchestrator(dashboard_runs_dir=tmp_path / "runs")

    result = orchestrator.handle_task("dashboard health")

    assert result.task_type == LocalAgentTaskType.DASHBOARD
    assert result.dashboard_result["read_only"] is True
