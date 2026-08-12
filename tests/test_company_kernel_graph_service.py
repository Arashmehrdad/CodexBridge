"""G1.3 atomic Company Kernel graph-acceptance service proofs.

All stores are disposable. These tests never launch a Task, Run, provider,
scheduler, gateway, or live Company Kernel capability.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import soma.company_kernel.service as service
from soma.company_kernel import MISSION_ID_DOMAIN, canonical_hash, canonical_json
from soma.company_kernel.graph_models import (
    PlanGraphDependencyEdgeV1,
    PlanGraphManifestV1,
    PlanGraphNodeV1,
)
from soma.company_kernel.service import (
    GraphAcceptanceConflict,
    GraphAcceptanceError,
    GraphAcceptanceIntegrityError,
    WorkPackageContractMaterialV1,
    accept_plan_graph,
)
from soma.company_kernel.store import CompanyKernelStore
from soma.company_kernel.models import work_package_contract_hash


COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PROJECT_ID = "project_graph_service"
RESOURCE_ID = "resource_graph_service"
OWNER = "owner-controller:arash"
NOW = "2026-08-12T04:00:00+00:00"


def _hash(character: str) -> str:
    return character * 64


def _prepare_store(tmp_path: Path) -> CompanyKernelStore:
    store = CompanyKernelStore(tmp_path / "runs")
    assert store.init_db() == [1, 2, 3]
    mission_contract = {"purpose": "prove graph acceptance"}
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO projects "
            "(project_id, project_key, lifecycle_state, scope_generation, created_at, updated_at) "
            "VALUES (?, 'graph-service', 'active', 1, ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO project_resources "
            "(resource_id, resource_kind, opaque_ref, identity_hash, created_at) "
            "VALUES (?, 'repository', 'd:/github/soma', ?, ?)",
            (RESOURCE_ID, _hash("a"), NOW),
        )
        conn.execute(
            "INSERT INTO project_resource_bindings "
            "(project_id, resource_id, access_mode, created_at) "
            "VALUES (?, ?, 'exclusive', ?)",
            (PROJECT_ID, RESOURCE_ID, NOW),
        )
        conn.execute(
            "INSERT INTO companies VALUES (?, 'soma-company', 'Soma Company', ?, ?, ?, ?)",
            (COMPANY_ID, OWNER, "create-company", _hash("b"), NOW),
        )
        conn.execute(
            """
            INSERT INTO missions(
                mission_id, company_id, mission_key, project_id, resource_id,
                scope_generation, mission_contract_json, mission_contract_hash,
                accountable_owner_ref, acceptance_authority_ref,
                current_plan_revision_id, plan_state_version, kernel_state_version,
                creation_request_id, creation_request_hash, created_at, updated_at
            ) VALUES (?, ?, 'graph-mission', ?, ?, 1, ?, ?, ?, ?, NULL, 0, 0, ?, ?, ?, ?)
            """,
            (
                MISSION_ID,
                COMPANY_ID,
                PROJECT_ID,
                RESOURCE_ID,
                canonical_json(mission_contract),
                canonical_hash(MISSION_ID_DOMAIN, mission_contract),
                OWNER,
                OWNER,
                "create-mission",
                _hash("c"),
                NOW,
                NOW,
            ),
        )
    return store


def _material(
    package_key: str,
    *,
    evidence: bool = False,
    variant: str = "base",
) -> WorkPackageContractMaterialV1:
    contract = {
        "purpose": f"package {package_key}",
        "variant": variant,
        "expected_output": f"evidence for {package_key}",
    }
    return WorkPackageContractMaterialV1(
        contract_version="v1",
        contract=contract,
        evidence_requirements_ref=(
            f"evidence-policy:{package_key}" if evidence else ""
        ),
        evidence_requirements_hash=(_hash("d") if evidence else ""),
    )


def _manifest_and_materials(
    *,
    reverse: bool = False,
    second_variant: str = "base",
    three_nodes: bool = False,
) -> tuple[PlanGraphManifestV1, dict[str, WorkPackageContractMaterialV1]]:
    materials = {
        "research": _material("research", evidence=True),
        "synthesis": _material("synthesis", variant=second_variant),
    }
    if three_nodes:
        materials["publish"] = _material("publish")

    nodes = [
        PlanGraphNodeV1(
            package_key=package_key,
            work_package_contract_hash=work_package_contract_hash(
                contract_version=material.contract_version,
                contract=material.contract,
            ),
            target_resource_id=RESOURCE_ID,
            evidence_requirements_hash=(material.evidence_requirements_hash or None),
        )
        for package_key, material in materials.items()
    ]
    edges = [
        PlanGraphDependencyEdgeV1(
            upstream_package_key="research",
            downstream_package_key="synthesis",
            requirement="evidence_available",
            evidence_selector_ref="selector:research-output",
            evidence_selector_hash=_hash("e"),
        )
    ]
    if three_nodes:
        edges.append(
            PlanGraphDependencyEdgeV1(
                upstream_package_key="synthesis",
                downstream_package_key="publish",
                requirement="accepted_outcome",
            )
        )
    if reverse:
        nodes = list(reversed(nodes))
        edges = list(reversed(edges))
    manifest = PlanGraphManifestV1(
        mission_id=MISSION_ID,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        package_nodes=nodes,
        dependency_edges=edges,
    )
    return manifest, materials


def _accept(
    store: CompanyKernelStore,
    *,
    controller_request_id: str = "graph-request-1",
    manifest: PlanGraphManifestV1 | None = None,
    materials: dict[str, WorkPackageContractMaterialV1] | None = None,
    expected_current_plan_revision_id: str | None = None,
    expected_plan_state_version: int = 0,
    expected_kernel_state_version: int = 0,
    plan_contract_base: dict | None = None,
    acceptance_basis_ref: str = "owner accepted graph",
    fault=None,
):
    if manifest is None or materials is None:
        manifest, materials = _manifest_and_materials()
    return accept_plan_graph(
        store,
        company_id=COMPANY_ID,
        mission_id=MISSION_ID,
        expected_current_plan_revision_id=expected_current_plan_revision_id,
        expected_plan_state_version=expected_plan_state_version,
        expected_kernel_state_version=expected_kernel_state_version,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        controller_request_id=controller_request_id,
        accepted_by_ref=OWNER,
        acceptance_basis_ref=acceptance_basis_ref,
        plan_contract_base=(
            {"purpose": "execute the accepted graph"}
            if plan_contract_base is None
            else plan_contract_base
        ),
        graph_manifest=manifest,
        work_package_contracts=materials,
        accepted_at=NOW,
        _fault_injector=fault,
    )


def _counts(store: CompanyKernelStore) -> dict[str, int]:
    with store.connect() as conn:
        return {
            name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
            for name in (
                "plan_revisions",
                "work_packages",
                "work_package_dependencies",
                "plan_graph_manifests",
                "tasks",
                "runs",
            )
        }


def _mission_state(store: CompanyKernelStore) -> tuple[str | None, int, int]:
    with store.connect() as conn:
        row = conn.execute(
            "SELECT current_plan_revision_id, plan_state_version, kernel_state_version "
            "FROM missions WHERE mission_id = ?",
            (MISSION_ID,),
        ).fetchone()
    return (
        str(row[0]) if row[0] is not None else None,
        int(row[1]),
        int(row[2]),
    )


def test_happy_acceptance_is_atomic_reconstructable_and_launch_free(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    manifest, materials = _manifest_and_materials()

    result = _accept(store, manifest=manifest, materials=materials)

    assert result.created is True
    assert result.replay_kind == "none"
    assert result.graph_manifest_hash == manifest.graph_manifest_hash
    assert set(result.package_ids) == {"research", "synthesis"}
    assert len(result.edge_ids) == 1
    assert _mission_state(store) == (result.plan_revision_id, 1, 1)
    assert _counts(store) == {
        "plan_revisions": 1,
        "work_packages": 2,
        "work_package_dependencies": 1,
        "plan_graph_manifests": 1,
        "tasks": 0,
        "runs": 0,
    }

    with store.connect() as conn:
        plan = conn.execute(
            "SELECT plan_contract_json FROM plan_revisions WHERE plan_revision_id = ?",
            (result.plan_revision_id,),
        ).fetchone()
        contract = __import__("json").loads(plan[0])
        assert contract["plan_graph"] == {
            "schema_version": "plan_graph_manifest.v1",
            "manifest_hash": manifest.graph_manifest_hash,
        }
        package = conn.execute(
            "SELECT evidence_requirements_ref, evidence_requirements_hash "
            "FROM work_packages WHERE package_key = 'research'",
        ).fetchone()
        assert tuple(package) == ("evidence-policy:research", _hash("d"))
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_exact_request_replay_returns_same_graph_without_new_rows(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    first = _accept(store)
    before = _counts(store)

    replay = _accept(store)

    assert replay.created is False
    assert replay.replay_kind == "request"
    assert replay.plan_revision_id == first.plan_revision_id
    assert replay.graph_manifest_hash == first.graph_manifest_hash
    assert replay.request_hash == first.request_hash
    assert _counts(store) == before
    assert _mission_state(store) == (first.plan_revision_id, 1, 1)


def test_same_request_id_with_different_graph_fails_closed(tmp_path: Path) -> None:
    store = _prepare_store(tmp_path)
    first = _accept(store)
    changed_manifest, changed_materials = _manifest_and_materials(
        second_variant="changed"
    )

    with pytest.raises(GraphAcceptanceConflict, match="already used"):
        _accept(
            store,
            manifest=changed_manifest,
            materials=changed_materials,
        )

    assert _counts(store)["plan_revisions"] == 1
    assert _mission_state(store) == (first.plan_revision_id, 1, 1)


def test_reordered_identical_graph_converges_by_content(tmp_path: Path) -> None:
    store = _prepare_store(tmp_path)
    first_manifest, first_materials = _manifest_and_materials()
    first = _accept(store, manifest=first_manifest, materials=first_materials)
    reversed_manifest, reversed_materials = _manifest_and_materials(reverse=True)
    assert reversed_manifest.graph_manifest_hash == first_manifest.graph_manifest_hash

    replay = _accept(
        store,
        controller_request_id="graph-request-content-replay",
        manifest=reversed_manifest,
        materials=reversed_materials,
    )

    assert replay.created is False
    assert replay.replay_kind == "content"
    assert replay.plan_revision_id == first.plan_revision_id
    assert _counts(store)["plan_revisions"] == 1


def test_content_replay_with_changed_request_metadata_fails_closed(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    first = _accept(store)

    with pytest.raises(GraphAcceptanceConflict, match="different request metadata"):
        _accept(
            store,
            controller_request_id="graph-request-different-metadata",
            acceptance_basis_ref="different owner basis",
        )

    assert _counts(store)["plan_revisions"] == 1
    assert _mission_state(store) == (first.plan_revision_id, 1, 1)


def test_reserved_plan_graph_and_route_specific_contracts_are_rejected(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    manifest, materials = _manifest_and_materials()

    with pytest.raises(GraphAcceptanceError, match="may not pre-populate plan_graph"):
        _accept(
            store,
            manifest=manifest,
            materials=materials,
            plan_contract_base={"plan_graph": {"manifest_hash": _hash("f")}},
        )

    bad_materials = dict(materials)
    bad_materials["synthesis"] = {
        "contract_version": "v1",
        "contract": {"purpose": "bad", "provider": "openai"},
    }
    with pytest.raises(GraphAcceptanceError, match="route-specific"):
        _accept(store, manifest=manifest, materials=bad_materials)

    assert _counts(store)["plan_revisions"] == 0


def test_manifest_and_package_evidence_hash_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    manifest, materials = _manifest_and_materials()
    bad_materials = dict(materials)
    bad_materials["research"] = WorkPackageContractMaterialV1(
        contract_version=materials["research"].contract_version,
        contract=materials["research"].contract,
        evidence_requirements_ref="evidence-policy:research",
        evidence_requirements_hash=_hash("9"),
    )

    with pytest.raises(GraphAcceptanceConflict, match="evidence requirements hash"):
        _accept(store, manifest=manifest, materials=bad_materials)

    assert _counts(store)["plan_revisions"] == 0


@pytest.mark.parametrize(
    "phase", ["after_plan_insert", "after_package:0", "after_mission_cas"]
)
def test_faults_inside_acceptance_transaction_roll_back_everything(
    tmp_path: Path,
    phase: str,
) -> None:
    store = _prepare_store(tmp_path)

    def fault(observed_phase: str, _conn: sqlite3.Connection) -> None:
        if observed_phase == phase:
            raise RuntimeError(f"fault:{phase}")

    with pytest.raises(RuntimeError, match="fault:"):
        _accept(store, fault=fault)

    assert _counts(store) == {
        "plan_revisions": 0,
        "work_packages": 0,
        "work_package_dependencies": 0,
        "plan_graph_manifests": 0,
        "tasks": 0,
        "runs": 0,
    }
    assert _mission_state(store) == (None, 0, 0)


def test_partial_edge_insert_fault_rolls_back_complete_graph(tmp_path: Path) -> None:
    store = _prepare_store(tmp_path)
    manifest, materials = _manifest_and_materials(three_nodes=True)

    def fault(phase: str, _conn: sqlite3.Connection) -> None:
        if phase == "after_edge:0":
            raise RuntimeError("partial-edge")

    with pytest.raises(RuntimeError, match="partial-edge"):
        _accept(store, manifest=manifest, materials=materials, fault=fault)

    assert _counts(store)["work_package_dependencies"] == 0
    assert _counts(store)["work_packages"] == 0
    assert _counts(store)["plan_revisions"] == 0
    assert _mission_state(store) == (None, 0, 0)


def test_reconstruction_hash_mismatch_rolls_back(tmp_path: Path, monkeypatch) -> None:
    store = _prepare_store(tmp_path)
    manifest, materials = _manifest_and_materials()
    original = service._reconstruct_manifest

    def mismatched(conn, *, mission_row, plan_revision_id):
        rebuilt = original(
            conn,
            mission_row=mission_row,
            plan_revision_id=plan_revision_id,
        )
        altered_material = _material("unexpected")
        return PlanGraphManifestV1(
            mission_id=rebuilt.mission_id,
            project_id=rebuilt.project_id,
            resource_id=rebuilt.resource_id,
            scope_generation=rebuilt.scope_generation,
            package_nodes=[
                *rebuilt.package_nodes,
                PlanGraphNodeV1(
                    package_key="unexpected",
                    work_package_contract_hash=work_package_contract_hash(
                        contract_version=altered_material.contract_version,
                        contract=altered_material.contract,
                    ),
                    target_resource_id=RESOURCE_ID,
                ),
            ],
            dependency_edges=rebuilt.dependency_edges,
        )

    monkeypatch.setattr(service, "_reconstruct_manifest", mismatched)
    with pytest.raises(GraphAcceptanceIntegrityError, match="reconstruction hash"):
        _accept(store, manifest=manifest, materials=materials)

    assert _counts(store)["plan_revisions"] == 0
    assert _mission_state(store) == (None, 0, 0)


def test_mission_cas_race_rolls_back_candidate_graph(tmp_path: Path) -> None:
    store = _prepare_store(tmp_path)

    def race(phase: str, conn: sqlite3.Connection) -> None:
        if phase == "before_mission_cas":
            conn.execute(
                "UPDATE missions SET plan_state_version = plan_state_version + 1 "
                "WHERE mission_id = ?",
                (MISSION_ID,),
            )

    with pytest.raises(GraphAcceptanceConflict, match="CAS lost race"):
        _accept(store, fault=race)

    assert _counts(store)["plan_revisions"] == 0
    assert _mission_state(store) == (None, 0, 0)


def test_project_scope_generation_change_before_acceptance_rejects(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET scope_generation = 2 WHERE project_id = ?",
            (PROJECT_ID,),
        )

    with pytest.raises(GraphAcceptanceConflict, match="generation changed"):
        _accept(store)

    assert _counts(store)["plan_revisions"] == 0
    assert _mission_state(store) == (None, 0, 0)


def test_scope_change_after_commit_preserves_history_and_exact_replay(
    tmp_path: Path,
) -> None:
    store = _prepare_store(tmp_path)
    first = _accept(store)
    before = _counts(store)
    with store.connect() as conn:
        conn.execute(
            "UPDATE projects SET scope_generation = 2 WHERE project_id = ?",
            (PROJECT_ID,),
        )

    replay = _accept(store)
    assert replay.replay_kind == "request"
    assert replay.plan_revision_id == first.plan_revision_id
    assert _counts(store) == before

    changed_manifest, changed_materials = _manifest_and_materials(
        second_variant="new-after-scope-change"
    )
    with pytest.raises(GraphAcceptanceConflict, match="generation changed"):
        _accept(
            store,
            controller_request_id="new-request-after-scope-change",
            manifest=changed_manifest,
            materials=changed_materials,
            expected_current_plan_revision_id=first.plan_revision_id,
            expected_plan_state_version=1,
            expected_kernel_state_version=1,
        )

    assert _counts(store) == before
    assert _mission_state(store) == (first.plan_revision_id, 1, 1)


def test_wrong_acceptance_authority_rejected_without_mutation(tmp_path: Path) -> None:
    store = _prepare_store(tmp_path)
    manifest, materials = _manifest_and_materials()

    with pytest.raises(GraphAcceptanceConflict, match="acceptance authority"):
        accept_plan_graph(
            store,
            company_id=COMPANY_ID,
            mission_id=MISSION_ID,
            expected_current_plan_revision_id=None,
            expected_plan_state_version=0,
            expected_kernel_state_version=0,
            project_id=PROJECT_ID,
            resource_id=RESOURCE_ID,
            scope_generation=1,
            controller_request_id="wrong-authority",
            accepted_by_ref="someone-else",
            acceptance_basis_ref="invalid",
            plan_contract_base={"purpose": "bad authority"},
            graph_manifest=manifest,
            work_package_contracts=materials,
            accepted_at=NOW,
        )

    assert _counts(store)["plan_revisions"] == 0
