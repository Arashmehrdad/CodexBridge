from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from soma.continuations import ContinuationService
from soma.gateway_models import ContinuationActionRequest, ContinuationQueryRequest
from soma.cf1_gateway_operation_inventory import operation_names_by_gateway
import soma.server as server


QUERY = TypeAdapter(ContinuationQueryRequest)
ACTION = TypeAdapter(ContinuationActionRequest)


def _service(tmp_path: Path) -> ContinuationService:
    return ContinuationService(tmp_path / "runs")


def test_c3_gateway_models_are_strict_discriminated_and_context_ref_is_not_auth() -> None:
    assert QUERY.validate_python({"operation": "capabilities"}).operation == "capabilities"
    assert QUERY.validate_python({"operation": "list"}).limit == 20
    assert QUERY.validate_python(
        {"operation": "resume", "continuation_id": "cont_20260815T120000Z_abcdef123456"}
    ).effect_limit == 20
    with pytest.raises(ValidationError):
        QUERY.validate_python(
            {
                "operation": "status",
                "continuation_id": "cont_20260815T120000Z_abcdef123456",
                "cursor": "cross-operation-field",
            }
        )
    with pytest.raises(ValidationError):
        ACTION.validate_python(
            {
                "operation": "open",
                "controller_request_id": "open-invalid",
                "provenance_class": "controller_submitted_text",
            }
        )
    with pytest.raises(ValidationError):
        ACTION.validate_python(
            {
                "operation": "open",
                "controller_request_id": "open-invalid-both",
                "instruction_text": "one",
                "instruction_ref": "two",
                "provenance_class": "controller_submitted_text",
            }
        )
    schema_text = json.dumps(TypeAdapter(ContinuationActionRequest).json_schema())
    assert "not an authorization token" in schema_text


def test_c3_public_discovery_is_flat_and_operation_inventory_is_exact() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    by_name = {tool.name: tool.to_mcp_tool().model_dump(mode="json") for tool in tools}
    assert "continuation_query" in by_name
    assert "continuation_action" in by_name
    assert "request" not in by_name["continuation_query"]["inputSchema"].get(
        "properties", {}
    )
    assert "request" not in by_name["continuation_action"]["inputSchema"].get(
        "properties", {}
    )
    inventory = operation_names_by_gateway()
    assert inventory["continuation_query"] == frozenset(
        {"capabilities", "list", "status", "resume", "handoffs", "effects"}
    )
    assert inventory["continuation_action"] == frozenset(
        {"open", "update_contract", "checkpoint", "complete", "cancel"}
    )


def test_c3_open_checkpoint_resume_and_contract_change_gateway_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(server, "get_continuation_service", lambda: service)

    opened = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "open",
                "controller_request_id": "c3-open",
                "label": "C3 smoke",
                "instruction_text": "Continue C3 source acceptance.",
                "provenance_class": "controller_submitted_text",
            }
        )
    )
    assert opened["ok"] is True
    assert opened["created"] is True
    continuation_id = opened["continuation"]["continuation_id"]
    first_ref = opened["continuation_context_ref"]

    checkpoint = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "checkpoint",
                "continuation_context_ref": first_ref,
                "freeform_handoff_text": "C3 gateway checkpoint; Sol decides what follows.",
                "controller_request_id": "c3-checkpoint",
            }
        )
    )
    assert checkpoint["ok"] is True
    assert checkpoint["continuation_context_ref"] == first_ref

    resumed = server.continuation_query(
        QUERY.validate_python(
            {"operation": "resume", "continuation_id": continuation_id}
        )
    )
    assert resumed["continuation_context_ref"] == first_ref
    assert resumed["sol_handoff"]["handoff_text"].startswith("C3 gateway checkpoint")
    assert resumed["contract_changed_since_handoff"] is False
    assert "recommended_next_action" not in json.dumps(resumed)

    updated = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "update_contract",
                "continuation_context_ref": first_ref,
                "instruction_text": "Continue C3 under the revised owner instruction.",
                "provenance_class": "controller_submitted_text",
                "controller_request_id": "c3-contract-2",
            }
        )
    )
    assert updated["ok"] is True
    second_ref = updated["continuation_context_ref"]
    assert second_ref != first_ref

    stale = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "checkpoint",
                "continuation_context_ref": first_ref,
                "freeform_handoff_text": "must not be accepted under stale context",
                "controller_request_id": "c3-stale-checkpoint",
            }
        )
    )
    assert stale["ok"] is False
    assert stale["error_code"] == "stale_continuation_contract"
    assert "reasoning" not in stale["error"].lower()

    resumed_after_update = server.continuation_query(
        QUERY.validate_python(
            {"operation": "resume", "continuation_id": continuation_id}
        )
    )
    assert resumed_after_update["continuation_context_ref"] == second_ref
    assert resumed_after_update["contract_changed_since_handoff"] is True


