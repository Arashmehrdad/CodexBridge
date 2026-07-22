from __future__ import annotations

import pytest

from soma.hermes_companion_protocol import (
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
    HermesCompanionProtocolError,
    HermesInterfaceDriftError,
    build_handshake,
    effective_schema_hash,
    tool_describe,
    tool_search,
)


TOOL_DEFINITIONS = [
    {
        "name": "filesystem.read_text",
        "description": "Read one text file",
        "toolset": "filesystem",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "github.issue_search",
        "description": "Search repository issues",
        "toolset": "github",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _handshake() -> dict:
    return build_handshake(
        registry_generation=7,
        tool_definitions=TOOL_DEFINITIONS,
        active_toolsets=["github", "filesystem", "github"],
        python_identity={"executable": "C:/Python/python.exe", "version": "3.12.4"},
        imported_modules=["tools.registry", "tools.tool_search"],
        initialization_warnings=["one plugin unavailable"],
    )


def test_handshake_binds_pinned_revision_registry_and_schema_without_model_runtime() -> None:
    handshake = _handshake()

    assert handshake["protocol_version"] == HERMES_COMPANION_PROTOCOL_VERSION
    assert handshake["hermes_revision"] == PINNED_HERMES_REVISION
    assert handshake["registry_generation"] == 7
    assert handshake["effective_schema_hash"] == effective_schema_hash(
        list(reversed(TOOL_DEFINITIONS))
    )
    assert handshake["active_toolsets"] == ["filesystem", "github"]
    assert handshake["model_runtime_initialized"] is False
    assert handshake["encoded_bytes"] > 0


def test_handshake_rejects_revision_protocol_and_model_runtime_drift() -> None:
    with pytest.raises(HermesInterfaceDriftError, match="revision"):
        build_handshake(
            registry_generation=1,
            tool_definitions=TOOL_DEFINITIONS,
            active_toolsets=[],
            python_identity={},
            hermes_revision="0" * 40,
        )
    with pytest.raises(HermesInterfaceDriftError, match="protocol"):
        build_handshake(
            registry_generation=1,
            tool_definitions=TOOL_DEFINITIONS,
            active_toolsets=[],
            python_identity={},
            protocol_version="2.0",
        )
    with pytest.raises(HermesCompanionProtocolError, match="model runtime"):
        build_handshake(
            registry_generation=1,
            tool_definitions=TOOL_DEFINITIONS,
            active_toolsets=[],
            python_identity={},
            imported_modules=["model_client.openai"],
        )


def test_search_is_bounded_deterministic_and_schema_bound() -> None:
    handshake = _handshake()
    schema_hash = effective_schema_hash(TOOL_DEFINITIONS)

    result = tool_search(
        query="repository",
        tool_definitions=list(reversed(TOOL_DEFINITIONS)),
        handshake=handshake,
        expected_registry_generation=7,
        expected_schema_hash=schema_hash,
        limit=10,
    )

    assert result["operation"] == "tool_search"
    assert result["result_count"] == 1
    assert result["results"][0]["name"] == "github.issue_search"
    assert len(result["results"][0]["schema_hash"]) == 64
    with pytest.raises(HermesCompanionProtocolError, match="output bound"):
        tool_search(
            query="file",
            tool_definitions=TOOL_DEFINITIONS,
            handshake=handshake,
            expected_registry_generation=7,
            expected_schema_hash=schema_hash,
            max_bytes=256,
        )


def test_describe_returns_one_exact_schema_and_rejects_interface_drift() -> None:
    handshake = _handshake()
    schema_hash = effective_schema_hash(TOOL_DEFINITIONS)

    result = tool_describe(
        tool_name="filesystem.read_text",
        tool_definitions=TOOL_DEFINITIONS,
        handshake=handshake,
        expected_registry_generation=7,
        expected_schema_hash=schema_hash,
    )

    assert result["operation"] == "tool_describe"
    assert result["definition"] == TOOL_DEFINITIONS[0]
    assert len(result["tool_schema_hash"]) == 64

    with pytest.raises(HermesInterfaceDriftError, match="generation"):
        tool_describe(
            tool_name="filesystem.read_text",
            tool_definitions=TOOL_DEFINITIONS,
            handshake=handshake,
            expected_registry_generation=8,
            expected_schema_hash=schema_hash,
        )
    with pytest.raises(HermesInterfaceDriftError, match="schema"):
        tool_describe(
            tool_name="filesystem.read_text",
            tool_definitions=TOOL_DEFINITIONS,
            handshake=handshake,
            expected_registry_generation=7,
            expected_schema_hash="f" * 64,
        )
    with pytest.raises(HermesCompanionProtocolError, match="unavailable"):
        tool_describe(
            tool_name="missing.tool",
            tool_definitions=TOOL_DEFINITIONS,
            handshake=handshake,
            expected_registry_generation=7,
            expected_schema_hash=schema_hash,
        )


def test_invalid_catalog_and_search_constraints_fail_closed() -> None:
    duplicate = [TOOL_DEFINITIONS[0], dict(TOOL_DEFINITIONS[0])]
    with pytest.raises(HermesCompanionProtocolError, match="unique"):
        effective_schema_hash(duplicate)

    handshake = _handshake()
    with pytest.raises(HermesCompanionProtocolError, match="query"):
        tool_search(
            query=" ",
            tool_definitions=TOOL_DEFINITIONS,
            handshake=handshake,
            expected_registry_generation=7,
            expected_schema_hash=effective_schema_hash(TOOL_DEFINITIONS),
        )
    with pytest.raises(HermesCompanionProtocolError, match="limit"):
        tool_search(
            query="file",
            tool_definitions=TOOL_DEFINITIONS,
            handshake=handshake,
            expected_registry_generation=7,
            expected_schema_hash=effective_schema_hash(TOOL_DEFINITIONS),
            limit=101,
        )
