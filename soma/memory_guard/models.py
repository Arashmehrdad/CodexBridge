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


class RuntimeRefused(GuardError):
    """The live provider runtime is not the frozen, evidence-bound stack."""


class ProviderExecutionRefused(GuardError):
    """The provider process did not complete successfully, so output is unusable."""


class HealthState(str, Enum):
    """Published honestly. Only HEALTHY permits semantic retrieval."""

    HEALTHY = "healthy"
    REBUILDING = "rebuilding"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    #: The runtime no longer matches the stack the evidence was measured
    #: against. Distinct from DEGRADED: nothing is broken, but the accepted
    #: health verdict does not transfer to an unverified stack.
    INCOMPATIBLE = "incompatible"


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
    COVERAGE_MEMBERSHIP_UNAVAILABLE = "coverage_membership_unavailable"
    COVERAGE_STALE_ENTITIES = "coverage_stale_entities"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    PATH_OUTSIDE_ROOT = "path_outside_root"
    PROVIDER_EXIT_FAILURE = "provider_exit_failure"
    RUNTIME_MISMATCH = "runtime_mismatch"


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
class RuntimeIdentity:
    """The provider stack actually present, measured rather than assumed.

    `FROZEN_EVIDENCE_STACK` records what the acceptance evidence was measured
    against. Until this identity is verified against it at runtime, a silently
    upgraded provider would inherit a health verdict that was never measured for
    it -- so the constants are enforced here rather than merely documented.
    """

    executable: str
    executable_sha256: str
    provider_version: str
    embedding_model: str
    similarity_threshold: float | None
    config_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "executable": self.executable,
            "executable_sha256": self.executable_sha256,
            "provider_version": self.provider_version,
            "embedding_model": self.embedding_model,
            "similarity_threshold": self.similarity_threshold,
            "config_sha256": self.config_sha256,
        }

    def mismatches(self) -> tuple[str, ...]:
        """Every way this runtime departs from the frozen evidence stack."""
        problems: list[str] = []
        expected_version = FROZEN_EVIDENCE_STACK["basic_memory"]
        if self.provider_version != expected_version:
            problems.append(
                f"provider version {self.provider_version!r} is not the accepted "
                f"{expected_version!r}"
            )
        expected_model = FROZEN_EVIDENCE_STACK["embedding_model"]
        if self.embedding_model != expected_model:
            problems.append(
                f"embedding model {self.embedding_model!r} is not the accepted "
                f"{expected_model!r}"
            )
        if (
            self.similarity_threshold is not None
            and abs(self.similarity_threshold - PILOT_SIMILARITY_THRESHOLD) > 1e-9
        ):
            problems.append(
                f"similarity threshold {self.similarity_threshold!r} is not the "
                f"calibrated {PILOT_SIMILARITY_THRESHOLD!r}"
            )
        return tuple(problems)


@dataclass(frozen=True)
class CoverageReport:
    """OS manifest compared against provider-visible coverage.

    Two levels of evidence are distinguished, and only the stronger one can
    unlock semantic retrieval:

    * **cardinality** -- the provider reported *how many* entities it holds.
      This is what `bm project info --json` supplies. It proves nothing about
      *which* files those entities correspond to: two different sets of equal
      size reconcile identically, and a stale entity for a deleted file keeps
      the count whole while the index is wrong.
    * **exact membership** -- the provider enumerated the relative paths it has
      indexed, so the guard can compare sets rather than totals.

    `provider_paths is None` means the accepted provider interface did not
    expose membership. That is *unproven*, never "assume the counts agree", so
    `proven_complete` stays False and semantic retrieval stays blocked. See
    `MEMORY-INTEGRATION-FOUNDATION-1` step 2: Soma may not publish a stronger
    health claim than the provider evidence supports.
    """

    project_id: str
    provider_project: str
    os_eligible_files: int
    provider_entities: int | None
    pending_changes: int | None
    os_paths: tuple[str, ...] = ()
    provider_paths: tuple[str, ...] | None = None
    notes: tuple[str, ...] = ()

    @property
    def exact_membership_available(self) -> bool:
        """Whether the provider enumerated membership rather than a bare count."""
        return self.provider_paths is not None

    @property
    def missing_paths(self) -> tuple[str, ...]:
        """Canonical files the provider did not account for."""
        if self.provider_paths is None:
            return ()
        return tuple(sorted(set(self.os_paths) - set(self.provider_paths)))

    @property
    def extra_paths(self) -> tuple[str, ...]:
        """Provider entities with no canonical file -- stale or foreign."""
        if self.provider_paths is None:
            return ()
        return tuple(sorted(set(self.provider_paths) - set(self.os_paths)))

    @property
    def cardinality_agrees(self) -> bool:
        """Counts match exactly. Necessary, never sufficient."""
        if self.provider_entities is None:
            return False
        return self.provider_entities == self.os_eligible_files

    @property
    def proven_complete(self) -> bool:
        if self.provider_entities is None:
            return False
        if self.pending_changes is None or self.pending_changes > 0:
            return False
        # Cardinality alone is not proof. Without membership evidence the guard
        # reports unproven and semantic retrieval stays blocked.
        if self.provider_paths is None:
            return False
        if self.missing_paths or self.extra_paths:
            return False
        return self.cardinality_agrees

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "provider_project": self.provider_project,
            "os_eligible_files": self.os_eligible_files,
            "provider_entities": self.provider_entities,
            "pending_changes": self.pending_changes,
            "exact_membership_available": self.exact_membership_available,
            "cardinality_agrees": self.cardinality_agrees,
            "missing_paths": list(self.missing_paths),
            "extra_paths": list(self.extra_paths),
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
