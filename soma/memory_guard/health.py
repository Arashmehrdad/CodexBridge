"""Completeness accounting: the OS Markdown manifest is the authority.

The pilot's decisive lesson is that a provider's own "ok" is not evidence. Health
is established by reconciling the canonical filesystem against provider-visible
coverage, and by known-hit probes -- never by a status field alone, and never by
a low-scoring result being returned at all.
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    CoverageReport,
    HealthDisposition,
    HealthState,
    ProviderBinding,
    RefusalReason,
)
from .provider import BasicMemoryProvider, ProviderCall


#: Directories never counted as canonical content.
EXCLUDED_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {".git", ".obsidian", ".basic-memory", ".trash", "node_modules", "__pycache__"}
)


def os_manifest(root: str | Path) -> tuple[str, ...]:
    """Every eligible canonical Markdown file under the bound root."""
    base = Path(root).expanduser()
    if not base.is_dir():
        return ()
    found: list[str] = []
    for path in base.rglob("*.md"):
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in path.relative_to(base).parts):
            continue
        if not path.is_file():
            continue
        found.append(path.relative_to(base).as_posix())
    return tuple(sorted(found))


def _entity_count(payload: dict | None) -> int | None:
    """Read a provider entity count, or None when the shape is not understood.

    Deliberately conservative: an unrecognised payload is unproven coverage, not
    zero and not complete.
    """
    if not isinstance(payload, dict):
        return None
    for key in ("entity_count", "entities", "note_count", "notes", "total_entities"):
        value = payload.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    statistics = payload.get("statistics")
    if isinstance(statistics, dict):
        return _entity_count(statistics)
    return None


def _pending_changes(payload: dict | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("total")
    if isinstance(total, int) and total >= 0:
        return total
    return None


def indexed_paths(payload: dict | None) -> tuple[str, ...] | None:
    """Relative paths the provider says it has indexed, or None when unknown.

    None is *unproven membership*, never "the provider indexed nothing". The
    accepted interface may not expose membership at all; see
    `MEMORY-INTEGRATION-FOUNDATION-1` step 2. Until it is measured, coverage
    stays unproven and semantic retrieval stays blocked.
    """
    if not isinstance(payload, dict):
        return None
    for key in ("entities", "notes", "files", "results", "documents"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        found: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            raw = (
                row.get("file_path")
                or row.get("path")
                or row.get("relative_path")
                or row.get("file")
            )
            if not isinstance(raw, str) or not raw:
                return None
            found.append(str(raw).replace("\\", "/").lstrip("./"))
        return tuple(sorted(found))
    return None


def build_coverage(
    binding: ProviderBinding,
    *,
    info_call: ProviderCall | None,
    status_call: ProviderCall | None,
    membership_call: ProviderCall | None = None,
) -> CoverageReport:
    """Reconcile the OS manifest against provider-reported coverage.

    `membership_call` carries a provider response that enumerates indexed paths.
    When it is absent or unrecognised, coverage records cardinality only and
    `proven_complete` stays False -- counts alone cannot distinguish two
    equal-sized but different sets, nor a stale entity for a deleted file.
    """
    files = os_manifest(binding.canonical_root)
    notes: list[str] = []

    info_payload = (
        BasicMemoryProvider.parse_json(info_call) if info_call is not None else None
    )
    entities = _entity_count(info_payload)
    if entities is None:
        notes.append(
            "provider did not report an entity count in a recognised shape; "
            "coverage treated as unproven"
        )

    status_payload = (
        BasicMemoryProvider.parse_json(status_call) if status_call is not None else None
    )
    pending = _pending_changes(status_payload)
    if pending is None:
        notes.append("provider did not report pending changes; treated as unproven")

    membership_payload = (
        BasicMemoryProvider.parse_json(membership_call)
        if membership_call is not None
        else None
    )
    provider_paths = indexed_paths(membership_payload)
    if provider_paths is None:
        notes.append(
            "provider did not enumerate indexed paths; membership is unproven and "
            "cardinality alone cannot establish exact coverage"
        )

    return CoverageReport(
        project_id=binding.project_id,
        provider_project=binding.provider_project,
        os_eligible_files=len(files),
        provider_entities=entities,
        pending_changes=pending,
        os_paths=files,
        provider_paths=provider_paths,
        notes=tuple(notes),
    )


def disposition(
    coverage: CoverageReport,
    *,
    rebuilding: bool = False,
    runtime_mismatch: str = "",
) -> HealthDisposition:
    """Publish health honestly. Only proven-complete coverage is HEALTHY."""
    if runtime_mismatch:
        return HealthDisposition(
            state=HealthState.INCOMPATIBLE,
            coverage=coverage,
            reason=RefusalReason.RUNTIME_MISMATCH,
            detail=runtime_mismatch,
        )

    if rebuilding:
        return HealthDisposition(
            state=HealthState.REBUILDING,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_UNPROVEN,
            detail="a rebuild is in progress; semantic retrieval is blocked",
        )

    if coverage.os_eligible_files == 0 and coverage.provider_entities in (0, None):
        return HealthDisposition(
            state=HealthState.UNAVAILABLE,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_UNPROVEN,
            detail="no canonical Markdown found under the bound root",
        )

    if coverage.provider_entities is None or coverage.pending_changes is None:
        return HealthDisposition(
            state=HealthState.DEGRADED,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_UNPROVEN,
            detail="; ".join(coverage.notes) or "provider coverage is unproven",
        )

    if coverage.pending_changes > 0:
        return HealthDisposition(
            state=HealthState.REBUILDING,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_INCOMPLETE,
            detail=(
                f"{coverage.pending_changes} pending change(s) not yet indexed"
            ),
        )

    if coverage.provider_entities < coverage.os_eligible_files:
        return HealthDisposition(
            state=HealthState.DEGRADED,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_INCOMPLETE,
            detail=(
                f"provider covers {coverage.provider_entities} of "
                f"{coverage.os_eligible_files} canonical files"
            ),
        )

    if not coverage.exact_membership_available:
        return HealthDisposition(
            state=HealthState.DEGRADED,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_MEMBERSHIP_UNAVAILABLE,
            detail=(
                f"counts agree at {coverage.os_eligible_files}, but the provider "
                "did not enumerate which files it indexed; equal totals do not "
                "prove equal sets, so semantic retrieval stays blocked"
            ),
        )

    if coverage.missing_paths:
        return HealthDisposition(
            state=HealthState.DEGRADED,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_INCOMPLETE,
            detail=(
                f"{len(coverage.missing_paths)} canonical file(s) absent from the "
                f"index, first: {coverage.missing_paths[0]!r}"
            ),
        )

    if coverage.extra_paths:
        return HealthDisposition(
            state=HealthState.DEGRADED,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_STALE_ENTITIES,
            detail=(
                f"{len(coverage.extra_paths)} indexed entit(y/ies) have no canonical "
                f"file, first: {coverage.extra_paths[0]!r}"
            ),
        )

    if not coverage.cardinality_agrees:
        return HealthDisposition(
            state=HealthState.DEGRADED,
            coverage=coverage,
            reason=RefusalReason.COVERAGE_INCOMPLETE,
            detail=(
                f"provider reports {coverage.provider_entities} entities for "
                f"{coverage.os_eligible_files} canonical files"
            ),
        )

    return HealthDisposition(state=HealthState.HEALTHY, coverage=coverage)
