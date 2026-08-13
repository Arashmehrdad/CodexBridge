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
    "soma.agent_worker_benchmark.semantic.v5"
)
BENCHMARK_SOURCE_QUOTE_CONTRACT_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.source_quote.v1"
)
BENCHMARK_ADAPTER_ID: Final[str] = "soma.reasoning.codex_app_server.g6"
BENCHMARK_EVIDENCE_COMPACTION_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.evidence_compaction.v2"
)
BENCHMARK_PACKET_SCHEMA_BINDING_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.packet_schema_binding.v2"
)
MAX_BENCHMARK_QUOTE_CHARACTERS: Final[int] = 480
BenchmarkFactValue = str | int | float | bool | None


class BenchmarkSemanticValidationError(ValueError):
    """Provider semantic output is not exactly supported by the frozen packet."""


class _FrozenBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkSourceQuoteV1(_FrozenBenchmarkModel):
    """One support-only quote copied from exactly one assigned frozen source line."""

    source_path: str = Field(min_length=1, max_length=2048)
    quote: str = Field(
        min_length=1,
        max_length=MAX_BENCHMARK_QUOTE_CHARACTERS,
        pattern=r"^[^\r\n]+$",
    )

    @model_validator(mode="after")
    def _validate_quote(self):
        if not self.quote.strip():
            raise ValueError("source quote must contain non-whitespace text")
        return self


class BenchmarkSemanticClaimV1(_FrozenBenchmarkModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_class: Literal[
        "observation", "inference", "recommendation", "negative_finding"
    ]
    subject_key: str = Field(min_length=1, max_length=256)
    statement: str = Field(min_length=1, max_length=4096)
    evidence_quotes: tuple[BenchmarkSourceQuoteV1, ...] = Field(
        default=(), max_length=24
    )
    uncertainty_ids: tuple[str, ...] = Field(default=(), max_length=12)


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
    evidence_quotes: tuple[BenchmarkSourceQuoteV1, ...] = Field(
        default=(), max_length=24
    )


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


def source_quote_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_SOURCE_QUOTE_CONTRACT_VERSION,
                "relation_model": "support_only",
                "source_binding": "exact_assignment_source_path",
                "quote_match": "exact_unique_single_line_substring",
                "quote_max_characters": MAX_BENCHMARK_QUOTE_CHARACTERS,
                "soma_injects_source_hash_and_line_locator": True,
            }
        )
    )


def packet_schema_binding_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_PACKET_SCHEMA_BINDING_VERSION,
                "claim_subject_key": "exact_assignment_fact_key_enum",
                "source_quote_path": "exact_assignment_source_path_enum",
                "source_path_def_name": "BenchmarkPacketSourcePath",
            }
        )
    )


def semantic_output_schema(packet_bytes: bytes | None = None) -> dict[str, Any]:
    schema = _strict_provider_schema(BenchmarkSemanticPayloadV1.model_json_schema())
    if packet_bytes is None:
        return schema

    packet = parse_assignment_packet(packet_bytes)
    questions = packet.get("rubric", {}).get("questions", [])
    fact_keys = [
        str(item["fact_key"])
        for item in questions
        if isinstance(item, dict) and isinstance(item.get("fact_key"), str)
    ]
    if len(fact_keys) != len(questions) or len(fact_keys) != len(set(fact_keys)):
        raise BenchmarkSemanticValidationError(
            "assignment fact keys are invalid or duplicate"
        )
    source_paths = list(_packet_sources(packet))
    if not source_paths:
        raise BenchmarkSemanticValidationError("assignment source set is empty")

    definitions = schema.setdefault("$defs", {})
    definitions["BenchmarkPacketSourcePath"] = {
        "enum": source_paths,
        "type": "string",
    }
    claim_properties = definitions["BenchmarkSemanticClaimV1"]["properties"]
    claim_properties["subject_key"] = {
        "enum": fact_keys,
        "type": "string",
    }
    quote_properties = definitions["BenchmarkSourceQuoteV1"]["properties"]
    quote_properties["source_path"] = {
        "$ref": "#/$defs/BenchmarkPacketSourcePath"
    }
    return schema


def evidence_compaction_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_EVIDENCE_COMPACTION_VERSION,
                "evidence_record_ceiling": MAX_EVIDENCE_RECORDS,
                "mandatory_policy": "first_per_nonempty_claim",
                "fill_policy": "round_robin_remaining_in_provider_order",
                "duplicate_policy": "deduplicate_identical_source_quote_per_claim",
                "fact_semantics": "one_support_record_per_claim_source_quote",
                "raw_provider_evidence_retained": True,
            }
        )
    )


def _semantic_instruction_text() -> str:
    return (
        "You are a read-only G6 benchmark evidence worker. Use only the ASSIGNMENT "
        "JSON below. Do not use tools, files, network sources, memory, chat history, "
        "or unstated assumptions. Return only the object required by the output "
        "schema. Use schema_version "
        f"{BENCHMARK_SEMANTIC_SCHEMA_VERSION!r}. Every claim subject_key must be one "
        "of the assignment fact keys. Every evidence_quotes entry is support-only: "
        "its quote must be a one-line exact verbatim substring copied from the "
        "declared assigned source, must directly support the exact claim statement, "
        "and should be long enough to occur only once in that source. There is no "
        "opposition relation. If the source contradicts a proposition, phrase the "
        "claim as the corresponding negative finding and quote evidence that supports "
        "that negative statement. Do not calculate line numbers or mint evidence IDs; "
        "Soma will verify each quote against the frozen source and inject the exact "
        "source hash, line locator, fact key, fact value, and evidence cross-reference "
        "mechanically. Prefer the smallest unique proof-bearing quote; do not cite "
        "context-only or merely nearby text. If exact support is unavailable, preserve "
        "uncertainty or a partial/blocked disposition instead of attaching unrelated "
        "evidence. Evaluate the supplied critical trap as false, true, or unsupported "
        "from the frozen sources only. Do not implement or modify anything."
    )


