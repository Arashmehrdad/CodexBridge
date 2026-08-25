from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_json_sha256
from .coverage import CoverageSummary
from .models import (
    PREDICATE_REGISTRY_VERSION,
    RESEARCH_MAP_SCHEMA_VERSION,
    ProjectManifest,
    RelationLifecycle,
    ResearchMapRelation,
)
from .sidecars import ResearchMapIssue, SidecarScanResult, SidecarState

DESIRED_STATE_SCHEMA_VERSION = "soma.research-map.desired-state.v1"


@dataclass(frozen=True, slots=True)
class EffectiveRelation:
    relation_id: str
    source_path: str
    declared_lifecycle: RelationLifecycle
    effective_lifecycle: RelationLifecycle
    superseded_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GovernanceAnalysis:
    relations: tuple[EffectiveRelation, ...]
    issues: tuple[ResearchMapIssue, ...]


@dataclass(frozen=True, slots=True)
class DesiredStateResult:
    semantic_desired_state_sha256: str
    governance: GovernanceAnalysis
    payload: dict[str, object]


def _eligible_relations(
    scan: SidecarScanResult,
) -> list[tuple[str, ResearchMapRelation]]:
    relations: list[tuple[str, ResearchMapRelation]] = []
    for record in scan.records:
        if record.sidecar_state is not SidecarState.VALID or record.sidecar is None:
            continue
        for relation in record.sidecar.relations:
            relations.append((record.source_path, relation))
    relations.sort(key=lambda item: (item[1].relation_id, item[0]))
    return relations


def analyze_governance(scan: SidecarScanResult) -> GovernanceAnalysis:
    relation_map: dict[str, tuple[str, ResearchMapRelation]] = {}
    issues: list[ResearchMapIssue] = []

    for source_path, relation in _eligible_relations(scan):
        if relation.relation_id in relation_map:
            issues.append(
                ResearchMapIssue(
                    code="duplicate_relation_id",
                    source_path=source_path,
                    relation_id=relation.relation_id,
                )
            )
            continue
        relation_map[relation.relation_id] = (source_path, relation)

    successors_by_target: dict[str, list[str]] = {}
    edges: dict[str, list[str]] = {relation_id: [] for relation_id in relation_map}
    for successor_id, (source_path, relation) in sorted(relation_map.items()):
        for target_id in sorted(relation.supersedes):
            if target_id not in relation_map:
                issues.append(
                    ResearchMapIssue(
                        code="dangling_supersedes",
                        source_path=source_path,
                        relation_id=successor_id,
                    )
                )
                continue
            successors_by_target.setdefault(target_id, []).append(successor_id)
            edges[successor_id].append(target_id)

    visit_state: dict[str, int] = {}
    stack: list[str] = []
    cycle_nodes: set[str] = set()

    def visit(node: str) -> None:
        visit_state[node] = 1
        stack.append(node)
        for target in sorted(edges.get(node, ())):
            state = visit_state.get(target, 0)
            if state == 0:
                visit(target)
            elif state == 1:
                try:
                    start = stack.index(target)
                except ValueError:
                    start = 0
                cycle_nodes.update(stack[start:])
        stack.pop()
        visit_state[node] = 2

    for relation_id in sorted(relation_map):
        if visit_state.get(relation_id, 0) == 0:
            visit(relation_id)

    for relation_id in sorted(cycle_nodes):
        source_path, _ = relation_map[relation_id]
        issues.append(
            ResearchMapIssue(
                code="supersession_cycle",
                source_path=source_path,
                relation_id=relation_id,
            )
        )

    effective: list[EffectiveRelation] = []
    for relation_id, (source_path, relation) in sorted(relation_map.items()):
        successors = tuple(sorted(successors_by_target.get(relation_id, ())))
        lifecycle = relation.lifecycle
        if lifecycle is RelationLifecycle.CURRENT and successors:
            lifecycle = RelationLifecycle.SUPERSEDED
        effective.append(
            EffectiveRelation(
                relation_id=relation_id,
                source_path=source_path,
                declared_lifecycle=relation.lifecycle,
                effective_lifecycle=lifecycle,
                superseded_by=successors,
            )
        )

    unique_issues = tuple(sorted(set(issues), key=ResearchMapIssue.sort_key))
    return GovernanceAnalysis(relations=tuple(effective), issues=unique_issues)


def _normalized_research_map(manifest: ProjectManifest) -> dict[str, object]:
    roots = [
        {
            "path": root.path,
            "sidecar_dir": root.sidecar_dir,
            "include": sorted(root.include),
        }
        for root in manifest.research_map.roots
    ]
    roots.sort(key=lambda item: (str(item["path"]), str(item["sidecar_dir"])))
    return {
        "enabled": manifest.research_map.enabled,
        "schema": manifest.research_map.schema_name,
        "roots": roots,
    }


def _issue_payload(issue: ResearchMapIssue) -> dict[str, str]:
    payload = {"code": issue.code}
    if issue.source_path:
        payload["source_path"] = issue.source_path
    if issue.sidecar_path:
        payload["sidecar_path"] = issue.sidecar_path
    if issue.relation_id:
        payload["relation_id"] = issue.relation_id
    return payload


def build_desired_state(
    manifest: ProjectManifest,
    scan: SidecarScanResult,
    coverage: CoverageSummary,
) -> DesiredStateResult:
    """Build a backend-independent deterministic semantic desired-state identity."""
    coverage_by_source = {entry.source_path: entry for entry in coverage.entries}
    governance = analyze_governance(scan)

    records: list[dict[str, object]] = []
    for record in sorted(
        scan.records,
        key=lambda item: (item.source_path, item.expected_sidecar_path),
    ):
        coverage_entry = coverage_by_source[record.source_path]
        item: dict[str, object] = {
            "root_path": record.root_path,
            "source_path": record.source_path,
            "logical_record_id": record.logical_record_id,
            "source_exists": record.source_exists,
            "canonical_text_sha256": record.canonical_text_sha256,
            "expected_sidecar_path": record.expected_sidecar_path,
            "sidecar_state": record.sidecar_state.value,
            "coverage_state": coverage_entry.state.value,
            "canonical_sidecar_sha256": record.canonical_sidecar_sha256,
        }
        if record.sidecar is not None:
            item["sidecar"] = record.sidecar.model_dump(
                mode="json",
                exclude_none=True,
                by_alias=True,
            )
        elif record.malformed_sidecar_raw_sha256 is not None:
            item["malformed_sidecar_raw_sha256"] = record.malformed_sidecar_raw_sha256
        records.append(item)

    relation_states = [
        {
            "relation_id": relation.relation_id,
            "source_path": relation.source_path,
            "declared_lifecycle": relation.declared_lifecycle.value,
            "effective_lifecycle": relation.effective_lifecycle.value,
            "superseded_by": list(relation.superseded_by),
        }
        for relation in governance.relations
    ]

    all_issues = tuple(
        sorted(
            set(scan.issues) | set(governance.issues),
            key=ResearchMapIssue.sort_key,
        )
    )
    payload: dict[str, object] = {
        "schema": DESIRED_STATE_SCHEMA_VERSION,
        "repository_uid": manifest.repository_uid,
        "research_map_schema_version": RESEARCH_MAP_SCHEMA_VERSION,
        "predicate_registry_version": PREDICATE_REGISTRY_VERSION,
        "research_map": _normalized_research_map(manifest),
        "records": records,
        "governance": relation_states,
        "issues": [_issue_payload(issue) for issue in all_issues],
    }
    return DesiredStateResult(
        semantic_desired_state_sha256=canonical_json_sha256(payload),
        governance=governance,
        payload=payload,
    )
