from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import normalize_repo_relative_path, relation_id

RESEARCH_MAP_SCHEMA_VERSION = "soma.research-map.v2"
PREDICATE_REGISTRY_VERSION = "soma.research-map.predicates.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_UID_RE = re.compile(r"^srepo_[0-9a-f]{16,64}$")
_RELATION_ID_RE = re.compile(r"^rel_[0-9a-f]{64}$")


class ResearchMapModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Predicate(StrEnum):
    ALLOWS = "ALLOWS"
    CONSTRAINS = "CONSTRAINS"
    FALSIFIES = "FALSIFIES"
    FORBIDS = "FORBIDS"
    LIMITS = "LIMITS"
    MOTIVATES = "MOTIVATES"
    NARROWS = "NARROWS"
    PRESERVES = "PRESERVES"
    QUALIFIES = "QUALIFIES"
    REQUIRES = "REQUIRES"
    SUPPORTS = "SUPPORTS"

    GOVERNS = "GOVERNS"
    AMENDS = "AMENDS"
    AUDITS = "AUDITS"
    ACCEPTS = "ACCEPTS"
    SUPERSEDES = "SUPERSEDES"
    RECONCILES = "RECONCILES"
    CLOSES = "CLOSES"
    REOPENS = "REOPENS"
    AUTHORIZES = "AUTHORIZES"
    PARKS = "PARKS"

    INFORMED_BY = "INFORMED_BY"
    IMPORTS_EVIDENCE_FROM = "IMPORTS_EVIDENCE_FROM"
    DERIVES_FROM = "DERIVES_FROM"
    REPRODUCES = "REPRODUCES"
    REPLAYS = "REPLAYS"


class EpistemicClass(StrEnum):
    OBSERVED = "observed"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    DECISION = "decision"
    REQUIREMENT = "requirement"
    CONSTRAINT = "constraint"
    INTERPRETATION = "interpretation"
    UNKNOWN = "unknown"


class RelationLifecycle(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    DISPUTED = "disputed"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class ReviewState(StrEnum):
    REVIEWED = "reviewed"
    DEFERRED = "deferred"


class Materiality(StrEnum):
    MATERIAL = "material"
    NONE = "none"


def _validate_string_map(value: dict[str, list[str]], field_name: str) -> dict[str, list[str]]:
    for key, items in value.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 128:
            raise ValueError(f"{field_name} keys must be non-empty strings <= 128 chars")
        if not isinstance(items, list):
            raise TypeError(f"{field_name} values must be lists")
        if len(items) > 100:
            raise ValueError(f"{field_name} lists may contain at most 100 values")
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item) > 1000:
                raise ValueError(
                    f"{field_name} values must be non-empty strings <= 1000 chars"
                )
            if item in seen:
                raise ValueError(f"{field_name} values must not contain duplicates")
            seen.add(item)
    return value


class ResearchRootConfig(ResearchMapModel):
    path: str = Field(min_length=1, max_length=1024)
    sidecar_dir: str = Field(default="_soma_map", min_length=1, max_length=256)
    include: list[str] = Field(default_factory=lambda: ["*.md"], min_length=1, max_length=32)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return normalize_repo_relative_path(value)

    @field_validator("sidecar_dir")
    @classmethod
    def validate_sidecar_dir(cls, value: str) -> str:
        normalized = normalize_repo_relative_path(value)
        if normalized == ".":
            raise ValueError("sidecar_dir must not equal the research root")
        return normalized

    @field_validator("include")
    @classmethod
    def validate_include(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for pattern in value:
            if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 256:
                raise ValueError("include patterns must be non-empty strings <= 256 chars")
            normalized = pattern.replace("\\", "/")
            if normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
                raise ValueError("include patterns must be repository-relative")
            if ".." in normalized.split("/"):
                raise ValueError("include patterns must not traverse upward")
            if normalized in seen:
                raise ValueError("include patterns must not contain duplicates")
            seen.add(normalized)
        return value


class ResearchMapConfig(ResearchMapModel):
    enabled: bool = True
    schema_name: Literal["soma.research-map.v2"] = Field(
        default=RESEARCH_MAP_SCHEMA_VERSION,
        alias="schema",
        serialization_alias="schema",
    )
    roots: list[ResearchRootConfig] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def reject_overlapping_roots(self) -> ResearchMapConfig:
        paths = sorted(root.path for root in self.roots)
        for index, left in enumerate(paths):
            for right in paths[index + 1 :]:
                if right == left or right.startswith(f"{left}/"):
                    raise ValueError("research roots must not overlap or double-own sources")
        return self


class ProjectManifest(ResearchMapModel):
    schema_name: Literal["soma.project.v1"] = Field(
        default="soma.project.v1",
        alias="schema",
        serialization_alias="schema",
    )
    repository_uid: str
    research_map: ResearchMapConfig

    @field_validator("repository_uid")
    @classmethod
    def validate_repository_uid(cls, value: str) -> str:
        normalized = value.casefold()
        if not _REPOSITORY_UID_RE.fullmatch(normalized):
            raise ValueError("repository_uid must be srepo_ followed by 16-64 hex chars")
        return normalized


class SourceEnvelope(ResearchMapModel):
    path: str = Field(min_length=1, max_length=1024)
    canonical_text_sha256: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = normalize_repo_relative_path(value)
        if not normalized.casefold().endswith(".md"):
            raise ValueError("research-map source path must identify UTF-8 Markdown")
        if "/_soma_map/" in f"/{normalized.casefold()}/":
            raise ValueError("source path must identify research source, not a map sidecar")
        return normalized

    @field_validator("canonical_text_sha256")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        normalized = value.casefold()
        if not _SHA256_RE.fullmatch(normalized):
            raise ValueError("canonical_text_sha256 must be a SHA-256 digest")
        return normalized


class ReviewEnvelope(ResearchMapModel):
    state: ReviewState
    controller: str = Field(min_length=1, max_length=128)
    materiality: Materiality | None = None

    @model_validator(mode="after")
    def validate_materiality(self) -> ReviewEnvelope:
        if self.state is ReviewState.REVIEWED and self.materiality is None:
            raise ValueError("reviewed sidecars require materiality")
        if self.state is ReviewState.DEFERRED and self.materiality is not None:
            raise ValueError("deferred sidecars must omit materiality")
        return self


class SemanticNode(ResearchMapModel):
    key: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=2000)

    @field_validator("key", "label")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("semantic node values must not be blank")
        return value