def semantic_prompt_contract_hash() -> str:
    return sha256_hex(_semantic_instruction_text().encode("utf-8"))


def semantic_prompt(packet_bytes: bytes) -> str:
    packet = parse_assignment_packet(packet_bytes)
    return (
        _semantic_instruction_text()
        + "\n\nASSIGNMENT JSON:\n"
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


def _resolve_source_quote_from_sources(
    sources: dict[str, dict[str, Any]], source_quote: BenchmarkSourceQuoteV1
) -> BenchmarkCitationV1:
    source = sources.get(source_quote.source_path)
    if source is None:
        raise BenchmarkSemanticValidationError(
            f"source quote path {source_quote.source_path!r} is not assignment-provided"
        )
    content = str(source["content"])
    quote = source_quote.quote
    occurrences = content.count(quote)
    if occurrences == 0:
        raise BenchmarkSemanticValidationError(
            "source quote is not an exact substring of its declared frozen source: "
            f"{source_quote.source_path!r}"
        )
    if occurrences != 1:
        raise BenchmarkSemanticValidationError(
            "source quote must identify exactly one frozen-source occurrence: "
            f"{source_quote.source_path!r} has {occurrences} matches"
        )
    start_offset = content.index(quote)
    start_line = content.count("\n", 0, start_offset) + 1
    citation_id = "Q" + sha256_hex(
        f"{source_quote.source_path}\0{quote}".encode("utf-8")
    )[:24]
    return BenchmarkCitationV1(
        citation_id=citation_id,
        source_path=source_quote.source_path,
        source_hash=str(source["sha256"]),
        start_line=start_line,
        end_line=start_line,
        excerpt=quote,
    )


def resolve_source_quote(
    packet_bytes: bytes, source_quote: BenchmarkSourceQuoteV1
) -> BenchmarkCitationV1:
    packet = parse_assignment_packet(packet_bytes)
    return _resolve_source_quote_from_sources(_packet_sources(packet), source_quote)


def validate_semantic_against_packet(
    payload: BenchmarkSemanticPayloadV1, packet_bytes: bytes
) -> None:
    packet = parse_assignment_packet(packet_bytes)
    allowed_fact_keys = _assignment_fact_keys(packet)
    sources = _packet_sources(packet)

    claims_by_key: dict[str, list[BenchmarkSemanticClaimV1]] = {}
    for claim in payload.claims:
        if claim.subject_key not in allowed_fact_keys:
            raise BenchmarkSemanticValidationError(
                f"claim subject_key {claim.subject_key!r} is not assignment-provided"
            )
        claims_by_key.setdefault(claim.subject_key, []).append(claim)
        for source_quote in claim.evidence_quotes:
            _resolve_source_quote_from_sources(sources, source_quote)
    for source_quote in payload.critical_trap.evidence_quotes:
        _resolve_source_quote_from_sources(sources, source_quote)

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


def compact_claim_quotes(
    payload: BenchmarkSemanticPayloadV1,
) -> tuple[dict[str, tuple[BenchmarkSourceQuoteV1, ...]], int]:
    buckets: list[tuple[str, tuple[BenchmarkSourceQuoteV1, ...]]] = []
    provider_reference_count = 0
    for claim in payload.claims:
        provider_reference_count += len(claim.evidence_quotes)
        unique: list[BenchmarkSourceQuoteV1] = []
        seen: set[tuple[str, str]] = set()
        for source_quote in claim.evidence_quotes:
            key = (source_quote.source_path, source_quote.quote)
            if key in seen:
                continue
            seen.add(key)
            unique.append(source_quote)
        if unique:
            buckets.append((claim.claim_id, tuple(unique)))

    if len(buckets) > MAX_EVIDENCE_RECORDS:
        raise BenchmarkSemanticValidationError(
            "claims with source quotes exceed final EvidenceSubmission evidence cap"
        )

    selected: dict[str, list[BenchmarkSourceQuoteV1]] = {
        claim_id: [quotes[0]] for claim_id, quotes in buckets
    }
    remaining_slots = MAX_EVIDENCE_RECORDS - len(buckets)
    depth = 1
    while remaining_slots > 0:
        progressed = False
        for claim_id, quotes in buckets:
            if depth >= len(quotes):
                continue
            selected[claim_id].append(quotes[depth])
            remaining_slots -= 1
            progressed = True
            if remaining_slots == 0:
                break
        if not progressed:
            break
        depth += 1

    published_reference_count = sum(len(quotes) for quotes in selected.values())
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

    packet = parse_assignment_packet(packet_bytes)
    sources = _packet_sources(packet)
    selected_quotes, _omitted_quote_references = compact_claim_quotes(payload)
    evidence_records_list: list[EvidenceRecordV1] = []
    claim_evidence_ids: dict[tuple[str, str, str], str] = {}
    for claim in payload.claims:
        for source_quote in selected_quotes.get(claim.claim_id, ()):
            citation = _resolve_source_quote_from_sources(sources, source_quote)
            quote_key = (claim.claim_id, source_quote.source_path, source_quote.quote)
            evidence_id = (
                "g6_evidence_"
                + sha256_hex(
                    f"{claim.claim_id}\0{citation.citation_id}".encode("utf-8")
                )[:24]
            )
            claim_evidence_ids[quote_key] = evidence_id
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
                    claim_evidence_ids[
                        (claim.claim_id, item.source_path, item.quote)
                    ]
                    for item in selected_quotes.get(claim.claim_id, ())
                ),
                opposes_evidence_ids=(),
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
