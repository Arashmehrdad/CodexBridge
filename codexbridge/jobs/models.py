from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codexbridge.local_agent.models import PermissionTier


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    NEEDS_INPUT = "needs_input"
    REPORTED = "reported"
    BLOCKED = "blocked"
    PROFILE_MISSING = "profile_missing"
    PERMISSION_DENIED = "permission_denied"
    REPO_MISSING = "repo_missing"


class JobProfile(BaseModel):
    profile_id: str
    argv: list[str] = Field(min_length=1)
    permission_tier: PermissionTier = PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB
    timeout_seconds: int = Field(default=300, ge=1)
    allowed_artifact_globs: list[str] = Field(default_factory=list)
    description: str = ""
    enabled: bool = True


class JobStartRequest(BaseModel):
    profile_id: str
    repo_name: str | None = None
    repo_path: Path | None = None
    timeout_seconds: int | None = None


class JobArtifact(BaseModel):
    path: Path
    relative_path: str


class JobEvent(BaseModel):
    event_id: str
    job_id: str
    timestamp: str
    level: str = "info"
    stage: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class JobResult(BaseModel):
    job_id: str
    repo_name: str | None = None
    repo_path: Path | None = None
    job_profile: str
    argv: list[str] = Field(default_factory=list)
    permission_tier: PermissionTier
    status: JobStatus
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float | None = None
    timeout_seconds: int
    exit_code: int | None = None
    pid: int | None = None
    working_directory: Path | None = None
    stdout_path: Path
    stderr_path: Path
    events_path: Path
    result_json_path: Path
    artifact_paths: list[Path] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    failure_summary: str = ""
    next_recommended_action: str = ""
    audit_event_id: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class JobStatusResult(BaseModel):
    job: JobResult
    events: list[JobEvent] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class JobCancelResult(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    audit_event_id: str


class JobReport(BaseModel):
    job_id: str
    status: JobStatus
    report_path: Path
    resume_prompt_path: Path
    manifest_path: Path | None = None
    summary: str
    question_for_chatgpt: str = ""
