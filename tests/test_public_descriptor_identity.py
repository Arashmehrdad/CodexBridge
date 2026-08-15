from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from pydantic import TypeAdapter
import pytest

from soma.gateway_models import SystemCapabilityIdentityQuery, SystemQueryRequest
import soma.server as server


PUBLIC_SCHEMA_HASH = "ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42"


def _actions() -> list[dict]:
    return [
        {
            "name": "z_tool",
            "title": "Z tool",
            "description": "Use this when you need the z tool.",
            "inputSchema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
            "_meta": {"invoking": "Running z tool", "invoked": "Ran z tool"},
        },
        {
            "name": "a_tool",
            "title": "A tool",
            "description": "Use this when you need the a tool.",
            "inputSchema": {"type": "object", "properties": {}},
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            },
            "_meta": {"invoking": "Running a tool", "invoked": "Ran a tool"},
        },
    ]


def _identity_request(**values: object) -> SystemQueryRequest:
    return TypeAdapter(SystemQueryRequest).validate_python(
        {"operation": "capability_identity", "view": "full", **values}
    )


def test_served_descriptor_dump_uses_the_exact_json_contract() -> None:
    class FakeModel:
        def model_dump(self, **kwargs: object) -> dict:
            assert kwargs == {
                "mode": "json",
                "by_alias": True,
                "exclude_none": False,
            }
            return {"name": "fake"}

    class FakeTool:
        def to_mcp_tool(self) -> FakeModel:
            return FakeModel()

    assert server._served_descriptor_from_tool(FakeTool()) == {"name": "fake"}


def test_descriptor_hash_is_canonical_and_name_ordered() -> None:
    actions = _actions()
    equivalent = list(reversed(deepcopy(actions)))
    assert server._descriptor_hash_from_actions(
        actions
    ) == server._descriptor_hash_from_actions(equivalent)

    non_ascii_actions = [{"name": "é", "description": "Use this when café."}]
    expected_snapshot = json.dumps(
        non_ascii_actions,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert (
        server._descriptor_hash_from_actions(non_ascii_actions)
        == hashlib.sha256(expected_snapshot).hexdigest()
    )


@pytest.mark.parametrize(
    ("change", "label"),
    [
        (lambda action: action.update(title="Changed title"), "title"),
        (
            lambda action: action.update(
                description="Use this when the description changes."
            ),
            "description",
        ),
        (
            lambda action: action["annotations"].update(
                openWorldHint=not action["annotations"]["openWorldHint"]
            ),
            "annotation",
        ),
        (
            lambda action: action["_meta"].update(
                invoking="A different invocation label"
            ),
            "invocation_meta",
        ),
    ],
)
def test_descriptor_metadata_changes_change_only_descriptor_identity(
    change, label: str
) -> None:
    original = _actions()
    changed = deepcopy(original)
    change(changed[0])

    assert label
    assert server._descriptor_hash_from_actions(
        original
    ) != server._descriptor_hash_from_actions(changed)
    assert server._input_schema_hash_from_actions(
        original
    ) == server._input_schema_hash_from_actions(changed)


def test_input_schema_change_changes_both_descriptor_and_public_schema_identity() -> (
    None
):
    original = _actions()
    changed = deepcopy(original)
    changed[0]["inputSchema"]["properties"]["value"]["type"] = "integer"

    assert server._descriptor_hash_from_actions(
        original
    ) != server._descriptor_hash_from_actions(changed)
    assert server._input_schema_hash_from_actions(
        original
    ) != server._input_schema_hash_from_actions(changed)


def test_reordered_same_process_discovery_passes_have_the_same_descriptor_hash() -> (
    None
):
    reordered_passes = []
    for order in ((0, 1), (1, 0), (0, 1)):
        fresh = deepcopy(_actions())
        reordered_passes.append(
            server._descriptor_hash_from_actions([fresh[index] for index in order])
        )
    assert len(set(reordered_passes)) == 1


def test_fresh_process_discovery_has_stable_descriptor_identity() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = """
import asyncio
import json

import soma.server as server

server.refresh_public_contract_hash()
tools = asyncio.run(server.mcp.list_tools())
actions = [
    tool.to_mcp_tool().model_dump(
        mode="json",
        by_alias=True,
        exclude_none=False,
    )
    for tool in tools
]
print(
    json.dumps(
        {
            "tool_count": len(tools),
            "public_schema_hash": server._input_schema_hash_from_actions(actions),
            "public_descriptor_hash": server._descriptor_hash_from_actions(actions),
        },
        sort_keys=True,
    )
)
"""
    results = []
    for _ in range(3):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        output_lines = completed.stdout.splitlines()
        assert len(output_lines) == 1, completed.stdout
        results.append(json.loads(output_lines[0]))

    assert [result["tool_count"] for result in results] == [34, 34, 34]
    assert [result["public_schema_hash"] for result in results] == [
        PUBLIC_SCHEMA_HASH
    ] * 3
    descriptor_hashes = [result["public_descriptor_hash"] for result in results]
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in descriptor_hashes)
    assert len(set(descriptor_hashes)) == 1


