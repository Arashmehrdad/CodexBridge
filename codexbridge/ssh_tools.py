from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .config import (
    AppConfig,
    SSHCommandProfileConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
)
from .safety import redact_secret_values, validate_repo_relative_path
from .ssh_commands import (
    _run_ssh_argv,
    build_ssh_argv,
    build_ssh_connection_options,
    build_ssh_destination,
    resolve_ssh_connection,
    resolve_ssh_command_profile,
    resolve_ssh_host,
    validate_ssh_alias,
    validate_ssh_command_profile,
    validate_ssh_host_id,
)

SSH_INSPECTIONS = (
    "host_info",
    "uptime",
    "cpu_info",
    "memory_status",
    "disk_status",
    "mounts",
    "process_status",
    "port_status",
    "network_status",
    "route_status",
    "failed_services",
    "service_status",
    "journal",
    "kernel_errors",
    "firewall_status",
    "docker_status",
    "docker_images",
    "docker_disk",
    "docker_compose_projects",
    "file_stat",
    "file_list",
    "file_read",
    "file_tail",
    "file_hash",
    "directory_size",
    "git_status",
    "git_log",
    "git_head",
    "git_diff_summary",
)

SSH_ACTIONS = (
    "exec_profile",
    "service_start",
    "service_stop",
    "service_restart",
    "service_reload",
    "service_enable",
    "service_disable",
    "docker_compose_pull",
    "docker_compose_build",
    "docker_compose_up",
    "docker_compose_down",
    "docker_compose_restart",
    "git_fetch",
    "git_pull_ff",
    "create_directory",
    "copy_path",
    "move_path",
    "remove_file",
    "remove_directory",
    "package_update",
    "package_upgrade",
    "package_install",
    "package_remove",
    "reboot",
    "shutdown",
    "run_argv",
)

