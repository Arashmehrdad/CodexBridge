from __future__ import annotations

import copy

import pytest

from codexbridge.remote_controller_state import (
    REMOTE_CONTROLLER_STATE_VERSION,
    REMOTE_CONTROLLER_VERSION,
    build_remote_controller_state_contract,
    validate_remote_controller_state_contract,
)


def _build() -> dict:
    return build_remote_controller_state_contract(
        run_id="20260717T120000Z_ssh_monitored_command_deadbeef",
        host_id="my_vps",
        command_id="uptime",
        lease_generation=4,
        remote_argv=["python3", "-c", "print('ok')"],
        timeout_seconds=7200,
    )


def test_remote_controller_state_contract_is_deterministic_and_complete() -> None:
    first = _build()
    second = _build()

    assert first == second
    assert first["version"] == REMOTE_CONTROLLER_STATE_VERSION
    assert first["request_id"] == "20260717T120000Z_ssh_monitored_command_deadbeef"
    assert first["host_id"] == "my_vps"
    assert first["command_id"] == "uptime"
    assert first["lease_generation"] == 4
    assert len(first["execution_id"]) == 32
    assert len(first["idempotency_key"]) == 64
    assert first["controller"]["version"] == REMOTE_CONTROLLER_VERSION
    assert len(first["controller"]["fingerprint"]) == 64
    remote = first["remote"]
    assert remote["state_dir"] == f".codexbridge/jobs/{first['execution_id']}"
    assert remote["state_path"].endswith("/state.json")
    assert remote["input_path"].endswith("/input.json")
    assert remote["stdout_path"].endswith("/stdout.bin")
    assert remote["stderr_path"].endswith("/stderr.bin")
    assert remote["result_path"].endswith("/result.json")
    assert remote["authoritative_state"] == "launch_pending"
    assert remote["pid"] is None
    assert remote["pgid"] is None
    assert remote["process_start_identity"] == ""
    assert remote["heartbeat_at"] == ""
    assert remote["cancellation_requested_at"] == ""
    assert remote["cancellation_completed_at"] == ""
    assert remote["publication_state"] == "pending"
    assert first["local"]["remote_job_id"] == first["execution_id"]
    assert first["local"]["reconciliation_state"] == "not_started"
    assert first["local"]["uncertainty_state"] == "none"
    assert first["execution"]["executable_identity"] == "python3"
    assert first["execution"]["shell_identity"] == "direct_argv"
    assert first["execution"]["resource_monitor_state"] == "not_started"


def test_remote_controller_state_contract_changes_with_request_or_lease() -> None:
    baseline = _build()
    changed_lease = build_remote_controller_state_contract(
        run_id=baseline["request_id"],
        host_id="my_vps",
        command_id="uptime",
        lease_generation=5,
        remote_argv=["python3", "-c", "print('ok')"],
        timeout_seconds=7200,
    )
    changed_command = build_remote_controller_state_contract(
        run_id=baseline["request_id"],
        host_id="my_vps",
        command_id="hostname",
        lease_generation=4,
        remote_argv=["hostname"],
        timeout_seconds=7200,
    )

    assert changed_lease["execution_id"] != baseline["execution_id"]
    assert changed_lease["idempotency_key"] == baseline["idempotency_key"]
    assert changed_command["execution_id"] != baseline["execution_id"]
    assert changed_command["idempotency_key"] != baseline["idempotency_key"]


def test_remote_controller_state_contract_rejects_persisted_drift() -> None:
    contract = _build()
    mutated = copy.deepcopy(contract)
    mutated["remote"]["state_path"] = ".codexbridge/jobs/other/state.json"

    with pytest.raises(
        ValueError,
        match="Remote-controller state contract changed after acceptance",
    ):
        validate_remote_controller_state_contract(
            mutated,
            run_id=contract["request_id"],
            host_id="my_vps",
            command_id="uptime",
            lease_generation=4,
            remote_argv=["python3", "-c", "print('ok')"],
            timeout_seconds=7200,
        )

    assert validate_remote_controller_state_contract(
        contract,
        run_id=contract["request_id"],
        host_id="my_vps",
        command_id="uptime",
        lease_generation=4,
        remote_argv=["python3", "-c", "print('ok')"],
        timeout_seconds=7200,
    ) == contract
