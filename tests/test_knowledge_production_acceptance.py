from __future__ import annotations

from pathlib import Path

import pytest

from soma.knowledge import (
    KnowledgeInput,
    KnowledgeService,
    SourceLocator,
    SourceReference,
)


SOMA_PROJECT_ID = "proj_a144f759-1619-4276-9292-28704b6611f4"
SIBLING_PROJECT_ID = "proj_0cf013d0-191b-57f4-a84b-7a43819a1578"


@pytest.fixture
def knowledge(tmp_path: Path) -> KnowledgeService:
    return KnowledgeService(
        vault_root=tmp_path / "vault",
        db_path=tmp_path / "knowledge.sqlite3",
    )


def _research_note(
    *,
    project_id: str = SOMA_PROJECT_ID,
    vault_path: str = "research/cf1-retrieval.md",
    title: str = "CF1 retrieval finding",
    body: str = "Compact projections keep ordinary chat responses bounded.",
    idempotency_key: str = "",
    sources: list[SourceReference] | None = None,
    locators: list[SourceLocator] | None = None,
) -> KnowledgeInput:
    return KnowledgeInput(
        project_id=project_id,
        vault_path=vault_path,
        kind="research_note",
        title=title,
        summary=body,
        body=body,
        tags=["research", "cf1"],
        idempotency_key=idempotency_key,
        sources=sources or [],
        locators=locators or [],
    )


def test_save_and_retrieve_research_note(knowledge: KnowledgeService) -> None:
    saved = knowledge.save(_research_note())

    retrieved = knowledge.get(SOMA_PROJECT_ID, saved.knowledge_id)

    assert retrieved.knowledge_id == saved.knowledge_id
    assert retrieved.project_id == SOMA_PROJECT_ID
    assert retrieved.kind == "research_note"
    assert retrieved.title == "CF1 retrieval finding"
    assert "bounded" in retrieved.body
    assert retrieved.content_sha256
    assert retrieved.revision == 1


def test_save_is_idempotent_within_a_project(knowledge: KnowledgeService) -> None:
    note = _research_note(idempotency_key="chatgpt-research-cycle-42")

    first = knowledge.save(note)
    repeated = knowledge.save(note)

    assert repeated.knowledge_id == first.knowledge_id
    assert repeated.revision == first.revision
    assert knowledge.search(SOMA_PROJECT_ID, "Compact projections").total == 1


def test_exact_project_scope_prevents_sibling_disclosure(
    knowledge: KnowledgeService,
) -> None:
    soma = knowledge.save(
        _research_note(body="The shared worker lease is sixty seconds.")
    )
    knowledge.save(
        _research_note(
            project_id=SIBLING_PROJECT_ID,
            vault_path="research/sibling-lease.md",
            title="Sibling lease finding",
            body="The shared worker lease is ninety seconds.",
        )
    )

    soma_hits = knowledge.search(SOMA_PROJECT_ID, "shared worker lease").records

    assert [record.knowledge_id for record in soma_hits] == [soma.knowledge_id]
    assert all(record.project_id == SOMA_PROJECT_ID for record in soma_hits)
    with pytest.raises((KeyError, PermissionError)):
        knowledge.get(SIBLING_PROJECT_ID, soma.knowledge_id)


def test_supersession_preserves_history_and_defaults_to_current(
    knowledge: KnowledgeService,
) -> None:
    old = knowledge.save(
        _research_note(
            title="Knowledge provider decision",
            body="MCP Connector is the selected provider.",
        )
    )
    current = knowledge.supersede(
        _research_note(
            vault_path="research/provider-decision-v2.md",
            title="Knowledge provider decision",
            body="MCP Connector 0.28.1 is rejected after incomplete rebuild evidence.",
        ),
        supersedes_ids=[old.knowledge_id],
    )

    current_hits = knowledge.search(
        SOMA_PROJECT_ID, "Knowledge provider decision"
    ).records
    historical_hits = knowledge.search(
        SOMA_PROJECT_ID,
        "Knowledge provider decision",
        current_only=False,
    ).records

    assert [record.knowledge_id for record in current_hits] == [current.knowledge_id]
    assert {record.knowledge_id for record in historical_hits} == {
        old.knowledge_id,
        current.knowledge_id,
    }
    assert knowledge.get(SOMA_PROJECT_ID, old.knowledge_id).status == "superseded"


