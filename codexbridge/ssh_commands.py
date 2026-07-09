from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from .config import AppConfig, SSHCommandProfileConfig, SSHHostConfig

MAX_SSH_OUTPUT_BYTES = 100_000
MAX_REMOTE_ARGV_ITEMS = 64
MAX_REMOTE_ARG_BYTES = 512
MAX_REMOTE_COMMAND_BYTES = 4096

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ALIAS_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_CONTROL_OR_SHELL_META_RE = re.compile(r"[\x00-\x1f\x7f;&|<>`$()*?]")
_BLOCKED_REMOTE_LAUNCHERS = {
    "bash",
    "cmd",
    "cmd.exe",
    "dash",
    "fish",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "sh",
    "zsh",
}


def validate_ssh_host_id(host_id: str) -> str:
    value = str(host_id).strip()
    if not value or not _ID_RE.fullmatch(value):
        raise ValueError(f"Invalid SSH host_id: {host_id!r}")
    return value


def validate_ssh_alias(ssh_alias: str) -> str:
    value = str(ssh_alias).strip()
    if not value or not _ALIAS_RE.fullmatch(value):
        raise ValueError(
            "SSH alias must contain only letters, numbers, dots, underscores, or hyphens"
        )
    return value


def validate_ssh_command_profile(
    profile: SSHCommandProfileConfig,
) -> SSHCommandProfileConfig:
    command_id = str(profile.command_id).strip()
    if not command_id or not _ID_RE.fullmatch(command_id):
        raise ValueError(f"Invalid SSH command_id: {profile.command_id!r}")
    argv = [str(item) for item in profile.argv]
    if not argv:
        raise ValueError(
            f"SSH command profile '{command_id}' must have a non-empty argv"
        )
    if len(argv) > MAX_REMOTE_ARGV_ITEMS:
        raise ValueError(f"SSH command profile '{command_id}' has too many argv items")
    if Path(argv[0]).name.lower() in _BLOCKED_REMOTE_LAUNCHERS:
        raise ValueError(
            f"SSH command profile '{command_id}' may not launch a remote shell"
        )
    total_bytes = 0
    for item in argv:
        if not item:
            raise ValueError(
                f"SSH command profile '{command_id}' contains an empty argv item"
            )
        encoded_size = len(item.encode("utf-8"))
        total_bytes += encoded_size
        if encoded_size > MAX_REMOTE_ARG_BYTES:
            raise ValueError(
                f"SSH command profile '{command_id}' contains an oversized argv item"
            )
        if _CONTROL_OR_SHELL_META_RE.search(item):
            raise ValueError(
                f"SSH command profile '{command_id}' contains blocked shell syntax"
            )
    if total_bytes > MAX_REMOTE_COMMAND_BYTES:
        raise ValueError(f"SSH command profile '{command_id}' is too large")
    return profile


def resolve_ssh_host(config: AppConfig, host_id: str) -> SSHHostConfig:
    if not config.ssh.enabled:
        raise ValueError("SSH capability is disabled in config.yaml")
    normalized_host_id = validate_ssh_host_id(host_id)
    host = config.ssh.hosts.get(normalized_host_id)
    if host is None:
        raise ValueError(f"Unknown SSH host_id: {normalized_host_id}")
    validate_ssh_alias(host.ssh_alias)
    seen: set[str] = set()
    for profile in host.command_profiles:
        validate_ssh_command_profile(profile)
        if profile.command_id in seen:
            raise ValueError(
                f"Duplicate SSH command_id for host '{normalized_host_id}': "
                f"{profile.command_id}"
            )
        seen.add(profile.command_id)
    return host


def resolve_ssh_command_profile(
    config: AppConfig, host_id: str, command_id: str
) -> tuple[SSHHostConfig, SSHCommandProfileConfig]:
    host = resolve_ssh_host(config, host_id)
    normalized_command_id = str(command_id).strip()
    if not normalized_command_id or not _ID_RE.fullmatch(normalized_command_id):
        raise ValueError(f"Invalid SSH command_id: {command_id!r}")
    for profile in host.command_profiles:
        if profile.command_id == normalized_command_id:
            return host, validate_ssh_command_profile(profile)
    allowed = sorted(profile.command_id for profile in host.command_profiles)
    raise ValueError(
        f"Unknown SSH command_id for host '{host_id}': {normalized_command_id}. "
        f"Allowed: {allowed}"
    )


def resolve_ssh_executable(config: AppConfig) -> str:
    configured = str(config.ssh.executable).strip()
    if not configured:
        raise ValueError("SSH executable must not be empty")
    candidate = Path(configured)
    if candidate.is_absolute():
        if not candidate.is_file():
            raise ValueError(f"SSH executable does not exist: {configured}")
        return str(candidate)
    resolved = shutil.which(configured)
    if not resolved:
        raise ValueError(f"SSH executable was not found on PATH: {configured}")
    return resolved


