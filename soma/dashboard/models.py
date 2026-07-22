from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DashboardItem(BaseModel):
    id: str
    source_kind: str
    status: str = ""
    created_at: str = ""
    updated_at: str = ""
    ended_at: str = ""
    repo_name: str | None = None
    repo_path: Path | None = None
    artifact_path: Path | None = None
    summary: str = ""
    error: str = ""
    failure_summary: str = ""
    next_recommended_action: str = ""
    readiness: str = ""
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class DashboardRunSummary(DashboardItem):
    source_kind: str = "run"


class DashboardCommandSummary(DashboardItem):
    source_kind: str = "command"
    command_id: str = ""
    exit_code: int | None = None


class DashboardJobSummary(DashboardItem):
    source_kind: str = "job"
    job_profile: str = ""


class DashboardWorkflowSummary(DashboardItem):
    source_kind: str = "workflow"
    terminal_status: str = ""
    active_child_run_id: str = ""
    step_states: list[str] = Field(default_factory=list)


class DashboardSupervisorSummary(DashboardItem):
    source_kind: str = "supervisor"
    codex_invoked: bool = False
    codex_packet_path: Path | None = None


class DashboardApprovalSummary(DashboardItem):
    source_kind: str = "approval"
    required_approver: str = ""
    action_type: str = ""


class DashboardCodexEscalationSummary(DashboardItem):
    source_kind: str = "codex_escalation"
    packet_path: Path | None = None
    codex_invoked: bool = False


class DashboardReturnLoopSummary(DashboardItem):
    source_kind: str = "return_loop"
    ready: bool = False
    delivered: bool = False


class DashboardLocalCodingSummary(DashboardItem):
    source_kind: str = "local_coding"
    target_file: Path | None = None
    approval_request_id: str | None = None


class DashboardMemorySummary(BaseModel):
    source_kind: str = "memory"
    total_records: int = 0
    recent: list[DashboardItem] = Field(default_factory=list)
    error: str = ""


class DashboardRepoStatusSummary(BaseModel):
    source_kind: str = "repo_status"
    status: str = "artifact_only"
    latest_git_status_artifact: Path | None = None
    summary: str = ""
    error: str = ""


class DashboardHealthResult(BaseModel):
    ok: bool
    read_only: bool = True
    runs_dir: Path
    errors: list[str] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    health: DashboardHealthResult
    runs: list[DashboardRunSummary] = Field(default_factory=list)
    commands: list[DashboardCommandSummary] = Field(default_factory=list)
    jobs: list[DashboardJobSummary] = Field(default_factory=list)
    workflows: list[DashboardWorkflowSummary] = Field(default_factory=list)
    supervisors: list[DashboardSupervisorSummary] = Field(default_factory=list)
    approvals: list[DashboardApprovalSummary] = Field(default_factory=list)
    codex_escalations: list[DashboardCodexEscalationSummary] = Field(
        default_factory=list
    )
    return_loop: list[DashboardReturnLoopSummary] = Field(default_factory=list)
    local_coding: list[DashboardLocalCodingSummary] = Field(default_factory=list)
    memory: DashboardMemorySummary = Field(default_factory=DashboardMemorySummary)
    repo_status: DashboardRepoStatusSummary = Field(
        default_factory=DashboardRepoStatusSummary
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
