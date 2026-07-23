"""Broker UTC offset detection and H4 boundary normalization.

The broker feed exposes wall-clock epochs in broker time. The offset is
never hard-coded: it is detected from several fresh ticks by comparing
the raw broker epoch against host UTC, then rounded to the nearest
quarter hour because real broker offsets are whole 15-minute multiples.

Raw broker timestamps are always retained beside the detected offset and
the normalized UTC value, and offset changes are recorded as events
without ever reinterpreting historical timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
H4_SECONDS = 4 * 60 * 60
OFFSET_ROUNDING_SECONDS = 15 * 60
MINIMUM_OFFSET_SAMPLES = 3
MAXIMUM_SAMPLE_DEVIATION_SECONDS = 120


@dataclass(frozen=True)
class OffsetSample:
    """One raw broker tick epoch paired with the host UTC observation time."""

    raw_epoch_seconds: int
    host_utc: datetime


@dataclass(frozen=True)
class BrokerOffsetDetection:
    offset_seconds: int
    sample_count: int
    max_deviation_seconds: float
    detected_at_utc: datetime


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def detect_broker_utc_offset(
    samples: list[OffsetSample] | tuple[OffsetSample, ...],
    *,
    detected_at_utc: datetime,
    rounding_seconds: int = OFFSET_ROUNDING_SECONDS,
    minimum_samples: int = MINIMUM_OFFSET_SAMPLES,
    maximum_deviation_seconds: float = MAXIMUM_SAMPLE_DEVIATION_SECONDS,
) -> BrokerOffsetDetection:
    """Detect the broker UTC offset from several fresh tick samples.

    Each sample's delta is ``raw_epoch - host_epoch``. Fresh ticks make
    the delta approximately the broker offset plus network/tick latency;
    rounding the median delta to the nearest 15 minutes removes latency
    noise. Detection fails closed when samples disagree by more than the
    permitted deviation, which indicates stale ticks or a clock problem
    rather than a stable broker offset.
    """
    if rounding_seconds < 1:
        raise ValueError("rounding_seconds must be positive")
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be positive")
    if len(samples) < minimum_samples:
        raise ValueError(
            f"offset detection requires at least {minimum_samples} fresh tick samples;"
            f" received {len(samples)}"
        )
    detected_at = _aware(detected_at_utc, "detected_at_utc")
    deltas = sorted(
        float(int(sample.raw_epoch_seconds))
        - _aware(sample.host_utc, "sample host_utc").timestamp()
        for sample in samples
    )
    max_deviation = deltas[-1] - deltas[0]
    if max_deviation > maximum_deviation_seconds:
        raise ValueError(
            "offset samples deviate by "
            f"{max_deviation:.1f}s (limit {maximum_deviation_seconds:.1f}s); "
            "refusing to detect a broker offset from unstable ticks"
        )
    middle = len(deltas) // 2
    median = (
        deltas[middle]
        if len(deltas) % 2 == 1
        else (deltas[middle - 1] + deltas[middle]) / 2
    )
    offset = int(round(median / rounding_seconds)) * rounding_seconds
    return BrokerOffsetDetection(
        offset_seconds=offset,
        sample_count=len(samples),
        max_deviation_seconds=max_deviation,
        detected_at_utc=detected_at,
    )


def broker_h4_open_epoch(raw_epoch_seconds: int) -> int:
    """The broker-time H4 boundary containing a raw broker epoch.

    H4 boundaries are broker-day aligned, so the boundary is computed on
    the raw broker epoch directly — normalization to UTC happens only
    after broker-time conversion, never before.
    """
    raw = int(raw_epoch_seconds)
    if raw <= 0:
        raise ValueError("raw_epoch_seconds must be positive")
    return raw - (raw % H4_SECONDS)


def normalize_h4_open(raw_open_epoch_seconds: int, offset_seconds: int) -> datetime:
    """Convert one broker-time H4 boundary to UTC using a detected offset."""
    raw = int(raw_open_epoch_seconds)
    if raw % H4_SECONDS != 0:
        raise ValueError("raw_open_epoch_seconds is not a broker H4 boundary")
    return datetime.fromtimestamp(raw - int(offset_seconds), tz=UTC)
