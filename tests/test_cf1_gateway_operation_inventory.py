from __future__ import annotations

import asyncio
from typing import Any

from codexbridge.cf1_gateway_operation_inventory import (
    CF1_GATEWAY_OPERATION_INVENTORY_VERSION,
    PUBLIC_GATEWAY_OPERATION_INVENTORY,
    ConnectorRepresentation,
    JsonDecodeCost,
    PaginationBehavior,
    RequestEchoBehavior,
    operation_inventory_by_gateway,
    operation_names_by_gateway,
    validate_gateway_operation_inventory,
)
from codexbridge.knowledge_tools_integration import register_knowledge_tools
from codexbridge.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
import codexbridge.server as server


def _resolve_schema(value: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    current = value
    seen: set[str] = set()
    while "$ref" in current:
        reference = str(current["$ref"])
        if reference in seen or not reference.startswith("#/"):
            raise AssertionError(f"unsupported or recursive schema reference: {reference}")
        seen.add(reference)
        resolved: Any = root
        for part in reference[2:].split("/"):
            resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
        if not isinstance(resolved, dict):
            raise AssertionError(f"schema reference did not resolve to an object: {reference}")
        current = resolved
    return current


def _schema_operation_names(action: dict[str, Any]) -> frozenset[str]:
    root = action["inputSchema"]
    request = root.get("properties", {}).get("request")
    if not isinstance(request, dict):
        return frozenset({"invoke"})
    request = _resolve_schema(request, root)
    variants = request.get("oneOf")
    if not isinstance(variants, list):
        variants = [request]

    names: set[str] = set()
    for raw_variant in variants:
        variant = _resolve_schema(raw_variant, root)
        properties = variant.get("properties", {})
        for discriminator_name in ("operation", "action"):
            discriminator = properties.get(discriminator_name)
            if not isinstance(discriminator, dict):
                continue
            discriminator = _resolve_schema(discriminator, root)
            if "const" in discriminator:
                names.add(str(discriminator["const"]))
            enum_values = discriminator.get("enum")
            if isinstance(enum_values, list):
                names.update(str(value) for value in enum_values)
    return frozenset(names or {"invoke"})


def _discovered_actions() -> dict[str, dict[str, Any]]:
    async def _list() -> dict[str, dict[str, Any]]:
        register_knowledge_tools(server.mcp)
        tools = await server.mcp.list_tools()
        return {
            tool.name: tool.to_mcp_tool().model_dump(mode="json")
            for tool in tools
        }

    return asyncio.run(_list())


def _entry_for(gateway: str, operation: str):
    matches = [
        entry
        for entry in PUBLIC_GATEWAY_OPERATION_INVENTORY
        if entry.gateway == gateway and operation in entry.operation_names
    ]
    assert len(matches) == 1
    return matches[0]


def test_cf1_gateway_operation_inventory_is_versioned_and_exact() -> None:
    validate_gateway_operation_inventory()
    grouped = operation_inventory_by_gateway()

    assert CF1_GATEWAY_OPERATION_INVENTORY_VERSION == (
        "cf1.3.gateway-operations.v5"
    )
    assert set(grouped) == set(PUBLIC_GATEWAY_NAMES)
    assert set(operation_names_by_gateway()) == set(PUBLIC_GATEWAY_NAMES)

    for gateway, entries in grouped.items():
        assert entries
        flattened = [
            operation
            for entry in entries
            for operation in entry.operation_names
        ]
        assert flattened
        assert len(flattened) == len(set(flattened)), gateway


def test_inventory_matches_every_current_mcp_discriminator() -> None:
    inventory = operation_names_by_gateway()
    actions = _discovered_actions()

    assert set(actions) <= set(inventory)
    for gateway, action in actions.items():
        assert inventory[gateway] == _schema_operation_names(action), gateway


def test_every_operation_records_required_cf1_measurement_dimensions() -> None:
    assert PUBLIC_GATEWAY_OPERATION_INVENTORY

    for entry in PUBLIC_GATEWAY_OPERATION_INVENTORY:
        assert entry.implementation_path.startswith("codexbridge.")
        assert ":" in entry.implementation_path
        assert entry.response_path
        assert entry.notes
        assert isinstance(entry.request_echo, RequestEchoBehavior)
        assert isinstance(entry.json_decode_cost, JsonDecodeCost)
        assert isinstance(entry.pagination, PaginationBehavior)
        assert entry.connector_representation is (
            ConnectorRepresentation.INLINE_WITH_RESOURCE_FALLBACK
        )

        if entry.default_response_bytes is not None:
            assert entry.default_response_bytes > 0
        if entry.maximum_response_bytes is not None:
            assert entry.maximum_response_bytes > 0
        if (
            entry.default_response_bytes is not None
            and entry.maximum_response_bytes is not None
        ):
            assert entry.default_response_bytes <= entry.maximum_response_bytes
        if entry.default_item_limit is not None:
            assert entry.default_item_limit > 0
        if entry.maximum_item_limit is not None:
            assert entry.maximum_item_limit > 0
        if (
            entry.default_item_limit is not None
            and entry.maximum_item_limit is not None
        ):
            assert entry.default_item_limit <= entry.maximum_item_limit


def test_cf1_inventory_records_compact_run_envelope_byte_budgets() -> None:
    summary = _entry_for("run_query", "summary")
    summary_list = _entry_for("run_query", "summary_list")
    control = _entry_for("run_query", "control")
    events = _entry_for("run_query", "events")
    terminal = _entry_for("run_query", "terminal")
    assert summary.default_response_bytes == 6 * 1024
    assert summary.maximum_response_bytes == 6 * 1024
    assert summary_list.default_response_bytes == 12 * 1024
    assert summary_list.maximum_response_bytes == 12 * 1024
    assert summary_list.pagination is PaginationBehavior.CURSOR
    assert summary_list.default_item_limit == 10
    assert summary_list.maximum_item_limit == 100
    assert control.default_response_bytes == 8 * 1024
    assert control.maximum_response_bytes == 8 * 1024
    assert control.json_decode_cost is JsonDecodeCost.NONE
    assert "1 KiB" in control.notes
    assert events.default_response_bytes == 12 * 1024
    assert events.maximum_response_bytes == 12 * 1024
    assert events.default_item_limit == 20
    assert events.maximum_item_limit == 500
    assert events.pagination is PaginationBehavior.CURSOR
    assert "gap" in events.notes
    assert "expiry" in events.notes
    assert terminal.default_response_bytes == 12 * 1024
    assert terminal.maximum_response_bytes == 12 * 1024
    assert terminal.json_decode_cost is JsonDecodeCost.BOUNDED_OBJECT
    assert terminal.pagination is PaginationBehavior.NONE
    assert "source-hash" in terminal.notes
    assert "result_json" in terminal.notes

    compact_operations = {
        "summary",
        "summary_list",
        "control",
            "events",
            "terminal",
            "preflight",
        }
    assert all(
        entry.default_response_bytes is None
        and entry.maximum_response_bytes is None
        for entry in PUBLIC_GATEWAY_OPERATION_INVENTORY
        if compact_operations.isdisjoint(entry.operation_names)
    )

    output = _entry_for("run_query", "output")
    assert "20,000" in output.notes
    assert "200,000" in output.notes
    assert "not complete response byte ceilings" in output.notes


def test_high_cost_operations_preserve_current_behavioral_baseline() -> None:
    run_list = _entry_for("run_query", "list")
    assert run_list.request_echo is RequestEchoBehavior.FULL_AUTHORITATIVE_ROW
    assert run_list.json_decode_cost is JsonDecodeCost.FULL_JSON_BLOBS
    assert run_list.pagination is PaginationBehavior.CHUNK_CURSOR
    assert run_list.default_item_limit == 20
    assert run_list.maximum_item_limit == 500
    assert "input_json" in run_list.notes
    assert "worker lease" in run_list.notes

    run_events = _entry_for("run_query", "events")
    assert run_events.pagination is PaginationBehavior.CURSOR
    assert run_events.default_item_limit == 20
    assert run_events.maximum_item_limit == 500

    cloudflare = _entry_for("cloudflare_query", "inspect")
    assert cloudflare.pagination is PaginationBehavior.PAGE_NUMBER
    assert cloudflare.default_item_limit == 100
    assert cloudflare.maximum_item_limit == 100

    repo_read = _entry_for("repo_query", "read_files")
    assert repo_read.maximum_item_limit == 20
    assert "aggregate returned content" in repo_read.notes

    historical_ticks = _entry_for("trading_query", "historical_ticks")
    assert historical_ticks.pagination is PaginationBehavior.NONE
    assert "no result count" in historical_ticks.notes


def test_durable_action_paths_record_request_echo_explicitly() -> None:
    for gateway, operation in {
        ("codex_plan", "invoke"),
        ("codex_implement", "invoke"),
        ("run_start", "powershell"),
        ("docker_action", "compose_up"),
        ("cloudflare_action", "dns_create"),
        ("ssh_action", "reviewed_script"),
        ("supervisor_action", "start"),
        ("workflow_action", "start"),
        ("repo_preview", "patch"),
        ("knowledge_action", "remember_decision"),
    }:
        entry = _entry_for(gateway, operation)
        assert entry.request_echo is RequestEchoBehavior.DURABLE_INPUT_RECORD
