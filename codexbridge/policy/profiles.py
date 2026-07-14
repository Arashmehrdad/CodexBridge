from __future__ import annotations

from types import MappingProxyType

from .models import AutonomyProfileModel, CanonicalPermissionTier


BUILTIN_AUTONOMY_PROFILES = MappingProxyType(
    {
        "conservative": AutonomyProfileModel(
            name="conservative",
            allow_tiers=[CanonicalPermissionTier.T0_READ_ONLY],
            human_approval_tiers=[
                CanonicalPermissionTier.T1_SAFE_LOCAL_TEST,
                CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
                CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN,
                CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
                CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED,
                CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION,
            ],
        ),
        "balanced": AutonomyProfileModel(
            name="balanced",
            allow_tiers=[
                CanonicalPermissionTier.T0_READ_ONLY,
                CanonicalPermissionTier.T1_SAFE_LOCAL_TEST,
                CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            ],
            chatgpt_approval_tiers=[
                CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN,
                CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
                CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED,
            ],
            human_approval_tiers=[CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION],
        ),
        "permissive": AutonomyProfileModel(
            name="permissive",
            allow_tiers=[
                CanonicalPermissionTier.T0_READ_ONLY,
                CanonicalPermissionTier.T1_SAFE_LOCAL_TEST,
                CanonicalPermissionTier.T2_LONG_RUNNING_NON_DESTRUCTIVE_JOB,
                CanonicalPermissionTier.T3_WRITE_PREVIEW_DRY_RUN,
                CanonicalPermissionTier.T4_WRITE_APPLY_CHATGPT_DELEGATED,
                CanonicalPermissionTier.T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED,
            ],
            human_approval_tiers=[CanonicalPermissionTier.T6_HUMAN_ONLY_RISKY_ACTION],
        ),
    }
)


def get_autonomy_profile(name: str) -> AutonomyProfileModel:
    return BUILTIN_AUTONOMY_PROFILES.get(name, BUILTIN_AUTONOMY_PROFILES["balanced"])


def list_autonomy_profiles() -> dict[str, AutonomyProfileModel]:
    return dict(BUILTIN_AUTONOMY_PROFILES)
