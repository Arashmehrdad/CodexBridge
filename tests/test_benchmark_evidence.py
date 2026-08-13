"""G6 generic frozen-source semantic evidence bridge tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from soma.agent_worker_benchmark import build_assignment_packet
from soma.reasoning.benchmark_evidence import (
    BENCHMARK_SEMANTIC_SCHEMA_VERSION,
    BenchmarkSemanticPayloadV1,
    BenchmarkSemanticValidationError,
    BenchmarkUsageV1,
    build_evidence_submission,
    citation_catalog,
    compact_claim_citations,
    parse_semantic_output,
    semantic_output_schema,
    semantic_payload_hash,
    semantic_prompt,
    validate_semantic_against_packet,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _packet() -> bytes:
    return build_assignment_packet(REPO_ROOT, "B01")


def _citation_for(source_path: str, needle: str) -> str:
    matches = [
        item.citation_id
        for item in citation_catalog(_packet())
        if item.source_path == source_path and needle in item.excerpt
    ]
    assert len(matches) == 1, (source_path, needle, matches)
    return matches[0]


def _valid_payload_dict() -> dict:
    packet = json.loads(_packet())
    sources = {source["path"]: source for source in packet["sources"]}
    models = sources["soma/tasks/models.py"]
    backends = sources["soma/tasks/backends.py"]
    projections = sources["soma/tasks/projections.py"]

    evidence_specs = [
        (
            "e_state_owner",
            models,
            "class TaskState",
            "task.canonical_state_owner",
            "TaskState",
        ),
        (
            "e_task_kind",
            models,
            "class TaskKind",
            "task.current_task_kind_set",
            "TaskKind",
        ),
        (
            "e_backend_kind",
            models,
            "class BackendKind",
            "task.current_backend_kind_set",
            "BackendKind",
        ),
        (
            "e_result_policy",
            projections,
            "result_reference",
            "task.result_body_policy",
            "bounded result reference",
        ),
        (
            "e_protocol",
            backends,
            "class ExecutionBackend",
            "task.backend_protocol_shape",
            "ExecutionBackend protocol",
        ),
    ]
    claims = []
    citation_ids = []
    for index, (_evidence_id, source, needle, fact_key, _fact_value) in enumerate(
        evidence_specs, start=1
    ):
        citation_id = _citation_for(source["path"], needle)
        citation_ids.append(citation_id)
        claims.append(
            {
                "claim_id": f"claim_{index}",
                "claim_class": "observation",
                "subject_key": fact_key,
                "statement": f"Fixture claim for {fact_key}.",
                "supports_citation_ids": [citation_id],
                "opposes_citation_ids": [],
                "uncertainty_ids": [],
            }
        )

    return {
        "schema_version": BENCHMARK_SEMANTIC_SCHEMA_VERSION,
        "submission_disposition": "complete",
        "executive_summary": "Bounded B01 fixture evidence.",
        "claims": claims,
        "uncertainties": [],
        "blockers": [],
        "critical_trap": {
            "disposition": "false",
            "statement": "Task admission is not substantive outcome acceptance.",
            "supports_citation_ids": [citation_ids[0]],
        },
    }


def _valid_payload() -> BenchmarkSemanticPayloadV1:
    return BenchmarkSemanticPayloadV1.model_validate(_valid_payload_dict())


def test_schema_and_prompt_are_strict_read_only() -> None:
    schema = semantic_output_schema()
    prompt = semantic_prompt(_packet())

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema_version",
        "submission_disposition",
        "executive_summary",
        "claims",
        "uncertainties",
        "blockers",
        "critical_trap",
    }

    def assert_strict(value) -> None:
        if isinstance(value, list):
            for item in value:
                assert_strict(item)
            return
        if not isinstance(value, dict):
            return
        assert "default" not in value
        properties = value.get("properties")
        if isinstance(properties, dict):
            assert value.get("additionalProperties") is False
            assert value.get("required") == list(properties)
        for item in value.values():
            assert_strict(item)

    assert_strict(schema)
    assert "evidence" not in schema["properties"]
    claim_properties = schema["$defs"]["BenchmarkSemanticClaimV1"]["properties"]
    assert "supports_citation_ids" in claim_properties
    assert "opposes_citation_ids" in claim_properties
    assert "supports_evidence_ids" not in claim_properties
    assert "Do not use tools, files, network sources" in prompt
    assert "Do not implement or modify anything" in prompt
    assert BENCHMARK_SEMANTIC_SCHEMA_VERSION in prompt


def test_valid_payload_is_grounded_in_frozen_packet() -> None:
    payload = _valid_payload()

    validate_semantic_against_packet(payload, _packet())
    assert payload.critical_trap.disposition == "false"
    assert len(payload.claims) == 5


def test_unknown_citation_id_is_rejected() -> None:
    value = _valid_payload_dict()
    unknown = "S99C9999"
    value["claims"][0]["supports_citation_ids"] = [unknown]
    value["critical_trap"]["supports_citation_ids"] = [unknown]
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="assignment catalog"):
        validate_semantic_against_packet(payload, _packet())


def test_citation_catalog_is_deterministic_bounded_and_source_exact() -> None:
    first = citation_catalog(_packet())
    second = citation_catalog(_packet())
    packet = json.loads(_packet())
    sources = {source["path"]: source for source in packet["sources"]}

    assert first == second
    assert first
    assert len({item.citation_id for item in first}) == len(first)
    for item in first:
        lines = sources[item.source_path]["content"].splitlines()
        selected = "\n".join(lines[item.start_line - 1 : item.end_line])
        assert selected == item.excerpt
        assert 1 <= item.end_line - item.start_line + 1 <= 4
        assert len(item.excerpt) <= 480


def test_provider_schema_has_no_parallel_evidence_list() -> None:
    schema = semantic_output_schema()
    assert "evidence" not in schema["properties"]
    assert "BenchmarkSemanticEvidenceV1" not in schema.get("$defs", {})
    prompt = semantic_prompt(_packet())
    assert "or return a parallel evidence list" in prompt.lower()
    assert "those two citation-id sets must be disjoint" in prompt.lower()


def test_packet_bound_schema_enums_exact_fact_keys_and_catalog_ids() -> None:
    packet = _packet()
    packet_value = json.loads(packet)
    schema = semantic_output_schema(packet)
    definitions = schema["$defs"]
    claim_properties = definitions["BenchmarkSemanticClaimV1"]["properties"]
    trap_properties = definitions["BenchmarkCriticalTrapV1"]["properties"]
    expected_fact_keys = [
        item["fact_key"] for item in packet_value["rubric"]["questions"]
    ]
    expected_citations = [item.citation_id for item in citation_catalog(packet)]

    assert claim_properties["subject_key"] == {
        "enum": expected_fact_keys,
        "type": "string",
    }
    assert definitions["BenchmarkPacketCitationId"] == {
        "enum": expected_citations,
        "type": "string",
    }
    citation_ref = {"$ref": "#/$defs/BenchmarkPacketCitationId"}
    assert claim_properties["supports_citation_ids"]["items"] == citation_ref
    assert claim_properties["opposes_citation_ids"]["items"] == citation_ref
    assert trap_properties["supports_citation_ids"]["items"] == citation_ref
    assert semantic_output_schema(packet) == schema


def test_b06_packet_schema_excludes_observed_hallucinated_citation_ids() -> None:
    packet = build_assignment_packet(REPO_ROOT, "B06")
    schema = semantic_output_schema(packet)
    allowed = set(schema["$defs"]["BenchmarkPacketCitationId"]["enum"])

    assert allowed == {item.citation_id for item in citation_catalog(packet)}
    assert {"S02C0051", "S02C0052", "S02C0054"}.isdisjoint(allowed)


def test_unassigned_fact_key_is_rejected() -> None:
    value = _valid_payload_dict()
    value["claims"][0]["subject_key"] = "invented.semantic.key"
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(
        BenchmarkSemanticValidationError, match="not assignment-provided"
    ):
        validate_semantic_against_packet(payload, _packet())


def test_claim_citation_volume_is_compacted_deterministically_to_evidence_cap() -> None:
    value = _valid_payload_dict()
    catalog_ids = [item.citation_id for item in citation_catalog(_packet())][:25]
    for index, claim in enumerate(value["claims"]):
        claim["supports_citation_ids"] = catalog_ids[index * 5 : (index + 1) * 5]
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    validate_semantic_against_packet(payload, _packet())
    selected, omitted = compact_claim_citations(payload)
    assert sum(len(items) for items in selected.values()) == 24
    assert omitted == 1
    assert [
        len(selected[(claim["claim_id"], "support")]) for claim in value["claims"]
    ] == [
        5,
        5,
        5,
        5,
        4,
    ]

    submission = build_evidence_submission(
        payload=payload,
        packet_bytes=_packet(),
        task_id="task_g6_compaction",
        backend_ref="reasoning_g6_compaction",
        assignment_ref="benchmark:B01",
        provider_model="gpt-5.6-luna",
        provider_thread_id="thr_g6_compaction",
        usage=BenchmarkUsageV1(),
        wall_time_seconds=0.5,
    )
    assert len(submission.evidence) == 24
    assert [len(claim.supports_evidence_ids) for claim in submission.claims] == [
        5,
        5,
        5,
        5,
        4,
    ]


def test_complete_submission_requires_all_five_fact_keys() -> None:
    value = _valid_payload_dict()
    value["claims"] = value["claims"][:-1]
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="missing required"):
        validate_semantic_against_packet(payload, _packet())


def test_exact_json_parser_rejects_markdown_wrapper() -> None:
    payload = _valid_payload()
    text = payload.model_dump_json()

    assert parse_semantic_output(text) == payload
    with pytest.raises(BenchmarkSemanticValidationError, match="not exact JSON"):
        parse_semantic_output("```json\n" + text + "\n```")


def test_bridge_injects_canonical_identity_and_builds_bounded_submission() -> None:
    packet = _packet()
    payload = _valid_payload()
    submission = build_evidence_submission(
        payload=payload,
        packet_bytes=packet,
        task_id="task_g6_fixture",
        backend_ref="reasoning_g6_fixture",
        assignment_ref="benchmark:B01",
        provider_model="gpt-5.6-luna",
        provider_thread_id="thr_g6_fixture",
        usage=BenchmarkUsageV1(
            input_tokens=120,
            cached_input_tokens=20,
            output_tokens=30,
            reasoning_output_tokens=5,
            total_tokens=150,
        ),
        wall_time_seconds=1.5,
        provenance_refs=(("codex:thread:thr_g6_fixture", "a" * 64),),
        raw_provider_ref="codex:events:g6-fixture",
        raw_provider_hash="b" * 64,
    )

    assert submission.work_identity.task_id == "task_g6_fixture"
    assert submission.work_identity.backend_ref == "reasoning_g6_fixture"
    assert submission.assignment.contract_hash == hashlib.sha256(packet).hexdigest()
    assert submission.assignment.contract_hash != semantic_payload_hash(payload)
    assert submission.producer.provider == "codex"
    assert submission.producer.native_session_ref == "thr_g6_fixture"
    assert submission.usage.input_tokens == 120
    assert submission.usage.output_tokens == 30
    assert submission.within_normal_target is True
    assert {record.fact_key for record in submission.evidence} == {
        "task.canonical_state_owner",
        "task.current_task_kind_set",
        "task.current_backend_kind_set",
        "task.result_body_policy",
        "task.backend_protocol_shape",
    }
    assert all(record.source_ref.startswith("git:") for record in submission.evidence)


def test_semantic_hash_is_deterministic() -> None:
    assert semantic_payload_hash(_valid_payload()) == semantic_payload_hash(
        _valid_payload()
    )
