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


def build_coverage(
    binding: ProviderBinding,
    *,
    info_call: ProviderCall | None,
    status_call: ProviderCall | None,
) -> CoverageReport:
    """Reconcile the OS manifest against provider-reported coverage."""
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

    return CoverageReport(
        project_id=binding.project_id,
        provider_project=binding.provider_project,
        os_eligible_files=len(files),
        provider_entities=entities,
        pending_changes=pending,
        notes=tuple(notes),
    )


def disposition(
    coverage: CoverageReport, *, rebuilding: bool = False
) -> HealthDisposition:
    """Publish health honestly. Only proven-complete coverage is HEALTHY."""
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

    return HealthDisposition(state=HealthState.HEALTHY, coverage=coverage)
