"""Immutable Company Kernel v1 records and exact identity helpers.

The module contains no persistence or runtime action. It defines only the
irreducible company-domain facts accepted by the V3-1B architecture gate and the
canonicalisation needed to identify them. Execution state remains in the
canonical Task and Run planes.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


COMPANY_KERNEL_SCHEMA_COMPONENT: Final[str] = "company_kernel"
COMPANY_KERNEL_SCHEMA_VERSION: Final[int] = 3
COMPANY_KERNEL_MODEL_VERSION: Final[str] = "company_kernel.v1"

COMPANY_ID_DOMAIN: Final[str] = "soma.company_kernel.company.v1"
MISSION_ID_DOMAIN: Final[str] = "soma.company_kernel.mission.v1"
PLAN_REVISION_ID_DOMAIN: Final[str] = "soma.company_kernel.plan_revision.v1"
WORK_PACKAGE_ID_DOMAIN: Final[str] = "soma.company_kernel.work_package.v1"
OUTCOME_ID_DOMAIN: Final[str] = "soma.company_kernel.outcome.v1"
ATTEMPT_ID_DOMAIN: Final[str] = "soma.company_kernel.attempt.v1"
ACCEPTANCE_ID_DOMAIN: Final[str] = "soma.company_kernel.acceptance.v1"
RECONCILIATION_ID_DOMAIN: Final[str] = "soma.company_kernel.reconciliation.v1"

_SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{64}$")
_ID_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "company_id": re.compile(r"^company_[a-f0-9]{24}$"),
    "mission_id": re.compile(r"^mission_[a-f0-9]{24}$"),
    "plan_revision_id": re.compile(r"^planrev_[a-f0-9]{24}$"),
    "work_package_id": re.compile(r"^workpkg_[a-f0-9]{24}$"),
    "outcome_id": re.compile(r"^outcome_[a-f0-9]{24}$"),
    "attempt_id": re.compile(r"^wpattempt_[a-f0-9]{24}$"),
    "acceptance_commit_id": re.compile(r"^accept_[a-f0-9]{24}$"),
    "reconciliation_id": re.compile(r"^kreconcile_[a-f0-9]{24}$"),
}
_ID_PREFIXES: Final[dict[str, str]] = {
    COMPANY_ID_DOMAIN: "company",
    MISSION_ID_DOMAIN: "mission",
    PLAN_REVISION_ID_DOMAIN: "planrev",
    WORK_PACKAGE_ID_DOMAIN: "workpkg",
    OUTCOME_ID_DOMAIN: "outcome",
    ATTEMPT_ID_DOMAIN: "wpattempt",
    ACCEPTANCE_ID_DOMAIN: "accept",
    RECONCILIATION_ID_DOMAIN: "kreconcile",
}

# These keys identify a route, worker, process, Task or Run. They may occur in a
# WorkPackageAttempt route descriptor, but never in the route-neutral contract
# used to derive one substantive outcome identity.
ROUTE_SPECIFIC_CONTRACT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "provider",
        "provider_id",
        "model",
        "model_id",
        "profile",
        "profile_id",
        "executable_profile",
        "argv",
        "environment",
        "session",
        "session_id",
        "native_session_id",
        "task_id",
        "run_id",
        "pid",
        "process_id",
        "worker_id",
    }
)


def canonical_json(payload: Any) -> str:
    """Return the sole Company Kernel JSON representation."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(domain: str, payload: Any) -> str:
    """Hash one exact payload in an explicit identity domain."""
    if domain not in _ID_PREFIXES:
        raise ValueError(f"unknown company-kernel identity domain: {domain}")
    material = f"{domain}\0{canonical_json(payload)}".encode("utf-8")
    return sha256(material).hexdigest()


def derive_identity(domain: str, payload: Any) -> str:
    """Derive one opaque 24-hex identity from exact canonical material."""
    prefix = _ID_PREFIXES.get(domain)
    if prefix is None:
        raise ValueError(f"unknown company-kernel identity domain: {domain}")
    return f"{prefix}_{canonical_hash(domain, payload)[:24]}"


