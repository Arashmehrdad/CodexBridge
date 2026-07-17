from __future__ import annotations

import tarfile
from hashlib import sha256
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
    SSHWatchdogConfig,
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
    assert (
        ssh_tools.validate_remote_path(
            host, "/srv/app/shared/.env.production", sensitive=True
        )
        == "/srv/app/shared/.env.production"
    )


def test_inspection_builders_cover_service_git_and_file_debugging(
    tmp_path: Path,
) -> None:
    config, _ = make_config(tmp_path)

    host_info = ssh_tools.build_ssh_inspection(config, "sample_host", "host_info")
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

    assert host_info.remote_argv == ["hostnamectl", "--static"]
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


def test_transfer_supports_explicit_endpoint_identity_and_port(
    tmp_path: Path, monkeypatch
) -> None:
    config, repo = make_config(tmp_path)
    original = config.ssh.hosts["sample_host"]
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    config.ssh.hosts["sample_host"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        port=2222,
        identity_file=str(identity),
        allowed_remote_roots=original.allowed_remote_roots,
        allowed_executables=original.allowed_executables,
        deployment_profiles=original.deployment_profiles,
        command_profiles=original.command_profiles,
    )
    captured: dict = {}
    monkeypatch.setattr(ssh_tools.shutil, "which", lambda value: f"{value}.exe")

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
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
    assert captured["argv"][captured["argv"].index("-i") + 1] == str(identity)
    assert captured["argv"][captured["argv"].index("-P") + 1] == "2222"
    assert captured["argv"][-1] == (
        "pod-user-123@ssh.runpod.io:/srv/app/incoming/app.txt"
    )


def test_transfer_rereads_file_backed_endpoint(tmp_path: Path, monkeypatch) -> None:
    config, repo = make_config(tmp_path)
    original = config.ssh.hosts["sample_host"]
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    connection_file = tmp_path / "runpod.txt"
    connection_file.write_text(
        f"ssh root@194.68.245.114 -p 22054 -i {identity}\n",
        encoding="utf-8",
    )
    config.ssh.hosts["sample_host"] = SSHHostConfig(
        connection_file=str(connection_file),
        allowed_remote_roots=original.allowed_remote_roots,
        allowed_executables=original.allowed_executables,
        deployment_profiles=original.deployment_profiles,
        command_profiles=original.command_profiles,
    )
    captured: dict = {}
    monkeypatch.setattr(ssh_tools.shutil, "which", lambda value: f"{value}.exe")

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
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
    assert captured["argv"][captured["argv"].index("-P") + 1] == "22054"
    assert "StrictHostKeyChecking=accept-new" in captured["argv"]
    assert "StrictHostKeyChecking=yes" not in captured["argv"]
    assert captured["argv"][-1] == (
        "root@194.68.245.114:/srv/app/incoming/app.txt"
    )


def test_download_is_hash_verified_and_atomically_published(
    tmp_path: Path, monkeypatch
) -> None:
    config, repo = make_config(tmp_path)
    payload = b"binary\x00payload\xff\n"
    captured: dict = {}
    monkeypatch.setattr(ssh_tools.shutil, "which", lambda value: f"{value}.exe")

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        Path(argv[-1]).write_bytes(payload)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ssh_tools.subprocess, "run", fake_run)
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

    published = run_dir / "downloads" / "api.log"
    assert result["ok"] is True
    assert result["writes_remote"] is False
    assert Path(result["local_path"]) == published
    assert published.read_bytes() == payload
    assert result["download_size_bytes"] == len(payload)
    assert result["download_sha256"] == sha256(payload).hexdigest()
    assert result["staging_relative_path"] == "downloads/api.log"
    assert result["publication"] == "atomic_replace"
    assert result["cleanup_manifest"] == {
        "version": 1,
        "cleanup_entries": ["downloads/.api.log.partial"],
        "protected_entries": ["downloads/api.log"],
    }
    assert result["cleanup_manifest_path"] == "transfer_cleanup_manifest.json"
    assert (run_dir / "transfer_cleanup_manifest.json").is_file()
    assert Path(captured["argv"][-1]).name == ".api.log.partial"
    assert not Path(captured["argv"][-1]).exists()


