"""Public task_action contracts for steer and supply_input."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

import soma.server as server
from soma.cf1_gateway_operation_inventory import operation_names_by_gateway
from soma.gateway_models import TaskActionRequest
from soma.tasks.projections import task_capabilities


ADAPTER = TypeAdapter(TaskActionRequest)


def _steer_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "operation": "steer",
        "project_id": "proj_11111111-1111-1111-1111-111111111111",
        "task_id": "task_20260802T190000Z_aaaaaaaaaaaa",
        "if_state_version": 3,
        "session_binding_id": "wsession_20260802T190000Z_bbbbbbbbbbbb",
        "idempotency_key": "public-steer-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "focus on the bounded result",
    }
    payload.update(overrides)
    return payload


def _input_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "operation": "supply_input",
        "project_id": "proj_11111111-1111-1111-1111-111111111111",
        "task_id": "task_20260802T190000Z_aaaaaaaaaaaa",
        "if_state_version": 4,
        "session_binding_id": "wsession_20260802T190000Z_bbbbbbbbbbbb",
        "checkpoint_id": "taskckpt_20260802T190000Z_cccccccccccc",
        "idempotency_key": "public-input-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "continue",
    }
    payload.update(overrides)
    return payload


def test_discriminated_models_require_exact_interaction_identity() -> None:
    steer = ADAPTER.validate_python(_steer_payload())
    supplied = ADAPTER.validate_python(_input_payload())

    assert steer.operation == "steer"
    assert steer.checkpoint_id == ""
    assert supplied.operation == "supply_input"
    assert supplied.checkpoint_id.startswith("taskckpt_")

    for field in (
        "project_id",
        "task_id",
        "session_binding_id",
        "idempotency_key",
        "sender_ref",
        "recipient_ref",
        "payload",
    ):
        invalid = _steer_payload()
        invalid[field] = ""
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(invalid)

    missing_checkpoint = _input_payload()
    missing_checkpoint.pop("checkpoint_id")
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(missing_checkpoint)


def test_payload_and_response_budget_are_bounded() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_steer_payload(payload="x" * 1_000_001))
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_input_payload(response_budget_bytes=65_537))
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_steer_payload(unexpected=True))


def test_server_routes_steer_without_echoing_payload(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    secret = "secret-steer-payload-never-echo"

    class FakeManager:
        def steer_task(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(dict(kwargs))
            return {
                "ok": True,
                "operation": "steer",
                "message_id": "wmessage_20260802T190000Z_dddddddddddd",
                "attempt_id": "wattempt_20260802T190000Z_eeeeeeeeeeee",
                "payload_echoed": False,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: object())
    monkeypatch.setattr(server, "get_task_manager", lambda *_args: FakeManager())

    request = ADAPTER.validate_python(_steer_payload(payload=secret))
    result = server.task_action(request)

    assert len(calls) == 1
    assert calls[0]["payload"] == secret
    assert calls[0]["budget"] == 12 * 1024
    assert result["payload_echoed"] is False
    assert secret not in repr(result)


def test_server_routes_supply_input_with_exact_checkpoint(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    secret = "secret-input-payload-never-echo"

    class FakeManager:
        def supply_input(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(dict(kwargs))
            return {
                "ok": True,
                "operation": "supply_input",
                "checkpoint_id": kwargs["checkpoint_id"],
                "payload_echoed": False,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: object())
    monkeypatch.setattr(server, "get_task_manager", lambda *_args: FakeManager())

    request = ADAPTER.validate_python(_input_payload(payload=secret))
    result = server.task_action(request)

    assert len(calls) == 1
    assert calls[0]["checkpoint_id"] == request.checkpoint_id
    assert calls[0]["payload"] == secret
    assert result["checkpoint_id"] == request.checkpoint_id
    assert secret not in repr(result)


def test_capabilities_and_cf1_inventory_publish_the_same_commands() -> None:
    capabilities = task_capabilities(schema_state={})
    commands = capabilities["version_guarded_commands"]
    assert "steer" in commands
    assert "supply_input" in commands
    assert capabilities["interaction"]["production_transport_default"] == (
        "unavailable"
    )
    assert capabilities["interaction"]["payload_echoed"] is False

    operation_names = operation_names_by_gateway()["task_action"]
    assert "steer" in operation_names
    assert "supply_input" in operation_names
