"""G6 v9 smart-worker / mechanical-Soma evidence boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.agent_worker_benchmark import build_assignment_packet
from soma.reasoning.benchmark_evidence_v9 import (
    BENCHMARK_SEMANTIC_SCHEMA_VERSION,
    BenchmarkSemanticPayloadV1,
    BenchmarkSemanticValidationError,
    BenchmarkSourceLocatorV1,
    BenchmarkUsageV1,
    build_evidence_submission,
    resolve_source_locator,
    semantic_output_schema,
    semantic_prompt,
    validate_semantic_against_packet,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _packet() -> bytes:
    return build_assignment_packet(REPO_ROOT, "B01")


def _location_for(source_path: str, needle: str) -> dict[str, int | str]:
    packet = json.loads(_packet())
    source = next(item for item in packet["sources"] if item["path"] == source_path)
    matches = [
        number
        for number, line in enumerate(source["content"].splitlines(), start=1)
        if needle in line
    ]
    assert matches, (source_path, needle)
    number = matches[0]
    return {"source_path": source_path, "start_line": number, "end_line": number}


def _payload() -> BenchmarkSemanticPayloadV1:
    specs = [
        ("soma/tasks/models.py", "class TaskState", "task.canonical_state_owner"),
        ("soma/tasks/models.py", "class TaskKind", "task.current_task_kind_set"),
        ("soma/tasks/models.py", "class BackendKind", "task.current_backend_kind_set"),
        ("soma/tasks/projections.py", "result_reference", "task.result_body_policy"),
        ("soma/tasks/backends.py", "class ExecutionBackend", "task.backend_protocol_shape"),
    ]
    claims = []
    locations = []
    for index, (path, needle, fact_key) in enumerate(specs, start=1):
        location = _location_for(path, needle)
        locations.append(location)
        claims.append(
            {
                "claim_id": f"claim_{index}",
                "claim_class": "observation",
                "subject_key": fact_key,
                "statement": f"Worker assertion for {fact_key}.",
                "evidence_locations": [location],
                "uncertainty_ids": [],
            }
        )
    return BenchmarkSemanticPayloadV1.model_validate(
        {
            "schema_version": BENCHMARK_SEMANTIC_SCHEMA_VERSION,
            "submission_disposition": "complete",
            "executive_summary": "Fixture worker result.",
            "claims": claims,
            "uncertainties": [],
            "blockers": [],
            "critical_trap": {
                "disposition": "false",
                "statement": "Fixture trap disposition.",
                "evidence_locations": [locations[0]],
            },
        }
    )


def test_provider_contract_makes_semantic_authority_explicit() -> None:
    prompt = semantic_prompt(_packet())
    schema = semantic_output_schema(_packet())

    assert "smart read-only G6 reasoning worker" in prompt
    assert "You own the semantic reasoning" in prompt
    assert "Soma will not judge whether your evidence proves your claim" in prompt
    assert "PROVIDER ASSIGNMENT VIEW JSON" in prompt
    assert "numbered_content" in prompt
    assert "evidence_locations" in schema["$defs"]["BenchmarkSemanticClaimV1"][
        "properties"
    ]
    assert "BenchmarkSourceQuoteV1" not in schema.get("$defs", {})


def test_locator_materialization_needs_no_unique_quote_identity() -> None:
    packet_value = json.loads(_packet())
    source = next(
        item for item in packet_value["sources"] if item["path"] == "soma/tasks/backends.py"
    )
    lines = source["content"].splitlines()
    repeated_text = next(
        line for line in lines if line and source["content"].count(line) > 1
    )
    line_number = next(
        index for index, line in enumerate(lines, start=1) if line == repeated_text
    )
    locator = BenchmarkSourceLocatorV1(
        source_path=source["path"], start_line=line_number, end_line=line_number
    )

    citation = resolve_source_locator(_packet(), locator)

    assert citation.start_line == line_number
    assert citation.end_line == line_number
    assert citation.excerpt == repeated_text[:512]


def test_soma_rejects_only_invalid_assignment_or_locator_mechanics() -> None:
    payload = _payload()
    value = payload.model_dump(mode="json")
    value["claims"][0]["evidence_locations"] = [
        {"source_path": "invented.py", "start_line": 1, "end_line": 1}
    ]
    bad_path = BenchmarkSemanticPayloadV1.model_validate(value)
    with pytest.raises(BenchmarkSemanticValidationError, match="not assignment-provided"):
        validate_semantic_against_packet(bad_path, _packet())

    value = payload.model_dump(mode="json")
    value["claims"][0]["evidence_locations"] = [
        {
            "source_path": "soma/tasks/models.py",
            "start_line": 999999,
            "end_line": 999999,
        }
    ]
    bad_range = BenchmarkSemanticPayloadV1.model_validate(value)
    with pytest.raises(BenchmarkSemanticValidationError, match="line count"):
        validate_semantic_against_packet(bad_range, _packet())


def test_soma_preserves_worker_semantics_without_grading_them() -> None:
    payload = _payload()
    value = payload.model_dump(mode="json")
    value["claims"][0]["statement"] = (
        "Deliberately semantically wrong fixture statement; Sol must judge this later."
    )
    semantically_wrong_but_mechanically_valid = BenchmarkSemanticPayloadV1.model_validate(
        value
    )

    validate_semantic_against_packet(semantically_wrong_but_mechanically_valid, _packet())
    submission = build_evidence_submission(
        payload=semantically_wrong_but_mechanically_valid,
        packet_bytes=_packet(),
        task_id="task_g6_v9_fixture",
        backend_ref="reasoning_g6_v9_fixture",
        assignment_ref="benchmark:B01",
        provider_model="gpt-5.6-luna",
        provider_thread_id="thr_g6_v9_fixture",
        usage=BenchmarkUsageV1(),
        wall_time_seconds=0.1,
    )

    assert submission.claims[0].statement.startswith("Deliberately semantically wrong")
    assert submission.claims[0].supports_evidence_ids
    assert submission.evidence[0].source_ref.startswith("git:")
    assert submission.evidence[0].locator.startswith("lines:")
