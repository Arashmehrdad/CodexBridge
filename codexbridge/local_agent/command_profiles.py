from __future__ import annotations

from types import MappingProxyType

from pydantic import BaseModel, Field

from .models import PermissionTier


class CommandProfile(BaseModel):
    command_id: str
    argv: list[str] = Field(min_length=1)
    permission_tier: PermissionTier
    default_timeout_seconds: int


BUILTIN_COMMAND_PROFILES: MappingProxyType[str, CommandProfile] = MappingProxyType(
    {
        "pytest": CommandProfile(
            command_id="pytest",
            argv=["python", "-m", "pytest", "-q"],
            permission_tier=PermissionTier.SAFE_LOCAL_TEST,
            default_timeout_seconds=120,
        ),
        "pip_check": CommandProfile(
            command_id="pip_check",
            argv=["python", "-m", "pip", "check"],
            permission_tier=PermissionTier.SAFE_LOCAL_TEST,
            default_timeout_seconds=60,
        ),
        "git_status": CommandProfile(
            command_id="git_status",
            argv=["git", "status", "--short"],
            permission_tier=PermissionTier.READ_ONLY,
            default_timeout_seconds=30,
        ),
    }
)


def get_command_profile(command_id: str) -> CommandProfile | None:
    return BUILTIN_COMMAND_PROFILES.get(command_id)


def list_command_profiles() -> dict[str, CommandProfile]:
    return dict(BUILTIN_COMMAND_PROFILES)
