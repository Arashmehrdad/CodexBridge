"""Guard the flat public MCP gateway input contract.

Every public gateway is implemented as ``tool(request: DiscriminatedUnion)``,
which used to make ``tools/list`` advertise a mandatory outer ``request``
object. These tests inspect the *actual* advertised contract and the *actual*
tool-call path rather than the Python models, so a regression in the
registration boundary cannot pass unnoticed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from soma import server
from soma.gateway_models import RepoPreviewedChangeApply
from soma.knowledge_tools_integration import register_knowledge_tools
from soma.mcp_flat_input import (
    FlatGatewayTool,
    flatten_request_input_schema,
    normalize_gateway_arguments,
)
from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES

# ``cancel_run`` already took flat scalar parameters, so it never carried the
# envelope and is the one public gateway with no request model at all.
GATEWAYS_WITHOUT_REQUEST_MODEL = frozenset({"cancel_run"})

# Gateways whose request model is a discriminated union of operation models.
# These are the ones whose ``oneOf`` is hoisted to the argument root.
UNION_GATEWAYS = frozenset(
    {
        "cloudflare_action", "cloudflare_query", "docker_action", "docker_query",
        "knowledge_action", "knowledge_query", "repo_apply", "repo_commit",
        "repo_preview", "repo_query", "run_query", "run_start", "ssh_action",
        "ssh_inspect", "ssh_query", "supervisor_action", "supervisor_query",
        "system_action", "system_query", "trading_companion_action",
        "trading_query", "workflow_action", "workflow_query",
    }
)

# Gateways whose request model is a single model rather than a union. They still
# carried the ``request`` envelope and still get flattened; they simply have no
# ``oneOf`` to hoist.
SINGLE_MODEL_GATEWAYS = frozenset(
    {
        "trading_action_submit", "trading_runtime_control",
        "trading_signal_cancel_before_entry", "trading_signal_get",
        "trading_signal_list", "trading_signal_submit",
    }
)

FLATTENED_GATEWAYS = UNION_GATEWAYS | SINGLE_MODEL_GATEWAYS


def _discovered_actions() -> dict[str, dict[str, Any]]:
    async def _list() -> dict[str, dict[str, Any]]:
        register_knowledge_tools(server.mcp)
        tools = await server.mcp.list_tools()
        return {
            tool.name: tool.to_mcp_tool().model_dump(mode="json") for tool in tools
        }

    return asyncio.run(_list())


@pytest.fixture(scope="module")
def actions() -> dict[str, dict[str, Any]]:
    return _discovered_actions()


@pytest.fixture(scope="module")
def live_tools(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Bind the real server config so gateway bodies can execute."""
    from soma.config import load_config

    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    if not config_path.is_file():
        pytest.skip("config.yaml is required for live gateway invocation")
    server.set_config(load_config(config_path), config_path)

    async def _list() -> dict[str, Any]:
        register_knowledge_tools(server.mcp)
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    return asyncio.run(_list())


def _call(live_tools: dict[str, Any], name: str, arguments: dict[str, Any]) -> Any:
    return asyncio.run(live_tools[name].run(arguments))


def _branches(schema: dict[str, Any]) -> list[dict[str, Any]]:
    variants = schema.get("oneOf")
    return list(variants) if isinstance(variants, list) else [schema]


def _branch(schema: dict[str, Any], operation: str) -> dict[str, Any]:
    for variant in _branches(schema):
        properties = variant.get("properties") or {}
        for discriminator in ("operation", "action"):
            declared = properties.get(discriminator)
            if isinstance(declared, dict) and declared.get("const") == operation:
                return variant
    raise AssertionError(f"no branch advertises operation {operation!r}")


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


# --------------------------------------------------------------------------
# tools/list schema
# --------------------------------------------------------------------------