def test_failed_download_removes_partial_staging_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    config, repo = make_config(tmp_path)
    monkeypatch.setattr(ssh_tools.shutil, "which", lambda value: f"{value}.exe")

    def fake_run(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=1, stdout="", stderr="transfer failed")

    monkeypatch.setattr(ssh_tools.subprocess, "run", fake_run)
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

    assert result["ok"] is False
    assert result["cleanup_removed"] == ["downloads/.api.log.partial"]
    assert not (run_dir / "downloads" / ".api.log.partial").exists()
    assert not (run_dir / "downloads" / "api.log").exists()


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
        call[:2] == ["ln", "-sfn"]
        and call[1:]
        == [
            "-sfn",
            "/srv/app/shared/.env.production",
            "/srv/app/releases/run123/.env.production",
        ]
        for call in remote_calls
    )
    compose_call = next(
        call for call in remote_calls if call[:2] == ["docker", "compose"]
    )
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
    cleanup = next(
        step for step in result["steps"] if step["step"] == "cleanup_archive"
    )
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
    policy = result["execution_policy"]
    assert policy["autonomy_profiles"] == ["permissive"]
    assert policy["active_autonomy_profiles"] == ["permissive"]
    assert policy["compatibility_only_autonomy_profiles"] == []
    modes = {
        item["execution_mode"]: item for item in policy["execution_modes"]
    }
    assert modes["structured"] == {
        "execution_mode": "structured",
        "allowed_autonomy_profiles": ["permissive"],
        "active_allowed_autonomy_profiles": ["permissive"],
        "implemented": True,
    }
    assert modes["reviewed_script"]["allowed_autonomy_profiles"] == ["permissive"]
    assert modes["reviewed_script"]["implemented"] is True
    assert modes["root_shell"]["allowed_autonomy_profiles"] == ["permissive"]
    assert modes["root_shell"]["implemented"] is True

    permissive_only = ssh_tools.enrich_ssh_capabilities(config, base)
    permissive_policy = permissive_only["execution_policy"]
    assert permissive_policy["active_autonomy_profiles"] == ["permissive"]
    assert permissive_policy["compatibility_only_autonomy_profiles"] == []
    permissive_modes = {
        item["execution_mode"]: item
        for item in permissive_policy["execution_modes"]
    }
    assert permissive_modes["structured"]["active_allowed_autonomy_profiles"] == [
        "permissive"
    ]
    assert permissive_modes["reviewed_script"][
        "active_allowed_autonomy_profiles"
    ] == ["permissive"]
    assert permissive_modes["root_shell"]["active_allowed_autonomy_profiles"] == [
        "permissive"
    ]

    assert result["hosts"][0]["deployments"][0]["deployment_id"] == ("sample_deploy")
    assert result["structured_probes"] == ["environment", "gpu_telemetry"]
    assert result["hosts"][0]["watchdog"]["enforcement_mode"] == "observe_only"
    assert result["hosts"][0]["watchdog"]["can_terminate_remote_processes"] is False

    host = config.ssh.hosts["sample_host"]
    host.watchdog = SSHWatchdogConfig(
        enabled=True,
        enforcement_mode="terminate",
        allow_automatic_termination=True,
    )
    gated = ssh_tools.enrich_ssh_capabilities(config, base)
    assert gated["hosts"][0]["watchdog"]["can_terminate_remote_processes"] is False

    host.command_profiles[0].watchdog_eligible = True
    active = ssh_tools.enrich_ssh_capabilities(config, base)
    assert active["hosts"][0]["watchdog"]["can_terminate_remote_processes"] is True


