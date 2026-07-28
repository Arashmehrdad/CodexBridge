"""MEMORY-INTEGRATION-FOUNDATION-1 steps 3-4 and 6.

Covers the scope discriminator, compare-and-swap correction, the lifecycle
vocabulary, honest three-dimensional retrieval state, packet persistence, the
configurable vault root, and the legacy-writer freeze.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soma.config import CanonicalMemoryConfig
from soma.knowledge import (
    CanonicalMemoryService,
    KnowledgeInput,
    KnowledgeService,
    MemoryConflict,
    MemoryScope,
    MemoryWriteRefused,
    PacketStore,
    ScopeRefused,
    resolve_personal_scope,
    resolve_scope,
)
from soma.memory.repository import (
    LegacyCanonicalWriteFrozen,
    ProjectMemoryRepository,
)

PROJECT_ID = "proj_a144f759-1619-4276-9292-28704b6611f4"
OTHER_PROJECT_ID = "proj_0cf013d0-191b-57f4-a84b-7a43819a1578"


@pytest.fixture()
def service(tmp_path: Path) -> CanonicalMemoryService:
    knowledge = KnowledgeService(
        vault_root=tmp_path / "vault", db_path=tmp_path / "knowledge.sqlite3"
    )
    return CanonicalMemoryService(
        knowledge,
        MemoryScope(kind="project", project_id=PROJECT_ID, repo_name="soma"),
        packet_store=PacketStore(tmp_path / "packets"),
    )


def note(**overrides) -> KnowledgeInput:
    payload = {
        "project_id": PROJECT_ID,
        "vault_path": "decisions/endpoint.md",
        "kind": "decision",
        "title": "Listener port",
        "summary": "The listener accepts connections on port 8801.",
        "body": "The listener accepts connections on port 8801. ALPHACANARY",
    }
    payload.update(overrides)
    return KnowledgeInput(**payload)


# ----------------------------------------------------------------------
# scope


def test_personal_scope_is_refused_in_this_lane():
    with pytest.raises(ScopeRefused, match="not activated"):
        resolve_personal_scope("owner_arash")


def test_unknown_scope_kind_is_refused():
    with pytest.raises(ScopeRefused, match="not recognised"):
        resolve_scope(object(), {"kind": "global"})


def test_project_scope_requires_both_identifiers():
    with pytest.raises(ScopeRefused, match="project_id is required"):
        resolve_scope(object(), {"kind": "project", "repo_name": "soma"})
    with pytest.raises(ScopeRefused, match="repo_name is required"):
        resolve_scope(object(), {"kind": "project", "project_id": PROJECT_ID})


def test_writing_outside_the_bound_scope_is_refused(service):
    with pytest.raises(MemoryWriteRefused, match="bound scope"):
        service.save(note(project_id=OTHER_PROJECT_ID))


# ----------------------------------------------------------------------
# lifecycle


def test_save_stamps_temporal_validity(service):
    record = service.save(note(idempotency_key="k1"))
    assert record.valid_from
    assert record.valid_until == ""
    assert record.status == "current"
    assert record.format_version == 2


def test_correction_is_compare_and_swap(service):
    record = service.save(note(idempotency_key="k1"))
    updated = service.correct(
        record.knowledge_id,
        expected_sha256=record.content_sha256,
        changes={"review_state": "reviewed"},
    )
    assert updated.review_state == "reviewed"
    assert updated.revision == record.revision + 1

    # A concurrent owner edit must refuse, not overwrite.
    with pytest.raises(MemoryConflict, match="re-read before correcting"):
        service.correct(
            record.knowledge_id,
            expected_sha256=record.content_sha256,
            changes={"review_state": "rejected"},
        )


def test_correction_may_not_change_meaning(service):
    record = service.save(note(idempotency_key="k1"))
    with pytest.raises(MemoryWriteRefused, match="replacement record"):
        service.correct(
            record.knowledge_id,
            expected_sha256=record.content_sha256,
            changes={"body": "something entirely different"},
        )


def test_superseded_may_not_be_set_directly(service):
    record = service.save(note(idempotency_key="k1"))
    with pytest.raises(MemoryWriteRefused, match="unsupported lifecycle"):
        service.set_status(
            record.knowledge_id, "superseded", expected_sha256=record.content_sha256
        )


def test_archive_closes_the_validity_window_and_leaves_context(service):
    record = service.save(note(idempotency_key="k1"))
    archived = service.set_status(
        record.knowledge_id, "archived", expected_sha256=record.content_sha256
    )
    assert archived.status == "archived"
    assert archived.valid_until

    outcome = service.search("ALPHACANARY")
    assert outcome.records == ()


# ----------------------------------------------------------------------
# retrieval honesty


def test_retrieval_names_its_mode_and_both_health_dimensions(service):
    service.save(note(idempotency_key="k1"))
    outcome = service.search("ALPHACANARY", provider_health="degraded")
    assert outcome.retrieval_mode == "catalog_lexical"
    assert outcome.canonical_health == "healthy"
    assert outcome.provider_health == "degraded"
    assert [record.title for record in outcome.records] == ["Listener port"]


def test_unadopted_owner_notes_are_warned_about_not_hidden(service, tmp_path):
    service.save(note(idempotency_key="k1"))
    (tmp_path / "vault" / "journal.md").write_text(
        "Bought milk. Rang the plumber.\n", encoding="utf-8"
    )
    service.knowledge.rebuild(PROJECT_ID)
    outcome = service.search("ALPHACANARY")
    assert any("not adopted" in warning for warning in outcome.warnings)


# ----------------------------------------------------------------------
# packets


def test_packet_is_persisted_before_projection_and_retrievable(service, tmp_path):
    service.save(note(idempotency_key="k1"))
    packet = service.build_packet("ALPHACANARY", pinned=[{"fact": "owner is Arash"}])
    assert packet.packet_id.startswith("pkt_")
    assert packet.packet_sha256
    assert packet.pinned_context == [{"fact": "owner is Arash"}]
    assert packet.records[0]["content_sha256"]
    assert packet.records[0]["vault_path"] == "decisions/endpoint.md"

    store = PacketStore(tmp_path / "packets")
    restored = store.get(packet.packet_id)
    assert restored["packet_id"] == packet.packet_id
    assert restored["records"][0]["knowledge_id"] == packet.records[0]["knowledge_id"]


def test_packet_retrieval_refuses_a_traversing_identifier(tmp_path):
    store = PacketStore(tmp_path / "packets")
    with pytest.raises(ValueError, match="opaque identifier"):
        store.get("../../etc/passwd")


# ----------------------------------------------------------------------
# vault root configuration


def test_default_vault_root_preserves_the_legacy_location(tmp_path):
    config = CanonicalMemoryConfig()
    assert config.resolve_vault_root(tmp_path, PROJECT_ID) == (
        tmp_path / "knowledge" / "projects" / PROJECT_ID / "vault"
    )


def test_external_vault_root_is_used_when_configured(tmp_path):
    external = tmp_path / "Soma Memory"
    config = CanonicalMemoryConfig(
        canonical_vault_root=str(external),
        canonical_vault_kind="external_private_vault",
    )
    assert config.resolve_vault_root(tmp_path / "runs", PROJECT_ID) == (
        external / "projects" / PROJECT_ID
    )


def test_relative_vault_root_is_refused(tmp_path):
    config = CanonicalMemoryConfig(canonical_vault_root="relative/vault")
    with pytest.raises(ValueError, match="absolute path"):
        config.resolve_vault_root(tmp_path, PROJECT_ID)


# ----------------------------------------------------------------------
# legacy retirement


@pytest.mark.parametrize(
    "method, args",
    [
        ("remember_project_fact", ("a fact",)),
        ("remember_decision", ("a decision",)),
        ("remember_validation_recipe", ("pytest -q",)),
    ],
)
def test_legacy_canonical_writers_are_frozen(tmp_path, method, args):
    repository = ProjectMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    with pytest.raises(LegacyCanonicalWriteFrozen, match="no longer a"):
        getattr(repository, method)(*args)


def test_legacy_store_remains_readable_for_migration(tmp_path):
    seeded = ProjectMemoryRepository(
        db_path=tmp_path / "memory.sqlite3", allow_canonical_writes=True
    )
    seeded.remember_decision("Historical decision", repo_name="soma")

    frozen = ProjectMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    assert frozen.search("Historical").total == 1


def test_operational_recollection_is_not_frozen(tmp_path):
    """Run and artifact recollection is what the legacy store legitimately owns."""
    from soma.memory.models import MemoryRecord, MemoryType

    repository = ProjectMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    record = repository.store.create(
        MemoryRecord(memory_type=MemoryType.RUN, title="run 1", content="exit 0")
    )
    assert record.memory_id


# ----------------------------------------------------------------------
# MEMORY-REAL-PROJECT-TRIAL-1 -- lexical retrieval defects found live


def test_multi_word_question_matches_terms_in_any_order(service):
    """Regression: lexical search was a single LIKE over the whole phrase.

    A controller asking "semantic retrieval disabled" got zero results while
    "semantic" alone matched, and the empty answer reported nothing omitted.
    With semantic retrieval disabled this is the production retrieval path.
    """
    service.save(
        note(
            vault_path="architecture/semantic.md",
            title="Semantic retrieval is disabled",
            body=(
                "Membership cannot be proven, so retrieval falls back to the "
                "canonical catalog."
            ),
            idempotency_key="k-semantic",
        )
    )

    for query in (
        "semantic",
        "semantic retrieval",
        "semantic retrieval disabled",
        "disabled semantic",
        "  retrieval   disabled  ",
    ):
        outcome = service.search(query)
        assert [r.title for r in outcome.records] == [
            "Semantic retrieval is disabled"
        ], query


def test_a_term_that_is_absent_still_excludes_the_record(service):
    """Term-AND, not term-OR: every term must appear."""
    service.save(
        note(
            vault_path="architecture/semantic.md",
            title="Semantic retrieval is disabled",
            body="Membership cannot be proven.",
            idempotency_key="k-semantic",
        )
    )
    assert service.search("semantic elephant").records == ()


def test_whitespace_only_query_is_refused_not_treated_as_match_everything(service):
    service.save(note(idempotency_key="k1"))
    with pytest.raises(ValueError, match="must not be empty"):
        service.search("   ")


def test_zero_results_from_a_question_says_why_not_just_zero(service):
    """Absence of a match must not read as absence of the memory."""
    service.save(note(idempotency_key="k1"))
    outcome = service.search("why is the listener configured that way")
    assert outcome.records == ()
    assert any("every query term" in warning for warning in outcome.warnings)


def test_single_term_miss_does_not_add_the_phrasing_warning(service):
    """One term that genuinely is not there is a real absence, not a phrasing hint."""
    service.save(note(idempotency_key="k1"))
    outcome = service.search("elephant")
    assert outcome.records == ()
    assert not any("every query term" in warning for warning in outcome.warnings)
