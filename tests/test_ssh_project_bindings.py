from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from soma.config import (
    AppConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
    SSHProjectBindingConfig,
)
from soma.ssh_project_bindings import (
    build_project_binding_validation_plan,
    evaluate_project_binding_validation,
    list_ssh_project_bindings,
    resolve_ssh_project_binding,
)
from soma.ssh_tools import _resolve_deployment, build_ssh_action, build_ssh_inspection


def _config(tmp_path: Path, *, allow_first_deployment: bool = False) -> AppConfig:
    return AppConfig(
        repos={
            "project_x": RepoConfig(path=str(tmp_path / "project-x")),
            "legacy_repo": RepoConfig(path=str(tmp_path / "legacy")),
        },
        config_dir=tmp_path,
        ssh=SSHConfig(
            enabled=True,
            hosts={
                "production_vps": SSHHostConfig(
                    ssh_alias="production-alias",
                    allowed_remote_roots=["/srv"],
                    command_profiles=[
                        SSHCommandProfileConfig(
                            command_id="api_health",
                            argv=["curl", "--fail", "http://127.0.0.1/healthz"],
                        )
                    ],
                    deployment_profiles={
                        "legacy_deploy": SSHDeploymentProfileConfig(
                            repo_name="legacy_repo",
                            remote_root="/srv/legacy",
                            compose_file="compose.yaml",
                        )
                    },
                )
            },
            project_bindings={
                "project_x_production": SSHProjectBindingConfig(
                    host_id="production_vps",
                    repo_name="project_x",
                    remote_root="/srv/project-x",
                    compose_file="docker-compose.yml",
                    env_file="/etc/project-x/production.env",
                    service_name="project-x.service",
                    health_command_id="api_health",
                    required_capabilities=["systemd", "docker", "git"],
                    allow_first_deployment=allow_first_deployment,
                    expected_writable_paths=["/srv/project-x"],
                    expected_read_only_paths=["/etc/project-x/production.env"],
                )
            },
        ),
    )


def _ok() -> dict[str, object]:
    return {
        "ok": True,
        "exit_code": 0,
        "timed_out": False,
        "error": "",
    }


def _failed(message: str = "missing") -> dict[str, object]:
    return {
        "ok": False,
        "exit_code": 1,
        "timed_out": False,
        "error": message,
    }


def test_canonical_binding_is_independent_from_host_profile(tmp_path: Path) -> None:
    config = _config(tmp_path)
    resolved = resolve_ssh_project_binding(
        config, "project_x_production"
    )

    assert resolved.source == "canonical"
    assert resolved.host_id == "production_vps"
    assert resolved.profile.repo_name == "project_x"
    assert resolved.profile.remote_root == "/srv/project-x"
    assert resolved.required_capabilities == ("systemd", "docker", "git")
    assert "project_x_production" not in resolved.host.deployment_profiles


def test_legacy_nested_deployment_remains_resolvable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    resolved = resolve_ssh_project_binding(
        config, "legacy_deploy", host_id="production_vps"
    )

    assert resolved.source == "legacy_nested"
    assert resolved.profile.repo_name == "legacy_repo"
    assert resolved.required_capabilities == ()
    assert _resolve_deployment(
        config, "production_vps", "legacy_deploy"
    ).remote_root == "/srv/legacy"


