"""Strict public company_query/company_action contract and delegation proofs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from soma.cf1_gateway_operation_inventory import operation_names_by_gateway
import soma.company_kernel.gateway as company_gateway
from soma.company_kernel.gateway import company_action_gateway, company_query_gateway
from soma.company_kernel.graph_models import PlanGraphManifestV1, PlanGraphNodeV1
from soma.company_kernel.models import work_package_contract_hash
from soma.company_kernel.service import WorkPackageContractMaterialV1
from soma.company_kernel.store import CompanyKernelStore
from soma.config import AppConfig, CompanyKernelRuntimeConfig, RepoConfig
from soma.gateway_models import CompanyActionRequest, CompanyQueryRequest
from soma.project_scope.store import ProjectScopeStore
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1


OWNER = "owner-controller:public-company-gateway"
PROJECT_ID = "Project_Public_Company_Gateway"
RESOURCE_ID = "Resource_Public_Company_Gateway"

QUERY_ADAPTER = TypeAdapter(CompanyQueryRequest)
ACTION_ADAPTER = TypeAdapter(CompanyActionRequest)


def _config(tmp_path: Path, *, enabled: bool = True) -> tuple[AppConfig, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        company_kernel=CompanyKernelRuntimeConfig(
            enabled=enabled,
            executive_authority_ref=OWNER if enabled else "",
        ),
        config_dir=tmp_path,
    )
    return config, repo


def _prepared(tmp_path: Path) -> tuple[AppConfig, Path, CompanyKernelStore]:
    config, repo = _config(tmp_path)
    store = CompanyKernelStore(config.resolve_runs_dir())
    assert store.init_db() == [1, 2, 3, 4]
    ProjectScopeStore(config.resolve_runs_dir()).apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="public-company-gateway",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )
    return config, repo, store


def _bootstrap_payload(**changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation": "bootstrap_kernel",
        "controller_request_id": "public-bootstrap-1",
        "company_key": "public-company",
        "company_display_name": "Public Company",
        "mission_key": "public-mission",
        "mission_contract": {"objective": "prove strict public gateway delegation"},
        "project_id": PROJECT_ID,
        "repo_name": "sample",
        "resource_id": RESOURCE_ID,
        "scope_generation": 1,
        "executive_authority_ref": OWNER,
    }
    payload.update(changes)
    return payload


def _query_payload(
    operation: str,
    *,
    company_id: str,
    mission_id: str,
    **changes: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation": operation,
        "company_id": company_id,
        "mission_id": mission_id,
        "project_id": PROJECT_ID,
        "repo_name": "sample",
    }
    payload.update(changes)
    return payload


def _reasoning_spec() -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:public-company",
        assignment_hash="1" * 64,
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash="2" * 64,
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash="3" * 64,
        authority_ref="authority:public-company",
        authority_hash="4" * 64,
        provider_route_ref="route:public-company",
        provider_route_hash="5" * 64,
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _bootstrap(config: AppConfig):
    return company_action_gateway(
        config,
        ACTION_ADAPTER.validate_python(_bootstrap_payload()),
        task_manager_factory=lambda: pytest.fail("bootstrap must not construct TaskManager"),
    )


def _accept_one_package_plan(
    config: AppConfig,
    *,
    company_id: str,
    mission_id: str,
) -> dict[str, Any]:
    material = WorkPackageContractMaterialV1(
        contract_version="v1",
        contract={
            "purpose": "prove public graph acceptance",
            "expected_output": "bounded evidence",
        },
    )
    manifest = PlanGraphManifestV1(
        mission_id=mission_id,
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
    request = ACTION_ADAPTER.validate_python(
        {
            "operation": "accept_plan_revision",
            "company_id": company_id,
            "mission_id": mission_id,
            "expected_current_plan_revision_id": None,
            "expected_plan_state_version": 0,
            "expected_kernel_state_version": 0,
            "project_id": PROJECT_ID,
            "resource_id": RESOURCE_ID,
            "scope_generation": 1,
            "controller_request_id": "public-plan-1",
            "accepted_by_ref": OWNER,
            "acceptance_basis_ref": "owner accepted public bounded graph",
            "plan_contract_base": {"purpose": "execute public bounded graph"},
            "graph_manifest": manifest.model_dump(mode="json"),
            "work_package_contracts": {
                "proof": material.model_dump(mode="json")
            },
        }
    )
    return company_action_gateway(
        config,
        request,
        task_manager_factory=lambda: pytest.fail("plan acceptance must not construct TaskManager"),
    )


def test_public_company_unions_are_strict_and_match_inventory() -> None:
    query_ops = operation_names_by_gateway()["company_query"]
    action_ops = operation_names_by_gateway()["company_action"]
    assert query_ops == {
        "capabilities",
        "mission_status",
        "current_plan",
        "work_package",
        "outcome_status",
        "acceptance_commit",
        "reconciliation_receipt",
    }
    assert action_ops == {
        "bootstrap_kernel",
        "accept_plan_revision",
        "reserve_attempt",
        "accept_outcome",
        "reconcile_one",
    }
    assert "define_work_package" not in action_ops

    with pytest.raises(ValidationError):
        QUERY_ADAPTER.validate_python({"operation": "mission_status"})
    with pytest.raises(ValidationError):
        ACTION_ADAPTER.validate_python(_bootstrap_payload(unexpected=True))
    with pytest.raises(ValidationError):
        ACTION_ADAPTER.validate_python(
            _bootstrap_payload(mission_contract={"huge": "x" * 200_001})
        )


def test_capabilities_are_honest_while_runtime_is_disabled(tmp_path: Path) -> None:
    config, _repo = _config(tmp_path, enabled=False)
    result = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python({"operation": "capabilities"}),
    )
    assert result["ok"] is True
    assert result["runtime_enabled"] is False
    assert result["reasoning_attempt_route_enabled"] is False
    assert result["live_activation_gate_complete"] is False
    assert result["automatic_outcome_acceptance"] is False


def test_capabilities_report_live_activation_only_after_schema_install(tmp_path: Path) -> None:
    config, _repo = _config(tmp_path, enabled=True)
    before = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python({"operation": "capabilities"}),
    )
    assert before["runtime_enabled"] is True
    assert before["schema"]["up_to_date"] is False
    assert before["live_activation_gate_complete"] is False

    store = CompanyKernelStore(config.resolve_runs_dir())
    assert store.init_db() == [1, 2, 3, 4]
    after = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python({"operation": "capabilities"}),
    )
    assert after["runtime_enabled"] is True
    assert after["schema"]["up_to_date"] is True
    assert after["live_activation_gate_complete"] is True
    assert after["reasoning_attempt_route_enabled"] is False


def test_non_capability_query_refuses_before_live_activation(tmp_path: Path) -> None:
    config, _repo = _config(tmp_path, enabled=False)
    request = QUERY_ADAPTER.validate_python(
        _query_payload(
            "mission_status",
            company_id="company_" + "1" * 24,
            mission_id="mission_" + "2" * 24,
        )
    )
    result = company_query_gateway(config, request)
    assert result["ok"] is False
    assert "not activated" in result["error"]


def test_bootstrap_and_query_use_the_same_canonical_root(tmp_path: Path) -> None:
    config, _repo, store = _prepared(tmp_path)
    bootstrap = _bootstrap(config)
    assert bootstrap["ok"] is True
    company_id = bootstrap["result"]["company"]["company_id"]
    mission_id = bootstrap["result"]["mission"]["mission_id"]

    query = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "mission_status",
                company_id=company_id,
                mission_id=mission_id,
            )
        ),
    )
    assert query["ok"] is True
    assert query["result"]["company_id"] == company_id
    assert query["result"]["mission_id"] == mission_id
    assert query["result"]["project_id"] == PROJECT_ID
    assert query["result"]["current_plan_revision_id"] is None

    counts = store.table_counts()
    assert counts["companies"] == 1
    assert counts["missions"] == 1
    assert counts["plan_revisions"] == 0


def test_public_plan_acceptance_is_atomic_graph_authority_and_queries_rebuild_it(
    tmp_path: Path,
) -> None:
    config, _repo, _store = _prepared(tmp_path)
    bootstrap = _bootstrap(config)
    company_id = bootstrap["result"]["company"]["company_id"]
    mission_id = bootstrap["result"]["mission"]["mission_id"]

    accepted = _accept_one_package_plan(
        config,
        company_id=company_id,
        mission_id=mission_id,
    )
    assert accepted["ok"] is True
    assert accepted["result"]["package_count"] == 1
    plan_id = accepted["result"]["plan_revision_id"]
    package_id = accepted["result"]["package_ids"]["proof"]

    current = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "current_plan",
                company_id=company_id,
                mission_id=mission_id,
            )
        ),
    )
    package = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "work_package",
                company_id=company_id,
                mission_id=mission_id,
                work_package_id=package_id,
            )
        ),
    )
    outcome = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "outcome_status",
                company_id=company_id,
                mission_id=mission_id,
                outcome_id=package["result"]["outcome_id"],
            )
        ),
    )

    assert current["result"]["plan_revision_id"] == plan_id
    assert current["result"]["package_count"] == 1
    assert package["result"]["work_package_id"] == package_id
    assert package["result"]["state"] == "not_started"
    assert outcome["result"]["work_package_id"] == package_id


def test_scoped_queries_reject_wrong_project_or_repository(tmp_path: Path) -> None:
    config, _repo, _store = _prepared(tmp_path)
    bootstrap = _bootstrap(config)
    company_id = bootstrap["result"]["company"]["company_id"]
    mission_id = bootstrap["result"]["mission"]["mission_id"]

    wrong_project = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "mission_status",
                company_id=company_id,
                mission_id=mission_id,
                project_id="Other_Project",
            )
        ),
    )
    wrong_repo = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "mission_status",
                company_id=company_id,
                mission_id=mission_id,
                repo_name="missing",
            )
        ),
    )
    assert wrong_project["ok"] is False
    assert "ProjectScope" in wrong_project["error"]
    assert wrong_repo["ok"] is False
    assert "repo" in wrong_repo["error"].lower()


def test_reserve_attempt_refuses_before_task_manager_when_reasoning_is_disabled(
    tmp_path: Path,
) -> None:
    config, _repo, _store = _prepared(tmp_path)
    called = False

    def task_manager_factory():
        nonlocal called
        called = True
        raise AssertionError("TaskManager must not be constructed")

    request = ACTION_ADAPTER.validate_python(
        {
            "operation": "reserve_attempt",
            "company_id": "company_" + "1" * 24,
            "mission_id": "mission_" + "2" * 24,
            "work_package_id": "workpkg_" + "3" * 24,
            "project_id": PROJECT_ID,
            "resource_id": RESOURCE_ID,
            "scope_generation": 1,
            "executive_authority_ref": OWNER,
            "controller_request_id": "public-attempt-disabled",
            "repo_name": "sample",
            "reasoning_spec": _reasoning_spec().model_dump(mode="json"),
        }
    )
    result = company_action_gateway(
        config,
        request,
        task_manager_factory=task_manager_factory,
    )
    assert result["ok"] is False
    assert "reasoning is disabled" in result["error"]
    assert called is False


def test_enabled_public_reserve_attempt_strips_gateway_only_authority_fields_before_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _repo, _store = _prepared(tmp_path)
    bootstrap = _bootstrap(config)
    company_id = bootstrap["result"]["company"]["company_id"]
    mission_id = bootstrap["result"]["mission"]["mission_id"]
    config.reasoning.enabled = True
    captured: dict[str, Any] = {}
    manager = object()

    def fake_admit(observed_manager: object, request: object):
        captured["manager"] = observed_manager
        captured["request"] = request
        return SimpleNamespace(
            mission_id=mission_id,
            plan_revision_id="planrev_" + "8" * 24,
            work_package_id="workpkg_" + "9" * 24,
            attempt_id="wpattempt_" + "a" * 24,
            attempt_hash="b" * 64,
            task_id="task-public-company",
            proof_refs=(),
            created=True,
            task_start={"status": "accepted"},
        )

    monkeypatch.setattr(company_gateway, "admit_reasoning_work_package", fake_admit)
    request = ACTION_ADAPTER.validate_python(
        {
            "operation": "reserve_attempt",
            "company_id": company_id,
            "mission_id": mission_id,
            "work_package_id": "workpkg_" + "9" * 24,
            "project_id": PROJECT_ID,
            "resource_id": RESOURCE_ID,
            "scope_generation": 1,
            "executive_authority_ref": OWNER,
            "controller_request_id": "public-attempt-enabled",
            "repo_name": "sample",
            "reasoning_spec": _reasoning_spec().model_dump(mode="json"),
        }
    )
    result = company_action_gateway(
        config,
        request,
        task_manager_factory=lambda: manager,
    )

    assert result["ok"] is True
    assert captured["manager"] is manager
    delegated = captured["request"].model_dump(mode="python")
    assert delegated["mission_id"] == mission_id
    assert delegated["work_package_id"] == request.work_package_id
    assert delegated["repo_name"] == "sample"
    assert "company_id" not in delegated
    assert "project_id" not in delegated
    assert "resource_id" not in delegated
    assert "executive_authority_ref" not in delegated


def test_accept_outcome_public_boundary_delegates_exact_internal_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _repo, _store = _prepared(tmp_path)
    captured: dict[str, Any] = {}
    acceptance = SimpleNamespace(
        acceptance_commit_id="accept_" + "1" * 24,
        company_id="company_" + "2" * 24,
        mission_id="mission_" + "3" * 24,
        work_package_id="workpkg_" + "4" * 24,
        outcome_id="outcome_" + "5" * 24,
        attempt_id="wpattempt_" + "6" * 24,
        task_id="task-public-acceptance",
        backend_kind="soma_durable_run",
        backend_ref="run-public-acceptance",
        result_published_hash="7" * 64,
        public_result_source_sha256="8" * 64,
        acceptance_authority_ref=OWNER,
        acceptance_basis_ref="owner acceptance basis",
        acceptance_basis_hash="9" * 64,
        accepted_at="2026-08-14T13:00:00+00:00",
    )

    def fake_accept(observed_config: AppConfig, request: object, *, store: object):
        captured["config"] = observed_config
        captured["request"] = request
        captured["store"] = store
        return SimpleNamespace(
            acceptance=acceptance,
            created=True,
            replay_kind="none",
            request_hash="a" * 64,
        )

    monkeypatch.setattr(company_gateway, "accept_outcome", fake_accept)
    request = ACTION_ADAPTER.validate_python(
        {
            "operation": "accept_outcome",
            "controller_request_id": "public-acceptance-1",
            "company_id": acceptance.company_id,
            "mission_id": acceptance.mission_id,
            "plan_revision_id": "planrev_" + "b" * 24,
            "work_package_id": acceptance.work_package_id,
            "outcome_id": acceptance.outcome_id,
            "attempt_id": acceptance.attempt_id,
            "task_id": acceptance.task_id,
            "backend_kind": acceptance.backend_kind,
            "backend_ref": acceptance.backend_ref,
            "project_id": PROJECT_ID,
            "resource_id": RESOURCE_ID,
            "scope_generation": 1,
            "expected_kernel_state_version": 7,
            "result_published_hash": acceptance.result_published_hash,
            "public_result_source_sha256": acceptance.public_result_source_sha256,
            "acceptance_authority_ref": OWNER,
            "acceptance_basis_ref": acceptance.acceptance_basis_ref,
            "acceptance_basis_hash": acceptance.acceptance_basis_hash,
        }
    )
    result = company_action_gateway(
        config,
        request,
        task_manager_factory=lambda: pytest.fail("acceptance must not construct TaskManager"),
    )

    assert result["ok"] is True
    assert captured["config"] is config
    delegated = captured["request"].model_dump(mode="python")
    assert delegated["controller_request_id"] == "public-acceptance-1"
    assert delegated["expected_kernel_state_version"] == 7
    assert delegated["acceptance_authority_ref"] == OWNER
    assert result["result"]["acceptance"]["acceptance_commit_id"] == acceptance.acceptance_commit_id


def test_reconcile_one_records_one_receipt_and_public_query_reads_it(
    tmp_path: Path,
) -> None:
    config, _repo, _store = _prepared(tmp_path)
    bootstrap = _bootstrap(config)
    company_id = bootstrap["result"]["company"]["company_id"]
    mission_id = bootstrap["result"]["mission"]["mission_id"]
    accepted = _accept_one_package_plan(
        config,
        company_id=company_id,
        mission_id=mission_id,
    )
    assert accepted["ok"] is True

    reconcile = company_action_gateway(
        config,
        ACTION_ADAPTER.validate_python(
            {
                "operation": "reconcile_one",
                "company_id": company_id,
                "mission_id": mission_id,
                "project_id": PROJECT_ID,
                "resource_id": RESOURCE_ID,
                "scope_generation": 1,
                "executive_authority_ref": OWNER,
                "trigger_kind": "owner_turn",
                "trigger_ref": "owner-turn:public-gateway-1",
                "expected_kernel_state_version": 1,
                "selected_transition": "no_op",
            }
        ),
        task_manager_factory=lambda: pytest.fail("reconcile must not construct TaskManager"),
    )
    assert reconcile["ok"] is True
    receipt_id = reconcile["result"]["receipt"]["reconciliation_id"]

    queried = company_query_gateway(
        config,
        QUERY_ADAPTER.validate_python(
            _query_payload(
                "reconciliation_receipt",
                company_id=company_id,
                mission_id=mission_id,
                reconciliation_id=receipt_id,
            )
        ),
    )
    assert queried["ok"] is True
    assert queried["result"]["reconciliation_id"] == receipt_id
    assert queried["result"]["selected_transition"] == "no_op"


def test_public_response_budget_fails_explicitly_without_semantic_truncation(
    tmp_path: Path,
) -> None:
    config, _repo = _config(tmp_path, enabled=False)
    request = QUERY_ADAPTER.validate_python(
        {
            "operation": "capabilities",
            "response_budget_bytes": 1024,
        }
    )
    result = company_query_gateway(config, request)
    assert result["ok"] is False
    assert result["error_code"] == "company_response_budget_too_small"
    assert result["omitted_payload_sha256"]
