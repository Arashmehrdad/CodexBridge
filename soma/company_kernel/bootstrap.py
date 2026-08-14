"""Trusted internal Company/Mission bootstrap for the Kernel of One.

This module creates only the immutable company-domain root required by the
already-accepted Company Kernel services. It does not migrate the database,
launch Tasks or Runs, call a provider, register a public gateway, or create any
acceptance/reconciliation authority.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.config import AppConfig, resolve_repo_identity
from soma.project_scope.store import ProjectScopeStore

from .models import (
    COMPANY_ID_DOMAIN,
    COMPANY_KERNEL_SCHEMA_VERSION,
    MISSION_ID_DOMAIN,
    Company,
    Mission,
    canonical_hash,
    canonical_json,
    derive_identity,
    validate_opaque,
)
from .schema import schema_state
from .store import CompanyKernelStore


BOOTSTRAP_REQUEST_DOMAIN: Final[str] = "soma.company_kernel.bootstrap_request.v1"
COMPANY_CREATION_REQUEST_DOMAIN: Final[str] = (
    "soma.company_kernel.company_creation_request.v1"
)
MISSION_CREATION_REQUEST_DOMAIN: Final[str] = (
    "soma.company_kernel.mission_creation_request.v1"
)


class KernelBootstrapError(ValueError):
    """The requested trusted kernel root cannot be established."""


class KernelBootstrapConflict(KernelBootstrapError):
    """Caller material conflicts with durable or configured authority."""


class KernelBootstrapIntegrityError(KernelBootstrapError):
    """Durable bootstrap state is partial or internally inconsistent."""


class KernelBootstrapRequestV1(BaseModel):
    """Exact caller assertion for one Company/Mission root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    controller_request_id: str = Field(min_length=1, max_length=128)
    company_key: str = Field(min_length=1, max_length=128)
    company_display_name: str = Field(min_length=1, max_length=500)
    mission_key: str = Field(min_length=1, max_length=128)
    mission_contract: dict[str, Any]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    executive_authority_ref: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_request(self):
        for field_name in (
            "controller_request_id",
            "company_key",
            "company_display_name",
            "mission_key",
            "project_id",
            "repo_name",
            "resource_id",
            "executive_authority_ref",
        ):
            validate_opaque(str(getattr(self, field_name)), field_name, max_length=500)
        if not isinstance(self.mission_contract, dict):
            raise ValueError("mission_contract must be one JSON object")
        try:
            encoded = canonical_json(self.mission_contract)
        except (TypeError, ValueError) as exc:
            raise ValueError("mission_contract must be JSON-serializable") from exc
        if len(encoded.encode("utf-8")) > 200_000:
            raise ValueError("mission_contract exceeds 200000 UTF-8 bytes")
        return self


