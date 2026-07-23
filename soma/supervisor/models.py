from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SupervisorStatus(str, Enum):
    CREATED = "created"
    INSPECTING = "inspecting"
    PLANNING = "planning"
    VALIDATING_LOCALLY = "validating_locally"
    NEEDS_EXTERNAL_CODER = "needs_external_coder"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_INPUT = "needs_input"
    CANCELLED = "cancelled"
    REPORTED = "reported"
    # Legacy read-only values retained so historical supervisor records
    # remain parseable. New runs never produce them; Soma no longer
    # integrates or invokes Codex.
    CODEX_NOT_NEEDED = "codex_not_needed"
    CODEX_PACKET_READY = "codex_packet_ready"
    INVOKING_CODEX = "invoking_codex"
    VALIDATING_AFTER_CODEX = "validating_after_codex"


class SupervisorTaskRequest(BaseModel):
    supervisor_id: str = Field(default_factory=lambda: f"supervisor_{uuid4().hex}")
    objective: str
    repo_name: str | None = None
    repo_path: Path | None = None
    validation_commands: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupervisorStep(BaseModel):
    name: str
    status: str
    summary: str = ""
    artifact_path: Path | None = None


class SupervisorPlan(BaseModel):
    objective: str
    likely_task_type: str
    external_coder_required: bool
    validation_steps: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)
    policy_considerations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_next_action: str = ""


class SupervisorDecision(BaseModel):
    external_coder_needed: bool
    status: SupervisorStatus
    reasons: list[str] = Field(default_factory=list)


class SupervisorArtifact(BaseModel):
    path: Path
    artifact_type: str


class SupervisorEvent(BaseModel):
    timestamp: str
    supervisor_id: str
    level: str = "info"
    stage: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class SupervisorRun(BaseModel):
    supervisor_id: str
    objective: str
    repo_name: str | None = None
    repo_path: Path | None = None
    status: SupervisorStatus
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float | None = None
    local_inspection_summary: str = ""
    local_plan_summary: str = ""
    validation_commands: list[str] = Field(default_factory=list)
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    memory_context_ids: list[str] = Field(default_factory=list)
    policy_summary: dict[str, Any] = Field(default_factory=dict)
    external_coder_handoff_id: str | None = None
    external_coder_handoff_path: Path | None = None
    external_coder_prompt_path: Path | None = None
    # Legacy read-only fields retained so historical supervisor records
    # remain parseable; new runs never populate them.
    codex_escalation_id: str | None = None
    codex_packet_path: Path | None = None
    codex_invoked: bool = False
    codex_result_path: Path | None = None
    post_validation_results: list[dict[str, Any]] = Field(default_factory=list)
    failure_summary: str = ""
    next_recommended_action: str = ""
    question_for_chatgpt: str = ""
    artifact_paths: list[Path] = Field(default_factory=list)
    audit_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class SupervisorStatusResult(BaseModel):
    run: SupervisorRun
    events: list[SupervisorEvent] = Field(default_factory=list)


class SupervisorResult(BaseModel):
    run: SupervisorRun
    report_path: Path | None = None
    resume_prompt_path: Path | None = None
    pulse_manifest_path: Path | None = None


class SupervisorReport(BaseModel):
    supervisor_id: str
    report_path: Path
    resume_prompt_path: Path
    pulse_manifest_path: Path | None = None


class SupervisorResumePrompt(BaseModel):
    supervisor_id: str
    content: str
    path: Path
