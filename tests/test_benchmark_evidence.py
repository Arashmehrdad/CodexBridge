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
    BenchmarkSourceQuoteV1,
    BenchmarkUsageV1,
    build_evidence_submission,
    compact_claim_quotes,
    parse_semantic_output,
    resolve_source_quote,
    semantic_output_schema,
    semantic_payload_hash,
    semantic_prompt,
    validate_semantic_against_packet,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _packet() -> bytes:
    return build_assignment_packet(REPO_ROOT, "B01")


def _quote_for(source_path: str, needle: str) -> dict[str, str]:
    packet = json.loads(_packet())
    source = next(item for item in packet["sources"] if item["path"] == source_path)
    matches = [line.strip() for line in source["content"].splitlines() if needle in line]
    assert len(matches) == 1, (source_path, needle, matches)
    quote = matches[0]
    assert quote and source["content"].count(quote) == 1
    return {"source_path": source_path, "quote": quote}


def _unique_quote_pool(count: int) -> list[dict[str, str]]:
    packet = json.loads(_packet())
    result: list[dict[str, str]] = []
    for source in packet["sources"]:
        content = source["content"]
        for line in content.splitlines():
            quote = line.strip()
            if not quote or len(quote) > 480 or content.count(quote) != 1:
                continue
            result.append({"source_path": source["path"], "quote": quote})
            if len(result) == count:
                return result
    raise AssertionError(f"only found {len(result)} unique source quotes")


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
    evidence_quotes = []
    for index, (_evidence_id, source, needle, fact_key, _fact_value) in enumerate(
        evidence_specs, start=1
    ):
        source_quote = _quote_for(source["path"], needle)
        evidence_quotes.append(source_quote)
        claims.append(
            {
                "claim_id": f"claim_{index}",
                "claim_class": "observation",
                "subject_key": fact_key,
                "statement": f"Fixture claim for {fact_key}.",
                "evidence_quotes": [source_quote],
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
            "evidence_quotes": [evidence_quotes[0]],
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
    assert "evidence_quotes" in claim_properties
    assert "supports_citation_ids" not in claim_properties
    assert "opposes_citation_ids" not in claim_properties
    assert "supports_evidence_ids" not in claim_properties
    assert "Do not use tools, files, network sources" in prompt
    assert "There is no opposition relation" in prompt
    assert "Do not implement or modify anything" in prompt
    assert BENCHMARK_SEMANTIC_SCHEMA_VERSION in prompt


def test_valid_payload_is_grounded_in_frozen_packet() -> None:
    payload = _valid_payload()

    validate_semantic_against_packet(payload, _packet())
    assert payload.critical_trap.disposition == "false"
    assert len(payload.claims) == 5


def test_unknown_source_path_is_rejected() -> None:
    value = _valid_payload_dict()
    value["claims"][0]["evidence_quotes"] = [
        {"source_path": "invented.py", "quote": "invented"}
    ]
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="not assignment-provided"):
        validate_semantic_against_packet(payload, _packet())


def test_source_quote_resolution_is_deterministic_single_line_and_source_exact() -> None:
    source_quote = BenchmarkSourceQuoteV1.model_validate(
        _quote_for("soma/tasks/models.py", "class BackendKind")
    )
    first = resolve_source_quote(_packet(), source_quote)
    second = resolve_source_quote(_packet(), source_quote)

    assert first == second
    assert first.source_path == "soma/tasks/models.py"
    assert first.start_line == first.end_line
    assert first.excerpt == source_quote.quote
    assert len(first.excerpt) <= 480


def test_source_quote_must_be_unique_and_single_line() -> None:
    packet = json.loads(_packet())
    source = next(item for item in packet["sources"] if item["path"] == "soma/tasks/models.py")
    repeated = next(
        line.strip()
        for line in source["content"].splitlines()
        if line.strip() and source["content"].count(line.strip()) > 1
    )
    payload_value = _valid_payload_dict()
    payload_value["claims"][0]["evidence_quotes"] = [
        {"source_path": source["path"], "quote": repeated}
    ]
    payload = BenchmarkSemanticPayloadV1.model_validate(payload_value)
    with pytest.raises(BenchmarkSemanticValidationError, match="exactly one"):
        validate_semantic_against_packet(payload, _packet())

    with pytest.raises(ValueError):
        BenchmarkSourceQuoteV1(source_path=source["path"], quote="a\nb")


def test_provider_schema_has_support_only_quotes_and_no_parallel_evidence_list() -> None:
    schema = semantic_output_schema()
    assert "evidence" not in schema["properties"]
    assert "BenchmarkSemanticEvidenceV1" not in schema.get("$defs", {})
    prompt = semantic_prompt(_packet())
    assert "evidence_quotes" in prompt
    assert "support-only" in prompt
    assert "there is no opposition relation" in prompt.lower()
    assert "CITATION CATALOG JSON" not in prompt


def test_packet_bound_schema_enums_exact_fact_keys_and_source_paths() -> None:
    packet = _packet()
    packet_value = json.loads(packet)
    schema = semantic_output_schema(packet)
    definitions = schema["$defs"]
    claim_properties = definitions["BenchmarkSemanticClaimV1"]["properties"]
    quote_properties = definitions["BenchmarkSourceQuoteV1"]["properties"]
    expected_fact_keys = [
        item["fact_key"] for item in packet_value["rubric"]["questions"]
    ]
    expected_source_paths = [item["path"] for item in packet_value["sources"]]

    assert claim_properties["subject_key"] == {
        "enum": expected_fact_keys,
        "type": "string",
    }
    assert definitions["BenchmarkPacketSourcePath"] == {
        "enum": expected_source_paths,
        "type": "string",
    }
    assert quote_properties["source_path"] == {
        "$ref": "#/$defs/BenchmarkPacketSourcePath"
    }
    assert semantic_output_schema(packet) == schema


def test_b06_packet_schema_binds_only_assigned_source_paths() -> None:
    packet = build_assignment_packet(REPO_ROOT, "B06")
    packet_value = json.loads(packet)
    schema = semantic_output_schema(packet)
    allowed = set(schema["$defs"]["BenchmarkPacketSourcePath"]["enum"])

    assert allowed == {item["path"] for item in packet_value["sources"]}


def test_unassigned_fact_key_is_rejected() -> None:
    value = _valid_payload_dict()
    value["claims"][0]["subject_key"] = "invented.semantic.key"
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(
        BenchmarkSemanticValidationError, match="not assignment-provided"
    ):
        validate_semantic_against_packet(payload, _packet())


def test_claim_quote_volume_is_compacted_deterministically_to_evidence_cap() -> None:
    value = _valid_payload_dict()
    quote_pool = _unique_quote_pool(25)
    for index, claim in enumerate(value["claims"]):
        claim["evidence_quotes"] = quote_pool[index * 5 : (index + 1) * 5]
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    validate_semantic_against_packet(payload, _packet())
    selected, omitted = compact_claim_quotes(payload)
    assert sum(len(items) for items in selected.values()) == 24
    assert omitted == 1
    assert [len(selected[claim["claim_id"]]) for claim in value["claims"]] == [
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
    assert all(not claim.opposes_evidence_ids for claim in submission.claims)


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
