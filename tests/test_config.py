from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from soma.config import (
    AppConfig,
    CloudflareConfig,
    CloudflareProfileConfig,
    DockerConfig,
    DockerExecProfileConfig,
    ExecutableProfileConfig,
    LocalModelConfig,
    ParallelExecutionConfig,
    RepoConfig,
    TradingConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHDeploymentProfileConfig,
    SSHHostConfig,
    SSHWatchdogConfig,
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
    assert config.repos["stream_alpha"].commit_mode == "explicit_only"
    assert config.repos["stream_alpha"].allow_push is False
    assert config.repos["stream_alpha"].refuse_unrelated_staged_files is True
    assert config.repos["stream_alpha"].require_commit_report is True
    assert config.supervisors.default_autonomy_profile == "permissive"
    assert config.supervisors.effective_profile().max_plan_tier == 3
    assert config.supervisors.effective_profile().max_implementation_tier == 3
    powershell = config.executable_profiles["powershell"]
    assert powershell.profile_id == "powershell"
    assert powershell.enabled is False
    assert powershell.executable_path == "C:/Program Files/PowerShell/7/pwsh.exe"
    assert powershell.autonomy_profile == "permissive"
    assert powershell.unrestricted_argv is True
    assert powershell.cancellation_policy == "process_tree"
    hermes_python = config.executable_profiles["hermes_python"]
    assert hermes_python.profile_id == "hermes_python"
    assert hermes_python.enabled is False
    assert hermes_python.executable_path == "D:/Github/Soma/.venv/Scripts/python.exe"
    assert hermes_python.autonomy_profile == "permissive"
    assert hermes_python.environment_policy == "arbitrary"
    assert hermes_python.unrestricted_environment is True
    assert hermes_python.stdin_mode == "text"
    assert hermes_python.cancellation_policy == "process_tree"
    assert config.parallel_execution.enabled is False
    assert config.parallel_execution.max_concurrent_powershell is None
    assert config.parallel_execution.default_mode == "all_at_once"
    assert config.trading.enabled is False
    assert config.trading.provider == "mt5"
    assert config.trading.account_environment == "demo"
    assert config.trading.symbol == "BITCOIN_i"
    assert config.trading.maximum_tick_age_seconds == 120
    assert config.ssh.enabled is False
    assert config.ssh.active_autonomy_profiles == ["permissive"]
    assert config.docker.enabled is False
    assert config.docker.executable == "docker"
    assert config.cloudflare.enabled is False
    assert config.cloudflare.token_env == "CLOUDFLARE_API_TOKEN"
    assert config.cloudflare.allow_turnstile_write is False
    assert config.cloudflare.allow_turnstile_secret_rotation is False
    assert config.cloudflare.allow_turnstile_delete is False
    production = config.cloudflare.profiles["production"]
    assert production.zone_name == "example.com"
    assert production.turnstile.secret_destination is not None
    assert production.turnstile.secret_destination.path == ".env.production"
    assert production.turnstile.secret_destination.variable == "TURNSTILE_SECRET_KEY"
    assert config.ssh.hosts["my_vps"].ssh_alias == "my-vps"
    assert [
        profile.command_id for profile in config.ssh.hosts["my_vps"].command_profiles
    ] == ["health", "uptime", "restart_app"]
    watchdog = config.ssh.hosts["my_vps"].watchdog
    assert watchdog.enabled is False
    assert watchdog.enforcement_mode == "observe_only"
    assert watchdog.allow_automatic_termination is False
    assert watchdog.poll_interval_seconds == 30
    assert watchdog.max_gpu_memory_percent == 95


def test_config_defaults_to_permissive_supervisor_profile(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    assert config.repos["sample"].commit_mode == "explicit_only"
    assert config.repos["sample"].allow_push is False
    assert config.repos["sample"].refuse_unrelated_staged_files is True
    assert config.repos["sample"].require_commit_report is True
    assert config.supervisors.default_autonomy_profile == "permissive"
    assert set(config.supervisors.autonomy_profiles) == {
        "permissive",
        "balanced",
        "conservative",
    }
    assert config.supervisors.effective_profile().stop_on_requires_human is True
    assert config.supervisors.effective_profile().max_plan_tier == 3
    assert config.supervisors.effective_profile().max_implementation_tier == 3
    assert config.supervisors.notifications.enabled is True
    assert config.supervisors.notifications.file.enabled is False
    assert config.supervisors.notifications.webhook.enabled is False
    assert config.supervisors.notifications.windows_toast.enabled is False
    assert config.local_model.enabled is False
    assert config.local_model.base_url == "http://localhost:11434/v1"
    assert config.local_model.model == "llama3.2"
    assert config.return_loop.return_loop_enabled is True
    assert config.return_loop.conversation_target == "soma_gpt"
    assert config.memory.memory_enabled is True
    assert (
        config.resolve_memory_db_path()
        == tmp_path / "runs" / "memory" / "project_memory.sqlite3"
    )
    assert config.autonomy.autonomy_enabled is True
    assert config.autonomy.autonomy_default_profile == "balanced"
    assert config.resolve_approval_store_path() == tmp_path / "runs" / "approvals"
    assert config.external_coder.external_coder_handoff_enabled is True
    assert config.external_coder.external_coder_require_policy_approval is True
    assert (
        config.resolve_external_coder_handoff_dir()
        == tmp_path / "runs" / "external_coder_handoffs"
    )


def test_executable_profile_contract_accepts_permissive_powershell() -> None:
    profile = ExecutableProfileConfig(
        profile_id="powershell",
        enabled=True,
        executable_path=r"C:\Program Files\PowerShell\7\pwsh.exe",
        working_directory_policy="arbitrary",
        environment_policy="arbitrary",
        stdin_mode="bytes",
        stdout_mode="protected_artifact",
        stderr_mode="protected_artifact",
        timeout_seconds=None,
        allow_no_timeout=True,
        unrestricted_argv=True,
        unrestricted_paths=True,
        unrestricted_environment=True,
        unrestricted_network=True,
        unrestricted_child_processes=True,
    )

    assert profile.target == "local"
    assert profile.autonomy_profile == "permissive"
    assert profile.timeout_seconds is None
    assert profile.allow_no_timeout is True
    assert profile.unrestricted_argv is True


def test_executable_profile_contract_rejects_unsafe_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="executable_path must be absolute"):
        ExecutableProfileConfig(
            profile_id="powershell",
            executable_path="pwsh.exe",
        )
    with pytest.raises(ValidationError, match="allow_no_timeout"):
        ExecutableProfileConfig(
            profile_id="powershell",
            executable_path=str(tmp_path / "pwsh.exe"),
            timeout_seconds=None,
        )
    with pytest.raises(ValidationError, match="requires fixed_working_directory"):
        ExecutableProfileConfig(
            profile_id="powershell",
            executable_path=str(tmp_path / "pwsh.exe"),
            working_directory_policy="fixed",
        )
    with pytest.raises(ValidationError, match="mapping key must match"):
        AppConfig(
            repos={"sample": RepoConfig(path=str(tmp_path))},
            executable_profiles={
                "pwsh": ExecutableProfileConfig(
                    profile_id="powershell",
                    executable_path=str(tmp_path / "pwsh.exe"),
                )
            },
            config_dir=tmp_path,
        )


def test_parallel_execution_config_supports_unbounded_or_bounded_powershell() -> None:
    unbounded = ParallelExecutionConfig(enabled=True, max_concurrent_powershell=None)
    bounded = ParallelExecutionConfig(enabled=True, max_concurrent_powershell=8)

    assert unbounded.autonomy_profile == "permissive"
    assert unbounded.max_concurrent_powershell is None
    assert bounded.max_concurrent_powershell == 8

    with pytest.raises(ValidationError):
        ParallelExecutionConfig(enabled=True, max_concurrent_powershell=0)
    with pytest.raises(ValidationError):
        ParallelExecutionConfig(enabled=True, autonomy_profile="balanced")


def test_trading_config_is_demo_only_and_requires_absolute_terminal_path() -> None:
    config = TradingConfig(
        enabled=True,
        terminal_path=r"C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        symbol=" BITCOIN_i ",
        provider_utc_offset_seconds=10_800,
        maximum_tick_age_seconds=90,
    )

    assert config.provider == "mt5"
    assert config.account_environment == "demo"
    assert config.symbol == "BITCOIN_i"
    assert config.provider_utc_offset_seconds == 10_800
    assert config.maximum_tick_age_seconds == 90

    with pytest.raises(ValidationError, match="terminal_path must be absolute"):
        TradingConfig(enabled=True, terminal_path="terminal64.exe")
    with pytest.raises(ValidationError):
        TradingConfig(account_environment="live")
    with pytest.raises(ValidationError, match="symbol must not be empty"):
        TradingConfig(symbol="   ")


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


def test_ssh_active_autonomy_profiles_are_canonical_and_unique() -> None:
    config = SSHConfig(active_autonomy_profiles=["permissive"])
    assert config.active_autonomy_profiles == ["permissive"]
    assert config.autonomy_profile_migration_report() == {
        "migration_id": "ssh_active_autonomy_profiles_v1",
        "migration_required": False,
        "configured_profiles": ["permissive"],
        "legacy_profiles": [],
        "target_profiles": ["permissive"],
        "rollback": {"active_autonomy_profiles": ["permissive"]},
        "replacement": {"active_autonomy_profiles": ["permissive"]},
        "preserves_durable_history": True,
    }

    with pytest.raises(ValidationError, match="permissive"):
        SSHConfig(active_autonomy_profiles=["balanced", "permissive"])
    with pytest.raises(ValidationError):
        SSHConfig(active_autonomy_profiles=["permissive", "permissive"])
    with pytest.raises(ValidationError):
        SSHConfig(active_autonomy_profiles=[])
    with pytest.raises(ValidationError):
        SSHConfig(active_autonomy_profiles=["chatgpt_delegated"])


def test_repo_command_profile_migration_report_is_deterministic(tmp_path: Path) -> None:
    profile = {
        "command_id": "eslint",
        "argv": ["node", "node_modules/eslint/bin/eslint.js", "."],
        "timeout_seconds": 600,
        "description": "Run lint",
        "writes_files": False,
        "async_only": True,
    }
    retained = {
        "command_id": "service_restart",
        "argv": ["pwsh.exe", "-File", "restart.ps1"],
        "timeout_seconds": 180,
    }
    config = RepoConfig(
        path=str(tmp_path),
        command_profiles=[profile, retained],
    )

    assert config.command_profile_migration_report("sample") == {
        "migration_id": "ordinary_validation_command_profiles_v1",
        "migration_required": True,
        "repo_name": "sample",
        "candidate_command_ids": ["eslint"],
        "candidates": [
            {
                "command_id": "eslint",
                "configured_profile": profile,
                "replacement": {
                    "operation": "powershell",
                    "repo_name": "sample",
                    "working_directory": str(tmp_path),
                    "argv": [
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "& 'node' 'node_modules/eslint/bin/eslint.js' '.'; exit $LASTEXITCODE",
                    ],
                    "timeout_seconds": 600,
                },
            }
        ],
        "rollback": {"command_profiles": [profile, retained]},
        "preserves_durable_history": True,
    }


def test_repo_command_profile_migration_report_escapes_single_quotes(
    tmp_path: Path,
) -> None:
    config = RepoConfig(
        path=str(tmp_path),
        command_profiles=[
            {
                "command_id": "frontend_validate",
                "argv": ["node", "odd'file.js"],
                "timeout_seconds": 60,
            }
        ],
    )

    report = config.command_profile_migration_report("sample")
    assert report["candidates"][0]["replacement"]["argv"][-1] == (
        "& 'node' 'odd''file.js'; exit $LASTEXITCODE"
    )


def test_ssh_host_rejects_duplicate_command_ids() -> None:
    profile = SSHCommandProfileConfig(command_id="status", argv=["uptime"])
    with pytest.raises(ValidationError, match="unique"):
        SSHHostConfig(
            ssh_alias="my-vps",
            command_profiles=[profile, profile.model_copy()],
        )


def test_ssh_command_profile_supports_remote_runs_beyond_one_hour() -> None:
    profile = SSHCommandProfileConfig(
        command_id="r4_live_process_tree",
        argv=["python3", "/var/tmp/soma-r4/r4_parent.py"],
        timeout_seconds=4500,
        watchdog_eligible=True,
    )

    assert profile.timeout_seconds == 4500
    with pytest.raises(ValidationError):
        SSHCommandProfileConfig(
            command_id="too_long",
            argv=["python3", "job.py"],
            timeout_seconds=86401,
        )


def test_ssh_host_supports_alias_file_or_explicit_endpoint(tmp_path: Path) -> None:
    direct = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        port=2222,
        identity_file=str(tmp_path / "runpod_key"),
    )
    assert direct.ssh_alias == ""
    assert direct.hostname == "ssh.runpod.io"
    assert direct.user == "pod-user-123"
    assert direct.port == 2222
    assert direct.force_pty is False

    forced = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        identity_file=str(tmp_path / "runpod_key"),
        force_pty=True,
    )
    assert forced.force_pty is True

    connection_file = SSHHostConfig(connection_file=str(tmp_path / "runpod.txt"))
    assert connection_file.connection_file == str(tmp_path / "runpod.txt")

    with pytest.raises(ValidationError, match="exactly one"):
        SSHHostConfig(
            ssh_alias="runpod-wan",
            hostname="ssh.runpod.io",
            user="pod-user-123",
            identity_file=str(tmp_path / "runpod_key"),
        )
    with pytest.raises(ValidationError, match="exactly one"):
        SSHHostConfig()
    with pytest.raises(ValidationError, match="Explicit SSH host requires"):
        SSHHostConfig(hostname="ssh.runpod.io", user="pod-user-123")
    with pytest.raises(ValidationError, match="exactly one"):
        SSHHostConfig(
            ssh_alias="runpod-wan",
            connection_file=str(tmp_path / "runpod.txt"),
        )
    with pytest.raises(ValidationError, match="absolute path"):
        SSHHostConfig(connection_file="relative/runpod.txt")
    with pytest.raises(ValidationError, match="absolute path"):
        SSHHostConfig(
            hostname="ssh.runpod.io",
            user="pod-user-123",
            identity_file="relative/key",
        )
    with pytest.raises(ValidationError, match="SSH hostname"):
        SSHHostConfig(
            hostname="bad host",
            user="pod-user-123",
            identity_file=str(tmp_path / "runpod_key"),
        )


