from __future__ import annotations

from pathlib import Path

from codexbridge.config import AppConfig, MemoryConfig

from .models import MemoryRecord, MemoryType, RepoProfileMemory, ValidationRecipeMemory
from .store import ProjectMemoryStore


class ProjectMemoryRepository:
    def __init__(self, *, config: AppConfig | None = None, db_path: Path | None = None, memory_config: MemoryConfig | None = None):
        settings = memory_config or (config.memory if config else MemoryConfig())
        if db_path is None:
            db_path = config.resolve_memory_db_path() if config else Path.cwd() / "runs" / "memory" / "project_memory.sqlite3"
        self.store = ProjectMemoryStore(
            db_path,
            max_content_bytes=settings.memory_max_content_bytes,
            redact_sensitive=settings.memory_redact_sensitive,
            block_sensitive=settings.memory_block_sensitive,
        )

    def remember_project_fact(self, fact: str, *, repo_name: str | None = None, repo_path: Path | None = None) -> MemoryRecord:
        return self.store.create(
            MemoryRecord(
                memory_type=MemoryType.STATIC,
                repo_name=repo_name,
                repo_path=repo_path,
                title="Project fact",
                summary=fact[:300],
                content=fact,
                tags=["project_fact"],
                source_kind="manual",
            )
        )

    def remember_decision(self, decision: str, *, repo_name: str | None = None, repo_path: Path | None = None, accepted_by: str | None = None) -> MemoryRecord:
        return self.store.create(
            MemoryRecord(
                memory_type=MemoryType.DECISION,
                repo_name=repo_name,
                repo_path=repo_path,
                title="Decision",
                summary=decision[:300],
                content=decision,
                tags=["decision"],
                source_kind="manual",
                metadata={"accepted_by": accepted_by} if accepted_by else {},
            )
        )

    def remember_validation_recipe(self, recipe: str, *, repo_name: str | None = None) -> MemoryRecord:
        return self.store.create(
            MemoryRecord(
                memory_type=MemoryType.STATIC,
                repo_name=repo_name,
                title="Validation recipe",
                summary=recipe[:300],
                content=recipe,
                tags=["validation_recipe", "known_command"],
                source_kind="manual",
            )
        )

    def remember_repo_profile(self, profile: RepoProfileMemory) -> MemoryRecord:
        return self.store.create(
            MemoryRecord(
                memory_type=MemoryType.STATIC,
                project_key=profile.project_key,
                repo_name=profile.repo_name,
                repo_path=profile.repo_path,
                title=f"Repo profile: {profile.repo_name or profile.repo_path or profile.project_key}",
                summary=profile.notes,
                content=profile.model_dump_json(indent=2),
                tags=["repo_profile", "architecture"],
                source_kind="repo_profile",
                metadata=profile.model_dump(mode="json"),
            )
        )

    def remember_validation_recipe_model(self, recipe: ValidationRecipeMemory) -> MemoryRecord:
        return self.remember_validation_recipe("\n".join(recipe.commands) + ("\n" + recipe.notes if recipe.notes else ""), repo_name=recipe.repo_name)

    def search(self, query: str, *, limit: int = 20):
        return self.store.search(query, limit=limit)

    def latest_job_summary(self) -> MemoryRecord | None:
        return self.store.latest_by_type(MemoryType.JOB)

    def latest_run_summary(self) -> MemoryRecord | None:
        return self.store.latest_by_type(MemoryType.RUN)

    def latest_decision_summary(self) -> MemoryRecord | None:
        return self.store.latest_by_type(MemoryType.DECISION)

    def continue_last_task(self) -> MemoryRecord | None:
        return self.latest_job_summary() or self.latest_run_summary() or self.latest_decision_summary()
