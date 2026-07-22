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
        "locks",
        "preflight",
        "group_status",
        "group_result",
        "repo_apply",
    }
    assert all(
        entry.default_response_bytes is None
        and entry.maximum_response_bytes is None
        for entry in PUBLIC_GATEWAY_OPERATION_INVENTORY
        if entry.gateway == "run_query"
        and compact_operations.isdisjoint(entry.operation_names)
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
    assert cloudflare.default_response_bytes == 12 * 1024
    assert cloudflare.maximum_response_bytes == 12 * 1024
    assert cloudflare.pagination is PaginationBehavior.PAGE_NUMBER
    assert cloudflare.default_item_limit == 100
    assert cloudflare.maximum_item_limit == 100
    assert "serialized UTF-8 budget" in cloudflare.notes

    h4 = _entry_for("trading_query", "h4_candles")
    assert h4.default_response_bytes == 12 * 1024
    assert h4.maximum_response_bytes == 12 * 1024
    assert "UTF-8 byte budget" in h4.notes

    supervisor_events = _entry_for("supervisor_query", "events")
    assert supervisor_events.default_response_bytes == 12 * 1024
    assert supervisor_events.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in supervisor_events.notes

    supervisor_notifications = _entry_for("supervisor_query", "notifications")
    assert supervisor_notifications.default_response_bytes == 12 * 1024
    assert supervisor_notifications.maximum_response_bytes == 12 * 1024
    assert "delivery-status filtered" in supervisor_notifications.notes

    supervisor_prompt = _entry_for("supervisor_query", "resume_prompt")
    assert supervisor_prompt.default_response_bytes == 12 * 1024
    assert supervisor_prompt.maximum_response_bytes == 12 * 1024
    assert "view=full" in supervisor_prompt.notes

    supervisor_status = _entry_for("supervisor_query", "status")
    assert supervisor_status.default_response_bytes == 12 * 1024
    assert supervisor_status.maximum_response_bytes == 12 * 1024
    assert "view=full" in supervisor_status.notes

    supervisor_result = _entry_for("supervisor_query", "result")
    assert supervisor_result.default_response_bytes == 12 * 1024
    assert supervisor_result.maximum_response_bytes == 12 * 1024
    assert "view=full" in supervisor_result.notes

    reload_entry = _entry_for("system_action", "reload")
    assert reload_entry.default_response_bytes == 12 * 1024
    assert reload_entry.maximum_response_bytes == 12 * 1024
    assert "view=full" in reload_entry.notes
    rollback_entry = _entry_for("system_action", "rollback")
    assert rollback_entry.default_response_bytes == 12 * 1024
    assert rollback_entry.maximum_response_bytes == 12 * 1024
    assert "view=full" in rollback_entry.notes

    refresh_entry = _entry_for("knowledge_action", "refresh_wiki")
    assert refresh_entry.default_response_bytes == 12 * 1024
    assert refresh_entry.maximum_response_bytes == 12 * 1024
    assert "view=full" in refresh_entry.notes
    decision_entry = _entry_for("knowledge_action", "remember_decision")
    assert decision_entry.default_response_bytes == 12 * 1024
    assert decision_entry.maximum_response_bytes == 12 * 1024
    assert "view=full" in decision_entry.notes

    workflow_events = _entry_for("workflow_query", "events")
    assert workflow_events.default_response_bytes == 12 * 1024
    assert workflow_events.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in workflow_events.notes

    workflow_status = _entry_for("workflow_query", "status")
    assert workflow_status.default_response_bytes == 12 * 1024
    assert workflow_status.maximum_response_bytes == 12 * 1024
    assert "view=full" in workflow_status.notes

    workflow_result = _entry_for("workflow_query", "result")
    assert workflow_result.default_response_bytes == 12 * 1024
    assert workflow_result.maximum_response_bytes == 12 * 1024
    assert "view=full" in workflow_result.notes

    ssh_inspection = _entry_for("ssh_inspect", "inspection")
    assert ssh_inspection.default_response_bytes == 12 * 1024
    assert ssh_inspection.maximum_response_bytes == 12 * 1024
    assert "UTF-8 budget" in ssh_inspection.notes

    signal_list = _entry_for("trading_signal_list", "invoke")
    assert signal_list.default_response_bytes == 12 * 1024
    assert signal_list.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in signal_list.notes

    signal_submit = _entry_for("trading_signal_submit", "invoke")
    assert signal_submit.default_response_bytes == 12 * 1024
    assert signal_submit.maximum_response_bytes == 12 * 1024
    assert "view=full" in signal_submit.notes

    signal_get = _entry_for("trading_signal_get", "invoke")
    assert signal_get.default_response_bytes == 12 * 1024
    assert signal_get.maximum_response_bytes == 12 * 1024
    assert "view=full" in signal_get.notes

    signal_cancel = _entry_for("trading_signal_cancel_before_entry", "invoke")
    assert signal_cancel.default_response_bytes == 12 * 1024
    assert signal_cancel.maximum_response_bytes == 12 * 1024
    assert "view=full" in signal_cancel.notes

    wiki_page = _entry_for("knowledge_query", "read_wiki")
    assert wiki_page.default_response_bytes == 12 * 1024
    assert wiki_page.maximum_response_bytes == 12 * 1024
    assert "view=full" in wiki_page.notes

    knowledge_search = _entry_for("knowledge_query", "search")
    assert knowledge_search.default_response_bytes == 12 * 1024
    assert knowledge_search.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in knowledge_search.notes

    repo_commit = _entry_for("repo_commit", "commit_selected")
    assert repo_commit.default_response_bytes == 12 * 1024
    assert repo_commit.maximum_response_bytes == 12 * 1024
    assert "view=full" in repo_commit.notes

    search = _entry_for("repo_query", "search_text")
    assert search.default_response_bytes == 16 * 1024
    assert search.maximum_response_bytes == 16 * 1024
    assert search.pagination is PaginationBehavior.CURSOR
    assert "exact-file scope" in search.notes
    assert "timeout/partial-result reporting" in search.notes

    docker_capabilities = _entry_for("docker_query", "capabilities")
    assert docker_capabilities.default_response_bytes == 12 * 1024
    assert docker_capabilities.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in docker_capabilities.notes

    docker_health = _entry_for("docker_query", "health")
    assert docker_health.default_response_bytes == 12 * 1024
    assert docker_health.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in docker_health.notes

    cloudflare_capabilities = _entry_for("cloudflare_query", "capabilities")
    assert cloudflare_capabilities.default_response_bytes == 12 * 1024
    assert cloudflare_capabilities.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in cloudflare_capabilities.notes

    cloudflare_health = _entry_for("cloudflare_query", "health")
    assert cloudflare_health.default_response_bytes == 12 * 1024
    assert cloudflare_health.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in cloudflare_health.notes

    system_self_check = _entry_for("system_query", "self_check")
    assert system_self_check.default_response_bytes == 12 * 1024
    assert system_self_check.maximum_response_bytes == 12 * 1024
    assert "view=full" in system_self_check.notes

    repo_read = _entry_for("repo_query", "read_files")
    assert repo_read.maximum_item_limit == 20
    assert repo_read.default_response_bytes == 48 * 1024
    assert repo_read.maximum_response_bytes == 128 * 1024
    assert "aggregate content is enforced" in repo_read.notes

    ssh_capabilities = _entry_for("ssh_query", "capabilities")
    assert ssh_capabilities.default_response_bytes == 12 * 1024
    assert ssh_capabilities.maximum_response_bytes == 12 * 1024
    assert "view=full" in ssh_capabilities.notes
    ssh_profiles = _entry_for("ssh_query", "profile_preview")
    assert ssh_profiles.default_response_bytes == 12 * 1024
    assert ssh_profiles.maximum_response_bytes == 12 * 1024
    assert "view=full" in ssh_profiles.notes

    repo_list = _entry_for("repo_query", "list_files")
    assert repo_list.default_response_bytes == 12 * 1024
    assert repo_list.maximum_response_bytes == 12 * 1024
    assert "view=full" in repo_list.notes

    recent_files = _entry_for("repo_query", "recent_files")
    assert recent_files.default_response_bytes == 12 * 1024
    assert recent_files.maximum_response_bytes == 12 * 1024
    assert "view=full" in recent_files.notes

    log = _entry_for("repo_query", "log")
    assert log.default_response_bytes == 12 * 1024
    assert log.maximum_response_bytes == 12 * 1024
    assert "view=full" in log.notes

    status = _entry_for("repo_query", "status")
    assert status.default_response_bytes == 12 * 1024
    assert status.maximum_response_bytes == 12 * 1024
    assert "view=full" in status.notes

    patch_status = _entry_for("repo_query", "patch_status")
    assert patch_status.default_response_bytes == 12 * 1024
    assert patch_status.maximum_response_bytes == 12 * 1024
    assert "complete patch manifest" in patch_status.notes

    compact_status = _entry_for("repo_query", "compact_status")
    assert compact_status.default_response_bytes == 12 * 1024
    assert compact_status.maximum_response_bytes == 12 * 1024
    assert "serialized UTF-8 budget" in compact_status.notes

    docker_inspect = _entry_for("docker_query", "inspect")
    assert docker_inspect.default_response_bytes == 12 * 1024
    assert docker_inspect.maximum_response_bytes == 12 * 1024
    assert "UTF-8 byte budget" in docker_inspect.notes

    historical_ticks = _entry_for("trading_query", "historical_ticks")
    assert historical_ticks.default_response_bytes == 12 * 1024
    assert historical_ticks.maximum_response_bytes == 12 * 1024
    assert historical_ticks.pagination is PaginationBehavior.NONE
    assert "UTF-8 byte budget" in historical_ticks.notes

    group_status = _entry_for("run_query", "group_status")
    assert group_status.default_response_bytes == 12 * 1024
    assert group_status.maximum_response_bytes == 12 * 1024
    assert "view=full" in group_status.notes

    group_result = _entry_for("run_query", "group_result")
    assert group_result.default_response_bytes == 12 * 1024
    assert group_result.maximum_response_bytes == 12 * 1024
    assert "view=full" in group_result.notes

    symbols = _entry_for("trading_query", "symbols")
    assert symbols.default_response_bytes == 12 * 1024
    assert symbols.maximum_response_bytes == 12 * 1024
    assert symbols.pagination is PaginationBehavior.LIMIT_ONLY
    assert "UTF-8 byte budget" in symbols.notes


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
