from __future__ import annotations

import copy

import pytest

from soma.remote_controller_state import (
    REMOTE_CONTROLLER_STATE_VERSION,
    REMOTE_CONTROLLER_VERSION,
    build_remote_controller_state_contract,
    reconcile_remote_controller_state,
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
    assert remote["state_dir"] == f".soma/jobs/{first['execution_id']}"
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
    assert first["execution"]["resource_monitor_state"] == {
        "status": "not_started",
        "memory_policy": {
            "conservative_bytes": 40_000_000_000,
            "graceful_bytes": 45_000_000_000,
            "hard_bytes": 48_000_000_000,
        },
        "latest_sample": None,
        "latest_decision": None,
        "signals": {
            "gpu": {"status": "not_started", "devices": []},
            "disk": {"status": "not_started"},
            "heartbeat": {
                "status": "not_started",
                "controller_heartbeat_at": "",
            },
            "cuda_oom": {
                "status": "not_started",
                "detected": False,
                "marker": "",
            },
        },
        "sampled_at": "",
    }


def test_remote_controller_state_contract_preserves_no_timeout_policy() -> None:
    contract = build_remote_controller_state_contract(
        run_id="20260717T120000Z_remote_powershell_deadbeef",
        host_id="my_vps",
        command_id="remote_powershell",
        lease_generation=1,
        remote_argv=["/usr/bin/pwsh", "-Command", "Write-Output ok"],
        timeout_seconds=None,
    )

    assert contract["execution"]["timeout_seconds"] is None
    assert validate_remote_controller_state_contract(
        contract,
        run_id=contract["request_id"],
        host_id="my_vps",
        command_id="remote_powershell",
        lease_generation=1,
        remote_argv=["/usr/bin/pwsh", "-Command", "Write-Output ok"],
        timeout_seconds=None,
    ) == contract


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
    mutated["remote"]["state_path"] = ".soma/jobs/other/state.json"

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


def test_remote_controller_reconciliation_adopts_matching_live_state() -> None:
    contract = _build()
    observed = copy.deepcopy(contract)
    observed["remote"].update(
        {
            "pid": 4312,
            "pgid": 4312,
            "process_start_identity": "998877",
            "authoritative_state": "running",
            "heartbeat_at": "2026-07-17T14:00:00Z",
        }
    )

    result = reconcile_remote_controller_state(contract, observed)

    assert result["reconciliation_state"] == "adopted"
    assert result["uncertainty_state"] == "none"
    assert result["adoptable"] is True
    assert result["terminal"] is False
    assert result["remote_process"]["pid"] == 4312
    assert result["remote_process"]["start_time_ticks"] == "998877"
    assert result["remote_process"]["execution_id"] == contract["execution_id"]


def test_remote_controller_reconciliation_returns_terminal_evidence_once_ready() -> None:
    contract = _build()
    observed = copy.deepcopy(contract)
    observed["remote"].update(
        {
            "pid": 4312,
            "pgid": 4312,
            "process_start_identity": "998877",
            "authoritative_state": "completed",
            "heartbeat_at": "2026-07-17T14:01:00Z",
            "publication_state": "ready",
        }
    )
    observed["result"] = {"returncode": 0, "ended_at": "2026-07-17T14:01:00Z"}

    result = reconcile_remote_controller_state(contract, observed)

    assert result["reconciliation_state"] == "terminal_observed"
    assert result["terminal"] is True
    assert result["adoptable"] is False
    assert result["result"]["returncode"] == 0


def test_remote_controller_reconciliation_preserves_network_uncertainty() -> None:
    contract = _build()

    result = reconcile_remote_controller_state(contract, None)

    assert result["reconciliation_state"] == "uncertain"
    assert result["uncertainty_state"] == "network_or_state_unavailable"
    assert result["adoptable"] is False
    assert result["terminal"] is False


def test_remote_controller_reconciliation_rejects_identity_mismatch() -> None:
    contract = _build()
    observed = copy.deepcopy(contract)
    observed["execution_id"] = "different"

    with pytest.raises(ValueError, match="identity does not match"):
        reconcile_remote_controller_state(contract, observed)
