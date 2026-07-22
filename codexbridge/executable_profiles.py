from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Mapping, Sequence

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


def _is_absolute_path(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _resolve_working_directory(
    profile: ExecutableProfileConfig,
    requested_working_directory: str,
    *,
    default_working_directory: str = "",
) -> str:
    requested = str(requested_working_directory or "")
    if profile.working_directory_policy == "service_default":
        if requested:
            raise ValueError("Executable profile does not accept a working directory")
        selected = str(default_working_directory or "")
        if not selected:
            return ""
        if not _is_absolute_path(selected):
            raise ValueError("Executable default working directory must be absolute")
        path = Path(selected)
        if not path.exists() or not path.is_dir() or path.is_symlink():
            raise ValueError("Executable default working directory must be an existing directory")
        return str(path.resolve())
    if profile.working_directory_policy == "fixed":
        if requested and Path(requested) != Path(profile.fixed_working_directory):
            raise ValueError("Executable profile requires its fixed working directory")
        selected = profile.fixed_working_directory
    else:
        if not requested:
            raise ValueError("Arbitrary working-directory policy requires a directory")
        selected = requested
    if not _is_absolute_path(selected):
        raise ValueError("Executable working directory must be absolute")
    path = Path(selected)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise ValueError("Executable working directory must be an existing directory")
    return str(path.resolve())


def _resolve_environment(
    profile: ExecutableProfileConfig,
    requested_environment: Mapping[str, str] | None,
) -> dict[str, str]:
    requested = dict(requested_environment or {})
    if profile.environment_policy == "inherit":
        if requested:
            raise ValueError("Executable profile does not accept environment overrides")
        return {}
    if profile.environment_policy == "fixed":
        if requested and requested != profile.fixed_environment:
            raise ValueError("Executable profile requires its fixed environment")
        return dict(profile.fixed_environment)
    normalized: dict[str, str] = {}
    for name, value in requested.items():
        key = str(name)
        if not key or "=" in key or "\x00" in key:
            raise ValueError("Executable environment names must be non-empty and valid")
        text = str(value)
        if "\x00" in text:
            raise ValueError("Executable environment values must not contain NUL")
        normalized[key] = text
    return normalized


def build_local_executable_run_request(
    config: AppConfig,
    profile_id: str,
    argv: Sequence[str],
    *,
    working_directory: str = "",
    environment: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
    stdin_bytes: bytes | None = None,
    timeout_seconds: int | None = None,
    default_working_directory: str = "",
) -> dict[str, object]:
    profile, executable_identity = resolve_verified_local_executable(config, profile_id)
    if not profile.unrestricted_argv:
        raise ValueError(f"Executable profile '{profile_id}' does not allow arbitrary argv")
    exact_argv = [str(argument) for argument in argv]
    if any("\x00" in argument for argument in exact_argv):
        raise ValueError("Executable argv values must not contain NUL")
    if stdin_text is not None and stdin_bytes is not None:
        raise ValueError("Specify either stdin_text or stdin_bytes, not both")
    selected_stdin_text = stdin_text
    selected_stdin_bytes = stdin_bytes
    if stdin_text is not None:
        if profile.stdin_mode == "bytes":
            selected_stdin_text = None
            selected_stdin_bytes = stdin_text.encode("utf-8")
        elif profile.stdin_mode != "text":
            raise ValueError("Executable profile is not configured for text stdin")
    if stdin_bytes is not None and profile.stdin_mode != "bytes":
        raise ValueError("Executable profile is not configured for binary stdin")
    selected_timeout = profile.timeout_seconds if timeout_seconds is None else timeout_seconds
    if selected_timeout is None and not profile.allow_no_timeout:
        raise ValueError("Executable profile does not allow no-timeout runs")
    if selected_timeout is not None:
        selected_timeout = int(selected_timeout)
        if selected_timeout < 1 or selected_timeout > 604800:
            raise ValueError("Executable timeout_seconds must be between 1 and 604800")
    return {
        "profile_id": profile.profile_id,
        "executable_identity": executable_identity,
        "argv": exact_argv,
        "working_directory": _resolve_working_directory(
            profile,
            working_directory,
            default_working_directory=default_working_directory,
        ),
        "environment": _resolve_environment(profile, environment),
        "inherit_environment": profile.environment_policy in {"inherit", "arbitrary"},
        "stdin_mode": profile.stdin_mode,
        "stdin_text": selected_stdin_text,
        "stdin_base64": (
            b64encode(selected_stdin_bytes).decode("ascii")
            if selected_stdin_bytes is not None
            else ""
        ),
        "stdout_mode": profile.stdout_mode,
        "stderr_mode": profile.stderr_mode,
        "timeout_seconds": selected_timeout,
        "cancellation_policy": profile.cancellation_policy,
        "public_output_max_bytes": profile.public_output_max_bytes,
        "preserve_protected_artifacts": profile.preserve_protected_artifacts,
        "autonomy_profile": profile.autonomy_profile,
        "target": profile.target,
    }