def test_tested_inventory_covers_every_public_gateway(
    actions: dict[str, dict[str, Any]]
) -> None:
    """Completeness check against the authoritative public gateway list.

    A newly added gateway lands in none of these sets and fails here, so it
    cannot silently retain the old ``request`` wrapper.
    """
    assert PUBLIC_GATEWAY_NAMES <= set(actions)
    partitioned = UNION_GATEWAYS | SINGLE_MODEL_GATEWAYS | GATEWAYS_WITHOUT_REQUEST_MODEL
    assert partitioned == PUBLIC_GATEWAY_NAMES
    assert not (UNION_GATEWAYS & SINGLE_MODEL_GATEWAYS)

    # The declared shape must match the shape actually advertised.
    for name in UNION_GATEWAYS:
        assert isinstance(actions[name]["inputSchema"].get("oneOf"), list), name
    for name in SINGLE_MODEL_GATEWAYS:
        assert "oneOf" not in actions[name]["inputSchema"], name


@pytest.mark.parametrize("name", sorted(FLATTENED_GATEWAYS))
def test_gateway_schema_has_no_request_envelope(
    name: str, actions: dict[str, dict[str, Any]]
) -> None:
    schema = actions[name]["inputSchema"]
    assert schema["type"] == "object"
    assert "request" not in (schema.get("properties") or {})
    assert "request" not in (schema.get("required") or [])
    Draft202012Validator.check_schema(schema)


def _declared_values(declared: dict[str, Any]) -> set[str]:
    """A branch selects its operation by ``const``, or by ``enum`` for aliases."""
    if "const" in declared:
        return {declared["const"]}
    return set(declared.get("enum") or ())


@pytest.mark.parametrize("name", sorted(UNION_GATEWAYS))
def test_union_gateway_exposes_discriminator_at_root(
    name: str, actions: dict[str, dict[str, Any]]
) -> None:
    schema = actions[name]["inputSchema"]
    properties = schema.get("properties") or {}
    discriminator = "action" if "action" in properties else "operation"
    assert discriminator in properties, name
    assert schema.get("required") == [discriminator]

    # The root discriminator must be exactly the set of branch values: never
    # narrower (it would reject a legal call) and never wider (it would advertise
    # an operation that does not exist).
    advertised = set(properties[discriminator]["enum"])
    branch_values: set[str] = set()
    for variant in _branches(schema):
        branch_values |= _declared_values(variant["properties"][discriminator])
    assert advertised == branch_values, name

    # ``operation``/``action`` is the first key so a reader sees it first.
    assert next(iter(properties)) == discriminator


@pytest.mark.parametrize("name", sorted(FLATTENED_GATEWAYS))
def test_properties_lead_with_operation_then_identity(
    name: str, actions: dict[str, dict[str, Any]]
) -> None:
    identity_fields = ("repo_name", "run_id", "group_id", "workflow_id", "host_id")
    for variant in _branches(actions[name]["inputSchema"]):
        keys = list(variant.get("properties") or {})
        if not keys:
            continue
        leading = [key for key in ("operation", "action") if key in keys]
        if leading:
            assert keys[0] == leading[0], (name, keys)
        # Core identity sits right behind the discriminator. ``ssh_query``'s
        # profile_preview branch carries a payload field literally named
        # ``action``, which the ordering treats as discriminator-like, so allow
        # one slot of slack rather than demanding a fixed index.
        identity = [key for key in keys if key in identity_fields]
        if identity:
            assert keys.index(identity[0]) <= (2 if leading else 0), (name, keys)


@pytest.mark.parametrize("name", sorted(FLATTENED_GATEWAYS))
def test_schema_advertises_no_default_valued_noise(
    name: str, actions: dict[str, dict[str, Any]]
) -> None:
    """Clients must not be nudged into materializing default-valued fields."""
    for node in _walk(actions[name]["inputSchema"]):
        assert "default" not in node, (name, sorted(node))


