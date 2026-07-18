from __future__ import annotations

import pytest

from codexbridge.remote_powershell import (
    bind_remote_powershell_controller_request,
    build_remote_powershell_durable_input,
    build_remote_powershell_request,
    decode_remote_powershell_stdin,
    validate_remote_powershell_durable_input,
    validate_remote_powershell_request,
)


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
