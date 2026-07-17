from __future__ import annotations

import base64
import zlib
from pathlib import Path

import pytest

from codexbridge.remote_controller_state import build_remote_controller_state_contract

import codexbridge.ssh_watchdog as ssh_watchdog
from codexbridge.config import (
    AppConfig,
    RepoConfig,
    SSHCommandProfileConfig,
    SSHConfig,
    SSHHostConfig,
)
from codexbridge.ssh_watchdog import (
    validate_monitored_command_start,
    watchdog_termination_active,
)


def make_config(
    tmp_path: Path,
    *,
    eligible: bool = True,
    enabled: bool = True,
    mode: str = "observe_only",
    auto_terminate: bool = False,
) -> AppConfig:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        ssh=SSHConfig(
            enabled=True,
            hosts={
                "my_vps": SSHHostConfig(
                    ssh_alias="my-vps",
                    watchdog={
                        "enabled": enabled,
                        "enforcement_mode": mode,
                        "allow_automatic_termination": auto_terminate,
                    },
                    command_profiles=[
                        SSHCommandProfileConfig(
                            command_id="uptime",
                            argv=["uptime"],
                            watchdog_eligible=eligible,
                        )
                    ],
                )
            },
        ),
        config_dir=tmp_path,
    )


def test_monitored_start_requires_four_way_opt_in(tmp_path: Path) -> None:
    config = make_config(tmp_path, eligible=True, enabled=True, mode="observe_only")
    host, profile = validate_monitored_command_start(config, "my_vps", "uptime")
    assert host.watchdog.enabled is True
    assert profile.watchdog_eligible is True
    assert watchdog_termination_active(config, "my_vps", "uptime") is False

    terminating = make_config(
        tmp_path / "two",
        eligible=True,
        enabled=True,
        mode="terminate",
        auto_terminate=True,
    )
    assert watchdog_termination_active(terminating, "my_vps", "uptime") is True


def test_monitored_start_refuses_without_watchdog_or_profile_opt_in(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path, eligible=False, enabled=True)
    with pytest.raises(ValueError, match="watchdog_eligible"):
        validate_monitored_command_start(config, "my_vps", "uptime")

    disabled = make_config(tmp_path / "two", eligible=True, enabled=False)
    with pytest.raises(ValueError, match="enabled host watchdog"):
        validate_monitored_command_start(disabled, "my_vps", "uptime")


def test_encoded_controller_is_validator_safe_and_attached() -> None:
    contract = build_remote_controller_state_contract(
        run_id="run-1",
        host_id="my_vps",
        command_id="uptime",
        lease_generation=1,
        remote_argv=["python3", "-c", "print('ok')"],
        timeout_seconds=30,
    )
    source = ssh_watchdog._start_controller_source(
        ["python3", "-c", "print('ok')"],
        "START=",
        "EXIT=",
        contract,
    )

    profile = ssh_watchdog._encoded_controller_profile("controller", source, 30)

    assert profile.argv[:3] == ["python3", "-c", ssh_watchdog._CONTROLLER_LOADER]
    assert all("\n" not in argument and "\r" not in argument for argument in profile.argv)
    decoded = zlib.decompress(
        base64.b64decode("".join(profile.argv[3:]))
    ).decode("utf-8")
    assert "start_new_session=True" in decoded
    assert "stdout=sys.stdout.buffer" in decoded
    assert "stderr=sys.stderr.buffer" in decoded
    assert "atomic_json(state_path,state)" in decoded
    assert "durable_ownership" in decoded
    assert "rc=p.poll()" in decoded
    assert "os.replace(tmp,path)" in decoded
    assert "os.fsync(handle.fileno())" in decoded
    assert "stdout=subprocess.DEVNULL" not in decoded
    assert "stderr=subprocess.DEVNULL" not in decoded


def test_marker_parser_accepts_forced_pty_banner_and_trailer() -> None:
    marker = "__CODEXBRIDGE_REMOTE_TERMINATION_test__="
    output = (
        "Welcome to host\r\n"
        f"noise-prefix {marker}{{\"terminated\":true,\"identity_verified\":true}}\r\n"
        "__CODEXBRIDGE_EXIT_0__\r\n"
    )

    payload = ssh_watchdog._find_marker_payload(output, marker)

    assert payload == {"terminated": True, "identity_verified": True}


def test_unsafe_remote_identity_refuses_without_invoking_ssh(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not be called")

    monkeypatch.setattr(ssh_watchdog.subprocess, "run", unexpected_run)

    result = ssh_watchdog.terminate_remote_process_group(
        config,
        "my_vps",
        {"pid": 123, "pgid": 124, "start_time_ticks": "999"},
        grace_seconds=1,
    )

    assert result["terminated"] is False
    assert result["identity_verified"] is False
    assert "incomplete or unsafe" in result["error"]


def test_remote_state_probe_returns_persisted_state_and_result(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    contract = build_remote_controller_state_contract(
        run_id="run-1",
        host_id="my_vps",
        command_id="uptime",
        lease_generation=1,
        remote_argv=["uptime"],
        timeout_seconds=30,
    )
    observed = dict(contract)
    observed["remote"] = dict(contract["remote"])
    observed["remote"].update(
        {
            "pid": 321,
            "pgid": 321,
            "process_start_identity": "456",
            "authoritative_state": "completed",
        }
    )
    terminal = {"returncode": 0, "authoritative_state": "completed"}

    def fake_run(argv, **kwargs):
        del argv, kwargs
        marker = ssh_watchdog._marker("REMOTE_STATE", "fixed")
        return ssh_watchdog.subprocess.CompletedProcess(
            [],
            0,
            stdout=marker + ssh_watchdog.json.dumps(
                {"state": observed, "result": terminal, "error": ""},
                separators=(",", ":"),
            ),
            stderr="",
        )

    monkeypatch.setattr(ssh_watchdog.secrets, "token_hex", lambda _n: "fixed")
    monkeypatch.setattr(ssh_watchdog.subprocess, "run", fake_run)

    result = ssh_watchdog.probe_remote_controller_state(
        config, "my_vps", contract
    )

    assert result["ok"] is True
    assert result["state"] == observed
    assert result["result"] == terminal
    assert result["error"] == ""


def test_remote_state_probe_preserves_network_uncertainty(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    contract = build_remote_controller_state_contract(
        run_id="run-1",
        host_id="my_vps",
        command_id="uptime",
        lease_generation=1,
        remote_argv=["uptime"],
        timeout_seconds=30,
    )

    def timeout(*_args, **_kwargs):
        raise ssh_watchdog.subprocess.TimeoutExpired(["ssh"], 30)

    monkeypatch.setattr(ssh_watchdog.subprocess, "run", timeout)

    result = ssh_watchdog.probe_remote_controller_state(
        config, "my_vps", contract
    )

    assert result == {
        "ok": False,
        "state": None,
        "result": None,
        "error": "probe_timeout",
    }


def test_termination_controller_reverifies_identity_and_escalates() -> None:
    source = ssh_watchdog._termination_controller_source(
        {"pid": 321, "pgid": 321, "start_time_ticks": "98765"},
        5,
        "RESULT=",
    )

    assert "/proc/{pid}/stat" in source
    assert "pid!=pgid" in source
    assert 'result["error"]="remote identity mismatch"' in source
    assert "os.killpg(pgid,signal.SIGTERM)" in source
    assert "os.killpg(pgid,signal.SIGKILL)" in source
    assert "original_gone()" in source
