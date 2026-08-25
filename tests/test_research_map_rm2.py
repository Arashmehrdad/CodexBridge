from __future__ import annotations

import json
from pathlib import Path

from soma.research_map import (
    CoverageState,
    ManifestState,
    RelationLifecycle,
    ResearchMapHealthState,
    canonical_text_sha256,
    load_project_manifest,
    relation_id,
    scan_research_map,
)


def _write_manifest(
    repo: Path,
    *,
    roots: list[dict] | None = None,
    repository_uid: str = "srepo_0123456789abcdef",
    enabled: bool = True,
) -> None:
    payload = {
        "schema": "soma.project.v1",
        "repository_uid": repository_uid,
        "research_map": {
            "enabled": enabled,
            "schema": "soma.research-map.v2",
            "roots": roots
            or [
                {
                    "path": "docs/research",
                    "sidecar_dir": "_soma_map",
                    "include": ["*.md"],
                }
            ],
        },
    }
    (repo / "soma.project.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _relation(
    source_path: str,
    *,
    subject_key: str,
    object_key: str,
    anchor: str,
    statement: str,
    predicate: str = "SUPPORTS",
    supersedes: list[str] | None = None,
) -> dict:
    return {
        "relation_id": relation_id(source_path, subject_key, predicate, object_key),
        "subject": {"key": subject_key, "label": subject_key},
        "predicate": predicate,
        "object": {"key": object_key, "label": object_key},
        "statement": statement,
        "locator": {"anchor": anchor},
        "epistemic_class": "observed",
        "lifecycle": "current",
        "supersedes": supersedes or [],
        "facets": {},
        "qualifiers": {},
    }


def _sidecar_payload(
    source_path: str,
    source_text: str,
    *,
    materiality: str | None = "none",
    deferred: bool = False,
    relations: list[dict] | None = None,
) -> dict:
    review = (
        {"state": "deferred", "controller": "Sol"}
        if deferred
        else {
            "state": "reviewed",
            "controller": "Sol",
            "materiality": materiality,
        }
    )
    return {
        "schema_version": "soma.research-map.v2",
        "source": {
            "path": source_path,
            "canonical_text_sha256": canonical_text_sha256(source_text),
        },
        "review": review,
        "facets": {},
        "relations": relations or [],
    }


def _write_source(repo: Path, source_path: str, text: str, *, crlf: bool = False) -> None:
    path = repo / Path(source_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(rendered.encode("utf-8"))


def _sidecar_path(repo: Path, source_path: str) -> Path:
    source = Path(source_path)
    path = repo / source.parent / "_soma_map" / f"{source.stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_sidecar(
    repo: Path,
    source_path: str,
    payload: dict,
    *,
    crlf: bool = False,
    compact: bool = False,
) -> Path:
    path = _sidecar_path(repo, source_path)
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=compact,
        separators=(",", ":") if compact else None,
        indent=None if compact else 2,
    )
    if crlf:
        rendered = rendered.replace("\n", "\r\n")
    path.write_bytes(rendered.encode("utf-8"))
    return path


def _coverage_by_path(scan) -> dict[str, CoverageState]:
    return {entry.source_path: entry.state for entry in scan.coverage.entries}


def test_rm2_manifest_loader_is_read_only_and_bounded_to_feature_health(tmp_path: Path) -> None:
    missing = load_project_manifest(tmp_path)
    assert missing.state is ManifestState.MISSING
    assert not (tmp_path / "soma.project.json").exists()

    _write_manifest(tmp_path)
    before = (tmp_path / "soma.project.json").read_bytes()
    valid = load_project_manifest(tmp_path)
    assert valid.state is ManifestState.VALID
    assert valid.manifest is not None
    assert (tmp_path / "soma.project.json").read_bytes() == before

    (tmp_path / "soma.project.json").write_text("{broken", encoding="utf-8")
    degraded = scan_research_map(tmp_path)
    assert degraded.manifest_state is ManifestState.MALFORMED
    assert degraded.health_state is ResearchMapHealthState.DEGRADED
    assert degraded.semantic_desired_state_sha256 is None