def test_ssh_watchdog_config_is_bounded_and_observe_only() -> None:
    watchdog = SSHWatchdogConfig(
        enabled=True,
        max_gpu_memory_percent=80,
        max_gpu_temperature_c=85,
        max_system_memory_percent=90,
        min_disk_free_percent=10,
    )

    assert watchdog.enabled is True
    assert watchdog.enforcement_mode == "observe_only"
    assert watchdog.poll_interval_seconds == 30
    assert watchdog.consecutive_breaches == 2
    with pytest.raises(ValidationError):
        SSHWatchdogConfig(max_gpu_memory_percent=101)
    with pytest.raises(ValidationError):
        SSHWatchdogConfig(max_gpu_temperature_c=0)
    with pytest.raises(ValidationError):
        SSHWatchdogConfig(min_disk_free_percent=100)
    terminate = SSHWatchdogConfig(enforcement_mode="terminate")
    assert terminate.enforcement_mode == "terminate"
    with pytest.raises(ValidationError):
        SSHWatchdogConfig(poll_interval_seconds=4)
    with pytest.raises(ValidationError):
        SSHWatchdogConfig(consecutive_breaches=11)
    with pytest.raises(ValidationError):
        SSHWatchdogConfig(termination_grace_seconds=31)


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
        allowed_turnstile_sitekeys=["0x" + ("a" * 30)],
        turnstile={
            "secret_destination": {
                "type": "env_file",
                "path": ".env.production",
                "variable": "TURNSTILE_SECRET_KEY",
            }
        },
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
    assert config.allow_turnstile is False
    assert config.allow_turnstile_write is False
    assert config.allow_turnstile_secret_rotation is False
    assert config.allow_turnstile_delete is False
    assert profile.zone_name == "example.com"
    assert profile.allowed_dns_names == ["api.example.com"]
    assert profile.allowed_turnstile_sitekeys == ["0x" + ("a" * 30)]
    assert profile.turnstile.secret_destination is not None
    assert profile.turnstile.secret_destination.type == "env_file"
    assert profile.turnstile.secret_destination.path == ".env.production"
    assert profile.turnstile.secret_destination.variable == "TURNSTILE_SECRET_KEY"

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
    with pytest.raises(ValidationError, match="allowed_turnstile_sitekeys"):
        CloudflareProfileConfig(allowed_turnstile_sitekeys=["bad sitekey"])
    with pytest.raises(
        ValidationError, match="allowed_turnstile_sitekeys must be unique"
    ):
        CloudflareProfileConfig(allowed_turnstile_sitekeys=["sitekey", "sitekey"])
    for unsafe_path in ("../outside.env", "/outside.env", "file:stream"):
        with pytest.raises(ValidationError, match="safe repository-relative path"):
            CloudflareProfileConfig(
                turnstile={
                    "secret_destination": {
                        "type": "env_file",
                        "path": unsafe_path,
                        "variable": "TURNSTILE_SECRET_KEY",
                    }
                }
            )
    with pytest.raises(ValidationError, match="environment variable name"):
        CloudflareProfileConfig(
            turnstile={
                "secret_destination": {
                    "type": "env_file",
                    "path": ".env.production",
                    "variable": "bad-variable",
                }
            }
        )
    with pytest.raises(ValidationError, match="Input should be 'env_file'"):
        CloudflareProfileConfig(
            turnstile={
                "secret_destination": {
                    "type": "stdout",
                    "path": ".env.production",
                    "variable": "TURNSTILE_SECRET_KEY",
                }
            }
        )

    repo = RepoConfig(path=".", cloudflare_profiles=["production"])
    assert repo.cloudflare_profiles == ["production"]
    with pytest.raises(ValidationError, match="profile IDs assigned"):
        RepoConfig(path=".", cloudflare_profiles=["bad profile"])
    with pytest.raises(ValidationError, match="unique per repository"):
        RepoConfig(path=".", cloudflare_profiles=["production", "production"])


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
        repos={"soma": RepoConfig(path=str(repo))}, config_dir=tmp_path
    )

    resolved_name, resolved_repo = resolve_repo_config(config, "Soma")

    assert resolved_name == "soma"
    assert resolved_repo.path == str(repo)
    assert resolve_repo(config, "Soma") == repo.resolve()


def test_repo_commit_policy_fields_accept_overrides() -> None:
    repo = RepoConfig(
        path=".",
        commit_mode="all_allowed",
        allow_push=False,
        refuse_unrelated_staged_files=False,
        require_commit_report=False,
    )

    assert repo.commit_mode == "all_allowed"
    assert repo.allow_push is False
    assert repo.refuse_unrelated_staged_files is False
    assert repo.require_commit_report is False
