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
    parse_semantic_output,
    semantic_output_schema,
    semantic_payload_hash,
    semantic_prompt,
    validate_semantic_against_packet,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _packet() -> bytes:
    return build_assignment_packet(REPO_ROOT, "B01")


def _line_for(source: dict, needle: str) -> tuple[int, str]:
    for index, line in enumerate(source["content"].splitlines(), start=1):
        if needle in line:
            return index, line.strip()
    raise AssertionError(f"needle not found: {needle!r}")


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
    evidence = []
    claims = []
    for index, (evidence_id, source, needle, fact_key, fact_value) in enumerate(
        evidence_specs, start=1
    ):
        line_number, excerpt = _line_for(source, needle)
        evidence.append(
            {
                "evidence_id": evidence_id,
                "source_path": source["path"],
                "start_line": line_number,
                "end_line": line_number,
                "excerpt": excerpt,
                "fact_key": fact_key,
                "fact_value": fact_value,
            }
        )
        claims.append(
            {
                "claim_id": f"claim_{index}",
                "claim_class": "observation",
                "subject_key": fact_key,
                "statement": f"Fixture claim for {fact_key}.",
                "supports_evidence_ids": [evidence_id],
                "opposes_evidence_ids": [],
                "uncertainty_ids": [],
            }
        )

    return {
        "schema_version": BENCHMARK_SEMANTIC_SCHEMA_VERSION,
        "submission_disposition": "complete",
        "executive_summary": "Bounded B01 fixture evidence.",
        "claims": claims,
        "evidence": evidence,
        "uncertainties": [],
        "blockers": [],
        "critical_trap": {
            "disposition": "false",
            "statement": "Task admission is not substantive outcome acceptance.",
            "supports_evidence_ids": ["e_state_owner"],
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
        "evidence",
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
    fact_value = schema["$defs"]["BenchmarkSemanticEvidenceV1"]["properties"][
        "fact_value"
    ]
    assert {item.get("type") for item in fact_value["anyOf"]} == {
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    }
    assert "Do not use tools, files, network sources" in prompt
    assert "Do not implement or modify anything" in prompt
    assert BENCHMARK_SEMANTIC_SCHEMA_VERSION in prompt


def test_valid_payload_is_grounded_in_frozen_packet() -> None:
    payload = _valid_payload()

    validate_semantic_against_packet(payload, _packet())
    assert payload.critical_trap.disposition == "false"
    assert len(payload.claims) == 5
    assert len(payload.evidence) == 5


def test_wrong_source_path_is_rejected() -> None:
    value = _valid_payload_dict()
    value["evidence"][0]["source_path"] = "soma/not-in-assignment.py"
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="outside assignment"):
        validate_semantic_against_packet(payload, _packet())


def test_out_of_range_lines_are_rejected() -> None:
    value = _valid_payload_dict()
    value["evidence"][0]["start_line"] = 999999
    value["evidence"][0]["end_line"] = 999999
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="line range exceeds"):
        validate_semantic_against_packet(payload, _packet())


def test_fabricated_excerpt_is_rejected() -> None:
    value = _valid_payload_dict()
    value["evidence"][0]["excerpt"] = "this exact text is not in the frozen source"
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="excerpt is not exact"):
        validate_semantic_against_packet(payload, _packet())


def test_unassigned_fact_key_is_rejected() -> None:
    value = _valid_payload_dict()
    value["claims"][0]["subject_key"] = "invented.semantic.key"
    value["evidence"][0]["fact_key"] = "invented.semantic.key"
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(
        BenchmarkSemanticValidationError, match="not assignment-provided"
    ):
        validate_semantic_against_packet(payload, _packet())


def test_claim_cannot_use_evidence_from_another_fact_key() -> None:
    value = _valid_payload_dict()
    value["claims"][0]["supports_evidence_ids"] = ["e_task_kind"]
    payload = BenchmarkSemanticPayloadV1.model_validate(value)

    with pytest.raises(BenchmarkSemanticValidationError, match="another fact key"):
        validate_semantic_against_packet(payload, _packet())


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