def test_canonical_binding_rejects_wrong_host_hint(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with pytest.raises(ValueError, match="belongs to host"):
        resolve_ssh_project_binding(
            config,
            "project_x_production",
            host_id="different_host",
        )


def test_project_binding_config_rejects_unknown_targets_and_unsafe_contracts(
    tmp_path: Path,
) -> None:
    host = SSHHostConfig(ssh_alias="alias", allowed_remote_roots=["/srv"])
    with pytest.raises(ValidationError, match="unknown host"):
        SSHConfig(
            hosts={"production_vps": host},
            project_bindings={
                "bad": SSHProjectBindingConfig(
                    host_id="missing",
                    repo_name="project_x",
                    remote_root="/srv/project-x",
                )
            },
        )
    with pytest.raises(ValidationError, match="outside host"):
        SSHConfig(
            hosts={"production_vps": host},
            project_bindings={
                "bad": SSHProjectBindingConfig(
                    host_id="production_vps",
                    repo_name="project_x",
                    remote_root="/opt/project-x",
                )
            },
        )
    with pytest.raises(ValidationError, match="unknown repository"):
        AppConfig(
            repos={"known": RepoConfig(path=str(tmp_path))},
            config_dir=tmp_path,
            ssh=SSHConfig(
                hosts={"production_vps": host},
                project_bindings={
                    "bad": SSHProjectBindingConfig(
                        host_id="production_vps",
                        repo_name="missing",
                        remote_root="/srv/project-x",
                    )
                },
            ),
        )
    with pytest.raises(ValidationError, match="lowercase names"):
        SSHProjectBindingConfig(
            host_id="production_vps",
            repo_name="project_x",
            remote_root="/srv/project-x",
            required_capabilities=["Docker-Compose"],
        )
    with pytest.raises(ValidationError, match="absolute POSIX paths"):
        SSHProjectBindingConfig(
            host_id="production_vps",
            repo_name="project_x",
            remote_root="/srv/project-x",
            expected_writable_paths=["relative/path"],
        )


def test_binding_inventory_lists_canonical_and_legacy_without_duplicates(
    tmp_path: Path,
) -> None:
    items = list_ssh_project_bindings(_config(tmp_path))
    by_id = {item["binding_id"]: item for item in items}

    assert set(by_id) == {"project_x_production", "legacy_deploy"}
    assert by_id["project_x_production"]["source"] == "canonical"
    assert by_id["legacy_deploy"]["source"] == "legacy_nested"


def test_validation_plan_is_fixed_and_read_only(tmp_path: Path) -> None:
    resolved, checks = build_project_binding_validation_plan(
        _config(tmp_path), "project_x_production"
    )
    by_name = {check.name: check for check in checks}

    assert resolved.host_id == "production_vps"
    assert by_name["remote_parent_exists"].argv == (
        "test",
        "-d",
        "/srv",
    )
    assert by_name["remote_root_exists"].argv == (
        "test",
        "-d",
        "/srv/project-x",
    )
    assert by_name["compose_file_exists"].argv == (
        "test",
        "-f",
        "/srv/project-x/docker-compose.yml",
    )
    assert by_name["environment_file_exists"].argv == (
        "test",
        "-f",
        "/etc/project-x/production.env",
    )
    assert by_name["service_is_known"].argv[-1] == "project-x.service"
    assert by_name["health_command"].argv[0] == "curl"
    assert by_name["writable_path_0"].argv == (
        "test",
        "-w",
        "/srv/project-x",
    )
    assert by_name["read_only_path_0"].argv == (
        "test",
        "-r",
        "/etc/project-x/production.env",
    )


def test_binding_validation_reports_valid_state(tmp_path: Path) -> None:
    resolved, checks = build_project_binding_validation_plan(
        _config(tmp_path), "project_x_production"
    )
    results = {check.name: _ok() for check in checks}
    validation = evaluate_project_binding_validation(
        resolved,
        checks,
        results,
        capability_snapshot={
            "available_tools": ["systemd", "docker", "git"],
            "missing_required_capabilities": [],
            "unknown_required_capabilities": [],
        },
    )

    assert validation["ok"] is True
    assert validation["status"] == "valid"
    assert validation["failed_checks"] == []


def test_first_deployment_missing_paths_are_preparation_required(
    tmp_path: Path,
) -> None:
    resolved, checks = build_project_binding_validation_plan(
        _config(tmp_path, allow_first_deployment=True),
        "project_x_production",
    )
    results = {check.name: _ok() for check in checks}
    for name in (
        "remote_root_exists",
        "compose_file_exists",
        "writable_path_0",
    ):
        results[name] = _failed()
    validation = evaluate_project_binding_validation(
        resolved,
        checks,
        results,
        capability_snapshot={
            "available_tools": ["systemd", "docker", "git"]
        },
    )

    assert validation["ok"] is True
    assert validation["status"] == "preparation_required"
    assert validation["failed_checks"] == []
    assert set(validation["preparation_required_checks"]) == {
        "remote_root_exists",
        "compose_file_exists",
        "writable_path_0",
    }


def test_binding_validation_fails_required_checks_and_capabilities(
    tmp_path: Path,
) -> None:
    resolved, checks = build_project_binding_validation_plan(
        _config(tmp_path), "project_x_production"
    )
    results = {check.name: _ok() for check in checks}
    results["environment_file_exists"] = _failed("env missing")
    validation = evaluate_project_binding_validation(
        resolved,
        checks,
        results,
        capability_snapshot={
            "available_tools": ["git"],
            "missing_required_capabilities": ["docker", "systemd"],
        },
    )

    assert validation["ok"] is False
    assert validation["status"] == "invalid"
    assert "environment_file_exists" in validation["failed_checks"]
    assert "required_capabilities" in validation["failed_checks"]
    assert validation["missing_required_capabilities"] == ["docker", "systemd"]


def test_existing_ssh_actions_accept_canonical_binding_id(tmp_path: Path) -> None:
    config = _config(tmp_path)
    inspection = build_ssh_inspection(
        config,
        "production_vps",
        "file_stat",
        deployment_id="project_x_production",
    )
    assert inspection.remote_argv[-1] == "/srv/project-x"

    compose = build_ssh_action(
        config,
        "production_vps",
        "docker_compose_pull",
        deployment_id="project_x_production",
    )
    assert "/srv/project-x/docker-compose.yml" in compose.remote_argv
