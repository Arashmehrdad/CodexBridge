from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from .models import Materiality, ReviewState
from .sidecars import ScannedResearchRecord, SidecarScanResult, SidecarState


class CoverageState(StrEnum):
    REVIEWED_MATERIAL = "reviewed_material"
    REVIEWED_NO_MATERIAL = "reviewed_no_material"
    DEFERRED = "deferred"
    UNREVIEWED = "unreviewed"
    STALE = "stale"
    MISSING_SOURCE = "missing_source"


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    root_path: str
    source_path: str
    logical_record_id: str
    expected_sidecar_path: str
    state: CoverageState
    sidecar_state: SidecarState
    canonical_text_sha256: str | None
    canonical_sidecar_sha256: str | None


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    entries: tuple[CoverageEntry, ...]

    @property
    def total_count(self) -> int:
        return len(self.entries)

    @property
    def counts(self) -> dict[str, int]:
        counter = Counter(entry.state.value for entry in self.entries)
        return {state.value: counter.get(state.value, 0) for state in CoverageState}

    @property
    def reviewed_complete_count(self) -> int:
        return sum(
            1
            for entry in self.entries
            if entry.state
            in {CoverageState.REVIEWED_MATERIAL, CoverageState.REVIEWED_NO_MATERIAL}
        )

    @property
    def incomplete_count(self) -> int:
        return self.total_count - self.reviewed_complete_count

    @property
    def complete(self) -> bool:
        return self.total_count > 0 and self.incomplete_count == 0


def classify_record_coverage(record: ScannedResearchRecord) -> CoverageState:
    if record.sidecar_state is SidecarState.MISSING_SOURCE:
        return CoverageState.MISSING_SOURCE
    if record.sidecar_state in {
        SidecarState.STALE_HASH,
        SidecarState.INVALID_ANCHOR,
        SidecarState.SOURCE_INVALID,
        SidecarState.PATH_COLLISION,
    }:
        return CoverageState.STALE
    if record.sidecar_state is not SidecarState.VALID or record.sidecar is None:
        return CoverageState.UNREVIEWED

    review = record.sidecar.review
    if review.state is ReviewState.DEFERRED:
        return CoverageState.DEFERRED
    if review.materiality is Materiality.MATERIAL:
        return CoverageState.REVIEWED_MATERIAL
    if review.materiality is Materiality.NONE:
        return CoverageState.REVIEWED_NO_MATERIAL
    return CoverageState.UNREVIEWED


def classify_coverage(scan: SidecarScanResult) -> CoverageSummary:
    entries = [
        CoverageEntry(
            root_path=record.root_path,
            source_path=record.source_path,
            logical_record_id=record.logical_record_id,
            expected_sidecar_path=record.expected_sidecar_path,
            state=classify_record_coverage(record),
            sidecar_state=record.sidecar_state,
            canonical_text_sha256=record.canonical_text_sha256,
            canonical_sidecar_sha256=record.canonical_sidecar_sha256,
        )
        for record in scan.records
    ]
    entries.sort(key=lambda item: (item.source_path, item.expected_sidecar_path))
    return CoverageSummary(entries=tuple(entries))
