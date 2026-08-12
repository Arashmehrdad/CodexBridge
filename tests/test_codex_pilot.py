"""G5 CDX-R1 semantic packet and EvidenceSubmission bridge tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from soma.reasoning.codex_pilot import (
    CDX_R1_SEMANTIC_SCHEMA_VERSION,
    CDXR1SemanticPayloadV1,
    CDXR1SemanticValidationError,
    CDXR1UsageV1,
    build_evidence_submission,
    extract_usage,
    load_packet_bytes,
    packet_hash,
    parse_semantic_output,
    semantic_output_schema,
    semantic_payload_hash,
    semantic_prompt,
    validate_semantic_against_packet,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "agent-worker-research"
    / "fixtures"
    / "cdx-r1-synthetic-packet.json"
)


def _valid_payload_dict() -> dict:
    return {
        "schema_version": CDX_R1_SEMANTIC_SCHEMA_VERSION,
        "submission_disposition": "uncertain",
        "executive_summary": (
            "Meridian is on the beta channel; the packet gives conflicting "
            "retry limits of 3 and 4 attempts."
        ),
        "claims": [
            {
                "claim_id": "c_project",
                "claim_class": "observation",
                "subject_key": "project_codename",
                "statement": "The project codename is Meridian.",
                "supports_evidence_ids": ["e_r01"],
                "opposes_evidence_ids": [],
                "uncertainty_ids": [],
            },
            {
                "claim_id": "c_channel",
                "claim_class": "observation",
                "subject_key": "release_channel",
                "statement": "The release channel is beta.",
                "supports_evidence_ids": ["e_r02"],
                "opposes_evidence_ids": [],
                "uncertainty_ids": [],
            },
            {
                "claim_id": "c_retry",
                "claim_class": "observation",
                "subject_key": "retry_limit",
                "statement": "The packet contains incompatible retry limits of 3 and 4.",
                "supports_evidence_ids": ["e_r03", "e_r05"],
                "opposes_evidence_ids": [],
                "uncertainty_ids": ["u_retry"],
            },
        ],
        "evidence": [
            {
                "evidence_id": "e_r01",
                "record_id": "R01",
                "fact_key": "project_codename",
                "fact_value": "Meridian",
            },
            {
                "evidence_id": "e_r02",
                "record_id": "R02",
                "fact_key": "release_channel",
                "fact_value": "beta",
            },
            {
                "evidence_id": "e_r03",
                "record_id": "R03",
                "fact_key": "retry_limit",
                "fact_value": "3",
            },
            {
                "evidence_id": "e_r05",
                "record_id": "R05",
                "fact_key": "retry_limit",
                "fact_value": "4",
            },
        ],
        "uncertainties": [
            {
                "uncertainty_id": "u_retry",
                "kind": "conflicting_packet_facts",
                "statement": "R03 and R05 disagree on retry_limit.",
                "related_claim_ids": ["c_retry"],
                "required_resolution": "A higher-authority retry-limit source is required.",
            }
        ],
        "blockers": [],
    }


def _valid_payload() -> CDXR1SemanticPayloadV1:
    return CDXR1SemanticPayloadV1.model_validate(_valid_payload_dict())


def test_packet_and_prompt_are_exact_read_only_inputs() -> None:
    packet = load_packet_bytes(FIXTURE)
    prompt = semantic_prompt(packet)

    assert packet_hash(packet) == packet_hash(FIXTURE.read_bytes())
    assert '"record_id": "R01"' in prompt
    assert "Do not use tools, files, network sources" in prompt
    assert "retry_limit" in prompt
    assert CDX_R1_SEMANTIC_SCHEMA_VERSION in prompt


def test_output_schema_requires_complete_strict_top_level_shape() -> None:
    schema = semantic_output_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema_version",
        "submission_disposition",
        "executive_summary",
        "claims",
        "evidence",
        "uncertainties",
        "blockers",
    }


def test_valid_semantics_preserve_both_retry_values_and_uncertainty() -> None:
    packet = load_packet_bytes(FIXTURE)
    payload = _valid_payload()

    validate_semantic_against_packet(payload, packet)

    retry_values = {
        item.fact_value for item in payload.evidence if item.fact_key == "retry_limit"
    }
    assert retry_values == {"3", "4"}
    assert payload.claims[-1].uncertainty_ids == ("u_retry",)


def test_provider_cannot_change_packet_fact_value() -> None:
    packet = load_packet_bytes(FIXTURE)
    value = _valid_payload_dict()
    value["evidence"][0]["fact_value"] = "Northstar"
    payload = CDXR1SemanticPayloadV1.model_validate(value)

    with pytest.raises(CDXR1SemanticValidationError, match="changed packet fact value"):
        validate_semantic_against_packet(payload, packet)


def test_provider_must_preserve_both_conflicting_packet_values() -> None:
    packet = load_packet_bytes(FIXTURE)
    value = _valid_payload_dict()
    value["evidence"] = [
        item for item in value["evidence"] if item["record_id"] != "R05"
    ]
    value["claims"][-1]["supports_evidence_ids"] = ["e_r03"]
    payload = CDXR1SemanticPayloadV1.model_validate(value)

    with pytest.raises(CDXR1SemanticValidationError, match="did not preserve both"):
        validate_semantic_against_packet(payload, packet)


def test_provider_must_link_conflict_to_explicit_uncertainty() -> None:
    packet = load_packet_bytes(FIXTURE)
    value = _valid_payload_dict()
    value["claims"][-1]["uncertainty_ids"] = []
    value["uncertainties"] = []
    payload = CDXR1SemanticPayloadV1.model_validate(value)

    with pytest.raises(CDXR1SemanticValidationError, match="was not marked uncertain"):
        validate_semantic_against_packet(payload, packet)


def test_parse_semantic_output_requires_exact_json_not_markdown() -> None:
    payload = _valid_payload()
    text = payload.model_dump_json()

    parsed = parse_semantic_output(text)
    assert parsed == payload

    with pytest.raises(CDXR1SemanticValidationError, match="not exact JSON"):
        parse_semantic_output("```json\n" + text + "\n```")


def test_usage_projection_accepts_current_camel_case_snapshot() -> None:
    usage = extract_usage(
        (
            {
                "threadId": "thr_fixture",
                "tokenUsage": {
                    "total": {
                        "inputTokens": 120,
                        "cachedInputTokens": 20,
                        "outputTokens": 30,
                        "reasoningOutputTokens": 5,
                        "totalTokens": 150,
                    }
                },
            },
        )
    )

    assert usage == CDXR1UsageV1(
        input_tokens=120,
        cached_input_tokens=20,
        output_tokens=30,
        reasoning_output_tokens=5,
        total_tokens=150,
    )


def test_usage_projection_never_invents_missing_counts() -> None:
    assert extract_usage(()) == CDXR1UsageV1()
    assert extract_usage(({"threadId": "thr", "tokenUsage": None},)) == CDXR1UsageV1()


def test_mechanical_bridge_builds_valid_bounded_evidence_submission() -> None:
    packet = load_packet_bytes(FIXTURE)
    payload = _valid_payload()
    usage = CDXR1UsageV1(
        input_tokens=200,
        cached_input_tokens=25,
        output_tokens=50,
        reasoning_output_tokens=10,
        total_tokens=250,
    )

    submission = build_evidence_submission(
        payload=payload,
        packet_bytes=packet,
        task_id="task_cdx_r1_fixture",
        backend_ref="reasoning_cdx_r1_fixture",
        assignment_ref="assignment:cdx-r1-synthetic-packet",
        provider_model="gpt-5.6-luna",
        provider_thread_id="thr_fixture",
        usage=usage,
        wall_time_seconds=1.25,
        provenance_refs=(("codex:thread:thr_fixture", "a" * 64),),
        raw_provider_ref="codex:raw:fixture",
        raw_provider_hash="b" * 64,
    )

    assert submission.work_identity.task_id == "task_cdx_r1_fixture"
    assert submission.producer.provider == "codex"
    assert submission.producer.model_or_profile == "gpt-5.6-luna"
    assert submission.producer.native_session_ref == "thr_fixture"
    assert submission.assignment.contract_hash == packet_hash(packet)
    assert submission.usage.input_tokens == 200
    assert submission.usage.output_tokens == 50
    assert submission.usage.cost_usd == Decimal("0")
    assert {record.locator for record in submission.evidence} == {
        "record:R01",
        "record:R02",
        "record:R03",
        "record:R05",
    }
    assert submission.full_evidence_retrieval[0].ref == "codex:raw:fixture"
    assert submission.within_normal_target is True


def test_submission_and_semantic_identity_are_deterministic() -> None:
    packet = load_packet_bytes(FIXTURE)
    payload = _valid_payload()
    kwargs = {
        "payload": payload,
        "packet_bytes": packet,
        "task_id": "task_deterministic",
        "backend_ref": "reasoning_deterministic",
        "assignment_ref": "assignment:cdx-r1-synthetic-packet",
        "provider_model": "gpt-5.6-luna",
        "provider_thread_id": "thr_deterministic",
        "usage": CDXR1UsageV1(input_tokens=1, output_tokens=1, total_tokens=2),
        "wall_time_seconds": 2.0,
    }

    first = build_evidence_submission(**kwargs)
    second = build_evidence_submission(**kwargs)

    assert semantic_payload_hash(payload) == semantic_payload_hash(_valid_payload())
    assert first.submission_id == second.submission_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