HIGH_RISK_SSH_ACTIONS = {
    "service_stop": "allow_admin",
    "service_disable": "allow_admin",
    "docker_compose_down": "allow_admin",
    "move_path": "allow_admin",
    "remove_file": "allow_delete",
    "remove_directory": "allow_delete",
    "package_update": "allow_admin",
    "package_upgrade": "allow_admin",
    "package_install": "allow_admin",
    "package_remove": "allow_admin",
    "reboot": "allow_reboot",
    "shutdown": "allow_reboot",
    "run_argv": "allow_admin",
}

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+\-]{0,127}$")
_SAFE_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+:\-]{0,127}$")
_SAFE_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+\-]{0,127}$")
_CONTROL_OR_SHELL_META_RE = re.compile(r"[\x00-\x1f\x7f;&|<>`$(){}\[\]*?~]")
_BLOCKED_LAUNCHERS = {
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
_SECRET_PATH_PARTS = {
    ".env",
    ".npmrc",
    ".pypirc",
    "authorized_keys",
    "credentials",
    "gshadow",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "private_key",
    "secrets",
    "shadow",
}
_DEFAULT_DEPLOY_EXCLUDES = {
    ".git",
    ".github",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "runs",
    "venv",
}


@dataclass(frozen=True)
class SSHActionSpec:
    action: str
    remote_argv: list[str]
    timeout_seconds: int
    high_risk: bool = False
    writes_remote: bool = True
    description: str = ""


def _safe_name(value: str, field: str, *, required: bool = True) -> str:
    token = str(value or "").strip()
    if not token:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if not _SAFE_NAME_RE.fullmatch(token):
        raise ValueError(f"Invalid {field}: {value!r}")
    return token


def _safe_packages(packages: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for package in packages or []:
        value = str(package).strip()
        if not _SAFE_PACKAGE_RE.fullmatch(value):
            raise ValueError(f"Invalid package name: {package!r}")
        normalized.append(value)
    return normalized


def _validate_runtime_argv(
    host: SSHHostConfig, executable: str, args: list[str]
) -> list[str]:
    executable = str(executable or "").strip()
    if not _SAFE_EXECUTABLE_RE.fullmatch(executable):
        raise ValueError(f"Invalid remote executable: {executable!r}")
    if executable.lower() in _BLOCKED_LAUNCHERS:
        raise ValueError("Remote shell launchers are not supported")
    allowed = {item.lower() for item in host.allowed_executables}
    if executable.lower() not in allowed:
        raise ValueError(
            f"Remote executable {executable!r} is not allowlisted. Allowed: {sorted(allowed)}"
        )
    if len(args) > 64:
        raise ValueError("Remote argv has too many arguments")
    normalized = [executable]
    total_bytes = len(executable.encode("utf-8"))
    for item in args:
        value = str(item)
        if not value or _CONTROL_OR_SHELL_META_RE.search(value):
            raise ValueError(f"Remote argv contains blocked syntax: {value!r}")
        encoded_size = len(value.encode("utf-8"))
        if encoded_size > 512:
            raise ValueError("Remote argv item exceeds 512 bytes")
        total_bytes += encoded_size
        normalized.append(value)
    if total_bytes > 4096:
        raise ValueError("Remote argv exceeds 4096 bytes")
    return normalized


def _is_secret_path(path: str) -> bool:
    lowered = path.lower()
    parts = {part.lower() for part in PurePosixPath(lowered).parts}
    if parts & _SECRET_PATH_PARTS:
        return True
    basename = PurePosixPath(lowered).name
    return (
        basename.endswith((".pem", ".key", ".p12", ".pfx"))
        or "secret" in basename
        or "credential" in basename
        or "token" in basename
    )


def validate_remote_path(
    host: SSHHostConfig,
    path: str,
    *,
    allow_missing: bool = True,
    sensitive: bool = False,
) -> str:
    del allow_missing
    raw = str(path or "").strip()
    if not raw or not raw.startswith("/") or "\\" in raw:
        raise ValueError("Remote path must be an absolute POSIX path")
    if any(char.isspace() for char in raw) or _CONTROL_OR_SHELL_META_RE.search(raw):
        raise ValueError("Remote path contains unsupported characters")
    normalized = posixpath.normpath(raw)
    roots = [posixpath.normpath(root) for root in host.allowed_remote_roots]
    if not roots:
        raise ValueError("No allowed_remote_roots are configured for this SSH host")
    if not any(
        normalized == root or normalized.startswith(root.rstrip("/") + "/")
        for root in roots
    ):
        raise ValueError(
            f"Remote path is outside configured roots: {normalized}. Allowed roots: {roots}"
        )
    if not sensitive and _is_secret_path(normalized):
        raise ValueError(
            "Remote secret-like paths are not readable through CodexBridge"
        )
    return normalized


def _resolve_deployment(
    host: SSHHostConfig, deployment_id: str
) -> SSHDeploymentProfileConfig:
    deployment_id = _safe_name(deployment_id, "deployment_id")
    profile = host.deployment_profiles.get(deployment_id)
    if profile is None:
        raise ValueError(
            f"Unknown deployment_id: {deployment_id!r}. "
            f"Allowed: {sorted(host.deployment_profiles)}"
        )
    validate_remote_path(host, profile.remote_root, sensitive=True)
    return profile


def _require_confirmation(config: AppConfig, action: str, confirmation: str) -> None:
    gate = HIGH_RISK_SSH_ACTIONS.get(action)
    if gate is None:
        return
    if not bool(getattr(config.ssh, gate)):
        raise ValueError(f"SSH action {action!r} is disabled by config gate {gate}")
    if confirmation != config.ssh.confirmation_token:
        raise ValueError(
            f"SSH action {action!r} requires confirmation token "
            f"{config.ssh.confirmation_token!r}"
        )


def _with_sudo(host: SSHHostConfig, argv: list[str]) -> list[str]:
    return ["sudo", "-n", *argv] if host.use_sudo else argv


def _run_remote_argv(
    config: AppConfig,
    host_id: str,
    remote_argv: list[str],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    profile = SSHCommandProfileConfig(
        command_id="runtime",
        argv=remote_argv,
        timeout_seconds=timeout_seconds,
        writes_remote=False,
    )
    validate_ssh_command_profile(profile)
    argv = build_ssh_argv(config, host_id, profile)
    result = _run_ssh_argv(
        argv,
        cwd=config.config_dir,
        timeout_seconds=timeout_seconds,
        output_limit=config.ssh.max_output_bytes,
    )
    result["argv"] = [*argv[:-1], "<bounded remote argv>"]
    result["stdout"] = redact_secret_values(str(result.get("stdout", "")))
    result["stderr"] = redact_secret_values(str(result.get("stderr", "")))
    result["host_id"] = validate_ssh_host_id(host_id)
    return result


def build_ssh_inspection(
    config: AppConfig,
    host_id: str,
    operation: str,
    *,
    path: str = "",
    target: str = "",
    deployment_id: str = "",
    tail: int = 200,
) -> SSHActionSpec:
    host = resolve_ssh_host(config, host_id)
    operation = str(operation or "").strip()
    if operation not in SSH_INSPECTIONS:
        raise ValueError(
            f"Unsupported SSH inspection operation: {operation!r}. "
            f"Allowed: {list(SSH_INSPECTIONS)}"
        )
    if tail < 1 or tail > 5000:
        raise ValueError("tail must be between 1 and 5000")
    timeout = 60

    fixed = {
        "host_info": ["hostnamectl", "--static"],
        "uptime": ["uptime"],
        "cpu_info": ["lscpu"],
        "memory_status": ["free", "-h"],
        "disk_status": ["df", "-hT"],
        "mounts": ["findmnt"],
        "process_status": ["ps", "-eo", "pid,ppid,user,stat,etime,%cpu,%mem,args"],
        "port_status": ["ss", "-ltnup"],
        "network_status": ["ip", "-brief", "address"],
        "route_status": ["ip", "route"],
        "failed_services": ["systemctl", "--failed", "--no-pager"],
        "kernel_errors": ["dmesg", "--level=err,warn", "--nopager"],
        "firewall_status": ["ufw", "status", "verbose"],
        "docker_status": ["docker", "ps", "-a", "--no-trunc"],
        "docker_images": ["docker", "images", "--digests", "--no-trunc"],
        "docker_disk": ["docker", "system", "df"],
        "docker_compose_projects": ["docker", "compose", "ls"],
    }
    if operation in fixed:
        remote_argv = fixed[operation]
    elif operation == "service_status":
        remote_argv = [
            "systemctl",
            "status",
            "--no-pager",
            _safe_name(target, "target"),
        ]
    elif operation == "journal":
        remote_argv = ["journalctl", "-n", str(tail), "--no-pager"]
        if target:
            remote_argv[1:1] = ["-u", _safe_name(target, "target")]
    else:
        resolved_path = path
        if deployment_id:
            profile = _resolve_deployment(host, deployment_id)
            resolved_path = profile.remote_root
        resolved_path = validate_remote_path(host, resolved_path)
        if operation == "file_stat":
            remote_argv = ["stat", "--", resolved_path]
        elif operation == "file_list":
            remote_argv = [
                "find",
                resolved_path,
                "-mindepth",
                "1",
                "-maxdepth",
                "2",
                "-printf",
                "%y %s %TY-%Tm-%TdT%TH:%TM:%TS %p\\n",
            ]
        elif operation == "file_read":
            remote_argv = ["sed", "-n", f"1,{min(tail, 1000)}p", resolved_path]
        elif operation == "file_tail":
            remote_argv = ["tail", "-n", str(tail), "--", resolved_path]
        elif operation == "file_hash":
            remote_argv = ["sha256sum", "--", resolved_path]
        elif operation == "directory_size":
            remote_argv = ["du", "-sh", "--", resolved_path]
        elif operation == "git_status":
            remote_argv = ["git", "-C", resolved_path, "status", "--short", "--branch"]
        elif operation == "git_log":
            remote_argv = [
                "git",
                "-C",
                resolved_path,
                "log",
                "-n",
                str(min(tail, 200)),
                "--oneline",
                "--decorate",
            ]
        elif operation == "git_head":
            remote_argv = ["git", "-C", resolved_path, "rev-parse", "HEAD"]
        else:
            remote_argv = ["git", "-C", resolved_path, "diff", "--stat"]

    return SSHActionSpec(
        action=operation,
        remote_argv=remote_argv,
        timeout_seconds=timeout,
        high_risk=False,
        writes_remote=False,
        description="Read-only SSH inspection",
    )


def run_ssh_inspection(
    config: AppConfig, host_id: str, operation: str, **kwargs: Any
) -> dict:
    spec = build_ssh_inspection(config, host_id, operation, **kwargs)
    result = _run_remote_argv(
        config,
        host_id,
        spec.remote_argv,
        timeout_seconds=spec.timeout_seconds,
    )
    result.update(
        {
            "operation": operation,
            "writes_remote": False,
            "high_risk": False,
        }
    )
    return result


def build_ssh_action(
    config: AppConfig,
    host_id: str,
    action: str,
    *,
    target: str = "",
    source: str = "",
    destination: str = "",
    path: str = "",
    deployment_id: str = "",
    command_id: str = "",
    packages: list[str] | None = None,
    executable: str = "",
    args: list[str] | None = None,
    force: bool = False,
    confirmation: str = "",
) -> SSHActionSpec:
    host = resolve_ssh_host(config, host_id)
    action = str(action or "").strip()
    if action not in SSH_ACTIONS:
        raise ValueError(
            f"Unsupported SSH action: {action!r}. Allowed: {list(SSH_ACTIONS)}"
        )
    _require_confirmation(config, action, confirmation)
    high_risk = action in HIGH_RISK_SSH_ACTIONS
    timeout = 600

    service_actions = {
        "service_start": "start",
        "service_stop": "stop",
        "service_restart": "restart",
        "service_reload": "reload",
        "service_enable": "enable",
        "service_disable": "disable",
    }
    compose_actions = {
        "docker_compose_pull": ["pull"],
        "docker_compose_build": ["build"],
        "docker_compose_up": ["up", "-d", "--build"],
        "docker_compose_down": ["down", "--remove-orphans"],
        "docker_compose_restart": ["restart"],
    }

    if action == "exec_profile":
        _, profile = resolve_ssh_command_profile(config, host_id, command_id)
        return SSHActionSpec(
            action=action,
            remote_argv=list(profile.argv),
            timeout_seconds=profile.timeout_seconds,
            high_risk=False,
            writes_remote=profile.writes_remote,
            description=profile.description,
        )
    if action in service_actions:
        remote_argv = _with_sudo(
            host,
            ["systemctl", service_actions[action], _safe_name(target, "target")],
        )
    elif action in compose_actions:
        profile = _resolve_deployment(host, deployment_id)
        compose_file = profile.compose_file or "docker-compose.yml"
        compose_path = validate_remote_path(
            host, posixpath.join(profile.remote_root, compose_file)
        )
        remote_argv = [
            "docker",
            "compose",
            "--project-directory",
            profile.remote_root,
            "-f",
            compose_path,
            *compose_actions[action],
        ]
        remote_argv.extend(
            _safe_name(item, "service") for item in profile.compose_services
        )
        timeout = 1800
    elif action == "git_fetch":
        profile = _resolve_deployment(host, deployment_id)
        remote_argv = ["git", "-C", profile.remote_root, "fetch", "--all", "--prune"]
    elif action == "git_pull_ff":
        profile = _resolve_deployment(host, deployment_id)
        remote_argv = ["git", "-C", profile.remote_root, "pull", "--ff-only"]
    elif action == "create_directory":
        remote_argv = [
            "mkdir",
            "-p",
            "--",
            validate_remote_path(host, path, sensitive=True),
        ]
    elif action == "copy_path":
        remote_argv = [
            "cp",
            "-a",
            "--",
            validate_remote_path(host, source, sensitive=True),
            validate_remote_path(host, destination, sensitive=True),
        ]
    elif action == "move_path":
        remote_argv = [
            "mv",
            "--",
            validate_remote_path(host, source, sensitive=True),
            validate_remote_path(host, destination, sensitive=True),
        ]
    elif action == "remove_file":
        remote_argv = [
            "rm",
            "-f" if force else "-i",
            "--",
            validate_remote_path(host, path, sensitive=True),
        ]
    elif action == "remove_directory":
        remote_argv = [
            "rm",
            "-rf" if force else "-r",
            "--",
            validate_remote_path(host, path, sensitive=True),
        ]
    elif action == "package_update":
        remote_argv = _with_sudo(host, ["apt-get", "update"])
        timeout = 1800
    elif action == "package_upgrade":
        remote_argv = _with_sudo(host, ["apt-get", "upgrade", "-y"])
        timeout = 3600
    elif action in {"package_install", "package_remove"}:
        normalized_packages = _safe_packages(packages)
        if not normalized_packages:
            raise ValueError(f"{action} requires at least one package")
        subcommand = "install" if action == "package_install" else "remove"
        remote_argv = _with_sudo(
            host, ["apt-get", subcommand, "-y", *normalized_packages]
        )
        timeout = 3600
    elif action == "reboot":
        remote_argv = _with_sudo(host, ["systemctl", "reboot"])
    elif action == "shutdown":
        remote_argv = _with_sudo(host, ["systemctl", "poweroff"])
    else:
        remote_argv = _validate_runtime_argv(host, executable, list(args or []))
        timeout = 1800

    return SSHActionSpec(
        action=action,
        remote_argv=remote_argv,
        timeout_seconds=timeout,
        high_risk=high_risk,
        writes_remote=True,
        description="Bounded SSH administration action",
    )


def run_ssh_action(config: AppConfig, host_id: str, action: str, **kwargs: Any) -> dict:
    spec = build_ssh_action(config, host_id, action, **kwargs)
    result = _run_remote_argv(
        config,
        host_id,
        spec.remote_argv,
        timeout_seconds=spec.timeout_seconds,
    )
    result.update(
        {
            "action": action,
            "writes_remote": spec.writes_remote,
            "high_risk": spec.high_risk,
            "remote_state_verified": False,
        }
    )
    return result


def resolve_scp_executable(config: AppConfig) -> str:
    configured = str(config.ssh.scp_executable).strip()
    if not configured:
        raise ValueError("SCP executable must not be empty")
    candidate = Path(configured)
    if candidate.is_absolute():
        if not candidate.is_file():
            raise ValueError(f"SCP executable does not exist: {configured}")
        return str(candidate)
    resolved = shutil.which(configured)
    if not resolved:
        raise ValueError(f"SCP executable was not found on PATH: {configured}")
    return resolved


def _scp_base(
    config: AppConfig, host_id: str, *, recursive: bool
) -> tuple[list[str], SSHHostConfig, str]:
    host = resolve_ssh_host(config, host_id)
    connection = resolve_ssh_connection(host)
    strict_host_key_checking = (
        "accept-new" if connection.mode == "connection_file" else "yes"
    )
    argv = [
        resolve_scp_executable(config),
        "-B",
        "-p",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        f"StrictHostKeyChecking={strict_host_key_checking}",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        f"ConnectTimeout={host.connect_timeout_seconds}",
    ]
    argv.extend(build_ssh_connection_options(host, scp=True, connection=connection))
    if recursive:
        argv.append("-r")
    return argv, host, connection.destination


def _run_local_argv(
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
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        exit_code = 124
        timed_out = True
    except (OSError, PermissionError) as exc:
        stdout = ""
        stderr = str(exc)
        exit_code = 1
    stdout = redact_secret_values(str(stdout))
    stderr = redact_secret_values(str(stderr))
    combined = (stdout + stderr).encode("utf-8")
    truncated = len(combined) > output_limit
    if truncated:
        stdout_bytes = stdout.encode("utf-8")
        if len(stdout_bytes) >= output_limit:
            stdout = stdout_bytes[:output_limit].decode("utf-8", errors="replace")
            stderr = ""
        else:
            remaining = output_limit - len(stdout_bytes)
            stderr = stderr.encode("utf-8")[:remaining].decode(
                "utf-8", errors="replace"
            )
    return {
        "ok": exit_code == 0 and not timed_out,
        "argv": argv,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": truncated,
        "error": (
            f"Timed out after {timeout_seconds}s"
            if timed_out
            else (stderr.strip()[:300] if exit_code != 0 else "")
        ),
    }


def run_ssh_transfer(
    config: AppConfig,
    host_id: str,
    direction: str,
    *,
    repo_root: Path,
    local_path: str,
    remote_path: str,
    run_dir: Path,
    recursive: bool = False,
    overwrite: bool = False,
    confirmation: str = "",
) -> dict:
    if not config.ssh.allow_transfer:
        raise ValueError("SSH transfer capability is disabled by allow_transfer")
    direction = str(direction or "").strip().lower()
    if direction not in {"upload", "download"}:
        raise ValueError("direction must be 'upload' or 'download'")
    if overwrite and confirmation != config.ssh.confirmation_token:
        raise ValueError(
            f"Overwrite transfer requires confirmation token {config.ssh.confirmation_token!r}"
        )
    argv, host, destination_host = _scp_base(
        config, host_id, recursive=recursive
    )
    remote = validate_remote_path(host, remote_path, sensitive=True)
    if direction == "upload":
        local = validate_repo_relative_path(repo_root, local_path)
        if not local.exists():
            raise ValueError(f"Local upload path does not exist: {local_path}")
        if local.is_dir() and not recursive:
            raise ValueError("Directory upload requires recursive=true")
        if _is_secret_path(local.as_posix()):
            raise ValueError(
                "Secret-like local files cannot be uploaded through CodexBridge"
            )
        argv.extend([str(local), f"{destination_host}:{remote}"])
        cwd = repo_root
        destination = remote
    else:
        downloads = run_dir / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        requested_name = (
            Path(local_path).name if local_path else PurePosixPath(remote).name
        )
        if not requested_name or requested_name in {".", ".."}:
            requested_name = "downloaded-artifact"
        local = downloads / requested_name
        if local.exists() and not overwrite:
            raise ValueError(f"Download destination already exists: {local.name}")
        argv.extend([f"{destination_host}:{remote}", str(local)])
        cwd = run_dir
        destination = str(local)
    result = _run_local_argv(
        argv,
        cwd=cwd,
        timeout_seconds=config.ssh.transfer_timeout_seconds,
        output_limit=config.ssh.max_output_bytes,
    )
    result.update(
        {
            "host_id": host_id,
            "direction": direction,
            "remote_path": remote,
            "local_path": str(local),
            "destination": destination,
            "writes_remote": direction == "upload",
            "remote_state_verified": False,
        }
    )
    result["argv"] = [argv[0], "<bounded scp arguments>"]
    return result


def _archive_filter(excludes: set[str]):
    def apply(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = set(PurePosixPath(info.name).parts)
        if parts & excludes or _is_secret_path(info.name):
            return None
        return info

    return apply


def run_ssh_deployment(
    config: AppConfig,
    host_id: str,
    deployment_id: str,
    *,
    repo_root: Path,
    run_dir: Path,
    run_id: str,
    confirmation: str,
) -> dict:
    if not config.ssh.allow_deploy:
        raise ValueError("SSH deployment capability is disabled by allow_deploy")
    if confirmation != config.ssh.confirmation_token:
        raise ValueError(
            f"SSH deployment requires confirmation token {config.ssh.confirmation_token!r}"
        )
    host = resolve_ssh_host(config, host_id)
    profile = _resolve_deployment(host, deployment_id)
    source_root = validate_repo_relative_path(repo_root, profile.local_subdir)
    if not source_root.is_dir():
        raise ValueError("Deployment local_subdir must resolve to a directory")

    archive_path = run_dir / f"{deployment_id}-{run_id}.tar.gz"
    excludes = set(_DEFAULT_DEPLOY_EXCLUDES)
    excludes.update(profile.exclude_paths)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(
            source_root,
            arcname=".",
            recursive=True,
            filter=_archive_filter(excludes),
        )
    if archive_path.stat().st_size > config.ssh.max_transfer_bytes:
        archive_path.unlink(missing_ok=True)
        raise ValueError("Deployment archive exceeds max_transfer_bytes")

    release_root = validate_remote_path(
        host,
        posixpath.join(profile.remote_root, "releases", run_id),
        sensitive=True,
    )
    current_link = validate_remote_path(
        host, posixpath.join(profile.remote_root, "current"), sensitive=True
    )
    remote_archive = validate_remote_path(
        host,
        posixpath.join(profile.remote_root, ".codexbridge", f"{run_id}.tar.gz"),
        sensitive=True,
    )
    steps: list[dict[str, Any]] = []

    def remote_step(name: str, argv: list[str], timeout: int = 600) -> bool:
        result = _run_remote_argv(config, host_id, argv, timeout_seconds=timeout)
        result["step"] = name
        steps.append(result)
        return bool(result.get("ok"))

    if not remote_step(
        "prepare",
        ["mkdir", "-p", "--", release_root, posixpath.dirname(remote_archive)],
    ):
        return _deployment_result(host_id, deployment_id, archive_path, steps)

    scp_result = _scp_base(config, host_id, recursive=False)
    if len(scp_result) == 2:  # Compatibility for existing test/plugin mocks.
        scp_argv, _ = scp_result
        destination_host = build_ssh_destination(host)
    else:
        scp_argv, _, destination_host = scp_result
    scp_argv.extend(
        [str(archive_path), f"{destination_host}:{remote_archive}"]
    )
    upload = _run_local_argv(
        scp_argv,
        cwd=run_dir,
        timeout_seconds=config.ssh.transfer_timeout_seconds,
        output_limit=config.ssh.max_output_bytes,
    )
    upload["step"] = "upload"
    upload["argv"] = [scp_argv[0], "<deployment archive>"]
    steps.append(upload)
    if not upload.get("ok"):
        return _deployment_result(host_id, deployment_id, archive_path, steps)

    if not remote_step(
        "extract",
        ["tar", "-xzf", remote_archive, "-C", release_root],
        timeout=1800,
    ):
        return _deployment_result(host_id, deployment_id, archive_path, steps)

    for remote_source, release_target in profile.shared_files.items():
        source_path = validate_remote_path(host, remote_source, sensitive=True)
        target_path = validate_remote_path(
            host,
            posixpath.join(release_root, release_target),
            sensitive=True,
        )
        if not remote_step(
            f"verify_shared:{release_target}",
            ["test", "-f", source_path],
        ):
            return _deployment_result(host_id, deployment_id, archive_path, steps)
        if not remote_step(
            f"link_shared:{release_target}",
            ["ln", "-sfn", source_path, target_path],
        ):
            return _deployment_result(host_id, deployment_id, archive_path, steps)

    if profile.compose_file:
        compose_path = validate_remote_path(
            host, posixpath.join(release_root, profile.compose_file)
        )
        compose_argv = [
            "docker",
            "compose",
            "--project-directory",
            release_root,
        ]
        if profile.compose_project_name:
            compose_argv.extend(
                [
                    "--project-name",
                    _safe_name(profile.compose_project_name, "compose_project_name"),
                ]
            )
        compose_argv.extend(["-f", compose_path])
        if profile.env_file:
            compose_argv.extend(
                [
                    "--env-file",
                    validate_remote_path(host, profile.env_file, sensitive=True),
                ]
            )
        compose_argv.extend(["up", "-d"])
        if profile.compose_build:
            compose_argv.append("--build")
        compose_argv.extend(
            _safe_name(item, "service") for item in profile.compose_services
        )
        if not remote_step("compose_up", compose_argv, timeout=3600):
            return _deployment_result(host_id, deployment_id, archive_path, steps)

    if profile.service_name:
        if not remote_step(
            "service_restart",
            _with_sudo(
                host,
                [
                    "systemctl",
                    "restart",
                    _safe_name(profile.service_name, "service_name"),
                ],
            ),
        ):
            return _deployment_result(host_id, deployment_id, archive_path, steps)

    if profile.health_command_id:
        _, health_profile = resolve_ssh_command_profile(
            config, host_id, profile.health_command_id
        )
        if not remote_step(
            "health_check",
            list(health_profile.argv),
            timeout=health_profile.timeout_seconds,
        ):
            return _deployment_result(host_id, deployment_id, archive_path, steps)

    if not remote_step("activate", ["ln", "-sfn", release_root, current_link]):
        return _deployment_result(host_id, deployment_id, archive_path, steps)

    cleanup = _run_remote_argv(
        config,
        host_id,
        ["rm", "-f", "--", remote_archive],
        timeout_seconds=600,
    )
    cleanup["step"] = "cleanup_archive"
    cleanup["non_fatal"] = True
    steps.append(cleanup)
    return _deployment_result(host_id, deployment_id, archive_path, steps)


def _deployment_result(
    host_id: str,
    deployment_id: str,
    archive_path: Path,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    required_steps = [step for step in steps if not step.get("non_fatal")]
    ok = bool(required_steps) and all(bool(step.get("ok")) for step in required_steps)
    failed_step = next(
        (str(step.get("step")) for step in required_steps if not step.get("ok")),
        "",
    )
    return {
        "ok": ok,
        "host_id": host_id,
        "deployment_id": deployment_id,
        "archive_path": str(archive_path),
        "steps": steps,
        "writes_remote": True,
        "remote_state_verified": False,
        "exit_code": 0 if ok else 1,
        "timed_out": any(bool(step.get("timed_out")) for step in steps),
        "output_truncated": any(bool(step.get("output_truncated")) for step in steps),
        "stdout": "\n".join(
            str(step.get("stdout", "")) for step in steps if step.get("stdout")
        ),
        "stderr": "\n".join(
            str(step.get("stderr", "")) for step in steps if step.get("stderr")
        ),
        "error": f"Deployment failed at step: {failed_step}" if failed_step else "",
    }


def enrich_ssh_capabilities(
    config: AppConfig, result: dict[str, Any]
) -> dict[str, Any]:
    result = dict(result)
    result.update(
        {
            "read_only_operations": list(SSH_INSPECTIONS),
            "actions": list(SSH_ACTIONS),
            "high_risk_actions": dict(HIGH_RISK_SSH_ACTIONS),
            "gates": {
                "allow_transfer": config.ssh.allow_transfer,
                "allow_deploy": config.ssh.allow_deploy,
                "allow_admin": config.ssh.allow_admin,
                "allow_delete": config.ssh.allow_delete,
                "allow_reboot": config.ssh.allow_reboot,
            },
            "confirmation_token": config.ssh.confirmation_token,
            "arbitrary_shell_supported": False,
        }
    )
    hosts_by_id = {host["host_id"]: host for host in result.get("hosts", [])}
    for host_id, host_config in config.ssh.hosts.items():
        host = hosts_by_id.get(host_id)
        if host is None:
            continue
        host["allowed_remote_roots"] = list(host_config.allowed_remote_roots)
        host["allowed_executables"] = list(host_config.allowed_executables)
        host["use_sudo"] = host_config.use_sudo
        host["deployments"] = [
            {
                "deployment_id": deployment_id,
                "repo_name": profile.repo_name,
                "remote_root": profile.remote_root,
                "compose_file": profile.compose_file,
                "service_name": profile.service_name,
                "health_command_id": profile.health_command_id,
            }
            for deployment_id, profile in sorted(
                host_config.deployment_profiles.items()
            )
        ]
    return result
