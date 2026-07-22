from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from soma.trading.market_packet import (
    MarketPacketBuilder,
    canonical_packet_bytes,
    packet_content_hash,
)
from soma.trading.mt5_provider import (
    Candle,
    ProviderHealth,
    ProviderTimestamp,
    SymbolSpecification,
    Tick,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
SYMBOL = "BITCOIN_i"
OFFSET = 3 * 60 * 60


def timestamp(value: datetime) -> ProviderTimestamp:
    return ProviderTimestamp(
        raw_epoch_seconds=int(value.timestamp()) + OFFSET,
        provider_utc_offset_seconds=OFFSET,
        normalized_utc=value,
    )


def candle(open_time: datetime, value: float) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe="4H",
        open_time=timestamp(open_time),
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
        first = NOW - timedelta(hours=4 * 101)
        self.completed = [candle(first + timedelta(hours=4 * index), 60_000 + index) for index in range(100)]
        self.developing = candle(first + timedelta(hours=400), 61_000)
        self.tick = Tick(
            symbol=SYMBOL,
            bid=64_000.0,
            ask=64_064.0,
            last=0.0,
            volume=1.0,
            timestamp=timestamp(NOW - timedelta(seconds=15)),
            age_seconds=15.0,
            fresh=True,
        )
        self.calls: list[str] = []

    def health(self) -> ProviderHealth:
        self.calls.append("health")
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
        self.calls.append("specification")
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
        self.calls.append("tick")
        return self.tick

    def h4_candles(self, _symbol: str, *, completed_count: int = 200):
        self.calls.append(f"candles:{completed_count}")
        return self.completed[-completed_count:], self.developing


def build(provider: PacketProvider | None = None):
    source = provider or PacketProvider()
    packet = MarketPacketBuilder(now=lambda: NOW).build(
        source, SYMBOL, completed_count=100
    )
    return packet, source


def test_packet_is_immutable_and_built_from_one_coherent_provider_sequence() -> None:
    packet, provider = build()

    assert provider.calls == ["health", "specification", "tick", "candles:100"]
    assert packet.payload.account_environment == "demo"
    assert packet.payload.latest_tick.ask == 64_064.0
    assert len(packet.payload.completed_4h_candles) == 100
    assert packet.payload.completed_4h_candles[-1].open_time.normalized_utc < packet.payload.developing_4h_candle.open_time.normalized_utc
    assert packet.payload.data_age_seconds == 15.0
    assert packet.packet_id == f"mp_{packet.content_hash[:24]}"
    with pytest.raises(FrozenInstanceError):
        packet.content_hash = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        packet.payload.symbol = "OTHER"  # type: ignore[misc]


def test_packet_hash_is_deterministic_and_sensitive_to_authoritative_values() -> None:
    first, _ = build()
    second, _ = build()

    assert first == second
    assert canonical_packet_bytes(first.payload) == canonical_packet_bytes(second.payload)
    assert packet_content_hash(first.payload) == first.content_hash

    changed_payload = replace(
        first.payload,
        latest_tick=replace(first.payload.latest_tick, ask=first.payload.latest_tick.ask + 0.01),
    )
    assert packet_content_hash(changed_payload) != first.content_hash


def test_builder_rejects_stale_ticks_and_wrong_environment() -> None:
    stale = PacketProvider()
    stale.tick = replace(stale.tick, fresh=False, age_seconds=121.0)
    with pytest.raises(RuntimeError, match="stale tick"):
        build(stale)
    assert stale.calls == ["health", "specification", "tick"]

    live = PacketProvider()
    original_health = live.health

    def live_health() -> ProviderHealth:
        return replace(original_health(), account_environment="unknown")

    live.health = live_health  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="demo account"):
        build(live)
    assert live.calls == ["health"]


def test_builder_rejects_completed_developing_overlap_and_incomplete_history() -> None:
    overlap = PacketProvider()
    overlap.developing = overlap.completed[-1]
    with pytest.raises(RuntimeError, match="must follow"):
        build(overlap)

    short = PacketProvider()
    short.completed = short.completed[:-1]
    with pytest.raises(RuntimeError, match="Expected 100 completed"):
        build(short)


@pytest.mark.parametrize("count", [99, 201])
def test_builder_enforces_frozen_v1_candle_window(count: int) -> None:
    with pytest.raises(ValueError, match="between 100 and 200"):
        MarketPacketBuilder(now=lambda: NOW).build(PacketProvider(), SYMBOL, completed_count=count)
