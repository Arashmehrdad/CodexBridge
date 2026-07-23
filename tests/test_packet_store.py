from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from soma.trading.market_packet import MarketPacket, MarketPacketBuilder
from soma.trading.mt5_provider import (
    Candle,
    ProviderHealth,
    ProviderTimestamp,
    SymbolSpecification,
    Tick,
)
from soma.trading.packet_store import MarketPacketStore
from soma.trading.versions import PACKET_SCHEMA_VERSION

UTC = timezone.utc
SYMBOL = "BITCOIN_i"
OFFSET = 3 * 60 * 60
H4 = 4 * 60 * 60
# Real broker H4 opens are broker-time boundaries: raw epoch % 14400 == 0.
DEVELOPING_RAW_OPEN = 1_784_534_400
DEVELOPING_OPEN_UTC = datetime.fromtimestamp(DEVELOPING_RAW_OPEN - OFFSET, tz=UTC)
NOW = DEVELOPING_OPEN_UTC + timedelta(hours=1)


def provider_timestamp(raw_epoch: int) -> ProviderTimestamp:
    return ProviderTimestamp(
        raw_epoch_seconds=raw_epoch,
        provider_utc_offset_seconds=OFFSET,
        normalized_utc=datetime.fromtimestamp(raw_epoch - OFFSET, tz=UTC),
    )


def candle(raw_open: int, value: float) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe="4H",
        open_time=provider_timestamp(raw_open),
        open=value,
        high=value + 2,
        low=value - 1,
        close=value + 1,
        tick_volume=100,
        spread=64,
        real_volume=0,
    )


class PacketProvider:
    def __init__(self) -> None:
        self.completed = [
            candle(DEVELOPING_RAW_OPEN - H4 * (100 - index), 60_000 + index)
            for index in range(100)
        ]
        self.developing = candle(DEVELOPING_RAW_OPEN, 61_000)
        tick_raw = int(NOW.timestamp()) + OFFSET - 15
        self.tick = Tick(
            symbol=SYMBOL,
            bid=64_000.0,
            ask=64_064.0,
            last=0.0,
            volume=1.0,
            timestamp=provider_timestamp(tick_raw),
            age_seconds=15.0,
            fresh=True,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            initialized=True,
            connected=True,
            account_environment="demo",
            server="Alpari-MT5-Demo",
            login=123,
            currency="USD",
            balance=998.72,
            equity=998.72,
            last_error=(1, "Success"),
        )

    def symbol_specification(self, symbol: str) -> SymbolSpecification:
        return SymbolSpecification(
            symbol=symbol,
            digits=2,
            point=0.01,
            tick_size=0.01,
            tick_value=0.01,
            contract_size=1.0,
            minimum_volume=0.01,
            maximum_volume=300.0,
            volume_step=0.01,
            trade_mode=4,
            order_mode=63,
            margin_initial=0.0,
            margin_maintenance=0.0,
            currency_base="USD",
            currency_profit="USD",
            currency_margin="USD",
        )

    def latest_tick(self, _symbol: str) -> Tick:
        return self.tick

    def h4_candles(self, _symbol: str, *, completed_count: int = 200):
        return self.completed[-completed_count:], self.developing


def build_packet() -> MarketPacket:
    return MarketPacketBuilder(now=lambda: NOW).build(
        PacketProvider(), SYMBOL, completed_count=100
    )


@pytest.fixture()
def store(tmp_path: Path) -> MarketPacketStore:
    return MarketPacketStore(tmp_path / "packets.sqlite3")


