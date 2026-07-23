"""Shared deterministic fixtures for the redesigned Trading Lab tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from soma.trading.market_packet import MarketPacket, MarketPacketBuilder
from soma.trading.mt5_provider import (
    Candle,
    ProviderHealth,
    ProviderTimestamp,
    SymbolSpecification,
    Tick,
)

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


def demo_health() -> ProviderHealth:
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


def bitcoin_specification(symbol: str = SYMBOL) -> SymbolSpecification:
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


class PacketProvider:
    """Deterministic connected demo provider snapshot for packet building."""

    def __init__(
        self,
        *,
        bid: float = 64_000.0,
        ask: float = 64_064.0,
        now: datetime = NOW,
    ) -> None:
        self.completed = [
            candle(DEVELOPING_RAW_OPEN - H4 * (100 - index), 60_000 + index)
            for index in range(100)
        ]
        self.developing = candle(DEVELOPING_RAW_OPEN, 61_000)
        tick_raw = int(now.timestamp()) + OFFSET - 15
        self.tick = Tick(
            symbol=SYMBOL,
            bid=bid,
            ask=ask,
            last=0.0,
            volume=1.0,
            timestamp=provider_timestamp(tick_raw),
            age_seconds=15.0,
            fresh=True,
        )

    def health(self) -> ProviderHealth:
        return demo_health()

    def symbol_specification(self, symbol: str) -> SymbolSpecification:
        return bitcoin_specification(symbol)

    def latest_tick(self, _symbol: str) -> Tick:
        return self.tick

    def h4_candles(self, _symbol: str, *, completed_count: int = 200):
        return self.completed[-completed_count:], self.developing


def build_packet(
    *,
    bid: float = 64_000.0,
    ask: float = 64_064.0,
    now: datetime = NOW,
) -> MarketPacket:
    return MarketPacketBuilder(now=lambda: now).build(
        PacketProvider(bid=bid, ask=ask, now=now), SYMBOL, completed_count=100
    )


def archived_tick(
    at: datetime,
    bid: float,
    ask: float,
    *,
    symbol: str = SYMBOL,
    source: str = "test",
):
    from soma.trading.tick_archive import ArchivedTick

    return ArchivedTick(
        symbol=symbol,
        raw_epoch_seconds=int(at.timestamp()) + OFFSET,
        broker_utc_offset_seconds=OFFSET,
        normalized_utc=at,
        bid=bid,
        ask=ask,
        last=0.0,
        volume=1.0,
        flags=0,
        source=source,
    )


def signal_record_v2(
    *,
    signal_id: str = "sig2_test000000000000000001",
    decision: str = "LONG",
    confidence: int | None = 73,
    bid: float = 64_000.0,
    ask: float = 64_064.0,
    stop_loss: float | None = 63_400.0,
    take_profit: float | None = 65_400.0,
    submitted_at: datetime = NOW + timedelta(minutes=2),
    entered_at: datetime | None = None,
    experiment_id: str = "exp1",
    policy_id: str = "hourly_fixed_bracket_v1",
    execution_mode: str = "internal_paper",
):
    """A directly constructed v2 signal record for resolver/replay tests."""
    from soma.trading.signal_journal_v2 import (
        SignalDecisionV2,
        SignalRecordV2,
        SignalStatusV2,
    )
    from soma.trading.versions import SIGNAL_SCHEMA_VERSION

    normalized_decision = SignalDecisionV2(decision)
    entry = None
    if normalized_decision is SignalDecisionV2.LONG:
        entry = ask
    elif normalized_decision is SignalDecisionV2.SHORT:
        entry = bid
    return SignalRecordV2(
        signal_id=signal_id,
        idempotency_key=f"key-{signal_id}",
        content_hash="0" * 64,
        schema_version=SIGNAL_SCHEMA_VERSION,
        packet_id="mp_test",
        packet_hash="0" * 64,
        symbol=SYMBOL,
        bid=bid,
        ask=ask,
        spread=ask - bid,
        market_data_timestamp=submitted_at - timedelta(seconds=15),
        tick_raw_epoch_seconds=int(submitted_at.timestamp()) + OFFSET,
        broker_utc_offset_seconds=OFFSET,
        parent_h4_raw_open_epoch=DEVELOPING_RAW_OPEN,
        parent_h4_open_utc=DEVELOPING_OPEN_UTC,
        packet_age_seconds=15.0,
        decision=normalized_decision,
        confidence=confidence,
        entry_reference_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=None,
        model_version="gpt-test-1",
        prompt_version="prompt-v1",
        policy_id=policy_id,
        execution_mode=execution_mode,
        experiment_id=experiment_id,
        reason="test",
        news_context="",
        status=(
            SignalStatusV2.ENTERED
            if entered_at is not None
            else SignalStatusV2.SUBMITTED
        ),
        submitted_at_utc=submitted_at,
        inserted_at_utc=submitted_at,
        entered_at_utc=entered_at,
    )