def test_environment_probe_returns_structured_gpu_and_watchdog_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    config, _ = make_config(tmp_path)
    config.ssh.hosts["sample_host"].watchdog = SSHWatchdogConfig(
        enabled=True,
        max_gpu_memory_percent=40,
        max_gpu_temperature_c=70,
        max_system_memory_percent=50,
        min_disk_free_percent=30,
    )

    def success(stdout: str = "") -> dict:
        return {
            "ok": True,
            "argv": ["ssh", "<bounded>"],
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": stdout,
            "stderr": "",
            "output_truncated": False,
            "error": "",
        }

    def fake_remote(config, host_id, argv, *, timeout_seconds):
        if argv[:1] == ["uname"]:
            return success("Linux 6.8.0 x86_64\n")
        if argv[:1] == ["pwd"]:
            return success("/workspace\n")
        if argv[:2] == ["python3", "-c"] and "__import__('torch')" in argv[2]:
            return success(
                '{"version":"2.7.0","cuda_available":true,'
                '"cuda_version":"12.8","device_count":1}\n'
            )
        if argv[:2] == ["python3", "-c"]:
            return success(
                '{"executable":"/opt/venv/bin/python3","version":"3.12.3",'
                '"prefix":"/opt/venv","base_prefix":"/usr",'
                '"virtual_env":"/opt/venv","platform":"Linux",'
                '"machine":"x86_64"}\n'
            )
        if argv[:1] == ["nvcc"]:
            return success("Cuda compilation tools, release 12.8, V12.8.61\n")
        if argv[:1] == ["free"]:
            return success(
                "              total        used        free      shared  buff/cache   available\n"
                "Mem:     1000000000   700000000   100000000           0   200000000   300000000\n"
            )
        if argv[:1] == ["df"]:
            return success(
                "Filesystem 1-blocks Used Available Use% Mounted on\n"
                "/dev/root 1000000000 800000000 200000000 80% /\n"
            )
        if argv[:2] == ["nvidia-smi", "--query-gpu=index,name,uuid,driver_version,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit"]:
            return success(
                "0, NVIDIA A40, GPU-abc, 550.54.15, 46068, 23034, 23034, 81, 52, 76, 184.5, 300.0\n"
            )
        if argv[:2] == ["nvidia-smi", "--query-compute-apps=pid,process_name,gpu_uuid,used_gpu_memory"]:
            return success("1234, python3, GPU-abc, 22000\n")
        raise AssertionError(f"Unexpected probe argv: {argv}")

    monkeypatch.setattr(ssh_tools, "_run_remote_argv", fake_remote)

    result = ssh_tools.run_ssh_environment_probe(config, "sample_host")

    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["environment"]["python"]["executable"] == "/opt/venv/bin/python3"
    assert result["environment"]["torch"]["cuda_available"] is True
    assert result["gpu"]["device_count"] == 1
    assert result["gpu"]["processes"][0]["pid"] == 1234
    assert result["watchdog"]["status"] == "breached"
    assert {item["metric"] for item in result["watchdog"]["breaches"]} == {
        "gpu_memory_percent",
        "gpu_temperature_c",
        "system_memory_percent",
        "root_disk_free_percent",
    }
    assert all("stdout" not in check for check in result["checks"].values())


def test_environment_probe_is_partial_when_optional_gpu_stack_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    config, _ = make_config(tmp_path)

    def fake_remote(config, host_id, argv, *, timeout_seconds):
        required = argv[0] in {"uname", "pwd", "free", "df"}
        outputs = {
            "uname": "Linux 6.8.0 x86_64\n",
            "pwd": "/workspace\n",
            "free": (
                "              total        used        free      shared  buff/cache   available\n"
                "Mem:     1000000000   100000000   100000000           0   800000000   900000000\n"
            ),
            "df": (
                "Filesystem 1-blocks Used Available Use% Mounted on\n"
                "/dev/root 1000000000 100000000 900000000 10% /\n"
            ),
        }
        return {
            "ok": required,
            "argv": ["ssh", "<bounded>"],
            "exit_code": 0 if required else 127,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": outputs.get(argv[0], ""),
            "stderr": "not found" if not required else "",
            "output_truncated": False,
            "error": "not found" if not required else "",
        }

    monkeypatch.setattr(ssh_tools, "_run_remote_argv", fake_remote)

    result = ssh_tools.run_ssh_environment_probe(config, "sample_host")

    assert result["ok"] is True
    assert result["status"] == "partial"
    assert result["gpu"]["status"] == "unavailable"
    assert result["environment"]["python"] == {}
    assert result["error"] == ""
