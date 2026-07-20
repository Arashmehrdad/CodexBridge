from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import codexbridge.ssh_commands as ssh_commands
from codexbridge.config import (
    AppConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHHostConfig,
)
from codexbridge.ssh_commands import (
    build_ssh_argv,
    build_ssh_payload_argv,
    list_ssh_capabilities,
    resolve_ssh_command_profile,
    run_ssh_command,
    run_ssh_payload,
    ssh_host_health,
    validate_ssh_alias,
    validate_ssh_command_profile,
    validate_ssh_host_id,
)


def make_config(
    tmp_path: Path,
    *,
    enabled: bool = True,
    writes_remote: bool = False,
    argv: list[str] | None = None,
) -> AppConfig:
    return AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        ssh=SSHConfig(
            enabled=enabled,
            executable="ssh",
            hosts={
                "my_vps": SSHHostConfig(
                    ssh_alias="my-vps",
                    connect_timeout_seconds=12,
                    command_profiles=[
                        SSHCommandProfileConfig(
                            command_id="status",
                            argv=argv or ["uptime"],
                            timeout_seconds=45,
                            description="Show server uptime",
                            writes_remote=writes_remote,
                        )
                    ],
                )
            },
        ),
        config_dir=tmp_path,
    )


def test_validate_host_id_and_alias() -> None:
    assert validate_ssh_host_id("my_vps") == "my_vps"
    assert validate_ssh_alias("server-name.tailnet.ts.net") == (
        "server-name.tailnet.ts.net"
    )
    with pytest.raises(ValueError, match="host_id"):
        validate_ssh_host_id("bad host")
    with pytest.raises(ValueError, match="SSH alias"):
        validate_ssh_alias("ubuntu@example.com")


def test_resolve_profile_requires_enabled_known_host_and_command(
    tmp_path: Path,
) -> None:
    disabled = make_config(tmp_path, enabled=False)
    with pytest.raises(ValueError, match="disabled"):
        resolve_ssh_command_profile(disabled, "my_vps", "status")

    config = make_config(tmp_path)
    with pytest.raises(ValueError, match="Unknown SSH host_id"):
        resolve_ssh_command_profile(config, "missing", "status")
    with pytest.raises(ValueError, match="Unknown SSH command_id"):
        resolve_ssh_command_profile(config, "my_vps", "missing")


def test_remote_profile_rejects_shell_launchers_and_metacharacters() -> None:
    shell_profile = SSHCommandProfileConfig(
        command_id="bad", argv=["bash", "-lc", "uptime"]
    )
    with pytest.raises(ValueError, match="wrapper: bash"):
        validate_ssh_command_profile(shell_profile)

    chained_profile = SSHCommandProfileConfig(
        command_id="bad", argv=["echo", "hello;whoami"]
    )
    with pytest.raises(ValueError, match="token: ;"):
        validate_ssh_command_profile(chained_profile)

    redirect_profile = SSHCommandProfileConfig(
        command_id="bad", argv=["echo", "hello>out.txt"]
    )
    with pytest.raises(ValueError, match="token: >"):
        validate_ssh_command_profile(redirect_profile)