def test_rm2_coverage_states_are_explicit_and_deferred_is_incomplete(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    root = "docs/research"

    material_path = f"{root}/001_material.md"
    material_text = "# Material\nmaterial anchor\n"
    _write_source(tmp_path, material_path, material_text)
    material_relation = _relation(
        material_path,
        subject_key="finding:material",
        object_key="claim:material",
        anchor="material anchor",
        statement="Material finding is retained.",
    )
    _write_sidecar(
        tmp_path,
        material_path,
        _sidecar_payload(
            material_path,
            material_text,
            materiality="material",
            relations=[material_relation],
        ),
    )

    none_path = f"{root}/002_none.md"
    none_text = "# None\n"
    _write_source(tmp_path, none_path, none_text)
    _write_sidecar(tmp_path, none_path, _sidecar_payload(none_path, none_text))

    deferred_path = f"{root}/003_deferred.md"
    deferred_text = "# Deferred\n"
    _write_source(tmp_path, deferred_path, deferred_text)
    _write_sidecar(
        tmp_path,
        deferred_path,
        _sidecar_payload(deferred_path, deferred_text, deferred=True),
    )

    unreviewed_path = f"{root}/004_unreviewed.md"
    _write_source(tmp_path, unreviewed_path, "# Unreviewed\n")

    stale_path = f"{root}/005_stale.md"
    stale_original = "# Stale\nold content\n"
    _write_source(tmp_path, stale_path, stale_original)
    _write_sidecar(tmp_path, stale_path, _sidecar_payload(stale_path, stale_original))
    _write_source(tmp_path, stale_path, "# Stale\nnew content\n")

    missing_path = f"{root}/006_missing.md"
    _write_sidecar(
        tmp_path,
        missing_path,
        _sidecar_payload(missing_path, "# Missing\n"),
    )

    scan = scan_research_map(tmp_path)
    states = _coverage_by_path(scan)
    assert states == {
        material_path: CoverageState.REVIEWED_MATERIAL,
        none_path: CoverageState.REVIEWED_NO_MATERIAL,
        deferred_path: CoverageState.DEFERRED,
        unreviewed_path: CoverageState.UNREVIEWED,
        stale_path: CoverageState.STALE,
        missing_path: CoverageState.MISSING_SOURCE,
    }
    assert scan.coverage.reviewed_complete_count == 2
    assert scan.coverage.incomplete_count == 4
    assert scan.coverage.complete is False
    assert scan.health_state is ResearchMapHealthState.DEGRADED


def test_rm2_same_semantic_clone_is_portable_across_source_and_json_line_endings(
    tmp_path: Path,
) -> None:
    repo_lf = tmp_path / "lf"
    repo_crlf = tmp_path / "crlf"
    repo_lf.mkdir()
    repo_crlf.mkdir()
    for repo in (repo_lf, repo_crlf):
        _write_manifest(repo)

    source_path = "docs/research/010_portable.md"
    text = "# Portable\nportable anchor λ\n"
    relation = _relation(
        source_path,
        subject_key="finding:portable",
        object_key="claim:portable",
        anchor="portable anchor λ",
        statement="Portable semantic state survives checkout line endings.",
    )
    payload = _sidecar_payload(
        source_path,
        text,
        materiality="material",
        relations=[relation],
    )

    _write_source(repo_lf, source_path, text)
    _write_sidecar(repo_lf, source_path, payload)
    _write_source(repo_crlf, source_path, text, crlf=True)
    _write_sidecar(repo_crlf, source_path, payload, crlf=True, compact=True)

    lf = scan_research_map(repo_lf)
    crlf = scan_research_map(repo_crlf)
    assert lf.health_state is ResearchMapHealthState.HEALTHY
    assert crlf.health_state is ResearchMapHealthState.HEALTHY
    assert lf.semantic_desired_state_sha256 == crlf.semantic_desired_state_sha256


def test_rm2_statement_refinement_changes_desired_state_without_relation_id_change(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path)
    source_path = "docs/research/011_refine.md"
    text = "# Refine\nrefine anchor\n"
    _write_source(tmp_path, source_path, text)
    relation = _relation(
        source_path,
        subject_key="finding:refine",
        object_key="claim:refine",
        anchor="refine anchor",
        statement="Initial reviewed wording.",
    )
    first_id = relation["relation_id"]
    payload = _sidecar_payload(
        source_path,
        text,
        materiality="material",
        relations=[relation],
    )
    _write_sidecar(tmp_path, source_path, payload)
    first = scan_research_map(tmp_path)

    payload["relations"][0]["statement"] = "Refined reviewed wording with the same identity."
    _write_sidecar(tmp_path, source_path, payload)
    second = scan_research_map(tmp_path)

    assert payload["relations"][0]["relation_id"] == first_id
    assert first.semantic_desired_state_sha256 != second.semantic_desired_state_sha256


def test_rm2_duplicate_numeric_research_ids_do_not_collide(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    paths = ["docs/research/001_alpha.md", "docs/research/001_beta.md"]
    for source_path in reversed(paths):
        text = f"# {Path(source_path).stem}\n"
        _write_source(tmp_path, source_path, text)
        _write_sidecar(tmp_path, source_path, _sidecar_payload(source_path, text))

    scan = scan_research_map(tmp_path)
    assert [entry.source_path for entry in scan.coverage.entries] == paths
    logical_ids = [entry.logical_record_id for entry in scan.coverage.entries]
    assert len(set(logical_ids)) == 2
    assert scan.health_state is ResearchMapHealthState.HEALTHY


def test_rm2_locator_failure_is_stale_and_malformed_sidecar_is_health_only(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path)

    anchor_path = "docs/research/020_anchor.md"
    anchor_text = "# Anchor\nreal source text\n"
    _write_source(tmp_path, anchor_path, anchor_text)
    bad_anchor_relation = _relation(
        anchor_path,
        subject_key="finding:anchor",
        object_key="claim:anchor",
        anchor="text that is not present",
        statement="This relation has an invalid exact locator.",
    )
    _write_sidecar(
        tmp_path,
        anchor_path,
        _sidecar_payload(
            anchor_path,
            anchor_text,
            materiality="material",
            relations=[bad_anchor_relation],
        ),
    )

    malformed_path = "docs/research/021_malformed.md"
    _write_source(tmp_path, malformed_path, "# Malformed\n")
    malformed_sidecar = _sidecar_path(tmp_path, malformed_path)
    malformed_sidecar.write_text("{not valid json", encoding="utf-8")

    scan = scan_research_map(tmp_path)
    states = _coverage_by_path(scan)
    assert states[anchor_path] is CoverageState.STALE
    assert states[malformed_path] is CoverageState.UNREVIEWED
    assert scan.health_state is ResearchMapHealthState.DEGRADED
    assert scan.semantic_desired_state_sha256 is not None
    issue_codes = {issue.code for issue in scan.issues}
    assert "locator_anchor_missing" in issue_codes
    assert "sidecar_invalid_json" in issue_codes


def test_rm2_successor_owned_supersession_does_not_require_old_sidecar_rewrite(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path)
    old_path = "docs/research/030_old.md"
    new_path = "docs/research/031_new.md"
    old_text = "# Old\nold anchor\n"
    new_text = "# New\nnew anchor\n"
    _write_source(tmp_path, old_path, old_text)
    _write_source(tmp_path, new_path, new_text)

    old_relation = _relation(
        old_path,
        subject_key="finding:old",
        object_key="claim:shared",
        anchor="old anchor",
        statement="Older current statement.",
    )
    new_relation = _relation(
        new_path,
        subject_key="finding:new",
        object_key="claim:shared",
        anchor="new anchor",
        statement="New reviewed statement supersedes the older relation.",
        supersedes=[old_relation["relation_id"]],
    )
    _write_sidecar(
        tmp_path,
        old_path,
        _sidecar_payload(old_path, old_text, materiality="material", relations=[old_relation]),
    )
    _write_sidecar(
        tmp_path,
        new_path,
        _sidecar_payload(new_path, new_text, materiality="material", relations=[new_relation]),
    )

    scan = scan_research_map(tmp_path)
    assert scan.governance is not None
    states = {relation.relation_id: relation for relation in scan.governance.relations}
    old = states[old_relation["relation_id"]]
    new = states[new_relation["relation_id"]]
    assert old.declared_lifecycle is RelationLifecycle.CURRENT
    assert old.effective_lifecycle is RelationLifecycle.SUPERSEDED
    assert old.superseded_by == (new_relation["relation_id"],)
    assert new.effective_lifecycle is RelationLifecycle.CURRENT
    assert scan.health_state is ResearchMapHealthState.HEALTHY


def test_rm2_governance_detects_dangling_supersession_and_cycles(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    path_a = "docs/research/040_a.md"
    path_b = "docs/research/041_b.md"
    text_a = "# A\na anchor\n"
    text_b = "# B\nb anchor\n"
    _write_source(tmp_path, path_a, text_a)
    _write_source(tmp_path, path_b, text_b)

    id_a = relation_id(path_a, "finding:a", "SUPPORTS", "claim:a")
    id_b = relation_id(path_b, "finding:b", "SUPPORTS", "claim:b")
    relation_a = _relation(
        path_a,
        subject_key="finding:a",
        object_key="claim:a",
        anchor="a anchor",
        statement="A participates in an adversarial cycle.",
        supersedes=[id_b],
    )
    relation_b = _relation(
        path_b,
        subject_key="finding:b",
        object_key="claim:b",
        anchor="b anchor",
        statement="B participates in an adversarial cycle and has one dangling target.",
        supersedes=[id_a, "rel_" + "f" * 64],
    )
    _write_sidecar(
        tmp_path,
        path_a,
        _sidecar_payload(path_a, text_a, materiality="material", relations=[relation_a]),
    )
    _write_sidecar(
        tmp_path,
        path_b,
        _sidecar_payload(path_b, text_b, materiality="material", relations=[relation_b]),
    )

    scan = scan_research_map(tmp_path)
    assert scan.governance is not None
    issue_codes = [issue.code for issue in scan.governance.issues]
    assert "dangling_supersedes" in issue_codes
    assert issue_codes.count("supersession_cycle") == 2
    assert scan.health_state is ResearchMapHealthState.DEGRADED


def test_rm2_duplicate_relation_ids_are_detected_across_sidecar_files(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    source_path = "docs/research/050_duplicate.md"
    text = "# Duplicate\nduplicate anchor\n"
    _write_source(tmp_path, source_path, text)
    relation = _relation(
        source_path,
        subject_key="finding:duplicate",
        object_key="claim:duplicate",
        anchor="duplicate anchor",
        statement="Duplicate relation identity must be detected mechanically.",
    )
    payload = _sidecar_payload(
        source_path,
        text,
        materiality="material",
        relations=[relation],
    )
    expected = _write_sidecar(tmp_path, source_path, payload)
    duplicate = expected.with_name("copy.json")
    duplicate.write_text(json.dumps(payload), encoding="utf-8")

    scan = scan_research_map(tmp_path)
    issue_codes = {issue.code for issue in scan.issues}
    assert "unexpected_sidecar_path" in issue_codes
    assert "duplicate_relation_id" in issue_codes
    assert scan.health_state is ResearchMapHealthState.DEGRADED


def test_rm2_manifest_root_order_and_include_order_do_not_change_semantic_identity(
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    roots_a = [
        {"path": "docs/a", "sidecar_dir": "_soma_map", "include": ["*.md", "note-*.md"]},
        {"path": "docs/b", "sidecar_dir": "_soma_map", "include": ["*.md"]},
    ]
    roots_b = [
        {"path": "docs/b", "sidecar_dir": "_soma_map", "include": ["*.md"]},
        {"path": "docs/a", "sidecar_dir": "_soma_map", "include": ["note-*.md", "*.md"]},
    ]
    _write_manifest(repo_a, roots=roots_a)
    _write_manifest(repo_b, roots=roots_b)

    for repo in (repo_a, repo_b):
        for source_path in ("docs/a/001.md", "docs/b/002.md"):
            text = f"# {Path(source_path).stem}\n"
            _write_source(repo, source_path, text)
            _write_sidecar(repo, source_path, _sidecar_payload(source_path, text))

    first = scan_research_map(repo_a)
    second = scan_research_map(repo_b)
    assert first.health_state is ResearchMapHealthState.HEALTHY
    assert second.health_state is ResearchMapHealthState.HEALTHY
    assert first.semantic_desired_state_sha256 == second.semantic_desired_state_sha256


def test_rm2_sidecar_source_path_mismatch_is_not_treated_as_reviewed(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    source_path = "docs/research/060_source.md"
    source_text = "# Source\n"
    _write_source(tmp_path, source_path, source_text)
    payload = _sidecar_payload(source_path, source_text)
    payload["source"]["path"] = "docs/research/061_other.md"
    _write_sidecar(tmp_path, source_path, payload)

    scan = scan_research_map(tmp_path)
    assert _coverage_by_path(scan)[source_path] is CoverageState.UNREVIEWED
    assert "sidecar_source_path_mismatch" in {issue.code for issue in scan.issues}
    assert scan.health_state is ResearchMapHealthState.DEGRADED


def test_rm2_disabled_manifest_does_not_scan_or_create_runtime_state(tmp_path: Path) -> None:
    _write_manifest(tmp_path, enabled=False)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    scan = scan_research_map(tmp_path)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    assert scan.health_state is ResearchMapHealthState.DISABLED
    assert scan.semantic_desired_state_sha256 is None
    assert scan.coverage.total_count == 0
    assert before == after