def validate_opaque(value: str, field: str, *, max_length: int = 512) -> str:
    """Validate shape without trimming, case-folding or otherwise inferring identity."""
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{field} must be a non-empty opaque string")
    if "\x00" in value:
        raise ValueError(f"{field} contains an embedded NUL")
    return value


def validate_sha256(value: str, field: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return value
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def validate_kernel_id(value: str, field: str) -> str:
    pattern = _ID_PATTERNS[field]
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def require_canonical_object_json(value: str, field: str) -> dict[str, Any]:
    validate_opaque(value, field, max_length=200_000)
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{field} must encode one JSON object")
    if canonical_json(decoded) != value:
        raise ValueError(f"{field} must use canonical sorted compact JSON")
    return decoded


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


def normalize_work_package_contract(
    *, contract_version: str, contract: dict[str, Any]
) -> dict[str, Any]:
    """Canonicalise bounded route-neutral intent and reject route authority leakage."""
    validate_opaque(contract_version, "contract_version", max_length=128)
    if not isinstance(contract, dict) or not contract:
        raise ValueError("contract must be a non-empty object")
    route_key = _find_route_specific_key(contract)
    if route_key:
        raise ValueError(f"route-specific field is forbidden in WorkPackage contract: {route_key}")
    return {
        "schema": WORK_PACKAGE_ID_DOMAIN,
        "contract_version": contract_version,
        "contract": json.loads(canonical_json(contract)),
    }


def work_package_contract_hash(
    *, contract_version: str, contract: dict[str, Any]
) -> str:
    return canonical_hash(
        WORK_PACKAGE_ID_DOMAIN,
        normalize_work_package_contract(
            contract_version=contract_version,
            contract=contract,
        ),
    )


def normalize_outcome_identity(
    *,
    mission_id: str,
    plan_revision_id: str,
    package_key: str,
    contract_hash: str,
    project_id: str,
    resource_id: str,
    scope_generation: int,
) -> dict[str, Any]:
    """Return the complete route-independent outcome identity material."""
    validate_kernel_id(mission_id, "mission_id")
    validate_kernel_id(plan_revision_id, "plan_revision_id")
    validate_opaque(package_key, "package_key", max_length=128)
    validate_sha256(contract_hash, "contract_hash")
    validate_opaque(project_id, "project_id", max_length=128)
    validate_opaque(resource_id, "resource_id", max_length=128)
    if not isinstance(scope_generation, int) or scope_generation < 1:
        raise ValueError("scope_generation must be at least 1")
    return {
        "schema": OUTCOME_ID_DOMAIN,
        "mission_id": mission_id,
        "plan_revision_id": plan_revision_id,
        "package_key": package_key,
        "contract_hash": contract_hash,
        "project_id": project_id,
        "resource_id": resource_id,
        "scope_generation": scope_generation,
    }


def outcome_id_for(**kwargs: Any) -> str:
    return derive_identity(OUTCOME_ID_DOMAIN, normalize_outcome_identity(**kwargs))


def route_request_hash(route_descriptor: dict[str, Any]) -> str:
    """Hash route-specific material without affecting substantive outcome identity."""
    if not isinstance(route_descriptor, dict) or not route_descriptor:
        raise ValueError("route_descriptor must be a non-empty object")
    return canonical_hash(
        ATTEMPT_ID_DOMAIN,
        {"schema": ATTEMPT_ID_DOMAIN, "route": route_descriptor},
    )


class _FrozenKernelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Company(_FrozenKernelRecord):
    company_id: str
    company_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=500)
    executive_authority_ref: str = Field(min_length=1, max_length=128)
    creation_request_id: str = Field(min_length=1, max_length=128)
    creation_request_hash: str
    created_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.company_id, "company_id")
        validate_sha256(self.creation_request_hash, "creation_request_hash")
        return self


