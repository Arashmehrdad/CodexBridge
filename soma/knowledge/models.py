from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    source_id: str = Field(min_length=1, max_length=256)
    uri: str = Field(default="", max_length=4096)
    title: str = Field(default="", max_length=1000)
    version: str = Field(default="", max_length=256)
    content_hash: str = Field(default="", max_length=256)


class SourceLocator(BaseModel):
    source_id: str = Field(min_length=1, max_length=256)
    locator: str = Field(min_length=1, max_length=2000)
    relationship: str = Field(default="supports", max_length=128)


class KnowledgeInput(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    vault_path: str = Field(min_length=1, max_length=1024)
    kind: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=1000)
    body: str = Field(default="", max_length=1_000_000)
    summary: str = Field(default="", max_length=10_000)
    tags: list[str] = Field(default_factory=list)
    status: str = Field(default="current", max_length=64)
    review_state: str = Field(default="unreviewed", max_length=64)
    sources: list[SourceReference] = Field(default_factory=list)
    locators: list[SourceLocator] = Field(default_factory=list)
    supersedes_ids: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(default="", max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


ResearchNoteInput = KnowledgeInput


class KnowledgeRecord(KnowledgeInput):
    knowledge_id: str
    revision: int = 1
    created_at: str
    updated_at: str
    content_sha256: str


class KnowledgeSearchPage(BaseModel):
    records: list[KnowledgeRecord]
    total: int
    next_cursor: str | None = None
    has_more: bool = False


class RebuildResult(BaseModel):
    project_id: str
    indexed_count: int
    malformed_count: int


class KnowledgeHealth(BaseModel):
    project_id: str
    status: Literal["healthy", "degraded", "empty"]
    canonical_count: int
    indexed_count: int
    malformed_count: int
