from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    STATIC = "static_memory"
    RUN = "run_memory"
    ARTIFACT = "artifact_memory"
    DECISION = "decision_memory"
    JOB = "job_memory"


class MemoryRecord(BaseModel):
    memory_id: str = Field(default_factory=lambda: f"mem_{uuid4().hex}")
    memory_type: MemoryType
    project_key: str = "soma"
    repo_name: str | None = None
    repo_path: Path | None = None
    title: str
    summary: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    source_kind: str = ""
    source_id: str = ""
    source_path: Path | None = None
    artifact_paths: list[Path] = Field(default_factory=list)
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    expires_at: str | None = None
    supersedes_memory_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sensitivity_flags: list[str] = Field(default_factory=list)
    content_sha256: str = ""
    audit_event_id: str = ""
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class MemorySearchResult(BaseModel):
    records: list[MemoryRecord]
    query: str = ""
    total: int


class RepoProfileMemory(BaseModel):
    repo_name: str | None = None
    repo_path: Path | None = None
    project_key: str = "soma"
    default_branch: str | None = None
    test_command_ids: list[str] = Field(default_factory=list)
    job_profile_ids: list[str] = Field(default_factory=list)
    validation_recipe: list[str] = Field(default_factory=list)
    known_artifact_dirs: list[Path] = Field(default_factory=list)
    coding_rules: list[str] = Field(default_factory=list)
    notes: str = ""


class ValidationRecipeMemory(BaseModel):
    repo_name: str | None = None
    project_key: str = "soma"
    commands: list[str] = Field(default_factory=list)
    notes: str = ""
