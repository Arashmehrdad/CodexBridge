from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.memory.models import MemoryRecord, MemoryType
from codexbridge.memory.store import ProjectMemoryStore


def store(tmp_path: Path, *, block_sensitive: bool = True) -> ProjectMemoryStore:
    return ProjectMemoryStore(
        tmp_path / "runs" / "memory" / "project_memory.sqlite3",
        block_sensitive=block_sensitive,
    )


def test_memory_schema_initializes_and_is_idempotent(tmp_path: Path) -> None:
    first = store(tmp_path)
    second = store(tmp_path)

    assert first.db_path.exists()
    assert first.schema_version() == 1
    assert second.schema_version() == 1


def test_create_get_update_archive_memory_record(tmp_path: Path) -> None:
    memory_store = store(tmp_path)
    created = memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.STATIC,
            title="Architecture note",
            summary="Use allowlists",
            content="Command execution uses profiles.",
            tags=["architecture"],
            repo_name="sample",
        )
    )

    fetched = memory_store.get(created.memory_id)
    assert fetched.title == "Architecture note"
    updated = memory_store.update(created.memory_id, summary="Use strict allowlists")
    assert updated.summary == "Use strict allowlists"
    archived = memory_store.archive(created.memory_id)
    assert archived.archived is True
    assert memory_store.list_records() == []
    assert (
        memory_store.list_records(include_archived=True)[0].memory_id
        == created.memory_id
    )


def test_list_by_type_repo_project_and_tag(tmp_path: Path) -> None:
    memory_store = store(tmp_path)
    memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.DECISION,
            project_key="p1",
            repo_name="repo",
            title="D1",
            tags=["decision"],
            content="Use sqlite",
        )
    )
    memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.STATIC,
            project_key="p2",
            repo_name="other",
            title="S1",
            tags=["static"],
            content="Note",
        )
    )

    assert len(memory_store.list_records(memory_type=MemoryType.DECISION)) == 1
    assert len(memory_store.list_records(repo_name="repo")) == 1
    assert len(memory_store.list_records(project_key="p1")) == 1
    assert len(memory_store.list_records(tag="decision")) == 1


def test_simple_search_and_recent_order(tmp_path: Path) -> None:
    memory_store = store(tmp_path)
    older = memory_store.create(
        MemoryRecord(memory_type=MemoryType.STATIC, title="Old", content="alpha")
    )
    newer = memory_store.create(
        MemoryRecord(memory_type=MemoryType.STATIC, title="New", content="beta alpha")
    )

    result = memory_store.search("alpha")
    assert result.total == 2
    assert memory_store.recent(limit=2)[0].memory_id == newer.memory_id
    assert {record.memory_id for record in result.records} == {
        older.memory_id,
        newer.memory_id,
    }


def test_duplicate_source_or_content_is_deduplicated(tmp_path: Path) -> None:
    memory_store = store(tmp_path)
    first = memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.RUN,
            title="Run",
            content="same",
            source_kind="run",
            source_id="1",
        )
    )
    duplicate = memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.RUN,
            title="Run",
            content="same",
            source_kind="run",
            source_id="1",
        )
    )

    assert duplicate.memory_id == first.memory_id
    assert len(memory_store.list_records()) == 1


def test_secret_like_content_is_blocked_or_redacted(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        store(tmp_path).create(
            MemoryRecord(
                memory_type=MemoryType.STATIC,
                title="Secret",
                content="api key = abc123",
            )
        )

    redacting_store = store(tmp_path / "redact", block_sensitive=False)
    record = redacting_store.create(
        MemoryRecord(
            memory_type=MemoryType.STATIC, title="Token", content="token=abc123"
        )
    )
    assert "abc123" not in record.content
    assert record.sensitivity_flags


def test_validation_recipes_known_commands_architecture_notes(tmp_path: Path) -> None:
    memory_store = store(tmp_path)
    memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.STATIC,
            title="Recipe",
            content="python -m pytest -q",
            tags=["validation_recipe", "known_command"],
            repo_name="repo",
        )
    )
    memory_store.create(
        MemoryRecord(
            memory_type=MemoryType.STATIC,
            title="Arch",
            content="Layered modules",
            tags=["architecture"],
            repo_name="repo",
        )
    )

    assert memory_store.validation_recipes("repo")[0].content == "python -m pytest -q"
    assert memory_store.known_commands("repo")[0].title == "Recipe"
    assert memory_store.architecture_notes("repo")[0].title == "Arch"
