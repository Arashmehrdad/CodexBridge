"""Internal atomic graph-capable PlanRevision acceptance service.

The service owns Company Kernel graph definition only. It never launches a Task,
Run, provider, scheduler, or public gateway. One ``BEGIN IMMEDIATE`` transaction
binds an immutable PlanRevision to its complete normalized WorkPackage DAG.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .graph_models import (
    DEPENDENCY_EDGE_ID_DOMAIN,
    PLAN_GRAPH_SCHEMA_VERSION,
    PlanGraphDependencyEdgeV1,
    PlanGraphManifestV1,
    PlanGraphNodeV1,
)
from .models import (
    PLAN_REVISION_ID_DOMAIN,
    ROUTE_SPECIFIC_CONTRACT_KEYS,
    WORK_PACKAGE_ID_DOMAIN,
    PlanRevision,
    WorkPackage,
    canonical_hash,
    canonical_json,
    derive_identity,
    outcome_id_for,
    validate_kernel_id,
    validate_opaque,
    validate_sha256,
    work_package_contract_hash,
)
from .schema import schema_state
from .store import CompanyKernelStore


PLAN_GRAPH_ACCEPTANCE_REQUEST_DOMAIN: Final[str] = (
    "soma.company_kernel.plan_graph_acceptance_request.v1"
)
WORK_PACKAGE_REQUEST_DOMAIN: Final[str] = "soma.company_kernel.work_package_request.v1"
DEPENDENCY_EDGE_ROW_ID_DOMAIN: Final[str] = "soma.company_kernel.dependency_edge_row.v1"


class GraphAcceptanceError(ValueError):
    """Deterministic graph-acceptance rejection."""


class GraphAcceptanceConflict(GraphAcceptanceError):
    """The caller's expected/replay identity conflicts with durable truth."""


class GraphAcceptanceIntegrityError(GraphAcceptanceError):
    """Normalized graph facts cannot reproduce their immutable manifest."""


class WorkPackageContractMaterialV1(BaseModel):
    """Exact route-neutral material used to create one immutable WorkPackage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = Field(min_length=1, max_length=128)
    contract: dict[str, Any]
    deliberation_ref: str = Field(default="", max_length=2048)
    evidence_requirements_ref: str = Field(default="", max_length=2048)
    evidence_requirements_hash: str = ""

    @model_validator(mode="after")
    def _validate_material(self):
        # The incumbent helper also rejects provider/Task/Run/session route facts.
        work_package_contract_hash(
            contract_version=self.contract_version,
            contract=self.contract,
        )
        validate_sha256(
            self.evidence_requirements_hash,
            "evidence_requirements_hash",
            allow_empty=True,
        )
        if bool(self.evidence_requirements_ref) != bool(
            self.evidence_requirements_hash
        ):
            raise ValueError(
                "evidence requirements reference and hash must appear together"
            )
        return self


class GraphAcceptanceResultV1(BaseModel):
    """Internal deterministic acceptance/replay receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    created: bool
    replay_kind: Literal["none", "request", "content"]
    plan_revision_id: str
    plan_content_hash: str
    graph_manifest_hash: str
    request_hash: str
    revision_number: int
    package_ids: dict[str, str]
    edge_ids: tuple[str, ...]


