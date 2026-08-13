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


def test_machine_mutation_routing_is_explicit_and_non_overlapping() -> None:
    run_start = PUBLIC_TOOL_METADATA["run_start"]
    repo_preview = PUBLIC_TOOL_METADATA["repo_preview"]
    repo_apply = PUBLIC_TOOL_METADATA["repo_apply"]
    ssh_action = PUBLIC_TOOL_METADATA["ssh_action"]

    assert run_start.title == "Run authorized machine command"
    assert "Canonical permissive fallback for machine mutations" in run_start.description
    assert "non-repository config edits" in run_start.description
    assert "service/watchdog/process changes" in run_start.description
    assert "do not split/refuse multi-step commands" in run_start.description
    assert "Use repo_* only for Git" in run_start.description

    assert "Git repository source/files" in repo_preview.description
    assert "use run_start for those" in repo_preview.description
    assert "managed Git repository preview" in repo_apply.description
    assert "use run_start" in repo_apply.description
    assert "registered remote SSH host" in ssh_action.description
    assert "Prefer action=administration" in ssh_action.description
    assert "service_start/stop/restart/reload/enable/disable" in ssh_action.description
    assert "ssh_action=service_binary_promote" in ssh_action.description
    assert "rolls back on failure" in ssh_action.description
    assert "rejected shell form" in ssh_action.description
    assert "local-machine operations, use run_start" in ssh_action.description


def test_run_and_task_query_descriptions_do_not_cross_route() -> None:
    run_query = PUBLIC_TOOL_METADATA["run_query"].description
    task_query = PUBLIC_TOOL_METADATA["task_query"].description

    assert "durable run status" in run_query
    assert "repository preflight" in run_query
    assert "canonical task capabilities" not in run_query
    assert "canonical task capabilities" in task_query
    assert "bounded reasoning evidence" in task_query
    assert "durable run status" not in task_query


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