class Mission(_FrozenKernelRecord):
    mission_id: str
    company_id: str
    mission_key: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    mission_contract_json: str = Field(min_length=2, max_length=200_000)
    mission_contract_hash: str
    accountable_owner_ref: str = Field(min_length=1, max_length=128)
    acceptance_authority_ref: str = Field(min_length=1, max_length=128)
    current_plan_revision_id: str | None = None
    plan_state_version: int = Field(default=0, ge=0)
    kernel_state_version: int = Field(default=0, ge=0)
    creation_request_id: str = Field(min_length=1, max_length=128)
    creation_request_hash: str
    created_at: str = Field(min_length=1, max_length=128)
    updated_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.mission_id, "mission_id")
        validate_kernel_id(self.company_id, "company_id")
        if self.current_plan_revision_id is not None:
            validate_kernel_id(self.current_plan_revision_id, "plan_revision_id")
        contract = require_canonical_object_json(
            self.mission_contract_json, "mission_contract_json"
        )
        validate_sha256(self.mission_contract_hash, "mission_contract_hash")
        if canonical_hash(MISSION_ID_DOMAIN, contract) != self.mission_contract_hash:
            raise ValueError("mission_contract_hash does not match canonical contract")
        validate_sha256(self.creation_request_hash, "creation_request_hash")
        if self.accountable_owner_ref != self.acceptance_authority_ref:
            raise ValueError("kernel-of-one Mission owner and acceptance authority must match")
        return self


class PlanRevision(_FrozenKernelRecord):
    plan_revision_id: str
    mission_id: str
    revision_number: int = Field(ge=1)
    parent_plan_revision_id: str | None = None
    plan_contract_json: str = Field(min_length=2, max_length=200_000)
    plan_content_hash: str
    deliberation_ref: str = Field(default="", max_length=2048)
    deliberation_hash: str = ""
    accepted_by_ref: str = Field(min_length=1, max_length=128)
    acceptance_basis_ref: str = Field(default="", max_length=2048)
    controller_request_id: str = Field(min_length=1, max_length=128)
    request_hash: str
    accepted_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.plan_revision_id, "plan_revision_id")
        validate_kernel_id(self.mission_id, "mission_id")
        if self.parent_plan_revision_id is not None:
            validate_kernel_id(self.parent_plan_revision_id, "plan_revision_id")
        contract = require_canonical_object_json(self.plan_contract_json, "plan_contract_json")
        validate_sha256(self.plan_content_hash, "plan_content_hash")
        if canonical_hash(PLAN_REVISION_ID_DOMAIN, contract) != self.plan_content_hash:
            raise ValueError("plan_content_hash does not match canonical plan")
        validate_sha256(self.deliberation_hash, "deliberation_hash", allow_empty=True)
        validate_sha256(self.request_hash, "request_hash")
        return self


class WorkPackage(_FrozenKernelRecord):
    work_package_id: str
    mission_id: str
    plan_revision_id: str
    package_key: str = Field(min_length=1, max_length=128)
    outcome_id: str
    project_id: str = Field(min_length=1, max_length=128)
    target_resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    contract_version: str = Field(min_length=1, max_length=128)
    contract_json: str = Field(min_length=2, max_length=200_000)
    contract_hash: str
    topology: Literal["single_active"] = "single_active"
    accountable_owner_ref: str = Field(min_length=1, max_length=128)
    acceptance_authority_ref: str = Field(min_length=1, max_length=128)
    deliberation_ref: str = Field(default="", max_length=2048)
    evidence_requirements_ref: str = Field(default="", max_length=2048)
    evidence_requirements_hash: str = ""
    controller_request_id: str = Field(min_length=1, max_length=128)
    request_hash: str
    created_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.work_package_id, "work_package_id")
        validate_kernel_id(self.mission_id, "mission_id")
        validate_kernel_id(self.plan_revision_id, "plan_revision_id")
        validate_kernel_id(self.outcome_id, "outcome_id")
        contract = require_canonical_object_json(self.contract_json, "contract_json")
        expected_hash = work_package_contract_hash(
            contract_version=self.contract_version,
            contract=contract,
        )
        validate_sha256(self.contract_hash, "contract_hash")
        if expected_hash != self.contract_hash:
            raise ValueError("contract_hash does not match canonical WorkPackage contract")
        expected_outcome = outcome_id_for(
            mission_id=self.mission_id,
            plan_revision_id=self.plan_revision_id,
            package_key=self.package_key,
            contract_hash=self.contract_hash,
            project_id=self.project_id,
            resource_id=self.target_resource_id,
            scope_generation=self.scope_generation,
        )
        if expected_outcome != self.outcome_id:
            raise ValueError("outcome_id does not match route-independent identity")
        validate_sha256(
            self.evidence_requirements_hash,
            "evidence_requirements_hash",
            allow_empty=True,
        )
        if bool(self.evidence_requirements_ref) != bool(self.evidence_requirements_hash):
            raise ValueError(
                "evidence requirements reference and hash must appear together"
            )
        validate_sha256(self.request_hash, "request_hash")
        if self.accountable_owner_ref != self.acceptance_authority_ref:
            raise ValueError("kernel-of-one WorkPackage authorities must match")
        return self


