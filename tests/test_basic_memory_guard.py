"""BASIC-MEMORY-GUARD-1 acceptance tests.

These mirror the implementation-acceptance list in
docs/BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md. The provider itself is
not installed for these tests: the guard is exercised through an injected runner,
which is the point -- the guard must refuse correctly without ever depending on
provider behaviour.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from soma.memory_guard import (
    ALLOWED_OPERATIONS,
    BasicMemoryGuard,
    BasicMemoryProvider,
    HealthState,
    IdentityRefused,
    PathRefused,
    ProfileRefused,
    ProjectBindingResolver,
    ProviderProfile,
    StaticBindingSource,
    ToolRefused,
    literal_search,
    load_profile,
    os_manifest,
    read_note,
    validate_env,
    validate_profile,
)
from soma.memory_guard.health import build_coverage, disposition
from soma.memory_guard.profile import FORCED_ENV

PROJECT_A = "proj_a144f759-1619-4276-9292-28704b6611f4"
PROJECT_B = "proj_0cf013d0-191b-57f4-a84b-7a43819a1578"


# ----------------------------------------------------------------------
# fixtures


class FakeScopeStore:
    """Minimal stand-in exposing only the connect() surface the guard uses."""

    def __init__(self, projects: dict[str, tuple[str, int]]) -> None:
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE projects (project_id TEXT PRIMARY KEY, "
            "lifecycle_state TEXT NOT NULL, scope_generation INTEGER NOT NULL)"
        )
        for project_id, (state, generation) in projects.items():
            self._conn.execute(
                "INSERT INTO projects VALUES (?, ?, ?)",
                (project_id, state, generation),
            )
        self._conn.commit()

    def connect(self) -> sqlite3.Connection:
        # The guard closes what it opens; hand out a view over the same data.
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE projects (project_id TEXT PRIMARY KEY, "
            "lifecycle_state TEXT NOT NULL, scope_generation INTEGER NOT NULL)"
        )
        rows = self._conn.execute("SELECT * FROM projects").fetchall()
        conn.executemany("INSERT INTO projects VALUES (?, ?, ?)", rows)
        conn.commit()
        return conn


def write_note(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{name}"\n---\n\n{body}\n', encoding="utf-8", newline="\n"
    )
    return path


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "projects" / "soma-pilot"
    b = tmp_path / "projects" / "soma-lab-pilot"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    write_note(a, "service-endpoint.md", "Listener on port 8801. ALPHA_CANARY")
    write_note(a, "worker-ceiling.md", "At most 4 units of work. BETA_CANARY")
    write_note(b, "lab-service-endpoint.md", "Lab listener on port 9142. LAB_CANARY")
    return a, b


@pytest.fixture()
def profile(tmp_path: Path, roots: tuple[Path, Path]) -> ProviderProfile:
    a, b = roots
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "ensure_frontmatter_on_sync": False,
                "default_project": None,
                "auto_update": False,
                "logfire_enabled": False,
                "logfire_send_to_logfire": False,
                "cloud_api_key": None,
                "default_workspace": None,
                "projects": {
                    "soma-pilot": {"path": str(a)},
                    "soma-lab-pilot": {"path": str(b)},
                },
            }
        ),
        encoding="utf-8",
    )
    return load_profile(config_dir)


def make_guard(
    profile: ProviderProfile,
    roots: tuple[Path, Path],
    responses: dict[str, tuple[int, str]],
    *,
    lifecycles: dict[str, tuple[str, int]] | None = None,
    record: list[list[str]] | None = None,
) -> BasicMemoryGuard:
    a, b = roots
    source = StaticBindingSource(
        {
            PROJECT_A: ("soma-pilot", str(a)),
            PROJECT_B: ("soma-lab-pilot", str(b)),
        }
    )
    store = FakeScopeStore(
        lifecycles or {PROJECT_A: ("active", 1), PROJECT_B: ("active", 1)}
    )
    resolver = ProjectBindingResolver(source, scope_store=store)

    def runner(argv, env, timeout):
        if record is not None:
            record.append(list(argv))
        for key, (code, out) in responses.items():
            if key in " ".join(argv):
                return code, out, ""
        return 0, "", ""

    return BasicMemoryGuard(resolver, profile, BasicMemoryProvider(profile, runner))


def healthy_responses(files: int, project: str = "soma-pilot") -> dict:
    return {
        "project info": (0, json.dumps({"entity_count": files})),
        "status": (0, json.dumps({"total": 0})),
    }


# ----------------------------------------------------------------------
# exact identity binding


def test_two_sibling_projects_bind_exactly(profile, roots):
    guard = make_guard(profile, roots, healthy_responses(2))
    a = guard.bind(PROJECT_A)
    b = guard.bind(PROJECT_B)
    assert a.provider_project == "soma-pilot"
    assert b.provider_project == "soma-lab-pilot"
    assert a.canonical_root != b.canonical_root
    assert a.root_identity_hash != b.root_identity_hash


@pytest.mark.parametrize("omitted", [None, "", "   "])
def test_omitted_identity_is_refused(profile, roots, omitted):
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(IdentityRefused, match="project_id is required"):
        guard.bind(omitted)


def test_unknown_project_is_refused(profile, roots):
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(IdentityRefused, match="not present in ProjectScope"):
        guard.bind("proj_does-not-exist")


@pytest.mark.parametrize("state", ["suspended", "archived"])
def test_inactive_project_is_refused(profile, roots, state):
    guard = make_guard(
        profile,
        roots,
        healthy_responses(2),
        lifecycles={PROJECT_A: (state, 1), PROJECT_B: ("active", 1)},
    )
    with pytest.raises(IdentityRefused, match=state):
        guard.bind(PROJECT_A)


def test_mismatched_claimed_identity_is_refused(profile, roots):
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(IdentityRefused, match="project_mismatch"):
        guard.bind(PROJECT_A, claimed_project_id=PROJECT_B)


def test_project_present_in_scope_but_unbound_is_refused(profile, roots, tmp_path):
    a, b = roots
    source = StaticBindingSource({PROJECT_A: ("soma-pilot", str(a))})
    store = FakeScopeStore({PROJECT_A: ("active", 1), PROJECT_B: ("active", 1)})
    resolver = ProjectBindingResolver(source, scope_store=store)
    with pytest.raises(IdentityRefused, match="no approved provider binding"):
        resolver.resolve(PROJECT_B)


def test_binding_table_refuses_shared_provider_project(roots):
    a, b = roots
    with pytest.raises(IdentityRefused, match="exactly one Soma project"):
        StaticBindingSource(
            {PROJECT_A: ("shared", str(a)), PROJECT_B: ("shared", str(b))}
        )


def test_binding_table_refuses_shared_root(roots):
    a, _ = roots
    with pytest.raises(IdentityRefused, match="one Markdown root"):
        StaticBindingSource(
            {PROJECT_A: ("soma-pilot", str(a)), PROJECT_B: ("soma-lab-pilot", str(a))}
        )


# ----------------------------------------------------------------------
# local-only profile


def test_profile_refuses_provider_markdown_mutation(profile):
    config = dict(profile.config)
    config["ensure_frontmatter_on_sync"] = True
    with pytest.raises(ProfileRefused, match="mutating_profile"):
        validate_profile(config)


def test_profile_refuses_configured_default_project(profile):
    config = dict(profile.config)
    config["default_project"] = "soma-pilot"
    with pytest.raises(ProfileRefused, match="default_project"):
        validate_profile(config)


def test_profile_refuses_reachable_cloud_credentials(profile):
    config = dict(profile.config)
    config["cloud_api_key"] = "sk-live-something"
    with pytest.raises(ProfileRefused, match="cloud_reachable"):
        validate_profile(config)


def test_profile_refuses_missing_setting(profile):
    config = dict(profile.config)
    del config["auto_update"]
    with pytest.raises(ProfileRefused, match="missing required setting"):
        validate_profile(config)


def test_environment_forces_local_and_refuses_cloud_overrides(profile):
    env = profile.env()
    validate_env(env)
    for key, value in FORCED_ENV.items():
        assert env[key] == value
    with pytest.raises(ProfileRefused, match="cloud_reachable"):
        validate_env({**env, "BASIC_MEMORY_FORCE_CLOUD": "1"})


# ----------------------------------------------------------------------
# tool allowlist


def test_allowlist_is_small_and_read_or_rebuild_only(profile, roots):
    assert set(ALLOWED_OPERATIONS) == {
        "search", "read_note", "status", "project_info", "reindex"
    }


@pytest.mark.parametrize("operation", ["doctor", "cloud", "write_note", "reset"])
def test_operations_outside_allowlist_are_refused(profile, roots, operation):
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(ToolRefused, match="not in the guard allowlist"):
        guard._provider.call(operation, provider_project="soma-pilot")


def test_status_wait_is_refused_as_a_sync_mechanism(profile, roots):
    """The pilot measured `bm status --wait` livelocking; it is never used."""
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(ToolRefused, match="forbidden_sync_path"):
        guard._provider.call("status", "--wait", provider_project="soma-pilot")


def test_cloud_flag_is_refused(profile, roots):
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(ToolRefused, match="forbidden_sync_path"):
        guard._provider.call("search", "q", "--cloud", provider_project="soma-pilot")


# ----------------------------------------------------------------------
# coverage and health


def test_complete_coverage_is_healthy_and_permits_semantic(profile, roots):
    guard = make_guard(profile, roots, healthy_responses(2))
    health = guard.health(PROJECT_A)
    assert health.state is HealthState.HEALTHY
    assert health.semantic_permitted


def test_unparsable_provider_count_is_unproven_not_complete(profile, roots):
    guard = make_guard(
        profile,
        roots,
        {"project info": (0, "Project: soma-pilot"), "status": (0, '{"total": 0}')},
    )
    health = guard.health(PROJECT_A)
    assert health.state is HealthState.DEGRADED
    assert not health.semantic_permitted
    assert health.coverage.provider_entities is None


def test_partial_coverage_blocks_semantic(profile, roots):
    guard = make_guard(
        profile,
        roots,
        {"project info": (0, '{"entity_count": 1}'), "status": (0, '{"total": 0}')},
    )
    health = guard.health(PROJECT_A)
    assert health.state is HealthState.DEGRADED
    assert not health.semantic_permitted
    assert "1 of 2" in health.detail


def test_pending_changes_report_rebuilding(profile, roots):
    guard = make_guard(
        profile,
        roots,
        {"project info": (0, '{"entity_count": 2}'), "status": (0, '{"total": 3}')},
    )
    health = guard.health(PROJECT_A)
    assert health.state is HealthState.REBUILDING
    assert not health.semantic_permitted


def test_empty_root_is_unavailable(profile, roots, tmp_path):
    a, _ = roots
    for note in a.glob("*.md"):
        note.unlink()
    guard = make_guard(
        profile,
        roots,
        {"project info": (0, '{"entity_count": 0}'), "status": (0, '{"total": 0}')},
    )
    assert guard.health(PROJECT_A).state is HealthState.UNAVAILABLE


# ----------------------------------------------------------------------
# fail-closed retrieval and fallback


def test_semantic_blocked_falls_back_to_canonical_markdown(profile, roots):
    guard = make_guard(
        profile,
        roots,
        {"project info": (0, '{"entity_count": 1}'), "status": (0, '{"total": 0}')},
    )
    result = guard.search(PROJECT_A, "ALPHA_CANARY")
    assert result.used_fallback
    assert not result.health.semantic_permitted
    assert [item["file_path"] for item in result.items] == ["service-endpoint.md"]


def test_semantic_blocked_without_fallback_returns_nothing_not_a_guess(profile, roots):
    guard = make_guard(
        profile,
        roots,
        {"project info": (0, '{"entity_count": 1}'), "status": (0, '{"total": 0}')},
    )
    result = guard.search(PROJECT_A, "ALPHA_CANARY", allow_fallback=False)
    assert result.items == ()
    assert not result.used_fallback


def test_unparsed_provider_response_is_not_read_as_no_matches(profile, roots):
    responses = healthy_responses(2)
    responses["search-notes"] = (0, "not json at all")
    guard = make_guard(profile, roots, responses)
    result = guard.search(PROJECT_A, "ALPHA_CANARY")
    assert result.used_fallback
    assert result.items


def test_healthy_semantic_search_uses_provider(profile, roots):
    record: list[list[str]] = []
    responses = healthy_responses(2)
    responses["search-notes"] = (
        0,
        json.dumps(
            {"results": [{"file_path": "service-endpoint.md",
                          "permalink": "soma-pilot/service-endpoint"}]}
        ),
    )
    guard = make_guard(profile, roots, responses, record=record)
    result = guard.search(PROJECT_A, "which port")
    assert not result.used_fallback
    assert result.items[0]["file_path"] == "service-endpoint.md"
    search_argv = [a for a in record if "search-notes" in a]
    assert ["--project", "soma-pilot"] == search_argv[0][-2:]
    assert "--vector" in search_argv[0]


# ----------------------------------------------------------------------
# path validation and sibling isolation


def test_sibling_permalink_in_results_is_refused(profile, roots):
    responses = healthy_responses(2)
    responses["search-notes"] = (
        0,
        json.dumps(
            {"results": [{"file_path": "service-endpoint.md",
                          "permalink": "soma-lab-pilot/lab-service-endpoint"}]}
        ),
    )
    guard = make_guard(profile, roots, responses)
    with pytest.raises(PathRefused, match="another provider"):
        guard.search(PROJECT_A, "which port")


def test_escaping_result_path_is_refused(profile, roots):
    responses = healthy_responses(2)
    responses["search-notes"] = (
        0,
        json.dumps({"results": [{"file_path": "../soma-lab-pilot/lab-service-endpoint.md"}]}),
    )
    guard = make_guard(profile, roots, responses)
    with pytest.raises(PathRefused, match="path_outside_root"):
        guard.search(PROJECT_A, "which port")


def test_read_outside_root_is_refused(profile, roots):
    guard = make_guard(profile, roots, healthy_responses(2))
    with pytest.raises(PathRefused):
        guard.read(PROJECT_A, "../soma-lab-pilot/lab-service-endpoint.md")


def test_fallback_never_leaves_the_bound_root(roots):
    a, b = roots
    hits = literal_search(a, "CANARY")
    assert hits
    for hit in hits:
        assert not str(hit["file_path"]).startswith("..")
    assert literal_search(a, "LAB_CANARY") == []


# ----------------------------------------------------------------------
# rebuild delegation


def test_rebuild_plan_uses_reindex_and_is_not_executed(profile, roots):
    record: list[list[str]] = []
    guard = make_guard(profile, roots, healthy_responses(2), record=record)
    plan = guard.rebuild_plan(PROJECT_A)
    assert plan.argv == ("reindex", "--full", "--project", "soma-pilot")
    assert "--wait" not in plan.argv
    assert plan.env["BASIC_MEMORY_MCP_PROJECT"] == "soma-pilot"
    assert plan.env["BASIC_MEMORY_FORCE_LOCAL"] == "1"
    # planning must not invoke the provider
    assert not any("reindex" in " ".join(argv) for argv in record)


# ----------------------------------------------------------------------
# scope discipline


def test_guard_does_not_import_production_memory_or_a_retrieval_stack():
    import ast

    package = Path(__file__).resolve().parents[1] / "soma" / "memory_guard"
    forbidden = {
        "soma.memory", "numpy", "fastembed", "onnxruntime", "torch",
        "sentence_transformers", "sqlite_vec", "litellm", "openai",
    }
    seen: set[str] = set()
    for module in package.glob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                seen.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                seen.add(node.module)
    assert not (seen & forbidden), f"guard imports forbidden modules: {seen & forbidden}"


def test_os_manifest_excludes_provider_and_vcs_state(tmp_path):
    root = tmp_path / "vault"
    write_note(root, "keep.md", "body")
    write_note(root / ".obsidian", "ignored.md", "body")
    write_note(root / ".git", "ignored.md", "body")
    assert os_manifest(root) == ("keep.md",)