def test_descriptor_identity_query_preserves_the_public_input_contract() -> None:
    assert (
        "expected_public_descriptor_hash"
        not in SystemCapabilityIdentityQuery.model_fields
    )
    assert (
        "expected_discovery_cache_generation"
        in SystemCapabilityIdentityQuery.model_fields
    )


def test_descriptor_identity_changes_discovery_cache_generation_without_schema_drift() -> (
    None
):
    original = _actions()
    changed = deepcopy(original)
    changed[0]["title"] = "Changed title"
    original_identity = server._operation_identity_metadata(
        actions=original, descriptor_actions=original
    )
    changed_identity = server._operation_identity_metadata(
        actions=changed, descriptor_actions=changed
    )

    assert (
        original_identity["public_descriptor_hash"]
        != changed_identity["public_descriptor_hash"]
    )
    assert (
        original_identity["public_schema_hash"]
        == changed_identity["public_schema_hash"]
    )
    assert (
        original_identity["discovery_cache_generation"]
        != changed_identity["discovery_cache_generation"]
    )


def test_refresh_populates_contract_and_descriptor_caches_from_one_discovery_pass(
    monkeypatch,
) -> None:
    original_list_tools = server.mcp.list_tools
    calls = 0

    async def counted_list_tools(*args, **kwargs):
        nonlocal calls
        if kwargs.get("run_middleware", True):
            calls += 1
        return await original_list_tools(*args, **kwargs)

    monkeypatch.setattr(server.mcp, "list_tools", counted_list_tools)
    monkeypatch.setattr(server, "_PUBLIC_CONTRACT_HASH_CACHE", "")
    monkeypatch.setattr(server, "_PUBLIC_DESCRIPTOR_HASH_CACHE", "")

    contract_hash = server.refresh_public_contract_hash()

    assert calls == 1
    assert len(contract_hash) == 64
    assert len(server.public_descriptor_hash()) == 64


def test_capabilities_and_capability_identity_expose_descriptor_identity() -> None:
    server.refresh_public_contract_hash()
    capabilities = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capabilities", "view": "full"}
        )
    )
    identity = server.system_query(_identity_request())

    assert len(capabilities["public_descriptor_hash"]) == 64
    assert capabilities["public_descriptor_hash"] == identity["public_descriptor_hash"]
    assert "public_descriptor_hash" not in server._with_process_capability_metadata(
        {"ok": True}
    )


def test_descriptor_change_converges_through_discovery_cache_generation() -> None:
    current = server.system_query(_identity_request())
    result = server.system_query(
        _identity_request(expected_discovery_cache_generation="0" * 64)
    )

    assert result["public_descriptor_hash"] == current["public_descriptor_hash"]
    assert "connector_public_descriptor_hash" not in result
    assert result["mismatches"] == ["connector_discovery_cache_generation"]
    assert result["connector_refresh_required"] is True
    assert result["restart_required"] is False