def build_ssh_argv(
    config: AppConfig,
    host_id: str,
    profile: SSHCommandProfileConfig | None = None,
) -> list[str]:
    host = resolve_ssh_host(config, host_id)
    ssh_alias = validate_ssh_alias(host.ssh_alias)
    if profile is None:
        remote_command = "true"
    else:
        validate_ssh_command_profile(profile)
        remote_command = shlex.join([str(item) for item in profile.argv])
    executable = resolve_ssh_executable(config)
    return [
        executable,
        "-n",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "-o",
        "ControlPersist=no",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        f"ConnectTimeout={host.connect_timeout_seconds}",
        ssh_alias,
        remote_command,
    ]


def _truncate_output(stdout: str, stderr: str, limit: int) -> tuple[str, str, bool]:
    combined_size = len((stdout + stderr).encode("utf-8"))
    if combined_size <= limit:
        return stdout, stderr, False
    stdout_bytes = stdout.encode("utf-8")
    stderr_bytes = stderr.encode("utf-8")
    if len(stdout_bytes) >= limit:
        return stdout_bytes[:limit].decode("utf-8", errors="replace"), "", True
    remaining = limit - len(stdout_bytes)
    return (
        stdout,
        stderr_bytes[:remaining].decode("utf-8", errors="replace"),
        True,
    )


def _run_ssh_argv(
    argv: list[str], *, cwd: Path, timeout_seconds: int, output_limit: int
) -> dict:
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=os.environ.copy(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            stdin=subprocess.DEVNULL,
            shell=False,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        exit_code = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = (
            (exc.stdout or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            (exc.stderr or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        exit_code = 124
        timed_out = True
    except (OSError, PermissionError) as exc:
        stdout = ""
        stderr = str(exc)
        exit_code = 1
    stdout, stderr, output_truncated = _truncate_output(stdout, stderr, output_limit)
    duration = round(time.monotonic() - started, 3)
    return {
        "ok": exit_code == 0 and not timed_out,
        "argv": argv,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": output_truncated,
        "error": (
            f"Timed out after {timeout_seconds}s"
            if timed_out
            else (stderr.strip()[:300] if exit_code != 0 else "")
        ),
    }


def run_ssh_command(config: AppConfig, host_id: str, command_id: str) -> dict:
    host, profile = resolve_ssh_command_profile(config, host_id, command_id)
    argv = build_ssh_argv(config, host_id, profile)
    result = _run_ssh_argv(
        argv,
        cwd=config.config_dir,
        timeout_seconds=profile.timeout_seconds,
        output_limit=config.ssh.max_output_bytes,
    )
    result["argv"] = [*argv[:-1], "<configured command>"]
    result.update(
        {
            "host_id": validate_ssh_host_id(host_id),
            "ssh_alias": validate_ssh_alias(host.ssh_alias),
            "command_id": profile.command_id,
            "writes_remote": bool(profile.writes_remote),
            "remote_state_verified": False,
        }
    )
    return result


def ssh_host_health(config: AppConfig, host_id: str) -> dict:
    host = resolve_ssh_host(config, host_id)
    argv = build_ssh_argv(config, host_id)
    timeout = max(5, host.connect_timeout_seconds + 5)
    result = _run_ssh_argv(
        argv,
        cwd=config.config_dir,
        timeout_seconds=timeout,
        output_limit=config.ssh.max_output_bytes,
    )
    result["argv"] = [*argv[:-1], "<health check>"]
    result.update(
        {
            "host_id": validate_ssh_host_id(host_id),
            "ssh_alias": validate_ssh_alias(host.ssh_alias),
            "status": "ok" if result["ok"] else "unavailable",
        }
    )
    return result


def list_ssh_capabilities(config: AppConfig) -> dict:
    hosts: list[dict] = []
    for host_id in sorted(config.ssh.hosts):
        host = config.ssh.hosts[host_id]
        validate_ssh_host_id(host_id)
        validate_ssh_alias(host.ssh_alias)
        commands = []
        seen: set[str] = set()
        for profile in host.command_profiles:
            validate_ssh_command_profile(profile)
            if profile.command_id in seen:
                raise ValueError(
                    f"Duplicate SSH command_id for host '{host_id}': "
                    f"{profile.command_id}"
                )
            seen.add(profile.command_id)
            commands.append(
                {
                    "command_id": profile.command_id,
                    "description": profile.description,
                    "timeout_seconds": profile.timeout_seconds,
                    "writes_remote": profile.writes_remote,
                }
            )
        hosts.append(
            {
                "host_id": host_id,
                "ssh_alias": host.ssh_alias,
                "connect_timeout_seconds": host.connect_timeout_seconds,
                "commands": commands,
            }
        )
    return {
        "ok": True,
        "enabled": config.ssh.enabled,
        "hosts": hosts,
        "error": "",
    }
