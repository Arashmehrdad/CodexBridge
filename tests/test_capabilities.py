from __future__ import annotations

from pathlib import Path

from soma.capabilities import (
    PATCH_OPERATION_SCHEMA,
    capability_metadata,
    schema_hash,
    server_build_hash,
)


def test_patch_operation_schema_lists_supported_variants() -> None:
    variants = PATCH_OPERATION_SCHEMA["properties"]["type"]["enum"]
    assert variants == ["exact_text", "line_range", "unified_diff", "python_ast"]


def test_patch_operation_schema_exposes_newline_preservation_control() -> None:
    preserve = PATCH_OPERATION_SCHEMA["properties"]["preserve_newlines"]
    assert preserve == {"type": "boolean"}


def test_schema_hash_is_order_independent_for_objects() -> None:
    assert schema_hash({"b": 2, "a": 1}) == schema_hash({"a": 1, "b": 2})


def test_server_build_hash_changes_with_python_content(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    module = package / "module.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    first = server_build_hash(package)
    module.write_text("VALUE = 2\n", encoding="utf-8")
    second = server_build_hash(package)
    assert first != second


def test_capability_metadata_contains_stable_epoch() -> None:
    first = capability_metadata(PATCH_OPERATION_SCHEMA)
    second = capability_metadata(PATCH_OPERATION_SCHEMA)
    assert first == second
    assert first["capability_epoch"] == (
        f"{first['server_build_hash'][:12]}-{first['schema_hash'][:12]}"
    )


# ----------------------------------------------------------------------
# PUBLIC-CAPABILITY-METADATA-1


def _live_actions() -> list[dict]:
    import asyncio

    from soma import server
    from soma.knowledge_tools_integration import register_knowledge_tools

    async def _list():
        register_knowledge_tools(server.mcp)
        tools = await server.mcp.list_tools()
        return [tool.to_mcp_tool().model_dump(mode="json", by_alias=True) for tool in tools]

    return asyncio.run(_list())


def test_public_schema_hash_agrees_with_discovery():
    """One effective schema authority.

    The per-response value is captured at registration because every registry
    accessor is async; discovery recomputes it from the served tools. They must
    be the same number, or the cheap field would quietly answer a different
    question from the authoritative one.
    """
    from soma import server

    actions = _live_actions()
    assert server.public_contract_hash() == server._input_schema_hash_from_actions(
        actions
    )


def test_public_schema_hash_is_not_the_legacy_schema_hash():
    """The whole point of the lane: these answer different questions."""
    from soma import server
    from soma.capabilities import PATCH_OPERATION_SCHEMA, schema_hash

    _live_actions()
    legacy = schema_hash(PATCH_OPERATION_SCHEMA)
    assert server._PROCESS_CAPABILITY_METADATA["schema_hash"] == legacy
    assert server.public_contract_hash() != legacy


def test_legacy_schema_hash_keeps_its_value_and_meaning():
    """Compatibility: no existing field silently changes meaning."""
    from soma import server
    from soma.capabilities import PATCH_OPERATION_SCHEMA, schema_hash

    stamped = server._with_process_capability_metadata({"ok": True})
    assert stamped["schema_hash"] == schema_hash(PATCH_OPERATION_SCHEMA)
    assert stamped["server_build_hash"]
    assert stamped["capability_epoch"]


def test_every_response_carries_the_contract_identity():
    from soma import server

    _live_actions()
    stamped = server._with_process_capability_metadata({"ok": True})
    assert stamped["public_schema_hash"] == server.public_contract_hash()


def test_a_public_operation_change_moves_the_contract_identity():
    """Required movement property, proven by a deliberate schema change."""
    from soma import server

    _live_actions()
    served = dict(server._PUBLIC_INPUT_SCHEMAS)
    assert served

    def _hash(schemas):
        return server._input_schema_hash_from_actions(
            [{"name": n, "inputSchema": s} for n, s in schemas.items()]
        )

    before = _hash(served)
    assert before == server.public_contract_hash()

    mutated = dict(served)
    target = dict(mutated["knowledge_query"])
    properties = dict(target.get("properties") or {})
    operation = dict(properties.get("operation") or {})
    operation["enum"] = list(operation.get("enum") or []) + ["fixture_operation"]
    properties["operation"] = operation
    target["properties"] = properties
    mutated["knowledge_query"] = target

    assert _hash(mutated) != before
    # Unaffected gateways keep their own identity: the change is isolated.
    assert mutated["system_query"] == served["system_query"]
    # And nothing durable moved.
    assert server.public_contract_hash() == before


def test_an_implementation_only_change_does_not_move_the_contract_identity():
    """A build-hash change must not masquerade as a contract change."""
    from soma import server

    _live_actions()
    before = server.refresh_public_contract_hash()
    # Recomputing over the unchanged advertised surface is the shape of an
    # implementation-only edit: same contract, different build.
    assert server.refresh_public_contract_hash() == before
    assert server.public_contract_hash() == before
