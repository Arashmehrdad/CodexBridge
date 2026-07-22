from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_WORKFLOW_STEPS = 50


class WorkflowStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLATION_PENDING = "cancellation_pending"
    RECOVERY_PENDING = "recovery_pending"
    NEEDS_APPROVAL = "needs_approval"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REPORTED = "reported"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowStepType(str, Enum):
    CODEX_IMPLEMENT = "codex_implement"
    PROJECT_COMMAND = "project_command"
    PYTEST_PATH = "pytest_path"
    GIT_READONLY = "git_readonly"
    LOCAL_SUMMARY = "local_summary"


class StepOnFailure(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"


class WorkflowStepBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: WorkflowStepType
    depends_on: list[str] = Field(default_factory=list)
    on_failure: StepOnFailure = StepOnFailure.STOP


class CodexImplementParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_plan: str
    allowed_files: list[str]
    tests: list[str] = Field(default_factory=list)


class ProjectCommandParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str


class PytestPathParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class GitReadonlyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str


class LocalSummaryParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_step_ids: list[str] = Field(default_factory=list)


class WorkflowStepDefinition(WorkflowStepBase):
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_parameters(self) -> "WorkflowStepDefinition":
        if self.type == WorkflowStepType.CODEX_IMPLEMENT:
            CodexImplementParameters.model_validate(self.parameters)
        elif self.type == WorkflowStepType.PROJECT_COMMAND:
            ProjectCommandParameters.model_validate(self.parameters)
        elif self.type == WorkflowStepType.PYTEST_PATH:
            PytestPathParameters.model_validate(self.parameters)
        elif self.type == WorkflowStepType.GIT_READONLY:
            GitReadonlyParameters.model_validate(self.parameters)
        elif self.type == WorkflowStepType.LOCAL_SUMMARY:
            LocalSummaryParameters.model_validate(self.parameters)
        return self


class WorkflowStepRecord(WorkflowStepDefinition):
    order_index: int
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    state_version: int = 0
    child_run_id: str | None = None
    child_launch_attempts: int = 0
    started_at: str | None = None
    ended_at: str | None = None
    summary: str = ""
    error: str = ""
    artifact_paths: list[Path] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_name: str
    objective: str
    steps: list[WorkflowStepDefinition]

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowDefinition":
        if not self.steps:
            raise ValueError("Workflow must contain at least one step")
        if len(self.steps) > MAX_WORKFLOW_STEPS:
            raise ValueError(
                f"Workflow exceeds maximum step count of {MAX_WORKFLOW_STEPS}"
            )
        seen: set[str] = set()
        index_by_id: dict[str, int] = {}
        for index, step in enumerate(self.steps):
            if not step.id or not step.id.strip():
                raise ValueError("Workflow step IDs must be non-empty")
            if step.id in seen:
                raise ValueError(f"Duplicate workflow step ID: {step.id}")
            seen.add(step.id)
            index_by_id[step.id] = index
        for index, step in enumerate(self.steps):
            for dependency in step.depends_on:
                if dependency not in index_by_id:
                    raise ValueError(
                        f"Workflow step {step.id} depends on missing step {dependency}"
                    )
                if index_by_id[dependency] >= index:
                    raise ValueError(
                        f"Workflow step {step.id} must depend only on earlier steps"
                    )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                raise ValueError(f"Workflow dependency cycle detected at {step_id}")
            visiting.add(step_id)
            step = self.steps[index_by_id[step_id]]
            for dependency in step.depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step in self.steps:
            visit(step.id)
        return self


class WorkflowRecord(BaseModel):
    workflow_id: str
    repo_name: str
    objective: str
    status: WorkflowStatus
    terminal_status: WorkflowStatus | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    ended_at: str | None = None
    launcher_pid: int | None = None
    launcher_identity: str = ""
    worker_pid: int | None = None
    worker_lease_token: str = Field(default="", exclude=True)
    lease_generation: int = 1
    state_version: int = 0
    worker_identity: str = ""
    worker_claimed_at: str | None = None
    launch_attempts: int = 0
    heartbeat_at: str | None = None
    active_child_run_id: str | None = None
    failure_summary: str = ""
    recommended_next_action: str = ""
    artifact_paths: list[Path] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    publication_status: str = "pending"
    publication_hash: str = ""
    published_at: str | None = None
    publication_error: str = ""
    steps: list[WorkflowStepRecord] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class WorkflowEvent(BaseModel):
    timestamp: str
    workflow_id: str
    level: Literal["info", "warning", "error"]
    stage: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class WorkflowReport(BaseModel):
    workflow_id: str
    report_path: Path
    resume_prompt_path: Path
    manifest_path: Path
    source_status: WorkflowStatus

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
