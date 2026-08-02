"""TaskManager interaction actions over deterministic and unavailable transport."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from soma.config import AppConfig
from soma.project_scope.store import ProjectScopeStore
from soma.tasks.manager import TaskManager
from soma.worker_substrate import (
    DeterministicInteractionTransport,
    TransportDispatchDisposition,
    UnavailableInteractionTransport,
    WorkerSubstrateStore,
)

from test_interaction_wait_transition import _enter
from test_interaction_wait_transition import waiting_fixture as _base_waiting_fixture
from test_worker_substrate_foundation import DEFAULT_RUN_ID, PROJECT_ID


@pytest.fixture()
def waiting_fixture(tmp_path):
    return _base_waiting_fixture.__wrapped__(tmp_path)


def _manager(waiting_fixture, transport):
    config = AppConfig(
        repos={},
        runs_dir=str(waiting_fixture["runs_dir"]),
    )
    return TaskManager(
        config,
        job_manager=SimpleNamespace(store=waiting_fixture["run_store"]),
        store=waiting_fixture["task_store"],
        scope_store=ProjectScopeStore(waiting_fixture["runs_dir"]),
        interaction_transport=transport,
    )


def _supply_request(waiting_fixture, *, payload="continue"):
    waiting = _enter(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    return waiting, {
        "project_id": PROJECT_ID,
        "task_id": waiting_fixture["task_id"],
        "if_state_version": task.state_version,
        "session_binding_id": waiting_fixture["binding"].session_binding_id,
        "checkpoint_id": waiting.checkpoint.checkpoint_id,
        "idempotency_key": "manager-input-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": payload,
    }


def test_unavailable_default_fails_before_command_or_message(waiting_fixture):
    _waiting, request = _supply_request(waiting_fixture)
    manager = _manager(waiting_fixture, UnavailableInteractionTransport())

    result = manager.supply_input(**request)

    assert result["ok"] is False
    assert result["error_code"] == "interaction_transport_unavailable"
    assert waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    ) == []
    assert WorkerSubstrateStore(waiting_fixture["runs_dir"]).list_messages(
        task_id=waiting_fixture["task_id"]
    ) == []


def test_deterministic_supply_input_returns_compact_no_echo_resume(waiting_fixture):
    secret = "secret-manager-input-never-echo"
    _waiting, request = _supply_request(waiting_fixture, payload=secret)
    transport = DeterministicInteractionTransport()
    manager = _manager(waiting_fixture, transport)

    result = manager.supply_input(**request)

    assert result["ok"] is True
    assert result["operation"] == "supply_input"
    assert result["error_code"] == ""
    assert result["acknowledged"] is True
    assert result["uncertain"] is False
    assert result["resumed"] is True
    assert result["transport_called"] is True
    assert result["payload_echoed"] is False
    assert result["run_id"] == DEFAULT_RUN_ID
    assert result["session_binding_id"] == request["session_binding_id"]
    assert result["checkpoint_id"] == request["checkpoint_id"]
    assert result["command_id"].startswith("taskcmd_")
    assert result["message_id"].startswith("wmessage_")
    assert result["attempt_id"].startswith("wattempt_")
    assert result["evidence_ref"].startswith("deterministic_transport:")
    assert secret not in repr(result)
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state.value == "running"
    assert len(transport.requests) == 1
    assert secret not in repr(transport.requests[0])


def test_rejected_input_preserves_durable_ids_but_is_not_success(waiting_fixture):
    _waiting, request = _supply_request(waiting_fixture)
    transport = DeterministicInteractionTransport(
        disposition=TransportDispatchDisposition.REJECTED,
        reason="deterministic rejection",
    )
    manager = _manager(waiting_fixture, transport)

    result = manager.supply_input(**request)

    assert result["ok"] is False
    assert result["error_code"] == "interaction_rejected"
    assert result["delivery"] == "rejected"
    assert result["acknowledged"] is False
    assert result["uncertain"] is False
    assert result["resumed"] is False
    assert result["command_id"].startswith("taskcmd_")
    assert result["message_id"].startswith("wmessage_")
    assert result["attempt_id"].startswith("wattempt_")
    assert result["error"] == "deterministic rejection"
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state.value == "awaiting_controller"


def test_uncertain_input_preserves_ids_and_forbids_success(waiting_fixture):
    _waiting, request = _supply_request(waiting_fixture)
    transport = DeterministicInteractionTransport(
        disposition=TransportDispatchDisposition.OUTCOME_UNKNOWN,
        reason="dispatch outcome cannot be proven",
    )
    manager = _manager(waiting_fixture, transport)

    result = manager.supply_input(**request)

    assert result["ok"] is False
    assert result["error_code"] == "interaction_uncertain"
    assert result["delivery"] == "outcome_unknown"
    assert result["acknowledged"] is False
    assert result["uncertain"] is True
    assert result["resumed"] is False
    assert result["transport_called"] is True
    assert result["command_id"].startswith("taskcmd_")
    assert result["message_id"].startswith("wmessage_")
    assert result["attempt_id"].startswith("wattempt_")
    assert "cannot be proven" in result["error"]
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state.value == "awaiting_controller"


def test_stale_version_and_wrong_checkpoint_create_nothing(waiting_fixture):
    waiting, request = _supply_request(waiting_fixture)
    manager = _manager(
        waiting_fixture,
        DeterministicInteractionTransport(),
    )

    stale = manager.supply_input(
        **{**request, "if_state_version": request["if_state_version"] + 1}
    )
    assert stale["ok"] is False
    assert stale["error_code"] == "stale_state_version"

    wrong = manager.supply_input(
        **{
            **request,
            "checkpoint_id": "taskckpt_20260802T000000Z_000000000000",
            "idempotency_key": "manager-input-wrong-checkpoint",
        }
    )
    assert wrong["ok"] is False
    assert wrong["error_code"] == "checkpoint_mismatch"

    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).checkpoint_ref == waiting.checkpoint.checkpoint_id
    assert waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    ) == []
    assert WorkerSubstrateStore(waiting_fixture["runs_dir"]).list_messages(
        task_id=waiting_fixture["task_id"]
    ) == []


def test_task_manager_and_worker_substrate_import_in_either_order() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    scripts = (
        (
            "from soma.tasks.manager import TaskManager; "
            "import soma.worker_substrate as ws; "
            "assert TaskManager; assert ws.InteractionDispatcher"
        ),
        (
            "import soma.worker_substrate as ws; "
            "from soma.tasks.manager import TaskManager; "
            "assert ws.InteractionDispatcher; assert TaskManager"
        ),
    )

    for script in scripts:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
