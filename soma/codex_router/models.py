from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class CodexEscalationStatus(str, Enum):
    LOCAL_ONLY = "local_only"
    CODEX_NOT_NEEDED = "codex_not_needed"
    CODEX_REQUIRED = "codex_required"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_REQUIRED = "human_required"
    BLOCKED = "blocked"
    PACKET_READY = "packet_ready"
    INVOKED = "invoked"
    COMPLETED = "completed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class CodexContextFile(BaseModel):
    path: Path
    included: bool = False
    skipped_reason: str = ""
    bytes_read: int = 0


class CodexContextSnippet(BaseModel):
    source: str
    text: str


class CodexValidationSnapshot(BaseModel):
    tests_already_run: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)


class CodexConstraint(BaseModel):
    text: str


class CodexAllowedFileSet(BaseModel):
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)


class CodexEscalationRequest(BaseModel):
    escalation_id: str = Field(default_factory=lambda: f"codex_{uuid4().hex}")
    objective: str
    task_type: str = "unknown"
    repo_name: str | None = None
    repo_path: Path | None = None
    relevant_files: list[Path] = Field(default_factory=list)
    current_error: str = ""
    failure_summary: str = ""
    tests_already_run: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    expected_output: str = "Changed files and validation results."
    invoke_codex: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodexEscalationDecision(BaseModel):
    status: CodexEscalationStatus
    codex_needed: bool
    reasons: list[str] = Field(default_factory=list)
    sensitivity_flags: list[str] = Field(default_factory=list)


class CodexEscalationPacket(BaseModel):
    escalation_id: str
    objective: str
    task_type: str
    repo_name: str | None = None
    repo_path: Path | None = None
    relevant_files: list[CodexContextFile] = Field(default_factory=list)
    relevant_snippets: list[CodexContextSnippet] = Field(default_factory=list)
    current_error: str = ""
    failure_summary: str = ""
    tests_already_run: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    constraints: list[CodexConstraint] = Field(default_factory=list)
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    expected_output: str = ""
    policy_decision: dict[str, Any] = Field(default_factory=dict)
    approval_request_id: str | None = None
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    local_model_summary: str = ""
    source_artifacts: list[Path] = Field(default_factory=list)
    created_at: str
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CodexInvocationRequest(BaseModel):
    packet: CodexEscalationPacket
    prompt: str


class CodexInvocationResult(BaseModel):
    status: CodexEscalationStatus
    invoked: bool = False
    summary: str = ""
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodexPacketArtifact(BaseModel):
    escalation_id: str
    packet_dir: Path
    packet_json_path: Path
    prompt_path: Path
    context_manifest_path: Path
    policy_result_path: Path
    codex_invocation_path: Path | None = None
    codex_result_path: Path | None = None


class CodexRouterResult(BaseModel):
    escalation_id: str
    status: CodexEscalationStatus
    packet: CodexEscalationPacket | None = None
    artifacts: CodexPacketArtifact | None = None
    invocation_result: CodexInvocationResult | None = None
    policy_decision: dict[str, Any] = Field(default_factory=dict)
    approval_request_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    sensitivity_flags: list[str] = Field(default_factory=list)
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
