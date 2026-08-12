"""Pure immutable graph and dependency-proof contracts for Company Kernel.

This module deliberately contains no persistence, scheduler, Task launch, or
runtime activation.  It freezes the route-neutral graph identity used by a
future PlanRevision transaction and the exact mechanical proof family used by
future downstream admission.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .models import canonical_json, validate_kernel_id, validate_opaque, validate_sha256


PLAN_GRAPH_SCHEMA_VERSION: Final[str] = "plan_graph_manifest.v1"
DEPENDENCY_PROOF_SCHEMA_VERSION: Final[str] = "dependency_satisfaction_proof.v1"

MAX_PACKAGES_PER_PLAN_GRAPH: Final[int] = 32
MAX_DEPENDENCY_EDGES_PER_PLAN_GRAPH: Final[int] = 128

PLAN_GRAPH_ID_DOMAIN: Final[str] = "soma.company_kernel.plan_graph.v1"
DEPENDENCY_EDGE_ID_DOMAIN: Final[str] = "soma.company_kernel.dependency_edge.v1"
DEPENDENCY_PROOF_ID_DOMAIN: Final[str] = "soma.company_kernel.dependency_proof.v1"

DependencyRequirement = Literal[
    "accepted_outcome",
    "published_success",
    "evidence_available",
    "settled",
]
SettlementClass = Literal[
    "terminal",
    "cancelled",
    "contained",
    "uncertain_contained",
]


def _domain_hash(domain: str, payload: Any) -> str:
    """Return a lowercase SHA-256 over one explicit graph identity domain."""

    material = f"{domain}\0{canonical_json(payload)}".encode("utf-8")
    return sha256(material).hexdigest()


class _FrozenGraphRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PlanGraphNodeV1(_FrozenGraphRecord):
    package_key: str = Field(min_length=1, max_length=128)
    work_package_contract_hash: str
    target_resource_id: str = Field(min_length=1, max_length=128)
    evidence_requirements_hash: str | None = None

    @model_validator(mode="after")
    def _validate_node(self):
        validate_opaque(self.package_key, "package_key", max_length=128)
        validate_sha256(
            self.work_package_contract_hash,
            "work_package_contract_hash",
        )
        validate_opaque(
            self.target_resource_id,
            "target_resource_id",
            max_length=128,
        )
        if self.evidence_requirements_hash is not None:
            validate_sha256(
                self.evidence_requirements_hash,
                "evidence_requirements_hash",
            )
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "package_key": self.package_key,
            "work_package_contract_hash": self.work_package_contract_hash,
            "target_resource_id": self.target_resource_id,
            "evidence_requirements_hash": self.evidence_requirements_hash,
        }


class PlanGraphDependencyEdgeV1(_FrozenGraphRecord):
    upstream_package_key: str = Field(min_length=1, max_length=128)
    downstream_package_key: str = Field(min_length=1, max_length=128)
    requirement: DependencyRequirement
    evidence_selector_ref: str | None = None
    evidence_selector_hash: str | None = None

    @model_validator(mode="after")
    def _validate_edge(self):
        validate_opaque(
            self.upstream_package_key,
            "upstream_package_key",
            max_length=128,
        )
        validate_opaque(
            self.downstream_package_key,
            "downstream_package_key",
            max_length=128,
        )
        if self.upstream_package_key == self.downstream_package_key:
            raise ValueError("dependency edge cannot point to the same package")

        if self.requirement == "evidence_available":
            if (
                self.evidence_selector_ref is None
                or self.evidence_selector_hash is None
            ):
                raise ValueError(
                    "evidence_available requires evidence_selector_ref and "
                    "evidence_selector_hash"
                )
            validate_opaque(
                self.evidence_selector_ref,
                "evidence_selector_ref",
                max_length=2048,
            )
            validate_sha256(
                self.evidence_selector_hash,
                "evidence_selector_hash",
            )
        elif (
            self.evidence_selector_ref is not None
            or self.evidence_selector_hash is not None
        ):
            raise ValueError("only evidence_available may carry an evidence selector")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "upstream_package_key": self.upstream_package_key,
            "downstream_package_key": self.downstream_package_key,
            "requirement": self.requirement,
            "evidence_selector_ref": self.evidence_selector_ref,
            "evidence_selector_hash": self.evidence_selector_hash,
        }

    def canonical_sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.upstream_package_key,
            self.downstream_package_key,
            self.requirement,
            self.evidence_selector_hash or "",
        )

    @property
    def edge_hash(self) -> str:
        return _domain_hash(DEPENDENCY_EDGE_ID_DOMAIN, self.canonical_payload())


class PlanGraphManifestV1(_FrozenGraphRecord):
    schema_version: Literal[PLAN_GRAPH_SCHEMA_VERSION] = PLAN_GRAPH_SCHEMA_VERSION
    mission_id: str
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    package_nodes: tuple[PlanGraphNodeV1, ...] = Field(
        min_length=1,
        max_length=MAX_PACKAGES_PER_PLAN_GRAPH,
    )
    dependency_edges: tuple[PlanGraphDependencyEdgeV1, ...] = Field(
        default=(),
        max_length=MAX_DEPENDENCY_EDGES_PER_PLAN_GRAPH,
    )

    @model_validator(mode="after")
    def _validate_manifest(self):
        validate_kernel_id(self.mission_id, "mission_id")
        validate_opaque(self.project_id, "project_id", max_length=128)
        validate_opaque(self.resource_id, "resource_id", max_length=128)

        package_keys = [node.package_key for node in self.package_nodes]
        if len(package_keys) != len(set(package_keys)):
            raise ValueError("package_keys must be unique within one plan graph")

        # Company Kernel v1 binds every WorkPackage target resource to the exact
        # Mission ProjectScope resource/generation.  G1.1 preserves that ceiling
        # rather than inventing a broader resource hierarchy.
        escaped = sorted(
            node.package_key
            for node in self.package_nodes
            if node.target_resource_id != self.resource_id
        )
        if escaped:
            raise ValueError(
                "package target resource escapes the Mission resource ceiling: "
                + ", ".join(escaped)
            )

        known_keys = set(package_keys)
        canonical_edge_keys: set[tuple[str, str, str, str]] = set()
        for edge in self.dependency_edges:
            if edge.upstream_package_key not in known_keys:
                raise ValueError(
                    "dependency upstream endpoint is missing from package_nodes: "
                    f"{edge.upstream_package_key}"
                )
            if edge.downstream_package_key not in known_keys:
                raise ValueError(
                    "dependency downstream endpoint is missing from package_nodes: "
                    f"{edge.downstream_package_key}"
                )
            edge_key = edge.canonical_sort_key()
            if edge_key in canonical_edge_keys:
                raise ValueError("duplicate canonical dependency edge")
            canonical_edge_keys.add(edge_key)

        self._reject_cycles()
        return self

    def _reject_cycles(self) -> None:
        adjacency = {node.package_key: [] for node in self.package_nodes}
        indegree = {node.package_key: 0 for node in self.package_nodes}
        for edge in self.dependency_edges:
            adjacency[edge.upstream_package_key].append(edge.downstream_package_key)
            indegree[edge.downstream_package_key] += 1

        ready = sorted(key for key, degree in indegree.items() if degree == 0)
        visited = 0
        while ready:
            current = ready.pop(0)
            visited += 1
            for downstream in sorted(adjacency[current]):
                indegree[downstream] -= 1
                if indegree[downstream] == 0:
                    ready.append(downstream)
                    ready.sort()

        if visited != len(self.package_nodes):
            raise ValueError("plan graph must be acyclic")

    def canonical_identity_payload(self) -> dict[str, Any]:
        nodes = sorted(self.package_nodes, key=lambda node: node.package_key)
        edges = sorted(
            self.dependency_edges,
            key=lambda edge: edge.canonical_sort_key(),
        )
        return {
            "schema_version": self.schema_version,
            "mission_id": self.mission_id,
            "project_id": self.project_id,
            "resource_id": self.resource_id,
            "scope_generation": self.scope_generation,
            "package_nodes": [node.canonical_payload() for node in nodes],
            "dependency_edges": [edge.canonical_payload() for edge in edges],
        }

    @property
    def graph_manifest_hash(self) -> str:
        return _domain_hash(PLAN_GRAPH_ID_DOMAIN, self.canonical_identity_payload())


class AcceptedOutcomeSatisfactionV1(_FrozenGraphRecord):
    kind: Literal["accepted_outcome"] = "accepted_outcome"
    acceptance_commit_id: str
    acceptance_commit_hash: str

    @model_validator(mode="after")
    def _validate_satisfaction(self):
        validate_kernel_id(self.acceptance_commit_id, "acceptance_commit_id")
        validate_sha256(self.acceptance_commit_hash, "acceptance_commit_hash")
        return self


class PublishedSuccessSatisfactionV1(_FrozenGraphRecord):
    kind: Literal["published_success"] = "published_success"
    attempt_id: str
    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    result_published_hash: str
    public_result_source_sha256: str

    @model_validator(mode="after")
    def _validate_satisfaction(self):
        validate_kernel_id(self.attempt_id, "attempt_id")
        validate_opaque(self.task_id, "task_id", max_length=128)
        validate_opaque(self.run_id, "run_id", max_length=128)
        validate_sha256(self.result_published_hash, "result_published_hash")
        validate_sha256(
            self.public_result_source_sha256,
            "public_result_source_sha256",
        )
        return self


class EvidenceAvailableSatisfactionV1(_FrozenGraphRecord):
    kind: Literal["evidence_available"] = "evidence_available"
    evidence_ref: str = Field(min_length=1, max_length=2048)
    evidence_hash: str
    evidence_selector_hash: str

    @model_validator(mode="after")
    def _validate_satisfaction(self):
        validate_opaque(self.evidence_ref, "evidence_ref", max_length=2048)
        validate_sha256(self.evidence_hash, "evidence_hash")
        validate_sha256(self.evidence_selector_hash, "evidence_selector_hash")
        return self


class SettledSatisfactionV1(_FrozenGraphRecord):
    kind: Literal["settled"] = "settled"
    attempt_set_hash: str
    head_attempt_id: str | None = None
    settlement_ref: str = Field(min_length=1, max_length=2048)
    settlement_hash: str
    settlement_class: SettlementClass

    @model_validator(mode="after")
    def _validate_satisfaction(self):
        validate_sha256(self.attempt_set_hash, "attempt_set_hash")
        if self.head_attempt_id is not None:
            validate_kernel_id(self.head_attempt_id, "attempt_id")
        validate_opaque(self.settlement_ref, "settlement_ref", max_length=2048)
        validate_sha256(self.settlement_hash, "settlement_hash")
        return self


DependencySatisfactionV1 = Annotated[
    AcceptedOutcomeSatisfactionV1
    | PublishedSuccessSatisfactionV1
    | EvidenceAvailableSatisfactionV1
    | SettledSatisfactionV1,
    Field(discriminator="kind"),
]
_SATISFACTION_ADAPTER: Final[TypeAdapter[DependencySatisfactionV1]] = TypeAdapter(
    DependencySatisfactionV1
)


def _stable_proof_payload(
    *,
    edge_hash: str,
    requirement: str,
    upstream_work_package_id: str,
    upstream_outcome_id: str,
    downstream_work_package_id: str,
    satisfaction: DependencySatisfactionV1,
) -> dict[str, Any]:
    return {
        "edge_hash": edge_hash,
        "requirement": requirement,
        "upstream_work_package_id": upstream_work_package_id,
        "upstream_outcome_id": upstream_outcome_id,
        "downstream_work_package_id": downstream_work_package_id,
        "satisfaction": satisfaction.model_dump(mode="json"),
    }


class DependencySatisfactionProofV1(_FrozenGraphRecord):
    schema_version: Literal[DEPENDENCY_PROOF_SCHEMA_VERSION] = (
        DEPENDENCY_PROOF_SCHEMA_VERSION
    )
    edge_id: str = Field(min_length=1, max_length=128)
    edge_hash: str
    requirement: DependencyRequirement
    upstream_work_package_id: str
    upstream_outcome_id: str
    downstream_work_package_id: str
    satisfaction: DependencySatisfactionV1
    observed_kernel_state_version: int = Field(ge=0)
    observed_at: str = Field(min_length=1, max_length=128)
    proof_hash: str

    @model_validator(mode="before")
    @classmethod
    def _populate_proof_hash(cls, raw: Any):
        if not isinstance(raw, dict) or "proof_hash" in raw:
            return raw
        required = {
            "edge_hash",
            "requirement",
            "upstream_work_package_id",
            "upstream_outcome_id",
            "downstream_work_package_id",
            "satisfaction",
        }
        if not required.issubset(raw):
            return raw
        values = dict(raw)
        satisfaction = _SATISFACTION_ADAPTER.validate_python(values["satisfaction"])
        values["satisfaction"] = satisfaction
        stable = _stable_proof_payload(
            edge_hash=str(values["edge_hash"]),
            requirement=str(values["requirement"]),
            upstream_work_package_id=str(values["upstream_work_package_id"]),
            upstream_outcome_id=str(values["upstream_outcome_id"]),
            downstream_work_package_id=str(values["downstream_work_package_id"]),
            satisfaction=satisfaction,
        )
        values["proof_hash"] = _domain_hash(DEPENDENCY_PROOF_ID_DOMAIN, stable)
        return values

    @model_validator(mode="after")
    def _validate_proof(self):
        validate_opaque(self.edge_id, "edge_id", max_length=128)
        validate_sha256(self.edge_hash, "edge_hash")
        validate_kernel_id(self.upstream_work_package_id, "work_package_id")
        validate_kernel_id(self.upstream_outcome_id, "outcome_id")
        validate_kernel_id(self.downstream_work_package_id, "work_package_id")
        validate_opaque(self.observed_at, "observed_at", max_length=128)
        validate_sha256(self.proof_hash, "proof_hash")
        if self.requirement != self.satisfaction.kind:
            raise ValueError(
                "dependency proof requirement must match satisfaction kind"
            )
        expected = _domain_hash(
            DEPENDENCY_PROOF_ID_DOMAIN,
            _stable_proof_payload(
                edge_hash=self.edge_hash,
                requirement=self.requirement,
                upstream_work_package_id=self.upstream_work_package_id,
                upstream_outcome_id=self.upstream_outcome_id,
                downstream_work_package_id=self.downstream_work_package_id,
                satisfaction=self.satisfaction,
            ),
        )
        if self.proof_hash != expected:
            raise ValueError(
                "proof_hash does not match stable dependency proof identity"
            )
        return self

    def stable_identity_payload(self) -> dict[str, Any]:
        return _stable_proof_payload(
            edge_hash=self.edge_hash,
            requirement=self.requirement,
            upstream_work_package_id=self.upstream_work_package_id,
            upstream_outcome_id=self.upstream_outcome_id,
            downstream_work_package_id=self.downstream_work_package_id,
            satisfaction=self.satisfaction,
        )