def test_operation_specific_required_fields_are_preserved(
    actions: dict[str, dict[str, Any]]
) -> None:
    search = _branch(actions["repo_query"]["inputSchema"], "search_text")
    assert set(search["required"]) == {"operation", "repo_name", "query"}

    # Optional fields stay optional rather than becoming required to hide a default.
    assert {"directory", "file_path", "max_results", "case_sensitive"} <= set(
        search["properties"]
    )
    assert {"directory", "file_path"}.isdisjoint(search["required"])

    preflight = _branch(actions["run_query"]["inputSchema"], "preflight")
    assert set(preflight["required"]) == {"operation", "repo_name"}
    # A field belonging to a sibling operation must not leak in as required.
    assert "run_id" not in preflight["properties"]


def test_constraints_enums_and_ranges_survive_flattening(
    actions: dict[str, dict[str, Any]]
) -> None:
    search = _branch(actions["repo_query"]["inputSchema"], "search_text")
    properties = search["properties"]
    assert properties["repo_name"]["minLength"] == 1
    assert properties["repo_name"]["maxLength"] == 128
    assert properties["query"]["maxLength"] == 10_000
    assert properties["max_results"] == {"type": "integer", "minimum": 1, "maximum": 500}
    assert properties["response_budget_bytes"]["minimum"] == 16384
    assert properties["response_budget_bytes"]["maximum"] == 16384
    assert search["additionalProperties"] is False

    status = _branch(actions["repo_query"]["inputSchema"], "status")
    assert status["properties"]["view"]["enum"] == ["compact", "full"]

    move = _branch(actions["repo_apply"]["inputSchema"], "move_file")
    assert move["properties"]["expected_sha256"]["pattern"] == r"^[A-Fa-f0-9]{64}$"


def test_already_flat_gateway_is_left_alone(actions: dict[str, dict[str, Any]]) -> None:
    schema = actions["cancel_run"]["inputSchema"]
    assert set(schema["required"]) == {"run_id"}
    assert "request" not in (schema.get("properties") or {})


# --------------------------------------------------------------------------
# tool calls
# --------------------------------------------------------------------------


def _assert_transport_equivalence(result: Any) -> dict[str, Any]:
    """Guard the commit-33623c4 cross-client result-channel contract."""
    structured = result.structured_content
    assert result.content, "content[] must not be empty"
    text = result.content[0].text
    assert text, "content[0].text must be populated"
    decoded = json.loads(text)
    assert decoded == structured, "content[0].text must match structuredContent"
    budget = structured.get("response_budget_bytes")
    if isinstance(budget, int):
        assert len(text.encode("utf-8")) <= budget
        assert structured["response_bytes"] <= budget
    return structured


def test_flat_run_query_preflight(live_tools) -> None:
    result = _call(live_tools, "run_query", {"operation": "preflight", "repo_name": "soma"})
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is True
    assert structured["repo_name"] == "soma"


def test_flat_run_query_status_rejects_unknown_run(live_tools) -> None:
    result = _call(
        live_tools, "run_query", {"operation": "status", "run_id": "run_does_not_exist"}
    )
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is False


def test_flat_repo_query_search_text(live_tools) -> None:
    result = _call(
        live_tools,
        "repo_query",
        {
            "operation": "search_text",
            "repo_name": "soma",
            "query": "run_query",
            "directory": "soma",
            "max_results": 5,
            "budget_ms": 30000,
        },
    )
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is True
    # Defaults omitted by the caller are still applied by the request model.
    assert structured["case_sensitive"] is False
    assert structured["directory"] == "soma"
    assert structured["response_budget_bytes"] == 16384


def test_flat_repo_query_read_files(live_tools) -> None:
    result = _call(
        live_tools,
        "repo_query",
        {
            "operation": "read_files",
            "repo_name": "soma",
            "requests": [{"path": "README.md", "max_bytes": 512}],
        },
    )
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is True


