from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig, DockerExecProfileConfig, RepoConfig
from .safety import redact_secret_values, validate_repo_relative_path


READ_ONLY_DOCKER_OPERATIONS = (
    "engine_version",
    "engine_info",
    "containers",
    "images",
    "networks",
    "volumes",
    "disk_usage",
    "compose_config",
    "compose_ps",
    "compose_images",
    "compose_logs",
    "container_details",
    "image_details",
    "network_details",
    "volume_details",
)

DOCKER_ACTIONS = (
    "compose_build",
    "compose_up",
    "compose_down",
    "compose_start",
    "compose_stop",
    "compose_restart",
    "compose_pause",
    "compose_unpause",
    "compose_kill",
    "compose_pull",
    "compose_exec",
    "container_exec",
    "image_build",
    "image_pull",
    "image_tag",
    "container_start",
    "container_stop",
    "container_restart",
    "container_pause",
    "container_unpause",
    "container_kill",
    "network_create",
    "volume_create",
    "compose_down_volumes",
    "compose_rm",
    "image_push",
    "container_remove",
    "image_remove",
    "network_remove",
    "volume_remove",
    "builder_prune",
    "container_prune",
    "image_prune",
    "network_prune",
    "volume_prune",
    "system_prune",
    "system_prune_volumes",
)

HIGH_RISK_ACTIONS = {
    "compose_down_volumes": "allow_compose_down_volumes",
    "compose_rm": "allow_remove",
    "image_push": "allow_push",
    "container_remove": "allow_remove",
    "image_remove": "allow_remove",
    "network_remove": "allow_remove",
    "volume_remove": "allow_remove",
    "builder_prune": "allow_prune",
    "container_prune": "allow_prune",
    "image_prune": "allow_prune",
    "network_prune": "allow_prune",
    "volume_prune": "allow_prune",
    "system_prune": "allow_prune",
    "system_prune_volumes": "allow_prune",
}

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+\-]{0,255}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_COMPOSE_CANDIDATES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)


@dataclass(frozen=True)
class DockerCommandSpec:
    action: str
    argv: list[str]
    timeout_seconds: int
    high_risk: bool = False
    writes_files: bool = False
    description: str = ""


def _require_enabled(config: AppConfig) -> None:
    if not config.docker.enabled:
        raise ValueError("Docker capability is disabled in config")


def _safe_token(value: str, field: str, *, required: bool = True) -> str:
    token = str(value or "").strip()
    if not token:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if not _SAFE_TOKEN_RE.fullmatch(token):
        raise ValueError(f"Invalid {field}: {value!r}")
    return token


def _safe_name(value: str, field: str, *, required: bool = True) -> str:
    token = str(value or "").strip()
    if not token:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if not _SAFE_NAME_RE.fullmatch(token):
        raise ValueError(f"Invalid {field}: {value!r}")
    return token


def _safe_services(services: list[str] | None) -> list[str]:
    return [_safe_name(service, "service") for service in (services or [])]


def _resolve_compose_files(repo_root: Path, repo_config: RepoConfig) -> list[str]:
    requested = list(repo_config.docker_compose_files or [])
    if not requested:
        requested = [name for name in _COMPOSE_CANDIDATES if (repo_root / name).is_file()]
    if not requested:
        raise ValueError("No repository Docker Compose file was found or configured")

    normalized: list[str] = []
    for relative in requested:
        candidate = validate_repo_relative_path(repo_root, relative)
        if not candidate.is_file() or candidate.suffix.lower() not in {".yml", ".yaml"}:
            raise ValueError(f"Compose file must be an existing repository YAML file: {relative}")
        normalized.append(candidate.relative_to(repo_root.resolve()).as_posix())
    return normalized


def _compose_prefix(config: AppConfig, repo_root: Path, repo_config: RepoConfig) -> list[str]:
    argv = [config.docker.executable, "compose"]
    for compose_file in _resolve_compose_files(repo_root, repo_config):
        argv.extend(["--file", compose_file])
    project_name = str(repo_config.docker_project_name or "").strip()
    if project_name:
        argv.extend(["--project-name", _safe_name(project_name, "docker_project_name")])
    return argv


def _exec_profile(repo_config: RepoConfig, command_id: str) -> DockerExecProfileConfig:
    command_id = str(command_id or "").strip()
    if not _COMMAND_ID_RE.fullmatch(command_id):
        raise ValueError(f"Invalid Docker exec command_id: {command_id!r}")
    for profile in repo_config.docker_exec_profiles:
        if profile.command_id == command_id:
            return profile
    allowed = sorted(profile.command_id for profile in repo_config.docker_exec_profiles)
    raise ValueError(f"Unknown Docker exec command_id: {command_id!r}. Allowed: {allowed}")


