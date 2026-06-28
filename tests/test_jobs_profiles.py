from __future__ import annotations

from codexbridge.jobs.job_profiles import get_job_profile, list_job_profiles
from codexbridge.local_agent.models import PermissionTier


def test_job_profile_registry_returns_builtins() -> None:
    profiles = list_job_profiles()

    assert {
        "dummy_success",
        "dummy_failure",
        "dummy_timeout",
        "sleep_short",
        "disabled_demo",
    } <= set(profiles)
    assert (
        profiles["dummy_success"].permission_tier
        == PermissionTier.LONG_RUNNING_NON_DESTRUCTIVE_JOB
    )
    assert profiles["dummy_success"].argv
    assert profiles["dummy_success"].enabled is True
    assert profiles["disabled_demo"].enabled is False


def test_unknown_job_profile_is_missing() -> None:
    assert get_job_profile("python -c import os") is None
