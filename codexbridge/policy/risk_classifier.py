from __future__ import annotations

from .models import CanonicalPermissionTier, LEGACY_PERMISSION_MAP, PolicyEvaluationRequest, RiskClassification, RiskLevel


SENSITIVE_MARKERS = ("api key", "secret", "password", "token", "private key", "credential", "authorization", "bearer")
HUMAN_MARKERS = (
    "production deploy",
    "production infrastructure",
    "real-money",
    "real money",
    "public repo push",
    "push to main",
    "push main",
    "push to master",
    "release tag",
    "deployment branch",
    "grant external access",
    "external permission",
    "connector ui approval",
    "sudo",
    "chmod -r",
    "chown -r",
)
BLOCKED_MARKERS = ("rm -rf", "delete volume", "drop database", "wipe", "format drive", "remove-item -recurse -force")


class RiskClassifier:
    def classify(self, request: PolicyEvaluationRequest) -> RiskClassification:
        text = f"{request.action} {request.action_type} {request.metadata}".lower()
        explicit_tier = _normalize_tier(request.permission_tier)
        sensitivity = [marker.upper().replace(" ", "_") for marker in SENSITIVE_MARKERS if marker in text]
        if sensitivity:
            return RiskClassification(
                action_type=request.action_type,
                permission_tier=CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
                risk_level=RiskLevel.CRITICAL,
                human_required=True,
                blocked=True,
                reasons=["secret_like_content"],
                matched_rules=["sensitive_marker"],
                sensitivity_flags=sensitivity,
            )
        if any(marker in text for marker in BLOCKED_MARKERS):
            return RiskClassification(
                action_type=request.action_type,
                permission_tier=CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
                risk_level=RiskLevel.CRITICAL,
                human_required=True,
                blocked=True,
                reasons=["destructive_action"],
                matched_rules=["destructive_marker"],
            )
        if any(marker in text for marker in HUMAN_MARKERS):
            return RiskClassification(
                action_type=request.action_type,
                permission_tier=CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
                risk_level=RiskLevel.HIGH,
                human_required=True,
                reasons=["human_only_boundary"],
                matched_rules=["human_required_marker"],
            )
        tier = explicit_tier or _infer_tier(text, request.action_type)
        risk = {
            CanonicalPermissionTier.T0_READ_ONLY: RiskLevel.LOW,
            CanonicalPermissionTier.T1_SAFE_LOCAL_TEST: RiskLevel.LOW,
            CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB: RiskLevel.MEDIUM,
            CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN: RiskLevel.MEDIUM,
            CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED: RiskLevel.MEDIUM,
            CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED: RiskLevel.MEDIUM,
            CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION: RiskLevel.HIGH,
        }[tier]
        return RiskClassification(action_type=request.action_type, permission_tier=tier, risk_level=risk, human_required=tier == CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION, reasons=[f"classified_{tier.value.lower()}"], matched_rules=["metadata_or_text_classification"])


def _normalize_tier(value) -> CanonicalPermissionTier | None:
    if value is None:
        return None
    if isinstance(value, CanonicalPermissionTier):
        return value
    return LEGACY_PERMISSION_MAP.get(str(value), CanonicalPermissionTier(str(value)) if str(value) in CanonicalPermissionTier._value2member_map_ else None)


def _infer_tier(text: str, action_type: str) -> CanonicalPermissionTier:
    if any(term in text for term in ("git status", "git diff", "inspect", "list files", "read-only", "read only")):
        return CanonicalPermissionTier.T0_READ_ONLY
    if any(term in text for term in ("pytest", "pip check", "run tests", "safe test")):
        return CanonicalPermissionTier.T1_SAFE_LOCAL_TEST
    if any(term in text for term in ("long-running", "long running", "job profile", "benchmark job", "cancel job", "job status")):
        return CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB
    if any(term in text for term in ("dry run", "preview", "plan write")):
        return CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN
    if any(term in text for term in ("commit", "private branch", "feature branch push")):
        return CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED
    if any(term in text for term in ("edit", "write", "apply", "fix", "refactor", "create module", "non-secret config")):
        return CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED
    return CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION if action_type == "unknown" else CanonicalPermissionTier.T0_READ_ONLY