def test_persian_unicode_literal_search(knowledge: KnowledgeService) -> None:
    saved = knowledge.save(
        _research_note(
            vault_path="research/persian-restart.md",
            title="بازیابی پس از راه‌اندازی مجدد",
            body="سوما باید دانش پروژه را پس از راه‌اندازی مجدد بازیابی کند.",
        )
    )

    page = knowledge.search(SOMA_PROJECT_ID, "دانش پروژه")

    assert [record.knowledge_id for record in page.records] == [saved.knowledge_id]


def test_provenance_and_exact_locator_round_trip(
    knowledge: KnowledgeService,
) -> None:
    source = SourceReference(
        source_id="src_seedmind_architecture",
        uri="attachment://seedmind-architecture-starter",
        title="SeedMind Research Knowledge Archive",
        version="2026-07-28",
        content_hash="sha256:" + ("a" * 64),
    )
    locator = SourceLocator(
        source_id=source.source_id,
        locator="Core architecture > Rebuildable retrieval layer",
        relationship="supports",
    )

    saved = knowledge.save(_research_note(sources=[source], locators=[locator]))
    retrieved = knowledge.get(SOMA_PROJECT_ID, saved.knowledge_id)

    assert retrieved.sources == [source]
    assert retrieved.locators == [locator]
    assert retrieved.locators[0].source_id == retrieved.sources[0].source_id


def test_rebuild_reports_complete_healthy_project(
    knowledge: KnowledgeService,
) -> None:
    first = knowledge.save(_research_note())
    second = knowledge.save(
        _research_note(
            vault_path="lessons/rebuild.md",
            title="Rebuild lesson",
            body="Derived state must be replaceable from canonical Markdown.",
        )
    )

    rebuilt = knowledge.rebuild(SOMA_PROJECT_ID)
    health = knowledge.health(SOMA_PROJECT_ID)

    assert rebuilt.project_id == SOMA_PROJECT_ID
    assert rebuilt.indexed_count == 2
    assert rebuilt.malformed_count == 0
    assert health.status == "healthy"
    assert health.canonical_count == 2
    assert health.indexed_count == 2
    assert {
        hit.knowledge_id for hit in knowledge.search(SOMA_PROJECT_ID, "rebuild").records
    } == {second.knowledge_id}
    assert knowledge.get(SOMA_PROJECT_ID, first.knowledge_id).content_sha256


def test_rebuild_detects_external_obsidian_body_edit(
    knowledge: KnowledgeService,
) -> None:
    saved = knowledge.save(_research_note())
    path = knowledge.vault_root / saved.vault_path
    original = path.read_text(encoding="utf-8")
    path.write_text(
        original.replace(
            "Compact projections keep ordinary chat responses bounded.",
            "Obsidian edited this research while preserving its stable identity.",
        ),
        encoding="utf-8",
    )

    from soma.knowledge.vault import integrity_drift

    result = knowledge.rebuild(SOMA_PROJECT_ID)
    recovered = knowledge.get(SOMA_PROJECT_ID, saved.knowledge_id)

    # The edit is adopted -- the file is canonical -- and it is *reported*.
    # `read()` used to recompute the stored hash on the way out, so an external
    # edit silently became its own proof of integrity: the record looked intact
    # and no caller could tell. The stored hash is now left alone, so the
    # disagreement between it and the content is what surfaces the edit.
    assert "Obsidian edited" in recovered.body
    assert knowledge.search(SOMA_PROJECT_ID, "Obsidian edited").total == 1
    assert recovered.content_sha256 == saved.content_sha256
    assert integrity_drift(recovered)

    assert result.drifted_count == 1
    health = knowledge.health(SOMA_PROJECT_ID)
    assert health.status == "dirty"
    assert health.drifted_paths == [saved.vault_path]
    assert health.malformed_count == 0


def test_malformed_markdown_is_excluded_and_health_is_degraded(
    knowledge: KnowledgeService,
) -> None:
    valid = knowledge.save(_research_note())
    malformed = knowledge.vault_root / "research" / "malformed.md"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text(
        "---\nproject_id: [not valid project metadata\n---\nsecret sibling claim\n",
        encoding="utf-8",
    )

    rebuilt = knowledge.rebuild(SOMA_PROJECT_ID)
    health = knowledge.health(SOMA_PROJECT_ID)

    assert rebuilt.malformed_count == 1
    assert health.status == "degraded"
    assert health.malformed_count == 1
    assert [
        record.knowledge_id
        for record in knowledge.search(SOMA_PROJECT_ID, "claim").records
    ] == []
    assert (
        knowledge.get(SOMA_PROJECT_ID, valid.knowledge_id).knowledge_id
        == valid.knowledge_id
    )


# ----------------------------------------------------------------------
# MEMORY-INTEGRATION-FOUNDATION-1 step 1 -- canonical lifecycle repairs


