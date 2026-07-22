from __future__ import annotations

from pathlib import Path

from soma.config import AutonomyConfig
from soma.run_store import utc_now

from .approval_store import ApprovalStore
from .audit import policy_audit_event
from .models import (
    ApprovalRequest,
    CanonicalPermissionTier,
    PolicyDecisionValue,
    PolicyEvaluationRequest,
    PolicyEvaluationResult,
)
from .profiles import get_autonomy_profile
from .risk_classifier import RiskClassifier


class PolicyEngine:
    def __init__(
        self,
        *,
        config: AutonomyConfig | None = None,
        approvals_dir: Path | None = None,
        risk_classifier: RiskClassifier | None = None,
    ):
        self.config = config or AutonomyConfig()
        self.approval_store = ApprovalStore(
            approvals_dir or Path.cwd() / "runs" / "approvals"
        )
        self.risk_classifier = risk_classifier or RiskClassifier()

    def evaluate(self, request: PolicyEvaluationRequest) -> PolicyEvaluationResult:
        audit = policy_audit_event(
            "policy_evaluation_requested",
            "Policy evaluation requested",
            {"request_id": request.request_id, "action_type": request.action_type},
        )
        classification = self.risk_classifier.classify(request)
        profile_name = request.autonomy_profile or self.config.autonomy_default_profile
        profile = get_autonomy_profile(profile_name)
        reasons = list(classification.reasons)
        decision = PolicyDecisionValue.UNKNOWN
        approval_required = False
        human_required = classification.human_required
        chatgpt_allowed = False
        blocked = classification.blocked
        approval_request_id = None

        if not self._repo_allowed(request, classification.permission_tier):
            blocked = True
            reasons.append("repo_not_whitelisted")

        if classification.blocked:
            decision = PolicyDecisionValue.BLOCKED
        elif classification.permission_tier in profile.allow_tiers:
            decision = PolicyDecisionValue.ALLOWED
        elif classification.permission_tier in profile.chatgpt_approval_tiers:
            decision = PolicyDecisionValue.NEEDS_CHATGPT_APPROVAL
            approval_required = True
            chatgpt_allowed = True
        elif (
            classification.permission_tier in profile.human_approval_tiers
            or human_required
        ):
            decision = PolicyDecisionValue.NEEDS_HUMAN_APPROVAL
            approval_required = True
            human_required = True
        else:
            decision = PolicyDecisionValue.BLOCKED
            blocked = True
            reasons.append("tier_not_allowed_by_profile")

        if (
            classification.permission_tier
            == CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION
        ):
            human_required = True
            approval_required = True
            if decision != PolicyDecisionValue.BLOCKED:
                decision = PolicyDecisionValue.NEEDS_HUMAN_APPROVAL

        if approval_required and not blocked:
            approval = ApprovalRequest(
                request_id=request.request_id,
                action_type=request.action_type,
                repo_name=request.repo_name,
                repo_path=request.repo_path,
                permission_tier=classification.permission_tier,
                risk_level=classification.risk_level,
                requested_by=request.requested_by,
                required_approver="human" if human_required else "chatgpt",
                reasons=reasons,
                created_at=utc_now(),
                audit_event_id=audit["audit_event_id"],
            )
            self.approval_store.create(approval)
            approval_request_id = approval.approval_request_id

        return PolicyEvaluationResult(
            request_id=request.request_id,
            action_type=request.action_type,
            repo_name=request.repo_name,
            repo_path=request.repo_path,
            requested_by=request.requested_by,
            autonomy_profile=profile.name,
            permission_tier=classification.permission_tier,
            risk_level=classification.risk_level,
            decision=decision,
            approval_required=approval_required,
            human_required=human_required,
            chatgpt_delegated_allowed=chatgpt_allowed,
            blocked=blocked or decision == PolicyDecisionValue.BLOCKED,
            reasons=reasons,
            matched_rules=classification.matched_rules,
            sensitivity_flags=classification.sensitivity_flags,
            approval_request_id=approval_request_id,
            audit_event_id=audit["audit_event_id"],
            created_at=utc_now(),
        )

    def _repo_allowed(
        self, request: PolicyEvaluationRequest, tier: CanonicalPermissionTier
    ) -> bool:
        if tier in {
            CanonicalPermissionTier.T0_READ_ONLY,
            CanonicalPermissionTier.T1_SAFE_LOCAL_TEST,
            CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
        }:
            return True
        if not self.config.autonomy_whitelisted_repos:
            return True
        return bool(
            request.repo_name
            and request.repo_name in self.config.autonomy_whitelisted_repos
        )
