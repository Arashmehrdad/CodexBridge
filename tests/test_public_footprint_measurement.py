from __future__ import annotations

import json
from hashlib import sha256

from soma.public_footprint_measurement import (
    PUBLIC_FOOTPRINT_MEASUREMENT_VERSION,
    measure_public_footprint,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def test_measurement_records_every_cf1_transport_layer_and_duplicate_copy() -> None:
    request = {"operation": "list", "repo_name": "Soma", "limit": 20}
    projection = [{"run_id": "run-1", "status": "completed", "summary": "done"}]
    projection_text = _canonical_bytes(projection).decode("utf-8")
    connector = {
        "structuredContent": projection,
        "content": [{"type": "text", "text": projection_text}],
    }
    authoritative = {"runs": projection, "input_json": {"token": "secret"}}

    result = measure_public_footprint(
        request_arguments=request,
        server_projection=projection,
        mcp_structured_content=projection,
        mcp_text_content=projection_text,
        connector_envelope=connector,
        authoritative_record=authoritative,
    )

    projection_bytes = len(_canonical_bytes(projection))
    assert result.version == PUBLIC_FOOTPRINT_MEASUREMENT_VERSION
    assert result.request_bytes == len(_canonical_bytes(request))
    assert result.server_projection_bytes == projection_bytes
    assert result.mcp_structured_content_bytes == projection_bytes
    assert result.mcp_text_content_bytes == projection_bytes
    assert result.duplicated_representation_bytes == projection_bytes * 2
    assert result.conversation_visible_bytes == len(_canonical_bytes(connector))
    assert result.transport_overhead_bytes == result.conversation_visible_bytes - projection_bytes
    assert result.authoritative_sha256 == sha256(_canonical_bytes(authoritative)).hexdigest()


def test_measurement_uses_serialized_utf8_bytes_not_character_count() -> None:
    projection = {"summary": "😀"}
    connector = {"structuredContent": projection, "content": []}

    result = measure_public_footprint(
        request_arguments={},
        server_projection=projection,
        mcp_structured_content=projection,
        mcp_text_content="",
        connector_envelope=connector,
        authoritative_record=projection,
    )

    assert result.server_projection_bytes == len(_canonical_bytes(projection))
    assert result.server_projection_bytes > len(json.dumps(projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def test_approximately_837_kb_twenty_run_fixture_is_measured_without_loss() -> None:
    detail = "x" * 20_850
    runs = [
        {
            "run_id": f"run-{index:02d}",
            "status": "completed",
            "input": {"detail": detail},
            "result": {"detail": detail},
        }
        for index in range(20)
    ]
    projection_text = _canonical_bytes(runs).decode("utf-8")
    connector = {
        "structuredContent": runs,
        "content": [{"type": "text", "text": projection_text}],
    }

    result = measure_public_footprint(
        request_arguments={"operation": "list", "limit": 20},
        server_projection=runs,
        mcp_structured_content=runs,
        mcp_text_content=projection_text,
        connector_envelope=connector,
        authoritative_record=runs,
    )

    assert 830_000 <= result.server_projection_bytes <= 845_000
    assert result.duplicated_representation_bytes == result.server_projection_bytes * 2
    assert result.authoritative_sha256 == sha256(_canonical_bytes(runs)).hexdigest()

