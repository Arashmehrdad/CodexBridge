from __future__ import annotations

import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import codexbridge.ssh_tools as ssh_tools
from codexbridge.config import (
    AppConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
)


def make_config(
    tmp_path: Path,
    *,
    allow_transfer: bool = True,
    allow_deploy: bool = True,
    allow_admin: bool = True,
    allow_delete: bool = True,
    allow_reboot: bool = True,
) -> tuple[AppConfig, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "app.txt").write_text("hello\n", encoding="utf-8")
    deployment = SSHDeploymentProfileConfig(
        repo_name="sample",
        remote_root="/srv/app",
        compose_file="docker-compose.yml",
        compose_project_name="sample-app",
        shared_files={
            "/srv/app/shared/.env.production": ".env.production",
        },
        health_command_id="health",
    )
    host = SSHHostConfig(
        ssh_alias="sample-host",
        allowed_remote_roots=["/srv/app", "/var/log"],
        allowed_executables=["git", "docker", "curl", "python3"],
        deployment_profiles={"sample_deploy": deployment},
        command_profiles=[
            SSHCommandProfileConfig(
                command_id="health",
                argv=["curl", "-fsS", "http://127.0.0.1:3000/health"],
                timeout_seconds=60,
            )
        ],
    )
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        ssh=SSHConfig(
            enabled=True,
            executable="ssh",
            scp_executable="scp",
            allow_transfer=allow_transfer,
            allow_deploy=allow_deploy,
            allow_admin=allow_admin,
            allow_delete=allow_delete,
            allow_reboot=allow_reboot,
            hosts={"sample_host": host},
        ),
        config_dir=tmp_path,
    )
    return config, repo


def test_remote_paths_are_root_bounded_and_secret_reads_are_blocked(
    tmp_path: Path,
) -> None:
    config, _ = make_config(tmp_path)
    host = config.ssh.hosts["sample_host"]

    assert ssh_tools.validate_remote_path(host, "/srv/app/current/logs/api.log") == (
        "/srv/app/current/logs/api.log"
    )
    with pytest.raises(ValueError, match="outside configured roots"):
        ssh_tools.validate_remote_path(host, "/home/other/file.txt")
    with pytest.raises(ValueError, match="secret-like"):
        ssh_tools.validate_remote_path(host, "/srv/app/current/.env")
    assert ssh_tools.validate_remote_path(
        host, "/srv/app/shared/.env.production", sensitive=True
    ) == "/srv/app/shared/.env.production"


def test_inspection_builders_cover_service_git_and_file_debugging(
    tmp_path: Path,
) -> None:
    config, _ = make_config(tmp_path)

    service = ssh_tools.build_ssh_inspection(
        config, "sample_host", "service_status", target="api.service"
    )
    git_status = ssh_tools.build_ssh_inspection(
        config,
        "sample_host",
        "git_status",
        deployment_id="sample_deploy",
    )
    tail = ssh_tools.build_ssh_inspection(
        config,
        "sample_host",
        "file_tail",
        path="/var/log/app.log",
        tail=350,
    )

    assert service.remote_argv == [
        "systemctl",
        "status",
        "--no-pager",
        "api.service",
    ]
    assert git_status.remote_argv == [
        "git",
        "-C",
        "/srv/app",
        "status",
        "--short",
        "--branch",
    ]
    assert tail.remote_argv == ["tail", "-n", "350", "--", "/var/log/app.log"]
    assert service.writes_remote is False


def test_actions_require_gates_and_confirmation_for_high_risk_work(
    tmp_path: Path,
) -> None:
    config, _ = make_config(tmp_path, allow_delete=False)

    with pytest.raises(ValueError, match="disabled by config gate allow_delete"):
        ssh_tools.build_ssh_action(
            config,
            "sample_host",
            "remove_file",
            path="/srv/app/current/old.txt",
            confirmation=config.ssh.confirmation_token,
        )

    config.ssh.allow_delete = True
    with pytest.raises(ValueError, match="requires confirmation token"):
        ssh_tools.build_ssh_action(
            config,
            "sample_host",
            "remove_file",
            path="/srv/app/current/old.txt",
        )

    removal = ssh_tools.build_ssh_action(
        config,
        "sample_host",
        "remove_file",
        path="/srv/app/current/old.txt",
        force=True,
        confirmation=config.ssh.confirmation_token,
    )
    assert removal.remote_argv == [
        "rm",
        "-f",
        "--",
        "/srv/app/current/old.txt",
    ]
    assert removal.high_risk is True


