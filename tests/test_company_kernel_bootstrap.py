"""V3-1B trusted Company/Mission bootstrap and plan-authority proofs."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from soma.company_kernel.bootstrap import (
    KernelBootstrapConflict,
    KernelBootstrapError,
    KernelBootstrapRequestV1,
    bootstrap_company_mission,
)
from soma.company_kernel.graph_models import PlanGraphManifestV1, PlanGraphNodeV1
from soma.company_kernel.models import work_package_contract_hash
from soma.company_kernel.service import (
    GraphAcceptanceConflict,
    WorkPackageContractMaterialV1,
    accept_plan_graph,
)
from soma.company_kernel.store import CompanyKernelStore
from soma.config import AppConfig, CompanyKernelRuntimeConfig, RepoConfig
from soma.project_scope.store import ProjectScopeStore


OWNER = "owner-controller:arash"
PROJECT_ID = "Project_Kernel_Bootstrap"
RESOURCE_ID = "Resource_Kernel_Bootstrap"
NOW = "2026-08-14T09:00:00+00:00"


def _runtime_config(tmp_path: Path, *, enabled: bool = True) -> tuple[AppConfig, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return (
        AppConfig(
            repos={"sample": RepoConfig(path=str(repo))},
            company_kernel=CompanyKernelRuntimeConfig(
                enabled=enabled,
                executive_authority_ref=OWNER if enabled else "",
            ),
            config_dir=tmp_path,
        ),
        repo,
    )


def _prepared(tmp_path: Path):
    config, repo = _runtime_config(tmp_path)
    store = CompanyKernelStore(config.resolve_runs_dir())
    assert store.init_db() == [1, 2, 3]
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="kernel-bootstrap",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    return config, repo, store, scope


def _request(**changes) -> KernelBootstrapRequestV1:
    payload = {
        "controller_request_id": "kernel-bootstrap-request-1",
        "company_key": "soma-personal-company",
        "company_display_name": "Soma Personal Company",
        "mission_key": "kernel-of-one",
        "mission_contract": {
            "objective": "operate one bounded kernel of one",
            "acceptance": "owner adjudication",
        },
        "project_id": PROJECT_ID,
        "repo_name": "sample",
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "executive_authority_ref": OWNER,
    }
    payload.update(changes)
    return KernelBootstrapRequestV1.model_validate(payload)


def _root_counts(store: CompanyKernelStore) -> tuple[int, int, int, int]:
    with store.connect() as conn:
        return (
            int(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]),
            int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]),
        )


def test_company_kernel_runtime_config_is_inert_and_requires_trusted_executive(
    tmp_path: Path,
) -> None:
    config = AppConfig(repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path)
    assert config.company_kernel.enabled is False
    assert config.company_kernel.executive_authority_ref == ""

    with pytest.raises(ValidationError, match="requires executive_authority_ref"):
        CompanyKernelRuntimeConfig(enabled=True)
    with pytest.raises(ValidationError, match="whitespace-only"):
        CompanyKernelRuntimeConfig(enabled=True, executive_authority_ref="   ")
    with pytest.raises(ValidationError, match="embedded NUL"):
        CompanyKernelRuntimeConfig(executive_authority_ref="owner\x00bad")


def test_disabled_runtime_refuses_bootstrap_without_mutation(tmp_path: Path) -> None:
    config, _repo = _runtime_config(tmp_path, enabled=False)
    store = CompanyKernelStore(config.resolve_runs_dir())
    store.init_db()

    with pytest.raises(KernelBootstrapError, match="disabled"):
        bootstrap_company_mission(config, _request(), store=store, created_at=NOW)

    assert _root_counts(store) == (0, 0, 0, 0)


def test_bootstrap_creates_exact_root_and_request_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    config, _repo, store, scope = _prepared(tmp_path)
    first = bootstrap_company_mission(
        config,
        _request(),
        store=store,
        scope_store=scope,
        created_at=NOW,
    )
    replay = bootstrap_company_mission(
        config,
        _request(repo_name="SAMPLE"),
        store=store,
        scope_store=scope,
        created_at="2026-08-14T10:00:00+00:00",
    )

    assert first.created is True
    assert first.replay_kind == "none"
    assert replay.created is False
    assert replay.replay_kind == "request"
    assert replay.request_hash == first.request_hash
    assert replay.company == first.company
    assert replay.mission == first.mission
    assert first.company.executive_authority_ref == OWNER
    assert first.mission.accountable_owner_ref == OWNER
    assert first.mission.acceptance_authority_ref == OWNER
    assert first.mission.project_id == PROJECT_ID
    assert first.mission.resource_id == RESOURCE_ID
    assert first.mission.scope_generation == 1
    assert _root_counts(store) == (1, 1, 0, 0)


def test_same_controller_request_with_changed_material_fails_closed(
    tmp_path: Path,
) -> None:
    config, _repo, store, scope = _prepared(tmp_path)
    first = bootstrap_company_mission(
        config, _request(), store=store, scope_store=scope, created_at=NOW
    )

    with pytest.raises(KernelBootstrapConflict, match="conflicts"):
        bootstrap_company_mission(
            config,
            _request(company_display_name="Different Company"),
            store=store,
            scope_store=scope,
            created_at=NOW,
        )

    assert _root_counts(store) == (1, 1, 0, 0)
    with store.connect() as conn:
        row = conn.execute("SELECT display_name FROM companies").fetchone()
    assert row[0] == first.company.display_name


def test_caller_cannot_mint_or_substitute_executive_authority(tmp_path: Path) -> None:
    config, _repo, store, scope = _prepared(tmp_path)

    with pytest.raises(KernelBootstrapConflict, match="trusted configuration"):
        bootstrap_company_mission(
            config,
            _request(executive_authority_ref="owner-controller:someone-else"),
            store=store,
            scope_store=scope,
            created_at=NOW,
        )

    assert _root_counts(store) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"project_id": "Other_Project"}, "No active repository binding"),
        ({"resource_id": "Other_Resource"}, "resource identity differs"),
        ({"scope_generation": 2}, "generation differs"),
        ({"repo_name": "missing"}, "Unknown repo_name"),
    ],
)
def test_bootstrap_requires_exact_active_project_scope(
    tmp_path: Path,
    changes: dict,
    message: str,
) -> None:
    config, _repo, store, scope = _prepared(tmp_path)

    with pytest.raises(KernelBootstrapError, match=message):
        bootstrap_company_mission(
            config,
            _request(**changes),
            store=store,
            scope_store=scope,
            created_at=NOW,
        )

    assert _root_counts(store) == (0, 0, 0, 0)


def test_new_bootstrap_refuses_archived_scope_but_exact_replay_survives(
    tmp_path: Path,
) -> None:
    config, repo, store, scope = _prepared(tmp_path)
    first = bootstrap_company_mission(
        config, _request(), store=store, scope_store=scope, created_at=NOW
    )
    archived = scope.archive_empty_repository_binding(
        project_id=PROJECT_ID,
        repo_name="sample",
        repository_root=repo,
        expected_scope_generation=1,
    )
    assert archived["lifecycle_state"] == "archived"

    replay = bootstrap_company_mission(
        config, _request(), store=store, scope_store=scope, created_at=NOW
    )
    assert replay.created is False
    assert replay.company == first.company

    with pytest.raises(KernelBootstrapConflict, match="No active repository binding"):
        bootstrap_company_mission(
            config,
            _request(controller_request_id="kernel-bootstrap-request-2"),
            store=store,
            scope_store=scope,
            created_at=NOW,
        )


@pytest.mark.parametrize(
    "phase", ["before_company_insert", "after_company_insert", "after_mission_insert"]
)
def test_bootstrap_faults_roll_back_company_and_mission_atomically(
    tmp_path: Path,
    phase: str,
) -> None:
    config, _repo, store, scope = _prepared(tmp_path)

    def fault(observed: str, _conn: sqlite3.Connection) -> None:
        if observed == phase:
            raise RuntimeError(f"fault:{phase}")

    with pytest.raises(RuntimeError, match="fault:"):
        bootstrap_company_mission(
            config,
            _request(),
            store=store,
            scope_store=scope,
            created_at=NOW,
            _fault_injector=fault,
        )

    assert _root_counts(store) == (0, 0, 0, 0)


def test_concurrent_identical_bootstrap_converges_to_one_root(tmp_path: Path) -> None:
    config, _repo, store, scope = _prepared(tmp_path)

    def call():
        return bootstrap_company_mission(
            config,
            _request(),
            store=store,
            scope_store=scope,
            created_at=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: call(), range(2)))

    assert sorted(result.created for result in results) == [False, True]
    assert len({result.company.company_id for result in results}) == 1
    assert len({result.mission.mission_id for result in results}) == 1
    assert _root_counts(store) == (1, 1, 0, 0)


def test_concurrent_conflicting_bootstrap_has_one_winner(tmp_path: Path) -> None:
    config, _repo, store, scope = _prepared(tmp_path)
    requests = [
        _request(company_display_name="Company A"),
        _request(company_display_name="Company B"),
    ]

    def call(request: KernelBootstrapRequestV1):
        try:
            return bootstrap_company_mission(
                config,
                request,
                store=store,
                scope_store=scope,
                created_at=NOW,
            )
        except KernelBootstrapConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(call, requests))

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, KernelBootstrapConflict) for result in results) == 1
    assert _root_counts(store) == (1, 1, 0, 0)


def test_bootstrapped_root_drives_existing_atomic_plan_graph_authority(
    tmp_path: Path,
) -> None:
    config, _repo, store, scope = _prepared(tmp_path)
    root = bootstrap_company_mission(
        config, _request(), store=store, scope_store=scope, created_at=NOW
    )
    material = WorkPackageContractMaterialV1(
        contract_version="v1",
        contract={
            "purpose": "prove bootstrapped plan authority",
            "expected_output": "bounded evidence",
        },
    )
    manifest = PlanGraphManifestV1(
        mission_id=root.mission.mission_id,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        package_nodes=[
            PlanGraphNodeV1(
                package_key="proof",
                work_package_contract_hash=work_package_contract_hash(
                    contract_version=material.contract_version,
                    contract=material.contract,
                ),
                target_resource_id=RESOURCE_ID,
            )
        ],
        dependency_edges=[],
    )
    kwargs = dict(
        store=store,
        company_id=root.company.company_id,
        mission_id=root.mission.mission_id,
        expected_current_plan_revision_id=None,
        expected_plan_state_version=0,
        expected_kernel_state_version=0,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        controller_request_id="bootstrapped-plan-request",
        accepted_by_ref=OWNER,
        acceptance_basis_ref="owner accepted bounded graph",
        plan_contract_base={"purpose": "execute bootstrapped plan"},
        graph_manifest=manifest,
        work_package_contracts={"proof": material},
        accepted_at=NOW,
    )
    first = accept_plan_graph(**kwargs)
    replay = accept_plan_graph(**kwargs)

    assert first.created is True
    assert replay.created is False
    assert replay.replay_kind == "request"
    assert replay.plan_revision_id == first.plan_revision_id
    assert _root_counts(store) == (1, 1, 0, 0)

    changed_material = WorkPackageContractMaterialV1(
        contract_version="v1",
        contract={
            "purpose": "different bounded plan",
            "expected_output": "different evidence",
        },
    )
    changed_manifest = PlanGraphManifestV1(
        mission_id=root.mission.mission_id,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        package_nodes=[
            PlanGraphNodeV1(
                package_key="proof",
                work_package_contract_hash=work_package_contract_hash(
                    contract_version=changed_material.contract_version,
                    contract=changed_material.contract,
                ),
                target_resource_id=RESOURCE_ID,
            )
        ],
        dependency_edges=[],
    )
    with pytest.raises(GraphAcceptanceConflict, match="current PlanRevision changed"):
        accept_plan_graph(
            **{
                **kwargs,
                "controller_request_id": "bootstrapped-plan-stale",
                "graph_manifest": changed_manifest,
                "work_package_contracts": {"proof": changed_material},
            }
        )
