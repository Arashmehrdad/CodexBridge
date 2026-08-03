from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.hermes_companion_client import (
    build_companion_launch,
    parse_companion_result,
    start_companion_request,
)
from soma.hermes_companion_protocol import (
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
)


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def start_executable_profile(self, repo_name: str, profile_id: str, argv: list[str], **kwargs):
        self.calls.append(
            {
                "repo_name": repo_name,
                "profile_id": profile_id,
                "argv": argv,
                **kwargs,
            }
        )
        return {"accepted": True, "run_id": "run-1"}


def test_build_handshake_launch_is_one_bounded_request(tmp_path: Path) -> None:
    checkout = tmp_path / "hermes"
    checkout.mkdir()

    launch = build_companion_launch(
        profile_id="python",
        checkout=checkout,
        operation="handshake",
    )

    request = json.loads(launch.stdin_text)
    assert request == {"operation": "handshake"}
    assert launch.argv[:3] == ("-m", "soma.hermes_companion", "--hermes-checkout")
    assert launch.checkout == str(checkout.resolve())
    assert launch.stdin_text.endswith("\n")


def test_build_bound_search_launch_persists_catalog_identity(tmp_path: Path) -> None:
    checkout = tmp_path / "hermes"
    checkout.mkdir()
    schema_hash = "a" * 64

    launch = build_companion_launch(
        profile_id="python",
        checkout=checkout,
        operation="tool_search",
        payload={"query": "github", "limit": 5},
        expected_registry_generation=7,
        expected_schema_hash=schema_hash,
    )

    request = json.loads(launch.stdin_text)
    assert request["protocol_version"] == HERMES_COMPANION_PROTOCOL_VERSION
    assert request["registry_generation"] == 7
    assert request["effective_schema_hash"] == schema_hash
    assert request["query"] == "github"

    call = build_companion_launch(
        profile_id="python",
        checkout=checkout,
        operation="tool_call",
        payload={"tool_name": "filesystem.read_text", "arguments": {"path": "README.md"}},
        expected_registry_generation=7,
        expected_schema_hash=schema_hash,
    )
    call_request = json.loads(call.stdin_text)
    assert call_request["tool_name"] == "filesystem.read_text"
    assert call_request["arguments"] == {"path": "README.md"}


def test_start_request_reuses_durable_executable_lifecycle(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "hermes"
    checkout.mkdir()
    manager = FakeManager()
    monkeypatch.chdir(tmp_path)
    launch = build_companion_launch(
        profile_id="python",
        checkout=checkout,
        operation="handshake",
    )

    response = start_companion_request(manager, "sample", launch)

    assert response["accepted"] is True
    assert response["hermes_companion"]["hermes_revision"] == PINNED_HERMES_REVISION
    assert response["hermes_companion"]["one_request"] is True
    assert manager.calls == [
        {
            "repo_name": "sample",
            "profile_id": "python",
            "argv": list(launch.argv),
            "working_directory": str(tmp_path.resolve()),
            "stdin_text": launch.stdin_text,
            "environment": {},
            "timeout_seconds": 120,
            "hermes_companion": {
                "operation": "handshake",
                "hermes_revision": PINNED_HERMES_REVISION,
                "checkout": launch.checkout,
                "expected_registry_generation": None,
                "expected_schema_hash": "",
                "one_request": True,
            },
        }
    ]


def test_repository_owned_hermes_home_is_the_only_environment_override(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "hermes"
    checkout.mkdir()
    home = tmp_path / "runs" / "isolated-hermes-home"
    home.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    launch = build_companion_launch(
        profile_id="python",
        checkout=checkout,
        hermes_home=home,
        operation="handshake",
    )
    assert launch.environment == {"HERMES_HOME": str(home.resolve())}

    outside = tmp_path.parent / "outside-hermes-home"
    outside.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="contained by the repository"):
        build_companion_launch(
            profile_id="python",
            checkout=checkout,
            hermes_home=outside,
            operation="handshake",
        )


def test_parse_handshake_and_bound_response_verify_exact_identity() -> None:
    schema_hash = "b" * 64
    handshake = {
        "ok": True,
        "operation": "handshake",
        "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
        "hermes_revision": PINNED_HERMES_REVISION,
        "registry_generation": 4,
        "effective_schema_hash": schema_hash,
        "model_runtime_initialized": False,
    }
    assert parse_companion_result(
        json.dumps(handshake), expected_operation="handshake"
    ) == handshake

    search = {
        "ok": True,
        "operation": "tool_search",
        "registry_generation": 4,
        "effective_schema_hash": schema_hash,
        "results": [],
    }
    assert parse_companion_result(
        json.dumps(search),
        expected_operation="tool_search",
        expected_registry_generation=4,
        expected_schema_hash=schema_hash,
    ) == search


def test_client_rejects_unbound_or_ambiguous_execution(tmp_path: Path) -> None:
    checkout = tmp_path / "hermes"
    checkout.mkdir()

    with pytest.raises(ValueError, match="expected_registry_generation"):
        build_companion_launch(
            profile_id="python",
            checkout=checkout,
            operation="tool_describe",
            payload={"tool_name": "filesystem.read_text"},
        )
    with pytest.raises(ValueError, match="emitted no response"):
        parse_companion_result("\n", expected_operation="handshake")
    with pytest.raises(ValueError, match="exactly one response"):
        parse_companion_result("{}\n{}\n", expected_operation="handshake")
    with pytest.raises(ValueError, match="operation drift"):
        parse_companion_result(
            json.dumps({"ok": True, "operation": "tool_search"}),
            expected_operation="handshake",
        )
