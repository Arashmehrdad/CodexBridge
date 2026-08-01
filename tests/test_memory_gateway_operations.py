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

import jsonschema
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

    unbound = tmp_path / "new_project"
    (unbound / "src").mkdir(parents=True)
    (unbound / ".git").mkdir()
    (unbound / "src" / "main.py").write_text(
        "print('new project')\n", encoding="utf-8"
    )

    vault = tmp_path / "Soma Memory"
    config = AppConfig(
        repos={
            "soma": RepoConfig(path=str(repo)),
            "lab": RepoConfig(path=str(sibling)),
            "new_project": RepoConfig(path=str(unbound)),
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
    """Invoke, then validate against the declared output schema.

    Regression: the dispatch returned keys the published schema did not
    declare. Calling the inner function directly hid it, while the live MCP
    surface validates output and rejected the response *after* the canonical
    write had already landed -- so the caller could not tell whether its write
    had succeeded. Every action response is now schema-checked here.
    """
    result = mcp.tools["knowledge_action"]["function"](
        TypeAdapter(KnowledgeActionRequest).validate_python(payload)
    )
    jsonschema.validate(result, mcp.tools["knowledge_action"]["output_schema"])
    return result


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
# explicit repository onboarding


def test_unbound_repository_can_be_bound_then_saved(gateway):
    mcp, _config, vault = gateway

    unresolved = query(
        mcp,
        {"operation": "memory_scope", "repo_name": "new_project"},
    )
    assert unresolved["ok"] is False
    assert "No active repository binding" in unresolved["error"]

    bound = action(
        mcp,
        {
            "action": "memory_bind_repository",
            "repo_name": "new_project",
            "project_key": "new-project-custom-key",
        },
    )
    assert bound["ok"] is True, bound.get("error")
    assert bound["binding_applied"] is True
    assert bound["idempotent"] is True
    assert bound["project_id"].startswith("proj_repo_")
    assert bound["project_key"] == "new-project-custom-key"
    assert bound["resource_id"].startswith("res_repo_")
    assert bound["scope"] == {
        "kind": "project",
        "project_id": bound["project_id"],
        "repo_name": "new_project",
    }

    resolved = query(
        mcp,
        {"operation": "memory_scope", "repo_name": "new_project"},
    )
    assert resolved["ok"] is True, resolved.get("error")
    assert resolved["scope"] == bound["scope"]

    saved = action(
        mcp,
        {
            "action": "memory_save",
            "scope": bound["scope"],
            "kind": "handoff",
            "title": "New project handoff",
            "body": "The repository is now bound to canonical memory.",
            "idempotency_key": "new-project-handoff-1",
        },
    )
    assert saved["ok"] is True, saved.get("error")
    assert (
        vault
        / "projects"
        / bound["project_id"]
        / saved["vault_path"]
    ).is_file()

    repeated = action(
        mcp,
        {"action": "memory_bind_repository", "repo_name": "new_project"},
    )
    assert repeated["ok"] is True
    assert repeated["binding_applied"] is False
    assert repeated["project_key"] == bound["project_key"]
    assert repeated["scope"] == bound["scope"]


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


def test_drift_is_reported_then_accepted_only_on_purpose(gateway):
    """The whole repair path, through the public surface."""
    mcp, _config, vault = gateway
    saved = action(mcp, save_payload())

    path = vault / "projects" / PROJECT_ID / "decisions" / "listener-port.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("ALPHACANARY", "ALPHACANARY EDITED"),
        encoding="utf-8",
    )
    synced = action(
        mcp, {"action": "memory_sync_provider", "scope": project_scope()}
    )
    assert synced["ok"] is True, synced.get("error")
    assert synced["drifted_count"] == 1
    assert synced["malformed_count"] == 0

    health = query(mcp, {"operation": "memory_health", "scope": project_scope()})
    assert health["canonical_health"] == "dirty"
    assert health["drifted_paths"] == ["decisions/listener-port.md"]

    # The record still answers, and says its provenance is unverified.
    found = query(
        mcp,
        {
            "operation": "memory_search",
            "scope": project_scope(),
            "query": "ALPHACANARY",
        },
    )
    assert found["records"]
    assert any("integrity hash" in warning for warning in found["warnings"])

    # Accepting the *old* hash is refused: the caller must name what it adopts.
    refused = action(
        mcp,
        {
            "action": "memory_accept_drift",
            "scope": project_scope(),
            "knowledge_id": saved["memory_id"],
            "accepted_sha256": saved["content_sha256"],
        },
    )
    assert refused["ok"] is False
    assert "re-read before accepting" in refused["error"]

    current = query(
        mcp,
        {
            "operation": "memory_get",
            "scope": project_scope(),
            "knowledge_id": saved["memory_id"],
        },
    )
    assert current["record"]["integrity_drift"] is True
    assert current["record"]["actual_sha256"]
    assert current["record"]["actual_sha256"] != current["record"]["content_sha256"]
    accepted = action(
        mcp,
        {
            "action": "memory_accept_drift",
            "scope": project_scope(),
            "knowledge_id": saved["memory_id"],
            # The hash to adopt comes from the read itself; a caller must not
            # have to recompute it out of band to repair anything.
            "accepted_sha256": current["record"]["actual_sha256"],
            "reason": "owner reviewed the Obsidian edit",
        },
    )
    assert accepted["ok"] is True, accepted.get("error")
    assert accepted["revision"] == 2
    assert "EDITED" in current["record"]["excerpt"]

    settled = query(mcp, {"operation": "memory_health", "scope": project_scope()})
    assert settled["canonical_health"] == "healthy"
    assert settled["drifted_count"] == 0


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


# ----------------------------------------------------------------------
# MEMORY-CONTROLLER-ERGONOMICS-1


def test_a_controller_can_discover_its_scope_from_a_repository_name(gateway):
    """A fresh controller knows a repo name, not an opaque project_id."""
    mcp, _config, _vault = gateway

    discovered = query(mcp, {"operation": "memory_scope", "repo_name": "soma"})

    assert discovered["ok"] is True, discovered.get("error")
    assert discovered["scope"] == {
        "kind": "project",
        "project_id": PROJECT_ID,
        "repo_name": "soma",
    }
    assert discovered["canonical_health"]
    assert discovered["vault_root"]


def test_the_discovered_scope_is_accepted_verbatim_by_every_memory_call(gateway):
    """Discovery is only useful if its output is directly usable."""
    mcp, _config, _vault = gateway
    scope = query(mcp, {"operation": "memory_scope", "repo_name": "soma"})["scope"]

    saved = action(mcp, {**save_payload(), "scope": scope})
    assert saved["ok"] is True, saved.get("error")

    health = query(mcp, {"operation": "memory_health", "scope": scope})
    assert health["ok"] is True, health.get("error")
    assert health["canonical_count"] == 1


def test_discovery_does_not_become_a_silent_default(gateway):
    """Scope stays explicit on every call; discovery is a separate step.

    Inferring the project at call time is what the architecture forbids: a
    memory operation must never quietly decide which project it addressed.
    """
    mcp, _config, _vault = gateway
    with pytest.raises(Exception):
        query(mcp, {"operation": "memory_health"})


def test_unknown_repository_is_refused_with_an_actionable_reason(gateway):
    mcp, _config, _vault = gateway
    refused = query(mcp, {"operation": "memory_scope", "repo_name": "not-a-repo"})
    assert refused["ok"] is False
    assert refused["error"]


def test_vault_path_is_derived_from_kind_and_title_when_omitted(gateway):
    """The one thing every caller previously had to invent per write."""
    mcp, _config, vault = gateway
    payload = save_payload()
    payload.pop("vault_path")

    saved = action(mcp, {**payload, "kind": "lesson", "title": "Counts are not membership"})

    assert saved["ok"] is True, saved.get("error")
    assert saved["vault_path"] == "lessons/counts-are-not-membership.md"
    written = vault / "projects" / PROJECT_ID / "lessons" / "counts-are-not-membership.md"
    assert written.is_file()


def test_an_explicit_vault_path_still_wins(gateway):
    """The owner's own filing of their vault outranks a generated name."""
    mcp, _config, _vault = gateway
    saved = action(
        mcp, {**save_payload(), "vault_path": "architecture/chosen-by-hand.md"}
    )
    assert saved["vault_path"] == "architecture/chosen-by-hand.md"


def test_a_title_with_no_usable_stem_is_refused_not_given_a_placeholder(gateway):
    """A generated placeholder would put an unfindable record in the vault."""
    mcp, _config, _vault = gateway
    payload = save_payload()
    payload.pop("vault_path")
    with pytest.raises(Exception, match="vault_path"):
        action(mcp, {**payload, "title": "،؟!"})
