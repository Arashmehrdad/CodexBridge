"""Focused tests for the PILOT-MEMORY-1B shadow benchmark.

These assert the gate's invariants, not the benchmark's score. A failing
retrieval class is a legitimate measured outcome and must not fail the suite;
a broken authority boundary must.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.pilot_memory_1b import runner
from soma.pilot_memory_1b.contract import (
    CONFUSION_PROJECT_ID,
    LEXICAL_F1_THRESHOLDS,
    SOMA_PROJECT_ID,
    contract_hash,
)
from soma.pilot_memory_1b.corpus import CURATED_NOTES, DELETION_NOTE_ID
from soma.pilot_memory_1b.derived import build_association_model, derived_search
from soma.pilot_memory_1b.generator import generate_specs
from soma.pilot_memory_1b.index import UnscopedQueryError, build_index
from soma.pilot_memory_1b.questions import QUESTIONS
from soma.pilot_memory_1b.vault import corpus_hash, write_vault

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    write_vault(root, CURATED_NOTES)
    return root


# -- authority boundaries ---------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    """Modules a file actually imports.

    Parsed rather than grepped: the package docstrings legitimately name the
    production surfaces they promise not to touch, and a substring check would
    flag that prose as a violation.
    """
    import ast

    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_package_does_not_import_production_memory() -> None:
    """The shadow lane must not reach the real durable memory store."""
    package_dir = REPO_ROOT / "soma" / "pilot_memory_1b"
    for path in package_dir.glob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith("soma.memory"), (
                f"{path.name} imports production memory: {module}"
            )
            assert not module.startswith("soma.project_scope"), (
                f"{path.name} imports ProjectScope: {module}"
            )
            assert not module.startswith("soma.tasks"), (
                f"{path.name} imports the live task plane: {module}"
            )


def test_no_network_imports() -> None:
    package_dir = REPO_ROOT / "soma" / "pilot_memory_1b"
    forbidden = {"requests", "httpx", "socket", "urllib", "urllib.request", "http"}
    for path in package_dir.glob("*.py"):
        for module in _imported_modules(path):
            root = module.split(".")[0]
            assert root not in forbidden, f"{path.name} imports {module}"


def test_only_the_two_exact_project_ids_appear() -> None:
    allowed = {SOMA_PROJECT_ID, CONFUSION_PROJECT_ID}
    assert {n.project_id for n in CURATED_NOTES} == allowed


def test_curated_corpus_size_within_gate_band() -> None:
    assert 50 <= len(CURATED_NOTES) <= 100


def test_note_ids_are_unique() -> None:
    ids = [n.note_id for n in CURATED_NOTES]
    assert len(ids) == len(set(ids))


# -- fail-closed scoping ----------------------------------------------------


def test_unscoped_search_raises(vault: Path) -> None:
    index = build_index(vault)
    with pytest.raises(UnscopedQueryError):
        index.search("listener port", None)


def test_unscoped_claim_lookup_raises(vault: Path) -> None:
    index = build_index(vault)
    with pytest.raises(UnscopedQueryError):
        index.current_claims(None, "store_size")


def test_unscoped_derived_search_raises(vault: Path) -> None:
    index = build_index(vault)
    model = build_association_model(index)
    with pytest.raises(UnscopedQueryError):
        derived_search(index, model, "listener port", None)


def test_scoped_search_never_crosses_projects(vault: Path) -> None:
    index = build_index(vault)
    for query in ("listener port", "worker lease retry", "store size", "tunnel"):
        for project, prefix in (
            (SOMA_PROJECT_ID, "soma-"),
            (CONFUSION_PROJECT_ID, "lab-"),
        ):
            for hit in index.search(query, project, limit=10):
                assert hit.startswith(prefix), f"{query} leaked {hit} into {project}"


def test_unknown_project_returns_nothing_rather_than_everything(vault: Path) -> None:
    index = build_index(vault)
    assert index.search("listener port", "proj_does-not-exist") == []


# -- supersession semantics -------------------------------------------------


def test_multi_hop_full_supersession_keeps_only_the_newest(vault: Path) -> None:
    index = build_index(vault)
    current = {c.note_id for c in index.current_claims(SOMA_PROJECT_ID, "store_size")}
    assert current == {"soma-store-size-v3"}


def test_partial_supersession_retains_the_untouched_claim(vault: Path) -> None:
    index = build_index(vault)
    lease = {c.note_id for c in index.current_claims(SOMA_PROJECT_ID, "lease_seconds")}
    retry = {c.note_id for c in index.current_claims(SOMA_PROJECT_ID, "retry_limit")}
    # v2 replaced only the lease; v1 still owns the retry limit.
    assert lease == {"soma-worker-profile-v2"}
    assert retry == {"soma-worker-profile-v1"}


def test_superseded_claims_are_preserved_not_deleted(vault: Path) -> None:
    index = build_index(vault)
    refs = index.claim_refs(SOMA_PROJECT_ID, "store_size")
    assert {r.note_id for r in refs} == {
        "soma-store-size-v1",
        "soma-store-size-v2",
        "soma-store-size-v3",
    }
    assert [r.note_id for r in refs if not r.current] == [
        "soma-store-size-v1",
        "soma-store-size-v2",
    ]


# -- metadata drift and structure -------------------------------------------


def test_malformed_frontmatter_is_surfaced_not_skipped(vault: Path) -> None:
    index = build_index(vault)
    assert "soma-drift-malformed" in index.malformed
    # The note must still be present; surfacing a defect is not dropping it.
    assert "soma-drift-malformed" in index.notes


def test_dangling_links_are_reported(vault: Path) -> None:
    index = build_index(vault)
    assert ("soma-dangling-reference", "soma-absent-target") in index.dangling


def test_unresolved_and_missing_sources_are_distinguished(vault: Path) -> None:
    index = build_index(vault, repo_root=REPO_ROOT)
    assert index.source_status["soma-drift-empty-source"] == "missing"
    assert index.source_status["soma-drift-deleted-source"] == "unresolved"
    assert index.source_status["soma-runtime-port"] == "resolves"


def test_deleting_a_note_produces_a_new_dangling_reference(vault: Path) -> None:
    (vault / f"{DELETION_NOTE_ID}.md").unlink()
    index = build_index(vault)
    assert DELETION_NOTE_ID not in index.notes
    assert ("soma-deletion-referrer", DELETION_NOTE_ID) in index.dangling


# -- rebuild and canonical authority ----------------------------------------


def test_rebuild_is_deterministic(vault: Path) -> None:
    assert build_index(vault).fingerprint() == build_index(vault).fingerprint()


def test_discarding_the_index_loses_nothing(vault: Path) -> None:
    before = build_index(vault)
    canonical = corpus_hash(vault)
    fingerprint = before.fingerprint()
    del before  # the only derived structure is now gone
    after = build_index(vault)
    assert after.fingerprint() == fingerprint
    assert corpus_hash(vault) == canonical


def test_index_holds_no_information_absent_from_files(vault: Path) -> None:
    """Every indexed note id must correspond to a canonical file."""
    index = build_index(vault)
    on_disk = {p.stem for p in vault.glob("*.md")}
    assert set(index.notes) <= on_disk


# -- benchmark integrity ----------------------------------------------------


def test_contract_is_frozen_and_matches_code() -> None:
    ok, drift = runner.verify_freeze()
    assert ok, f"frozen contract drifted: {drift}"


def test_frozen_file_records_the_current_hashes() -> None:
    stored = json.loads(runner.FREEZE_PATH.read_text(encoding="utf-8"))
    assert stored["contract_hash"] == contract_hash()
    assert stored["corpus_spec_hash"] == runner.corpus_spec_hash()
    assert stored["questions_hash"] == runner.questions_hash()


def test_no_oracle_leakage_in_corpus(vault: Path) -> None:
    assert runner.check_oracle_leakage(vault) == []


def test_every_declared_class_has_at_least_one_question() -> None:
    covered = {q.cls for q in QUESTIONS}
    for cls in LEXICAL_F1_THRESHOLDS:
        assert cls in covered, f"no question exercises {cls}"


def test_expected_note_ids_all_exist(vault: Path) -> None:
    index = build_index(vault)
    known = set(index.notes)
    for question in QUESTIONS:
        missing = question.expected - known
        assert not missing, f"{question.qid} expects unknown notes: {sorted(missing)}"


# -- generator --------------------------------------------------------------


def test_generator_is_deterministic() -> None:
    a = generate_specs(50)
    b = generate_specs(50)
    assert [n.note_id for n in a] == [n.note_id for n in b]
    assert [n.body for n in a] == [n.body for n in b]


def test_generator_uses_only_the_two_project_ids() -> None:
    assert {n.project_id for n in generate_specs(50)} == {
        SOMA_PROJECT_ID,
        CONFUSION_PROJECT_ID,
    }


# -- end to end -------------------------------------------------------------


def test_visible_suite_runs_and_cleans_up(tmp_path: Path) -> None:
    """The suite completes, reports honestly, and leaves nothing behind."""
    report = runner.execute(with_scale=False)
    assert report["ok"] is True
    assert report["oracle_leakage"]["clean"] is True
    assert report["cleanup"]["workdir_removed"] is True
    assert report["deterministic_rebuild"]["passed"] is True
    assert report["external_edit_attribution"]["passed"] is True
    # A named measured gap is a valid outcome; an unscoped leak never is.
    assert report["verdict"] in {
        "baseline_candidate_passes",
        "baseline_has_named_measured_gaps",
    }
    for question in report["lexical"]["per_question"]:
        assert "UNSCOPED_LEAK" not in question["retrieved"]
