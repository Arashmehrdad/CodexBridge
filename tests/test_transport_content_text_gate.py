"""Regression gate: every public gateway operation must serialize its payload
into ``content[].text``.

This is the assertion CF1's byte-size gates could not make. A byte-size budget
cannot distinguish a compact response from an *empty* one, so the connector
transport regressed to emitting only a scalar envelope summary in
``content[].text`` while the payload lived exclusively in ``structuredContent``.
ChatGPT reads ``structuredContent``; Claude, LangChain's MCP adapters, Agent
Zero, and most other MCP clients read ``content[].text`` and saw nothing usable.

MCP spec 2025-06-18 (Server/Tools, Structured Content) requires a tool that
returns structured content to also serialize that same JSON into a text content
block. These tests assert, for every public gateway operation, that the text
block is non-empty, JSON-parseable, and semantically equivalent to
``structuredContent``.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client

import soma.server as server
from soma.capabilities import PATCH_OPERATION_SCHEMA, capability_metadata
from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES


# One representative result dict per public gateway operation. The transport is
# a single chokepoint (`_mcp_transport_result`), so the exact fields do not
# change the serialization path; the map exists to force per-operation coverage
# — a new gateway operation without an entry fails the completeness assertion
# below. Budgeted operations carry `response_budget_bytes`/`response_bytes` so
# the byte-accounting path is exercised too.
_BUDGET = 12 * 1024
_REPRESENTATIVE_RESULTS: dict[str, dict] = {
    "repo_query": {
        "ok": True, "operation": "compact_status", "repo_name": "soma",
        "status": "clean", "changed_files": ["a.py"], "recent_commits": ["c"],
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "repo_preview": {"ok": True, "preview_id": "p1", "patch_id": "x", "files": ["a.py"]},
    "repo_apply": {"ok": True, "patch_id": "x", "status": "applied", "error": ""},
    "repo_commit": {"ok": True, "commit": "deadbeef", "status": "committed", "error": ""},
    "run_start": {"ok": True, "run_id": "r1", "operation": "launch", "status": "running"},
    "run_query": {
        "ok": True, "operation": "summary_list",
        "runs": [{"run_id": "r1", "status": "completed", "summary": "s"}],
        "byte_budget": _BUDGET, "payload_bytes": 1, "error": "",
    },
    "cancel_run": {"ok": True, "run_id": "r1", "status": "cancellation_requested"},
    "system_query": {
        "ok": True, "operation": "capabilities", "server_status": "ready",
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "system_action": {"ok": True, "operation": "reload", "status": "reloaded", "error": ""},
    "docker_query": {"ok": True, "operation": "list", "containers": [], "error": ""},
    "docker_action": {"ok": True, "run_id": "r1", "operation": "restart", "status": "running"},
    "cloudflare_query": {"ok": True, "operation": "health", "healthy": True, "error": ""},
    "cloudflare_action": {"ok": True, "run_id": "r1", "operation": "purge", "status": "running"},
    "ssh_query": {"ok": True, "operation": "profiles", "profiles": [], "error": ""},
    "ssh_action": {"ok": True, "run_id": "r1", "operation": "run", "status": "running"},
    "ssh_inspect": {"ok": True, "operation": "environment", "host": "h", "reachable": True},
    "supervisor_query": {"ok": True, "operation": "status", "supervisor_id": "s1", "state": "idle"},
    "supervisor_action": {"ok": True, "supervisor_id": "s1", "operation": "start", "status": "running"},
    "workflow_query": {"ok": True, "operation": "status", "workflow_id": "w1", "state": "idle"},
    "workflow_action": {"ok": True, "workflow_id": "w1", "operation": "advance", "status": "running"},
    "task_query": {
        "ok": True, "operation": "status", "task_id": "task_1", "state": "running",
        "phase": "backend_running", "state_version": 3, "backend_reference": "r1",
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "task_action": {
        "ok": True, "operation": "start", "task_id": "task_1", "state": "queued",
        "state_version": 1, "backend_reference": "r1", "created": True,
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "company_query": {
        "ok": True, "operation": "capabilities", "runtime_enabled": False,
        "automatic_outcome_acceptance": False,
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "company_action": {
        "ok": True, "operation": "reconcile_one",
        "result": {"created": True, "replay_kind": "none"},
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "knowledge_query": {
        "ok": True, "operation": "read_wiki", "repo_name": "soma", "sections": ["overview"],
        "response_budget_bytes": _BUDGET, "response_bytes": 1,
    },
    "knowledge_action": {"ok": True, "operation": "record_decision", "decision_id": "d1", "error": ""},
    "trading_query": {"ok": True, "operation": "runtime_status", "enabled": False, "error": ""},
    "trading_companion_action": {
        "ok": True,
        "action": "review",
        "run": {"companion_run_id": "cycle1", "status": "MODEL_APPROVED"},
        "response_budget_bytes": _BUDGET,
        "response_bytes": 1,
    },
    "trading_signal_submit": {"ok": True, "signal_id": "sig1", "status": "journaled", "error": ""},
    "trading_signal_get": {"ok": True, "signal_id": "sig1", "status": "journaled", "error": ""},
    "trading_signal_list": {"ok": True, "operation": "list", "signals": [], "error": ""},
    "trading_signal_cancel_before_entry": {"ok": True, "signal_id": "sig1", "status": "cancelled"},
    "trading_action_submit": {"ok": True, "action_id": "a1", "status": "recorded", "error": ""},
    "trading_runtime_control": {"ok": True, "operation": "status", "runtime_state": "idle", "error": ""},
}


def test_representative_results_cover_every_public_gateway_operation() -> None:
    # If a public gateway operation is added, it must gain a representative
    # result here so the transport gate below exercises it.
    assert set(_REPRESENTATIVE_RESULTS) == set(PUBLIC_GATEWAY_NAMES)


def _text_of(transported) -> str:
    return "".join(
        block.text
        for block in transported.content
        if getattr(block, "type", "") == "text"
    )


@pytest.mark.parametrize("operation", sorted(_REPRESENTATIVE_RESULTS))
def test_transport_emits_non_empty_parseable_text_for_every_operation(
    operation: str,
) -> None:
    # Reproduce the production wrapper composition: capability metadata is merged
    # in, then the result is transported.
    enriched = server._with_process_capability_metadata(
        dict(_REPRESENTATIVE_RESULTS[operation])
    )
    transported = server._mcp_transport_result(enriched)

    # structuredContent still carries the full projection; only response_bytes
    # may be refreshed to reflect the serialized text block.
    for key, value in enriched.items():
        if key == "response_bytes":
            continue
        assert transported.structured_content[key] == value

    # content[].text is the gate that was missing: non-empty and JSON parseable.
    text = _text_of(transported)
    assert text, f"{operation}: content[].text is empty"
    reconstructed = json.loads(text)

    # Both channels are semantically equivalent.
    assert reconstructed == transported.structured_content


@pytest.mark.parametrize("operation", sorted(_REPRESENTATIVE_RESULTS))
def test_budget_accounting_reflects_the_serialized_text_block(operation: str) -> None:
    source = dict(_REPRESENTATIVE_RESULTS[operation])
    if "response_bytes" not in source:
        pytest.skip("operation does not report response_bytes")
    enriched = server._with_process_capability_metadata(source)
    transported = server._mcp_transport_result(enriched)
    text = _text_of(transported)
    # response_bytes now accounts for the channel the model actually consumes.
    assert transported.structured_content["response_bytes"] == len(text.encode("utf-8"))
    # The consumed text block stays within the declared budget plus only the
    # fixed capability-metadata envelope merged by the transport layer.
    capability_envelope = len(
        json.dumps(
            capability_metadata(PATCH_OPERATION_SCHEMA),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert len(text.encode("utf-8")) <= source["response_budget_bytes"] + capability_envelope


def test_live_gateway_call_populates_both_channels() -> None:
    """End-to-end proof the wrapper is wired: a real MCP call yields a populated
    content[].text AND structuredContent carrying the same information."""

    async def call() -> object:
        async with Client(server.mcp) as client:
            return await client.call_tool(
                "system_query", {"request": {"operation": "capabilities"}}
            )

    result = asyncio.run(call())
    assert result.structured_content is not None
    text = _text_of(result)
    assert text, "live call produced an empty content[].text"
    assert json.loads(text) == result.structured_content
