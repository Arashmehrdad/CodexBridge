from __future__ import annotations

from datetime import datetime, timezone

import pytest

from soma.trading.broker_time import (
    BrokerOffsetDetection,
    OffsetSample,
    broker_h4_open_epoch,
    detect_broker_utc_offset,
    normalize_h4_open,
)

UTC = timezone.utc
NOW = datetime(2026, 7, 23, 9, 30, tzinfo=UTC)
BROKER_OFFSET = 3 * 60 * 60  # detected, never assumed


def sample(latency_seconds: float, offset: int = BROKER_OFFSET) -> OffsetSample:
    """A fresh tick observed ``latency_seconds`` after the broker stamped it."""
    host = NOW
    raw = int(host.timestamp()) + offset - int(latency_seconds)
    return OffsetSample(raw_epoch_seconds=raw, host_utc=host)


def test_detects_quarter_hour_offset_from_noisy_fresh_ticks() -> None:
    detection = detect_broker_utc_offset(
        [sample(1), sample(4), sample(9), sample(2), sample(30)],
        detected_at_utc=NOW,
    )
    assert isinstance(detection, BrokerOffsetDetection)
    assert detection.offset_seconds == BROKER_OFFSET
    assert detection.sample_count == 5
    assert detection.max_deviation_seconds == pytest.approx(29.0)


def test_detects_non_three_hour_offsets_rather_than_assuming_plus_three() -> None:
    # +05:30 broker: the detector must not hard-code +03:00.
    offset = 5 * 3600 + 30 * 60
    detection = detect_broker_utc_offset(
        [sample(2, offset), sample(5, offset), sample(8, offset)],
        detected_at_utc=NOW,
    )
    assert detection.offset_seconds == offset


def test_requires_minimum_samples_and_stable_deltas() -> None:
    with pytest.raises(ValueError, match="at least 3 fresh tick samples"):
        detect_broker_utc_offset([sample(1), sample(2)], detected_at_utc=NOW)
    with pytest.raises(ValueError, match="refusing to detect"):
        detect_broker_utc_offset(
            [sample(1), sample(2), sample(1000)], detected_at_utc=NOW
        )


def test_rejects_naive_timestamps() -> None:
    naive = OffsetSample(
        raw_epoch_seconds=int(NOW.timestamp()),
        host_utc=NOW.replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        detect_broker_utc_offset(
            [naive, sample(1), sample(2)], detected_at_utc=NOW
        )


def test_h4_boundary_is_computed_in_broker_time_then_normalized() -> None:
    # Broker epoch 08:00 broker-time boundary with a +03:00 offset is
    # 05:00 UTC — the boundary is taken on the raw epoch first.
    raw_boundary = 1_784_534_400  # divisible by 14400
    assert raw_boundary % 14_400 == 0
    inside = raw_boundary + 3_723
    assert broker_h4_open_epoch(inside) == raw_boundary
    normalized = normalize_h4_open(raw_boundary, BROKER_OFFSET)
    assert normalized == datetime.fromtimestamp(
        raw_boundary - BROKER_OFFSET, tz=UTC
    )
    with pytest.raises(ValueError, match="not a broker H4 boundary"):
        normalize_h4_open(raw_boundary + 60, BROKER_OFFSET)