def test_store_persists_immutable_packet_with_broker_time_identity(
    store: MarketPacketStore,
) -> None:
    packet = build_packet()
    stored = store.store(packet, inserted_at_utc=NOW)

    assert stored.packet_id == packet.packet_id
    assert stored.content_hash == packet.content_hash
    assert stored.schema_version == PACKET_SCHEMA_VERSION
    assert stored.symbol == SYMBOL
    assert stored.bid == 64_000.0
    assert stored.ask == 64_064.0
    # Raw broker timestamp, detected offset, and normalized UTC are all
    # retained on the stored record.
    assert stored.broker_utc_offset_seconds == OFFSET
    assert stored.tick_raw_epoch_seconds == int(NOW.timestamp()) + OFFSET - 15
    assert stored.tick_normalized_utc == NOW - timedelta(seconds=15)
    # Parent H4 identity: boundary taken in broker time, then normalized.
    assert stored.parent_h4_raw_open_epoch == DEVELOPING_RAW_OPEN
    assert stored.parent_h4_open_utc == DEVELOPING_OPEN_UTC
    assert stored.payload["symbol"] == SYMBOL

    # Idempotent re-store returns identical evidence.
    again = store.store(packet, inserted_at_utc=NOW + timedelta(minutes=5))
    assert again.inserted_at_utc == stored.inserted_at_utc
    assert store.count_packets() == 1


def test_store_rejects_hash_mismatch_and_detects_corruption(
    store: MarketPacketStore,
) -> None:
    packet = build_packet()
    tampered = replace(packet, content_hash="0" * 64)
    with pytest.raises(ValueError, match="does not match its payload"):
        store.store(tampered)

    stored = store.store(packet, inserted_at_utc=NOW)
    with store.connect() as conn:
        conn.execute(
            "UPDATE trading_market_packets SET payload_json = ? WHERE packet_id = ?",
            ('{"symbol": "TAMPERED"}', stored.packet_id),
        )
        conn.commit()
    with pytest.raises(RuntimeError, match="corrupt"):
        store.get(stored.packet_id)


def test_store_rejects_non_boundary_developing_candle(
    store: MarketPacketStore,
) -> None:
    packet = build_packet()
    shifted = replace(
        packet.payload.developing_4h_candle,
        open_time=provider_timestamp(DEVELOPING_RAW_OPEN + 60),
    )
    payload = replace(packet.payload, developing_4h_candle=shifted)
    from soma.trading.market_packet import packet_content_hash

    bad = MarketPacket(
        packet_id="mp_" + packet_content_hash(payload)[:24],
        content_hash=packet_content_hash(payload),
        payload=payload,
    )
    with pytest.raises(ValueError, match="broker-time H4 boundary"):
        store.store(bad)


def test_offset_events_record_changes_without_reinterpreting_history(
    store: MarketPacketStore,
) -> None:
    packet = build_packet()
    stored = store.store(packet, inserted_at_utc=NOW)

    first = store.record_offset_event(
        symbol=SYMBOL,
        offset_seconds=OFFSET,
        sample_count=5,
        max_deviation_seconds=12.0,
        detected_at_utc=NOW,
    )
    assert first.previous_offset_seconds is None

    second = store.record_offset_event(
        symbol=SYMBOL,
        offset_seconds=OFFSET + 3600,
        sample_count=4,
        max_deviation_seconds=8.0,
        detected_at_utc=NOW + timedelta(days=90),
    )
    assert second.previous_offset_seconds == OFFSET
    assert store.latest_offset(SYMBOL).offset_seconds == OFFSET + 3600
    assert [event.offset_seconds for event in store.offset_events(SYMBOL)] == [
        OFFSET,
        OFFSET + 3600,
    ]

    # The stored packet keeps the offset it was normalized with.
    assert store.get(stored.packet_id).broker_utc_offset_seconds == OFFSET


def test_list_packets_paginates(store: MarketPacketStore) -> None:
    packet = build_packet()
    store.store(packet, inserted_at_utc=NOW)
    assert [p.packet_id for p in store.list_packets(limit=1, offset=0)] == [
        packet.packet_id
    ]
    assert store.list_packets(limit=1, offset=1) == []
    with pytest.raises(ValueError, match="between 1 and 500"):
        store.list_packets(limit=0)