def test_build_ssh_argv_uses_alias_and_hardened_options(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    _, profile = resolve_ssh_command_profile(config, "my_vps", "status")

    argv = build_ssh_argv(config, "my_vps", profile)

    assert argv[0] == "ssh.exe"
    assert argv[1] == "-n"
    assert argv[-2:] == ["my-vps", "uptime"]
    assert "BatchMode=yes" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "PasswordAuthentication=no" in argv
    assert "KbdInteractiveAuthentication=no" in argv
    assert "ForwardAgent=no" in argv
    assert "ClearAllForwardings=yes" in argv
    assert "PermitLocalCommand=no" in argv
    assert "ControlMaster=no" in argv
    assert "ControlPath=none" in argv
    assert "ControlPersist=no" in argv
    assert "ConnectionAttempts=1" in argv
    assert "ConnectTimeout=12" in argv


def test_build_ssh_argv_supports_explicit_endpoint_and_identity(
    tmp_path: Path, monkeypatch
) -> None:
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        port=2222,
        identity_file=str(identity),
        connect_timeout_seconds=17,
        command_profiles=[
            SSHCommandProfileConfig(
                command_id="status",
                argv=["uptime"],
                timeout_seconds=45,
                description="Show server uptime",
            )
        ],
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    _, profile = resolve_ssh_command_profile(config, "my_vps", "status")

    argv = build_ssh_argv(config, "my_vps", profile)

    assert argv[-2:] == ["pod-user-123@ssh.runpod.io", "uptime"]
    assert "-tt" in argv
    assert "-T" not in argv
    assert argv[argv.index("-i") + 1] == str(identity)
    assert argv[argv.index("-p") + 1] == "2222"
    assert "ConnectTimeout=17" in argv
    capabilities = list_ssh_capabilities(config)
    assert capabilities["hosts"][0]["ssh_alias"] == "pod-user-123@ssh.runpod.io"
    assert capabilities["hosts"][0]["connection_mode"] == "explicit"
    assert capabilities["hosts"][0]["force_pty"] is True


def test_connection_file_is_reread_for_each_ssh_operation(
    tmp_path: Path, monkeypatch
) -> None:
    first_key = tmp_path / "first_key"
    second_key = tmp_path / "second_key"
    first_key.write_text("first\n", encoding="utf-8")
    second_key.write_text("second\n", encoding="utf-8")
    connection_file = tmp_path / "runpod-ssh-command.txt"
    connection_file.write_text(
        f"ssh root@194.68.245.114 -p 22054 -i {first_key}\n",
        encoding="utf-8",
    )
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        connection_file=str(connection_file),
        command_profiles=[
            SSHCommandProfileConfig(command_id="status", argv=["uptime"])
        ],
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    _, profile = resolve_ssh_command_profile(config, "my_vps", "status")

    first = build_ssh_argv(config, "my_vps", profile)
    assert first[-2] == "root@194.68.245.114"
    assert first[first.index("-p") + 1] == "22054"
    assert first[first.index("-i") + 1] == str(first_key)
    assert "StrictHostKeyChecking=accept-new" in first
    assert "StrictHostKeyChecking=yes" not in first

    connection_file.write_text(
        f"ssh root@203.0.113.20 -p 31000 -i {second_key}\n",
        encoding="utf-8",
    )
    second = build_ssh_argv(config, "my_vps", profile)
    assert second[-2] == "root@203.0.113.20"
    assert second[second.index("-p") + 1] == "31000"
    assert second[second.index("-i") + 1] == str(second_key)
    capabilities = list_ssh_capabilities(config)
    assert capabilities["hosts"][0]["connection_mode"] == "connection_file"


def test_connection_file_rejects_noncanonical_or_unsafe_commands(
    tmp_path: Path, monkeypatch
) -> None:
    identity = tmp_path / "key"
    identity.write_text("key\n", encoding="utf-8")
    connection_file = tmp_path / "runpod.txt"
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        connection_file=str(connection_file),
        command_profiles=[
            SSHCommandProfileConfig(command_id="status", argv=["uptime"])
        ],
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")

    connection_file.write_text("ssh root@example.com -i key -p 22\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must use"):
        resolve_ssh_command_profile(config, "my_vps", "status")

    connection_file.write_text(
        f"ssh root@example.com -p 22 -i {identity};whoami\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blocked shell syntax"):
        resolve_ssh_command_profile(config, "my_vps", "status")


def test_explicit_endpoint_requires_existing_identity_file(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        identity_file=str(tmp_path / "missing-key"),
        command_profiles=[
            SSHCommandProfileConfig(command_id="status", argv=["uptime"])
        ],
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")

    with pytest.raises(ValueError, match="identity_file does not exist"):
        resolve_ssh_command_profile(config, "my_vps", "status")


def test_run_ssh_command_uses_shell_false_and_returns_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(
        tmp_path, writes_remote=True, argv=["systemctl", "restart", "app"]
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(stdout="done\n", stderr="", returncode=0)

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_command(config, "my_vps", "status")

    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert captured["kwargs"]["cwd"] == tmp_path
    assert captured["argv"][-2] == "my-vps"
    assert captured["argv"][-1] == "systemctl restart app"
    assert result["ok"] is True
    assert result["host_id"] == "my_vps"
    assert result["command_id"] == "status"
    assert result["writes_remote"] is True
    assert result["remote_state_verified"] is False


def test_runpod_proxy_command_uses_pty_stdin_and_exit_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        identity_file=str(identity),
        command_profiles=[
            SSHCommandProfileConfig(command_id="status", argv=["uptime"])
        ],
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout=(
                "RunPod banner\r\nuptime output\r\n__CODEXBRIDGE_REMOTE_EXIT__=0\r\n"
            ),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_command(config, "my_vps", "status")

    assert "-tt" in captured["argv"]
    assert "-n" not in captured["argv"]
    assert captured["argv"][-1] == "pod-user-123@ssh.runpod.io"
    assert "input" in captured["kwargs"]
    assert "stdin" not in captured["kwargs"]
    assert b"uptime\n" in captured["kwargs"]["input"]
    assert b"__CODEXBRIDGE_REMOTE_EXIT__=" in captured["kwargs"]["input"]
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "__CODEXBRIDGE_REMOTE_EXIT__=" not in result["stdout"]


def test_runpod_proxy_marker_controls_remote_exit_code(
    tmp_path: Path,
    monkeypatch,
) -> None:
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        identity_file=str(identity),
        command_profiles=[
            SSHCommandProfileConfig(command_id="status", argv=["uptime"])
        ],
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    monkeypatch.setattr(
        ssh_commands.subprocess,
        "run",
        lambda argv, **kwargs: SimpleNamespace(
            stdout="\r\n__CODEXBRIDGE_REMOTE_EXIT__=7\r\n",
            stderr="",
            returncode=0,
        ),
    )

    result = run_ssh_command(config, "my_vps", "status")

    assert result["ok"] is False
    assert result["exit_code"] == 7
    assert result["error"] == "Remote command exited with code 7"


def test_ssh_health_uses_fixed_true_command(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = ssh_host_health(config, "my_vps")

    assert captured["argv"][-2:] == ["my-vps", "true"]
    assert result["status"] == "ok"
    assert result["ok"] is True


def test_ssh_timeout_is_structured(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="partial")

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_command(config, "my_vps", "status")

    assert result["ok"] is False
    assert result["timed_out"] is True
    assert result["exit_code"] == 124
    assert "Timed out" in result["error"]


def test_capability_listing_exposes_metadata_not_remote_argv(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    result = list_ssh_capabilities(config)

    assert result["ok"] is True
    assert result["enabled"] is True
    host = result["hosts"][0]
    assert host["host_id"] == "my_vps"
    assert host["ssh_alias"] == "my-vps"
    assert host["connection_mode"] == "alias"
    command = host["commands"][0]
    assert command == {
        "command_id": "status",
        "description": "Show server uptime",
        "timeout_seconds": 45,
        "writes_remote": False,
        "watchdog_eligible": False,
    }
    assert "argv" not in command


@pytest.mark.parametrize(
    ("interpreter", "arguments", "remote_command"),
    [
        ("bash", ["--mode", "safe value"], "exec bash -s -- --mode 'safe value'"),
        ("sh", ["--mode", "safe value"], "exec sh -s -- --mode 'safe value'"),
        ("python3", ["--mode", "safe value"], "exec python3 - --mode 'safe value'"),
        (
            "pwsh",
            ["--mode", "safe value"],
            "exec pwsh -NoLogo -NoProfile -NonInteractive -File - --mode 'safe value'",
        ),
    ],
)
def test_reviewed_payload_uses_exact_stdin_and_fixed_interpreter_envelope(
    tmp_path: Path,
    monkeypatch,
    interpreter: str,
    arguments: list[str],
    remote_command: str,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "printf '%s\\n' PAYLOAD_MARKER\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(stdout="payload finished\n", stderr="", returncode=0)

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_payload(
        config,
        "my_vps",
        interpreter,
        payload,
        payload_sha256=digest,
        arguments=arguments,
        timeout_seconds=30,
        writes_remote=False,
    )

    assert captured["argv"][-2:] == ["my-vps", remote_command]
    assert captured["kwargs"]["input"] == payload.encode("utf-8")
    assert captured["kwargs"]["shell"] is False
    assert "stdin" not in captured["kwargs"]
    assert payload not in " ".join(captured["argv"])
    assert result["argv"][-2:] == ["my-vps", "<reviewed script via stdin>"]
    assert payload not in " ".join(result["argv"])
    assert result["payload_sha256"] == digest
    assert result["arguments"] == arguments
    assert result["writes_remote"] is False
    assert result["stdout"] == "payload finished\n"


def test_reviewed_bash_payload_uses_binary_stdin_without_crlf_translation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "set -euo pipefail\nprintf '%s\\n' EXACT_LF\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout=b"payload finished\n",
            stderr=b"",
            returncode=0,
        )

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_payload(
        config,
        "my_vps",
        "bash",
        payload,
        payload_sha256=digest,
        timeout_seconds=30,
        writes_remote=True,
    )

    assert captured["kwargs"]["text"] is False
    assert captured["kwargs"]["input"] == payload.encode("utf-8")
    assert b"\r" not in captured["kwargs"]["input"]
    assert result["stdout"] == "payload finished\n"
    assert result["stderr"] == ""


def test_payload_hash_mismatch_is_rejected_before_ssh_launch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        ssh_commands.subprocess,
        "run",
        lambda *args, **kwargs: calls.append("run"),
    )

    with pytest.raises(ValueError, match="SHA-256"):
        run_ssh_payload(
            config,
            "my_vps",
            "bash",
            "echo altered\n",
            payload_sha256="0" * 64,
            timeout_seconds=30,
            writes_remote=True,
        )

    assert calls == []


def test_reviewed_payload_timeout_preserves_partial_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "sleep 30\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0],
            kwargs["timeout"],
            output="partial stdout\n",
            stderr="partial stderr\n",
        )

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_payload(
        config,
        "my_vps",
        "bash",
        payload,
        payload_sha256=digest,
        timeout_seconds=2,
        writes_remote=True,
    )

    assert result["ok"] is False
    assert result["timed_out"] is True
    assert result["exit_code"] == 124
    assert result["stdout"] == "partial stdout\n"
    assert result["stderr"] == "partial stderr\n"
    assert result["error"] == "Timed out after 2s"
    assert payload not in " ".join(result["argv"])


@pytest.mark.parametrize(
    "remote_command",
    [
        "bash -lc whoami",
        "exec bash -s -- ; whoami",
        "exec python3 - $(whoami)",
        "exec pwsh -NoLogo -NoProfile -NonInteractive -File - > output.txt",
    ],
)
def test_payload_builder_rejects_nonfixed_remote_commands(
    tmp_path: Path, remote_command: str
) -> None:
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="fixed launch envelope"):
        build_ssh_payload_argv(config, "my_vps", remote_command)


def test_forced_pty_payload_is_encoded_and_echo_redacted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        identity_file=str(identity),
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "printf '%s\\n' FORCED_PTY_SECRET\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    encoded = b64encode(payload.encode("utf-8")).decode("ascii")
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout=f"{encoded}\r\n__CODEXBRIDGE_REMOTE_EXIT__=0\r\n",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_payload(
        config,
        "my_vps",
        "bash",
        payload,
        payload_sha256=digest,
        timeout_seconds=30,
        writes_remote=True,
    )

    assert captured["argv"][-1] == "pod-user-123@ssh.runpod.io"
    stdin_text = captured["kwargs"]["input"].decode("utf-8")
    assert stdin_text.startswith("stty -echo 2>/dev/null || exit 125\n")
    assert payload not in stdin_text
    assert encoded in stdin_text
    assert payload not in result["stdout"]
    assert encoded not in result["stdout"]
    assert "[REDACTED]" in result["stdout"]
    assert result["argv"][-1] == "<reviewed script via stdin>"


def test_forced_pty_pwsh_payload_quotes_arguments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    identity = tmp_path / "runpod_key"
    identity.write_text("test-key\n", encoding="utf-8")
    config = make_config(tmp_path)
    config.ssh.hosts["my_vps"] = SSHHostConfig(
        hostname="ssh.runpod.io",
        user="pod-user-123",
        identity_file=str(identity),
    )
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "Write-Output $args[0]\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    arguments = ["safe value", "--mode=test"]
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout="__CODEXBRIDGE_REMOTE_EXIT__=0\r\n",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_payload(
        config,
        "my_vps",
        "pwsh",
        payload,
        payload_sha256=digest,
        arguments=arguments,
        timeout_seconds=30,
        writes_remote=True,
    )

    assert "-tt" in captured["argv"]
    stdin_text = captured["kwargs"]["input"].decode("utf-8")
    assert (
        'pwsh -NoLogo -NoProfile -NonInteractive -File '
        '"$__codexbridge_payload" \'safe value\' --mode=test'
        in stdin_text
    )
    assert payload not in stdin_text
    assert result["interpreter"] == "pwsh"
    assert result["arguments"] == arguments
    assert result["argv"][-1] == "<reviewed script via stdin>"


def test_root_payload_verifies_effective_uid_and_strips_internal_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "printf '%s\\n' ROOT_PAYLOAD_OK\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            stdout="root payload finished\n",
            stderr="__CODEXBRIDGE_ROOT_EUID__=0\n",
            returncode=0,
        )

    monkeypatch.setattr(ssh_commands.subprocess, "run", fake_run)

    result = run_ssh_payload(
        config,
        "my_vps",
        "bash",
        payload,
        payload_sha256=digest,
        timeout_seconds=30,
        writes_remote=True,
        root_required=True,
    )

    assert "id -u" in captured["argv"][-1]
    assert captured["kwargs"]["input"] == payload.encode("utf-8")
    assert result["ok"] is True
    assert result["root_identity_verified"] is True
    assert "__CODEXBRIDGE_ROOT_EUID__" not in result["stderr"]
    assert "__CODEXBRIDGE_ROOT_EUID__" not in result["error"]
    assert result["argv"][-1] == "<root shell via stdin>"


def test_root_payload_fails_when_effective_uid_marker_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "true\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        ssh_commands.subprocess,
        "run",
        lambda argv, **kwargs: SimpleNamespace(
            stdout="",
            stderr="",
            returncode=0,
        ),
    )

    result = run_ssh_payload(
        config,
        "my_vps",
        "bash",
        payload,
        payload_sha256=digest,
        timeout_seconds=30,
        writes_remote=True,
        root_required=True,
    )

    assert result["ok"] is False
    assert result["root_identity_verified"] is False
    assert result["error"] == "Remote root identity could not be verified"


def test_root_payload_nonzero_exit_has_clean_error_after_marker_removal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = make_config(tmp_path)
    monkeypatch.setattr(ssh_commands.shutil, "which", lambda _: "ssh.exe")
    payload = "exit 7\n"
    digest = sha256(payload.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        ssh_commands.subprocess,
        "run",
        lambda argv, **kwargs: SimpleNamespace(
            stdout="",
            stderr="__CODEXBRIDGE_ROOT_EUID__=0\n",
            returncode=7,
        ),
    )

    result = run_ssh_payload(
        config,
        "my_vps",
        "bash",
        payload,
        payload_sha256=digest,
        timeout_seconds=30,
        writes_remote=True,
        root_required=True,
    )

    assert result["ok"] is False
    assert result["root_identity_verified"] is True
    assert result["error"] == "Remote command exited with code 7"