def test_emergency_argv_is_allowlisted_and_never_accepts_shell_launchers(
    tmp_path: Path,
) -> None:
    config, _ = make_config(tmp_path)
    confirmation = config.ssh.confirmation_token

    spec = ssh_tools.build_ssh_action(
        config,
        "sample_host",
        "run_argv",
        executable="python3",
        args=["--version"],
        confirmation=confirmation,
    )
    assert spec.remote_argv == ["python3", "--version"]
    assert spec.high_risk is True

    with pytest.raises(ValueError, match="not allowlisted"):
        ssh_tools.build_ssh_action(
            config,
            "sample_host",
            "run_argv",
            executable="nc",
            args=["-z", "127.0.0.1", "80"],
            confirmation=confirmation,
        )
    with pytest.raises(ValueError, match="shell launchers"):
        ssh_tools.build_ssh_action(
            config,
            "sample_host",
            "run_argv",
            executable="bash",
            args=["-lc", "whoami"],
            confirmation=confirmation,
        )


def test_transfer_uses_scp_shell_false_and_repo_scoping(
    tmp_path: Path, monkeypatch
) -> None:
    config, repo = make_config(tmp_path)
    captured: dict = {}

    monkeypatch.setattr(ssh_tools.shutil, "which", lambda value: f"{value}.exe")

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = dict(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ssh_tools.subprocess, "run", fake_run)
    result = ssh_tools.run_ssh_transfer(
        config,
        "sample_host",
        "upload",
        repo_root=repo,
        local_path="app.txt",
        remote_path="/srv/app/incoming/app.txt",
        run_dir=tmp_path / "run",
    )

    assert result["ok"] is True
    assert result["writes_remote"] is True
    assert captured["kwargs"]["shell"] is False
    assert captured["argv"][-2] == str(repo / "app.txt")
    assert captured["argv"][-1] == "sample-host:/srv/app/incoming/app.txt"

    with pytest.raises(ValueError, match="Parent traversal"):
        ssh_tools.run_ssh_transfer(
            config,
            "sample_host",
            "upload",
            repo_root=repo,
            local_path="../outside.txt",
            remote_path="/srv/app/incoming/outside.txt",
            run_dir=tmp_path / "run",
        )


