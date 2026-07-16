from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .config import AppConfig, ExecutableProfileConfig


def resolve_executable_profile(
    config: AppConfig,
    profile_id: str,
    *,
    require_enabled: bool = True,
    require_local: bool = True,
) -> ExecutableProfileConfig:
    normalized_profile_id = str(profile_id or "").strip()
    if not normalized_profile_id:
        raise ValueError("Executable profile_id must not be empty")
    profile = config.executable_profiles.get(normalized_profile_id)
    if profile is None:
        raise ValueError(f"Unknown executable profile: {normalized_profile_id}")
    if require_enabled and not profile.enabled:
        raise ValueError(f"Executable profile '{normalized_profile_id}' is disabled")
    if require_local and profile.target != "local":
        raise ValueError(
            f"Executable profile '{normalized_profile_id}' is not a local target"
        )
    return profile


def inspect_executable_identity(profile: ExecutableProfileConfig) -> dict[str, object]:
    executable_path = Path(profile.executable_path)
    if not executable_path.exists():
        raise ValueError(
            f"Configured executable does not exist: {profile.executable_path}"
        )
    if not executable_path.is_file() or executable_path.is_symlink():
        raise ValueError(
            f"Configured executable must be a regular non-symlink file: "
            f"{profile.executable_path}"
        )

    digest = sha256()
    size_bytes = 0
    with executable_path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
    observed_sha256 = digest.hexdigest()
    if profile.expected_sha256 and observed_sha256 != profile.expected_sha256:
        raise ValueError(
            f"Executable SHA-256 mismatch for profile '{profile.profile_id}'"
        )

    stat = executable_path.stat()
    return {
        "profile_id": profile.profile_id,
        "executable_path": str(executable_path.resolve()),
        "observed_sha256": observed_sha256,
        "expected_sha256": profile.expected_sha256,
        "expected_signer": profile.expected_signer,
        "expected_version": profile.expected_version,
        "size_bytes": size_bytes,
        "modified_time_ns": stat.st_mtime_ns,
        "target": profile.target,
    }


def resolve_verified_local_executable(
    config: AppConfig,
    profile_id: str,
) -> tuple[ExecutableProfileConfig, dict[str, object]]:
    profile = resolve_executable_profile(config, profile_id)
    return profile, inspect_executable_identity(profile)
