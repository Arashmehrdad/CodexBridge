"""Durable tick retention with compressed daily archives.

Ticks ingested from the connected demo terminal (live monitoring or
historical recovery fetches) are retained in an append-only SQLite table
and exported as compressed daily archive files. The retained evidence is
what outcome resolution and offline replay consume: every resolved
outcome can point at the exact tick range, its content hash, and any
detected gaps.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence

UTC = timezone.utc
DEFAULT_MAX_GAP_SECONDS = 300.0


@dataclass(frozen=True)
class ArchivedTick:
    symbol: str
    raw_epoch_seconds: int
    broker_utc_offset_seconds: int
    normalized_utc: datetime
    bid: float
    ask: float
    last: float
    volume: float
    flags: int
    source: str


@dataclass(frozen=True)
class TickGap:
    start_utc: datetime
    end_utc: datetime
    gap_seconds: float


@dataclass(frozen=True)
class DailyArchiveRecord:
    id: int
    symbol: str
    day: date
    tick_count: int
    content_sha256: str
    relative_path: str
    created_at_utc: datetime


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _tick_line(tick: ArchivedTick) -> str:
    return json.dumps(
        {
            "raw_epoch_seconds": tick.raw_epoch_seconds,
            "broker_utc_offset_seconds": tick.broker_utc_offset_seconds,
            "normalized_utc": tick.normalized_utc.isoformat(),
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "flags": tick.flags,
            "source": tick.source,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


class TickArchive:
    """Append-only tick retention plus compressed daily archive files."""

    def __init__(self, db_path: Path, archive_dir: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir = Path(archive_dir).resolve()
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_ticks (
                    symbol TEXT NOT NULL,
                    raw_epoch_seconds INTEGER NOT NULL,
                    broker_utc_offset_seconds INTEGER NOT NULL,
                    normalized_utc TEXT NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    last REAL NOT NULL DEFAULT 0,
                    volume REAL NOT NULL DEFAULT 0,
                    flags INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL,
                    PRIMARY KEY (symbol, raw_epoch_seconds, bid, ask)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_ticks_normalized"
                " ON trading_ticks(symbol, normalized_utc)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_tick_archive_days (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    day TEXT NOT NULL,
                    tick_count INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
                """
            )

    # -- ingestion ----------------------------------------------------------

    def ingest(self, ticks: Iterable[Any], *, source: str) -> int:
        """Idempotently retain ticks; returns the newly inserted count.

        Accepts provider ``Tick``/``HistoricalTick`` objects (anything
        exposing ``bid``, ``ask``, ``timestamp`` with raw epoch, offset,
        and normalized UTC).
        """
        normalized_source = str(source).strip()
        if not normalized_source:
            raise ValueError("source must not be empty")
        inserted = 0
        with self.connect() as conn:
            for tick in ticks:
                timestamp = tick.timestamp
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO trading_ticks (
                        symbol, raw_epoch_seconds, broker_utc_offset_seconds,
                        normalized_utc, bid, ask, last, volume, flags, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(tick.symbol),
                        int(timestamp.raw_epoch_seconds),
                        int(timestamp.provider_utc_offset_seconds),
                        _aware(
                            timestamp.normalized_utc, "normalized_utc"
                        ).isoformat(),
                        float(tick.bid),
                        float(tick.ask),
                        float(getattr(tick, "last", 0.0)),
                        float(getattr(tick, "volume", 0.0)),
                        int(getattr(tick, "flags", 0)),
                        normalized_source,
                    ),
                )
                inserted += cursor.rowcount
            conn.commit()
        return inserted

    # -- reads --------------------------------------------------------------

    def ticks_between(
        self,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[ArchivedTick]:
        """Chronological retained ticks with ``start <= normalized < end``."""
        start = _aware(start_utc, "start_utc")
        end = _aware(end_utc, "end_utc")
        if end <= start:
            raise ValueError("end_utc must be after start_utc")
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_ticks WHERE symbol = ?"
                " AND normalized_utc >= ? AND normalized_utc < ?"
                " ORDER BY normalized_utc, raw_epoch_seconds, bid, ask",
                (str(symbol), start.isoformat(), end.isoformat()),
            ).fetchall()
        return [self._row_to_tick(row) for row in rows]

    def range_hash(
        self, symbol: str, start_utc: datetime, end_utc: datetime
    ) -> tuple[str, int]:
        """Content hash and count of the retained tick range."""
        ticks = self.ticks_between(symbol, start_utc, end_utc)
        digest = sha256()
        for tick in ticks:
            digest.update(_tick_line(tick).encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest(), len(ticks)

    def detect_gaps(
        self,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS,
    ) -> list[TickGap]:
        """Coverage gaps exceeding ``max_gap_seconds`` inside the window.

        Missing coverage at the window edges counts as a gap too.
        """
        if max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be positive")
        start = _aware(start_utc, "start_utc")
        end = _aware(end_utc, "end_utc")
        ticks = self.ticks_between(symbol, start, end)
        gaps: list[TickGap] = []
        cursor = start
        for tick in ticks:
            delta = (tick.normalized_utc - cursor).total_seconds()
            if delta > max_gap_seconds:
                gaps.append(TickGap(cursor, tick.normalized_utc, delta))
            cursor = tick.normalized_utc
        tail = (end - cursor).total_seconds()
        if tail > max_gap_seconds:
            gaps.append(TickGap(cursor, end, tail))
        return gaps

    # -- daily archives ------------------------------------------------------

    def archive_day(self, symbol: str, day: date) -> DailyArchiveRecord:
        """Export one normalized-UTC day to a compressed archive file.

        Re-archiving the same content is a no-op; new content for the same
        day (late recovery fetches) appends a new versioned archive record
        instead of rewriting the previous evidence.
        """
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        ticks = self.ticks_between(symbol, day_start, day_start + timedelta(days=1))
        if not ticks:
            raise ValueError(f"no retained ticks for {symbol} on {day.isoformat()}")
        body = "\n".join(_tick_line(tick) for tick in ticks) + "\n"
        content_hash = sha256(body.encode("utf-8")).hexdigest()

        existing = self.day_archives(symbol, day)
        for record in existing:
            if record.content_sha256 == content_hash:
                return record
        version = len(existing) + 1
        suffix = "" if version == 1 else f".v{version}"
        relative_path = f"{symbol}/{day.isoformat()}{suffix}.jsonl.gz"
        target = self.archive_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(target, "wt", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        created = datetime.now(UTC)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trading_tick_archive_days (
                    symbol, day, tick_count, content_sha256, relative_path,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(symbol),
                    day.isoformat(),
                    len(ticks),
                    content_hash,
                    relative_path,
                    created.isoformat(),
                ),
            )
            record_id = int(cursor.lastrowid)
            conn.commit()
        return DailyArchiveRecord(
            id=record_id,
            symbol=str(symbol),
            day=day,
            tick_count=len(ticks),
            content_sha256=content_hash,
            relative_path=relative_path,
            created_at_utc=created,
        )

    def day_archives(self, symbol: str, day: date) -> list[DailyArchiveRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_tick_archive_days"
                " WHERE symbol = ? AND day = ? ORDER BY id",
                (str(symbol), day.isoformat()),
            ).fetchall()
        return [
            DailyArchiveRecord(
                id=int(row["id"]),
                symbol=str(row["symbol"]),
                day=date.fromisoformat(str(row["day"])),
                tick_count=int(row["tick_count"]),
                content_sha256=str(row["content_sha256"]),
                relative_path=str(row["relative_path"]),
                created_at_utc=_parse_utc(str(row["created_at_utc"])),
            )
            for row in rows
        ]

    def read_archive(self, record: DailyArchiveRecord) -> Sequence[dict[str, Any]]:
        target = self.archive_dir / record.relative_path
        with gzip.open(target, "rt", encoding="utf-8") as handle:
            body = handle.read()
        if sha256(body.encode("utf-8")).hexdigest() != record.content_sha256:
            raise RuntimeError(
                f"daily archive {record.relative_path} failed hash verification;"
                " retained evidence is corrupt"
            )
        return [json.loads(line) for line in body.splitlines() if line]

    @staticmethod
    def _row_to_tick(row: sqlite3.Row) -> ArchivedTick:
        return ArchivedTick(
            symbol=str(row["symbol"]),
            raw_epoch_seconds=int(row["raw_epoch_seconds"]),
            broker_utc_offset_seconds=int(row["broker_utc_offset_seconds"]),
            normalized_utc=_parse_utc(str(row["normalized_utc"])),
            bid=float(row["bid"]),
            ask=float(row["ask"]),
            last=float(row["last"]),
            volume=float(row["volume"]),
            flags=int(row["flags"]),
            source=str(row["source"]),
        )
