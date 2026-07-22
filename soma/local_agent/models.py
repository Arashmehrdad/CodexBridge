from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LocalAgentTaskType(str, Enum):
    REPO_INSPECTION = "repo_inspection"
    LIST_TESTS = "list_tests"
    LIST_FILES = "list_files"
    RUN_TESTS = "run_tests"
    RUN_CHECKS = "run_checks"
    SOURCE_EDIT = "source_edit"
    LOCAL_MODEL_REASONING = "local_model_reasoning"
    LONG_RUN_JOB = "long_run_job"
    MEMORY = "memory"
    POLICY = "policy"
    CODEX_ROUTER = "codex_router"
    SUPERVISOR = "supervisor"
    LOCAL_CODING = "local_coding"
    DASHBOARD = "dashboard"
    RISKY_ACTION = "risky_action"
    UNKNOWN = "unknown"


class RoutingDecision(str, Enum):
    LOCAL_ONLY = "local_only"
    CODEX_REQUIRED = "codex_required"
    BLOCKED = "blocked"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"


class PermissionTier(str, Enum):
    READ_ONLY = "read_only"
    SAFE_LOCAL_TEST = "safe_local_test"
    LONG_RUNNING_NON_DESTRUCTIVE_JOB = "long_running_non_destructive_job"
    WRITE_PREVIEW_DRY_RUN = "write_preview_dry_run"
    WRITE_APPLY_DELEGATED_APPROVAL = "write_apply_under_delegated_approval"
    COMMIT_PRIVATE_BRANCH_PUSH_DELEGATED_APPROVAL = (
        "commit_private_branch_push_under_delegated_approval"
    )
    HUMAN_ONLY_RISKY_ACTION = "human_only_risky_action"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(str, Enum):
    CLASSIFIED = "classified"
    BLOCKED = "blocked"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"


class CommandRunStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    REPO_MISSING = "repo_missing"
    PROFILE_MISSING = "profile_missing"
    PERMISSION_DENIED = "permission_denied"


class LocalModelStatus(str, Enum):
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    FAILED = "failed"
    INVALID_JSON = "invalid_json"
    BLOCKED = "blocked"


class LocalAgentTaskInput(BaseModel):
    objective: str
    repo_name: str | None = None
    repo_path: Path | None = None
    task_id: str = Field(default_factory=lambda: f"local_task_{uuid4().hex}")
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalAgentTask(BaseModel):
    task_id: str
    objective: str
    task_type: LocalAgentTaskType
    repo_name: str | None = None
    repo_path: Path | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    event_id: str
    task_id: str
    timestamp: str
    action: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalAgentResult(BaseModel):
    task_id: str
    repo_name: str | None = None
    repo_path: Path | None = None
    objective: str
    task_type: LocalAgentTaskType
    routing_decision: RoutingDecision
    permission_tier: PermissionTier
    risk_level: RiskLevel
    status: TaskStatus
    summary: str
    message: str = ""
    errors: list[str] = Field(default_factory=list)
    audit_event: AuditEvent
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    command_result: "CommandRunResult | None" = None
    local_model_result: "LocalModelResult | None" = None
    job_result: Any | None = None
    memory_result: Any | None = None
    policy_result: Any | None = None
    codex_router_result: Any | None = None
    supervisor_result: Any | None = None
    local_coding_result: Any | None = None
    dashboard_result: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class CommandRunResult(BaseModel):
    run_id: str
    command_id: str
    repo_name: str | None = None
    repo_path: Path | None = None
    working_directory: Path | None = None
    argv: list[str] = Field(default_factory=list)
    permission_tier: PermissionTier
    status: CommandRunStatus
    exit_code: int | None = None
    duration_seconds: float = 0.0
    timeout_seconds: int
    timed_out: bool = False
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    result_path: Path | None = None
    audit_event_id: str
    created_at: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class LocalModelMessage(BaseModel):
    role: str
    content: str


class LocalModelRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"local_model_{uuid4().hex}")
    task_type: str
    model: str
    base_url: str = "http://localhost:11434/v1"
    messages: list[LocalModelMessage]
    temperature: float = 0.2
    max_tokens: int = 1024
    timeout_seconds: int = 30
    response_format: dict[str, Any] | None = None
    json_mode: bool = False


class LocalModelResult(BaseModel):
    request_id: str
    task_type: str
    model: str
    base_url: str
    messages: list[LocalModelMessage] = Field(default_factory=list, exclude=True)
    temperature: float
    max_tokens: int
    timeout_seconds: int
    response_format: dict[str, Any] | None = None
    json_mode: bool = False
    status: LocalModelStatus
    content: str = ""
    parsed_json: Any | None = None
    error: str = ""
    duration_seconds: float = 0.0
    audit_event_id: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
