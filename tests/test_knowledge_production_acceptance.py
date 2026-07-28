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

    knowledge.rebuild(SOMA_PROJECT_ID)
    recovered = knowledge.get(SOMA_PROJECT_ID, saved.knowledge_id)

    assert recovered.content_sha256 != saved.content_sha256
    assert "Obsidian edited" in recovered.body
    assert knowledge.search(SOMA_PROJECT_ID, "Obsidian edited").total == 1


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
