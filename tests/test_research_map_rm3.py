from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from soma import server
from soma.config import AppConfig, RepoConfig
from soma.gateway_models import ResearchMapQueryRequest
from soma.project_scope import ProjectScopeStore
from soma.research_map import canonical_text_sha256, relation_id
from soma.research_map.gateway import research_map_query_gateway


def _manifest(repo: Path) -> None:
    (repo / "soma.project.json").write_text(
        json.dumps(
            {
                "schema": "soma.project.v1",
                "repository_uid": "srepo_0123456789abcdef",
                "research_map": {
                    "enabled": True,
                    "schema": "soma.research-map.v2",
                    "roots": [
                        {
                            "path": "docs/research",
                            "sidecar_dir": "_soma_map",
                            "include": ["*.md"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def _source(repo: Path, name: str, text: str) -> str:
    source_path = f"docs/research/{name}.md"
    path = repo / source_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return source_path


def _sidecar(
    repo: Path,
    source_path: str,
    text: str,
    *,
    relation: dict | None = None,
) -> None:
    payload = {
        "schema_version": "soma.research-map.v2",
        "source": {
            "path": source_path,
            "canonical_text_sha256": canonical_text_sha256(text),
        },
        "review": {
            "state": "reviewed",
            "controller": "Sol",
            "materiality": "material" if relation else "none",
        },
        "facets": {},
        "relations": [relation] if relation else [],
    }
    source = Path(source_path)
    path = repo / source.parent / "_soma_map" / f"{source.stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _relation(source_path: str, anchor: str) -> dict:
    subject = "finding:rm3"
    predicate = "SUPPORTS"
    object_key = "claim:rm3"
    return {
        "relation_id": relation_id(source_path, subject, predicate, object_key),
        "subject": {"key": subject, "label": "RM3 finding"},
        "predicate": predicate,
        "object": {"key": object_key, "label": "RM3 claim"},
        "statement": "RM3 exact relation lookup preserves reviewed semantics.",
        "locator": {"anchor": anchor},
        "epistemic_class": "observed",
        "lifecycle": "current",
        "supersedes": [],
        "facets": {},
        "qualifiers": {},
    }


def _snapshot(repo: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (path.relative_to(repo).as_posix(), path.read_bytes())
        for path in repo.rglob("*")
        if path.is_file()
    )


def test_rm3_health_is_read_only_and_unadopted_is_bounded(tmp_path: Path) -> None:
    before = _snapshot(tmp_path)
    result = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="health",
    )
    after = _snapshot(tmp_path)

    assert result["ok"] is True
    assert result["status"] == "not_adopted"
    assert result["adoption_state"] == "not_adopted"
    assert result["manifest_state"] == "missing"
    assert result["semantic_desired_state_sha256"] is None
    assert before == after
    assert not (tmp_path / ".soma").exists()


def test_rm3_malformed_manifest_degrades_only_research_map(tmp_path: Path) -> None:
    (tmp_path / "soma.project.json").write_text("{broken", encoding="utf-8")
    result = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="health",
    )
    assert result["ok"] is True
    assert result["status"] == "degraded"
    assert result["manifest_state"] == "malformed"
    assert result["backend_state"] == "unavailable"


def test_rm3_coverage_cursor_is_deterministic_and_state_bound(tmp_path: Path) -> None:
    _manifest(tmp_path)
    for name in ("001_a", "002_b", "003_c"):
        text = f"# {name}\n"
        source_path = _source(tmp_path, name, text)
        _sidecar(tmp_path, source_path, text)

    first = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="coverage",
        limit=2,
        response_budget_bytes=12 * 1024,
    )
    assert [item["source_path"] for item in first["items"]] == [
        "docs/research/001_a.md",
        "docs/research/002_b.md",
    ]
    assert first["has_more"] is True

    second = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="coverage",
        limit=2,
        cursor=first["next_cursor"],
        response_budget_bytes=12 * 1024,
    )
    assert [item["source_path"] for item in second["items"]] == [
        "docs/research/003_c.md"
    ]

    changed = tmp_path / "docs/research/003_c.md"
    changed.write_text("# 003_c\nchanged\n", encoding="utf-8")
    stale = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="coverage",
        limit=2,
        cursor=first["next_cursor"],
        response_budget_bytes=12 * 1024,
    )
    assert stale["ok"] is False
    assert stale["status"] == "stale_cursor"


def test_rm3_exact_relation_and_search_unavailable_do_not_create_runtime(tmp_path: Path) -> None:
    _manifest(tmp_path)
    text = "# Relation\nexact anchor\n"
    source_path = _source(tmp_path, "010_relation", text)
    relation = _relation(source_path, "exact anchor")
    _sidecar(tmp_path, source_path, text, relation=relation)
    before = _snapshot(tmp_path)

    exact = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="relation",
        relation_id=relation["relation_id"],
        response_budget_bytes=32 * 1024,
    )
    assert exact["ok"] is True
    assert exact["status"] == "found"
    assert exact["relation"]["statement"] == relation["statement"]
    assert exact["effective_lifecycle"] == "current"
    assert len(exact["relation_content_sha256"]) == 64

    search = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="search",
        query="anything",
        limit=5,
    )
    assert search["ok"] is False
    assert search["status"] == "backend_unavailable"
    assert search["results"] == []
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".soma").exists()


def test_rm3_public_request_schema_requires_exact_project_scope() -> None:
    adapter = TypeAdapter(ResearchMapQueryRequest)
    with pytest.raises(ValidationError):
        adapter.validate_python({"operation": "health", "repo_name": "repo"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"operation": "health", "project_id": "proj_rm3"})


def test_rm3_server_gateway_enforces_project_scope(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs = tmp_path / "runs"
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(repo))},
        runs_dir=str(runs),
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    scope = ProjectScopeStore(runs)
    scope.init_db()
    scope.apply_bootstrap(
        project_id="proj_rm3",
        project_key="rm3",
        resource_id="res_rm3_repo",
        repo_name="repo",
        repository_root=repo,
    )
    monkeypatch.setattr(server, "get_project_scope_store", lambda: scope)
    request = TypeAdapter(ResearchMapQueryRequest).validate_python(
        {"operation": "health", "project_id": "proj_rm3", "repo_name": "repo"}
    )
    accepted = server.research_map_query(request)
    assert accepted["status"] == "not_adopted"
    assert accepted["resource_id"] == "res_rm3_repo"

    wrong = TypeAdapter(ResearchMapQueryRequest).validate_python(
        {"operation": "health", "project_id": "proj_other", "repo_name": "repo"}
    )
    refused = server.research_map_query(wrong)
    assert refused["ok"] is False
    assert refused["status"] == "scope_mismatch"


def test_rm3_relation_response_remains_bounded_with_large_facets(tmp_path: Path) -> None:
    _manifest(tmp_path)
    text = "# Large\nlarge anchor\n"
    source_path = _source(tmp_path, "020_large", text)
    relation = _relation(source_path, "large anchor")
    relation["facets"] = {"large": [f"{index:02d}-" + "x" * 896 for index in range(40)]}
    _sidecar(tmp_path, source_path, text, relation=relation)
    result = research_map_query_gateway(
        tmp_path,
        project_id="proj_rm3",
        repo_name="repo",
        operation="relation",
        relation_id=relation["relation_id"],
        response_budget_bytes=4 * 1024,
    )
    assert result["response_bytes"] <= 4 * 1024
    assert result["truncated"] is True
    assert result["relation_content_sha256"]
