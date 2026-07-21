from __future__ import annotations

import json
import math
import statistics
import tracemalloc
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter_ns
from typing import Any, Callable, Final

from codexbridge.cf1_fixture_matrix import CF1_FIXTURE_MATRIX, CF1FixtureSpec
from codexbridge.public_footprint_measurement import (
    PublicFootprintMeasurement,
    measure_public_footprint,
)

CF1_FIXTURE_FOOTPRINT_VERSION: Final[str] = "cf1.0.fixture-footprint.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


@dataclass(frozen=True)
class RepresentativeFixturePayload:
    fixture_name: str
    fixture_identity_sha256: str
    request_arguments: dict[str, Any]
    authoritative_record: dict[str, Any]
    server_projection: dict[str, Any]
    mcp_structured_content: dict[str, Any]
    mcp_text_content: str
    connector_envelope: dict[str, Any]


@dataclass(frozen=True)
class FixtureFootprintMeasurement:
    version: str
    fixture_name: str
    fixture_identity_sha256: str
    authoritative_bytes: int
    authoritative_sha256: str
    footprint: PublicFootprintMeasurement
    construction_p50_ms: float
    construction_p95_ms: float
    peak_python_alloc_bytes: int
    json_decode_calls: int


def build_representative_fixture_payload(
    fixture: CF1FixtureSpec,
    *,
    detail_bytes: int = 4096,
) -> RepresentativeFixturePayload:
    if detail_bytes < 0:
        raise ValueError("detail_bytes must be non-negative")

    detail = (fixture.name + ":") + ("x" * detail_bytes)
    values = {
        "lifecycle_status": fixture.lifecycle_status,
        "outcome": fixture.outcome,
        "current_phase": (
            "result" if fixture.lifecycle_status != "running" else "worker"
        ),
        "action_required": (
            "chatgpt_input" if fixture.outcome == "needs_input" else "none"
        ),
        "validation_state": (
            "passed" if fixture.outcome == "success" else "not_applicable"
        ),
        "cancellation_state": (
            "verified" if fixture.lifecycle_status == "cancelled" else "none"
        ),
        "cleanup_state": "complete",
        "reconciliation_required": fixture.outcome == "ambiguous_side_effect",
        "safety_failure": False,
        "state_version": 7,
    }
    public_state = {field: values[field] for field in fixture.required_public_fields}
    evidence = {
        kind: {
            "artifact_id": f"{fixture.name}-{kind}",
            "sha256": sha256(
                f"{fixture.name}:{kind}:{detail}".encode("utf-8")
            ).hexdigest(),
            "size_bytes": len(detail.encode("utf-8")),
            "detail": detail,
        }
        for kind in fixture.evidence_kinds
    }
    authoritative_record = {
        "fixture_matrix_version": "cf1.0.fixture-matrix.v1",
        "fixture_identity_sha256": fixture.identity_sha256,
        "fixture_name": fixture.name,
        "fixture_class": fixture.fixture_class.value,
        "tool": fixture.tool,
        "request": {
            "operation": fixture.name,
            "tool": fixture.tool,
            "arguments": {
                "objective": detail,
                "environment": {"CF1_FIXTURE": fixture.name},
                "stdin": detail,
            },
        },
        **public_state,
        "input_json": {
            "argv": ["fixture", fixture.name, detail],
            "environment": {"CF1_FIXTURE": fixture.name},
            "reviewed_script": detail,
        },
        "progress_json": {
            "phase": public_state["current_phase"],
            "heartbeat_at": "2026-07-21T02:00:00+00:00",
            "detail": detail,
        },
        "result_json": {
            "classification": fixture.outcome,
            "summary": f"Representative {fixture.name} result",
            "detail": detail,
            "evidence": evidence,
        },
        "evidence": evidence,
        "run_dir": f"D:/Github/CodexBridge/runs/{fixture.name}",
        "worker_lease_token": f"lease-{fixture.identity_sha256}",
    }
    server_projection = json.loads(_canonical_bytes(authoritative_record))
    text = _canonical_bytes(server_projection).decode("utf-8")
    connector_envelope = {
        "structuredContent": server_projection,
        "content": [{"type": "text", "text": text}],
        "metadata": {
            "fixture_name": fixture.name,
            "fixture_identity_sha256": fixture.identity_sha256,
        },
    }
    return RepresentativeFixturePayload(
        fixture_name=fixture.name,
        fixture_identity_sha256=fixture.identity_sha256,
        request_arguments={
            "operation": fixture.name,
            "tool": fixture.tool,
            "fixture_identity_sha256": fixture.identity_sha256,
        },
        authoritative_record=authoritative_record,
        server_projection=server_projection,
        mcp_structured_content=server_projection,
        mcp_text_content=text,
        connector_envelope=connector_envelope,
    )


def measure_fixture_footprint(
    fixture: CF1FixtureSpec,
    *,
    detail_bytes: int = 4096,
    iterations: int = 5,
    json_loader: Callable[[str], Any] = json.loads,
) -> FixtureFootprintMeasurement:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    durations_ms: list[float] = []
    peak_allocations: list[int] = []
    payload: RepresentativeFixturePayload | None = None
    json_decode_calls = 0

    for _ in range(iterations):
        tracemalloc.start()
        started = perf_counter_ns()
        try:
            candidate = build_representative_fixture_payload(
                fixture, detail_bytes=detail_bytes
            )
            decoded = json_loader(candidate.mcp_text_content)
            json_decode_calls += 1
            if decoded != candidate.server_projection:
                raise ValueError(
                    f"Fixture {fixture.name!r} text representation does not reconstruct"
                )
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        durations_ms.append(elapsed_ms)
        peak_allocations.append(int(peak))
        if payload is None:
            payload = candidate

    assert payload is not None
    footprint = measure_public_footprint(
        request_arguments=payload.request_arguments,
        server_projection=payload.server_projection,
        mcp_structured_content=payload.mcp_structured_content,
        mcp_text_content=payload.mcp_text_content,
        connector_envelope=payload.connector_envelope,
        authoritative_record=payload.authoritative_record,
    )
    authoritative_payload = _canonical_bytes(payload.authoritative_record)
    return FixtureFootprintMeasurement(
        version=CF1_FIXTURE_FOOTPRINT_VERSION,
        fixture_name=fixture.name,
        fixture_identity_sha256=fixture.identity_sha256,
        authoritative_bytes=len(authoritative_payload),
        authoritative_sha256=sha256(authoritative_payload).hexdigest(),
        footprint=footprint,
        construction_p50_ms=statistics.median(durations_ms),
        construction_p95_ms=_percentile_nearest_rank(durations_ms, 0.95),
        peak_python_alloc_bytes=max(peak_allocations),
        json_decode_calls=json_decode_calls,
    )


def measure_fixture_matrix(
    *,
    detail_bytes: int = 4096,
    iterations: int = 5,
) -> tuple[FixtureFootprintMeasurement, ...]:
    return tuple(
        measure_fixture_footprint(
            fixture, detail_bytes=detail_bytes, iterations=iterations
        )
        for fixture in CF1_FIXTURE_MATRIX
    )
