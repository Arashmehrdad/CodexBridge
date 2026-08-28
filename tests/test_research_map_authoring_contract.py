from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from soma.gateway_models import ResearchMapQueryRequest
from soma.research_map import relation_id
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


def _snapshot(repo: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (path.relative_to(repo).as_posix(), path.read_bytes())
        for path in repo.rglob("*")
        if path.is_file()
    )


def test_authoring_contract_exposes_exact_mechanics_without_mutation(tmp_path: Path) -> None:
    _manifest(tmp_path)
    before = _snapshot(tmp_path)

    result = research_map_query_gateway(
        tmp_path,
        project_id="proj_authoring",
        repo_name="repo",
        operation="authoring_contract",
        response_budget_bytes=32 * 1024,
    )

    assert result["ok"] is True
    assert result["status"] == "available"
    assert result["schema_version"] == "soma.research-map.v2"
    assert result["predicate_registry_version"] == "soma.research-map.predicates.v1"
    assert result["roots"] == [
        {
            "path": "docs/research",
            "sidecar_dir": "_soma_map",
            "include": ["*.md"],
        }
    ]
    assert result["sidecar_json_schema"]["title"] == "ResearchMapSidecar"
    assert len(result["sidecar_json_schema_sha256"]) == 64
    assert result["source_hash_contract"]["line_endings"] == (
        "normalize CRLF and CR to LF before hashing"
    )
    identity = result["relation_identity"]
    assert identity["helper_operation"] == "relation_id"
    assert identity["identity_fields"] == [
        "source_path",
        "subject_key",
        "predicate",
        "object_key",
    ]
    assert identity["statement_in_identity"] is False
    assert identity["labels_in_identity"] is False
    assert identity["anchor_in_identity"] is False
    assert result["authoring_boundary"]["materiality_owner"] == (
        "project scientific/research controller"
    )
    assert result["authoring_boundary"]["auto_generate_semantics"] is False
    assert result["response_bytes"] <= result["response_budget_bytes"]
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".soma").exists()


def test_relation_id_helper_matches_canonical_identity_and_sidecar_path(tmp_path: Path) -> None:
    _manifest(tmp_path)
    before = _snapshot(tmp_path)

    result = research_map_query_gateway(
        tmp_path,
        project_id="proj_authoring",
        repo_name="repo",
        operation="relation_id",
        source_path="docs\\research\\042_result.md",
        subject_key="  finding:r042  ",
        predicate="SUPPORTS",
        object_key="  claim:r042  ",
    )

    expected = relation_id(
        "docs/research/042_result.md",
        "finding:r042",
        "SUPPORTS",
        "claim:r042",
    )
    assert result == {
        "ok": True,
        "operation": "relation_id",
        "status": "generated",
        "project_id": "proj_authoring",
        "repo_name": "repo",
        "source_path": "docs/research/042_result.md",
        "expected_sidecar_path": "docs/research/_soma_map/042_result.json",
        "relation_id": expected,
        "identity": {
            "subject_key": "finding:r042",
            "predicate": "SUPPORTS",
            "object_key": "claim:r042",
        },
        "statement_in_identity": False,
        "error": "",
    }
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / ".soma").exists()


def test_relation_id_helper_refuses_paths_outside_adopted_roots(tmp_path: Path) -> None:
    _manifest(tmp_path)
    result = research_map_query_gateway(
        tmp_path,
        project_id="proj_authoring",
        repo_name="repo",
        operation="relation_id",
        source_path="notes/not_research.md",
        subject_key="finding:x",
        predicate="SUPPORTS",
        object_key="claim:x",
    )
    assert result["ok"] is False
    assert result["status"] == "source_not_owned"


def test_authoring_helpers_require_adoption(tmp_path: Path) -> None:
    contract = research_map_query_gateway(
        tmp_path,
        project_id="proj_authoring",
        repo_name="repo",
        operation="authoring_contract",
        response_budget_bytes=32 * 1024,
    )
    identity = research_map_query_gateway(
        tmp_path,
        project_id="proj_authoring",
        repo_name="repo",
        operation="relation_id",
        source_path="docs/research/a.md",
        subject_key="finding:a",
        predicate="SUPPORTS",
        object_key="claim:a",
    )
    assert contract["status"] == "not_adopted"
    assert identity["status"] == "not_adopted"
    assert not (tmp_path / ".soma").exists()


def test_public_request_contract_exposes_authoring_helpers_strictly() -> None:
    adapter = TypeAdapter(ResearchMapQueryRequest)
    contract = adapter.validate_python(
        {
            "operation": "authoring_contract",
            "project_id": "proj_authoring",
            "repo_name": "repo",
        }
    )
    assert contract.operation == "authoring_contract"

    identity = adapter.validate_python(
        {
            "operation": "relation_id",
            "project_id": "proj_authoring",
            "repo_name": "repo",
            "source_path": "docs/research/a.md",
            "subject_key": "finding:a",
            "predicate": "SUPPORTS",
            "object_key": "claim:a",
        }
    )
    assert identity.operation == "relation_id"
    assert str(identity.predicate) == "SUPPORTS"

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "operation": "relation_id",
                "project_id": "proj_authoring",
                "repo_name": "repo",
                "source_path": "docs/research/a.md",
                "subject_key": "finding:a",
                "predicate": "MADE_UP",
                "object_key": "claim:a",
            }
        )
