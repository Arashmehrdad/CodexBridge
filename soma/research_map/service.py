from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .coverage import CoverageSummary, classify_coverage
from .desired_state import DesiredStateResult, GovernanceAnalysis, build_desired_state
from .manifest import ManifestState, load_project_manifest
from .sidecars import ResearchMapIssue, SidecarScanResult, scan_research_sidecars


class ResearchMapHealthState(StrEnum):
    NOT_ADOPTED = "not_adopted"
    DISABLED = "disabled"
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ResearchMapScan:
    manifest_state: ManifestState
    health_state: ResearchMapHealthState
    repository_uid: str | None
    coverage: CoverageSummary
    sidecar_scan: SidecarScanResult
    desired_state: DesiredStateResult | None
    issues: tuple[ResearchMapIssue, ...]

    @property
    def semantic_desired_state_sha256(self) -> str | None:
        if self.desired_state is None:
            return None
        return self.desired_state.semantic_desired_state_sha256

    @property
    def governance(self) -> GovernanceAnalysis | None:
        if self.desired_state is None:
            return None
        return self.desired_state.governance


def _empty_coverage() -> CoverageSummary:
    return CoverageSummary(entries=())


def _empty_sidecar_scan() -> SidecarScanResult:
    return SidecarScanResult(records=(), issues=())


def scan_research_map(repository_root: str | Path) -> ResearchMapScan:
    """Scan one repository's tracked research-map state without DB or backend access."""
    manifest_result = load_project_manifest(repository_root)
    if manifest_result.state is ManifestState.MISSING:
        return ResearchMapScan(
            manifest_state=manifest_result.state,
            health_state=ResearchMapHealthState.NOT_ADOPTED,
            repository_uid=None,
            coverage=_empty_coverage(),
            sidecar_scan=_empty_sidecar_scan(),
            desired_state=None,
            issues=(),
        )

    if not manifest_result.valid or manifest_result.manifest is None:
        issue = ResearchMapIssue(
            code=manifest_result.error_code or "manifest_malformed",
            sidecar_path="soma.project.json",
        )
        return ResearchMapScan(
            manifest_state=manifest_result.state,
            health_state=ResearchMapHealthState.DEGRADED,
            repository_uid=None,
            coverage=_empty_coverage(),
            sidecar_scan=_empty_sidecar_scan(),
            desired_state=None,
            issues=(issue,),
        )

    manifest = manifest_result.manifest
    if not manifest.research_map.enabled:
        return ResearchMapScan(
            manifest_state=manifest_result.state,
            health_state=ResearchMapHealthState.DISABLED,
            repository_uid=manifest.repository_uid,
            coverage=_empty_coverage(),
            sidecar_scan=_empty_sidecar_scan(),
            desired_state=None,
            issues=(),
        )

    sidecar_scan = scan_research_sidecars(repository_root, manifest)
    coverage = classify_coverage(sidecar_scan)
    desired_state = build_desired_state(manifest, sidecar_scan, coverage)
    issues = tuple(
        sorted(
            set(sidecar_scan.issues) | set(desired_state.governance.issues),
            key=ResearchMapIssue.sort_key,
        )
    )
    health = (
        ResearchMapHealthState.DEGRADED
        if issues
        else ResearchMapHealthState.HEALTHY
    )
    return ResearchMapScan(
        manifest_state=manifest_result.state,
        health_state=health,
        repository_uid=manifest.repository_uid,
        coverage=coverage,
        sidecar_scan=sidecar_scan,
        desired_state=desired_state,
        issues=issues,
    )
