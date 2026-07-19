from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace

import pytest

from codexbridge.hermes_companion import (
    HermesCompanion,
    HermesCompanionRuntimeError,
    HermesRegistrySnapshot,
    load_pinned_registry,
    serve_stdio,
)
from codexbridge.hermes_companion_protocol import (
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
)


DEFINITIONS = (
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
)


def _companion() -> HermesCompanion:
    return HermesCompanion(
        HermesRegistrySnapshot(
            generation=11,
            definitions=DEFINITIONS,
            active_toolsets=("filesystem", "github"),
        )
    )


def _bound_request(companion: HermesCompanion, operation: str, **values: object) -> dict:
    return {
        "operation": operation,
        "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
        "registry_generation": companion.handshake["registry_generation"],
        "effective_schema_hash": companion.handshake["effective_schema_hash"],
        **values,
    }


def test_dispatch_routes_handshake_search_and_describe_without_model_runtime() -> None:
    companion = _companion()

    handshake = companion.dispatch({"operation": "handshake"})
    search = companion.dispatch(
        _bound_request(companion, "tool_search", query="repository", limit=10)
    )
    describe = companion.dispatch(
        _bound_request(
            companion,
            "tool_describe",
            tool_name="filesystem.read_text",
        )
    )

    assert handshake["hermes_revision"] == PINNED_HERMES_REVISION
    assert handshake["model_runtime_initialized"] is False
    assert search["result_count"] == 1
    assert search["results"][0]["name"] == "github.issue_search"
    assert describe["definition"] == DEFINITIONS[0]


def test_dispatch_rejects_identity_drift_and_unknown_operations() -> None:
    companion = _companion()
    drifted = _bound_request(companion, "tool_search", query="file")
    drifted["effective_schema_hash"] = "f" * 64

    with pytest.raises(ValueError, match="schema drift"):
        companion.dispatch(drifted)
    with pytest.raises(ValueError, match="unsupported companion operation"):
        companion.dispatch(_bound_request(companion, "tool_call"))


def test_stdio_emits_one_bounded_json_response_per_request() -> None:
    companion = _companion()
    requests = [
        {"operation": "handshake"},
        _bound_request(companion, "tool_search", query="file", limit=10),
        {"operation": "tool_search", "protocol_version": "2.0"},
        ["not", "an", "object"],
    ]
    stdin = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
    stdout = io.StringIO()

    assert serve_stdio(companion, stdin, stdout) == 0
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]

    assert len(responses) == 4
    assert responses[0]["ok"] is True
    assert responses[1]["operation"] == "tool_search"
    assert responses[2]["ok"] is False
    assert responses[2]["error_type"] == "HermesCompanionProtocolError"
    assert responses[3]["ok"] is False


def test_pinned_loader_rejects_revision_drift_before_import(monkeypatch, tmp_path) -> None:
    imported = False

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="0" * 40 + "\n", stderr="")

    def fake_import(name: str):
        nonlocal imported
        imported = True
        raise AssertionError(name)

    monkeypatch.setattr("codexbridge.hermes_companion.subprocess.run", fake_run)
    monkeypatch.setattr("codexbridge.hermes_companion.importlib.import_module", fake_import)

    with pytest.raises(HermesCompanionRuntimeError, match="revision drift"):
        load_pinned_registry(tmp_path)
    assert imported is False


def test_pinned_loader_uses_discovered_pinned_registry_catalog(monkeypatch, tmp_path) -> None:
    observed_definition_calls: list[tuple[set[str], bool]] = []

    class Registry:
        generation = 3
        active_toolsets = ("filesystem",)

        def get_all_tool_names(self):
            return {"filesystem.read_text"}

        def get_definitions(self, tool_names, quiet=False):
            observed_definition_calls.append((set(tool_names), quiet))
            return [dict(DEFINITIONS[0])]

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=PINNED_HERMES_REVISION + "\n",
            stderr="",
        )

    discovered = {"called": False}

    def discover_builtin_tools():
        discovered["called"] = True
        return ["tools.filesystem"]

    monkeypatch.setattr("codexbridge.hermes_companion.subprocess.run", fake_run)
    monkeypatch.setattr(
        "codexbridge.hermes_companion.importlib.import_module",
        lambda name: SimpleNamespace(
            registry=Registry(), discover_builtin_tools=discover_builtin_tools
        ),
    )

    snapshot = load_pinned_registry(tmp_path)

    assert discovered["called"] is True
    assert observed_definition_calls == [({"filesystem.read_text"}, True)]
    assert snapshot.generation == 3
    assert snapshot.definitions == (DEFINITIONS[0],)


def test_pinned_loader_imports_only_registry_and_rejects_model_runtime(monkeypatch, tmp_path) -> None:
    class Registry:
        generation = 3
        active_toolsets = ("filesystem",)

        def get_all_tool_names(self):
            return {"filesystem.read_text"}

        def get_definitions(self, tool_names, quiet=False):
            return [dict(DEFINITIONS[0])]

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=PINNED_HERMES_REVISION + "\n",
            stderr="",
        )

    observed_imports: list[str] = []

    def fake_import(name: str):
        observed_imports.append(name)
        sys.modules["model_client.openai"] = SimpleNamespace()
        return SimpleNamespace(
            registry=Registry(), discover_builtin_tools=lambda: ["tools.filesystem"]
        )

    monkeypatch.setattr("codexbridge.hermes_companion.subprocess.run", fake_run)
    monkeypatch.setattr("codexbridge.hermes_companion.importlib.import_module", fake_import)
    try:
        with pytest.raises(ValueError, match="model runtime"):
            load_pinned_registry(tmp_path)
    finally:
        sys.modules.pop("model_client.openai", None)

    assert observed_imports == ["tools.registry"]