def _require_high_risk_approval(config: AppConfig, action: str, confirmation: str) -> None:
    gate = HIGH_RISK_ACTIONS.get(action)
    if gate is None:
        return
    if not bool(getattr(config.docker, gate)):
        raise ValueError(f"Docker action {action!r} is disabled by config gate {gate}")
    if confirmation != config.docker.confirmation_token:
        raise ValueError(
            f"Docker action {action!r} requires confirmation token "
            f"{config.docker.confirmation_token!r}"
        )


def _validate_repo_directory(repo_root: Path, value: str, field: str) -> str:
    raw = str(value or ".").strip() or "."
    candidate = validate_repo_relative_path(repo_root, raw)
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(f"{field} must be an existing repository directory")
    return candidate.relative_to(repo_root.resolve()).as_posix() or "."


def _validate_repo_file(repo_root: Path, value: str, field: str) -> str:
    candidate = validate_repo_relative_path(repo_root, value)
    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"{field} must be an existing repository file")
    return candidate.relative_to(repo_root.resolve()).as_posix()


def build_docker_inspection(
    config: AppConfig,
    repo_root: Path,
    repo_config: RepoConfig,
    operation: str,
    *,
    target: str = "",
    service: str = "",
    tail: int = 200,
) -> DockerCommandSpec:
    _require_enabled(config)
    operation = str(operation or "").strip()
    if operation not in READ_ONLY_DOCKER_OPERATIONS:
        raise ValueError(
            f"Unsupported Docker inspection operation: {operation!r}. "
            f"Allowed: {list(READ_ONLY_DOCKER_OPERATIONS)}"
        )
    docker = config.docker.executable
    timeout = min(config.docker.default_timeout_seconds, 300)

    if operation == "engine_version":
        argv = [docker, "version"]
    elif operation == "engine_info":
        argv = [docker, "info"]
    elif operation == "containers":
        argv = [docker, "container", "ls", "--all", "--no-trunc"]
    elif operation == "images":
        argv = [docker, "image", "ls", "--digests", "--no-trunc"]
    elif operation == "networks":
        argv = [docker, "network", "ls"]
    elif operation == "volumes":
        argv = [docker, "volume", "ls"]
    elif operation == "disk_usage":
        argv = [docker, "system", "df", "--verbose"]
    elif operation == "compose_config":
        argv = _compose_prefix(config, repo_root, repo_config) + ["config"]
    elif operation == "compose_ps":
        argv = _compose_prefix(config, repo_root, repo_config) + ["ps", "--all"]
    elif operation == "compose_images":
        argv = _compose_prefix(config, repo_root, repo_config) + ["images"]
    elif operation == "compose_logs":
        if tail < 1 or tail > 5000:
            raise ValueError("tail must be between 1 and 5000")
        argv = _compose_prefix(config, repo_root, repo_config) + [
            "logs",
            "--no-color",
            "--tail",
            str(tail),
        ]
        if service:
            argv.append(_safe_name(service, "service"))
    elif operation == "container_details":
        argv = [
            docker,
            "container",
            "inspect",
            "--format",
            "{{json (dict \"Id\" .Id \"Name\" .Name \"Image\" .Image \"State\" .State \"HostConfig\" .HostConfig)}}",
            _safe_token(target, "target"),
        ]
    elif operation == "image_details":
        argv = [
            docker,
            "image",
            "inspect",
            "--format",
            "{{json (dict \"Id\" .Id \"RepoTags\" .RepoTags \"RepoDigests\" .RepoDigests \"Created\" .Created \"Size\" .Size \"Architecture\" .Architecture \"Os\" .Os)}}",
            _safe_token(target, "target"),
        ]
    elif operation == "network_details":
        argv = [
            docker,
            "network",
            "inspect",
            "--format",
            "{{json (dict \"Name\" .Name \"Id\" .Id \"Driver\" .Driver \"Scope\" .Scope \"Internal\" .Internal \"IPAM\" .IPAM)}}",
            _safe_token(target, "target"),
        ]
    else:
        argv = [
            docker,
            "volume",
            "inspect",
            "--format",
            "{{json (dict \"Name\" .Name \"Driver\" .Driver \"Mountpoint\" .Mountpoint \"Scope\" .Scope)}}",
            _safe_token(target, "target"),
        ]

    return DockerCommandSpec(
        action=operation,
        argv=argv,
        timeout_seconds=timeout,
        description="Read-only Docker inspection",
    )


