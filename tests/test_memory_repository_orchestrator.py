from __future__ import annotations

from pathlib import Path

from codexbridge.local_agent import LocalAgentOrchestrator
from codexbridge.local_agent.models import LocalAgentTaskType, RoutingDecision
from codexbridge.memory.models import (
    MemoryRecord,
    MemoryType,
    RepoProfileMemory,
    ValidationRecipeMemory,
)
from codexbridge.memory.repository import ProjectMemoryRepository


def repo(tmp_path: Path) -> ProjectMemoryRepository:
    return ProjectMemoryRepository(
        db_path=tmp_path / "runs" / "memory" / "project_memory.sqlite3"
    )


def test_decision_validation_and_repo_profile_memory(tmp_path: Path) -> None:
    memory_repo = repo(tmp_path)
    decision = memory_repo.remember_decision(
        "Use SQLite for first memory store", accepted_by="user"
    )
    recipe = memory_repo.remember_validation_recipe_model(
        ValidationRecipeMemory(
            repo_name="repo", commands=["python -m pytest -q", "python -m pip check"]
        )
    )
    profile = memory_repo.remember_repo_profile(
        RepoProfileMemory(
            repo_name="repo",
            test_command_ids=["pytest"],
            job_profile_ids=["dummy_success"],
            notes="CodexBridge repo",
        )
    )

    assert memory_repo.latest_decision_summary().memory_id == decision.memory_id
    assert "pytest" in recipe.content
    assert profile.metadata["repo_name"] == "repo"


def test_latest_job_run_and_continue_last_task(tmp_path: Path) -> None:
    memory_repo = repo(tmp_path)
    memory_repo.store.create(
        MemoryRecord(memory_type=MemoryType.RUN, title="Run", content="run summary")
    )
    job = memory_repo.store.create(
        MemoryRecord(memory_type=MemoryType.JOB, title="Job", content="job summary")
    )

    assert memory_repo.latest_run_summary().title == "Run"
    assert memory_repo.latest_job_summary().memory_id == job.memory_id
    assert memory_repo.continue_last_task().memory_id == job.memory_id


def test_orchestrator_routes_explicit_memory_tasks(tmp_path: Path) -> None:
    memory_repo = repo(tmp_path)
    orchestrator = LocalAgentOrchestrator(memory_repository=memory_repo)

    remembered = orchestrator.handle_task(
        "remember project fact: CodexBridge uses allowlisted commands"
    )
    search = orchestrator.handle_task("search memory: allowlisted")

    assert remembered.task_type == LocalAgentTaskType.MEMORY
    assert remembered.routing_decision == RoutingDecision.LOCAL_ONLY
    assert remembered.memory_result["memory_type"] == "static_memory"
    assert search.memory_result["total"] == 1
    assert remembered.audit_event.metadata["codex_called"] is False


def test_orchestrator_continue_last_task_uses_memory_only(tmp_path: Path) -> None:
    memory_repo = repo(tmp_path)
    memory_repo.store.create(
        MemoryRecord(
            memory_type=MemoryType.JOB, title="Latest job", content="job completed"
        )
    )

    result = LocalAgentOrchestrator(memory_repository=memory_repo).handle_task(
        "continue last CodexBridge task"
    )

    assert result.memory_result["title"] == "Latest job"


def test_orchestrator_does_not_route_edit_tasks_to_memory(tmp_path: Path) -> None:
    result = LocalAgentOrchestrator(memory_repository=repo(tmp_path)).handle_task(
        "fix and refactor memory store"
    )

    assert result.routing_decision == RoutingDecision.LOCAL_ONLY
    assert result.memory_result is None


def test_memory_modules_do_not_execute_commands_or_call_external_agents() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("codexbridge/memory").glob("*.py")
    )

    assert "subprocess" not in source
    assert "CodexRunner" not in source
    assert "import PulseSender" not in source
    assert "from PulseSender" not in source
    assert "playwright" not in source.lower()
    assert "selenium" not in source.lower()
