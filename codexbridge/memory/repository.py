from __future__ import annotations

import json
from pathlib import Path

from codexbridge.config import AppConfig, MemoryConfig

from .models import MemoryRecord, MemorySearchResult, MemoryType, RepoProfileMemory, ValidationRecipeMemory
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

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        repo_name: str | None = None,
        project_key: str | None = None,
        include_global: bool = False,
    ) -> MemorySearchResult:
        """
        Search memory, scoped to a repository or project when supplied.

        With no scope this preserves the historical global search. When a
        repository or project scope is supplied, unrelated records are never
        returned. ``include_global`` additionally allows unscoped shared
        records, which is useful for cross-project user preferences.
        """
        normalized = query.strip().casefold()
        if not normalized:
            raise ValueError("query must not be empty")
        maximum = max(1, min(limit, 200))
        if repo_name is None and project_key is None:
            return self.store.search(query, limit=maximum)

        candidates = self.store.list_records(
            repo_name=repo_name,
            project_key=project_key,
            limit=500,
        )
        if include_global:
            for record in self.store.list_records(limit=500):
                if record.repo_name is None and record.project_key is None:
                    candidates.append(record)

        seen: set[str] = set()
        matches: list[MemoryRecord] = []
        for record in candidates:
            if record.memory_id in seen:
                continue
            seen.add(record.memory_id)
            haystack = "\n".join(
                [
                    record.title,
                    record.summary,
                    record.content,
                    " ".join(record.tags),
                    json.dumps(record.metadata, sort_keys=True),
                ]
            ).casefold()
            if normalized in haystack:
                matches.append(record)
                if len(matches) >= maximum:
                    break
        return MemorySearchResult(records=matches, query=query, total=len(matches))

    def latest_job_summary(self, *, repo_name: str | None = None, project_key: str | None = None) -> MemoryRecord | None:
        return self._latest_by_type(MemoryType.JOB, repo_name=repo_name, project_key=project_key)

    def latest_run_summary(self, *, repo_name: str | None = None, project_key: str | None = None) -> MemoryRecord | None:
        return self._latest_by_type(MemoryType.RUN, repo_name=repo_name, project_key=project_key)

    def latest_decision_summary(self, *, repo_name: str | None = None, project_key: str | None = None) -> MemoryRecord | None:
        return self._latest_by_type(MemoryType.DECISION, repo_name=repo_name, project_key=project_key)

    def continue_last_task(self, *, repo_name: str | None = None, project_key: str | None = None) -> MemoryRecord | None:
        return (
            self.latest_job_summary(repo_name=repo_name, project_key=project_key)
            or self.latest_run_summary(repo_name=repo_name, project_key=project_key)
            or self.latest_decision_summary(repo_name=repo_name, project_key=project_key)
        )

    def _latest_by_type(
        self,
        memory_type: MemoryType,
        *,
        repo_name: str | None = None,
        project_key: str | None = None,
    ) -> MemoryRecord | None:
        if repo_name is None and project_key is None:
            return self.store.latest_by_type(memory_type)
        records = self.store.list_records(
            repo_name=repo_name,
            project_key=project_key,
            memory_type=memory_type,
            limit=1,
        )
        return records[0] if records else None
