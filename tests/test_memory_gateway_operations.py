"""MEMORY-INTEGRATION-FOUNDATION-1 steps 5, 7-9.

One synthetic project driven end to end through the real public gateway pair:
save, get, lexical search, supersession, lifecycle transitions, health, context
packet and exact packet retrieval — plus sibling isolation, scope refusal, and
the honest degraded state that the step 2 measurement forces.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import TypeAdapter

from soma.config import AppConfig, RepoConfig
from soma.gateway_models import KnowledgeActionRequest, KnowledgeQueryRequest
from soma.knowledge_tools_integration import register_knowledge_tools
from soma.project_scope import ProjectScopeStore

PROJECT_ID = "proj_memory_foundation_1"
SIBLING_PROJECT_ID = "proj_memory_foundation_sibling"


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}

    def tool(self, *, output_schema: dict, annotations: dict):
        def decorator(function):
            self.tools[function.__name__] = {
                "function": function,
                "output_schema": output_schema,
                "annotations": annotations,
            }
            return function

        return decorator


@pytest.fixture()
def gateway(tmp_path: Path, monkeypatch):
    repo = tmp_path / "soma"
    (repo / "src").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "src" / "main.py").write_text("print('soma')\n", encoding="utf-8")

    sibling = tmp_path / "lab"
    (sibling / "src").mkdir(parents=True)
    (sibling / ".git").mkdir()
    (sibling / "src" / "main.py").write_text("print('lab')\n", encoding="utf-8")

    vault = tmp_path / "Soma Memory"
    config = AppConfig(
        repos={
            "soma": RepoConfig(path=str(repo)),
            "lab": RepoConfig(path=str(sibling)),
        },
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    # The production intent: an owner-facing vault outside runs/ and outside any
    # code repository.
    config.canonical_memory.canonical_vault_root = str(vault)
    config.canonical_memory.canonical_vault_kind = "external_private_vault"

    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="memory-foundation",
        resource_id="res_memory_foundation",
        repo_name="soma",
        repository_root=repo,
    )
    scope.apply_bootstrap(
        project_id=SIBLING_PROJECT_ID,
        project_key="memory-foundation-lab",
        resource_id="res_memory_foundation_lab",
        repo_name="lab",
        repository_root=sibling,
    )

    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_memory_gateway_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: config
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    register_knowledge_tools(mcp)
    return mcp, config, vault


def query(mcp, payload: dict) -> dict:
    return mcp.tools["knowledge_query"]["function"](
        TypeAdapter(KnowledgeQueryRequest).validate_python(payload)
    )


def action(mcp, payload: dict) -> dict:
    return mcp.tools["knowledge_action"]["function"](
        TypeAdapter(KnowledgeActionRequest).validate_python(payload)
    )


def project_scope(project_id: str = PROJECT_ID, repo_name: str = "soma") -> dict:
    return {"kind": "project", "project_id": project_id, "repo_name": repo_name}


def save_payload(**overrides) -> dict:
    payload = {
        "action": "memory_save",
        "scope": project_scope(),
        "vault_path": "decisions/listener-port.md",
        "kind": "decision",
        "title": "Listener port",
        "summary": "The listener accepts connections on port 8801.",
        "body": "The listener accepts connections on port 8801. ALPHACANARY",
        "controller": "claude_code",
        "idempotency_key": "listener-port-1",
    }
    payload.update(overrides)
    return payload


# ----------------------------------------------------------------------
# end-to-end flow


def test_save_then_search_then_get_round_trips_through_the_gateway(gateway):
    mcp, _config, vault = gateway

    saved = action(mcp, save_payload())
    assert saved["ok"] is True, saved.get("error")
    assert saved["memory_id"].startswith("kn_")
    assert saved["content_sha256"]

    # Canonical Markdown landed in the owner-facing vault, not under runs/.
    written = vault / "projects" / PROJECT_ID / "decisions" / "listener-port.md"
    assert written.is_file()
    assert "ALPHACANARY" in written.read_text(encoding="utf-8")

    found = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": project_scope(),
            "query": "ALPHACANARY",
        },
    )
    assert found["ok"] is True, found.get("error")
    assert [record["knowledge_id"] for record in found["records"]] == [
        saved["memory_id"]
    ]
    assert found["records"][0]["vault_path"] == "decisions/listener-port.md"

    exact = query(
        mcp,
        {
            "operation": "memory_get",
            "scope": project_scope(),
            "knowledge_id": saved["memory_id"],
            "view": "full",
        },
    )
    assert exact["ok"] is True
    assert "ALPHACANARY" in exact["record"]["body"]


def test_retrieval_states_its_mode_and_never_claims_semantic(gateway):
    """Step 2 measured that completeness is unprovable, so the answer says so."""
    mcp, _config, _vault = gateway
    action(mcp, save_payload())

    found = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": project_scope(),
            "query": "ALPHACANARY",
        },
    )
    assert found["retrieval_mode"] == "catalog_lexical"
    assert found["provider_health"] == "degraded"
    assert found["canonical_health"] == "healthy"


def test_sibling_project_sees_nothing(gateway):
    mcp, _config, _vault = gateway
    action(mcp, save_payload())

    leaked = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": project_scope(SIBLING_PROJECT_ID, "lab"),
            "query": "ALPHACANARY",
        },
    )
    assert leaked["ok"] is True, leaked.get("error")
    assert leaked["records"] == []


def test_wrong_project_for_repository_is_refused(gateway):
    mcp, _config, _vault = gateway
    refused = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": project_scope(SIBLING_PROJECT_ID, "soma"),
            "query": "ALPHACANARY",
        },
    )
    assert refused["ok"] is False
    assert "ProjectScope" in refused["error"]


def test_personal_scope_is_refused_at_the_gateway(gateway):
    mcp, _config, _vault = gateway
    refused = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": {"kind": "personal", "owner_id": "owner_arash"},
            "query": "anything",
        },
    )
    assert refused["ok"] is False


# ----------------------------------------------------------------------
# lifecycle


def test_supersession_replaces_the_current_answer(gateway):
    mcp, _config, _vault = gateway
    original = action(mcp, save_payload())

    replacement = action(
        mcp,
        save_payload(
            action="memory_supersede",
            vault_path="decisions/listener-port-v2.md",
            title="Listener port (corrected)",
            body="The listener accepts connections on port 9902. ALPHACANARY",
            idempotency_key="listener-port-2",
            supersedes_ids=[original["memory_id"]],
        ),
    )
    assert replacement["ok"] is True, replacement.get("error")

    found = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": project_scope(),
            "query": "ALPHACANARY",
        },
    )
    ids = [record["knowledge_id"] for record in found["records"]]
    assert replacement["memory_id"] in ids
    assert original["memory_id"] not in ids


def test_lifecycle_transition_requires_the_expected_hash(gateway):
    mcp, _config, _vault = gateway
    saved = action(mcp, save_payload())

    stale = action(
        mcp,
        {
            "action": "memory_archive",
            "scope": project_scope(),
            "knowledge_id": saved["memory_id"],
            "expected_sha256": "0" * 64,
        },
    )
    assert stale["ok"] is False
    assert "re-read before correcting" in stale["error"]

    archived = action(
        mcp,
        {
            "action": "memory_archive",
            "scope": project_scope(),
            "knowledge_id": saved["memory_id"],
            "expected_sha256": saved["content_sha256"],
        },
    )
    assert archived["ok"] is True, archived.get("error")
    assert archived["status"] == "archived"


# ----------------------------------------------------------------------
# health, owner edits, packets, rebuild


def test_owner_authored_note_is_reported_not_treated_as_corruption(gateway):
    mcp, _config, vault = gateway
    action(mcp, save_payload())
    (vault / "projects" / PROJECT_ID / "shopping.md").write_text(
        "Milk, bread, plumber.\n", encoding="utf-8"
    )

    synced = action(
        mcp, {"action": "memory_sync_provider", "scope": project_scope()}
    )
    assert synced["ok"] is True, synced.get("error")
    assert synced["unadopted_count"] == 1
    assert synced["malformed_count"] == 0

    health = query(
        mcp, {"operation": "memory_health", "scope": project_scope()}
    )
    assert health["canonical_health"] == "healthy"
    assert health["unadopted_count"] == 1


def test_context_packet_is_stored_and_retrievable_exactly(gateway):
    mcp, _config, _vault = gateway
    saved = action(mcp, save_payload())

    packet = query(
        mcp,
        {
            "operation": "memory_context",
            "scope": project_scope(),
            "query": "ALPHACANARY",
        },
    )
    assert packet["ok"] is True, packet.get("error")
    assert packet["packet_id"].startswith("pkt_")
    assert packet["packet_sha256"]
    assert packet["retrieval_mode"] == "catalog_lexical"

    exact = query(
        mcp,
        {
            "operation": "memory_packet_get",
            "scope": project_scope(),
            "packet_id": packet["packet_id"],
        },
    )
    assert exact["ok"] is True, exact.get("error")
    assert exact["packet_id"] == packet["packet_id"]
    assert exact["records"][0]["knowledge_id"] == saved["memory_id"]


def test_rebuild_refuses_while_completeness_is_unprovable(gateway):
    """Launching work whose result cannot be believed would be dishonest."""
    mcp, _config, _vault = gateway
    refused = action(
        mcp,
        {
            "action": "memory_rebuild_index",
            "scope": project_scope(),
            "controller_request_id": "req-1",
        },
    )
    assert refused["ok"] is False
    assert "semantic retrieval is disabled" in refused["error"]
    assert "memory_sync_provider" in refused["error"]


def test_memory_and_research_remain_separate_authorities(gateway):
    """A memory note must not surface as reviewed research."""
    mcp, _config, _vault = gateway
    action(mcp, save_payload())

    research = query(
        mcp,
        {
            "operation": "search_research",
            "project_id": PROJECT_ID,
            "repo_name": "soma",
            "query": "ALPHACANARY",
        },
    )
    assert research.get("records", []) == [] or research["ok"] is False