class WorkPackageAttempt(_FrozenKernelRecord):
    attempt_id: str
    work_package_id: str
    outcome_id: str
    task_id: str = Field(min_length=1, max_length=128)
    route_request_hash: str
    route_descriptor_json: str = Field(min_length=2, max_length=200_000)
    supersedes_attempt_id: str | None = None
    containment_evidence_ref: str = Field(default="", max_length=2048)
    containment_evidence_hash: str = ""
    controller_request_id: str = Field(min_length=1, max_length=128)
    request_hash: str
    created_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.attempt_id, "attempt_id")
        validate_kernel_id(self.work_package_id, "work_package_id")
        validate_kernel_id(self.outcome_id, "outcome_id")
        if self.supersedes_attempt_id is not None:
            validate_kernel_id(self.supersedes_attempt_id, "attempt_id")
            if self.supersedes_attempt_id == self.attempt_id:
                raise ValueError("an attempt cannot supersede itself")
        descriptor = require_canonical_object_json(
            self.route_descriptor_json, "route_descriptor_json"
        )
        validate_sha256(self.route_request_hash, "route_request_hash")
        if route_request_hash(descriptor) != self.route_request_hash:
            raise ValueError("route_request_hash does not match route descriptor")
        validate_sha256(
            self.containment_evidence_hash,
            "containment_evidence_hash",
            allow_empty=True,
        )
        if bool(self.containment_evidence_ref) != bool(self.containment_evidence_hash):
            raise ValueError("containment evidence reference and hash must appear together")
        validate_sha256(self.request_hash, "request_hash")
        return self


class AcceptanceCommit(_FrozenKernelRecord):
    acceptance_commit_id: str
    company_id: str
    mission_id: str
    work_package_id: str
    outcome_id: str
    attempt_id: str
    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    result_published_hash: str
    public_result_source_sha256: str
    acceptance_authority_ref: str = Field(min_length=1, max_length=128)
    acceptance_basis_ref: str = Field(min_length=1, max_length=2048)
    acceptance_basis_hash: str = ""
    controller_request_id: str = Field(min_length=1, max_length=128)
    request_hash: str
    accepted_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.acceptance_commit_id, "acceptance_commit_id")
        validate_kernel_id(self.company_id, "company_id")
        validate_kernel_id(self.mission_id, "mission_id")
        validate_kernel_id(self.work_package_id, "work_package_id")
        validate_kernel_id(self.outcome_id, "outcome_id")
        validate_kernel_id(self.attempt_id, "attempt_id")
        validate_sha256(self.result_published_hash, "result_published_hash")
        validate_sha256(
            self.public_result_source_sha256,
            "public_result_source_sha256",
        )
        validate_sha256(
            self.acceptance_basis_hash,
            "acceptance_basis_hash",
            allow_empty=True,
        )
        validate_sha256(self.request_hash, "request_hash")
        return self


class KernelReconciliationReceipt(_FrozenKernelRecord):
    reconciliation_id: str
    mission_id: str
    trigger_kind: Literal["owner_turn", "package_completion"]
    trigger_ref: str = Field(min_length=1, max_length=2048)
    observed_kernel_state_version: int = Field(ge=0)
    selected_transition: Literal[
        "no_op",
        "plan_selected",
        "package_defined",
        "attempt_reserved",
        "acceptance_candidate_ready",
        "outcome_accepted",
    ]
    target_ref: str = Field(default="", max_length=2048)
    effect_hash: str
    created_at: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_record(self):
        validate_kernel_id(self.reconciliation_id, "reconciliation_id")
        validate_kernel_id(self.mission_id, "mission_id")
        validate_sha256(self.effect_hash, "effect_hash")
        return self