FaultInjector = Callable[[str, sqlite3.Connection], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_hash(domain: str, payload: Any) -> str:
    material = f"{domain}\0{canonical_json(payload)}".encode("utf-8")
    return sha256(material).hexdigest()


def _find_route_specific_key(value: Any, path: str = "contract") -> str:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key.lower() in ROUTE_SPECIFIC_CONTRACT_KEYS:
                return f"{path}.{key}"
            found = _find_route_specific_key(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_route_specific_key(child, f"{path}[{index}]")
            if found:
                return found
    return ""


def _canonical_object(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphAcceptanceError(f"{field} must be an object")
    try:
        return json.loads(canonical_json(dict(value)))
    except (TypeError, ValueError) as exc:
        raise GraphAcceptanceError(f"{field} must be JSON-serializable") from exc


def _normalize_manifest(
    graph_manifest: PlanGraphManifestV1 | Mapping[str, Any],
) -> PlanGraphManifestV1:
    if isinstance(graph_manifest, PlanGraphManifestV1):
        return graph_manifest
    try:
        return PlanGraphManifestV1.model_validate(graph_manifest)
    except Exception as exc:
        raise GraphAcceptanceError(f"invalid graph manifest: {exc}") from exc


def _normalize_package_materials(
    *,
    manifest: PlanGraphManifestV1,
    work_package_contracts: Mapping[
        str, WorkPackageContractMaterialV1 | Mapping[str, Any]
    ],
) -> dict[str, WorkPackageContractMaterialV1]:
    if not isinstance(work_package_contracts, Mapping):
        raise GraphAcceptanceError(
            "work_package_contracts must be keyed by package_key"
        )
    expected_keys = {node.package_key for node in manifest.package_nodes}
    supplied_keys = {str(key) for key in work_package_contracts}
    if supplied_keys != expected_keys:
        missing = sorted(expected_keys - supplied_keys)
        unknown = sorted(supplied_keys - expected_keys)
        raise GraphAcceptanceError(
            f"work package material keys must exactly match manifest; missing={missing}, "
            f"unknown={unknown}"
        )

    nodes = {node.package_key: node for node in manifest.package_nodes}
    normalized: dict[str, WorkPackageContractMaterialV1] = {}
    for package_key in sorted(expected_keys):
        raw = work_package_contracts[package_key]
        try:
            material = (
                raw
                if isinstance(raw, WorkPackageContractMaterialV1)
                else WorkPackageContractMaterialV1.model_validate(raw)
            )
        except Exception as exc:
            raise GraphAcceptanceError(
                f"invalid WorkPackage material for {package_key}: {exc}"
            ) from exc
        contract_hash = work_package_contract_hash(
            contract_version=material.contract_version,
            contract=material.contract,
        )
        node = nodes[package_key]
        if contract_hash != node.work_package_contract_hash:
            raise GraphAcceptanceConflict(
                f"WorkPackage contract hash does not match manifest node {package_key}"
            )
        expected_evidence_hash = node.evidence_requirements_hash or ""
        if material.evidence_requirements_hash != expected_evidence_hash:
            raise GraphAcceptanceConflict(
                f"evidence requirements hash does not match manifest node {package_key}"
            )
        normalized[package_key] = material
    return normalized


def _request_hash(
    *,
    company_id: str,
    mission_id: str,
    expected_current_plan_revision_id: str | None,
    expected_plan_state_version: int,
    expected_kernel_state_version: int,
    project_id: str,
    resource_id: str,
    scope_generation: int,
    accepted_by_ref: str,
    acceptance_basis_ref: str,
    deliberation_ref: str,
    deliberation_hash: str,
    plan_contract_base: dict[str, Any],
    manifest: PlanGraphManifestV1,
    package_materials: Mapping[str, WorkPackageContractMaterialV1],
) -> str:
    packages = {
        package_key: {
            "contract_version": material.contract_version,
            "contract": json.loads(canonical_json(material.contract)),
            "deliberation_ref": material.deliberation_ref,
            "evidence_requirements_ref": material.evidence_requirements_ref,
            "evidence_requirements_hash": material.evidence_requirements_hash,
        }
        for package_key, material in sorted(package_materials.items())
    }
    payload = {
        "company_id": company_id,
        "mission_id": mission_id,
        "expected_current_plan_revision_id": expected_current_plan_revision_id,
        "expected_plan_state_version": expected_plan_state_version,
        "expected_kernel_state_version": expected_kernel_state_version,
        "project_id": project_id,
        "resource_id": resource_id,
        "scope_generation": scope_generation,
        "accepted_by_ref": accepted_by_ref,
        "acceptance_basis_ref": acceptance_basis_ref,
        "deliberation_ref": deliberation_ref,
        "deliberation_hash": deliberation_hash,
        "plan_contract_base": plan_contract_base,
        "graph_manifest_hash": manifest.graph_manifest_hash,
        "work_package_contracts": packages,
    }
    return _domain_hash(PLAN_GRAPH_ACCEPTANCE_REQUEST_DOMAIN, payload)


def _package_controller_request_id(root_request_id: str, package_key: str) -> str:
    digest = sha256(f"{root_request_id}\0{package_key}".encode("utf-8")).hexdigest()
    return f"planpkg_{digest[:40]}"


def _work_package_identity_payload(
    *,
    mission_id: str,
    plan_revision_id: str,
    package_key: str,
    contract_hash: str,
    project_id: str,
    resource_id: str,
    scope_generation: int,
) -> dict[str, Any]:
    return {
        "schema": WORK_PACKAGE_ID_DOMAIN,
        "mission_id": mission_id,
        "plan_revision_id": plan_revision_id,
        "package_key": package_key,
        "contract_hash": contract_hash,
        "project_id": project_id,
        "resource_id": resource_id,
        "scope_generation": scope_generation,
    }


def _edge_row_id(
    *,
    plan_revision_id: str,
    upstream_work_package_id: str,
    downstream_work_package_id: str,
    edge: PlanGraphDependencyEdgeV1,
) -> str:
    payload = {
        "schema": DEPENDENCY_EDGE_ID_DOMAIN,
        "plan_revision_id": plan_revision_id,
        "upstream_work_package_id": upstream_work_package_id,
        "downstream_work_package_id": downstream_work_package_id,
        "requirement": edge.requirement,
        "evidence_selector_hash": edge.evidence_selector_hash or "",
    }
    return f"depedge_{_domain_hash(DEPENDENCY_EDGE_ROW_ID_DOMAIN, payload)[:24]}"


def _invoke_fault(
    injector: FaultInjector | None,
    phase: str,
    conn: sqlite3.Connection,
) -> None:
    if injector is not None:
        injector(phase, conn)


def _reconstruct_manifest(
    conn: sqlite3.Connection,
    *,
    mission_row: sqlite3.Row,
    plan_revision_id: str,
) -> PlanGraphManifestV1:
    package_rows = conn.execute(
        """
        SELECT
            work_package_id, package_key, contract_hash, target_resource_id,
            evidence_requirements_hash
        FROM work_packages
        WHERE mission_id = ? AND plan_revision_id = ?
        ORDER BY package_key
        """,
        (mission_row["mission_id"], plan_revision_id),
    ).fetchall()
    nodes = [
        PlanGraphNodeV1(
            package_key=str(row["package_key"]),
            work_package_contract_hash=str(row["contract_hash"]),
            target_resource_id=str(row["target_resource_id"]),
            evidence_requirements_hash=(
                str(row["evidence_requirements_hash"])
                if str(row["evidence_requirements_hash"])
                else None
            ),
        )
        for row in package_rows
    ]

    edge_rows = conn.execute(
        """
        SELECT
            upstream.package_key AS upstream_package_key,
            downstream.package_key AS downstream_package_key,
            dependency.requirement,
            dependency.evidence_selector_ref,
            dependency.evidence_selector_hash
        FROM work_package_dependencies AS dependency
        JOIN work_packages AS upstream
          ON upstream.work_package_id = dependency.upstream_work_package_id
         AND upstream.mission_id = dependency.mission_id
         AND upstream.plan_revision_id = dependency.plan_revision_id
        JOIN work_packages AS downstream
          ON downstream.work_package_id = dependency.downstream_work_package_id
         AND downstream.mission_id = dependency.mission_id
         AND downstream.plan_revision_id = dependency.plan_revision_id
        WHERE dependency.mission_id = ? AND dependency.plan_revision_id = ?
        ORDER BY
            upstream.package_key,
            downstream.package_key,
            dependency.requirement,
            dependency.evidence_selector_hash
        """,
        (mission_row["mission_id"], plan_revision_id),
    ).fetchall()
    edges = [
        PlanGraphDependencyEdgeV1(
            upstream_package_key=str(row["upstream_package_key"]),
            downstream_package_key=str(row["downstream_package_key"]),
            requirement=str(row["requirement"]),
            evidence_selector_ref=(
                str(row["evidence_selector_ref"])
                if str(row["evidence_selector_ref"])
                else None
            ),
            evidence_selector_hash=(
                str(row["evidence_selector_hash"])
                if str(row["evidence_selector_hash"])
                else None
            ),
        )
        for row in edge_rows
    ]
    return PlanGraphManifestV1(
        mission_id=str(mission_row["mission_id"]),
        project_id=str(mission_row["project_id"]),
        resource_id=str(mission_row["resource_id"]),
        scope_generation=int(mission_row["scope_generation"]),
        package_nodes=nodes,
        dependency_edges=edges,
    )


def _existing_result(
    conn: sqlite3.Connection,
    *,
    mission_row: sqlite3.Row,
    plan_row: sqlite3.Row,
    replay_kind: Literal["request", "content", "none"],
    expected_manifest_hash: str,
    created: bool,
) -> GraphAcceptanceResultV1:
    manifest_row = conn.execute(
        "SELECT * FROM plan_graph_manifests WHERE plan_revision_id = ?",
        (plan_row["plan_revision_id"],),
    ).fetchone()
    if manifest_row is None:
        raise GraphAcceptanceIntegrityError(
            "accepted PlanRevision is missing graph manifest"
        )
    if str(manifest_row["manifest_hash"]) != expected_manifest_hash:
        raise GraphAcceptanceConflict(
            "existing PlanRevision has a different graph manifest"
        )

    reconstructed = _reconstruct_manifest(
        conn,
        mission_row=mission_row,
        plan_revision_id=str(plan_row["plan_revision_id"]),
    )
    if reconstructed.graph_manifest_hash != str(manifest_row["manifest_hash"]):
        raise GraphAcceptanceIntegrityError(
            "normalized WorkPackages/dependencies do not reproduce manifest hash"
        )
    reconstructed_json = canonical_json(reconstructed.canonical_identity_payload())
    if reconstructed_json != str(manifest_row["manifest_json"]):
        raise GraphAcceptanceIntegrityError(
            "normalized WorkPackages/dependencies do not reproduce manifest JSON"
        )
    if len(reconstructed.package_nodes) != int(manifest_row["package_count"]):
        raise GraphAcceptanceIntegrityError(
            "manifest package count does not match rows"
        )
    if len(reconstructed.dependency_edges) != int(manifest_row["edge_count"]):
        raise GraphAcceptanceIntegrityError("manifest edge count does not match rows")

    package_rows = conn.execute(
        "SELECT package_key, work_package_id FROM work_packages "
        "WHERE mission_id = ? AND plan_revision_id = ? ORDER BY package_key",
        (mission_row["mission_id"], plan_row["plan_revision_id"]),
    ).fetchall()
    edge_rows = conn.execute(
        "SELECT edge_id FROM work_package_dependencies "
        "WHERE mission_id = ? AND plan_revision_id = ? ORDER BY edge_id",
        (mission_row["mission_id"], plan_row["plan_revision_id"]),
    ).fetchall()
    return GraphAcceptanceResultV1(
        created=created,
        replay_kind=replay_kind,
        plan_revision_id=str(plan_row["plan_revision_id"]),
        plan_content_hash=str(plan_row["plan_content_hash"]),
        graph_manifest_hash=str(manifest_row["manifest_hash"]),
        request_hash=str(plan_row["request_hash"]),
        revision_number=int(plan_row["revision_number"]),
        package_ids={
            str(row["package_key"]): str(row["work_package_id"]) for row in package_rows
        },
        edge_ids=tuple(str(row["edge_id"]) for row in edge_rows),
    )


def accept_plan_graph(
    store: CompanyKernelStore,
    *,
    company_id: str,
    mission_id: str,
    expected_current_plan_revision_id: str | None,
    expected_plan_state_version: int,
    expected_kernel_state_version: int,
    project_id: str,
    resource_id: str,
    scope_generation: int,
    controller_request_id: str,
    accepted_by_ref: str,
    acceptance_basis_ref: str,
    plan_contract_base: Mapping[str, Any],
    graph_manifest: PlanGraphManifestV1 | Mapping[str, Any],
    work_package_contracts: Mapping[
        str, WorkPackageContractMaterialV1 | Mapping[str, Any]
    ],
    deliberation_ref: str = "",
    deliberation_hash: str = "",
    accepted_at: str | None = None,
    _fault_injector: FaultInjector | None = None,
) -> GraphAcceptanceResultV1:
    """Atomically accept one complete immutable WorkPackage DAG.

    Exact request replay returns the already committed PlanRevision even if later
    scope/current-plan state has moved. A different request carrying content that
    is already the current PlanRevision converges to that immutable content. A
    historical non-current content collision fails closed because graph reselection
    is a distinct semantic transition not defined by this service.
    """

    validate_kernel_id(company_id, "company_id")
    validate_kernel_id(mission_id, "mission_id")
    if expected_current_plan_revision_id is not None:
        validate_kernel_id(expected_current_plan_revision_id, "plan_revision_id")
    if expected_plan_state_version < 0 or expected_kernel_state_version < 0:
        raise GraphAcceptanceError("expected kernel versions must be non-negative")
    validate_opaque(project_id, "project_id", max_length=128)
    validate_opaque(resource_id, "resource_id", max_length=128)
    if scope_generation < 1:
        raise GraphAcceptanceError("scope_generation must be at least 1")
    validate_opaque(controller_request_id, "controller_request_id", max_length=128)
    validate_opaque(accepted_by_ref, "accepted_by_ref", max_length=128)
    validate_opaque(acceptance_basis_ref, "acceptance_basis_ref", max_length=2048)
    validate_sha256(deliberation_hash, "deliberation_hash", allow_empty=True)
    if accepted_at is not None:
        validate_opaque(accepted_at, "accepted_at", max_length=128)

    manifest = _normalize_manifest(graph_manifest)
    if (
        manifest.mission_id != mission_id
        or manifest.project_id != project_id
        or manifest.resource_id != resource_id
        or manifest.scope_generation != scope_generation
    ):
        raise GraphAcceptanceConflict(
            "manifest Mission/ProjectScope identity does not match acceptance request"
        )

    base_contract = _canonical_object(plan_contract_base, "plan_contract_base")
    if "plan_graph" in base_contract:
        raise GraphAcceptanceError("plan_contract_base may not pre-populate plan_graph")
    route_key = _find_route_specific_key(base_contract, "plan_contract_base")
    if route_key:
        raise GraphAcceptanceError(
            f"route-specific field is forbidden in plan contract: {route_key}"
        )

    package_materials = _normalize_package_materials(
        manifest=manifest,
        work_package_contracts=work_package_contracts,
    )
    accepted_contract = dict(base_contract)
    accepted_contract["plan_graph"] = {
        "schema_version": PLAN_GRAPH_SCHEMA_VERSION,
        "manifest_hash": manifest.graph_manifest_hash,
    }
    accepted_contract = json.loads(canonical_json(accepted_contract))
    plan_content_hash = canonical_hash(PLAN_REVISION_ID_DOMAIN, accepted_contract)
    plan_revision_id = derive_identity(
        PLAN_REVISION_ID_DOMAIN,
        {
            "schema": PLAN_REVISION_ID_DOMAIN,
            "mission_id": mission_id,
            "plan_content_hash": plan_content_hash,
        },
    )
    request_hash = _request_hash(
        company_id=company_id,
        mission_id=mission_id,
        expected_current_plan_revision_id=expected_current_plan_revision_id,
        expected_plan_state_version=expected_plan_state_version,
        expected_kernel_state_version=expected_kernel_state_version,
        project_id=project_id,
        resource_id=resource_id,
        scope_generation=scope_generation,
        accepted_by_ref=accepted_by_ref,
        acceptance_basis_ref=acceptance_basis_ref,
        deliberation_ref=deliberation_ref,
        deliberation_hash=deliberation_hash,
        plan_contract_base=base_contract,
        manifest=manifest,
        package_materials=package_materials,
    )
    accepted_at_value = accepted_at or _utc_now()

    result: GraphAcceptanceResultV1 | None = None
    with store.transaction() as conn:
        state = schema_state(conn)
        if not state["up_to_date"] or int(state["schema_version"]) != 2:
            raise GraphAcceptanceError("Company Kernel schema v2 must be installed")
        if state["active_capability"] is not False:
            raise GraphAcceptanceError(
                "graph acceptance requires the inactive internal gate"
            )

        mission_row = conn.execute(
            """
            SELECT missions.*, companies.executive_authority_ref
            FROM missions
            JOIN companies ON companies.company_id = missions.company_id
            WHERE missions.mission_id = ? AND missions.company_id = ?
            """,
            (mission_id, company_id),
        ).fetchone()
        if mission_row is None:
            raise GraphAcceptanceError("company/mission identity was not found")
        if str(mission_row["acceptance_authority_ref"]) != accepted_by_ref:
            raise GraphAcceptanceConflict(
                "accepted_by_ref is not Mission acceptance authority"
            )
        if str(mission_row["executive_authority_ref"]) != accepted_by_ref:
            raise GraphAcceptanceConflict(
                "accepted_by_ref is not Company executive authority"
            )

        request_replay = conn.execute(
            "SELECT * FROM plan_revisions WHERE mission_id = ? AND controller_request_id = ?",
            (mission_id, controller_request_id),
        ).fetchone()
        if request_replay is not None:
            if str(request_replay["request_hash"]) != request_hash:
                raise GraphAcceptanceConflict(
                    "controller_request_id was already used for different graph content"
                )
            if (
                str(request_replay["plan_revision_id"]) != plan_revision_id
                or str(request_replay["plan_content_hash"]) != plan_content_hash
            ):
                raise GraphAcceptanceIntegrityError(
                    "request replay identity does not match derived PlanRevision"
                )
            result = _existing_result(
                conn,
                mission_row=mission_row,
                plan_row=request_replay,
                replay_kind="request",
                expected_manifest_hash=manifest.graph_manifest_hash,
                created=False,
            )
        else:
            if (
                str(mission_row["project_id"]) != project_id
                or str(mission_row["resource_id"]) != resource_id
                or int(mission_row["scope_generation"]) != scope_generation
            ):
                raise GraphAcceptanceConflict(
                    "acceptance ProjectScope identity does not match immutable Mission scope"
                )
            project_row = conn.execute(
                "SELECT lifecycle_state, scope_generation FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None or str(project_row["lifecycle_state"]) != "active":
                raise GraphAcceptanceConflict("ProjectScope project is not active")
            if int(project_row["scope_generation"]) != scope_generation:
                raise GraphAcceptanceConflict("ProjectScope generation changed")
            binding = conn.execute(
                "SELECT 1 FROM project_resource_bindings "
                "WHERE project_id = ? AND resource_id = ?",
                (project_id, resource_id),
            ).fetchone()
            if binding is None:
                raise GraphAcceptanceConflict("ProjectScope resource binding is absent")

            content_replay = conn.execute(
                "SELECT * FROM plan_revisions WHERE mission_id = ? AND plan_content_hash = ?",
                (mission_id, plan_content_hash),
            ).fetchone()
            if content_replay is not None:
                if str(content_replay["plan_revision_id"]) != plan_revision_id:
                    raise GraphAcceptanceIntegrityError(
                        "content-identical PlanRevision has a different derived identity"
                    )
                if str(content_replay["request_hash"]) != request_hash:
                    raise GraphAcceptanceConflict(
                        "content-identical PlanRevision was accepted under different request metadata"
                    )
                if (
                    str(mission_row["current_plan_revision_id"] or "")
                    != plan_revision_id
                ):
                    raise GraphAcceptanceConflict(
                        "identical graph content exists as a non-current historical PlanRevision"
                    )
                result = _existing_result(
                    conn,
                    mission_row=mission_row,
                    plan_row=content_replay,
                    replay_kind="content",
                    expected_manifest_hash=manifest.graph_manifest_hash,
                    created=False,
                )
            else:
                current_plan = mission_row["current_plan_revision_id"]
                current_plan_value = (
                    str(current_plan) if current_plan is not None else None
                )
                if current_plan_value != expected_current_plan_revision_id:
                    raise GraphAcceptanceConflict("current PlanRevision changed")
                if (
                    int(mission_row["plan_state_version"])
                    != expected_plan_state_version
                ):
                    raise GraphAcceptanceConflict("plan_state_version changed")
                if (
                    int(mission_row["kernel_state_version"])
                    != expected_kernel_state_version
                ):
                    raise GraphAcceptanceConflict("kernel_state_version changed")

                revision_number = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(revision_number), 0) + 1 "
                        "FROM plan_revisions WHERE mission_id = ?",
                        (mission_id,),
                    ).fetchone()[0]
                )
                plan = PlanRevision(
                    plan_revision_id=plan_revision_id,
                    mission_id=mission_id,
                    revision_number=revision_number,
                    parent_plan_revision_id=current_plan_value,
                    plan_contract_json=canonical_json(accepted_contract),
                    plan_content_hash=plan_content_hash,
                    deliberation_ref=deliberation_ref,
                    deliberation_hash=deliberation_hash,
                    accepted_by_ref=accepted_by_ref,
                    acceptance_basis_ref=acceptance_basis_ref,
                    controller_request_id=controller_request_id,
                    request_hash=request_hash,
                    accepted_at=accepted_at_value,
                )
                conn.execute(
                    """
                    INSERT INTO plan_revisions(
                        plan_revision_id, mission_id, revision_number,
                        parent_plan_revision_id, plan_contract_json, plan_content_hash,
                        deliberation_ref, deliberation_hash, accepted_by_ref,
                        acceptance_basis_ref, controller_request_id, request_hash,
                        accepted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.plan_revision_id,
                        plan.mission_id,
                        plan.revision_number,
                        plan.parent_plan_revision_id,
                        plan.plan_contract_json,
                        plan.plan_content_hash,
                        plan.deliberation_ref,
                        plan.deliberation_hash,
                        plan.accepted_by_ref,
                        plan.acceptance_basis_ref,
                        plan.controller_request_id,
                        plan.request_hash,
                        plan.accepted_at,
                    ),
                )
                _invoke_fault(_fault_injector, "after_plan_insert", conn)

                package_ids: dict[str, str] = {}
                nodes = {node.package_key: node for node in manifest.package_nodes}
                for package_index, package_key in enumerate(sorted(nodes)):
                    node = nodes[package_key]
                    material = package_materials[package_key]
                    contract_hash = node.work_package_contract_hash
                    identity_payload = _work_package_identity_payload(
                        mission_id=mission_id,
                        plan_revision_id=plan_revision_id,
                        package_key=package_key,
                        contract_hash=contract_hash,
                        project_id=project_id,
                        resource_id=node.target_resource_id,
                        scope_generation=scope_generation,
                    )
                    work_package_id = derive_identity(
                        WORK_PACKAGE_ID_DOMAIN,
                        identity_payload,
                    )
                    outcome_id = outcome_id_for(
                        mission_id=mission_id,
                        plan_revision_id=plan_revision_id,
                        package_key=package_key,
                        contract_hash=contract_hash,
                        project_id=project_id,
                        resource_id=node.target_resource_id,
                        scope_generation=scope_generation,
                    )
                    package_request_hash = _domain_hash(
                        WORK_PACKAGE_REQUEST_DOMAIN,
                        {
                            **identity_payload,
                            "contract_version": material.contract_version,
                            "contract": json.loads(canonical_json(material.contract)),
                            "deliberation_ref": material.deliberation_ref,
                            "evidence_requirements_ref": material.evidence_requirements_ref,
                            "evidence_requirements_hash": material.evidence_requirements_hash,
                        },
                    )
                    package = WorkPackage(
                        work_package_id=work_package_id,
                        mission_id=mission_id,
                        plan_revision_id=plan_revision_id,
                        package_key=package_key,
                        outcome_id=outcome_id,
                        project_id=project_id,
                        target_resource_id=node.target_resource_id,
                        scope_generation=scope_generation,
                        contract_version=material.contract_version,
                        contract_json=canonical_json(material.contract),
                        contract_hash=contract_hash,
                        accountable_owner_ref=str(mission_row["accountable_owner_ref"]),
                        acceptance_authority_ref=str(
                            mission_row["acceptance_authority_ref"]
                        ),
                        deliberation_ref=material.deliberation_ref,
                        evidence_requirements_ref=material.evidence_requirements_ref,
                        evidence_requirements_hash=material.evidence_requirements_hash,
                        controller_request_id=_package_controller_request_id(
                            controller_request_id,
                            package_key,
                        ),
                        request_hash=package_request_hash,
                        created_at=accepted_at_value,
                    )
                    conn.execute(
                        """
                        INSERT INTO work_packages(
                            work_package_id, mission_id, plan_revision_id, package_key,
                            outcome_id, project_id, target_resource_id, scope_generation,
                            contract_version, contract_json, contract_hash, topology,
                            accountable_owner_ref, acceptance_authority_ref,
                            deliberation_ref, evidence_requirements_ref,
                            controller_request_id, request_hash, created_at,
                            evidence_requirements_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            package.work_package_id,
                            package.mission_id,
                            package.plan_revision_id,
                            package.package_key,
                            package.outcome_id,
                            package.project_id,
                            package.target_resource_id,
                            package.scope_generation,
                            package.contract_version,
                            package.contract_json,
                            package.contract_hash,
                            package.topology,
                            package.accountable_owner_ref,
                            package.acceptance_authority_ref,
                            package.deliberation_ref,
                            package.evidence_requirements_ref,
                            package.controller_request_id,
                            package.request_hash,
                            package.created_at,
                            package.evidence_requirements_hash,
                        ),
                    )
                    package_ids[package_key] = work_package_id
                    _invoke_fault(
                        _fault_injector,
                        f"after_package:{package_index}",
                        conn,
                    )

                sorted_edges = sorted(
                    manifest.dependency_edges,
                    key=lambda edge: edge.canonical_sort_key(),
                )
                for edge_index, edge in enumerate(sorted_edges):
                    upstream_id = package_ids[edge.upstream_package_key]
                    downstream_id = package_ids[edge.downstream_package_key]
                    edge_id = _edge_row_id(
                        plan_revision_id=plan_revision_id,
                        upstream_work_package_id=upstream_id,
                        downstream_work_package_id=downstream_id,
                        edge=edge,
                    )
                    conn.execute(
                        """
                        INSERT INTO work_package_dependencies(
                            edge_id, mission_id, plan_revision_id,
                            upstream_work_package_id, downstream_work_package_id,
                            requirement, evidence_selector_ref, evidence_selector_hash,
                            edge_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            edge_id,
                            mission_id,
                            plan_revision_id,
                            upstream_id,
                            downstream_id,
                            edge.requirement,
                            edge.evidence_selector_ref or "",
                            edge.evidence_selector_hash or "",
                            edge.edge_hash,
                            accepted_at_value,
                        ),
                    )
                    _invoke_fault(_fault_injector, f"after_edge:{edge_index}", conn)

                manifest_json = canonical_json(manifest.canonical_identity_payload())
                conn.execute(
                    """
                    INSERT INTO plan_graph_manifests(
                        plan_revision_id, mission_id, schema_version, manifest_json,
                        manifest_hash, package_count, edge_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan_revision_id,
                        mission_id,
                        PLAN_GRAPH_SCHEMA_VERSION,
                        manifest_json,
                        manifest.graph_manifest_hash,
                        len(manifest.package_nodes),
                        len(manifest.dependency_edges),
                        accepted_at_value,
                    ),
                )
                _invoke_fault(_fault_injector, "before_reconstruction", conn)
                reconstructed = _reconstruct_manifest(
                    conn,
                    mission_row=mission_row,
                    plan_revision_id=plan_revision_id,
                )
                if reconstructed.graph_manifest_hash != manifest.graph_manifest_hash:
                    raise GraphAcceptanceIntegrityError(
                        "normalized graph reconstruction hash mismatch"
                    )
                if (
                    canonical_json(reconstructed.canonical_identity_payload())
                    != manifest_json
                ):
                    raise GraphAcceptanceIntegrityError(
                        "normalized graph reconstruction JSON mismatch"
                    )

                _invoke_fault(_fault_injector, "before_mission_cas", conn)
                if current_plan_value is None:
                    cursor = conn.execute(
                        """
                        UPDATE missions
                        SET current_plan_revision_id = ?, plan_state_version = ?,
                            kernel_state_version = ?, updated_at = ?
                        WHERE mission_id = ? AND current_plan_revision_id IS NULL
                          AND plan_state_version = ? AND kernel_state_version = ?
                        """,
                        (
                            plan_revision_id,
                            expected_plan_state_version + 1,
                            expected_kernel_state_version + 1,
                            accepted_at_value,
                            mission_id,
                            expected_plan_state_version,
                            expected_kernel_state_version,
                        ),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE missions
                        SET current_plan_revision_id = ?, plan_state_version = ?,
                            kernel_state_version = ?, updated_at = ?
                        WHERE mission_id = ? AND current_plan_revision_id = ?
                          AND plan_state_version = ? AND kernel_state_version = ?
                        """,
                        (
                            plan_revision_id,
                            expected_plan_state_version + 1,
                            expected_kernel_state_version + 1,
                            accepted_at_value,
                            mission_id,
                            current_plan_value,
                            expected_plan_state_version,
                            expected_kernel_state_version,
                        ),
                    )
                if cursor.rowcount != 1:
                    raise GraphAcceptanceConflict("Mission current-plan CAS lost race")
                _invoke_fault(_fault_injector, "after_mission_cas", conn)

                plan_row = conn.execute(
                    "SELECT * FROM plan_revisions WHERE plan_revision_id = ?",
                    (plan_revision_id,),
                ).fetchone()
                result = _existing_result(
                    conn,
                    mission_row=mission_row,
                    plan_row=plan_row,
                    replay_kind="none",
                    expected_manifest_hash=manifest.graph_manifest_hash,
                    created=True,
                )

    if result is None:
        raise GraphAcceptanceIntegrityError("graph acceptance produced no result")
    return result