class KernelBootstrapResultV1(BaseModel):
    """Deterministic internal bootstrap/replay receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    created: bool
    replay_kind: Literal["none", "request"]
    request_hash: str
    company: Company
    mission: Mission


FaultInjector = Callable[[str, sqlite3.Connection], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_hash(domain: str, payload: Any) -> str:
    material = f"{domain}\0{canonical_json(payload)}".encode("utf-8")
    return sha256(material).hexdigest()


def _canonical_object(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        decoded = json.loads(canonical_json(dict(value)))
    except (TypeError, ValueError) as exc:
        raise KernelBootstrapError("mission_contract must be JSON-serializable") from exc
    if not isinstance(decoded, dict):
        raise KernelBootstrapError("mission_contract must be one JSON object")
    return decoded


def _invoke_fault(
    injector: FaultInjector | None,
    phase: str,
    conn: sqlite3.Connection,
) -> None:
    if injector is not None:
        injector(phase, conn)


def _company_payload(
    *, company_key: str, executive_authority_ref: str
) -> dict[str, Any]:
    return {
        "schema": COMPANY_ID_DOMAIN,
        "company_key": company_key,
        "executive_authority_ref": executive_authority_ref,
    }


def _mission_identity_payload(
    *,
    company_id: str,
    mission_key: str,
    mission_contract_hash: str,
    project_id: str,
    resource_id: str,
    scope_generation: int,
) -> dict[str, Any]:
    return {
        "schema": MISSION_ID_DOMAIN,
        "company_id": company_id,
        "mission_key": mission_key,
        "mission_contract_hash": mission_contract_hash,
        "project_id": project_id,
        "resource_id": resource_id,
        "scope_generation": scope_generation,
    }


def _expected_records(
    request: KernelBootstrapRequestV1,
    *,
    canonical_repo_name: str,
    trusted_executive: str,
    created_at: str,
) -> tuple[Company, Mission, str]:
    mission_contract = _canonical_object(request.mission_contract)
    mission_contract_json = canonical_json(mission_contract)
    mission_contract_hash = canonical_hash(MISSION_ID_DOMAIN, mission_contract)
    company_id = derive_identity(
        COMPANY_ID_DOMAIN,
        _company_payload(
            company_key=request.company_key,
            executive_authority_ref=trusted_executive,
        ),
    )
    mission_id = derive_identity(
        MISSION_ID_DOMAIN,
        _mission_identity_payload(
            company_id=company_id,
            mission_key=request.mission_key,
            mission_contract_hash=mission_contract_hash,
            project_id=request.project_id,
            resource_id=request.resource_id,
            scope_generation=request.scope_generation,
        ),
    )
    company_request_material = {
        "company_key": request.company_key,
        "display_name": request.company_display_name,
        "executive_authority_ref": trusted_executive,
    }
    mission_request_material = {
        "company_id": company_id,
        "mission_key": request.mission_key,
        "mission_contract": mission_contract,
        "project_id": request.project_id,
        "repo_name": canonical_repo_name,
        "resource_id": request.resource_id,
        "scope_generation": request.scope_generation,
        "accountable_owner_ref": trusted_executive,
        "acceptance_authority_ref": trusted_executive,
    }
    root_material = {
        "controller_request_id": request.controller_request_id,
        "company": company_request_material,
        "mission": mission_request_material,
    }
    company = Company(
        company_id=company_id,
        company_key=request.company_key,
        display_name=request.company_display_name,
        executive_authority_ref=trusted_executive,
        creation_request_id=request.controller_request_id,
        creation_request_hash=_domain_hash(
            COMPANY_CREATION_REQUEST_DOMAIN, company_request_material
        ),
        created_at=created_at,
    )
    mission = Mission(
        mission_id=mission_id,
        company_id=company_id,
        mission_key=request.mission_key,
        project_id=request.project_id,
        resource_id=request.resource_id,
        scope_generation=request.scope_generation,
        mission_contract_json=mission_contract_json,
        mission_contract_hash=mission_contract_hash,
        accountable_owner_ref=trusted_executive,
        acceptance_authority_ref=trusted_executive,
        current_plan_revision_id=None,
        plan_state_version=0,
        kernel_state_version=0,
        creation_request_id=request.controller_request_id,
        creation_request_hash=_domain_hash(
            MISSION_CREATION_REQUEST_DOMAIN, mission_request_material
        ),
        created_at=created_at,
        updated_at=created_at,
    )
    return company, mission, _domain_hash(BOOTSTRAP_REQUEST_DOMAIN, root_material)


def _row_company(row: sqlite3.Row) -> Company:
    return Company.model_validate(dict(row))


def _row_mission(row: sqlite3.Row) -> Mission:
    return Mission.model_validate(dict(row))


def _assert_exact_company(actual: Company, expected: Company) -> None:
    fields = (
        "company_id",
        "company_key",
        "display_name",
        "executive_authority_ref",
        "creation_request_id",
        "creation_request_hash",
    )
    if any(getattr(actual, field) != getattr(expected, field) for field in fields):
        raise KernelBootstrapConflict(
            "controller request or Company identity conflicts with durable Company"
        )


def _assert_exact_mission(actual: Mission, expected: Mission) -> None:
    fields = (
        "mission_id",
        "company_id",
        "mission_key",
        "project_id",
        "resource_id",
        "scope_generation",
        "mission_contract_json",
        "mission_contract_hash",
        "accountable_owner_ref",
        "acceptance_authority_ref",
        "creation_request_id",
        "creation_request_hash",
    )
    if any(getattr(actual, field) != getattr(expected, field) for field in fields):
        raise KernelBootstrapConflict(
            "controller request or Mission identity conflicts with durable Mission"
        )


def _request_replay(
    conn: sqlite3.Connection,
    *,
    expected_company: Company,
    expected_mission: Mission,
) -> tuple[Company, Mission] | None:
    company_row = conn.execute(
        "SELECT * FROM companies WHERE creation_request_id = ?",
        (expected_company.creation_request_id,),
    ).fetchone()
    mission_row = conn.execute(
        "SELECT * FROM missions WHERE creation_request_id = ?",
        (expected_mission.creation_request_id,),
    ).fetchone()
    if company_row is None and mission_row is None:
        return None
    if company_row is None or mission_row is None:
        raise KernelBootstrapIntegrityError(
            "bootstrap controller request has only a partial Company/Mission root"
        )
    company = _row_company(company_row)
    mission = _row_mission(mission_row)
    _assert_exact_company(company, expected_company)
    _assert_exact_mission(mission, expected_mission)
    return company, mission


def _assert_no_identity_collision(
    conn: sqlite3.Connection,
    *,
    company: Company,
    mission: Mission,
) -> None:
    company_rows = conn.execute(
        "SELECT * FROM companies WHERE company_id = ? OR company_key = ?",
        (company.company_id, company.company_key),
    ).fetchall()
    if company_rows:
        if len(company_rows) != 1:
            raise KernelBootstrapIntegrityError(
                "Company identity resolves to multiple durable rows"
            )
        _assert_exact_company(_row_company(company_rows[0]), company)
        raise KernelBootstrapIntegrityError(
            "exact Company exists without the matching bootstrap Mission request"
        )
    mission_rows = conn.execute(
        "SELECT * FROM missions WHERE mission_id = ? OR (company_id = ? AND mission_key = ?)",
        (mission.mission_id, mission.company_id, mission.mission_key),
    ).fetchall()
    if mission_rows:
        if len(mission_rows) != 1:
            raise KernelBootstrapIntegrityError(
                "Mission identity resolves to multiple durable rows"
            )
        _assert_exact_mission(_row_mission(mission_rows[0]), mission)
        raise KernelBootstrapIntegrityError(
            "exact Mission exists outside the matching bootstrap controller request"
        )


def bootstrap_company_mission(
    config: AppConfig,
    request: KernelBootstrapRequestV1,
    *,
    store: CompanyKernelStore | None = None,
    scope_store: ProjectScopeStore | None = None,
    created_at: str | None = None,
    _fault_injector: FaultInjector | None = None,
) -> KernelBootstrapResultV1:
    """Atomically create or replay one trusted Company/Mission root."""

    runtime = config.company_kernel
    if not runtime.enabled:
        raise KernelBootstrapError("Company Kernel runtime capability is disabled")
    trusted_executive = runtime.executive_authority_ref
    if request.executive_authority_ref != trusted_executive:
        raise KernelBootstrapConflict(
            "executive authority assertion does not match trusted configuration"
        )
    try:
        canonical_repo_name, repo_root, _repo = resolve_repo_identity(
            config, request.repo_name
        )
    except (KeyError, ValueError) as exc:
        raise KernelBootstrapError(str(exc)) from exc

    kernel_store = store or CompanyKernelStore(config.resolve_runs_dir())
    project_scope = scope_store or ProjectScopeStore(config.resolve_runs_dir())
    created_at_value = created_at or _utc_now()
    expected_company, expected_mission, request_hash = _expected_records(
        request,
        canonical_repo_name=canonical_repo_name,
        trusted_executive=trusted_executive,
        created_at=created_at_value,
    )

    with kernel_store.transaction() as conn:
        state = schema_state(conn)
        if (
            not state["up_to_date"]
            or int(state["schema_version"]) != COMPANY_KERNEL_SCHEMA_VERSION
        ):
            raise KernelBootstrapError(
                f"Company Kernel schema v{COMPANY_KERNEL_SCHEMA_VERSION} must be installed"
            )
        if state["active_capability"] is not False:
            raise KernelBootstrapError(
                "bootstrap source gate requires the inactive internal Company Kernel"
            )

        replay = _request_replay(
            conn,
            expected_company=expected_company,
            expected_mission=expected_mission,
        )
        if replay is not None:
            company, mission = replay
            return KernelBootstrapResultV1(
                created=False,
                replay_kind="request",
                request_hash=request_hash,
                company=company,
                mission=mission,
            )

        try:
            binding = project_scope.resolve_repository(
                project_id=request.project_id,
                repo_name=canonical_repo_name,
                repository_root=repo_root,
                conn=conn,
            )
        except Exception as exc:
            raise KernelBootstrapConflict(str(exc)) from exc
        if binding.resource_id != request.resource_id:
            raise KernelBootstrapConflict(
                "ProjectScope resource identity differs from bootstrap request"
            )
        if binding.scope_generation != request.scope_generation:
            raise KernelBootstrapConflict(
                "ProjectScope generation differs from bootstrap request"
            )

        _assert_no_identity_collision(
            conn,
            company=expected_company,
            mission=expected_mission,
        )
        _invoke_fault(_fault_injector, "before_company_insert", conn)
        conn.execute(
            """
            INSERT INTO companies(
                company_id, company_key, display_name, executive_authority_ref,
                creation_request_id, creation_request_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expected_company.company_id,
                expected_company.company_key,
                expected_company.display_name,
                expected_company.executive_authority_ref,
                expected_company.creation_request_id,
                expected_company.creation_request_hash,
                expected_company.created_at,
            ),
        )
        _invoke_fault(_fault_injector, "after_company_insert", conn)
        conn.execute(
            """
            INSERT INTO missions(
                mission_id, company_id, mission_key, project_id, resource_id,
                scope_generation, mission_contract_json, mission_contract_hash,
                accountable_owner_ref, acceptance_authority_ref,
                current_plan_revision_id, plan_state_version, kernel_state_version,
                creation_request_id, creation_request_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0, ?, ?, ?, ?)
            """,
            (
                expected_mission.mission_id,
                expected_mission.company_id,
                expected_mission.mission_key,
                expected_mission.project_id,
                expected_mission.resource_id,
                expected_mission.scope_generation,
                expected_mission.mission_contract_json,
                expected_mission.mission_contract_hash,
                expected_mission.accountable_owner_ref,
                expected_mission.acceptance_authority_ref,
                expected_mission.creation_request_id,
                expected_mission.creation_request_hash,
                expected_mission.created_at,
                expected_mission.updated_at,
            ),
        )
        _invoke_fault(_fault_injector, "after_mission_insert", conn)

        company = _row_company(
            conn.execute(
                "SELECT * FROM companies WHERE company_id = ?",
                (expected_company.company_id,),
            ).fetchone()
        )
        mission = _row_mission(
            conn.execute(
                "SELECT * FROM missions WHERE mission_id = ?",
                (expected_mission.mission_id,),
            ).fetchone()
        )
        _assert_exact_company(company, expected_company)
        _assert_exact_mission(mission, expected_mission)

    return KernelBootstrapResultV1(
        created=True,
        replay_kind="none",
        request_hash=request_hash,
        company=company,
        mission=mission,
    )
