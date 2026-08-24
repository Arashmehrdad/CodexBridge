from __future__ import annotations

import pytest
from pydantic import ValidationError

from soma.research_map.canonical import canonical_text_sha256, relation_id
from soma.research_map.models import (
    ProjectManifest,
    ResearchMapRelation,
    ResearchMapSidecar,
)


def _valid_relation(path: str = "docs/research/038_example.md") -> dict:
    subject_key = "research:038"
    predicate = "FORBIDS"
    object_key = "mechanism:generic-upstream-dendritic-gating"
    return {
        "relation_id": relation_id(path, subject_key, predicate, object_key),
        "subject": {"key": subject_key, "label": "Research 038"},
        "predicate": predicate,
        "object": {"key": object_key, "label": "generic upstream dendritic gating revival"},
        "statement": (
            "Research 038 must not relabel generic upstream dendritic/context gating "
            "as a new solution."
        ),
        "locator": {
            "anchor": "must therefore not relabel generic upstream dendritic gating as a new solution — آزمون"
        },
        "epistemic_class": "constraint",
        "lifecycle": "current",
        "supersedes": [],
        "facets": {"programme": ["NSDN"], "thread": ["associative-geometry"]},
        "qualifiers": {"scope": ["upstream-gating"]},
    }


def _valid_sidecar() -> dict:
    path = "docs/research/038_example.md"
    return {
        "schema_version": "soma.research-map.v2",
        "source": {
            "path": path,
            "canonical_text_sha256": canonical_text_sha256("# Research 038\n"),
        },
        "review": {
            "state": "reviewed",
            "controller": "Sol",
            "materiality": "material",
        },
        "facets": {"programme": ["NSDN"]},
        "relations": [_valid_relation(path)],
    }


def test_valid_sidecar_round_trips_unicode_exactly() -> None:
    sidecar = ResearchMapSidecar.model_validate(_valid_sidecar())
    dumped = sidecar.model_dump(mode="json")

    assert dumped["relations"][0]["locator"]["anchor"].endswith("— آزمون")
    assert dumped["relations"][0]["predicate"] == "FORBIDS"
    assert dumped["relations"][0]["epistemic_class"] == "constraint"


def test_strict_sidecar_rejects_unknown_schema_predicate_lifecycle_and_epistemic() -> None:
    cases = []

    bad_schema = _valid_sidecar()
    bad_schema["schema_version"] = "soma.research-map.v999"
    cases.append(bad_schema)

    bad_predicate = _valid_sidecar()
    bad_predicate["relations"][0]["predicate"] = "RELATED_TO"
    cases.append(bad_predicate)

    bad_lifecycle = _valid_sidecar()
    bad_lifecycle["relations"][0]["lifecycle"] = "maybe"
    cases.append(bad_lifecycle)

    bad_epistemic = _valid_sidecar()
    bad_epistemic["relations"][0]["epistemic_class"] = "proven"
    cases.append(bad_epistemic)

    for payload in cases:
        with pytest.raises(ValidationError):
            ResearchMapSidecar.model_validate(payload)


def test_relation_identity_must_match_source_and_semantic_identity() -> None:
    payload = _valid_sidecar()
    payload["relations"][0]["relation_id"] = "rel_" + "0" * 64

    with pytest.raises(ValidationError, match="deterministic identity"):
        ResearchMapSidecar.model_validate(payload)


def test_sidecar_rejects_duplicate_relation_ids() -> None:
    payload = _valid_sidecar()
    payload["relations"].append(dict(payload["relations"][0]))

    with pytest.raises(ValidationError, match="duplicate relation IDs"):
        ResearchMapSidecar.model_validate(payload)


