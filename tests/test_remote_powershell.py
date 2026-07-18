from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.job_worker import JobWorker
from codexbridge.remote_powershell import (
    bind_remote_powershell_controller_request,
    build_remote_powershell_artifact_manifest,
    build_remote_powershell_durable_input,
    build_remote_powershell_request,
    decode_remote_powershell_stdin,
    validate_remote_powershell_artifact_manifest,
    validate_remote_powershell_durable_input,
    validate_remote_powershell_request,
)
from codexbridge.run_store import RunStore


def test_remote_powershell_envelope_preserves_exact_values_and_binary_stdin() -> None:
    request = build_remote_powershell_request(
        host_id="remote_windows",
        executable_path="/opt/microsoft/powershell/7/pwsh",
        argv=["-NoProfile", "-Command", "& git -C '/tmp/a b' status --short"],
        working_directory="/tmp/a b",
        environment={"ARBITRARY_VALUE": "a=b c", "EMPTY": ""},
        stdin_bytes=b"\x00\xff\r\ninput",
        timeout_seconds=None,
    )

    assert request["argv"][-1] == "& git -C '/tmp/a b' status --short"
    assert request["working_directory"] == "/tmp/a b"
    assert request["environment"] == {"ARBITRARY_VALUE": "a=b c", "EMPTY": ""}
    assert decode_remote_powershell_stdin(request) == b"\x00\xff\r\ninput"
    assert len(request["request_fingerprint"]) == 64


def test_remote_powershell_envelope_is_deterministic_and_sensitive_to_request_changes() -> None:
    first = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-Command", "Write-Output ok"],
        environment={"B": "2", "A": "1"},
    )
    second = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-Command", "Write-Output ok"],
        environment={"A": "1", "B": "2"},
    )
    changed = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-Command", "Write-Output changed"],
        environment={"A": "1", "B": "2"},
    )

    assert first == second
    assert changed["request_fingerprint"] != first["request_fingerprint"]


@pytest.mark.parametrize(
    "path",
    ["pwsh", "/usr/bin/bash", "C:/Program Files/PowerShell/7/pwsh.exe"],
)
def test_remote_powershell_requires_absolute_remote_powershell_identity(path: str) -> None:
    with pytest.raises(ValueError, match="absolute pwsh or powershell path"):
        build_remote_powershell_request(host_id="host", executable_path=path, argv=[])


def test_remote_powershell_rejects_tampered_binary_size() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=[],
        stdin_bytes=b"abc",
    )
    request["stdin_size_bytes"] = 2

    with pytest.raises(ValueError, match="stdin size"):
        decode_remote_powershell_stdin(request)


def test_remote_powershell_worker_revalidation_rejects_fingerprint_drift() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-Command", "Write-Output ok"],
        stdin_bytes=b"input",
    )
    validate_remote_powershell_request(request)
    request["argv"][-1] = "Write-Output changed"

    with pytest.raises(ValueError, match="changed after acceptance"):
        validate_remote_powershell_request(request)


def test_remote_powershell_binding_preserves_exact_r4_execution_identity() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/opt/microsoft/powershell/7/pwsh",
        argv=["-NoProfile", "-Command", "& git status --short"],
        timeout_seconds=None,
    )

    binding = bind_remote_powershell_controller_request(
        request,
        run_id="20260718T000000Z_ssh_remote_powershell_12345678",
        lease_generation=2,
    )

    assert binding == {
        "command_id": "remote_powershell",
        "remote_argv": [
            "/opt/microsoft/powershell/7/pwsh",
            "-NoProfile",
            "-Command",
            "& git status --short",
        ],
        "timeout_seconds": None,
        "request_fingerprint": request["request_fingerprint"],
        "request_id": "20260718T000000Z_ssh_remote_powershell_12345678",
        "lease_generation": 2,
    }


def test_remote_powershell_durable_input_binds_request_and_controller_before_launch() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-NoProfile", "-Command", "Write-Output ok"],
        timeout_seconds=3600,
    )
    durable = build_remote_powershell_durable_input(
        request,
        run_id="20260718T000000Z_remote_powershell_12345678",
        lease_generation=3,
    )

    validated = validate_remote_powershell_durable_input(
        durable,
        run_id="20260718T000000Z_remote_powershell_12345678",
        lease_generation=3,
    )

    assert validated == durable
    assert durable["remote_powershell_request"] == request
    assert durable["remote_powershell_binding"]["request_fingerprint"] == request["request_fingerprint"]
    assert durable["remote_controller_state"]["execution"]["executable_identity"] == "/usr/bin/pwsh"


