"""Typed vocabulary for the minimal Basic Memory binding and health guard.

BASIC-MEMORY-GUARD-1. The guard owns identity, routing and health disposition.
It never owns storage, embeddings, ranking, semantic search or graph traversal --
those belong to the replaceable provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final


GUARD_MODEL_VERSION: Final[str] = "basic_memory_guard.v1"
GUARD_DECISION_ID: Final[str] = "BASIC-MEMORY-GUARD-1"

#: The provider stack this guard's evidence was measured against. These are
#: evidence-bound starting points, not universal defaults: any change requires a
#: bounded compatibility check before its health disposition becomes accepted.
FROZEN_EVIDENCE_STACK: Final[dict[str, str]] = {
    "basic_memory": "0.22.1",
    "fastembed": "0.8.0",
    "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "windows_litellm_pin": "1.91.4",
}

#: Measured against the frozen pilot corpus, calibrated from the nonsense-query
#: noise ceiling (0.238) plus margin. Corpus-specific, not a universal default.
PILOT_SIMILARITY_THRESHOLD: Final[float] = 0.30


class GuardError(ValueError):
    """The guard refused to reach the provider."""


class IdentityRefused(GuardError):
    """Project identity was omitted, unknown, inactive or mismatched."""


class ProfileRefused(GuardError):
    """The provider profile is not the accepted local-only profile."""


class HealthRefused(GuardError):
    """Coverage could not be proven, so semantic retrieval is blocked."""


class ToolRefused(GuardError):
    """The requested provider operation is outside the exact allowlist."""


class PathRefused(GuardError):
    """A returned or requested path escaped the bound canonical root."""


class HealthState(str, Enum):
    """Published honestly. Only HEALTHY permits semantic retrieval."""

    HEALTHY = "healthy"
    REBUILDING = "rebuilding"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class RefusalReason(str, Enum):
    """Why the guard refused, recorded for provenance."""

    PROJECT_OMITTED = "project_omitted"
    PROJECT_UNKNOWN = "project_unknown"
    PROJECT_INACTIVE = "project_inactive"
    PROJECT_MISMATCH = "project_mismatch"
    NO_BINDING = "no_binding"
    SCOPE_GENERATION_STALE = "scope_generation_stale"
    CLOUD_REACHABLE = "cloud_reachable"
    MUTATING_PROFILE = "mutating_profile"
    FORBIDDEN_SYNC_PATH = "forbidden_sync_path"
    COVERAGE_UNPROVEN = "coverage_unproven"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    PATH_OUTSIDE_ROOT = "path_outside_root"


@dataclass(frozen=True)
class ProviderBinding:
    """Exact project_id -> provider project -> constrained process -> root.

    Every field is required. There is no inference path: a binding either exists
    in full or the guard refuses.
    """

    project_id: str
    provider_project: str
    canonical_root: str
    root_identity_hash: str
    scope_generation: int

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "provider_project": self.provider_project,
            "canonical_root": self.canonical_root,
            "root_identity_hash": self.root_identity_hash,
            "scope_generation": self.scope_generation,
        }

    def process_env(self) -> dict[str, str]:
        """Environment constraining a provider process to exactly this project."""
        return {
            "BASIC_MEMORY_MCP_PROJECT": self.provider_project,
            "BASIC_MEMORY_PROJECT": self.provider_project,
        }


@dataclass(frozen=True)
class CoverageReport:
    """OS manifest compared against provider-visible coverage.

    `provider_entities` is None when the provider did not report a count in a
    shape the guard understands. That is treated as unproven, never as zero and
    never as complete.
    """

    project_id: str
    provider_project: str
    os_eligible_files: int
    provider_entities: int | None
    pending_changes: int | None
    missing_paths: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def proven_complete(self) -> bool:
        if self.provider_entities is None:
            return False
        if self.pending_changes is None or self.pending_changes > 0:
            return False
        if self.missing_paths:
            return False
        return self.provider_entities >= self.os_eligible_files

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "provider_project": self.provider_project,
            "os_eligible_files": self.os_eligible_files,
            "provider_entities": self.provider_entities,
            "pending_changes": self.pending_changes,
            "missing_paths": list(self.missing_paths),
            "proven_complete": self.proven_complete,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class HealthDisposition:
    """The guard's published health, and whether semantic use is permitted."""

    state: HealthState
    coverage: CoverageReport
    reason: RefusalReason | None = None
    detail: str = ""
    stale_generation: bool = False

    @property
    def semantic_permitted(self) -> bool:
        return self.state is HealthState.HEALTHY

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "semantic_permitted": self.semantic_permitted,
            "reason": self.reason.value if self.reason else "",
            "detail": self.detail,
            "stale_generation": self.stale_generation,
            "coverage": self.coverage.to_dict(),
        }


@dataclass(frozen=True)
class GuardResult:
    """A provider response that survived binding, health and path validation."""

    project_id: str
    provider_project: str
    operation: str
    used_fallback: bool
    health: HealthDisposition
    items: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "provider_project": self.provider_project,
            "operation": self.operation,
            "used_fallback": self.used_fallback,
            "health": self.health.to_dict(),
            "items": list(self.items),
            "model_version": GUARD_MODEL_VERSION,
        }