def build_docker_action(
    config: AppConfig,
    repo_root: Path,
    repo_config: RepoConfig,
    action: str,
    *,
    target: str = "",
    destination: str = "",
    services: list[str] | None = None,
    command_id: str = "",
    context: str = ".",
    dockerfile: str = "",
    build: bool = False,
    force: bool = False,
    confirmation: str = "",
) -> DockerCommandSpec:
    _require_enabled(config)
    action = str(action or "").strip()
    if action not in DOCKER_ACTIONS:
        raise ValueError(f"Unsupported Docker action: {action!r}. Allowed: {list(DOCKER_ACTIONS)}")
    _require_high_risk_approval(config, action, confirmation)

    docker = config.docker.executable
    safe_services = _safe_services(services)
    high_risk = action in HIGH_RISK_ACTIONS
    timeout = config.docker.default_timeout_seconds
    writes_files = False

    compose_simple = {
        "compose_build": "build",
        "compose_start": "start",
        "compose_stop": "stop",
        "compose_restart": "restart",
        "compose_pause": "pause",
        "compose_unpause": "unpause",
        "compose_kill": "kill",
        "compose_pull": "pull",
    }
    container_simple = {
        "container_start": "start",
        "container_stop": "stop",
        "container_restart": "restart",
        "container_pause": "pause",
        "container_unpause": "unpause",
        "container_kill": "kill",
    }

    if action in compose_simple:
        argv = _compose_prefix(config, repo_root, repo_config) + [compose_simple[action]] + safe_services
        if action in {"compose_build", "compose_pull"}:
            timeout = max(timeout, 1800)
    elif action == "compose_up":
        argv = _compose_prefix(config, repo_root, repo_config) + ["up", "--detach"]
        if build:
            argv.append("--build")
        argv.extend(safe_services)
        timeout = max(timeout, 1800)
    elif action == "compose_down":
        argv = _compose_prefix(config, repo_root, repo_config) + ["down", "--remove-orphans"]
    elif action == "compose_down_volumes":
        argv = _compose_prefix(config, repo_root, repo_config) + [
            "down",
            "--volumes",
            "--remove-orphans",
        ]
    elif action == "compose_rm":
        argv = _compose_prefix(config, repo_root, repo_config) + ["rm", "--force", "--stop"] + safe_services
    elif action in {"compose_exec", "container_exec"}:
        profile = _exec_profile(repo_config, command_id)
        writes_files = profile.writes_files
        timeout = profile.timeout_seconds
        if action == "compose_exec":
            service = safe_services[0] if len(safe_services) == 1 else ""
            if not service:
                raise ValueError("compose_exec requires exactly one service")
            argv = _compose_prefix(config, repo_root, repo_config) + ["exec", "--no-TTY", service]
        else:
            argv = [docker, "container", "exec", _safe_token(target, "target")]
        argv.extend(profile.argv)
    elif action == "image_build":
        tag = _safe_token(target, "target")
        build_context = _validate_repo_directory(repo_root, context, "context")
        argv = [docker, "image", "build", "--tag", tag]
        if dockerfile:
            argv.extend(["--file", _validate_repo_file(repo_root, dockerfile, "dockerfile")])
        argv.append(build_context)
        timeout = max(timeout, 3600)
    elif action == "image_pull":
        argv = [docker, "image", "pull", _safe_token(target, "target")]
        timeout = max(timeout, 1800)
    elif action == "image_tag":
        argv = [
            docker,
            "image",
            "tag",
            _safe_token(target, "target"),
            _safe_token(destination, "destination"),
        ]
    elif action == "image_push":
        argv = [docker, "image", "push", _safe_token(target, "target")]
        timeout = max(timeout, 1800)
    elif action in container_simple:
        argv = [docker, "container", container_simple[action], _safe_token(target, "target")]
    elif action == "container_remove":
        argv = [docker, "container", "rm"]
        if force:
            argv.append("--force")
        argv.append(_safe_token(target, "target"))
    elif action == "image_remove":
        argv = [docker, "image", "rm"]
        if force:
            argv.append("--force")
        argv.append(_safe_token(target, "target"))
    elif action == "network_create":
        argv = [docker, "network", "create", _safe_name(target, "target")]
    elif action == "volume_create":
        argv = [docker, "volume", "create", _safe_name(target, "target")]
    elif action == "network_remove":
        argv = [docker, "network", "rm", _safe_name(target, "target")]
    elif action == "volume_remove":
        argv = [docker, "volume", "rm"]
        if force:
            argv.append("--force")
        argv.append(_safe_name(target, "target"))
    elif action == "builder_prune":
        argv = [docker, "builder", "prune", "--force"]
    elif action in {"container_prune", "image_prune", "network_prune", "volume_prune"}:
        kind = action.removesuffix("_prune")
        argv = [docker, kind, "prune", "--force"]
    elif action == "system_prune":
        argv = [docker, "system", "prune", "--force"]
    else:
        argv = [docker, "system", "prune", "--force", "--volumes"]

    return DockerCommandSpec(
        action=action,
        argv=argv,
        timeout_seconds=timeout,
        high_risk=high_risk,
        writes_files=writes_files,
        description="Bounded Docker runtime action",
    )


