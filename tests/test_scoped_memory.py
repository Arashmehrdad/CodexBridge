from __future__ import annotations

from pathlib import Path

from codexbridge.memory.repository import ProjectMemoryRepository


def test_scoped_search_does_not_cross_repositories(tmp_path: Path) -> None:
    memory = ProjectMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    memory.remember_decision("Use event sourcing for Alpha", repo_name="alpha")
    memory.remember_decision("Use direct writes for Beta", repo_name="beta")

    alpha = memory.search("Use", repo_name="alpha")
    beta = memory.search("Use", repo_name="beta")

    assert [record.repo_name for record in alpha.records] == ["alpha"]
    assert [record.repo_name for record in beta.records] == ["beta"]
    assert "event sourcing" in alpha.records[0].content
    assert "direct writes" in beta.records[0].content


def test_scoped_search_can_include_global_memory(tmp_path: Path) -> None:
    memory = ProjectMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    memory.remember_project_fact("Prefer PowerShell for validation")
    memory.remember_project_fact("Alpha uses Python 3.12", repo_name="alpha")
    memory.remember_project_fact("Beta uses Go", repo_name="beta")

    scoped_only = memory.search("Prefer", repo_name="alpha")
    with_global = memory.search("Prefer", repo_name="alpha", include_global=True)

    assert scoped_only.records == []
    assert len(with_global.records) == 1
    assert with_global.records[0].repo_name is None


def test_latest_decision_is_repository_scoped(tmp_path: Path) -> None:
    memory = ProjectMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    alpha = memory.remember_decision("Alpha decision", repo_name="alpha")
    beta = memory.remember_decision("Beta decision", repo_name="beta")

    assert (
        memory.latest_decision_summary(repo_name="alpha").memory_id == alpha.memory_id
    )
    assert memory.latest_decision_summary(repo_name="beta").memory_id == beta.memory_id
    assert memory.continue_last_task(repo_name="alpha").memory_id == alpha.memory_id
