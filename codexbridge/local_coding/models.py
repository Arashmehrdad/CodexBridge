from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LocalCodingStatus(str, Enum):
    DRAFT = "draft"
    PREVIEW_READY = "preview_ready"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    APPLIED = "applied"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LocalPatchOperationType(str, Enum):
    EXACT_TEXT_REPLACE = "exact_text_replace"
    APPEND_LINE = "append_line"
    REPLACE_LINE = "replace_line"
    UPDATE_JSON_KEY = "update_json_key"


class LocalCodingRequest(BaseModel):
    edit_id: str = Field(default_factory=lambda: f"local_edit_{uuid4().hex}")
    objective: str
    repo_name: str | None = None
    repo_path: Path
    target_file: Path | None = None
    operations: list["LocalPatchOperation"] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalCodingClassification(BaseModel):
    eligible: bool
    reason: str
    blocked_reasons: list[str] = Field(default_factory=list)
    suggested_route: str = "local_coding"
    risk_level: str = "low"


class LocalPatchOperation(BaseModel):
    operation_type: LocalPatchOperationType
    target_file: Path
    old_text: str = ""
    new_text: str = ""
    line_number: int | None = None
    json_key: str = ""
    json_value: Any | None = None


class LocalEditProposal(BaseModel):
    edit_id: str
    objective: str
    repo_name: str | None = None
    repo_path: Path
    target_file: Path
    operations: list[LocalPatchOperation]
    original_sha256: str
    resulting_sha256: str
    changed_lines: int
    changed_bytes: int
    status: LocalCodingStatus
    classification: LocalCodingClassification
    policy_result: dict[str, Any] = Field(default_factory=dict)
    approval_request_id: str | None = None
    validation_commands: list[str] = Field(default_factory=list)
    rollback_path: Path | None = None
    created_at: str
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class LocalPatchPreview(BaseModel):
    edit_id: str
    status: LocalCodingStatus
    proposal_path: Path
    preview_diff_path: Path
    preview_md_path: Path
    policy_result_path: Path
    approval_request_path: Path | None = None
    diff_summary: str
    unified_diff: str
    blocked_reasons: list[str] = Field(default_factory=list)
    audit_event_id: str


class LocalPatchValidationResult(BaseModel):
    valid: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    changed_lines: int = 0
    changed_bytes: int = 0
    sensitivity_flags: list[str] = Field(default_factory=list)


class LocalPatchApplyRequest(BaseModel):
    edit_id: str
    approval_request_id: str = ""


class LocalPatchApplyResult(BaseModel):
    edit_id: str
    status: LocalCodingStatus
    target_file: Path | None = None
    apply_result_path: Path | None = None
    validation_results_path: Path | None = None
    rollback_patch_path: Path | None = None
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class LocalPatchRollbackResult(BaseModel):
    edit_id: str
    status: LocalCodingStatus
    target_file: Path | None = None
    rollback_result_path: Path | None = None
    error: str = ""
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class LocalCodingArtifact(BaseModel):
    path: Path
    artifact_type: str


class LocalCodingAuditEvent(BaseModel):
    timestamp: str
    edit_id: str
    action: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalCodingRun(BaseModel):
    edit_id: str
    status: LocalCodingStatus
    repo_name: str | None = None
    repo_path: Path | None = None
    target_file: Path | None = None
    objective: str = ""
    proposal_path: Path | None = None
    preview_diff_path: Path | None = None
    preview_md_path: Path | None = None
    apply_result_path: Path | None = None
    rollback_result_path: Path | None = None
    approval_request_id: str | None = None
    artifact_paths: list[Path] = Field(default_factory=list)
    created_at: str
    updated_at: str
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
