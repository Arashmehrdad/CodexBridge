from __future__ import annotations

import gzip
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from soma.trading.mt5_provider import HistoricalTick
from soma.trading.tick_archive import TickArchive

from tests.trading_lab_fixtures import OFFSET, SYMBOL, provider_timestamp

UTC = timezone.utc
DAY = date(2026, 7, 22)
DAY_START = datetime(2026, 7, 22, tzinfo=UTC)


def historical_tick(at: datetime, bid: float, ask: float) -> HistoricalTick:
    return HistoricalTick(
        symbol=SYMBOL,
        bid=bid,
        ask=ask,
        last=0.0,
        volume=1.0,
        flags=6,
        timestamp=provider_timestamp(int(at.timestamp()) + OFFSET),
    )


@pytest.fixture()
def archive(tmp_path: Path) -> TickArchive:
    return TickArchive(tmp_path / "ticks.sqlite3", tmp_path / "archives")


def seed(archive: TickArchive, count: int = 10) -> list[HistoricalTick]:
    ticks = [
        historical_tick(
            DAY_START + timedelta(hours=10, seconds=index),
            64_000.0 + index,
            64_064.0 + index,
        )
        for index in range(count)
    ]
    assert archive.ingest(ticks, source="recovery") == count
    return ticks


def test_ingest_is_idempotent_and_reads_are_chronological(
    archive: TickArchive,
) -> None:
    ticks = seed(archive)
    assert archive.ingest(ticks, source="recovery") == 0
    stored = archive.ticks_between(
        SYMBOL, DAY_START, DAY_START + timedelta(days=1)
    )
    assert [tick.bid for tick in stored] == [64_000.0 + i for i in range(10)]
    # Raw broker epoch, offset, and normalized UTC are all retained.
    assert stored[0].raw_epoch_seconds == int(
        (DAY_START + timedelta(hours=10)).timestamp()
    ) + OFFSET
    assert stored[0].broker_utc_offset_seconds == OFFSET
    window = archive.ticks_between(
        SYMBOL,
        DAY_START + timedelta(hours=10, seconds=3),
        DAY_START + timedelta(hours=10, seconds=6),
    )
    assert [tick.bid for tick in window] == [64_003.0, 64_004.0, 64_005.0]


def test_range_hash_is_deterministic_and_content_sensitive(
    archive: TickArchive,
) -> None:
    seed(archive)
    first_hash, count = archive.range_hash(
        SYMBOL, DAY_START, DAY_START + timedelta(days=1)
    )
    again, _ = archive.range_hash(
        SYMBOL, DAY_START, DAY_START + timedelta(days=1)
    )
    assert count == 10
    assert first_hash == again
    archive.ingest(
        [historical_tick(DAY_START + timedelta(hours=11), 65_000.0, 65_064.0)],
        source="live",
    )
    changed, changed_count = archive.range_hash(
        SYMBOL, DAY_START, DAY_START + timedelta(days=1)
    )
    assert changed_count == 11
    assert changed != first_hash


def test_gap_detection_covers_interior_and_window_edges(
    archive: TickArchive,
) -> None:
    archive.ingest(
        [
            historical_tick(DAY_START + timedelta(hours=10), 64_000.0, 64_064.0),
            historical_tick(
                DAY_START + timedelta(hours=10, minutes=1), 64_001.0, 64_065.0
            ),
            historical_tick(DAY_START + timedelta(hours=12), 64_002.0, 64_066.0),
        ],
        source="recovery",
    )
    gaps = archive.detect_gaps(
        SYMBOL,
        DAY_START + timedelta(hours=9),
        DAY_START + timedelta(hours=13),
        max_gap_seconds=300,
    )
    assert len(gaps) == 3
    assert gaps[0].start_utc == DAY_START + timedelta(hours=9)
    assert gaps[1].gap_seconds == pytest.approx(119 * 60)
    assert gaps[2].end_utc == DAY_START + timedelta(hours=13)


def test_daily_archive_is_compressed_verified_and_append_only(
    archive: TickArchive, tmp_path: Path
) -> None:
    seed(archive)
    record = archive.archive_day(SYMBOL, DAY)
    assert record.tick_count == 10
    target = tmp_path / "archives" / record.relative_path
    assert target.exists()
    assert archive.read_archive(record)[0]["bid"] == 64_000.0

    # Same content is a no-op.
    assert archive.archive_day(SYMBOL, DAY).id == record.id

    # Late-recovered ticks produce a new versioned record, not a rewrite.
    archive.ingest(
        [historical_tick(DAY_START + timedelta(hours=20), 66_000.0, 66_064.0)],
        source="recovery",
    )
    second = archive.archive_day(SYMBOL, DAY)
    assert second.id != record.id
    assert second.relative_path.endswith(".v2.jsonl.gz")
    assert target.exists()
    assert len(archive.day_archives(SYMBOL, DAY)) == 2

    # Corruption of the archive file is detected on read.
    with gzip.open(target, "wt", encoding="utf-8") as handle:
        handle.write('{"bid": 1}\n')
    with pytest.raises(RuntimeError, match="corrupt"):
        archive.read_archive(record)


def test_archive_day_requires_ticks(archive: TickArchive) -> None:
    with pytest.raises(ValueError, match="no retained ticks"):
        archive.archive_day(SYMBOL, DAY)
