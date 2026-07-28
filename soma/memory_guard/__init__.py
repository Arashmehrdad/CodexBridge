"""Minimal Soma binding and health guard over a replaceable memory provider.

BASIC-MEMORY-GUARD-1. Soma owns exact project identity, routing, health
disposition, provenance and the public contract. Basic Memory owns only
disposable local parsing, embeddings and semantic retrieval.

This package implements no storage, embeddings, ranking, semantic search or graph
traversal, and never repairs or patches the provider.
"""

from .binding import ProjectBindingResolver, StaticBindingSource
from .fallback import literal_search, read_note, resolve_within_root
from .guard import BasicMemoryGuard, RebuildPlan
from .health import build_coverage, disposition, os_manifest
from .models import (
    FROZEN_EVIDENCE_STACK,
    GUARD_DECISION_ID,
    GUARD_MODEL_VERSION,
    PILOT_SIMILARITY_THRESHOLD,
    CoverageReport,
    GuardError,
    GuardResult,
    HealthDisposition,
    HealthRefused,
    HealthState,
    IdentityRefused,
    PathRefused,
    ProfileRefused,
    ProviderBinding,
    RefusalReason,
    ToolRefused,
)
from .profile import ProviderProfile, load_profile, validate_env, validate_profile
from .provider import ALLOWED_OPERATIONS, BasicMemoryProvider, ProviderCall

__all__ = [
    "ALLOWED_OPERATIONS",
    "FROZEN_EVIDENCE_STACK",
    "GUARD_DECISION_ID",
    "GUARD_MODEL_VERSION",
    "PILOT_SIMILARITY_THRESHOLD",
    "BasicMemoryGuard",
    "BasicMemoryProvider",
    "CoverageReport",
    "GuardError",
    "GuardResult",
    "HealthDisposition",
    "HealthRefused",
    "HealthState",
    "IdentityRefused",
    "PathRefused",
    "ProfileRefused",
    "ProjectBindingResolver",
    "ProviderBinding",
    "ProviderCall",
    "ProviderProfile",
    "RebuildPlan",
    "RefusalReason",
    "StaticBindingSource",
    "ToolRefused",
    "build_coverage",
    "disposition",
    "literal_search",
    "load_profile",
    "os_manifest",
    "read_note",
    "resolve_within_root",
    "validate_env",
    "validate_profile",
]
