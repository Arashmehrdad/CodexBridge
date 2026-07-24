from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ExternalCoderHandoffStatus(str, Enum):
    """Provider-neutral states for inert handoff artifact generation.

    Soma never launches, supervises, selects, or routes to an external coding
    agent. A generated artifact exists only for human use outside Soma and is
    never an executable run, worker request, fallback, or PowerShell target.
    """

    LOCAL_ONLY = "local_only"
    EXTERNAL_CODER_NOT_NEEDED = "external_coder_not_needed"
    NEEDS_EXTERNAL_CODER = "needs_external_coder"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_REQUIRED = "human_required"
    BLOCKED = "blocked"
    HANDOFF_READY = "handoff_ready"


class ExternalCoderContextFile(BaseModel):
    path: Path
    included: bool = False
    skipped_reason: str = ""
    bytes_read: int = 0


class ExternalCoderContextSnippet(BaseModel):
    source: str
    text: str


class ExternalCoderConstraint(BaseModel):
    text: str


class RepositoryStateSnapshot(BaseModel):
    """Bounded snapshot of branch, HEAD, and worktree state at handoff time."""

    captured: bool = False
    branch: str = ""
    head: str = ""
    worktree_status: str = ""
    worktree_clean: bool | None = None
    error: str = ""


class ExternalCoderHandoffRequest(BaseModel):
    handoff_id: str = Field(default_factory=lambda: f"handoff_{uuid4().hex}")
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
    expected_report: str = (
        "Changed files, commands run, validation results, and remaining risks."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalCoderHandoff(BaseModel):
    """The bounded, provider-neutral handoff packet.

    Contains everything an external coding agent needs, and nothing that
    invokes one: no executable references, no transport, no launch hooks.
    """

    handoff_id: str
    objective: str
    task_type: str
    repo_name: str | None = None
    repo_path: Path | None = None
    repository_state: RepositoryStateSnapshot = Field(
        default_factory=RepositoryStateSnapshot
    )
    relevant_files: list[ExternalCoderContextFile] = Field(default_factory=list)
    relevant_snippets: list[ExternalCoderContextSnippet] = Field(default_factory=list)
    current_error: str = ""
    failure_summary: str = ""
    tests_already_run: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    constraints: list[ExternalCoderConstraint] = Field(default_factory=list)
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    expected_report: str = ""
    policy_decision: dict[str, Any] = Field(default_factory=dict)
    approval_request_id: str | None = None
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    local_model_summary: str = ""
    source_artifacts: list[Path] = Field(default_factory=list)
    created_at: str
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ExternalCoderHandoffArtifact(BaseModel):
    handoff_id: str
    handoff_dir: Path
    handoff_json_path: Path
    prompt_path: Path
    context_manifest_path: Path
    policy_result_path: Path


class ExternalCoderHandoffResult(BaseModel):
    handoff_id: str
    status: ExternalCoderHandoffStatus
    handoff: ExternalCoderHandoff | None = None
    artifacts: ExternalCoderHandoffArtifact | None = None
    policy_decision: dict[str, Any] = Field(default_factory=dict)
    approval_request_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    sensitivity_flags: list[str] = Field(default_factory=list)
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