def _run_argv(config: AppConfig, spec: DockerCommandSpec, cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            spec.argv,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            shell=False,
            timeout=spec.timeout_seconds,
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
    max_bytes = config.docker.max_output_bytes
    combined = (stdout + stderr).encode("utf-8")
    output_truncated = len(combined) > max_bytes
    if output_truncated:
        stdout_bytes = stdout.encode("utf-8")
        if len(stdout_bytes) >= max_bytes:
            stdout = stdout_bytes[:max_bytes].decode("utf-8", errors="replace")
            stderr = ""
        else:
            remaining = max_bytes - len(stdout_bytes)
            stderr = stderr.encode("utf-8")[:remaining].decode("utf-8", errors="replace")

    return {
        "ok": exit_code == 0 and not timed_out,
        "action": spec.action,
        "argv": list(spec.argv),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": output_truncated,
        "high_risk": spec.high_risk,
        "writes_files": spec.writes_files,
        "error": (
            f"Timed out after {spec.timeout_seconds}s"
            if timed_out
            else (stderr.strip()[:300] if exit_code != 0 else "")
        ),
    }


def run_docker_inspection(
    config: AppConfig,
    repo_root: Path,
    repo_config: RepoConfig,
    operation: str,
    **kwargs: Any,
) -> dict[str, Any]:
    spec = build_docker_inspection(config, repo_root, repo_config, operation, **kwargs)
    return _run_argv(config, spec, repo_root)


def run_docker_action(
    config: AppConfig,
    repo_root: Path,
    repo_config: RepoConfig,
    action: str,
    **kwargs: Any,
) -> dict[str, Any]:
    spec = build_docker_action(config, repo_root, repo_config, action, **kwargs)
    return _run_argv(config, spec, repo_root)


def docker_health(config: AppConfig) -> dict[str, Any]:
    _require_enabled(config)
    version = _run_argv(
        config,
        DockerCommandSpec(
            action="engine_version",
            argv=[config.docker.executable, "version"],
            timeout_seconds=min(config.docker.default_timeout_seconds, 60),
        ),
        config.config_dir,
    )
    compose = _run_argv(
        config,
        DockerCommandSpec(
            action="compose_version",
            argv=[config.docker.executable, "compose", "version"],
            timeout_seconds=min(config.docker.default_timeout_seconds, 60),
        ),
        config.config_dir,
    )
    return {
        "ok": bool(version["ok"] and compose["ok"]),
        "enabled": True,
        "engine": version,
        "compose": compose,
        "error": version["error"] or compose["error"],
    }


def list_docker_capabilities(
    config: AppConfig,
    repo_config: RepoConfig | None = None,
) -> dict[str, Any]:
    exec_profiles = []
    compose_files: list[str] = []
    project_name = ""
    if repo_config is not None:
        exec_profiles = [
            {
                "command_id": profile.command_id,
                "description": profile.description,
                "timeout_seconds": profile.timeout_seconds,
                "writes_files": profile.writes_files,
            }
            for profile in repo_config.docker_exec_profiles
        ]
        compose_files = list(repo_config.docker_compose_files)
        project_name = repo_config.docker_project_name
    return {
        "ok": True,
        "enabled": config.docker.enabled,
        "executable": config.docker.executable,
        "read_only_operations": list(READ_ONLY_DOCKER_OPERATIONS),
        "actions": list(DOCKER_ACTIONS),
        "high_risk_actions": dict(HIGH_RISK_ACTIONS),
        "high_risk_gates": {
            "allow_push": config.docker.allow_push,
            "allow_prune": config.docker.allow_prune,
            "allow_remove": config.docker.allow_remove,
            "allow_compose_down_volumes": config.docker.allow_compose_down_volumes,
        },
        "confirmation_token": config.docker.confirmation_token,
        "compose_files": compose_files,
        "project_name": project_name,
        "exec_profiles": exec_profiles,
        "arbitrary_shell_supported": False,
        "arbitrary_argv_supported": False,
        "error": "",
    }
