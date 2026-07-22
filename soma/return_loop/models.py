from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ReturnLoopStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    SENT_BY_EXTERNAL_PULSESENDER = "sent_by_external_pulsesender"
    BLOCKED = "blocked"
    TOO_LARGE = "too_large"
    SENSITIVE = "sensitive"
    INVALID = "invalid"
    STALE = "stale"
    FAILED = "failed"


class ReturnLoopArtifact(BaseModel):
    path: Path
    sha256: str = ""
    content_bytes: int = 0
    exists: bool = False


class ResumePrompt(BaseModel):
    artifact_id: str
    source_kind: str
    content: str
    path: Path | None = None


class PulseSenderContract(BaseModel):
    send_policy: str = "external_pulsesender_only"
    conversation_target: str = "soma_gpt"
    soma_sends_messages: bool = False
    controls_browser: bool = False


class ReportManifest(BaseModel):
    schema_version: str = "1"
    artifact_type: str
    artifact_id: str
    conversation_target: str = "soma_gpt"
    status: ReturnLoopStatus
    ready: bool = False
    delivered: bool = False
    created_at: str
    updated_at: str
    report_path: Path | None = None
    resume_prompt_path: Path | None = None
    result_json_path: Path | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    artifact_paths: list[Path] = Field(default_factory=list)
    content_sha256: str = ""
    report_sha256: str = ""
    result_sha256: str = ""
    content_bytes: int = 0
    report_bytes: int = 0
    result_bytes: int = 0
    max_content_bytes: int = 20000
    max_report_bytes: int = 100000
    sensitivity_flags: list[str] = Field(default_factory=list)
    blocked_reason: str = ""
    recommended_next_action: str = ""
    question_for_chatgpt: str = ""
    source_kind: str
    source_status: str
    send_policy: str = "external_pulsesender_only"
    sent_at: str | None = None
    sender_id: str | None = None
    delivery_hash: str | None = None
    audit_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ReportReadinessResult(BaseModel):
    manifest_path: Path
    status: ReturnLoopStatus
    ready: bool
    blocked_reason: str = ""
    sensitivity_flags: list[str] = Field(default_factory=list)
    manifest: ReportManifest | None = None


class AtomicWriteResult(BaseModel):
    path: Path
    temp_path: Path
    bytes_written: int
    replaced: bool
    sha256: str
