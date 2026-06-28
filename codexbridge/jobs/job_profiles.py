from __future__ import annotations

import sys
from types import MappingProxyType

from codexbridge.local_agent.models import PermissionTier

from .models import JobProfile


BUILTIN_JOB_PROFILES: MappingProxyType[str, JobProfile] = MappingProxyType(
    {
        "dummy_success": JobProfile(
            profile_id="dummy_success",
            argv=[sys.executable, "-c", "print('dummy success')"],
            permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            timeout_seconds=30,
            allowed_artifact_globs=["artifacts/*.txt"],
            description="Deterministic successful demo job.",
            enabled=True,
        ),
        "dummy_failure": JobProfile(
            profile_id="dummy_failure",
            argv=[
                sys.executable,
                "-c",
                "import sys; print('dummy failure', file=sys.stderr); sys.exit(2)",
            ],
            permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            timeout_seconds=30,
            allowed_artifact_globs=[],
            description="Deterministic failing demo job.",
            enabled=True,
        ),
        "dummy_timeout": JobProfile(
            profile_id="dummy_timeout",
            argv=[sys.executable, "-c", "import time; time.sleep(5)"],
            permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            timeout_seconds=1,
            allowed_artifact_globs=[],
            description="Deterministic timeout demo job.",
            enabled=True,
        ),
        "sleep_short": JobProfile(
            profile_id="sleep_short",
            argv=[sys.executable, "-c", "import time; time.sleep(0.1); print('slept')"],
            permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            timeout_seconds=10,
            allowed_artifact_globs=[],
            description="Short sleep demo job.",
            enabled=True,
        ),
        "disabled_demo": JobProfile(
            profile_id="disabled_demo",
            argv=[sys.executable, "-c", "print('disabled')"],
            permission_tier=PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB,
            timeout_seconds=10,
            allowed_artifact_globs=[],
            description="Disabled profile for policy tests.",
            enabled=False,
        ),
    }
)


def get_job_profile(profile_id: str) -> JobProfile | None:
    return BUILTIN_JOB_PROFILES.get(profile_id)


def list_job_profiles() -> dict[str, JobProfile]:
    return dict(BUILTIN_JOB_PROFILES)
