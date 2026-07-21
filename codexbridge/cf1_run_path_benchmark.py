from __future__ import annotations

import json
import math
import statistics
import tracemalloc
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter_ns
from typing import Any, Callable, Final


CF1_RUN_PATH_BENCHMARK_VERSION: Final[str] = "cf1.0.run-path.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True)
class RunPathMeasurement:
    version: str
    name: str
    iterations: int
    serialized_bytes: int
    result_sha256: str
    authoritative_sha256: str
    p50_latency_ms: float
    p95_latency_ms: float
    peak_python_alloc_bytes: int
    json_decode_calls: int


def _percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def measure_run_path(
    *,
    name: str,
    operation: Callable[[], Any],
    authoritative_record: Any,
    iterations: int = 7,
    json_decode_counter: Callable[[], int] | None = None,
    require_deterministic_payload: bool = False,
) -> RunPathMeasurement:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    durations_ms: list[float] = []
    peak_allocations: list[int] = []
    payloads: list[bytes] = []
    decode_calls = 0

    for _ in range(iterations):
        decode_before = json_decode_counter() if json_decode_counter else 0
        tracemalloc.start()
        started = perf_counter_ns()
        try:
            result = operation()
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        decode_after = json_decode_counter() if json_decode_counter else decode_before
        durations_ms.append(elapsed_ms)
        peak_allocations.append(int(peak))
        payloads.append(_canonical_bytes(result))
        decode_calls += max(0, int(decode_after) - int(decode_before))

    first_payload = payloads[0]
    first_hash = sha256(first_payload).hexdigest()
    if require_deterministic_payload and any(
        payload != first_payload for payload in payloads[1:]
    ):
        raise ValueError(f"Run path {name!r} returned a non-deterministic payload")

    return RunPathMeasurement(
        version=CF1_RUN_PATH_BENCHMARK_VERSION,
        name=name,
        iterations=iterations,
        serialized_bytes=len(first_payload),
        result_sha256=first_hash,
        authoritative_sha256=sha256(_canonical_bytes(authoritative_record)).hexdigest(),
        p50_latency_ms=statistics.median(durations_ms),
        p95_latency_ms=_percentile_nearest_rank(durations_ms, 0.95),
        peak_python_alloc_bytes=max(peak_allocations),
        json_decode_calls=decode_calls,
    )
