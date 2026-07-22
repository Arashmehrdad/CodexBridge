from __future__ import annotations

from dataclasses import replace

import pytest

from soma.cf1_fixture_footprint import (
    CF1_FIXTURE_FOOTPRINT_VERSION,
    build_representative_fixture_payload,
    measure_fixture_footprint,
    measure_fixture_matrix,
)
from soma.cf1_fixture_matrix import CF1_FIXTURE_MATRIX, fixture_matrix_by_name


def test_representative_fixture_payload_preserves_public_distinctions_and_full_evidence() -> None:
    fixture = fixture_matrix_by_name()["ambiguous_side_effect"]

    payload = build_representative_fixture_payload(fixture, detail_bytes=128)

    assert payload.fixture_identity_sha256 == fixture.identity_sha256
    assert payload.server_projection == payload.authoritative_record
    assert payload.mcp_structured_content == payload.server_projection
    assert payload.mcp_text_content.encode("utf-8")
    assert payload.authoritative_record["outcome"] == "ambiguous_side_effect"
    assert payload.authoritative_record["reconciliation_required"] is True
    assert set(payload.authoritative_record["evidence"]) == set(fixture.evidence_kinds)
    assert payload.authoritative_record["input_json"]["reviewed_script"]
    assert payload.connector_envelope["structuredContent"] == payload.server_projection
    assert payload.connector_envelope["content"][0]["text"] == payload.mcp_text_content


def test_fixture_footprint_measurement_is_versioned_hash_bound_and_counts_duplicates() -> None:
    fixture = fixture_matrix_by_name()["successful_run"]

    first = measure_fixture_footprint(fixture, detail_bytes=256, iterations=3)
    second = measure_fixture_footprint(fixture, detail_bytes=256, iterations=3)

    assert first.version == CF1_FIXTURE_FOOTPRINT_VERSION
    assert first.fixture_identity_sha256 == fixture.identity_sha256
    assert first.authoritative_sha256 == second.authoritative_sha256
    assert first.authoritative_bytes == second.authoritative_bytes
    assert first.footprint.authoritative_sha256 == first.authoritative_sha256
    assert first.footprint.duplicated_representation_bytes == (
        first.footprint.server_projection_bytes * 2
    )
    assert first.footprint.conversation_visible_bytes > first.footprint.server_projection_bytes
    assert first.construction_p50_ms >= 0
    assert first.construction_p95_ms >= first.construction_p50_ms
    assert first.peak_python_alloc_bytes > 0
    assert first.json_decode_calls == 3


def test_fixture_matrix_measurement_covers_every_authoritative_fixture_once() -> None:
    measurements = measure_fixture_matrix(detail_bytes=32, iterations=1)

    assert len(measurements) == len(CF1_FIXTURE_MATRIX)
    assert [measurement.fixture_name for measurement in measurements] == [
        fixture.name for fixture in CF1_FIXTURE_MATRIX
    ]
    assert len({measurement.fixture_identity_sha256 for measurement in measurements}) == len(
        CF1_FIXTURE_MATRIX
    )
    assert all(measurement.json_decode_calls == 1 for measurement in measurements)


def test_fixture_measurement_rejects_invalid_bounds() -> None:
    fixture = CF1_FIXTURE_MATRIX[0]

    with pytest.raises(ValueError, match="detail_bytes must be non-negative"):
        build_representative_fixture_payload(fixture, detail_bytes=-1)
    with pytest.raises(ValueError, match="iterations must be positive"):
        measure_fixture_footprint(fixture, iterations=0)


def test_fixture_identity_changes_when_contract_changes() -> None:
    fixture = CF1_FIXTURE_MATRIX[0]
    changed = replace(fixture, outcome="validation_failure")

    original = build_representative_fixture_payload(fixture, detail_bytes=16)
    modified = build_representative_fixture_payload(changed, detail_bytes=16)

    assert original.fixture_identity_sha256 != modified.fixture_identity_sha256
    assert original.authoritative_record != modified.authoritative_record