def test_flat_repo_preview_patch_validates_without_mutating(live_tools) -> None:
    result = _call(
        live_tools,
        "repo_preview",
        {
            "operation": "patch",
            "repo_name": "soma",
            "operations": [
                {
                    "type": "replace_once",
                    "path": "tests/does-not-exist.txt",
                    "find": "a",
                    "replace": "b",
                }
            ],
        },
    )
    structured = _assert_transport_equivalence(result)
    # A preview never mutates; the missing path must surface as a failed preview.
    assert structured["ok"] is False


def test_flat_repo_apply_previewed_change_model_validation() -> None:
    """Validate the apply payload shape without performing a mutation."""
    schema = _discovered_actions()["repo_apply"]["inputSchema"]
    previewed = _branch(schema, "previewed_change")
    assert set(previewed["properties"]) == {"operation", "repo_name", "patch_id"}
    assert set(previewed["required"]) == {"operation", "repo_name", "patch_id"}

    flat = {"operation": "previewed_change", "repo_name": "soma", "patch_id": "patch_1"}
    Draft202012Validator(previewed).validate(flat)
    model = RepoPreviewedChangeApply.model_validate(
        normalize_gateway_arguments(flat)
    )
    assert model.patch_id == "patch_1"


def test_flat_knowledge_query_read_wiki(live_tools) -> None:
    result = _call(
        live_tools, "knowledge_query", {"operation": "read_wiki", "repo_name": "soma"}
    )
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is True


def test_flat_system_query_capabilities(live_tools) -> None:
    """A non-repository gateway on the flat contract."""
    result = _call(live_tools, "system_query", {"operation": "capabilities"})
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is True
    assert structured["actions_count"] >= len(PUBLIC_GATEWAY_NAMES)


def test_flat_workflow_query_is_a_non_repository_gateway(live_tools) -> None:
    result = _call(
        live_tools, "workflow_query", {"operation": "status", "workflow_id": "wf_missing"}
    )
    structured = _assert_transport_equivalence(result)
    assert structured["ok"] is False


# --------------------------------------------------------------------------
# backwards compatibility
# --------------------------------------------------------------------------


def test_legacy_wrapped_call_still_works(live_tools) -> None:
    legacy = _call(
        live_tools, "run_query", {"request": {"operation": "preflight", "repo_name": "soma"}}
    )
    flat = _call(live_tools, "run_query", {"operation": "preflight", "repo_name": "soma"})
    assert legacy.structured_content["ok"] is True
    assert (
        legacy.structured_content["tracked_worktree"]["head_commit"]
        == flat.structured_content["tracked_worktree"]["head_commit"]
    )
    _assert_transport_equivalence(legacy)


def test_legacy_form_is_not_advertised(actions: dict[str, dict[str, Any]]) -> None:
    for name in FLATTENED_GATEWAYS:
        encoded = json.dumps(actions[name]["inputSchema"])
        assert '"request"' not in encoded, name


def test_normalize_unwraps_only_a_lone_request_envelope() -> None:
    assert normalize_gateway_arguments({"operation": "status"}) == {"operation": "status"}
    assert normalize_gateway_arguments({"request": {"operation": "status"}}) == {
        "operation": "status"
    }
    assert normalize_gateway_arguments({}) == {}


# --------------------------------------------------------------------------
# negative validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, arguments",
    [
        ("run_query", {"repo_name": "soma"}),  # missing operation
        ("run_query", {"operation": "not_an_operation", "repo_name": "soma"}),
        ("run_query", {"operation": "preflight"}),  # missing required repo_name
        ("run_query", {"operation": "preflight", "repo_name": "soma", "bogus": 1}),
        # A field that belongs to a sibling operation must not be accepted.
        ("run_query", {"operation": "preflight", "repo_name": "soma", "tail_bytes": 10}),
        ("repo_query", {"operation": "search_text", "repo_name": "x" * 200, "query": "a"}),
        ("repo_query", {"operation": "search_text", "repo_name": "soma", "query": ""}),
        ("repo_query", {"operation": "status", "repo_name": "soma", "response_budget_bytes": 10}),
        ("repo_query", {"operation": "status", "repo_name": "soma", "view": "not_a_view"}),
        ("repo_apply", {"operation": "move_file", "repo_name": "soma",
                        "source_path": "a", "destination_path": "b",
                        "expected_sha256": "nothex"}),
    ],
)
def test_invalid_flat_payloads_are_rejected(live_tools, name, arguments) -> None:
    with pytest.raises(Exception) as excinfo:
        _call(live_tools, name, arguments)
    # The internal envelope must not leak into caller-facing error locations.
    assert "\nrequest." not in str(excinfo.value)