def test_reviewed_no_material_and_deferred_are_distinct_from_material() -> None:
    no_material = _valid_sidecar()
    no_material["review"]["materiality"] = "none"
    no_material["relations"] = []
    assert ResearchMapSidecar.model_validate(no_material).relations == []

    deferred = _valid_sidecar()
    deferred["review"] = {"state": "deferred", "controller": "Sol"}
    deferred["relations"] = []
    assert ResearchMapSidecar.model_validate(deferred).review.state.value == "deferred"

    bad_material = _valid_sidecar()
    bad_material["relations"] = []
    with pytest.raises(ValidationError, match="material sidecars require"):
        ResearchMapSidecar.model_validate(bad_material)

    bad_deferred = _valid_sidecar()
    bad_deferred["review"] = {
        "state": "deferred",
        "controller": "Sol",
        "materiality": "none",
    }
    bad_deferred["relations"] = []
    with pytest.raises(ValidationError, match="deferred sidecars must omit"):
        ResearchMapSidecar.model_validate(bad_deferred)


def test_sidecar_rejects_non_markdown_or_reserved_source_paths() -> None:
    for path in (
        "docs/research/result.json",
        ".soma/research-map/source.md",
        "docs/research/_soma_map/038.md",
    ):
        payload = _valid_sidecar()
        payload["source"]["path"] = path
        with pytest.raises(ValidationError):
            ResearchMapSidecar.model_validate(payload)


def test_project_manifest_is_portable_strict_and_rejects_overlapping_roots() -> None:
    manifest = ProjectManifest.model_validate(
        {
            "schema": "soma.project.v1",
            "repository_uid": "srepo_0123456789abcdef",
            "research_map": {
                "enabled": True,
                "schema": "soma.research-map.v2",
                "roots": [
                    {
                        "path": "docs/architecture_research",
                        "sidecar_dir": "_soma_map",
                        "include": ["*.md"],
                    },
                    {
                        "path": "docs/axon_independent_architecture",
                        "sidecar_dir": "_soma_map",
                        "include": ["*.md"],
                    },
                ],
            },
        }
    )
    assert manifest.repository_uid == "srepo_0123456789abcdef"
    assert len(manifest.research_map.roots) == 2
    dumped = manifest.model_dump(mode="json", by_alias=True)
    assert dumped["schema"] == "soma.project.v1"
    assert dumped["research_map"]["schema"] == "soma.research-map.v2"

    with pytest.raises(ValidationError, match="overlap"):
        ProjectManifest.model_validate(
            {
                "schema": "soma.project.v1",
                "repository_uid": "srepo_0123456789abcdef",
                "research_map": {
                    "enabled": True,
                    "schema": "soma.research-map.v2",
                    "roots": [
                        {"path": "docs/research", "sidecar_dir": "_soma_map", "include": ["*.md"]},
                        {"path": "docs/research/nested", "sidecar_dir": "_soma_map", "include": ["*.md"]},
                    ],
                },
            }
        )


def test_project_manifest_rejects_runtime_paths_unknown_fields_and_bad_uid() -> None:
    base = {
        "schema": "soma.project.v1",
        "repository_uid": "srepo_0123456789abcdef",
        "research_map": {
            "enabled": True,
            "schema": "soma.research-map.v2",
            "roots": [{"path": "docs/research", "sidecar_dir": "_soma_map", "include": ["*.md"]}],
        },
    }

    bad_path = {**base, "research_map": {**base["research_map"], "roots": [{"path": ".soma/research", "sidecar_dir": "_soma_map", "include": ["*.md"]}]}}
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(bad_path)

    bad_uid = {**base, "repository_uid": "proj_local_path_hash"}
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(bad_uid)

    unknown = {**base, "project_id": "proj_repo_local"}
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(unknown)


def test_relation_model_rejects_self_supersession_and_duplicate_facets() -> None:
    relation = _valid_relation()
    relation["supersedes"] = [relation["relation_id"]]
    with pytest.raises(ValidationError, match="cannot supersede itself"):
        ResearchMapRelation.model_validate(relation)

    relation = _valid_relation()
    relation["facets"] = {"dataset": ["PathMNIST", "PathMNIST"]}
    with pytest.raises(ValidationError, match="duplicates"):
        ResearchMapRelation.model_validate(relation)
