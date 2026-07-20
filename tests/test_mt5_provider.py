from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from codexbridge.trading.mt5_provider import MT5Provider


UTC = timezone.utc
OFFSET = 3 * 60 * 60
NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


class FakeMT5:
    TIMEFRAME_H4 = 16388
    COPY_TICKS_ALL = -1
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self) -> None:
        self.range_args = None
        self.shutdown_called = False

    def initialize(self, *_args, **_kwargs):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return (1, "Success")

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def account_info(self):
        return SimpleNamespace(
            trade_mode=0,
            server="Alpari-MT5-Demo",
            login=123,
            currency="USD",
            balance=998.72,
            equity=998.72,
        )

    def symbols_get(self):
        return [
            SimpleNamespace(name="BITCOIN CASH_i", description="Bitcoin Cash", path="Crypto", visible=True),
            SimpleNamespace(name="BITCOIN_i", description="Bitcoin", path="Crypto", visible=True),
        ]

    def symbol_select(self, _symbol, _enable):
        return True

    def symbol_info(self, _symbol):
        return SimpleNamespace(
            digits=2,
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=0.01,
            trade_contract_size=1.0,
            volume_min=0.01,
            volume_max=10.0,
            volume_step=0.01,
            trade_mode=4,
            order_mode=127,
            margin_initial=0.0,
            margin_maintenance=0.0,
            currency_base="BTC",
            currency_profit="USD",
            currency_margin="USD",
        )

    def symbol_info_tick(self, _symbol):
        raw = int(NOW.timestamp()) + OFFSET - 30
        return SimpleNamespace(time=raw, bid=64000.0, ask=64064.0, last=0.0, volume_real=2.0)

    def copy_rates_from_pos(self, _symbol, _timeframe, _start, _count):
        return [
            {"time": int(datetime(2026, 7, 20, 3, 0, tzinfo=UTC).timestamp()) + OFFSET, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "tick_volume": 10, "spread": 2, "real_volume": 1},
            {"time": int(datetime(2026, 7, 20, 7, 0, tzinfo=UTC).timestamp()) + OFFSET, "open": 1.5, "high": 2.5, "low": 1, "close": 2, "tick_volume": 11, "spread": 3, "real_volume": 2},
        ]

    def copy_ticks_range(self, symbol, start, end, flags):
        self.range_args = (symbol, start, end, flags)
        return [{"time": int(NOW.timestamp()) + OFFSET, "bid": 1, "ask": 2, "last": 1.5, "volume_real": 3, "flags": 7}]


def provider(fake: FakeMT5 | None = None) -> tuple[MT5Provider, FakeMT5]:
    binding = fake or FakeMT5()
    adapter = MT5Provider(
        binding=binding,
        provider_utc_offset_seconds=OFFSET,
        now=lambda: NOW,
        maximum_tick_age_seconds=60,
    )
    adapter.connect()
    return adapter, binding


def test_health_and_exact_symbol_resolution_disambiguate_bitcoin_cash() -> None:
    adapter, _ = provider()

    health = adapter.health()
    symbols = adapter.list_symbols("bitcoin")

    assert health.connected is True
    assert health.account_environment == "demo"
    assert [symbol.name for symbol in symbols] == ["BITCOIN CASH_i", "BITCOIN_i"]
    assert adapter.resolve_exact_symbol("BITCOIN_i").description == "Bitcoin"
    with pytest.raises(LookupError):
        adapter.resolve_exact_symbol("BITCOIN")


def test_specification_and_tick_preserve_raw_time_and_normalize_offset() -> None:
    adapter, _ = provider()

    specification = adapter.symbol_specification("BITCOIN_i")
    tick = adapter.latest_tick("BITCOIN_i")

    assert specification.contract_size == 1.0
    assert specification.minimum_volume == 0.01
    assert tick.ask - tick.bid == 64.0
    assert tick.timestamp.provider_utc_offset_seconds == OFFSET
    assert tick.timestamp.normalized_utc == datetime(2026, 7, 20, 7, 59, 30, tzinfo=UTC)
    assert tick.age_seconds == 30
    assert tick.fresh is True


def test_h4_candles_separate_completed_from_developing() -> None:
    adapter, _ = provider()

    completed, developing = adapter.h4_candles("BITCOIN_i", completed_count=10)

    assert len(completed) == 1
    assert completed[0].open_time.normalized_utc.hour == 3
    assert developing is not None
    assert developing.open_time.normalized_utc.hour == 7


def test_historical_ticks_translate_query_bounds_and_normalize_results() -> None:
    adapter, binding = provider()
    start = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
    end = datetime(2026, 7, 20, 7, 0, tzinfo=UTC)

    ticks = adapter.historical_ticks("BITCOIN_i", start, end)

    assert binding.range_args[1] == datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    assert binding.range_args[2] == datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    assert ticks[0].timestamp.normalized_utc == NOW
    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.historical_ticks("BITCOIN_i", datetime(2026, 7, 20, 6), end)