@pytest.mark.parametrize(
    "arguments",
    [
        {"request": "not-an-object"},
        {"request": ["operation"]},
        {"request": 7},
    ],
)
def test_malformed_wrapped_input_is_rejected(live_tools, arguments) -> None:
    with pytest.raises(Exception, match="must be an object"):
        _call(live_tools, "run_query", arguments)


def test_conflicting_flat_and_wrapped_payloads_are_rejected(live_tools) -> None:
    with pytest.raises(Exception, match="mix the flat form"):
        _call(
            live_tools,
            "run_query",
            {
                "operation": "preflight",
                "repo_name": "soma",
                "request": {"operation": "preflight", "repo_name": "other"},
            },
        )


# --------------------------------------------------------------------------
# flattening unit behaviour
# --------------------------------------------------------------------------


def test_flatten_ignores_schemas_without_a_request_envelope() -> None:
    assert flatten_request_input_schema({"type": "object", "properties": {"run_id": {}}}) is None
    assert flatten_request_input_schema({}) is None
    assert (
        flatten_request_input_schema(
            {"properties": {"request": {}, "extra": {}}, "required": ["request"]}
        )
        is None
    )


def test_flatten_resolves_a_referenced_envelope_and_keeps_defs() -> None:
    root = {
        "type": "object",
        "properties": {"request": {"$ref": "#/$defs/Payload"}},
        "required": ["request"],
        "$defs": {
            "Payload": {
                "type": "object",
                "properties": {
                    "extra": {"type": "string", "default": "x"},
                    "operation": {"const": "go", "type": "string"},
                },
                "required": ["operation"],
            }
        },
    }
    flat = flatten_request_input_schema(root)
    assert flat is not None
    assert flat["type"] == "object"
    assert list(flat["properties"]) == ["operation", "extra"]
    assert "default" not in flat["properties"]["extra"]
    assert flat["$defs"]["Payload"]["properties"]["operation"]["const"] == "go"


def test_flatten_preserves_a_property_literally_named_default() -> None:
    """``default`` stripping must respect schema positions, not bare key names."""
    root = {
        "type": "object",
        "properties": {
            "request": {
                "type": "object",
                "properties": {"default": {"type": "string", "default": "noise"}},
                "required": ["default"],
            }
        },
        "required": ["request"],
    }
    flat = flatten_request_input_schema(root)
    assert flat is not None
    assert "default" in flat["properties"]
    assert flat["properties"]["default"] == {"type": "string"}


def test_flat_gateway_tool_is_used_for_every_flattened_gateway() -> None:
    async def _tools() -> dict[str, Any]:
        register_knowledge_tools(server.mcp)
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    tools = asyncio.run(_tools())
    for name in FLATTENED_GATEWAYS:
        assert isinstance(tools[name], FlatGatewayTool), name
    assert not isinstance(tools["cancel_run"], FlatGatewayTool)


def test_discovered_schema_is_the_loaded_tool_schema_object() -> None:
    async def _tools() -> dict[str, Any]:
        register_knowledge_tools(server.mcp)
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    tools = asyncio.run(_tools())
    actions = _discovered_actions()
    for name in PUBLIC_GATEWAY_NAMES:
        assert actions[name]["inputSchema"] == tools[name].parameters, name
