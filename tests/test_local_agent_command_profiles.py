from __future__ import annotations

from codexbridge.local_agent.command_profiles import get_command_profile, list_command_profiles
from codexbridge.local_agent.models import PermissionTier


def test_builtin_command_profiles_are_allowlisted() -> None:
    profiles = list_command_profiles()

    assert set(profiles) == {"pytest", "pip_check", "git_status"}
    assert profiles["pytest"].argv == ["python", "-m", "pytest", "-q"]
    assert profiles["pytest"].permission_tier == PermissionTier.SAFE_LOCAL_TEST
    assert profiles["pytest"].default_timeout_seconds == 120
    assert profiles["pip_check"].argv == ["python", "-m", "pip", "check"]
    assert profiles["pip_check"].permission_tier == PermissionTier.SAFE_LOCAL_TEST
    assert profiles["pip_check"].default_timeout_seconds == 60
    assert profiles["git_status"].argv == ["git", "status", "--short"]
    assert profiles["git_status"].permission_tier == PermissionTier.READ_ONLY
    assert profiles["git_status"].default_timeout_seconds == 30


def test_unknown_profile_is_not_available() -> None:
    assert get_command_profile("python -c import os") is None
