from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from codexbridge.config import (
    AppConfig,
    DockerConfig,
    DockerExecProfileConfig,
    LocalModelConfig,
    RepoConfig,
    SSHCommandProfileConfig,
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
    assert config.ssh.hosts["my_vps"].ssh_alias == "my-vps"
    assert [
        profile.command_id for profile in config.ssh.hosts["my_vps"].command_profiles
    ] == ["uptime", "restart_app"]


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
