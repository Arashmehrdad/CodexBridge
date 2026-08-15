from __future__ import annotations

import asyncio
import hashlib
import json

import soma.server as server
from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
from soma.public_tool_metadata import (
    ANNOTATION_KEYS,
    PUBLIC_TOOL_METADATA,
    fastmcp_registration_kwargs,
)


PRE_B3_DESCRIPTOR_HASH = (
    "4480a27354c0f140ed2931904dfe1c786f3c8c30b01ca7e69384965ecaaa1c49"
)
PRE_B3_INPUT_SCHEMA_HASH = (
    "bb32b7c07dba1d71f90dda396ed11e92ddf1192e9c76460f6d0bc0ed3ea0b176"
)
CURRENT_INPUT_SCHEMA_HASH = (
    "fc7d024201ac816919577a4cb618873bae82d12bdbb1afa3833e601d44ee8c48"
)
PRE_B3_OUTPUT_SCHEMA_HASH = (
    "247aa7e6a7958ca51decb7f8e5a68119315ed949a54315e4b671a8e35ad91bde"
)
CURRENT_OUTPUT_SCHEMA_HASH = (
    "356b08f3f6b8cc66dd6b586d14ff9502c5ae6d2ad6e9f9a747ce3f9db3e73e69"
)
PRE_B3_OPERATION_INVENTORY_HASH = (
    "a6f31b3275f074d0660ba4aa48f3886cce2093bf5847cf0e3eae172afae92377"
)
CURRENT_OPERATION_INVENTORY_HASH = (
    "ffdcc0d5f7bb2d93316c3ce0b67de86b1d8f1dc35162316005b95a117417165b"
)


def _actions() -> list[dict]:
    server.refresh_public_contract_hash()
    tools = asyncio.run(server.mcp.list_tools())
    return [
        tool.to_mcp_tool().model_dump(mode="json", by_alias=True, exclude_none=False)
        for tool in tools
    ]


def _schema_digest(actions: list[dict], field: str) -> str:
    payload = [
        {"name": action["name"], field: action[field]}
        for action in sorted(actions, key=lambda action: action["name"])
    ]
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def test_registry_metadata_is_the_exact_fastmcp_public_descriptor_authority() -> None:
    actions = _actions()
    by_name = {action["name"]: action for action in actions}

    assert len(actions) == 38
    assert set(by_name) == set(PUBLIC_GATEWAY_NAMES)
    assert set(by_name) == set(PUBLIC_TOOL_METADATA)
    for name, metadata in PUBLIC_TOOL_METADATA.items():
        action = by_name[name]
        assert action["title"] == metadata.title
        assert action["description"] == metadata.description
        assert {key: action["annotations"][key] for key in ANNOTATION_KEYS} == dict(
            metadata.annotations
        )
        assert action["_meta"]["openai/toolInvocation/invoking"] == metadata.invoking
        assert action["_meta"]["openai/toolInvocation/invoked"] == metadata.invoked
        assert action["title"].strip()
        assert "fastmcp" in action["_meta"]


def test_registry_conversion_overrides_generic_fields_and_preserves_other_meta() -> (
    None
):
    generic = {
        "title": "Generic title",
        "description": "Generic description",
        "annotations": {"readOnlyHint": False},
        "meta": {
            "fastmcp": {"tags": ["sdk-owned"]},
            "sdk_owned": {"preserve": True},
            "openai/toolInvocation/invoking": "wrong",
        },
    }
    merged = fastmcp_registration_kwargs("repo_query", **generic)

    assert merged["title"] == PUBLIC_TOOL_METADATA["repo_query"].title
    assert merged["description"] == PUBLIC_TOOL_METADATA["repo_query"].description
    assert merged["annotations"] == dict(PUBLIC_TOOL_METADATA["repo_query"].annotations)
    assert merged["meta"]["fastmcp"] == {"tags": ["sdk-owned"]}
    assert merged["meta"]["sdk_owned"] == {"preserve": True}
    assert merged["meta"]["openai/toolInvocation/invoking"] == (
        PUBLIC_TOOL_METADATA["repo_query"].invoking
    )
    assert fastmcp_registration_kwargs("internal_tool", **generic) == generic


def test_public_registration_name_prefers_explicit_name_over_wrapped_function() -> None:
    def wrapped_function() -> None:
        return None

    assert server._public_tool_registration_name(wrapped_function, (), {}) == (
        "wrapped_function"
    )
    assert (
        server._public_tool_registration_name(
            wrapped_function, ("positional_name",), {}
        )
        == "positional_name"
    )
    assert (
        server._public_tool_registration_name(
            wrapped_function, (), {"name": "keyword_name"}
        )
        == "keyword_name"
    )


def test_current_public_gateway_schema_identity_is_intentional() -> None:
    actions = _actions()

    assert server._input_schema_hash_from_actions(actions) == (
        "5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd"
    )
    assert _schema_digest(actions, "inputSchema") == CURRENT_INPUT_SCHEMA_HASH
    assert CURRENT_INPUT_SCHEMA_HASH != PRE_B3_INPUT_SCHEMA_HASH
    assert _schema_digest(actions, "outputSchema") == CURRENT_OUTPUT_SCHEMA_HASH
    assert CURRENT_OUTPUT_SCHEMA_HASH != PRE_B3_OUTPUT_SCHEMA_HASH
    operation_inventory_hash = server._operation_identity_metadata(actions=actions)[
        "operation_inventory_hash"
    ]
    assert operation_inventory_hash == CURRENT_OPERATION_INVENTORY_HASH
    assert CURRENT_OPERATION_INVENTORY_HASH != PRE_B3_OPERATION_INVENTORY_HASH
    assert server._descriptor_hash_from_actions(actions) != PRE_B3_DESCRIPTOR_HASH
