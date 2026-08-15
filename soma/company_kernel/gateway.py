"""Strict public projection/delegation helpers for the V3-1B Company Kernel.

The public MCP functions live in :mod:`soma.server`; this module keeps their
Company-domain logic small and auditable. Queries reconstruct canonical facts
without a materialised lifecycle cache. Actions delegate to the already-proven
internal authorities and never reproduce their transactions.

Registration is intentionally separate from runtime activation. Except for the
capability query, Company operations refuse while ``config.company_kernel`` is
disabled. WorkPackageAttempt execution admission remains frozen until the owner
explicitly activates the corrected provider-neutral canonical Task route.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from hashlib import sha256
from typing import Any, Iterator, Mapping

from soma.config import AppConfig, resolve_repo_identity
from soma.project_scope.models import repository_identity_hash
from soma.public_projection_contract import (
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
)

from .acceptance import OutcomeAcceptanceRequestV1, accept_outcome
from .bootstrap import KernelBootstrapRequestV1, bootstrap_company_mission
from .models import AcceptanceCommit, KernelReconciliationReceipt
from .projections import (
    project_mission_in_connection,
    project_plan_revision_in_connection,
    project_work_package_in_connection,
)
from .reconciliation import ReconcileOneRequestV1, reconcile_one
from .service import accept_plan_graph
from .store import CompanyKernelStore


COMPANY_QUERY_OPERATIONS: tuple[str, ...] = (
    "capabilities",
    "mission_status",
    "current_plan",
    "work_package",
    "outcome_status",
    "acceptance_commit",
    "reconciliation_receipt",
)
COMPANY_ACTION_OPERATIONS: tuple[str, ...] = (
    "bootstrap_kernel",
    "accept_plan_revision",
    "reserve_attempt",
    "accept_outcome",
    "reconcile_one",
)
PUBLIC_COMPACT_ATTEMPT_LIMIT = 8
PUBLIC_COMPACT_PROOF_LIMIT = 16


class CompanyGatewayError(ValueError):
    """One public Company gateway assertion conflicts with canonical truth."""


@contextmanager
def _read_connection(store: CompanyKernelStore) -> Iterator[sqlite3.Connection]:
    if not store.db_path.exists():
        raise CompanyGatewayError("Company Kernel database is not installed")
    uri = f"file:{store.db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _public_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _encoded_size(payload: Mapping[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    )


def _with_projection_envelope(payload: dict[str, Any], *, view: str) -> dict[str, Any]:
    result = dict(payload)
    result.update(
        {
            "view": view,
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
        }
    )
    return result


def _finalize(
    payload: dict[str, Any],
    *,
    operation: str,
    view: str,
    budget: int,
) -> dict[str, Any]:
    result = _with_projection_envelope(payload, view=view)
    result.setdefault("operation", operation)
    result.setdefault("ok", True)
    for _ in range(4):
        size = _encoded_size(result)
        if result.get("response_bytes") == size:
            break
        result["response_bytes"] = size
    required = _encoded_size(result)
    if required <= budget:
        return result
    error = _with_projection_envelope(
        {
            "ok": False,
            "operation": operation,
            "error_code": "company_response_budget_too_small",
            "error": "Company gateway response exceeds the requested UTF-8 byte budget",
            "required_response_bytes": required,
            "response_budget_bytes": budget,
            "omitted_payload_sha256": _public_hash(result),
        },
        view=view,
    )
    error["response_bytes"] = _encoded_size(error)
    return error


def _error(
    operation: str,
    exc: BaseException | str,
    *,
    view: str,
    budget: int,
    code: str = "company_gateway_conflict",
) -> dict[str, Any]:
    message = str(exc)
    return _finalize(
        {
            "ok": False,
            "operation": operation,
            "error_code": code,
            "error": message,
        },
        operation=operation,
        view=view,
        budget=budget,
    )


def _require_runtime(config: AppConfig) -> None:
    if not config.company_kernel.enabled:
        raise CompanyGatewayError(
            "Company Kernel runtime is not activated by owner configuration"
        )
    if not config.company_kernel.executive_authority_ref:
        raise CompanyGatewayError("Company Kernel trusted executive is not configured")


def _require_trusted_executive(config: AppConfig, asserted: str) -> None:
    _require_runtime(config)
    if asserted != config.company_kernel.executive_authority_ref:
        raise CompanyGatewayError(
            "executive authority assertion does not match trusted configuration"
        )


def _require_scoped_query(
    conn: sqlite3.Connection,
    config: AppConfig,
    *,
    company_id: str,
    mission_id: str,
    project_id: str,
    repo_name: str,
) -> sqlite3.Row:
    try:
        canonical_repo_name, repo_root, _repo = resolve_repo_identity(config, repo_name)
    except (KeyError, ValueError) as exc:
        raise CompanyGatewayError(str(exc)) from exc
    mission = conn.execute(
        "SELECT company_id, project_id, resource_id, scope_generation "
        "FROM missions WHERE mission_id = ?",
        (mission_id,),
    ).fetchone()
    if mission is None:
        raise CompanyGatewayError("exact Mission identity is unavailable")
    if str(mission["company_id"]) != company_id:
        raise CompanyGatewayError("Mission does not belong to the asserted Company")
    if str(mission["project_id"]) != project_id:
        raise CompanyGatewayError(
            "Mission does not belong to the asserted ProjectScope"
        )
    binding = conn.execute(
        "SELECT resource_id, identity_hash FROM project_repository_bindings "
        "WHERE project_id = ? AND repo_name = ?",
        (project_id, canonical_repo_name),
    ).fetchone()
    if binding is None:
        raise CompanyGatewayError(
            "asserted repository is not bound to the Mission ProjectScope"
        )
    if str(binding["resource_id"]) != str(mission["resource_id"]):
        raise CompanyGatewayError(
            "repository resource identity differs from the immutable Mission scope"
        )
    if str(binding["identity_hash"]) != repository_identity_hash(repo_root):
        raise CompanyGatewayError(
            "repository binding identity differs from current configured repository"
        )
    return mission


def _require_public_attempt_authority(config: AppConfig, request: Any) -> None:
    _require_trusted_executive(config, request.executive_authority_ref)
    store = CompanyKernelStore(config.resolve_runs_dir())
    with _read_connection(store) as conn:
        mission = conn.execute(
            "SELECT missions.company_id, missions.project_id, missions.resource_id, "
            "missions.scope_generation, missions.accountable_owner_ref, "
            "missions.acceptance_authority_ref, companies.executive_authority_ref "
            "FROM missions JOIN companies ON companies.company_id = missions.company_id "
            "WHERE missions.mission_id = ?",
            (request.mission_id,),
        ).fetchone()
        if mission is None:
            raise CompanyGatewayError("exact Mission identity is unavailable")
        expected = request.executive_authority_ref
        if str(mission["company_id"]) != request.company_id:
            raise CompanyGatewayError("Mission does not belong to the asserted Company")
        if any(
            str(mission[field]) != expected
            for field in (
                "accountable_owner_ref",
                "acceptance_authority_ref",
                "executive_authority_ref",
            )
        ):
            raise CompanyGatewayError(
                "public attempt authority does not match the immutable Company/Mission authority chain"
            )
        if (
            str(mission["project_id"]) != request.project_id
            or str(mission["resource_id"]) != request.resource_id
            or int(mission["scope_generation"]) != request.scope_generation
        ):
            raise CompanyGatewayError(
                "public attempt ProjectScope assertion does not match immutable Mission scope"
            )
        _require_scoped_query(
            conn,
            config,
            company_id=request.company_id,
            mission_id=request.mission_id,
            project_id=request.project_id,
            repo_name=request.repo_name,
        )


def _compact_work_package(payload: dict[str, Any]) -> dict[str, Any]:
    attempts = list(payload.get("attempts") or ())
    if len(attempts) > PUBLIC_COMPACT_ATTEMPT_LIMIT:
        attempts = attempts[-PUBLIC_COMPACT_ATTEMPT_LIMIT:]
    compact = dict(payload)
    compact["attempts"] = attempts
    compact["attempts_truncated"] = bool(payload.get("attempts_truncated")) or (
        int(payload.get("attempt_count", len(attempts))) > len(attempts)
    )
    compact["public_attempt_limit"] = PUBLIC_COMPACT_ATTEMPT_LIMIT
    return compact


def _capabilities(config: AppConfig) -> dict[str, Any]:
    store = CompanyKernelStore(config.resolve_runs_dir())
    schema = store.schema_state()
    live_activation_ready = bool(
        config.company_kernel.enabled
        and config.company_kernel.executive_authority_ref
        and schema.get("up_to_date")
    )
    return {
        "ok": True,
        "operation": "capabilities",
        "component": "company_kernel",
        "query_operations": list(COMPANY_QUERY_OPERATIONS),
        "action_operations": list(COMPANY_ACTION_OPERATIONS),
        "runtime_enabled": bool(config.company_kernel.enabled),
        "trusted_executive_configured": bool(
            config.company_kernel.executive_authority_ref
        ),
        "attempt_admission_enabled": False,
        "canonical_task_route_model": "provider_neutral",
        "reasoning_attempt_route_enabled": False,
        "optional_reasoning_route_configured": bool(config.reasoning.enabled),
        "scheduled_reconciliation": False,
        "automatic_outcome_acceptance": False,
        "live_activation_gate_complete": live_activation_ready,
        "schema": schema,
        "authority": {
            "company_root": "company_kernel_bootstrap",
            "plan_and_packages": "accept_plan_graph",
            "attempt_admission": "company_kernel_admission",
            "execution": "canonical_task_backend",
            "outcome_acceptance": "named_acceptance_authority",
            "reconciliation": "receipt_only_reconcile_one",
        },
    }


def company_query_gateway(config: AppConfig, request: Any) -> dict[str, Any]:
    """Serve one strict read-only Company query from canonical facts."""
    operation = str(request.operation)
    view = str(request.view)
    budget = int(request.response_budget_bytes)
    if operation == "capabilities":
        return _finalize(
            _capabilities(config),
            operation=operation,
            view=view,
            budget=budget,
        )
    try:
        _require_runtime(config)
        store = CompanyKernelStore(config.resolve_runs_dir())
        with _read_connection(store) as conn:
            mission_row = _require_scoped_query(
                conn,
                config,
                company_id=request.company_id,
                mission_id=request.mission_id,
                project_id=request.project_id,
                repo_name=request.repo_name,
            )
            if operation == "mission_status":
                value = project_mission_in_connection(conn, request.mission_id)
                data: Any = value.model_dump(mode="json")
            elif operation == "current_plan":
                current = str(
                    conn.execute(
                        "SELECT COALESCE(current_plan_revision_id, '') FROM missions "
                        "WHERE mission_id = ?",
                        (request.mission_id,),
                    ).fetchone()[0]
                )
                data = (
                    project_plan_revision_in_connection(conn, current).model_dump(
                        mode="json"
                    )
                    if current
                    else None
                )
            elif operation == "work_package":
                value = project_work_package_in_connection(
                    conn, request.work_package_id
                )
                if value.mission_id != request.mission_id:
                    raise CompanyGatewayError(
                        "WorkPackage does not belong to the asserted Mission"
                    )
                data = value.model_dump(mode="json")
                if view == "compact":
                    data = _compact_work_package(data)
            elif operation == "outcome_status":
                rows = conn.execute(
                    "SELECT work_package_id FROM work_packages "
                    "WHERE mission_id = ? AND outcome_id = ? ORDER BY work_package_id",
                    (request.mission_id, request.outcome_id),
                ).fetchall()
                if len(rows) != 1:
                    raise CompanyGatewayError(
                        "exact Mission/outcome identity is unavailable"
                        if not rows
                        else "Mission/outcome identity is not unique"
                    )
                value = project_work_package_in_connection(
                    conn, str(rows[0]["work_package_id"])
                )
                data = value.model_dump(mode="json")
                if view == "compact":
                    data = _compact_work_package(data)
            elif operation == "acceptance_commit":
                row = conn.execute(
                    "SELECT * FROM acceptance_commits WHERE acceptance_commit_id = ? "
                    "AND company_id = ? AND mission_id = ?",
                    (
                        request.acceptance_commit_id,
                        request.company_id,
                        request.mission_id,
                    ),
                ).fetchone()
                if row is None:
                    raise CompanyGatewayError(
                        "exact AcceptanceCommit identity is unavailable"
                    )
                data = AcceptanceCommit.model_validate(dict(row)).model_dump(
                    mode="json"
                )
            elif operation == "reconciliation_receipt":
                row = conn.execute(
                    "SELECT receipt.* FROM kernel_reconciliation_receipts receipt "
                    "JOIN missions ON missions.mission_id = receipt.mission_id "
                    "WHERE receipt.reconciliation_id = ? AND receipt.mission_id = ? "
                    "AND missions.company_id = ?",
                    (
                        request.reconciliation_id,
                        request.mission_id,
                        request.company_id,
                    ),
                ).fetchone()
                if row is None:
                    raise CompanyGatewayError(
                        "exact reconciliation receipt identity is unavailable"
                    )
                data = KernelReconciliationReceipt.model_validate(dict(row)).model_dump(
                    mode="json"
                )
            else:  # pragma: no cover - discriminated public schema is closed
                raise CompanyGatewayError(
                    f"unsupported company_query operation: {operation}"
                )
            payload = {
                "ok": True,
                "operation": operation,
                "company_id": request.company_id,
                "mission_id": request.mission_id,
                "project_id": request.project_id,
                "repo_name": request.repo_name,
                "result": data,
                "scope_generation": int(mission_row["scope_generation"]),
            }
        return _finalize(payload, operation=operation, view=view, budget=budget)
    except (ValueError, KeyError, sqlite3.Error) as exc:
        return _error(operation, exc, view=view, budget=budget)


def _compact_bootstrap(result: Any) -> dict[str, Any]:
    company = result.company
    mission = result.mission
    return {
        "created": result.created,
        "replay_kind": result.replay_kind,
        "request_hash": result.request_hash,
        "company": {
            "company_id": company.company_id,
            "company_key": company.company_key,
            "display_name": company.display_name,
            "executive_authority_ref": company.executive_authority_ref,
        },
        "mission": {
            "mission_id": mission.mission_id,
            "mission_key": mission.mission_key,
            "project_id": mission.project_id,
            "resource_id": mission.resource_id,
            "scope_generation": mission.scope_generation,
            "mission_contract_hash": mission.mission_contract_hash,
            "current_plan_revision_id": mission.current_plan_revision_id,
            "plan_state_version": mission.plan_state_version,
            "kernel_state_version": mission.kernel_state_version,
        },
    }


def _compact_plan(result: Any) -> dict[str, Any]:
    return {
        "created": result.created,
        "replay_kind": result.replay_kind,
        "plan_revision_id": result.plan_revision_id,
        "plan_content_hash": result.plan_content_hash,
        "graph_manifest_hash": result.graph_manifest_hash,
        "request_hash": result.request_hash,
        "revision_number": result.revision_number,
        "package_ids": dict(result.package_ids),
        "package_count": len(result.package_ids),
        "edge_count": len(result.edge_ids),
    }


def _compact_admission(result: Any) -> dict[str, Any]:
    refs = [item.model_dump(mode="json") for item in result.proof_refs]
    return {
        "mission_id": result.mission_id,
        "plan_revision_id": result.plan_revision_id,
        "work_package_id": result.work_package_id,
        "attempt_id": result.attempt_id,
        "attempt_hash": result.attempt_hash,
        "task_id": result.task_id,
        "created": result.created,
        "proof_refs": refs[:PUBLIC_COMPACT_PROOF_LIMIT],
        "proof_count": len(refs),
        "proof_refs_truncated": len(refs) > PUBLIC_COMPACT_PROOF_LIMIT,
        "task_start_status": str(result.task_start.get("status", "")),
    }


def _compact_acceptance(result: Any) -> dict[str, Any]:
    acceptance = result.acceptance
    return {
        "created": result.created,
        "replay_kind": result.replay_kind,
        "request_hash": result.request_hash,
        "acceptance": {
            "acceptance_commit_id": acceptance.acceptance_commit_id,
            "company_id": acceptance.company_id,
            "mission_id": acceptance.mission_id,
            "work_package_id": acceptance.work_package_id,
            "outcome_id": acceptance.outcome_id,
            "attempt_id": acceptance.attempt_id,
            "task_id": acceptance.task_id,
            "backend_kind": acceptance.backend_kind,
            "backend_ref": acceptance.backend_ref,
            "result_published_hash": acceptance.result_published_hash,
            "public_result_source_sha256": acceptance.public_result_source_sha256,
            "acceptance_authority_ref": acceptance.acceptance_authority_ref,
            "acceptance_basis_ref": acceptance.acceptance_basis_ref,
            "acceptance_basis_hash": acceptance.acceptance_basis_hash,
            "accepted_at": acceptance.accepted_at,
        },
    }


def company_action_gateway(
    config: AppConfig,
    request: Any,
    *,
    task_manager_factory: Any,
) -> dict[str, Any]:
    """Delegate one strict Company mutation to its existing internal authority."""
    operation = str(request.operation)
    view = str(request.view)
    budget = int(request.response_budget_bytes)
    try:
        _require_runtime(config)
        payload = request.model_dump(
            mode="python",
            exclude={"operation", "view", "response_budget_bytes"},
        )
        store = CompanyKernelStore(config.resolve_runs_dir())
        if operation == "bootstrap_kernel":
            _require_trusted_executive(config, request.executive_authority_ref)
            result = bootstrap_company_mission(
                config,
                KernelBootstrapRequestV1.model_validate(payload),
                store=store,
            )
            data = _compact_bootstrap(result)
        elif operation == "accept_plan_revision":
            _require_trusted_executive(config, request.accepted_by_ref)
            result = accept_plan_graph(store, **payload)
            data = _compact_plan(result)
            if view == "full":
                data["edge_ids"] = list(result.edge_ids)
        elif operation == "reserve_attempt":
            _require_public_attempt_authority(config, request)
            raise CompanyGatewayError(
                "reserve_attempt remains frozen pending explicit owner activation of "
                "the corrected provider-neutral canonical Task admission route"
            )
        elif operation == "accept_outcome":
            _require_trusted_executive(config, request.acceptance_authority_ref)
            result = accept_outcome(
                config,
                OutcomeAcceptanceRequestV1.model_validate(payload),
                store=store,
            )
            data = _compact_acceptance(result)
        elif operation == "reconcile_one":
            _require_trusted_executive(config, request.executive_authority_ref)
            result = reconcile_one(
                config,
                ReconcileOneRequestV1.model_validate(payload),
                store=store,
            )
            data = {
                "created": result.created,
                "replay_kind": result.replay_kind,
                "receipt": result.receipt.model_dump(mode="json"),
            }
        else:  # pragma: no cover - discriminated public schema is closed
            raise CompanyGatewayError(
                f"unsupported company_action operation: {operation}"
            )
        return _finalize(
            {"ok": True, "operation": operation, "result": data},
            operation=operation,
            view=view,
            budget=budget,
        )
    except (ValueError, KeyError, sqlite3.Error) as exc:
        code = (
            "company_kernel_not_activated"
            if "not activated" in str(exc)
            else "company_gateway_conflict"
        )
        return _error(operation, exc, view=view, budget=budget, code=code)
