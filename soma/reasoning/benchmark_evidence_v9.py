"""G6 v9 provider evidence bridge with a mechanical Soma boundary.

The reasoning worker owns semantic analysis and chooses the evidence locations it
believes support each claim. Soma does not judge whether a passage proves a
claim. It only validates assignment identity and file/line locator mechanics,
materializes immutable frozen-source evidence, and preserves it for later Sol
semantic adjudication.
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
    EvidenceWorkIdentityV1,
    MAX_EVIDENCE_EXCERPT_CHARACTERS,
    MAX_EVIDENCE_RECORDS,
)

from .benchmark_evidence import BenchmarkUsageV1, extract_usage as extract_usage


BENCHMARK_SEMANTIC_SCHEMA_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.semantic.v6"
)
BENCHMARK_SOURCE_LOCATOR_CONTRACT_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.source_locator.v2"
)
BENCHMARK_ADAPTER_ID: Final[str] = "soma.reasoning.codex_app_server.g6"
BENCHMARK_EVIDENCE_COMPACTION_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.evidence_compaction.v3"
)
BENCHMARK_PACKET_SCHEMA_BINDING_VERSION: Final[str] = (
    "soma.agent_worker_benchmark.packet_schema_binding.v3"
)


class BenchmarkSemanticValidationError(ValueError):
    """Provider output cannot be mapped mechanically to the frozen assignment."""


class _FrozenBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkSourceLocatorV1(_FrozenBenchmarkModel):
    """Worker-chosen location in one assignment-provided frozen source."""

    source_path: str = Field(min_length=1, max_length=2048)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_range(self):
        if self.end_line < self.start_line:
            raise ValueError("source locator end_line must be >= start_line")
        return self


class BenchmarkSemanticClaimV1(_FrozenBenchmarkModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_class: Literal[
        "observation", "inference", "recommendation", "negative_finding"
    ]
    subject_key: str = Field(min_length=1, max_length=256)
    statement: str = Field(min_length=1, max_length=4096)
    evidence_locations: tuple[BenchmarkSourceLocatorV1, ...] = Field(
        default=(), max_length=24
    )
    uncertainty_ids: tuple[str, ...] = Field(default=(), max_length=12)


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
    evidence_locations: tuple[BenchmarkSourceLocatorV1, ...] = Field(
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
            missing = set(claim.uncertainty_ids) - uncertainty_set
            if missing:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown uncertainty IDs: "
                    f"{sorted(missing)}"
                )
        for uncertainty in self.uncertainties:
            missing = set(uncertainty.related_claim_ids) - claim_set
            if missing:
                raise ValueError(
                    f"uncertainty {uncertainty.uncertainty_id} references unknown claims: "
                    f"{sorted(missing)}"
                )
        return self


@dataclass(frozen=True)
class BenchmarkCitationV1:
    citation_id: str
    source_path: str
    source_hash: str
    start_line: int
    end_line: int
    excerpt: str


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


def source_locator_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_SOURCE_LOCATOR_CONTRACT_VERSION,
                "worker_semantic_authority": (
                    "worker chooses claim and evidence locations"
                ),
                "soma_authority": (
                    "assignment identity, source membership, line-range validity, "
                    "immutable materialization only"
                ),
                "semantic_support_judgment": "sol_adjudication_only",
                "source_binding": "exact_assignment_source_path",
                "locator_model": "inclusive_one_based_line_range",
                "range_policy": "any_existing_range_inside_assigned_source",
                "provider_source_view": "zero_padded_numbered_lines",
            }
        )
    )


def packet_schema_binding_contract_hash() -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": BENCHMARK_PACKET_SCHEMA_BINDING_VERSION,
                "claim_subject_key": "exact_assignment_fact_key_enum",
                "source_locator_path": "exact_assignment_source_path_enum",
                "line_numbers": "packet_max_bound_plus_source_specific_local_check",
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
    sources = _packet_sources(packet)
    source_paths = list(sources)
    if not source_paths:
        raise BenchmarkSemanticValidationError("assignment source set is empty")
    max_source_lines = max(
        max(1, len(str(source["content"]).splitlines()))
        for source in sources.values()
    )

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
    locator_properties = definitions["BenchmarkSourceLocatorV1"]["properties"]
    locator_properties["source_path"] = {
        "$ref": "#/$defs/BenchmarkPacketSourcePath"
    }
    for field_name in ("start_line", "end_line"):
        locator_properties[field_name] = {
            "maximum": max_source_lines,
            "minimum": 1,
            "type": "integer",
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
                "duplicate_policy": "deduplicate_identical_locator_per_claim",
                "fact_semantics": "worker_declared_claim_to_location_reference",
                "semantic_precision_owner": "sol",
                "raw_provider_evidence_retained": True,
            }
        )
    )


def _semantic_instruction_text() -> str:
    return (
        "You are a smart read-only G6 reasoning worker. Use only the PROVIDER "
        "ASSIGNMENT VIEW below. Analyze the assigned source code and answer every "
        "fact-key question. You own the semantic reasoning: decide the claim and the "
        "source location(s) you believe support it. Return only the object required "
        "by the output schema, using schema_version "
        f"{BENCHMARK_SEMANTIC_SCHEMA_VERSION!r}. Every claim subject_key must be one "
        "of the assignment fact keys. For evidence_locations, point to an assigned "
        "source_path and an inclusive start_line/end_line range that exists in that "
        "assigned source. Choose a compact useful range for later review; Soma does "
        "not impose a semantic evidence-size rule. Each source's numbered_content "
        "uses a five-digit one-based line number, a "
        "literal | separator, then the exact frozen source line; the numeric prefix "
        "is locator metadata, not source text. Do not copy quotes and do not mint "
        "evidence IDs. Soma will only validate that your file/range exists in the "
        "frozen assignment and will materialize that evidence mechanically. Soma "
        "will not judge whether your evidence proves your claim; Sol performs that "
        "semantic adjudication later. Preserve uncertainty when the source does not "
        "establish an answer. Evaluate the critical trap from the frozen sources. "
        "Do not use tools, external files, network sources, memory, chat history, or "
        "unstated external knowledge. Do not implement or modify anything."
    )


def semantic_prompt_contract_hash() -> str:
    return sha256_hex(_semantic_instruction_text().encode("utf-8"))


def _provider_assignment_view(packet: dict[str, Any]) -> dict[str, Any]:
    view = {key: value for key, value in packet.items() if key != "sources"}
    provider_sources: list[dict[str, Any]] = []
    for source in _packet_sources(packet).values():
        lines = str(source["content"]).splitlines()
        provider_sources.append(
            {
                "path": source["path"],
                "sha256": source["sha256"],
                "git_blob_sha256": source.get("git_blob_sha256", ""),
                "representation": source.get("representation", ""),
                "numbered_content": "\n".join(
                    f"{number:05d}|{line}"
                    for number, line in enumerate(lines, start=1)
                ),
            }
        )
    view["sources"] = provider_sources
    return view


def semantic_prompt(packet_bytes: bytes) -> str:
    packet = parse_assignment_packet(packet_bytes)
    return (
        _semantic_instruction_text()
        + "\n\nPROVIDER ASSIGNMENT VIEW JSON:\n"
        + json.dumps(
            _provider_assignment_view(packet),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
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


def _resolve_source_locator_from_sources(
    sources: dict[str, dict[str, Any]], locator: BenchmarkSourceLocatorV1
) -> BenchmarkCitationV1:
    source = sources.get(locator.source_path)
    if source is None:
        raise BenchmarkSemanticValidationError(
            f"source locator path {locator.source_path!r} is not assignment-provided"
        )
    lines = str(source["content"]).splitlines()
    if locator.end_line > len(lines):
        raise BenchmarkSemanticValidationError(
            "source locator exceeds frozen-source line count: "
            f"{locator.source_path!r} has {len(lines)} lines"
        )
    materialized = "\n".join(lines[locator.start_line - 1 : locator.end_line])
    excerpt = materialized[:MAX_EVIDENCE_EXCERPT_CHARACTERS]
    citation_id = "L" + sha256_hex(
        f"{locator.source_path}\0{locator.start_line}\0{locator.end_line}".encode(
            "utf-8"
        )
    )[:24]
    return BenchmarkCitationV1(
        citation_id=citation_id,
        source_path=locator.source_path,
        source_hash=str(source["sha256"]),
        start_line=locator.start_line,
        end_line=locator.end_line,
        excerpt=excerpt,
    )


def resolve_source_locator(
    packet_bytes: bytes, locator: BenchmarkSourceLocatorV1
) -> BenchmarkCitationV1:
    packet = parse_assignment_packet(packet_bytes)
    return _resolve_source_locator_from_sources(_packet_sources(packet), locator)


def validate_semantic_against_packet(
    payload: BenchmarkSemanticPayloadV1, packet_bytes: bytes
) -> None:
    """Validate only assignment and locator mechanics, never semantic support."""

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
        for locator in claim.evidence_locations:
            _resolve_source_locator_from_sources(sources, locator)
    for locator in payload.critical_trap.evidence_locations:
        _resolve_source_locator_from_sources(sources, locator)

    # Missing assignment fact keys are benchmark quality data for FanIn/Sol, not a
    # transport-invalid condition. Soma preserves the worker submission as emitted.


def semantic_payload_hash(payload: BenchmarkSemanticPayloadV1) -> str:
    return sha256_hex(canonical_json_bytes(payload.model_dump(mode="json")))


def compact_claim_locations(
    payload: BenchmarkSemanticPayloadV1,
) -> tuple[dict[str, tuple[BenchmarkSourceLocatorV1, ...]], int]:
    buckets: list[tuple[str, tuple[BenchmarkSourceLocatorV1, ...]]] = []
    provider_reference_count = 0
    for claim in payload.claims:
        provider_reference_count += len(claim.evidence_locations)
        unique: list[BenchmarkSourceLocatorV1] = []
        seen: set[tuple[str, int, int]] = set()
        for locator in claim.evidence_locations:
            key = (locator.source_path, locator.start_line, locator.end_line)
            if key in seen:
                continue
            seen.add(key)
            unique.append(locator)
        if unique:
            buckets.append((claim.claim_id, tuple(unique)))

    if len(buckets) > MAX_EVIDENCE_RECORDS:
        raise BenchmarkSemanticValidationError(
            "claims with evidence locations exceed final EvidenceSubmission evidence cap"
        )

    selected: dict[str, list[BenchmarkSourceLocatorV1]] = {
        claim_id: [locations[0]] for claim_id, locations in buckets
    }
    remaining_slots = MAX_EVIDENCE_RECORDS - len(buckets)
    depth = 1
    while remaining_slots > 0:
        progressed = False
        for claim_id, locations in buckets:
            if depth >= len(locations):
                continue
            selected[claim_id].append(locations[depth])
            remaining_slots -= 1
            progressed = True
            if remaining_slots == 0:
                break
        if not progressed:
            break
        depth += 1

    published_reference_count = sum(len(items) for items in selected.values())
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
    selected_locations, _omitted = compact_claim_locations(payload)
    evidence_records_list: list[EvidenceRecordV1] = []
    claim_evidence_ids: dict[tuple[str, str, int, int], str] = {}
    for claim in payload.claims:
        for locator in selected_locations.get(claim.claim_id, ()):
            citation = _resolve_source_locator_from_sources(sources, locator)
            key = (
                claim.claim_id,
                locator.source_path,
                locator.start_line,
                locator.end_line,
            )
            evidence_id = "g6_evidence_" + sha256_hex(
                f"{claim.claim_id}\0{citation.citation_id}".encode("utf-8")
            )[:24]
            claim_evidence_ids[key] = evidence_id
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
                        (
                            claim.claim_id,
                            item.source_path,
                            item.start_line,
                            item.end_line,
                        )
                    ]
                    for item in selected_locations.get(claim.claim_id, ())
                ),
                opposes_evidence_ids=(),
                uncertainty_ids=claim.uncertainty_ids,
            )
            for claim in payload.claims
        ),
        evidence=tuple(evidence_records_list),
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
