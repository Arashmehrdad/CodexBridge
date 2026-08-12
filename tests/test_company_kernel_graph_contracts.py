"""G1.1 pure Company Kernel graph and dependency-proof contract tests."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from soma.company_kernel.graph_models import (
    DEPENDENCY_EDGE_ID_DOMAIN,
    DEPENDENCY_PROOF_ID_DOMAIN,
    DEPENDENCY_PROOF_SCHEMA_VERSION,
    MAX_DEPENDENCY_EDGES_PER_PLAN_GRAPH,
    MAX_PACKAGES_PER_PLAN_GRAPH,
    PLAN_GRAPH_ID_DOMAIN,
    PLAN_GRAPH_SCHEMA_VERSION,
    AcceptedOutcomeSatisfactionV1,
    DependencySatisfactionProofV1,
    EvidenceAvailableSatisfactionV1,
    PlanGraphDependencyEdgeV1,
    PlanGraphManifestV1,
    PlanGraphNodeV1,
    PublishedSuccessSatisfactionV1,
    SettledSatisfactionV1,
)


MISSION_ID = "mission_" + "1" * 24
UPSTREAM_PACKAGE_ID = "workpkg_" + "2" * 24
DOWNSTREAM_PACKAGE_ID = "workpkg_" + "3" * 24
UPSTREAM_OUTCOME_ID = "outcome_" + "4" * 24
ATTEMPT_ID = "wpattempt_" + "5" * 24
ACCEPTANCE_ID = "accept_" + "6" * 24
PROJECT_ID = "project_graph_fixture"
RESOURCE_ID = "resource_graph_fixture"
EDGE_ID = "dependency-edge-fixture"
NOW = "2026-08-12T00:00:00+00:00"


def _hash(character: str) -> str:
    return character * 64


def _node(
    package_key: str, *, target_resource_id: str = RESOURCE_ID
) -> PlanGraphNodeV1:
    marker = format((sum(package_key.encode("utf-8")) % 15) + 1, "x")
    return PlanGraphNodeV1(
        package_key=package_key,
        work_package_contract_hash=_hash(marker),
        target_resource_id=target_resource_id,
    )


def _edge(
    upstream: str,
    downstream: str,
    requirement: str = "accepted_outcome",
    *,
    selector_ref: str | None = None,
    selector_hash: str | None = None,
) -> PlanGraphDependencyEdgeV1:
    return PlanGraphDependencyEdgeV1(
        upstream_package_key=upstream,
        downstream_package_key=downstream,
        requirement=requirement,
        evidence_selector_ref=selector_ref,
        evidence_selector_hash=selector_hash,
    )


def _manifest(
    *,
    nodes: list[PlanGraphNodeV1] | tuple[PlanGraphNodeV1, ...] | None = None,
    edges: list[PlanGraphDependencyEdgeV1]
    | tuple[PlanGraphDependencyEdgeV1, ...]
    | None = None,
) -> PlanGraphManifestV1:
    return PlanGraphManifestV1(
        mission_id=MISSION_ID,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        package_nodes=nodes if nodes is not None else [_node("a"), _node("b")],
        dependency_edges=edges if edges is not None else [_edge("a", "b")],
    )


def _proof(
    satisfaction,
    *,
    requirement: str | None = None,
    observed_at: str = NOW,
    observed_kernel_state_version: int = 7,
) -> DependencySatisfactionProofV1:
    return DependencySatisfactionProofV1(
        edge_id=EDGE_ID,
        edge_hash=_hash("a"),
        requirement=requirement or satisfaction.kind,
        upstream_work_package_id=UPSTREAM_PACKAGE_ID,
        upstream_outcome_id=UPSTREAM_OUTCOME_ID,
        downstream_work_package_id=DOWNSTREAM_PACKAGE_ID,
        satisfaction=satisfaction,
        observed_kernel_state_version=observed_kernel_state_version,
        observed_at=observed_at,
    )


def test_frozen_contract_constants_are_exact() -> None:
    assert PLAN_GRAPH_SCHEMA_VERSION == "plan_graph_manifest.v1"
    assert DEPENDENCY_PROOF_SCHEMA_VERSION == "dependency_satisfaction_proof.v1"
    assert MAX_PACKAGES_PER_PLAN_GRAPH == 32
    assert MAX_DEPENDENCY_EDGES_PER_PLAN_GRAPH == 128
    assert PLAN_GRAPH_ID_DOMAIN == "soma.company_kernel.plan_graph.v1"
    assert DEPENDENCY_EDGE_ID_DOMAIN == "soma.company_kernel.dependency_edge.v1"
    assert DEPENDENCY_PROOF_ID_DOMAIN == "soma.company_kernel.dependency_proof.v1"


def test_forward_and_reversed_manifest_inputs_have_identical_graph_hash() -> None:
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [_edge("a", "b"), _edge("b", "c", "published_success")]

    forward = _manifest(nodes=nodes, edges=edges)
    reversed_input = _manifest(nodes=list(reversed(nodes)), edges=list(reversed(edges)))

    assert (
        forward.canonical_identity_payload()
        == reversed_input.canonical_identity_payload()
    )
    assert forward.graph_manifest_hash == reversed_input.graph_manifest_hash
    assert re.fullmatch(r"[0-9a-f]{64}", forward.graph_manifest_hash)


def test_cycle_is_rejected() -> None:
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "a")]

    with pytest.raises(ValidationError, match="acyclic"):
        _manifest(nodes=nodes, edges=edges)


def test_missing_dependency_endpoint_is_rejected() -> None:
    with pytest.raises(ValidationError, match="endpoint is missing"):
        _manifest(nodes=[_node("a"), _node("b")], edges=[_edge("a", "missing")])


def test_duplicate_package_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="package_keys must be unique"):
        _manifest(nodes=[_node("a"), _node("a")], edges=[])


def test_duplicate_canonical_edge_is_rejected() -> None:
    edge = _edge("a", "b")
    with pytest.raises(ValidationError, match="duplicate canonical dependency edge"):
        _manifest(edges=[edge, edge])


def test_selector_hash_is_the_canonical_edge_tiebreaker_and_duplicate_identity() -> (
    None
):
    first = _edge(
        "a",
        "b",
        "evidence_available",
        selector_ref="selector:first",
        selector_hash=_hash("b"),
    )
    same_selector_identity = _edge(
        "a",
        "b",
        "evidence_available",
        selector_ref="selector:second",
        selector_hash=_hash("b"),
    )

    with pytest.raises(ValidationError, match="duplicate canonical dependency edge"):
        _manifest(edges=[first, same_selector_identity])


def test_self_edge_is_rejected() -> None:
    with pytest.raises(ValidationError, match="same package"):
        _edge("a", "a")


def test_package_count_bound_is_enforced() -> None:
    nodes = [_node(f"p{index:02d}") for index in range(33)]
    with pytest.raises(ValidationError):
        _manifest(nodes=nodes, edges=[])


def test_edge_count_bound_is_enforced_before_unbounded_graph_validation() -> None:
    repeated = _edge("a", "b")
    with pytest.raises(ValidationError):
        _manifest(edges=[repeated] * 129)


def test_package_target_resource_cannot_escape_mission_ceiling() -> None:
    with pytest.raises(ValidationError, match="resource ceiling"):
        _manifest(nodes=[_node("a"), _node("b", target_resource_id="other-resource")])


def test_evidence_available_requires_exact_selector_ref_and_hash() -> None:
    valid = _edge(
        "a",
        "b",
        "evidence_available",
        selector_ref="selector:required-output",
        selector_hash=_hash("c"),
    )
    assert valid.evidence_selector_ref == "selector:required-output"
    assert re.fullmatch(r"[0-9a-f]{64}", valid.edge_hash)

    with pytest.raises(ValidationError, match="requires evidence_selector_ref"):
        _edge("a", "b", "evidence_available")


def test_non_evidence_requirement_cannot_carry_selector() -> None:
    with pytest.raises(ValidationError, match="only evidence_available"):
        _edge(
            "a",
            "b",
            "accepted_outcome",
            selector_ref="selector:forbidden",
            selector_hash=_hash("d"),
        )


def test_unknown_dependency_requirement_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _edge("a", "b", "not_a_requirement")


def test_route_specific_manifest_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanGraphNodeV1(
            package_key="a",
            work_package_contract_hash=_hash("e"),
            target_resource_id=RESOURCE_ID,
            provider="openai",
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlanGraphManifestV1(
            mission_id=MISSION_ID,
            project_id=PROJECT_ID,
            resource_id=RESOURCE_ID,
            scope_generation=1,
            package_nodes=[_node("a")],
            dependency_edges=[],
            task_id="task-route-leak",
        )


@pytest.mark.parametrize(
    ("requirement", "satisfaction"),
    [
        (
            "accepted_outcome",
            AcceptedOutcomeSatisfactionV1(
                acceptance_commit_id=ACCEPTANCE_ID,
                acceptance_commit_hash=_hash("1"),
            ),
        ),
        (
            "published_success",
            PublishedSuccessSatisfactionV1(
                attempt_id=ATTEMPT_ID,
                task_id="task_fixture",
                run_id="run_fixture",
                result_published_hash=_hash("2"),
                public_result_source_sha256=_hash("3"),
            ),
        ),
        (
            "evidence_available",
            EvidenceAvailableSatisfactionV1(
                evidence_ref="artifact:fixture",
                evidence_hash=_hash("4"),
                evidence_selector_hash=_hash("5"),
            ),
        ),
        (
            "settled",
            SettledSatisfactionV1(
                attempt_set_hash=_hash("6"),
                head_attempt_id=ATTEMPT_ID,
                settlement_ref="settlement:fixture",
                settlement_hash=_hash("7"),
                settlement_class="terminal",
            ),
        ),
    ],
)
def test_dependency_proof_tag_must_match_requirement(requirement, satisfaction) -> None:
    proof = _proof(satisfaction, requirement=requirement)
    assert proof.requirement == proof.satisfaction.kind
    assert re.fullmatch(r"[0-9a-f]{64}", proof.proof_hash)


def test_dependency_proof_tag_mismatch_is_rejected() -> None:
    satisfaction = EvidenceAvailableSatisfactionV1(
        evidence_ref="artifact:fixture",
        evidence_hash=_hash("8"),
        evidence_selector_hash=_hash("9"),
    )
    with pytest.raises(ValidationError, match="must match satisfaction kind"):
        _proof(satisfaction, requirement="accepted_outcome")


def test_observation_time_and_kernel_version_do_not_change_proof_hash() -> None:
    satisfaction = AcceptedOutcomeSatisfactionV1(
        acceptance_commit_id=ACCEPTANCE_ID,
        acceptance_commit_hash=_hash("a"),
    )
    first = _proof(
        satisfaction,
        observed_at="2026-08-12T00:00:00+00:00",
        observed_kernel_state_version=7,
    )
    later = _proof(
        satisfaction,
        observed_at="2026-08-12T01:00:00+00:00",
        observed_kernel_state_version=99,
    )

    assert first.proof_hash == later.proof_hash
    assert first.stable_identity_payload() == later.stable_identity_payload()


def test_satisfying_identity_change_changes_proof_hash() -> None:
    first = _proof(
        AcceptedOutcomeSatisfactionV1(
            acceptance_commit_id=ACCEPTANCE_ID,
            acceptance_commit_hash=_hash("b"),
        )
    )
    changed = _proof(
        AcceptedOutcomeSatisfactionV1(
            acceptance_commit_id=ACCEPTANCE_ID,
            acceptance_commit_hash=_hash("c"),
        )
    )

    assert first.proof_hash != changed.proof_hash


def test_explicit_incorrect_proof_hash_is_rejected() -> None:
    satisfaction = AcceptedOutcomeSatisfactionV1(
        acceptance_commit_id=ACCEPTANCE_ID,
        acceptance_commit_hash=_hash("d"),
    )
    valid = _proof(satisfaction)
    payload = valid.model_dump(mode="python")
    payload["proof_hash"] = _hash("f")

    with pytest.raises(ValidationError, match="proof_hash does not match"):
        DependencySatisfactionProofV1.model_validate(payload)


def test_settled_requires_attempt_set_hash() -> None:
    with pytest.raises(ValidationError):
        SettledSatisfactionV1(
            settlement_ref="settlement:fixture",
            settlement_hash=_hash("e"),
            settlement_class="terminal",
        )
