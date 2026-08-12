"""G6.1 frozen canonical-concurrency benchmark materialization tests."""

from __future__ import annotations

import json
from pathlib import Path

from soma.agent_worker_benchmark import (
    ASSIGNMENT_SCHEMA_VERSION,
    FROZEN_RESEARCH_CORPUS_HASH,
    G6_WORK_PACKAGE_CONTRACT_VERSION,
    SOURCE_COMMIT,
    UNITS,
    assignment_packet_hash,
    build_assignment_packet,
    build_g6_plan_graph_manifest,
    build_work_package_contract,
    materialization_manifest_hash,
    source_manifest,
    verify_frozen_sources,
    work_package_contract_materials,
)
from soma.company_kernel.models import work_package_contract_hash


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frozen_unit_shape_is_exactly_eight_units_and_twenty_one_sources() -> None:
    assert [unit.unit_id for unit in UNITS] == [
        f"B{index:02d}" for index in range(1, 9)
    ]
    assert len({unit.lane_id for unit in UNITS}) == 8
    assert sum(len(unit.sources) for unit in UNITS) == 21
    assert all(len(unit.questions) == 5 for unit in UNITS)
    assert all(unit.critical_trap for unit in UNITS)
    assert all(unit.expected_trap_disposition for unit in UNITS)


def test_materialization_manifest_preserves_research_identity_without_inventing_hash_recipe() -> (
    None
):
    manifest = source_manifest()

    assert manifest["research_identity"]["source_commit"] == SOURCE_COMMIT
    assert (
        manifest["research_identity"]["frozen_research_corpus_hash"]
        == FROZEN_RESEARCH_CORPUS_HASH
    )
    assert (
        manifest["research_identity"]["research_hash_serialization_recorded"] is False
    )
    assert len(materialization_manifest_hash()) == 64


def test_every_frozen_git_blob_matches_iteration_five_hash() -> None:
    result = verify_frozen_sources(REPO_ROOT)

    assert result["ok"] is True
    assert result["source_commit"] == SOURCE_COMMIT
    assert result["frozen_research_corpus_hash"] == FROZEN_RESEARCH_CORPUS_HASH
    assert result["unit_count"] == 8
    assert result["source_count"] == 21
    assert len(result["verified_sources"]) == 21
    assert all(item["bytes"] > 0 for item in result["verified_sources"])


def test_assignment_packet_is_byte_stable_and_contains_only_frozen_source_bytes() -> (
    None
):
    first = build_assignment_packet(REPO_ROOT, "B01")
    second = build_assignment_packet(REPO_ROOT, "B01")

    assert first == second
    assert assignment_packet_hash(REPO_ROOT, "B01") == assignment_packet_hash(
        REPO_ROOT, "B01"
    )

    packet = json.loads(first)
    assert packet["schema_version"] == ASSIGNMENT_SCHEMA_VERSION
    assert packet["corpus"]["source_commit"] == SOURCE_COMMIT
    assert packet["unit"]["unit_id"] == "B01"
    assert [question["fact_key"] for question in packet["rubric"]["questions"]] == [
        "task.canonical_state_owner",
        "task.current_task_kind_set",
        "task.current_backend_kind_set",
        "task.result_body_policy",
        "task.backend_protocol_shape",
    ]
    assert [source["path"] for source in packet["sources"]] == [
        "soma/tasks/models.py",
        "soma/tasks/backends.py",
        "soma/tasks/projections.py",
    ]
    assert all(source["content"] for source in packet["sources"])


def test_all_assignment_packets_are_distinct_but_repeatable() -> None:
    first_pass = {
        unit.unit_id: assignment_packet_hash(REPO_ROOT, unit.unit_id) for unit in UNITS
    }
    second_pass = {
        unit.unit_id: assignment_packet_hash(REPO_ROOT, unit.unit_id) for unit in UNITS
    }

    assert first_pass == second_pass
    assert len(set(first_pass.values())) == 8


def test_work_package_contracts_freeze_packet_identity_without_route_facts() -> None:
    materials = work_package_contract_materials(REPO_ROOT)

    assert list(materials) == [unit.unit_id for unit in UNITS]
    hashes = []
    for unit in UNITS:
        material = materials[unit.unit_id]
        contract = material.contract
        assert material.contract_version == G6_WORK_PACKAGE_CONTRACT_VERSION
        assert contract == build_work_package_contract(REPO_ROOT, unit.unit_id)
        assert contract["benchmark"]["unit_id"] == unit.unit_id
        assert contract["benchmark"]["assignment_packet_sha256"] == assignment_packet_hash(
            REPO_ROOT, unit.unit_id
        )
        serialized = json.dumps(contract, sort_keys=True).lower()
        for forbidden in (
            '"provider"',
            '"model"',
            '"backend_ref"',
            '"task_id"',
            '"run_id"',
            '"session_id"',
        ):
            assert forbidden not in serialized
        hashes.append(
            work_package_contract_hash(
                contract_version=material.contract_version,
                contract=contract,
            )
        )
    assert len(set(hashes)) == 8


def test_g6_graph_is_eight_independent_route_neutral_nodes() -> None:
    manifest = build_g6_plan_graph_manifest(
        REPO_ROOT,
        mission_id="mission_" + "a" * 24,
        project_id="project_benchmark",
        resource_id="resource_benchmark",
        scope_generation=1,
    )

    assert [node.package_key for node in manifest.package_nodes] == [
        unit.unit_id for unit in UNITS
    ]
    assert manifest.dependency_edges == ()
    assert all(
        node.target_resource_id == "resource_benchmark"
        for node in manifest.package_nodes
    )
    assert len(manifest.graph_manifest_hash) == 64