def test_c3_list_cursor_and_read_paths_do_not_mutate_continuation_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(server, "get_continuation_service", lambda: service)
    ids: list[str] = []
    for index in range(3):
        opened = server.continuation_action(
            ACTION.validate_python(
                {
                    "operation": "open",
                    "controller_request_id": f"c3-list-open-{index}",
                    "label": f"item-{index}",
                    "instruction_text": f"instruction {index}",
                    "provenance_class": "controller_submitted_text",
                }
            )
        )
        ids.append(opened["continuation"]["continuation_id"])

    before = {
        continuation_id: service.continuation_store.get_continuation(continuation_id)
        for continuation_id in ids
    }
    first = server.continuation_query(
        QUERY.validate_python({"operation": "list", "limit": 2})
    )
    assert first["count"] == 2
    assert first["total_count"] == 3
    assert first["has_more"] is True
    second = server.continuation_query(
        QUERY.validate_python(
            {"operation": "list", "limit": 2, "cursor": first["next_cursor"]}
        )
    )
    assert second["count"] == 1
    assert second["has_more"] is False

    target = ids[0]
    assert server.continuation_query(
        QUERY.validate_python({"operation": "status", "continuation_id": target})
    )["ok"] is True
    assert server.continuation_query(
        QUERY.validate_python({"operation": "handoffs", "continuation_id": target})
    )["count"] == 0
    assert server.continuation_query(
        QUERY.validate_python({"operation": "effects", "continuation_id": target})
    )["count"] == 0
    server.continuation_query(
        QUERY.validate_python({"operation": "resume", "continuation_id": target})
    )

    after = {
        continuation_id: service.continuation_store.get_continuation(continuation_id)
        for continuation_id in ids
    }
    assert after == before


def test_c3_complete_preserves_resume_and_rejects_new_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(server, "get_continuation_service", lambda: service)
    opened = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "open",
                "controller_request_id": "c3-close-open",
                "instruction_text": "Close after checkpoint.",
                "provenance_class": "controller_submitted_text",
            }
        )
    )
    continuation_id = opened["continuation"]["continuation_id"]
    context_ref = opened["continuation_context_ref"]
    server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "checkpoint",
                "continuation_context_ref": context_ref,
                "freeform_handoff_text": "final handoff",
                "controller_request_id": "c3-close-handoff",
            }
        )
    )
    closed = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "complete",
                "continuation_id": continuation_id,
                "controller_request_id": "c3-complete",
            }
        )
    )
    assert closed["ok"] is True
    assert closed["continuation"]["lifecycle"] == "completed"
    resume = server.continuation_query(
        QUERY.validate_python(
            {"operation": "resume", "continuation_id": continuation_id}
        )
    )
    assert resume["continuation"]["lifecycle"] == "completed"
    assert resume["sol_handoff"]["handoff_text"] == "final handoff"

    rejected = server.continuation_action(
        ACTION.validate_python(
            {
                "operation": "checkpoint",
                "continuation_context_ref": context_ref,
                "freeform_handoff_text": "after close",
                "controller_request_id": "c3-after-close",
            }
        )
    )
    assert rejected["ok"] is False
    assert rejected["error_code"] == "continuation_closed"


def test_c3_missing_continuation_query_is_honest(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(server, "get_continuation_service", lambda: service)
    result = server.continuation_query(
        QUERY.validate_python(
            {
                "operation": "status",
                "continuation_id": "cont_20260815T120000Z_abcdef123456",
            }
        )
    )
    assert result["ok"] is False
    assert result["error_code"] == "continuation_not_found"
