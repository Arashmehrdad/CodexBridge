"""Controlled V3-2 worker gateway activation harness proofs."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from soma.run_store import RunStore
from soma.tasks.store import TaskStore
from soma.worker_authority.store import WorkerAuthorityStore
from soma.worker_gateway import activation


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text("repos: {}\nruns_dir: runs\n", encoding="utf-8")
    return config


def _accepted_owner_identity() -> dict[str, object]:
    return {
        "tool_count": activation.EXPECTED_OWNER_TOOL_COUNT,
        "tool_names": [],
        "public_schema_hash": activation.EXPECTED_OWNER_PUBLIC_SCHEMA_HASH,
    }


def test_activation_inspection_is_inert(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runs = tmp_path / "runs"
    RunStore(runs)
    store = WorkerAuthorityStore(runs)
    assert store.is_installed() is False

    inspected = activation.run_activation(config, execute=False)

    assert inspected["execute"] is False
    assert inspected["network_boundary"] == {
        "host": "127.0.0.1",
        "public_route": False,
    }
    assert inspected["worker_authority_schema"]["schema_version"] == 0
    assert store.is_installed() is False
    assert not (runs / "v3_2_worker_gateway_activation").exists()


@pytest.mark.skipif(os.name != "nt", reason="activation listener proof uses Windows netstat")
def test_disposable_activation_proves_real_loopback_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    runs = tmp_path / "runs"
    RunStore(runs)

    async def fake_owner_identity(_owner_mcp_url: str) -> dict[str, object]:
        return _accepted_owner_identity()

    monkeypatch.setattr(activation, "_owner_identity", fake_owner_identity)

    result = activation.run_activation(
        config,
        execute=True,
        owner_mcp_url="http://owner.invalid/mcp",
    )

    assert result["status"] == "completed"
    assert result["network_boundary"] == {
        "host": "127.0.0.1",
        "public_route": False,
    }
    assert result["schema_before"]["schema_version"] == 0
    assert result["migrations_applied"] == [1]
    assert result["schema_after_migration"]["up_to_date"] is True
    assert result["listener"]["addresses"] == ["127.0.0.1"]
    assert result["listener_teardown"]["closed"] is True
    assert result["proof"]["malformed_auth_http_statuses"] == [401]
    assert result["proof"]["principal_revoked_http_statuses"] == [401]
    assert result["proof"]["capability_count"] == 1
    assert result["proof"]["exact_invoke_ok"] is True
    assert result["proof"]["wrong_parameters_code"] == "parameter_contract_mismatch"
    assert result["proof"]["stale_state_code"] == "stale_task_state_version"
    assert result["proof"]["grant_revoked_code"] == "grant_revoked"
    assert result["proof"]["handler_execution_count"] == 1
    assert result["proof"]["secret_leak"] is False
    assert result["disposable_authority_revoked"] == {
        "grant": True,
        "principal": True,
    }
    assert result["owner_before"] == _accepted_owner_identity()
    assert result["owner_after"] == _accepted_owner_identity()

    backup = Path(str(result["database_backup"]["path"]))
    assert backup.exists()
    assert backup.stat().st_size == result["database_backup"]["size_bytes"]
    assert len(str(result["database_backup"]["sha256"])) == 64

    store = WorkerAuthorityStore(runs)
    assert store.is_installed() is True
    assert store.table_counts() == {
        "worker_principals": 1,
        "worker_capability_grants": 1,
        "worker_authority_revocations": 2,
    }

    task = TaskStore(runs).get_task(result["disposable_scope"]["task_id"])
    run = RunStore(runs).get_run(result["disposable_scope"]["run_id"])
    assert task.state.value == "completed"
    assert run["status"] == "completed"

    activation_root = runs / "v3_2_worker_gateway_activation"
    result_files = list(activation_root.glob("v3_2_worker_gateway_activation_*/result.json"))
    assert len(result_files) == 1
    serialized = result_files[0].read_text(encoding="utf-8")
    parsed = json.loads(serialized)
    assert parsed["proof"]["secret_leak"] is False
    assert "wa1_" not in serialized
    assert "verifier_hash" not in serialized
