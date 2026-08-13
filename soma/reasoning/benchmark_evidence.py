"""Strict G6 benchmark semantic output and EvidenceSubmission bridge.

Provider output is limited to source-grounded semantic claims. Canonical Task,
backend, assignment, provider, and usage identities are injected mechanically by
Soma after the semantic payload validates against one frozen benchmark packet.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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
    MAX_EVIDENCE_RECORDS,
    EvidenceWorkIdentityV1,
)


BENCHMARK_SEMANTIC_SCHEMA_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.semantic.v4"
)
BENCHMARK_CITATION_CATALOG_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.citation_catalog.v1"
)
BENCHMARK_ADAPTER_ID: Final[str] = "soma.reasoning.codex_app_server.g6"
BENCHMARK_EVIDENCE_COMPACTION_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.evidence_compaction.v1"
)
MAX_BENCHMARK_LINE_SPAN: Final[int] = 24
CITATION_CHUNK_MAX_LINES: Final[int] = 4
CITATION_CHUNK_MAX_CHARACTERS: Final[int] = 480
BenchmarkFactValue = str | int | float | bool | None


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
    supports_citation_ids: tuple[str, ...] = Field(default=(), max_length=24)
    opposes_citation_ids: tuple[str, ...] = Field(default=(), max_length=24)
    uncertainty_ids: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def _validate_citation_polarity(self):
        if len(self.supports_citation_ids) != len(set(self.supports_citation_ids)):
            raise ValueError("supports_citation_ids must be unique")
        if len(self.opposes_citation_ids) != len(set(self.opposes_citation_ids)):
            raise ValueError("opposes_citation_ids must be unique")
        if set(self.supports_citation_ids) & set(self.opposes_citation_ids):
            raise ValueError("one citation cannot both support and oppose one claim")
        return self


@dataclass(frozen=True)
class BenchmarkCitationV1:
    citation_id: str
    source_path: str
    source_hash: str
    start_line: int
    end_line: int
    excerpt: str


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
    supports_citation_ids: tuple[str, ...] = Field(default=(), max_length=24)


class BenchmarkSemanticPayloadV1(_FrozenBenchmarkModel):
    schema_version: Literal[BENCHMARK_SEMANTIC_SCHEMA_VERSION]
    submission_disposition: Literal["complete", "partial", "blocked", "uncertain"]
    executive_summary: str = Field(max_length=1024)
    claims: tuple[BenchmarkSemanticClaimV1, ...] = Field(max_length=12)
    uncertainties: tuple[BenchmarkSemanticUncertaintyV1, ...] = Field(max_length=12)
    blockers: tuple[BenchmarkSemanticBlockerV1, ...] = Field(max_length=8)
    critical_trap: BenchmarkCriticalTrapV1

    @model_validator(mode="after")
    def _validate_local_refs(self):
        claim_ids = [claim.claim_id for claim in self.claims]
        uncertainty_ids = [item.uncertainty_id for item in self.uncertainties]
        blocker_ids = [item.blocker_id for item in self.blockers]
        for label, values in (
            ("claim", claim_ids),
            ("uncertainty", uncertainty_ids),
            ("blocker", blocker_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")

        uncertainty_set = set(uncertainty_ids)
        claim_set = set(claim_ids)
        for claim in self.claims:
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
        raise BenchmarkSemanticValidationError(
            "benchmark packet is not valid JSON"
        ) from exc
    if packet.get("schema_version") != "soma.agent_worker_benchmark.assignment.v1":
        raise BenchmarkSemanticValidationError("unexpected benchmark assignment schema")
    return packet


def _strict_provider_schema(value: Any) -> Any:
    """Normalize Pydantic JSON Schema to the provider strict-output contract.

    Structured Outputs requires every declared object property to appear in
    ``required``. Defaults are validation conveniences for local Pydantic models,
    not provider output semantics, so they are removed from the wire schema.
    """

    if isinstance(value, list):
        return [_strict_provider_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {
        key: _strict_provider_schema(item)
        for key, item in value.items()
        if key != "default"
    }
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["additionalProperties"] = False
        normalized["required"] = list(properties)
    return normalized


def semantic_output_schema() -> dict[str, Any]:
    return _strict_provider_schema(BenchmarkSemanticPayloadV1.model_json_schema())


def _citation_chunks(lines: list[str]) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(lines):
        selected: list[str] = []
        end = start
        while end < len(lines) and len(selected) < CITATION_CHUNK_MAX_LINES:
            candidate = "\n".join((*selected, lines[end]))
            if selected and len(candidate) > CITATION_CHUNK_MAX_CHARACTERS:
                break
            if not selected and len(candidate) > CITATION_CHUNK_MAX_CHARACTERS:
                raise BenchmarkSemanticValidationError(
                    "frozen source line exceeds citation chunk character ceiling"
                )
            selected.append(lines[end])
            end += 1
        excerpt = "\n".join(selected)
        chunks.append((start + 1, end, excerpt))
        start = end
    return chunks


def citation_catalog(packet_bytes: bytes) -> tuple[BenchmarkCitationV1, ...]:
    packet = parse_assignment_packet(packet_bytes)
    sources = _packet_sources(packet)
    entries: list[BenchmarkCitationV1] = []
    for source_index, source in enumerate(sources.values(), start=1):
        lines = str(source["content"]).splitlines()
        for chunk_index, (start_line, end_line, excerpt) in enumerate(
            _citation_chunks(lines), start=1
        ):
            entries.append(
                BenchmarkCitationV1(
                    citation_id=f"S{source_index:02d}C{chunk_index:04d}",
                    source_path=str(source["path"]),
                    source_hash=str(source["sha256"]),
                    start_line=start_line,
                    end_line=end_line,
                    excerpt=excerpt,
                )
            )
    return tuple(entries)


def citation_catalog_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_CITATION_CATALOG_VERSION,
                "chunk_max_lines": CITATION_CHUNK_MAX_LINES,
                "chunk_max_characters": CITATION_CHUNK_MAX_CHARACTERS,
                "citation_id_format": "S{source_index:02d}C{chunk_index:04d}",
                "provider_selects_identity_only": True,
                "soma_injects_source_locator_excerpt": True,
            }
        )
    )


def evidence_compaction_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_EVIDENCE_COMPACTION_VERSION,
                "evidence_record_ceiling": MAX_EVIDENCE_RECORDS,
                "mandatory_policy": "first_per_nonempty_claim_polarity",
                "fill_policy": "round_robin_remaining_in_provider_order",
                "fact_semantics": "one_record_per_claim_polarity_citation",
                "raw_provider_evidence_retained": True,
            }
        )
    )


def citation_catalog_payload(packet_bytes: bytes) -> dict[str, Any]:
    packet = parse_assignment_packet(packet_bytes)
    sources = list(_packet_sources(packet).values())
    return {
        "schema_version": BENCHMARK_CITATION_CATALOG_VERSION,
        "sources": [
            {"source_index": index, "path": str(source["path"])}
            for index, source in enumerate(sources, start=1)
        ],
        "citations": [
            {
                "citation_id": item.citation_id,
                "source_path": item.source_path,
                "locator": f"lines:{item.start_line}-{item.end_line}",
                "excerpt": item.excerpt,
            }
            for item in citation_catalog(packet_bytes)
        ],
    }


def semantic_prompt(packet_bytes: bytes) -> str:
    packet = parse_assignment_packet(packet_bytes)
    catalog = citation_catalog_payload(packet_bytes)
    return (
        "You are a read-only G6 benchmark evidence worker. Use only the ASSIGNMENT "
        "JSON and mechanically derived CITATION CATALOG below. Do not use tools, "
        "files, network sources, memory, chat history, or unstated assumptions. "
        "Return only the object required by the output schema. Use schema_version "
        f"{BENCHMARK_SEMANTIC_SCHEMA_VERSION!r}. Every claim subject_key must be one "
        "of the assignment fact keys. Do not calculate line numbers, copy source "
        "text, mint evidence IDs, or return a parallel evidence list. Claims must "
        "select exact catalog IDs through supports_citation_ids or "
        "opposes_citation_ids. Soma will derive every final EvidenceRecord from each "
        "claim/citation pair and inject the exact path, hash, locator, excerpt, fact "
        "key, fact value, and evidence cross-reference mechanically. Preserve "
        "uncertainty instead of "
        "inventing a winner. Evaluate "
        "the supplied critical trap as false, true, or unsupported from the frozen "
        "sources only. Do not implement or modify anything.\n\n"
        "ASSIGNMENT JSON:\n"
        + json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n\nCITATION CATALOG JSON:\n"
        + json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
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
            raise BenchmarkSemanticValidationError(
                "assignment source must be an object"
            )
        path = source.get("path")
        content = source.get("content")
        digest = source.get("sha256")
        if not isinstance(path, str) or not path:
            raise BenchmarkSemanticValidationError("assignment source path is invalid")
        if path in result:
            raise BenchmarkSemanticValidationError(
                "assignment source paths must be unique"
            )
        if not isinstance(content, str) or not isinstance(digest, str):
            raise BenchmarkSemanticValidationError(
                "assignment source content/hash is invalid"
            )
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
        raise BenchmarkSemanticValidationError(
            "assignment fact keys are invalid or duplicate"
        )
    return {str(value) for value in keys}


def validate_semantic_against_packet(
    payload: BenchmarkSemanticPayloadV1, packet_bytes: bytes
) -> None:
    packet = parse_assignment_packet(packet_bytes)
    allowed_fact_keys = _assignment_fact_keys(packet)

    claims_by_key: dict[str, list[BenchmarkSemanticClaimV1]] = {}
    for claim in payload.claims:
        if claim.subject_key not in allowed_fact_keys:
            raise BenchmarkSemanticValidationError(
                f"claim subject_key {claim.subject_key!r} is not assignment-provided"
            )
        claims_by_key.setdefault(claim.subject_key, []).append(claim)

    catalog = {item.citation_id: item for item in citation_catalog(packet_bytes)}
    referenced_citations: list[str] = []
    for claim in payload.claims:
        referenced_citations.extend(claim.supports_citation_ids)
        referenced_citations.extend(claim.opposes_citation_ids)
    referenced_citations.extend(payload.critical_trap.supports_citation_ids)
    unknown_citations = set(referenced_citations) - set(catalog)
    if unknown_citations:
        raise BenchmarkSemanticValidationError(
            "semantic payload references citation IDs outside the mechanically "
            f"derived assignment catalog: {sorted(unknown_citations)}"
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


def compact_claim_citations(
    payload: BenchmarkSemanticPayloadV1,
) -> tuple[dict[tuple[str, str], tuple[str, ...]], int]:
    buckets: list[tuple[str, str, tuple[str, ...]]] = []
    for claim in payload.claims:
        if claim.supports_citation_ids:
            buckets.append((claim.claim_id, "support", claim.supports_citation_ids))
        if claim.opposes_citation_ids:
            buckets.append((claim.claim_id, "oppose", claim.opposes_citation_ids))

    if len(buckets) > MAX_EVIDENCE_RECORDS:
        raise BenchmarkSemanticValidationError(
            "claim citation polarities exceed final EvidenceSubmission evidence cap"
        )

    selected: dict[tuple[str, str], list[str]] = {
        (claim_id, polarity): [citation_ids[0]]
        for claim_id, polarity, citation_ids in buckets
    }
    remaining_slots = MAX_EVIDENCE_RECORDS - len(buckets)
    depth = 1
    while remaining_slots > 0:
        progressed = False
        for claim_id, polarity, citation_ids in buckets:
            if depth >= len(citation_ids):
                continue
            selected[(claim_id, polarity)].append(citation_ids[depth])
            remaining_slots -= 1
            progressed = True
            if remaining_slots == 0:
                break
        if not progressed:
            break
        depth += 1

    provider_reference_count = sum(len(citation_ids) for _, _, citation_ids in buckets)
    published_reference_count = sum(
        len(citation_ids) for citation_ids in selected.values()
    )
    return (
        {key: tuple(value) for key, value in selected.items()},
        provider_reference_count - published_reference_count,
    )


def build_evidence_submission(
    *,
    payload: BenchmarkSemanticPayloadV1,
    packet_bytes: bytes,
    task_id: str,
    backend_ref: str,
    assignment_ref: str,
    assignment_hash: str | None = None,
    provider_model: str,
    provider_thread_id: str,
    usage: BenchmarkUsageV1,
    wall_time_seconds: float,
    provenance_refs: tuple[tuple[str, str], ...] = (),
    raw_provider_ref: str = "",
    raw_provider_hash: str = "",
) -> EvidenceSubmissionV1:
    validate_semantic_against_packet(payload, packet_bytes)
    parse_assignment_packet(packet_bytes)
    packet_hash = sha256_hex(packet_bytes)
    canonical_assignment_hash = assignment_hash or packet_hash
    if len(canonical_assignment_hash) != 64 or any(
        char not in "0123456789abcdef" for char in canonical_assignment_hash
    ):
        raise ValueError("assignment_hash must be lowercase SHA-256")
    payload_digest = semantic_payload_hash(payload)
    submission_digest = sha256_hex(
        f"{task_id}\0{backend_ref}\0{payload_digest}".encode("utf-8")
    )

    catalog = {item.citation_id: item for item in citation_catalog(packet_bytes)}
    selected_citations, _omitted_citation_references = compact_claim_citations(payload)
    evidence_records_list: list[EvidenceRecordV1] = []
    claim_evidence_ids: dict[tuple[str, str, str], str] = {}
    for claim in payload.claims:
        for polarity in ("support", "oppose"):
            for citation_id in selected_citations.get((claim.claim_id, polarity), ()):
                evidence_id = (
                    "g6_evidence_"
                    + sha256_hex(
                        f"{claim.claim_id}\0{polarity}\0{citation_id}".encode("utf-8")
                    )[:24]
                )
                claim_evidence_ids[(claim.claim_id, polarity, citation_id)] = (
                    evidence_id
                )
                citation = catalog[citation_id]
                evidence_records_list.append(
                    EvidenceRecordV1(
                        evidence_id=evidence_id,
                        source_kind="frozen_git_source",
                        source_ref=f"git:{SOURCE_COMMIT}:{citation.source_path}",
                        source_hash=citation.source_hash,
                        locator=f"lines:{citation.start_line}-{citation.end_line}",
                        content_type="text/x-python",
                        excerpt=citation.excerpt,
                        fact_key=claim.subject_key,
                        fact_value=claim.statement,
                    )
                )
    evidence_records = tuple(evidence_records_list)
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
            contract_ref=assignment_ref, contract_hash=canonical_assignment_hash
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
                supports_evidence_ids=tuple(
                    claim_evidence_ids[(claim.claim_id, "support", item)]
                    for item in selected_citations.get((claim.claim_id, "support"), ())
                ),
                opposes_evidence_ids=tuple(
                    claim_evidence_ids[(claim.claim_id, "oppose", item)]
                    for item in selected_citations.get((claim.claim_id, "oppose"), ())
                ),
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
