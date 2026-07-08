from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from codexbridge.config import (
    AppConfig,
    CloudflareConfig,
    CloudflareProfileConfig,
    DockerConfig,
    DockerExecProfileConfig,
    LocalModelConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
    SupervisorAutonomyProfile,
    SupervisorsConfig,
    load_config,
    resolve_repo_config,
    resolve_repo,
)


def init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def test_config_example_loads_without_repo_validation() -> None:
    config = load_config("config.example.yaml", validate_repos=False)
    assert "stream_alpha" in config.repos
    assert config.codex.executable == "codex"
    assert config.supervisors.default_autonomy_profile == "balanced"
    assert config.supervisors.effective_profile().max_implementation_tier == 2
    assert config.ssh.enabled is False
    assert config.docker.enabled is False
    assert config.docker.executable == "docker"
    assert config.cloudflare.enabled is False
    assert config.cloudflare.token_env == "CLOUDFLARE_API_TOKEN"
    assert config.cloudflare.profiles["production"].zone_name == "example.com"
    assert config.ssh.hosts["my_vps"].ssh_alias == "my-vps"
    assert [
        profile.command_id for profile in config.ssh.hosts["my_vps"].command_profiles
    ] == ["health", "uptime", "restart_app"]


def test_config_defaults_to_balanced_supervisor_profile(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    assert config.supervisors.default_autonomy_profile == "balanced"
    assert config.supervisors.effective_profile().stop_on_requires_human is True
    assert config.supervisors.notifications.enabled is True
    assert config.supervisors.notifications.file.enabled is False
    assert config.supervisors.notifications.webhook.enabled is False
    assert config.supervisors.notifications.windows_toast.enabled is False
    assert config.local_model.enabled is False
    assert config.local_model.base_url == "http://localhost:11434/v1"
    assert config.local_model.model == "llama3.2"
    assert config.return_loop.return_loop_enabled is True
    assert config.return_loop.conversation_target == "codexbridge_gpt"
    assert config.memory.memory_enabled is True
    assert (
        config.resolve_memory_db_path()
        == tmp_path / "runs" / "memory" / "project_memory.sqlite3"
    )
    assert config.autonomy.autonomy_enabled is True
    assert config.autonomy.autonomy_default_profile == "chatgpt_delegated"
    assert config.resolve_approval_store_path() == tmp_path / "runs" / "approvals"
    assert config.codex_router.codex_router_enabled is True
    assert config.codex_router.codex_router_invoke_enabled is False
    assert (
        config.resolve_codex_router_packet_dir()
        == tmp_path / "runs" / "codex_escalations"
    )


def test_local_model_config_defaults_and_overrides() -> None:
    config = LocalModelConfig(
        enabled=True,
        model="qwen2.5-coder",
        timeout_seconds=10,
        temperature=0.0,
        max_tokens=512,
    )

    assert config.enabled is True
    assert config.base_url == "http://localhost:11434/v1"
    assert config.model == "qwen2.5-coder"
    assert config.timeout_seconds == 10


def test_config_loads_named_supervisor_profiles(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        supervisors=SupervisorsConfig(
            default_autonomy_profile="custom",
            autonomy_profiles={
                "custom": SupervisorAutonomyProfile(
                    max_plan_tier=1, max_implementation_tier=1
                ),
            },
        ),
        config_dir=tmp_path,
    )
    assert config.supervisors.effective_profile().max_implementation_tier == 1


def test_ssh_host_rejects_duplicate_command_ids() -> None:
    profile = SSHCommandProfileConfig(command_id="status", argv=["uptime"])
    with pytest.raises(ValidationError, match="unique"):
        SSHHostConfig(
            ssh_alias="my-vps",
            command_profiles=[profile, profile.model_copy()],
        )


def test_ssh_deployment_and_admin_config_validation() -> None:
    deployment = SSHDeploymentProfileConfig(
        repo_name="sample",
        remote_root="/srv/sample",
        compose_file="docker-compose.yml",
        compose_project_name="sample-app",
        shared_files={"/srv/sample/shared/.env": ".env"},
    )
    host = SSHHostConfig(
        ssh_alias="sample-host",
        allowed_remote_roots=["/srv/sample/", "/var/log"],
        allowed_executables=["docker", "git"],
        deployment_profiles={"sample": deployment},
    )
    config = SSHConfig(
        enabled=True,
        allow_transfer=True,
        allow_deploy=True,
        allow_admin=True,
        allow_delete=True,
        allow_reboot=True,
        hosts={"sample": host},
    )

    assert host.allowed_remote_roots == ["/srv/sample", "/var/log"]
    assert config.scp_executable == "scp"
    assert config.confirmation_token == "CONFIRM_SSH_HIGH_RISK"
    assert config.hosts["sample"].deployment_profiles[
        "sample"
    ].compose_project_name == ("sample-app")

    with pytest.raises(ValidationError, match="absolute POSIX path"):
        SSHDeploymentProfileConfig(repo_name="sample", remote_root="relative/path")
    with pytest.raises(ValidationError, match="repository-relative"):
        SSHDeploymentProfileConfig(
            repo_name="sample",
            remote_root="/srv/sample",
            local_subdir="../outside",
        )
    with pytest.raises(ValidationError, match="absolute POSIX paths"):
        SSHHostConfig(
            ssh_alias="sample-host",
            allowed_remote_roots=["relative/path"],
        )
    with pytest.raises(ValidationError, match="release-relative"):
        SSHDeploymentProfileConfig(
            repo_name="sample",
            remote_root="/srv/sample",
            shared_files={"/srv/sample/shared/.env": "../.env"},
        )


def test_cloudflare_config_and_profile_validation() -> None:
    profile = CloudflareProfileConfig(
        account_id="b" * 32,
        zone_id="a" * 32,
        zone_name="Example.COM.",
        allowed_dns_names=["api.example.com"],
        allowed_ruleset_phases=["http_request_firewall_custom"],
        allowed_tunnel_ids=["12345678-1234-1234-1234-123456789abc"],
    )
    config = CloudflareConfig(
        enabled=True,
        allow_dns_write=True,
        allow_delete=True,
        profiles={"production": profile},
    )

    assert config.api_base_url == "https://api.cloudflare.com/client/v4"
    assert config.env_file == ".env"
    assert config.confirmation_token == "CONFIRM_CLOUDFLARE_HIGH_RISK"
    assert profile.zone_name == "example.com"
    assert profile.allowed_dns_names == ["api.example.com"]

    with pytest.raises(ValidationError, match="official client v4"):
        CloudflareConfig(api_base_url="https://example.com/client/v4")
    with pytest.raises(ValidationError, match="safe path relative"):
        CloudflareConfig(env_file="../outside.env")
    with pytest.raises(ValidationError, match="32-character hex ID"):
        CloudflareProfileConfig(account_id="not-an-id")
    with pytest.raises(ValidationError, match="inside zone_name"):
        CloudflareProfileConfig(
            zone_name="example.com", allowed_dns_names=["outside.test"]
        )
    with pytest.raises(ValidationError, match="UUID"):
        CloudflareProfileConfig(allowed_tunnel_ids=["bad-id"])


def test_docker_config_and_exec_profile_validation() -> None:
    config = DockerConfig(enabled=True, allow_push=True, allow_prune=True)
    assert config.enabled is True
    assert config.allow_push is True
    assert config.allow_prune is True
    assert config.confirmation_token == "CONFIRM_DOCKER_HIGH_RISK"

    profile = DockerExecProfileConfig(command_id="health", argv=["python", "-V"])
    with pytest.raises(ValidationError, match="unique"):
        RepoConfig(
            path=".",
            docker_exec_profiles=[profile, profile.model_copy()],
        )
    with pytest.raises(ValidationError, match="shell operators"):
        DockerExecProfileConfig(command_id="bad", argv=["sh; whoami"])


def test_unknown_default_supervisor_profile_rejected() -> None:
    with pytest.raises(ValidationError):
        SupervisorsConfig(
            default_autonomy_profile="missing",
            autonomy_profiles={"balanced": SupervisorAutonomyProfile()},
        )


def test_invalid_supervisor_profile_values_rejected() -> None:
    with pytest.raises(ValidationError):
        SupervisorAutonomyProfile(max_plan_tier=0)


def test_invalid_supervisor_notification_values_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(
            repos={"sample": RepoConfig(path=".")},
            supervisors={"notifications": {"max_payload_chars": 10}},
        )


def test_unknown_repo_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"repos:\n  sample:\n    path: '{repo.as_posix()}'\nruns_dir: runs\n",
        encoding="utf-8",
    )
    config = load_config(config_file)
    with pytest.raises(ValueError, match="Unknown repo_name"):
        resolve_repo(config, "missing")


def test_missing_repo_path_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("repos:\n  sample:\n    path: 'missing'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not exist"):
        load_config(config_file)


def test_repo_must_contain_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"repos:\n  sample:\n    path: '{repo.as_posix()}'\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="does not contain .git"):
        load_config(config_file)


def test_resolve_repo_config_accepts_case_insensitive_name(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    config = AppConfig(
        repos={"codexbridge": RepoConfig(path=str(repo))}, config_dir=tmp_path
    )

    resolved_name, resolved_repo = resolve_repo_config(config, "CodexBridge")

    assert resolved_name == "codexbridge"
    assert resolved_repo.path == str(repo)
    assert resolve_repo(config, "CodexBridge") == repo.resolve()
