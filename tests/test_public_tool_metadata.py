from __future__ import annotations

from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
from soma.public_tool_metadata import ANNOTATION_KEYS, PUBLIC_TOOL_METADATA


def test_public_metadata_matches_the_32_tool_inventory() -> None:
    assert set(PUBLIC_TOOL_METADATA) == set(PUBLIC_GATEWAY_NAMES)
    assert len(PUBLIC_TOOL_METADATA) == 32
    assert len(PUBLIC_TOOL_METADATA) == len(set(PUBLIC_TOOL_METADATA))
    assert not set(PUBLIC_TOOL_METADATA) - set(PUBLIC_GATEWAY_NAMES)


def test_public_metadata_records_have_complete_human_facing_fields() -> None:
    for name, metadata in PUBLIC_TOOL_METADATA.items():
        assert metadata.name == name
        assert metadata.title.strip()
        assert metadata.description.startswith("Use this when")
        assert len(metadata.invoking) <= 64
        assert len(metadata.invoked) <= 64
        assert set(metadata.annotations) == ANNOTATION_KEYS
        assert all(type(value) is bool for value in metadata.annotations.values())


def test_candidate_b_conservative_annotations_are_exact() -> None:
    expected = {
        "knowledge_query": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        "knowledge_action": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        "ssh_query": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "docker_action": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "cloudflare_action": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "trading_query": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "repo_preview": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        "repo_apply": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        "cancel_run": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        "run_start": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "ssh_action": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    }

    for name, expected_annotations in expected.items():
        assert dict(PUBLIC_TOOL_METADATA[name].annotations) == expected_annotations
