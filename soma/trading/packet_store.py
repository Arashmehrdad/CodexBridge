"""Durable immutable market-packet store.

Every hourly analysis packet is persisted exactly once, keyed by its
content hash. Signal submission later references a stored packet and
derives symbol, bid, ask, timestamps, parent H4 candle identity, and the
packet hash from the stored evidence instead of trusting caller-supplied
copies. Stored packets are never updated; hash verification on read
detects any corruption of retained evidence.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from .broker_time import broker_h4_open_epoch, normalize_h4_open
from .market_packet import MarketPacket, canonical_packet_bytes
from .versions import PACKET_SCHEMA_VERSION

UTC = timezone.utc


@dataclass(frozen=True)
class StoredMarketPacket:
    packet_id: str
    content_hash: str
    schema_version: str
    symbol: str
    server: str
    account_environment: str
    created_at_utc: datetime
    bid: float
    ask: float
    tick_raw_epoch_seconds: int
    broker_utc_offset_seconds: int
    tick_normalized_utc: datetime
    parent_h4_raw_open_epoch: int
    parent_h4_open_utc: datetime
    payload: dict[str, Any]
    inserted_at_utc: datetime


@dataclass(frozen=True)
class BrokerOffsetEvent:
    id: int
    symbol: str
    offset_seconds: int
    previous_offset_seconds: int | None
    sample_count: int
    max_deviation_seconds: float
    detected_at_utc: datetime


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MarketPacketStore:
    """Append-only SQLite store for immutable market packets."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS trading_market_packets (
                    packet_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    schema_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    server TEXT NOT NULL,
                    account_environment TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    tick_raw_epoch_seconds INTEGER NOT NULL,
                    broker_utc_offset_seconds INTEGER NOT NULL,
                    tick_normalized_utc TEXT NOT NULL,
                    parent_h4_raw_open_epoch INTEGER NOT NULL,
                    parent_h4_open_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    inserted_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_market_packets_symbol_created"
                " ON trading_market_packets(symbol, created_at_utc)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_broker_offset_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    offset_seconds INTEGER NOT NULL,
                    previous_offset_seconds INTEGER,
                    sample_count INTEGER NOT NULL,
                    max_deviation_seconds REAL NOT NULL,
                    detected_at_utc TEXT NOT NULL
                )
                """
            )

    # -- packets ------------------------------------------------------------

    def store(
        self,
        packet: MarketPacket,
        *,
        inserted_at_utc: datetime | None = None,
    ) -> StoredMarketPacket:
        """Persist one immutable packet; storing the same packet is a no-op.

        The broker offset, raw tick epoch, and normalized UTC come from the
        packet's own retained ``ProviderTimestamp`` evidence. The parent H4
        candle identity is the packet's developing candle, and its boundary
        is validated in broker time before normalization.
        """
        payload = packet.payload
        payload_bytes = canonical_packet_bytes(payload)
        recomputed = sha256(payload_bytes).hexdigest()
        if recomputed != packet.content_hash:
            raise ValueError("packet content hash does not match its payload")

        tick = payload.latest_tick
        developing = payload.developing_4h_candle
        offset = int(tick.timestamp.provider_utc_offset_seconds)
        parent_raw_open = int(developing.open_time.raw_epoch_seconds)
        if parent_raw_open != broker_h4_open_epoch(parent_raw_open):
            raise ValueError(
                "developing H4 candle open is not on a broker-time H4 boundary"
            )
        parent_open_utc = normalize_h4_open(parent_raw_open, offset)
        inserted = _aware(inserted_at_utc or datetime.now(UTC), "inserted_at_utc")

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM trading_market_packets WHERE packet_id = ?",
                (packet.packet_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["content_hash"]) != packet.content_hash:
                    conn.rollback()
                    raise ValueError(
                        "packet_id already stored with different content"
                    )
                conn.commit()
                return self._row_to_packet(existing)
            conn.execute(
                """
                INSERT INTO trading_market_packets (
                    packet_id, content_hash, schema_version, symbol, server,
                    account_environment, created_at_utc, bid, ask,
                    tick_raw_epoch_seconds, broker_utc_offset_seconds,
                    tick_normalized_utc, parent_h4_raw_open_epoch,
                    parent_h4_open_utc, payload_json, inserted_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    packet.packet_id,
                    packet.content_hash,
                    PACKET_SCHEMA_VERSION,
                    payload.symbol,
                    payload.server,
                    payload.account_environment,
                    _aware(payload.created_at_utc, "created_at_utc").isoformat(),
                    float(tick.bid),
                    float(tick.ask),
                    int(tick.timestamp.raw_epoch_seconds),
                    offset,
                    _aware(
                        tick.timestamp.normalized_utc, "tick_normalized_utc"
                    ).isoformat(),
                    parent_raw_open,
                    parent_open_utc.isoformat(),
                    payload_bytes.decode("utf-8"),
                    inserted.isoformat(),
                ),
            )
            conn.commit()
        return self.get(packet.packet_id)

    def get(self, packet_id: str) -> StoredMarketPacket:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_market_packets WHERE packet_id = ?",
                (str(packet_id).strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Market packet not found: {packet_id}")
        return self._row_to_packet(row)

    def list_packets(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[StoredMarketPacket]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must not be negative")
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_market_packets"
                " ORDER BY created_at_utc DESC, packet_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_packet(row) for row in rows]

    def count_packets(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM trading_market_packets"
            ).fetchone()
        return int(row["n"])

    # -- broker offset events ----------------------------------------------

    def record_offset_event(
        self,
        *,
        symbol: str,
        offset_seconds: int,
        sample_count: int,
        max_deviation_seconds: float,
        detected_at_utc: datetime,
    ) -> BrokerOffsetEvent:
        """Append one detected-offset event without touching stored packets.

        Offset changes are recorded as new events; historical packets and
        their retained raw/normalized timestamps are never reinterpreted.
        """
        normalized_symbol = str(symbol).strip()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        previous = self.latest_offset(normalized_symbol)
        detected = _aware(detected_at_utc, "detected_at_utc")
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trading_broker_offset_events (
                    symbol, offset_seconds, previous_offset_seconds,
                    sample_count, max_deviation_seconds, detected_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_symbol,
                    int(offset_seconds),
                    previous.offset_seconds if previous is not None else None,
                    int(sample_count),
                    float(max_deviation_seconds),
                    detected.isoformat(),
                ),
            )
            event_id = int(cursor.lastrowid)
            conn.commit()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_broker_offset_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_offset_event(row)

    def latest_offset(self, symbol: str) -> BrokerOffsetEvent | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_broker_offset_events WHERE symbol = ?"
                " ORDER BY id DESC LIMIT 1",
                (str(symbol).strip(),),
            ).fetchone()
        return self._row_to_offset_event(row) if row is not None else None

    def offset_events(self, symbol: str) -> list[BrokerOffsetEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_broker_offset_events WHERE symbol = ?"
                " ORDER BY id",
                (str(symbol).strip(),),
            ).fetchall()
        return [self._row_to_offset_event(row) for row in rows]

    # -- row mapping --------------------------------------------------------

    @staticmethod
    def _row_to_offset_event(row: sqlite3.Row) -> BrokerOffsetEvent:
        return BrokerOffsetEvent(
            id=int(row["id"]),
            symbol=str(row["symbol"]),
            offset_seconds=int(row["offset_seconds"]),
            previous_offset_seconds=(
                int(row["previous_offset_seconds"])
                if row["previous_offset_seconds"] is not None
                else None
            ),
            sample_count=int(row["sample_count"]),
            max_deviation_seconds=float(row["max_deviation_seconds"]),
            detected_at_utc=_parse_utc(str(row["detected_at_utc"])),
        )

    @staticmethod
    def _row_to_packet(row: sqlite3.Row) -> StoredMarketPacket:
        payload_json = str(row["payload_json"])
        recomputed = sha256(payload_json.encode("utf-8")).hexdigest()
        if recomputed != str(row["content_hash"]):
            raise RuntimeError(
                f"stored packet {row['packet_id']} failed hash verification;"
                " retained evidence is corrupt"
            )
        return StoredMarketPacket(
            packet_id=str(row["packet_id"]),
            content_hash=str(row["content_hash"]),
            schema_version=str(row["schema_version"]),
            symbol=str(row["symbol"]),
            server=str(row["server"]),
            account_environment=str(row["account_environment"]),
            created_at_utc=_parse_utc(str(row["created_at_utc"])),
            bid=float(row["bid"]),
            ask=float(row["ask"]),
            tick_raw_epoch_seconds=int(row["tick_raw_epoch_seconds"]),
            broker_utc_offset_seconds=int(row["broker_utc_offset_seconds"]),
            tick_normalized_utc=_parse_utc(str(row["tick_normalized_utc"])),
            parent_h4_raw_open_epoch=int(row["parent_h4_raw_open_epoch"]),
            parent_h4_open_utc=_parse_utc(str(row["parent_h4_open_utc"])),
            payload=json.loads(payload_json),
            inserted_at_utc=_parse_utc(str(row["inserted_at_utc"])),
        )
