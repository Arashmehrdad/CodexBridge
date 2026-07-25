from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .config import (
    AppConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
    SSHProjectBindingConfig,
)

_BINDING_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_CAPABILITY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class ResolvedSSHProjectBinding:
    binding_id: str
    host_id: str
    host: SSHHostConfig
    profile: SSHDeploymentProfileConfig
    source: str
    required_capabilities: tuple[str, ...]
    allow_first_deployment: bool
    expected_writable_paths: tuple[str, ...]
    expected_read_only_paths: tuple[str, ...]


@dataclass(frozen=True)
class SSHProjectValidationCheck:
    name: str
    argv: tuple[str, ...]
    required: bool = True
    preparation_allowed: bool = False


def _safe_binding_id(binding_id: str) -> str:
    value = str(binding_id or "").strip()
    if not _BINDING_ID_RE.fullmatch(value):
        raise ValueError(
            "SSH project binding ID must use letters, numbers, _ or -"
        )
    return value


def _canonical_binding(
    config: AppConfig,
    binding_id: str,
    binding: SSHProjectBindingConfig,
) -> ResolvedSSHProjectBinding:
    host = config.ssh.hosts.get(binding.host_id)
    if host is None:  # pragma: no cover - AppConfig validation rejects this
        raise ValueError(
            f"SSH project binding {binding_id!r} references an unknown host"
        )
    return ResolvedSSHProjectBinding(
        binding_id=binding_id,
        host_id=binding.host_id,
        host=host,
        profile=binding,
        source="canonical",
        required_capabilities=tuple(binding.required_capabilities),
        allow_first_deployment=binding.allow_first_deployment,
        expected_writable_paths=tuple(binding.expected_writable_paths),
        expected_read_only_paths=tuple(binding.expected_read_only_paths),
    )


def _legacy_binding(
    config: AppConfig,
    binding_id: str,
    host_id: str,
) -> ResolvedSSHProjectBinding:
    normalized_host_id = str(host_id or "").strip()
    if not normalized_host_id:
        raise ValueError(
            "Legacy SSH deployment resolution requires host_id"
        )
    host = config.ssh.hosts.get(normalized_host_id)
    if host is None:
        raise ValueError(f"Unknown SSH host_id: {normalized_host_id!r}")
    profile = host.deployment_profiles.get(binding_id)
    if profile is None:
        raise ValueError(
            f"Unknown SSH project binding/deployment ID: {binding_id!r}. "
            f"Canonical: {sorted(config.ssh.project_bindings)}. "
            f"Legacy for host {normalized_host_id!r}: {sorted(host.deployment_profiles)}"
        )
    return ResolvedSSHProjectBinding(
        binding_id=binding_id,
        host_id=normalized_host_id,
        host=host,
        profile=profile,
        source="legacy_nested",
        required_capabilities=(),
        allow_first_deployment=False,
        expected_writable_paths=(),
        expected_read_only_paths=(),
    )


def resolve_ssh_project_binding(
    config: AppConfig,
    binding_id: str,
    *,
    host_id: str = "",
) -> ResolvedSSHProjectBinding:
    """Resolve canonical bindings first and legacy nested deployments second."""

    normalized_id = _safe_binding_id(binding_id)
    canonical = config.ssh.project_bindings.get(normalized_id)
    if canonical is not None:
        if host_id and canonical.host_id != str(host_id).strip():
            raise ValueError(
                f"SSH project binding {normalized_id!r} belongs to host "
                f"{canonical.host_id!r}, not {str(host_id).strip()!r}"
            )
        return _canonical_binding(config, normalized_id, canonical)
    return _legacy_binding(config, normalized_id, host_id)


def list_ssh_project_bindings(config: AppConfig) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for binding_id, binding in sorted(config.ssh.project_bindings.items()):
        items.append(
            {
                "binding_id": binding_id,
                "host_id": binding.host_id,
                "repo_name": binding.repo_name,
                "source": "canonical",
                "remote_root": binding.remote_root,
                "required_capabilities": list(binding.required_capabilities),
                "allow_first_deployment": binding.allow_first_deployment,
                "health_command_id": binding.health_command_id,
            }
        )
    for host_id, host in sorted(config.ssh.hosts.items()):
        for binding_id, profile in sorted(host.deployment_profiles.items()):
            if binding_id in config.ssh.project_bindings:
                continue
            items.append(
                {
                    "binding_id": binding_id,
                    "host_id": host_id,
                    "repo_name": profile.repo_name,
                    "source": "legacy_nested",
                    "remote_root": profile.remote_root,
                    "required_capabilities": [],
                    "allow_first_deployment": False,
                    "health_command_id": profile.health_command_id,
                }
            )
    return items


def _command_profile_argv(
    resolved: ResolvedSSHProjectBinding,
    command_id: str,
) -> tuple[str, ...]:
    for profile in resolved.host.command_profiles:
        if profile.command_id == command_id:
            return tuple(str(item) for item in profile.argv)
    raise ValueError(
        f"SSH project binding references unknown health command {command_id!r}"
    )