def test_integrity_hash_covers_lifecycle_and_provenance(knowledge):
    """Regression: the v1 hash covered only content, so lifecycle was unprotected."""
    record = knowledge.save(_research_note(idempotency_key="integrity-1"))
    baseline = record.content_sha256

    from soma.knowledge.vault import content_hash

    tampered = record.model_copy(update={"status": "rejected"})
    assert content_hash(tampered) != baseline

    relinked = record.model_copy(update={"supersedes_ids": ["kn_somethingelse"]})
    assert content_hash(relinked) != baseline

    reprovenanced = record.model_copy(
        update={"sources": [SourceReference(source_id="src_injected", uri="x")]}
    )
    assert content_hash(reprovenanced) != baseline


def test_owner_note_is_unadopted_not_malformed(knowledge, tmp_path):
    """A hand-written Obsidian note must not report the vault as corrupt."""
    knowledge.save(_research_note(idempotency_key="adopt-1"))
    vault = Path(knowledge.vault_root)
    (vault / "daily").mkdir(parents=True, exist_ok=True)
    (vault / "daily" / "2026-07-28.md").write_text(
        "# Thursday\n\nCalled the bank. Follow up on the invoice.\n",
        encoding="utf-8",
    )

    health = knowledge.health(SOMA_PROJECT_ID)
    assert health.malformed_count == 0
    assert health.unadopted_count == 1
    assert health.unadopted_paths == ["daily/2026-07-28.md"]
    assert health.status == "healthy"


def test_corrupt_soma_record_is_still_degraded(knowledge):
    """An unparsable Soma-owned record remains corruption, not an owner note."""
    knowledge.save(_research_note(idempotency_key="corrupt-1"))
    vault = Path(knowledge.vault_root)
    (vault / "broken.md").write_text(
        "---\nknowledge_id: kn_broken\nproject_id: "
        + SOMA_PROJECT_ID
        + "\nkind: [unclosed\n---\n\nbody\n",
        encoding="utf-8",
    )
    health = knowledge.health(SOMA_PROJECT_ID)
    assert health.malformed_count == 1
    assert health.malformed_paths == ["broken.md"]
    assert health.status == "degraded"


def test_supersession_is_link_derived_and_survives_interruption(knowledge, monkeypatch):
    """Regression: an interrupted predecessor rewrite left state reading current."""
    original = knowledge.save(
        _research_note(vault_path="a.md", idempotency_key="chain-1")
    )

    # The projection write fails exactly as a crash between the two writes would.
    def explode(record):
        raise OSError("interrupted before the predecessor was rewritten")

    monkeypatch.setattr(knowledge, "_project_superseded", explode)
    successor = knowledge.supersede(
        _research_note(vault_path="b.md", idempotency_key="chain-2"),
        [original.knowledge_id],
    )

    # The predecessor's own file still declares `current` ...
    stale = knowledge.get(SOMA_PROJECT_ID, original.knowledge_id)
    assert stale.status == "current"
    # ... but the successor's link is what actually determines effective state.
    assert knowledge.effective_status(stale) == "superseded"
    assert successor.supersedes_ids == [original.knowledge_id]

    # And a current-only search must not return it.
    page = knowledge.search(SOMA_PROJECT_ID, "Compact projections", current_only=True)
    assert original.knowledge_id not in {r.knowledge_id for r in page.records}


def test_supersession_links_rebuild_from_markdown_alone(knowledge):
    original = knowledge.save(
        _research_note(vault_path="a.md", idempotency_key="rebuild-1")
    )
    knowledge.supersede(
        _research_note(vault_path="b.md", idempotency_key="rebuild-2"),
        [original.knowledge_id],
    )
    knowledge.catalog.replace_project(
        SOMA_PROJECT_ID, [], canonical_count=0, malformed_count=0, updated_at="now"
    )
    knowledge.rebuild(SOMA_PROJECT_ID)
    assert original.knowledge_id in knowledge.catalog.superseded_ids(SOMA_PROJECT_ID)


def test_search_prefers_canonical_markdown_over_the_catalog(knowledge):
    """Regression: search served a cached projection an owner edit had outdated."""
    record = knowledge.save(
        _research_note(body="Original body ZULUCANARY", idempotency_key="reread-1")
    )
    path = Path(knowledge.vault_root) / record.vault_path
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("Original body ZULUCANARY", "Owner rewrote this by hand"),
        encoding="utf-8",
    )
    page = knowledge.search(SOMA_PROJECT_ID, "ZULUCANARY")
    assert page.records
    assert page.records[0].body == "Owner rewrote this by hand"
