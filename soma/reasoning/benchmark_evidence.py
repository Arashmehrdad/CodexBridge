"""Strict G6 benchmark semantic output and EvidenceSubmission bridge.

Provider output is limited to source-grounded semantic claims. Canonical Task,
backend, assignment, provider, and usage identities are injected mechanically by
Soma after the semantic payload validates against one frozen benchmark packet.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.agent_worker_benchmark import SOURCE_COMMIT
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


BENCHMARK_SEMANTIC_SCHEMA_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.semantic.v1"
)
BENCHMARK_ADAPTER_ID: Final[str] = "soma.reasoning.codex_app_server.g6"
MAX_BENCHMARK_LINE_SPAN: Final[int] = 24


class BenchmarkSemanticValidationError(ValueError):
    """Provider semantic output is not exactly supported by the frozen packet."""


class _FrozenBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkSemanticClaimV1(_FrozenBenchmarkModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_class: Literal[
        "observation", "inference", "recommendation", "negative_finding"
    ]
    subject_key: str = Field(min_length=1, max_length=256)
    statement: str = Field(min_length=1, max_length=4096)
    supports_evidence_ids: tuple[str, ...] = Field(default=(), max_length=24)
    opposes_evidence_ids: tuple[str, ...] = Field(default=(), max_length=24)
    uncertainty_ids: tuple[str, ...] = Field(default=(), max_length=12)


class BenchmarkSemanticEvidenceV1(_FrozenBenchmarkModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    source_path: str = Field(min_length=1, max_length=512)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=512)
    fact_key: str = Field(min_length=1, max_length=256)
    fact_value: Any

    @model_validator(mode="after")
    def _validate_lines(self):
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.end_line - self.start_line + 1 > MAX_BENCHMARK_LINE_SPAN:
            raise ValueError(
                f"evidence line span exceeds {MAX_BENCHMARK_LINE_SPAN} lines"
            )
        return self


class BenchmarkSemanticUncertaintyV1(_FrozenBenchmarkModel):
    uncertainty_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)
    related_claim_ids: tuple[str, ...] = Field(default=(), max_length=12)
    required_resolution: str | None = Field(default=None, max_length=2048)


class BenchmarkSemanticBlockerV1(_FrozenBenchmarkModel):
    blocker_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)


class BenchmarkCriticalTrapV1(_FrozenBenchmarkModel):
    disposition: Literal["false", "true", "unsupported"]
    statement: str = Field(min_length=1, max_length=2048)
    supports_evidence_ids: tuple[str, ...] = Field(default=(), max_length=24)


class BenchmarkSemanticPayloadV1(_FrozenBenchmarkModel):
    schema_version: Literal[BENCHMARK_SEMANTIC_SCHEMA_VERSION]
    submission_disposition: Literal["complete", "partial", "blocked", "uncertain"]
    executive_summary: str = Field(max_length=1024)
    claims: tuple[BenchmarkSemanticClaimV1, ...] = Field(max_length=12)
    evidence: tuple[BenchmarkSemanticEvidenceV1, ...] = Field(max_length=24)
    uncertainties: tuple[BenchmarkSemanticUncertaintyV1, ...] = Field(max_length=12)
    blockers: tuple[BenchmarkSemanticBlockerV1, ...] = Field(max_length=8)
    critical_trap: BenchmarkCriticalTrapV1

    @model_validator(mode="after")
    def _validate_local_refs(self):
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
            missing_evidence = (
                set(claim.supports_evidence_ids) | set(claim.opposes_evidence_ids)
            ) - evidence_set
            if missing_evidence:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown evidence IDs: "
                    f"{sorted(missing_evidence)}"
                )
            missing_uncertainties = set(claim.uncertainty_ids) - uncertainty_set
            if missing_uncertainties:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown uncertainty IDs: "
                    f"{sorted(missing_uncertainties)}"
                )
        for uncertainty in self.uncertainties:
            missing_claims = set(uncertainty.related_claim_ids) - claim_set
            if missing_claims:
                raise ValueError(
                    f"uncertainty {uncertainty.uncertainty_id} references unknown claims: "
                    f"{sorted(missing_claims)}"
                )
        missing_trap_evidence = set(self.critical_trap.supports_evidence_ids) - evidence_set
        if missing_trap_evidence:
            raise ValueError(
                "critical_trap references unknown evidence IDs: "
                f"{sorted(missing_trap_evidence)}"
            )
        return self


class BenchmarkUsageV1(_FrozenBenchmarkModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_assignment_packet(packet_bytes: bytes) -> dict[str, Any]:
    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkSemanticValidationError("benchmark packet is not valid JSON") from exc
    if packet.get("schema_version") != "soma.agent_worker_benchmark.assignment.v1":
        raise BenchmarkSemanticValidationError("unexpected benchmark assignment schema")
    return packet


def semantic_output_schema() -> dict[str, Any]:
    return BenchmarkSemanticPayloadV1.model_json_schema()


def semantic_prompt(packet_bytes: bytes) -> str:
    packet = parse_assignment_packet(packet_bytes)
    return (
        "You are a read-only G6 benchmark evidence worker. Use only the ASSIGNMENT "
        "JSON below. Do not use tools, files, network sources, memory, chat history, "
        "or unstated assumptions. Return only the object required by the output "
        "schema. Use schema_version "
        f"{BENCHMARK_SEMANTIC_SCHEMA_VERSION!r}. Every claim subject_key must be one "
        "of the assignment fact keys. Every evidence item must cite one assignment "
        "source path, a bounded 1-based line range, an exact excerpt from that range, "
        "and the fact key it supports. Preserve uncertainty instead of inventing a "
        "winner. Evaluate the supplied critical trap as false, true, or unsupported "
        "from the frozen sources only. Do not implement or modify anything.\n\n"
        "ASSIGNMENT JSON:\n"
        + json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def parse_semantic_output(text: str) -> BenchmarkSemanticPayloadV1:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BenchmarkSemanticValidationError(
            f"provider final message is not exact JSON: {exc}"
        ) from exc
    try:
        return BenchmarkSemanticPayloadV1.model_validate(value)
    except ValueError as exc:
        raise BenchmarkSemanticValidationError(str(exc)) from exc


def _packet_sources(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = packet.get("sources")
    if not isinstance(sources, list):
        raise BenchmarkSemanticValidationError("assignment sources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise BenchmarkSemanticValidationError("assignment source must be an object")
        path = source.get("path")
        content = source.get("content")
        digest = source.get("sha256")
        if not isinstance(path, str) or not path:
            raise BenchmarkSemanticValidationError("assignment source path is invalid")
        if path in result:
            raise BenchmarkSemanticValidationError("assignment source paths must be unique")
        if not isinstance(content, str) or not isinstance(digest, str):
            raise BenchmarkSemanticValidationError("assignment source content/hash is invalid")
        result[path] = source
    return result


def _assignment_fact_keys(packet: dict[str, Any]) -> set[str]:
    rubric = packet.get("rubric")
    questions = rubric.get("questions") if isinstance(rubric, dict) else None
    if not isinstance(questions, list):
        raise BenchmarkSemanticValidationError("assignment questions are invalid")
    keys = {
        item.get("fact_key")
        for item in questions
        if isinstance(item, dict) and isinstance(item.get("fact_key"), str)
    }
    if len(keys) != len(questions):
        raise BenchmarkSemanticValidationError("assignment fact keys are invalid or duplicate")
    return {str(value) for value in keys}


def validate_semantic_against_packet(
    payload: BenchmarkSemanticPayloadV1, packet_bytes: bytes
) -> None:
    packet = parse_assignment_packet(packet_bytes)
    sources = _packet_sources(packet)
    allowed_fact_keys = _assignment_fact_keys(packet)

    claims_by_key: dict[str, list[BenchmarkSemanticClaimV1]] = {}
    for claim in payload.claims:
        if claim.subject_key not in allowed_fact_keys:
            raise BenchmarkSemanticValidationError(
                f"claim subject_key {claim.subject_key!r} is not assignment-provided"
            )
        claims_by_key.setdefault(claim.subject_key, []).append(claim)

    evidence_by_id = {item.evidence_id: item for item in payload.evidence}
    for evidence in payload.evidence:
        if evidence.fact_key not in allowed_fact_keys:
            raise BenchmarkSemanticValidationError(
                f"evidence fact_key {evidence.fact_key!r} is not assignment-provided"
            )
        source = sources.get(evidence.source_path)
        if source is None:
            raise BenchmarkSemanticValidationError(
                f"evidence cites source outside assignment: {evidence.source_path!r}"
            )
        lines = str(source["content"]).splitlines()
        if evidence.end_line > len(lines):
            raise BenchmarkSemanticValidationError(
                f"evidence line range exceeds source {evidence.source_path!r}"
            )
        selected = "\n".join(lines[evidence.start_line - 1 : evidence.end_line])
        if evidence.excerpt not in selected:
            raise BenchmarkSemanticValidationError(
                f"evidence excerpt is not exact text from {evidence.source_path!r} "
                f"lines {evidence.start_line}-{evidence.end_line}"
            )

    for claim in payload.claims:
        linked = [evidence_by_id[item] for item in claim.supports_evidence_ids]
        if any(item.fact_key != claim.subject_key for item in linked):
            raise BenchmarkSemanticValidationError(
                f"claim {claim.claim_id} cites evidence for another fact key"
            )

    missing_claim_keys = allowed_fact_keys - set(claims_by_key)
    if payload.submission_disposition == "complete" and missing_claim_keys:
        raise BenchmarkSemanticValidationError(
            "complete submission is missing required fact-key claims: "
            f"{sorted(missing_claim_keys)}"
        )


def semantic_payload_hash(payload: BenchmarkSemanticPayloadV1) -> str:
    return sha256_hex(canonical_json_bytes(payload.model_dump(mode="json")))


def extract_usage(token_usage_events: tuple[dict[str, Any], ...]) -> BenchmarkUsageV1:
    if not token_usage_events:
        return BenchmarkUsageV1()
    params = token_usage_events[-1]
    block = params.get("tokenUsage") or params.get("usage") or {}
    if not isinstance(block, dict):
        return BenchmarkUsageV1()
    candidate = block.get("total") or block.get("last") or block
    if not isinstance(candidate, dict):
        candidate = {}

    def pick(*names: str) -> int:
        for name in names:
            value = candidate.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return 0

    return BenchmarkUsageV1(
        input_tokens=pick("inputTokens", "input_tokens"),
        cached_input_tokens=pick("cachedInputTokens", "cached_input_tokens"),
        output_tokens=pick("outputTokens", "output_tokens"),
        reasoning_output_tokens=pick(
            "reasoningOutputTokens", "reasoning_output_tokens"
        ),
        total_tokens=pick("totalTokens", "total_tokens"),
    )


def build_evidence_submission(
    *,
    payload: BenchmarkSemanticPayloadV1,
    packet_bytes: bytes,
    task_id: str,
    backend_ref: str,
    assignment_ref: str,
    provider_model: str,
    provider_thread_id: str,
    usage: BenchmarkUsageV1,
    wall_time_seconds: float,
    provenance_refs: tuple[tuple[str, str], ...] = (),
    raw_provider_ref: str = "",
    raw_provider_hash: str = "",
) -> EvidenceSubmissionV1:
    validate_semantic_against_packet(payload, packet_bytes)
    packet = parse_assignment_packet(packet_bytes)
    sources = _packet_sources(packet)
    assignment_hash = sha256_hex(packet_bytes)
    payload_digest = semantic_payload_hash(payload)
    submission_digest = sha256_hex(
        f"{task_id}\0{backend_ref}\0{payload_digest}".encode("utf-8")
    )

    evidence_records = tuple(
        EvidenceRecordV1(
            evidence_id=item.evidence_id,
            source_kind="frozen_git_source",
            source_ref=f"git:{SOURCE_COMMIT}:{item.source_path}",
            source_hash=str(sources[item.source_path]["sha256"]),
            locator=f"lines:{item.start_line}-{item.end_line}",
            content_type="text/x-python",
            excerpt=item.excerpt,
            fact_key=item.fact_key,
            fact_value=item.fact_value,
        )
        for item in payload.evidence
    )
    provenance = tuple(
        EvidenceHashedReferenceV1(ref=ref, hash=digest)
        for ref, digest in provenance_refs
    )
    retrieval: tuple[EvidenceHashedReferenceV1, ...] = ()
    if raw_provider_ref or raw_provider_hash:
        if not raw_provider_ref or not raw_provider_hash:
            raise ValueError("raw provider ref/hash must appear together")
        retrieval = (
            EvidenceHashedReferenceV1(ref=raw_provider_ref, hash=raw_provider_hash),
        )

    return EvidenceSubmissionV1(
        submission_id=f"g6_submission_{submission_digest[:24]}",
        work_identity=EvidenceWorkIdentityV1(task_id=task_id, backend_ref=backend_ref),
        assignment=EvidenceAssignmentV1(
            contract_ref=assignment_ref, contract_hash=assignment_hash
        ),
        producer=EvidenceProducerV1(
            backend_kind="soma_reasoning",
            provider="codex",
            model_or_profile=provider_model,
            adapter_id=BENCHMARK_ADAPTER_ID,
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
        evidence=evidence_records,
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
            referenced_body_bytes=len(packet_bytes), omitted_body_bytes=0
        ),
    )
