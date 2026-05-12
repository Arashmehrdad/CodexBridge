from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class CanonicalPermissionTier(str, Enum):
    T0_READ_ONLY = "T0_READ_ONLY"
    T1_SAFE_LOCAL_TEST = "T1_SAFE_LOCAL_TEST"
    T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB = "T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB"
    T3_WRITE_PREVIEW_DRY_RUN = "T3_WRITE_PREVIEW_DRY_RUN"
    T4_WRITE_APPLY_CHATGPT_DELEGATED = "T4_WRITE_APPLY_CHATGPT_DELEGATED"
    T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED = "T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED"
    T6_HUMAN_ONLY_RISKY_ACTION = "T6_HUMAN_ONLY_RISKY_ACTION"


LEGACY_PERMISSION_MAP = {
    "read_only": CanonicalPermissionTier.T0_READ_ONLY,
    "safe_local_test": CanonicalPermissionTier.T1_SAFE_LOCAL_TEST,
    "long_running_non_destructive_job": CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
    "write_preview_dry_run": CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN,
    "write_apply_under_delegated_approval": CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
    "commit_private_branch_push_under_delegated_approval": CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED,
    "human_only_risky_action": CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
}


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class PolicyDecisionValue(str, Enum):
    ALLOWED = "allowed"
    ALLOWED_WITH_CHATGPT_DELEGATED_APPROVAL = "allowed_with_chatgpt_delegated_approval"
    NEEDS_CHATGPT_APPROVAL = "needs_chatgpt_approval"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"
    BLOCKED = "blocked"
    DENIED = "denied"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AutonomyProfileModel(BaseModel):
    name: str
    allow_tiers: list[CanonicalPermissionTier] = Field(default_factory=list)
    chatgpt_approval_tiers: list[CanonicalPermissionTier] = Field(default_factory=list)
    human_approval_tiers: list[CanonicalPermissionTier] = Field(default_factory=list)


class RiskClassification(BaseModel):
    action_type: str
    permission_tier: CanonicalPermissionTier
    risk_level: RiskLevel
    human_required: bool = False
    blocked: bool = False
    reasons: list[str] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)
    sensitivity_flags: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approval_request_id: str = Field(default_factory=lambda: f"approval_{uuid4().hex}")
    request_id: str
    action_type: str
    repo_name: str | None = None
    repo_path: Path | None = None
    permission_tier: CanonicalPermissionTier
    risk_level: RiskLevel
    requested_by: str = "chatgpt"
    required_approver: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reasons: list[str] = Field(default_factory=list)
    created_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_notes: str = ""
    audit_event_id: str


class ApprovalDecision(BaseModel):
    approval_request_id: str
    status: ApprovalStatus
    decided_by: str
    decided_at: str
    decision_notes: str = ""


class ApprovalStoreRecord(ApprovalRequest):
    pass


class PolicyEvaluationRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"policy_{uuid4().hex}")
    action: str
    action_type: str = "unknown"
    repo_name: str | None = None
    repo_path: Path | None = None
    requested_by: str = "chatgpt"
    autonomy_profile: str = "chatgpt_delegated"
    permission_tier: CanonicalPermissionTier | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyRule(BaseModel):
    rule_id: str
    description: str
    decision: PolicyDecisionValue


class PolicyEvaluationResult(BaseModel):
    request_id: str
    action_type: str
    repo_name: str | None = None
    repo_path: Path | None = None
    requested_by: str
    autonomy_profile: str
    permission_tier: CanonicalPermissionTier
    risk_level: RiskLevel
    decision: PolicyDecisionValue
    approval_required: bool = False
    human_required: bool = False
    chatgpt_delegated_allowed: bool = False
    blocked: bool = False
    reasons: list[str] = Field(default_factory=list)
    matched_rules: list[str] = Field(default_factory=list)
    sensitivity_flags: list[str] = Field(default_factory=list)
    approval_request_id: str | None = None
    audit_event_id: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