def test_remote_powershell_artifact_manifest_binds_remote_and_local_binary_evidence() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-Command", "[Console]::OpenStandardOutput().WriteByte(255)"],
    )
    durable = build_remote_powershell_durable_input(
        request,
        run_id="20260718T000000Z_remote_powershell_artifacts",
        lease_generation=4,
    )
    manifest = durable["remote_powershell_artifact_manifest"]

    assert validate_remote_powershell_artifact_manifest(
        manifest,
        run_id="20260718T000000Z_remote_powershell_artifacts",
        lease_generation=4,
        controller_state=durable["remote_controller_state"],
    ) == manifest
    assert manifest["execution_id"] == durable["remote_controller_state"]["execution_id"]
    assert manifest["streams"] == [
        {
            "stream": "stdout",
            "remote_path": durable["remote_controller_state"]["remote"]["stdout_path"],
            "local_relative_path": "artifacts/remote-stdout.bin",
            "classification": "protected_evidence",
            "transfer_encoding": "binary",
            "publication_state": "pending",
        },
        {
            "stream": "stderr",
            "remote_path": durable["remote_controller_state"]["remote"]["stderr_path"],
            "local_relative_path": "artifacts/remote-stderr.bin",
            "classification": "protected_evidence",
            "transfer_encoding": "binary",
            "publication_state": "pending",
        },
    ]


def test_remote_powershell_artifact_manifest_rejects_path_drift() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=[],
    )
    durable = build_remote_powershell_durable_input(
        request,
        run_id="20260718T000000Z_remote_powershell_artifacts",
        lease_generation=1,
    )
    manifest = dict(durable["remote_powershell_artifact_manifest"])
    manifest["streams"] = [dict(item) for item in manifest["streams"]]
    manifest["streams"][0]["local_relative_path"] = "../stdout.bin"

    with pytest.raises(ValueError, match="artifact manifest changed"):
        validate_remote_powershell_artifact_manifest(
            manifest,
            run_id="20260718T000000Z_remote_powershell_artifacts",
            lease_generation=1,
            controller_state=durable["remote_controller_state"],
        )


def test_remote_powershell_worker_dispatches_exact_controller_inputs(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "ssh:",
                "  enabled: true",
                "  hosts:",
                "    remote_windows:",
                "      ssh_alias: remote-windows",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260718T000000Z_remote_powershell_deadbeef"
    request = build_remote_powershell_request(
        host_id="remote_windows",
        executable_path="/opt/microsoft/powershell/7/pwsh",
        argv=["-NoProfile", "-Command", "[Console]::OpenStandardInput().ReadByte()"],
        working_directory="/tmp/a b",
        environment={"ARBITRARY_VALUE": "a=b c"},
        stdin_bytes=b"\x00\xffinput",
        timeout_seconds=None,
    )
    durable = build_remote_powershell_durable_input(
        request,
        run_id=run_id,
        lease_generation=1,
    )
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="ssh:remote_windows",
        tool="remote_powershell",
        run_dir=run_dir,
        input_data=durable,
    )
    captured: dict = {}

    def execute_remote(config, host_id, command_id, **kwargs):
        del config
        captured.update(host_id=host_id, command_id=command_id, kwargs=kwargs)
        return {
            "ok": True,
            "status": "completed",
            "exit_code": 0,
            "timed_out": False,
            "stdout": "remote powershell finished\n",
            "stderr": "",
            "host_id": host_id,
            "ssh_alias": "remote-windows",
            "command_id": command_id,
            "writes_remote": True,
            "watchdog_mode": "observe_only",
            "automatic_termination_active": False,
            "remote_process": {"pid": 101, "pgid": 101},
            "remote_exit_confirmed": True,
            "watchdog_samples": [],
            "termination": {},
            "safety_failure": False,
            "output_truncated": False,
            "error": "",
            "argv": ["ssh.exe", "remote-windows"],
        }

    monkeypatch.setattr("codexbridge.job_worker.start_monitored_ssh_command", execute_remote)

    assert JobWorker(config_path, run_id).execute() == 0
    result = store.get_run(run_id)["result"]
    assert result["tool"] == "remote_powershell"
    assert result["request_fingerprint"] == request["request_fingerprint"]
    assert captured["host_id"] == "remote_windows"
    assert captured["command_id"] == "remote_powershell"
    assert captured["kwargs"]["remote_argv"] == [
        "/opt/microsoft/powershell/7/pwsh",
        *request["argv"],
    ]
    assert captured["kwargs"]["working_directory"] == "/tmp/a b"
    assert captured["kwargs"]["environment"] == {"ARBITRARY_VALUE": "a=b c"}
    assert captured["kwargs"]["stdin_bytes"] == b"\x00\xffinput"
    assert captured["kwargs"]["timeout_seconds"] is None


def test_remote_powershell_durable_input_rejects_controller_drift() -> None:
    request = build_remote_powershell_request(
        host_id="host",
        executable_path="/usr/bin/pwsh",
        argv=["-Command", "Write-Output ok"],
        timeout_seconds=60,
    )
    durable = build_remote_powershell_durable_input(
        request,
        run_id="20260718T000000Z_remote_powershell_12345678",
        lease_generation=1,
    )
    durable["remote_controller_state"]["execution"]["executable_identity"] = "/usr/bin/bash"

    with pytest.raises(ValueError, match="durable input changed"):
        validate_remote_powershell_durable_input(
            durable,
            run_id="20260718T000000Z_remote_powershell_12345678",
            lease_generation=1,
        )