def build_project_binding_validation_plan(
    config: AppConfig,
    binding_id: str,
    *,
    host_id: str = "",
) -> tuple[ResolvedSSHProjectBinding, tuple[SSHProjectValidationCheck, ...]]:
    resolved = resolve_ssh_project_binding(
        config, binding_id, host_id=host_id
    )
    profile = resolved.profile
    parent = posixpath.dirname(profile.remote_root.rstrip("/")) or "/"
    checks: list[SSHProjectValidationCheck] = [
        SSHProjectValidationCheck(
            "remote_parent_exists", ("test", "-d", parent)
        ),
        SSHProjectValidationCheck(
            "remote_root_exists",
            ("test", "-d", profile.remote_root),
            preparation_allowed=resolved.allow_first_deployment,
        ),
    ]
    if profile.compose_file:
        checks.append(
            SSHProjectValidationCheck(
                "compose_file_exists",
                (
                    "test",
                    "-f",
                    posixpath.join(profile.remote_root, profile.compose_file),
                ),
                preparation_allowed=resolved.allow_first_deployment,
            )
        )
    if profile.env_file:
        checks.append(
            SSHProjectValidationCheck(
                "environment_file_exists", ("test", "-f", profile.env_file)
            )
        )
    if profile.service_name:
        checks.append(
            SSHProjectValidationCheck(
                "service_is_known",
                (
                    "systemctl",
                    "show",
                    "--property=LoadState",
                    "--value",
                    profile.service_name,
                ),
            )
        )
    if profile.health_command_id:
        checks.append(
            SSHProjectValidationCheck(
                "health_command",
                _command_profile_argv(resolved, profile.health_command_id),
            )
        )
    for index, path in enumerate(resolved.expected_writable_paths):
        checks.append(
            SSHProjectValidationCheck(
                f"writable_path_{index}",
                ("test", "-w", path),
                preparation_allowed=resolved.allow_first_deployment,
            )
        )
    for index, path in enumerate(resolved.expected_read_only_paths):
        checks.append(
            SSHProjectValidationCheck(
                f"read_only_path_{index}", ("test", "-r", path)
            )
        )
    return resolved, tuple(checks)


def _result_ok(result: Mapping[str, Any] | None) -> bool:
    return bool(result and result.get("ok"))


def evaluate_project_binding_validation(
    resolved: ResolvedSSHProjectBinding,
    checks: Sequence[SSHProjectValidationCheck],
    results: Mapping[str, Mapping[str, Any]],
    *,
    capability_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    capability_snapshot = dict(capability_snapshot or {})
    available_tools = set(capability_snapshot.get("available_tools") or [])
    available_capabilities = set(
        capability_snapshot.get("available_capabilities") or available_tools
    )
    explicit_missing = set(
        capability_snapshot.get("missing_required_capabilities") or []
    )
    explicit_unknown = set(
        capability_snapshot.get("unknown_required_capabilities") or []
    )
    missing_capabilities = sorted(
        {
            name
            for name in resolved.required_capabilities
            if name not in available_capabilities
        }
        | explicit_missing
    )
    unknown_capabilities = sorted(explicit_unknown)

    check_results: list[dict[str, Any]] = []
    failed: list[str] = []
    preparation: list[str] = []
    for check in checks:
        result = results.get(check.name)
        ok = _result_ok(result)
        state = "passed"
        if not ok and check.preparation_allowed:
            state = "preparation_required"
            preparation.append(check.name)
        elif not ok and check.required:
            state = "failed"
            failed.append(check.name)
        check_results.append(
            {
                "name": check.name,
                "state": state,
                "required": check.required,
                "preparation_allowed": check.preparation_allowed,
                "exit_code": int((result or {}).get("exit_code", 1)),
                "timed_out": bool((result or {}).get("timed_out")),
                "error": str((result or {}).get("error") or "")[:1024],
            }
        )

    if missing_capabilities or unknown_capabilities:
        failed.append("required_capabilities")
    status = "valid"
    if failed:
        status = "invalid"
    elif preparation:
        status = "preparation_required"
    return {
        "ok": status != "invalid",
        "status": status,
        "binding_id": resolved.binding_id,
        "host_id": resolved.host_id,
        "repo_name": resolved.profile.repo_name,
        "source": resolved.source,
        "allow_first_deployment": resolved.allow_first_deployment,
        "required_capabilities": list(resolved.required_capabilities),
        "missing_required_capabilities": missing_capabilities,
        "unknown_required_capabilities": unknown_capabilities,
        "failed_checks": sorted(set(failed)),
        "preparation_required_checks": sorted(set(preparation)),
        "checks": check_results,
        "error": "" if status != "invalid" else "Project binding validation failed",
    }
