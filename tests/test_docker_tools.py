from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import codexbridge.docker_tools as docker_tools
from codexbridge.config import (
    AppConfig,
    DockerConfig,
    DockerExecProfileConfig,
    RepoConfig,
)


def make_config(tmp_path: Path, **docker_overrides) -> tuple[AppConfig, RepoConfig]:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  api:\n    image: example/api\n", encoding="utf-8")
    repo_config = RepoConfig(
        path=str(tmp_path),
        docker_exec_profiles=[
            DockerExecProfileConfig(
                command_id="health",
                argv=["python", "-m", "app.health"],
                timeout_seconds=45,
            )
        ],
    )
    docker_values = {
        "enabled": True,
        "allow_push": False,
        "allow_prune": False,
        "allow_remove": False,
        "allow_compose_down_volumes": False,
    }
    docker_values.update(docker_overrides)
    config = AppConfig(
        repos={"sample": repo_config},
        docker=DockerConfig(**docker_values),
        config_dir=tmp_path,
    )
    return config, repo_config


def test_compose_up_uses_repo_compose_file_and_fixed_argv(tmp_path: Path) -> None:
    config, repo_config = make_config(tmp_path)

    spec = docker_tools.build_docker_action(
        config,
        tmp_path,
        repo_config,
        "compose_up",
        services=["api"],
        build=True,
    )

    assert spec.argv == [
        "docker",
        "compose",
        "--file",
        "docker-compose.yml",
        "up",
        "--detach",
        "--build",
        "api",
    ]
    assert spec.high_risk is False


def test_compose_inspection_is_read_only_and_tail_is_bounded(tmp_path: Path) -> None:
    config, repo_config = make_config(tmp_path)

    spec = docker_tools.build_docker_inspection(
        config,
        tmp_path,
        repo_config,
        "compose_logs",
        service="api",
        tail=250,
    )

    assert spec.argv[-5:] == ["logs", "--no-color", "--tail", "250", "api"]
    assert spec.high_risk is False
    assert spec.writes_files is False

    with pytest.raises(ValueError, match="tail must be between"):
        docker_tools.build_docker_inspection(
            config, tmp_path, repo_config, "compose_logs", tail=5001
        )


def test_unsafe_service_and_target_values_are_rejected(tmp_path: Path) -> None:
    config, repo_config = make_config(tmp_path)

    with pytest.raises(ValueError, match="Invalid service"):
        docker_tools.build_docker_action(
            config,
            tmp_path,
            repo_config,
            "compose_restart",
            services=["api;whoami"],
        )

    with pytest.raises(ValueError, match="Invalid target"):
        docker_tools.build_docker_action(
            config,
            tmp_path,
            repo_config,
            "image_pull",
            target="image && whoami",
        )


def test_exec_requires_configured_command_id(tmp_path: Path) -> None:
    config, repo_config = make_config(tmp_path)

    spec = docker_tools.build_docker_action(
        config,
        tmp_path,
        repo_config,
        "compose_exec",
        services=["api"],
        command_id="health",
    )

    assert spec.argv[-5:] == ["--no-TTY", "api", "python", "-m", "app.health"]
    assert spec.timeout_seconds == 45

    with pytest.raises(ValueError, match="Unknown Docker exec command_id"):
        docker_tools.build_docker_action(
            config,
            tmp_path,
            repo_config,
            "compose_exec",
            services=["api"],
            command_id="shell",
        )


def test_high_risk_action_requires_config_gate_and_confirmation(tmp_path: Path) -> None:
    config, repo_config = make_config(tmp_path)

    with pytest.raises(ValueError, match="disabled by config gate"):
        docker_tools.build_docker_action(
            config,
            tmp_path,
            repo_config,
            "volume_prune",
            confirmation=config.docker.confirmation_token,
        )

    config.docker.allow_prune = True
    with pytest.raises(ValueError, match="requires confirmation token"):
        docker_tools.build_docker_action(
            config, tmp_path, repo_config, "volume_prune"
        )

    spec = docker_tools.build_docker_action(
        config,
        tmp_path,
        repo_config,
        "volume_prune",
        confirmation=config.docker.confirmation_token,
    )
    assert spec.argv == ["docker", "volume", "prune", "--force"]
    assert spec.high_risk is True


def test_push_and_remove_have_separate_opt_in_gates(tmp_path: Path) -> None:
    config, repo_config = make_config(
        tmp_path, allow_push=True, allow_remove=True
    )
    confirmation = config.docker.confirmation_token

    push = docker_tools.build_docker_action(
        config,
        tmp_path,
        repo_config,
        "image_push",
        target="registry.example.com/team/app:latest",
        confirmation=confirmation,
    )
    remove = docker_tools.build_docker_action(
        config,
        tmp_path,
        repo_config,
        "container_remove",
        target="api-1",
        force=True,
        confirmation=confirmation,
    )

    assert push.argv == [
        "docker",
        "image",
        "push",
        "registry.example.com/team/app:latest",
    ]
    assert remove.argv == ["docker", "container", "rm", "--force", "api-1"]


def test_run_argv_uses_shell_false_and_redacts_output(tmp_path: Path, monkeypatch) -> None:
    config, _ = make_config(tmp_path)
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="password=super-secret\n",
            stderr="",
        )

    monkeypatch.setattr(docker_tools.subprocess, "run", fake_run)
    result = docker_tools._run_argv(
        config,
        docker_tools.DockerCommandSpec(
            action="engine_version", argv=["docker", "version"], timeout_seconds=30
        ),
        tmp_path,
    )

    assert result["ok"] is True
    assert "super-secret" not in result["stdout"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["cwd"] == tmp_path


def test_capabilities_never_advertise_arbitrary_shell_or_argv(tmp_path: Path) -> None:
    config, repo_config = make_config(tmp_path)

    result = docker_tools.list_docker_capabilities(config, repo_config)

    assert result["enabled"] is True
    assert result["arbitrary_shell_supported"] is False
    assert result["arbitrary_argv_supported"] is False
    assert result["exec_profiles"][0]["command_id"] == "health"
    assert "system_prune_volumes" in result["actions"]