class SourceLocator(ResearchMapModel):
    anchor: str = Field(min_length=1, max_length=20_000)

    @field_validator("anchor")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("anchor must not be blank")
        return value


class ResearchMapRelation(ResearchMapModel):
    relation_id: str
    subject: SemanticNode
    predicate: Predicate
    object: SemanticNode
    statement: str = Field(min_length=1, max_length=100_000)
    locator: SourceLocator
    epistemic_class: EpistemicClass
    lifecycle: RelationLifecycle = RelationLifecycle.CURRENT
    supersedes: list[str] = Field(default_factory=list, max_length=100)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    qualifiers: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("relation_id")
    @classmethod
    def validate_relation_id(cls, value: str) -> str:
        normalized = value.casefold()
        if not _RELATION_ID_RE.fullmatch(normalized):
            raise ValueError("relation_id must be rel_ followed by a SHA-256 digest")
        return normalized

    @field_validator("statement")
    @classmethod
    def reject_blank_statement(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("statement must not be blank")
        return value

    @field_validator("supersedes")
    @classmethod
    def validate_supersedes(cls, value: list[str]) -> list[str]:
        normalized = [item.casefold() for item in value]
        if any(not _RELATION_ID_RE.fullmatch(item) for item in normalized):
            raise ValueError("supersedes entries must be relation IDs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("supersedes must not contain duplicates")
        return normalized

    @field_validator("facets")
    @classmethod
    def validate_facets(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        return _validate_string_map(value, "facets")

    @field_validator("qualifiers")
    @classmethod
    def validate_qualifiers(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        return _validate_string_map(value, "qualifiers")

    @model_validator(mode="after")
    def reject_self_supersession(self) -> ResearchMapRelation:
        if self.relation_id in self.supersedes:
            raise ValueError("a relation cannot supersede itself")
        return self


class ResearchMapSidecar(ResearchMapModel):
    schema_version: Literal["soma.research-map.v2"] = RESEARCH_MAP_SCHEMA_VERSION
    source: SourceEnvelope
    review: ReviewEnvelope
    facets: dict[str, list[str]] = Field(default_factory=dict)
    relations: list[ResearchMapRelation] = Field(default_factory=list, max_length=1000)

    @field_validator("facets")
    @classmethod
    def validate_facets(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        return _validate_string_map(value, "facets")

    @model_validator(mode="after")
    def validate_relations(self) -> ResearchMapSidecar:
        relation_ids: set[str] = set()
        for relation in self.relations:
            expected = relation_id(
                self.source.path,
                relation.subject.key,
                relation.predicate.value,
                relation.object.key,
            )
            if relation.relation_id != expected:
                raise ValueError(
                    f"relation_id does not match deterministic identity for {relation.subject.key}"
                )
            if relation.relation_id in relation_ids:
                raise ValueError("sidecar contains duplicate relation IDs")
            relation_ids.add(relation.relation_id)

        if self.review.state is ReviewState.DEFERRED:
            if self.relations:
                raise ValueError("deferred sidecars must not contain relations")
            return self

        if self.review.materiality is Materiality.NONE and self.relations:
            raise ValueError("reviewed-no-material sidecars must have no relations")
        if self.review.materiality is Materiality.MATERIAL and not self.relations:
            raise ValueError("material sidecars require at least one relation")
        return self
