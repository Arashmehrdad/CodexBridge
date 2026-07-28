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


#: The accepted lifecycle vocabulary (SOMA-SHARED-MEMORY-ARCH-1).
#:
#: `superseded` is *derived*, never the ground truth: a successor carrying
#: `supersedes_ids` is sufficient to establish a predecessor's effective state,
#: so an interrupted supersession cannot leave the store wrong. See
#: `KnowledgeService.effective_status`.
LifecycleState = Literal[
    "proposed",
    "current",
    "superseded",
    "disputed",
    "rejected",
    "archived",
]

#: Which authority a record speaks with. Ordinary memory never becomes reviewed
#: research merely because a generic `research_note` kind was used.
AuthorityClass = Literal["owner_memory", "controller_memory", "imported_legacy"]

#: Records written before authoritative lifecycle metadata existed.
KNOWLEDGE_FORMAT_VERSION: int = 2


class KnowledgeInput(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    vault_path: str = Field(min_length=1, max_length=1024)
    kind: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=1000)
    body: str = Field(default="", max_length=1_000_000)
    summary: str = Field(default="", max_length=10_000)
    tags: list[str] = Field(default_factory=list)
    status: LifecycleState = "current"
    review_state: str = Field(default="unreviewed", max_length=64)
    authority_class: AuthorityClass = "controller_memory"
    sources: list[SourceReference] = Field(default_factory=list)
    locators: list[SourceLocator] = Field(default_factory=list)
    supersedes_ids: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(default="", max_length=512)
    #: Temporal truth. Empty `valid_until` means "still valid as far as Soma
    #: knows", which is deliberately distinct from a recorded end date.
    valid_from: str = Field(default="", max_length=64)
    valid_until: str = Field(default="", max_length=64)
    #: Provenance of the request that produced the record.
    controller: str = Field(default="", max_length=128)
    task_id: str = Field(default="", max_length=128)
    run_id: str = Field(default="", max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


ResearchNoteInput = KnowledgeInput


class KnowledgeRecord(KnowledgeInput):
    knowledge_id: str
    revision: int = 1
    created_at: str
    updated_at: str
    content_sha256: str
    format_version: int = KNOWLEDGE_FORMAT_VERSION
    #: When Soma learned the fact, as distinct from when the fact became true.
    recorded_at: str = ""


class KnowledgeSearchPage(BaseModel):
    records: list[KnowledgeRecord]
    total: int
    next_cursor: str | None = None
    has_more: bool = False


class RebuildResult(BaseModel):
    project_id: str
    indexed_count: int
    malformed_count: int
    unadopted_count: int = 0


class KnowledgeHealth(BaseModel):
    """Canonical-vault health, separate from provider health.

    `unadopted_count` is deliberately not part of `malformed_count`. An owner's
    hand-written Obsidian note is not corruption: it is a file Soma does not yet
    manage. Conflating the two reported `degraded` the moment the owner used the
    workspace the architecture asks them to use.
    """

    project_id: str
    status: Literal["healthy", "dirty", "degraded", "empty"]
    canonical_count: int
    indexed_count: int
    malformed_count: int
    unadopted_count: int = 0
    unadopted_paths: list[str] = Field(default_factory=list)
    malformed_paths: list[str] = Field(default_factory=list)
    generation: int = 0