def test_download_is_saved_under_run_artifacts(tmp_path: Path, monkeypatch) -> None:
    config, repo = make_config(tmp_path)
    monkeypatch.setattr(ssh_tools.shutil, "which", lambda value: f"{value}.exe")
    monkeypatch.setattr(
        ssh_tools.subprocess,
        "run",
        lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = ssh_tools.run_ssh_transfer(
        config,
        "sample_host",
        "download",
        repo_root=repo,
        local_path="api.log",
        remote_path="/var/log/api.log",
        run_dir=run_dir,
    )

    assert result["ok"] is True
    assert result["writes_remote"] is False
    assert Path(result["local_path"]) == run_dir / "downloads" / "api.log"


def test_deployment_excludes_secrets_links_shared_files_and_activates_last(
    tmp_path: Path, monkeypatch
) -> None:
    config, repo = make_config(tmp_path)
    (repo / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=hidden\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    remote_calls: list[list[str]] = []

    def fake_remote(config, host_id, argv, *, timeout_seconds):
        remote_calls.append(list(argv))
        return {
            "ok": True,
            "argv": ["ssh", "<bounded>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    monkeypatch.setattr(ssh_tools, "_run_remote_argv", fake_remote)
    monkeypatch.setattr(
        ssh_tools,
        "_scp_base",
        lambda config, host_id, recursive: (["scp"], config.ssh.hosts[host_id]),
    )
    monkeypatch.setattr(
        ssh_tools,
        "_run_local_argv",
        lambda argv, **kwargs: {
            "ok": True,
            "argv": list(argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )

    result = ssh_tools.run_ssh_deployment(
        config,
        "sample_host",
        "sample_deploy",
        repo_root=repo,
        run_dir=run_dir,
        run_id="run123",
        confirmation=config.ssh.confirmation_token,
    )

    assert result["ok"] is True
    archive = Path(result["archive_path"])
    with tarfile.open(archive, "r:gz") as handle:
        names = handle.getnames()
    assert any(name.endswith("app.txt") for name in names)
    assert not any(".env" in name for name in names)
    assert not any("node_modules" in name for name in names)

    assert ["test", "-f", "/srv/app/shared/.env.production"] in remote_calls
    assert any(
        call[:2] == ["ln", "-sfn"] and call[1:] == [
            "-sfn",
            "/srv/app/shared/.env.production",
            "/srv/app/releases/run123/.env.production",
        ]
        for call in remote_calls
    )
    compose_call = next(call for call in remote_calls if call[:2] == ["docker", "compose"])
    assert "--project-name" in compose_call
    assert "sample-app" in compose_call
    assert "/srv/app/releases/run123" in compose_call
    health_index = next(i for i, call in enumerate(remote_calls) if call[0] == "curl")
    activate_index = next(
        i
        for i, call in enumerate(remote_calls)
        if call == ["ln", "-sfn", "/srv/app/releases/run123", "/srv/app/current"]
    )
    assert activate_index > health_index


def test_cleanup_failure_is_non_fatal_after_successful_deployment(
    tmp_path: Path, monkeypatch
) -> None:
    config, repo = make_config(tmp_path)
    (repo / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def fake_remote(config, host_id, argv, *, timeout_seconds):
        is_cleanup = argv[:2] == ["rm", "-f"]
        return {
            "ok": not is_cleanup,
            "argv": ["ssh", "<bounded>"],
            "exit_code": 1 if is_cleanup else 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "cleanup failed" if is_cleanup else "",
            "output_truncated": False,
            "error": "cleanup failed" if is_cleanup else "",
        }

    monkeypatch.setattr(ssh_tools, "_run_remote_argv", fake_remote)
    monkeypatch.setattr(
        ssh_tools,
        "_scp_base",
        lambda config, host_id, recursive: (["scp"], config.ssh.hosts[host_id]),
    )
    monkeypatch.setattr(
        ssh_tools,
        "_run_local_argv",
        lambda argv, **kwargs: {
            "ok": True,
            "argv": list(argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )

    result = ssh_tools.run_ssh_deployment(
        config,
        "sample_host",
        "sample_deploy",
        repo_root=repo,
        run_dir=run_dir,
        run_id="run456",
        confirmation=config.ssh.confirmation_token,
    )

    assert result["ok"] is True
    cleanup = next(step for step in result["steps"] if step["step"] == "cleanup_archive")
    assert cleanup["ok"] is False
    assert cleanup["non_fatal"] is True


def test_capability_listing_exposes_deployments_and_blocks_arbitrary_shell(
    tmp_path: Path,
) -> None:
    config, _ = make_config(tmp_path)
    base = {
        "ok": True,
        "enabled": True,
        "hosts": [
            {
                "host_id": "sample_host",
                "ssh_alias": "sample-host",
                "commands": [],
            }
        ],
        "error": "",
    }

    result = ssh_tools.enrich_ssh_capabilities(config, base)

    assert "git_status" in result["read_only_operations"]
    assert "docker_compose_up" in result["actions"]
    assert result["gates"]["allow_deploy"] is True
    assert result["arbitrary_shell_supported"] is False
    assert result["hosts"][0]["deployments"][0]["deployment_id"] == (
        "sample_deploy"
    )
