"""CDX-R1 semantic output and EvidenceSubmission bridge.

The Codex provider may supply semantic claims/evidence only. Canonical Soma work
identity, assignment identity, usage, and provenance are injected mechanically by
this module after the provider output validates against the committed synthetic
packet.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.worker_evidence.models import (
    EvidenceAssignmentV1,
    EvidenceBlockerV1,
    EvidenceByteAccountingV1,
    EvidenceClaimV1,
    EvidenceHashedReferenceV1,
    EvidenceProducerV1,
    EvidenceRecordV1,
    EvidenceSubmissionV1,
    EvidenceUncertaintyV1,
    EvidenceUsageV1,
    EvidenceWorkIdentityV1,
)


CDX_R1_SEMANTIC_SCHEMA_VERSION: Final[str] = "soma.cdx_r1.semantic.v1"
CDX_R1_PACKET_SCHEMA_VERSION: Final[str] = "soma.cdx_r1.synthetic_packet.v1"
CDX_R1_ADAPTER_ID: Final[str] = "soma.reasoning.codex_app_server.cdx-r1"


class CDXR1SemanticValidationError(ValueError):
    """Provider semantic output does not match the frozen synthetic packet."""


class _FrozenPilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CDXR1SemanticClaimV1(_FrozenPilotModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_class: Literal[
        "observation",
        "inference",
        "recommendation",
        "negative_finding",
    ]
    subject_key: str | None = Field(max_length=256)
    statement: str = Field(min_length=1, max_length=4096)
    supports_evidence_ids: tuple[str, ...] = Field(max_length=24)
    opposes_evidence_ids: tuple[str, ...] = Field(max_length=24)
    uncertainty_ids: tuple[str, ...] = Field(max_length=12)


class CDXR1SemanticEvidenceV1(_FrozenPilotModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    record_id: str = Field(min_length=1, max_length=64)
    fact_key: str = Field(min_length=1, max_length=256)
    fact_value: str = Field(max_length=2048)


class CDXR1SemanticUncertaintyV1(_FrozenPilotModel):
    uncertainty_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)
    related_claim_ids: tuple[str, ...] = Field(max_length=12)
    required_resolution: str | None = Field(max_length=2048)


class CDXR1SemanticBlockerV1(_FrozenPilotModel):
    blocker_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)


class CDXR1SemanticPayloadV1(_FrozenPilotModel):
    schema_version: Literal[CDX_R1_SEMANTIC_SCHEMA_VERSION]
    submission_disposition: Literal["complete", "partial", "blocked", "uncertain"]
    executive_summary: str = Field(max_length=1024)
    claims: tuple[CDXR1SemanticClaimV1, ...] = Field(max_length=12)
    evidence: tuple[CDXR1SemanticEvidenceV1, ...] = Field(max_length=24)
    uncertainties: tuple[CDXR1SemanticUncertaintyV1, ...] = Field(max_length=12)
    blockers: tuple[CDXR1SemanticBlockerV1, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_local_references(self):
        claim_ids = [claim.claim_id for claim in self.claims]
        evidence_ids = [item.evidence_id for item in self.evidence]
        uncertainty_ids = [item.uncertainty_id for item in self.uncertainties]
        blocker_ids = [item.blocker_id for item in self.blockers]
        for label, values in (
            ("claim", claim_ids),
            ("evidence", evidence_ids),
            ("uncertainty", uncertainty_ids),
            ("blocker", blocker_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")

        evidence_set = set(evidence_ids)
        uncertainty_set = set(uncertainty_ids)
        claim_set = set(claim_ids)
        for claim in self.claims:
            unknown_evidence = (
                set(claim.supports_evidence_ids) | set(claim.opposes_evidence_ids)
            ) - evidence_set
            if unknown_evidence:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown evidence IDs: "
                    f"{sorted(unknown_evidence)}"
                )
            unknown_uncertainties = set(claim.uncertainty_ids) - uncertainty_set
            if unknown_uncertainties:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown uncertainty IDs: "
                    f"{sorted(unknown_uncertainties)}"
                )
        for uncertainty in self.uncertainties:
            unknown_claims = set(uncertainty.related_claim_ids) - claim_set
            if unknown_claims:
                raise ValueError(
                    f"uncertainty {uncertainty.uncertainty_id} references unknown claim IDs: "
                    f"{sorted(unknown_claims)}"
                )
        return self


class CDXR1UsageV1(_FrozenPilotModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_packet_bytes(path: Path) -> bytes:
    data = Path(path).read_bytes()
    packet = json.loads(data.decode("utf-8"))
    if packet.get("schema_version") != CDX_R1_PACKET_SCHEMA_VERSION:
        raise CDXR1SemanticValidationError("unexpected CDX-R1 packet schema version")
    return data


def packet_hash(packet_bytes: bytes) -> str:
    return sha256_hex(packet_bytes)


def semantic_output_schema() -> dict[str, Any]:
    """Return the exact strict schema supplied to App Server turn/start."""

    return CDXR1SemanticPayloadV1.model_json_schema()


def semantic_prompt(packet_bytes: bytes) -> str:
    packet_text = packet_bytes.decode("utf-8")
    return (
        "You are the read-only CDX-R1 evidence extraction worker. "
        "Use only the PACKET JSON below. Do not use tools, files, network sources, "
        "memory, or unstated assumptions. Return only the object required by the "
        "provided output schema. Use schema_version "
        f"{CDX_R1_SEMANTIC_SCHEMA_VERSION!r}. Every evidence item must copy one "
        "record_id, fact_key, and fact_value exactly from the packet. Every factual "
        "claim must cite exact evidence IDs. The two retry_limit records conflict; "
        "preserve both values and represent the conflict as unresolved uncertainty "
        "rather than selecting a winner.\n\nPACKET JSON:\n" + packet_text
    )


def parse_semantic_output(text: str) -> CDXR1SemanticPayloadV1:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CDXR1SemanticValidationError(
            f"Codex final message is not exact JSON: {exc}"
        ) from exc
    try:
        return CDXR1SemanticPayloadV1.model_validate(value)
    except ValueError as exc:
        raise CDXR1SemanticValidationError(str(exc)) from exc


def _packet_index(
    packet_bytes: bytes,
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    packet = json.loads(packet_bytes.decode("utf-8"))
    if packet.get("schema_version") != CDX_R1_PACKET_SCHEMA_VERSION:
        raise CDXR1SemanticValidationError("unexpected CDX-R1 packet schema version")
    records = packet.get("records")
    if not isinstance(records, list):
        raise CDXR1SemanticValidationError("packet records must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise CDXR1SemanticValidationError("packet record must be an object")
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise CDXR1SemanticValidationError("packet record_id is invalid")
        if record_id in by_id:
            raise CDXR1SemanticValidationError("packet record_id values must be unique")
        by_id[record_id] = record
    required = packet.get("required_fact_keys")
    conflicts = packet.get("expected_conflict_fact_keys")
    if not isinstance(required, list) or not all(isinstance(v, str) for v in required):
        raise CDXR1SemanticValidationError("required_fact_keys is invalid")
    if not isinstance(conflicts, list) or not all(
        isinstance(v, str) for v in conflicts
    ):
        raise CDXR1SemanticValidationError("expected_conflict_fact_keys is invalid")
    return by_id, list(required), list(conflicts)


def validate_semantic_against_packet(
    payload: CDXR1SemanticPayloadV1,
    packet_bytes: bytes,
) -> None:
    records, required_fact_keys, conflict_fact_keys = _packet_index(packet_bytes)
    evidence_by_fact: dict[str, list[CDXR1SemanticEvidenceV1]] = {}
    for evidence in payload.evidence:
        record = records.get(evidence.record_id)
        if record is None:
            raise CDXR1SemanticValidationError(
                f"evidence {evidence.evidence_id} cites unknown record {evidence.record_id}"
            )
        facts = record.get("facts")
        if not isinstance(facts, dict) or evidence.fact_key not in facts:
            raise CDXR1SemanticValidationError(
                f"evidence {evidence.evidence_id} cites unsupported fact_key "
                f"{evidence.fact_key!r} for {evidence.record_id}"
            )
        expected = str(facts[evidence.fact_key])
        if evidence.fact_value != expected:
            raise CDXR1SemanticValidationError(
                f"evidence {evidence.evidence_id} changed packet fact value for "
                f"{evidence.record_id}/{evidence.fact_key}"
            )
        evidence_by_fact.setdefault(evidence.fact_key, []).append(evidence)

    claims_by_fact: dict[str, list[CDXR1SemanticClaimV1]] = {}
    for claim in payload.claims:
        if claim.subject_key:
            claims_by_fact.setdefault(claim.subject_key, []).append(claim)

    for fact_key in required_fact_keys:
        if fact_key not in evidence_by_fact:
            raise CDXR1SemanticValidationError(
                f"required fact_key {fact_key!r} has no exact packet evidence"
            )
        if fact_key not in claims_by_fact:
            raise CDXR1SemanticValidationError(
                f"required fact_key {fact_key!r} has no provider claim"
            )

    uncertainty_by_id = {item.uncertainty_id: item for item in payload.uncertainties}
    for fact_key in conflict_fact_keys:
        values = {item.fact_value for item in evidence_by_fact.get(fact_key, [])}
        if len(values) < 2:
            raise CDXR1SemanticValidationError(
                f"conflict fact_key {fact_key!r} did not preserve both packet values"
            )
        related_claims = claims_by_fact.get(fact_key, [])
        uncertainty_ids = {
            uncertainty_id
            for claim in related_claims
            for uncertainty_id in claim.uncertainty_ids
        }
        if not uncertainty_ids:
            raise CDXR1SemanticValidationError(
                f"conflict fact_key {fact_key!r} was not marked uncertain"
            )
        if not any(
            uncertainty_id in uncertainty_by_id
            and set(uncertainty_by_id[uncertainty_id].related_claim_ids)
            & {claim.claim_id for claim in related_claims}
            for uncertainty_id in uncertainty_ids
        ):
            raise CDXR1SemanticValidationError(
                f"conflict fact_key {fact_key!r} uncertainty lacks claim linkage"
            )


def semantic_payload_hash(payload: CDXR1SemanticPayloadV1) -> str:
    return sha256_hex(canonical_json_bytes(payload.model_dump(mode="json")))


def _non_negative_int(value: Any) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )


def extract_usage(token_usage_events: tuple[dict[str, Any], ...]) -> CDXR1UsageV1:
    """Project the latest raw App Server token-usage snapshot without invention."""

    if not token_usage_events:
        return CDXR1UsageV1()
    params = token_usage_events[-1]
    block = params.get("tokenUsage") or params.get("usage") or {}
    if not isinstance(block, dict):
        return CDXR1UsageV1()
    candidate = block.get("total") or block.get("last") or block
    if not isinstance(candidate, dict):
        candidate = {}

    def pick(*names: str) -> int:
        for name in names:
            if name in candidate:
                return _non_negative_int(candidate.get(name))
        return 0

    return CDXR1UsageV1(
        input_tokens=pick("inputTokens", "input_tokens"),
        cached_input_tokens=pick("cachedInputTokens", "cached_input_tokens"),
        output_tokens=pick("outputTokens", "output_tokens"),
        reasoning_output_tokens=pick(
            "reasoningOutputTokens",
            "reasoning_output_tokens",
        ),
        total_tokens=pick("totalTokens", "total_tokens"),
    )


def build_evidence_submission(
    *,
    payload: CDXR1SemanticPayloadV1,
    packet_bytes: bytes,
    task_id: str,
    backend_ref: str,
    assignment_ref: str,
    provider_model: str,
    provider_thread_id: str,
    usage: CDXR1UsageV1,
    wall_time_seconds: float,
    provenance_refs: tuple[tuple[str, str], ...] = (),
    raw_provider_ref: str = "",
    raw_provider_hash: str = "",
) -> EvidenceSubmissionV1:
    """Inject canonical identity/provenance around validated provider semantics."""

    validate_semantic_against_packet(payload, packet_bytes)
    assignment_hash = packet_hash(packet_bytes)
    records, _required, _conflicts = _packet_index(packet_bytes)
    payload_digest = semantic_payload_hash(payload)
    submission_digest = sha256_hex(
        f"{task_id}\0{backend_ref}\0{payload_digest}".encode("utf-8")
    )

    evidence_records = []
    for item in payload.evidence:
        record = records[item.record_id]
        excerpt = str(record.get("text") or "")[:512] or None
        evidence_records.append(
            EvidenceRecordV1(
                evidence_id=item.evidence_id,
                source_kind="synthetic_packet",
                source_ref=assignment_ref,
                source_hash=assignment_hash,
                locator=f"record:{item.record_id}",
                content_type="application/json",
                excerpt=excerpt,
                fact_key=item.fact_key,
                fact_value=item.fact_value,
            )
        )

    provenance = tuple(
        EvidenceHashedReferenceV1(ref=ref, hash=digest)
        for ref, digest in provenance_refs
    )
    retrieval = ()
    if raw_provider_ref or raw_provider_hash:
        if not raw_provider_ref or not raw_provider_hash:
            raise ValueError("raw provider ref/hash must appear together")
        retrieval = (
            EvidenceHashedReferenceV1(
                ref=raw_provider_ref,
                hash=raw_provider_hash,
            ),
        )

    return EvidenceSubmissionV1(
        submission_id=f"cdx_r1_submission_{submission_digest[:24]}",
        work_identity=EvidenceWorkIdentityV1(
            task_id=task_id,
            backend_ref=backend_ref,
        ),
        assignment=EvidenceAssignmentV1(
            contract_ref=assignment_ref,
            contract_hash=assignment_hash,
        ),
        producer=EvidenceProducerV1(
            backend_kind="soma_reasoning",
            provider="codex",
            model_or_profile=provider_model,
            adapter_id=CDX_R1_ADAPTER_ID,
            native_session_ref=provider_thread_id,
        ),
        submission_disposition=payload.submission_disposition,
        executive_summary=payload.executive_summary,
        claims=tuple(
            EvidenceClaimV1(
                claim_id=claim.claim_id,
                claim_class=claim.claim_class,
                subject_key=claim.subject_key,
                statement=claim.statement,
                supports_evidence_ids=claim.supports_evidence_ids,
                opposes_evidence_ids=claim.opposes_evidence_ids,
                uncertainty_ids=claim.uncertainty_ids,
            )
            for claim in payload.claims
        ),
        evidence=tuple(evidence_records),
        uncertainties=tuple(
            EvidenceUncertaintyV1(
                uncertainty_id=item.uncertainty_id,
                kind=item.kind,
                statement=item.statement,
                related_claim_ids=item.related_claim_ids,
                required_resolution=item.required_resolution,
            )
            for item in payload.uncertainties
        ),
        blockers=tuple(
            EvidenceBlockerV1(
                blocker_id=item.blocker_id,
                kind=item.kind,
                statement=item.statement,
            )
            for item in payload.blockers
        ),
        usage=EvidenceUsageV1(
            wall_time_seconds=wall_time_seconds,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=Decimal("0"),
        ),
        provenance=provenance,
        full_evidence_retrieval=retrieval,
        byte_accounting=EvidenceByteAccountingV1(
            referenced_body_bytes=len(packet_bytes),
            omitted_body_bytes=0,
        ),
    )
