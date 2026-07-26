"""Soma's public trading gateways, served by the standalone package.

These are the integration tests that outlive the migration. They drive
Soma's real gateway functions -- the same code paths MCP clients reach --
against isolated temporary databases and a deterministic fake MT5
provider, and assert on the public contract: operation names, envelope
fields, compact/full views, response budgets, error classifications, and
the deprecation responses.

Detailed domain behavior is tested in the TradingLab repository. What is
tested here is the boundary: that Soma's contract is unchanged now that
the domain lives in an external package.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from soma import server, trading_lab_adapter
from soma.config import AppConfig, RepoConfig

UTC = timezone.utc
SYMBOL = "BITCOIN_i"
OFFSET = 3 * 60 * 60
H1 = 60 * 60
H4 = 4 * 60 * 60
DEVELOPING_RAW_OPEN = 1_784_534_400
DEVELOPING_OPEN_UTC = datetime.fromtimestamp(DEVELOPING_RAW_OPEN - OFFSET, tz=UTC)
NOW = DEVELOPING_OPEN_UTC + timedelta(hours=1)

from trading_lab.candle_boundary import (  # noqa: E402
    CandleBoundary,
    detect_candle_gaps,
    resolve_candle_boundary,
)
from trading_lab.market_sessions import CRYPTO_WEEKEND_MAINTENANCE  # noqa: E402
from trading_lab.mt5_provider import (  # noqa: E402
    Candle,
    HistoricalCandles,
    HistoricalTick,
    ProviderHealth,
    ProviderTimestamp,
    SymbolSpecification,
    SymbolSummary,
    Tick,
)
from trading_lab.service import (  # noqa: E402
    ACTION_OPERATIONS,
    COMPANION_OPERATIONS,
    COMPATIBILITY_READ_OPERATIONS,
    DEPRECATED_QUERY_OPERATIONS,
    JOURNAL_QUERY_OPERATIONS,
    READ_OPERATIONS,
    RUNTIME_CONTROL_OPERATIONS,
    SIGNAL_OPERATIONS,
)
from trading_lab.timeframes import resolve_timeframe  # noqa: E402


# --------------------------------------------------------------------------
# Deterministic provider double.
# --------------------------------------------------------------------------


def provider_timestamp(raw_epoch: int) -> ProviderTimestamp:
    return ProviderTimestamp(
        raw_epoch_seconds=raw_epoch,
        provider_utc_offset_seconds=OFFSET,
        normalized_utc=datetime.fromtimestamp(raw_epoch - OFFSET, tz=UTC),
    )


def candle(
    raw_open: int, value: float, *, timeframe: str = "4H"
) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe=timeframe,
        open_time=provider_timestamp(raw_open),
        open=value,
        high=value + 2,
        low=value - 1,
        close=value + 1,
        tick_volume=100,
        spread=64,
        real_volume=0,
    )


def specification() -> SymbolSpecification:
    return SymbolSpecification(
        symbol=SYMBOL,
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


class FakeProvider:
    """A connected demo MT5 provider that never touches a terminal."""

    def __init__(
        self,
        *,
        connected: bool = True,
        environment: str = "demo",
        symbol_count: int = 40,
        now: datetime | None = None,
    ) -> None:
        self._connected = connected
        self._environment = environment
        self._now = now or NOW
        self.closed = False
        broker_epoch = int(self._now.timestamp()) + OFFSET
        h1_open_epoch = broker_epoch - (broker_epoch % H1)
        self._completed_h1 = [
            candle(
                h1_open_epoch - H1 * (100 - index),
                60_000 + index,
                timeframe="1H",
            )
            for index in range(100)
        ]
        self._developing_h1 = candle(
            h1_open_epoch, 61_000, timeframe="1H"
        )
        h4_open_epoch = broker_epoch - (broker_epoch % H4)
        self._completed_h4 = [
            candle(h4_open_epoch - H4 * (100 - index), 60_000 + index)
            for index in range(100)
        ]
        self._developing_h4 = candle(h4_open_epoch, 61_000)
        self._symbols = [
            SymbolSummary(
                name=f"SYM{index:03d}" if index else SYMBOL,
                description=f"Instrument {index} with a description long"
                " enough to exercise the response budget",
                path=f"Crypto\\Group{index}",
                visible=True,
            )
            for index in range(symbol_count)
        ]

    @property
    def binding(self) -> Any:  # pragma: no cover - broker_demo only
        raise AssertionError("the fake provider has no broker binding")

    def connect(self) -> ProviderHealth:
        return self.health()

    def close(self) -> None:
        self.closed = True

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            initialized=True,
            connected=self._connected,
            account_environment=self._environment,
            server="Alpari-MT5-Demo",
            login=123,
            currency="USD",
            balance=998.72,
            equity=998.72,
            last_error=(1, "Success"),
        )

    def list_symbols(self, query: str = "") -> list[SymbolSummary]:
        needle = query.strip().casefold()
        if not needle:
            return list(self._symbols)
        return [
            item
            for item in self._symbols
            if needle in item.name.casefold()
            or needle in item.description.casefold()
        ]

    def symbol_specification(self, symbol: str) -> SymbolSpecification:
        return specification()

    def latest_tick(self, _symbol: str) -> Tick:
        return Tick(
            symbol=SYMBOL,
            bid=64_000.0,
            ask=64_064.0,
            last=0.0,
            volume=1.0,
            timestamp=provider_timestamp(
                int(self._now.timestamp()) + OFFSET - 15
            ),
            age_seconds=15.0,
            fresh=True,
        )

    def _series(self, timeframe: Any) -> tuple[list[Candle], Candle]:
        period = resolve_timeframe(timeframe)
        if period.name == "H4":
            return self._completed_h4, self._developing_h4
        if period.name == "H1":
            return self._completed_h1, self._developing_h1
        raise LookupError(f"the fake provider has no {period.name} series")

    def candles(
        self,
        _symbol: str,
        timeframe: Any = None,
        *,
        completed_count: int = 200,
    ) -> tuple[list[Candle], Candle | None]:
        completed, developing = self._series(timeframe)
        return completed[-completed_count:], developing

    def candle_boundary(
        self,
        symbol: str,
        timeframe: Any = None,
        *,
        probe_bars: int = 3,
        probe_attempts: int = 2,
    ) -> CandleBoundary:
        """A live probe over the newest few bars, exactly like the adapter."""
        completed, developing = self._series(timeframe)
        return resolve_candle_boundary(
            symbol=symbol,
            timeframe=timeframe,
            tick=self.latest_tick(symbol),
            bars=[*completed[-(probe_bars - 1) :], developing],
            now=self._now,
            calendar=CRYPTO_WEEKEND_MAINTENANCE,
        )

    def historical_candles(
        self, symbol: str, timeframe: Any = None, *, count: int = 200
    ) -> HistoricalCandles:
        period = resolve_timeframe(timeframe)
        completed, _ = self._series(timeframe)
        window = completed[-count:]
        return HistoricalCandles(
            symbol=symbol,
            timeframe=period.name,
            timeframe_seconds=period.seconds,
            requested_count=count,
            candles=tuple(window),
            gaps=detect_candle_gaps(
                window, period, calendar=CRYPTO_WEEKEND_MAINTENANCE
            ),
            warnings=(),
        )

    def h1_candles(
        self, _symbol: str, *, completed_count: int = 200
    ) -> tuple[list[Candle], Candle | None]:
        return self._completed_h1[-completed_count:], self._developing_h1

    def h4_candles(
        self, _symbol: str, *, completed_count: int = 200
    ) -> tuple[list[Candle], Candle | None]:
        return self._completed_h4[-completed_count:], self._developing_h4

    def historical_ticks(
        self, _symbol: str, start_utc: datetime, end_utc: datetime
    ) -> list[HistoricalTick]:
        return [
            HistoricalTick(
                symbol=SYMBOL,
                bid=64_000.0 + index,
                ask=64_064.0 + index,
                last=0.0,
                volume=1.0,
                flags=0,
                timestamp=provider_timestamp(
                    int(start_utc.timestamp()) + OFFSET + index * 60
                ),
            )
            for index in range(60)
        ]


# --------------------------------------------------------------------------
# Fixtures.
# --------------------------------------------------------------------------


@pytest.fixture()
def trading_env(monkeypatch, tmp_path: Path):
    """A configured Soma with trading enabled and isolated state."""
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        trading={
            "enabled": True,
            "symbol": SYMBOL,
            "provider_utc_offset_seconds": OFFSET,
            "maximum_tick_age_seconds": 120,
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    trading_lab_adapter.reset_services_cache()

    provider = FakeProvider()
    monkeypatch.setattr(server, "_configured_mt5_provider", lambda: provider)
    monkeypatch.setattr(
        trading_lab_adapter,
        "configured_mt5_provider",
        lambda _config: provider,
    )
    yield config, provider, tmp_path
    trading_lab_adapter.reset_services_cache()


@pytest.fixture()
def disabled_env(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    trading_lab_adapter.reset_services_cache()
    yield config
    trading_lab_adapter.reset_services_cache()


def response_size(response: dict) -> int:
    return len(json.dumps(response, ensure_ascii=False).encode("utf-8"))


def query(**kwargs: Any) -> dict:
    from soma.gateway_models import TradingQueryRequest
    from pydantic import TypeAdapter

    request = TypeAdapter(TradingQueryRequest).validate_python(kwargs)
    return server.trading_query(request)


def stored_packet(config: AppConfig, provider: FakeProvider) -> str:
    """Store a packet that is fresh against the real clock.

    Signal submission stamps ``submitted_at_utc`` from ``datetime.now``
    and refuses packets outside the freshness window, so the packet has to
    be built against the same clock rather than the fixed fixture instant.
    """
    from trading_lab.market_packet import MarketPacketBuilder

    now = datetime.now(UTC)
    lab = trading_lab_adapter.services(config)
    packet = MarketPacketBuilder(now=lambda: now).build(
        FakeProvider(now=now), SYMBOL, completed_count=100
    )
    return lab.packet_store().store(packet, inserted_at_utc=now).packet_id


# --------------------------------------------------------------------------
# The package really is the implementation.
# --------------------------------------------------------------------------


class TestBackendIdentity:
    def test_soma_resolves_the_external_package(self) -> None:
        identity = trading_lab_adapter.package_identity()
        assert identity["backend"] == "package"
        assert identity["package"] == "trading_lab"
        assert identity["version"]
        assert "trading_lab" in identity["module_path"]

    def test_no_gateway_symbol_comes_from_the_in_tree_copy(self) -> None:
        for name in (
            "MT5Provider",
            "SignalSubmissionV2",
            "SignalDecisionV2",
            "SignalRejectedError",
            "TradingActionRequest",
            "TradingActionType",
            "TradingCapabilityRole",
            "TradingExecutionMode",
            "ActionState",
        ):
            symbol = getattr(server, name)
            assert symbol.__module__.startswith("trading_lab"), name

    def test_the_adapter_is_the_only_seam(self) -> None:
        """No Soma module may import the trading domain directly.

        Checked with the AST rather than substrings, so importing the
        adapter itself is not mistaken for importing the package.
        """
        import ast

        soma_root = Path(server.__file__).parent
        adapter = soma_root / "trading_lab_adapter.py"
        offenders: list[str] = []
        for path in sorted(soma_root.rglob("*.py")):
            if path == adapter:
                continue
            tree = ast.parse(path.read_text("utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [
                        alias.name.split(".")[0] for alias in node.names
                    ]
                elif isinstance(node, ast.ImportFrom):
                    roots = [(node.module or "").split(".")[0]]
                    if node.level:
                        roots = [
                            f".{root}" if root else "." for root in roots
                        ]
                else:
                    continue
                if "trading_lab" in roots or ".trading" in roots:
                    offenders.append(f"{path.name}:{node.lineno}")
        assert offenders == []

    def test_the_in_tree_implementation_is_gone(self) -> None:
        from importlib.util import find_spec

        assert not (Path(server.__file__).parent / "trading").exists()
        assert find_spec("soma.trading") is None


class TestStateCompatibility:
    """The cutover must not fork state onto new paths."""

    def test_paths_match_the_pre_migration_layout(self, trading_env) -> None:
        config, _provider, tmp_path = trading_env
        expected = (tmp_path / "runs" / "trading").resolve()
        assert server._trading_dir() == expected

        lab = trading_lab_adapter.services(config)
        assert lab.paths.root == expected
        assert lab.packet_store().db_path == expected / "packets.sqlite3"
        assert lab.signal_journal().db_path == expected / "signals.sqlite3"
        assert lab.outcome_journal().db_path == expected / "outcomes.sqlite3"
        assert lab.tick_archive().db_path == expected / "ticks.sqlite3"
        assert (
            lab.tick_archive().archive_dir == expected / "tick_archives"
        )
        assert lab.action_journal().db_path == expected / "actions.sqlite3"
        assert lab.safety().db_path == expected / "safety.sqlite3"
        assert lab.runtime().runtime_db_path == expected / "runtime.sqlite3"

    def test_config_maps_field_for_field(self, trading_env) -> None:
        config, _provider, _tmp = trading_env
        settings = trading_lab_adapter.settings_from_config(config)
        assert settings.symbol == config.trading.symbol
        assert (
            settings.provider_utc_offset_seconds
            == config.trading.provider_utc_offset_seconds
        )
        assert (
            settings.maximum_tick_age_seconds
            == config.trading.maximum_tick_age_seconds
        )
        assert settings.terminal_path == (config.trading.terminal_path or None)
        assert settings.timeframe == config.trading.timeframe
        assert settings.candle_count == config.trading.candle_count
        assert settings.session_calendar == config.trading.session_calendar
        assert (
            settings.boundary_probe_bars == config.trading.boundary_probe_bars
        )

    def test_the_timeframe_defaults_match_the_domain(self, trading_env) -> None:
        """H1 is the current experiment, named once and mapped straight through."""
        config, _provider, _tmp = trading_env
        assert config.trading.timeframe == "H1"
        assert config.trading.candle_count == 200
        assert config.trading.session_calendar == "crypto_weekend_maintenance"

    def test_the_domain_resolves_timeframes_soma_only_carries(
        self, trading_env
    ) -> None:
        """Soma holds no copy of the period registry; it forwards a string."""
        config, _provider, _tmp = trading_env
        config.trading.timeframe = "15m"
        settings = trading_lab_adapter.settings_from_config(config)
        assert settings.timeframe == "M15"

    @pytest.mark.parametrize(
        "field,value",
        [("timeframe", "H5"), ("session_calendar", "invented")],
    )
    def test_an_unknown_period_or_calendar_is_refused_by_the_domain(
        self, trading_env, field: str, value: str
    ) -> None:
        config, _provider, _tmp = trading_env
        setattr(config.trading, field, value)
        with pytest.raises(ValueError):
            trading_lab_adapter.settings_from_config(config)

    def test_the_provider_carries_the_configured_session_calendar(
        self, tmp_path: Path
    ) -> None:
        """Otherwise the Saturday maintenance pause reads as missing data.

        Built from a plain config rather than the ``trading_env`` fixture,
        which substitutes the fake provider for the real constructor.
        """
        (tmp_path / ".git").mkdir()
        config = AppConfig(
            repos={"repo": RepoConfig(path=str(tmp_path))},
            runs_dir=str(tmp_path / "runs"),
            trading={"enabled": True, "symbol": SYMBOL},
            config_dir=tmp_path,
        )
        provider = trading_lab_adapter.configured_mt5_provider(config)
        assert provider.session_calendar.name == "crypto_weekend_maintenance"

    def test_services_are_stable_within_one_configuration(
        self, trading_env
    ) -> None:
        """The paper executor holds positions; it must not be rebuilt."""
        config, _provider, _tmp = trading_env
        assert trading_lab_adapter.services(
            config
        ) is trading_lab_adapter.services(config)


# --------------------------------------------------------------------------
# Market-data reads.
# --------------------------------------------------------------------------


class TestMarketDataReads:
    def test_health_compact(self, trading_env) -> None:
        result = query(operation="health")
        assert result["ok"] is True
        assert result["operation"] == "health"
        assert result["result"]["account_environment"] == "demo"
        assert result["result"]["connected"] is True
        assert result["truncated"] is False
        assert result["response_bytes"] <= result["response_budget_bytes"]

    def test_health_full_has_no_envelope(self, trading_env) -> None:
        result = query(operation="health", view="full")
        assert result["ok"] is True
        assert "response_bytes" not in result
        assert "truncated" not in result

    def test_symbols(self, trading_env) -> None:
        result = query(operation="symbols")
        assert result["ok"] is True
        assert isinstance(result["result"], list)
        assert result["symbol"] == SYMBOL

    def test_symbols_query_filter(self, trading_env) -> None:
        result = query(operation="symbols", query="SYM001", view="full")
        assert [item["name"] for item in result["result"]] == ["SYM001"]

    def test_symbols_respects_the_budget(self, trading_env) -> None:
        result = query(operation="symbols", response_budget_bytes=1024)
        assert result["response_bytes"] <= 1024
        assert result["truncated"] is True
        assert result["has_more"] is True

    def test_specification(self, trading_env) -> None:
        result = query(operation="specification")
        assert result["ok"] is True
        assert result["result"]["symbol"] == SYMBOL
        assert result["result"]["digits"] == 2

    def test_tick(self, trading_env) -> None:
        result = query(operation="tick", view="full")
        assert result["result"]["bid"] == 64_000.0
        assert result["result"]["ask"] == 64_064.0
        assert result["result"]["fresh"] is True
        assert (
            result["result"]["timestamp"]["provider_utc_offset_seconds"]
            == OFFSET
        )

    def test_candles_default_to_the_configured_period(self, trading_env) -> None:
        result = query(operation="candles", completed_count=5, view="full")
        assert len(result["result"]["completed"]) == 5
        assert result["result"]["developing"]["timeframe"] == "1H"

    def test_candles_accept_an_explicit_period(self, trading_env) -> None:
        result = query(
            operation="candles",
            timeframe="H4",
            completed_count=5,
            view="full",
        )
        assert result["result"]["developing"]["timeframe"] == "4H"

    def test_candles_respect_the_budget(self, trading_env) -> None:
        result = query(
            operation="candles",
            completed_count=100,
            response_budget_bytes=2048,
        )
        assert result["response_bytes"] <= 2048
        assert result["truncated"] is True

    def test_an_unknown_period_is_refused_with_the_domain_message(
        self, trading_env
    ) -> None:
        """Soma forwards the string; the domain names what it accepts."""
        result = query(operation="candles", timeframe="H5")
        assert result["ok"] is False
        assert result["status"] == "provider_error"
        assert "unknown timeframe" in result["error"]

    def test_candle_boundary_is_a_separate_bounded_read(
        self, trading_env
    ) -> None:
        result = query(operation="candle_boundary", view="full")
        boundary = result["result"]

        assert boundary["timeframe"] == "H1"
        assert boundary["boundary_source"] == "live_probe"
        assert boundary["decision_candle"]["timeframe"] == "1H"
        assert boundary["developing"]["timeframe"] == "1H"
        # The just-closed candle, not the developing one, is the decision.
        assert (
            boundary["decision_open_utc"]
            < boundary["developing"]["open_time"]["normalized_utc"]
        )
        assert boundary["synchronised"] is True
        assert boundary["latest_tick"]["fresh"] is True

    def test_candle_boundary_compact_stays_within_the_budget(
        self, trading_env
    ) -> None:
        result = query(operation="candle_boundary", response_budget_bytes=1024)
        assert result["response_bytes"] <= 1024
        assert result["truncated"] is True

    def test_historical_candles_is_its_own_window_read(
        self, trading_env
    ) -> None:
        result = query(operation="historical_candles", count=10, view="full")
        window = result["result"]

        assert window["timeframe"] == "H1"
        assert window["requested_count"] == 10
        assert len(window["candles"]) == 10
        assert window["gaps"] == []

    def test_historical_candles_trims_the_oldest_bars_first(
        self, trading_env
    ) -> None:
        full = query(operation="historical_candles", count=100, view="full")
        trimmed = query(
            operation="historical_candles",
            count=100,
            response_budget_bytes=2048,
        )

        assert trimmed["response_bytes"] <= 2048
        assert trimmed["truncated"] is True
        # What survives is the end of the window: the bars nearest the
        # decision boundary.
        assert (
            trimmed["result"]["candles"][-1]
            == full["result"]["candles"][-1]
        )

    def test_h1_candles(self, trading_env) -> None:
        result = query(operation="h1_candles", completed_count=5, view="full")
        assert len(result["result"]["completed"]) == 5
        assert result["result"]["completed"][-1]["timeframe"] == "1H"
        assert result["result"]["developing"]["timeframe"] == "1H"

    def test_h1_candles_respects_the_budget(self, trading_env) -> None:
        result = query(
            operation="h1_candles",
            completed_count=100,
            response_budget_bytes=2048,
        )
        assert result["response_bytes"] <= 2048
        assert result["truncated"] is True

    def test_h4_candles(self, trading_env) -> None:
        result = query(operation="h4_candles", completed_count=5, view="full")
        assert len(result["result"]["completed"]) == 5
        assert result["result"]["developing"]["timeframe"] == "4H"

    def test_h4_candles_respects_the_budget(self, trading_env) -> None:
        result = query(
            operation="h4_candles",
            completed_count=100,
            response_budget_bytes=2048,
        )
        assert result["response_bytes"] <= 2048
        assert result["truncated"] is True

    def test_historical_ticks(self, trading_env) -> None:
        result = query(
            operation="historical_ticks",
            start_utc=NOW.isoformat(),
            end_utc=(NOW + timedelta(hours=1)).isoformat(),
            view="full",
        )
        assert len(result["result"]) == 60

    def test_historical_ticks_respects_the_budget(self, trading_env) -> None:
        result = query(
            operation="historical_ticks",
            start_utc=NOW.isoformat(),
            end_utc=(NOW + timedelta(hours=1)).isoformat(),
            response_budget_bytes=1024,
        )
        assert result["response_bytes"] <= 1024
        assert result["truncated"] is True

    def test_the_provider_is_always_closed(self, trading_env) -> None:
        _config, provider, _tmp = trading_env
        query(operation="health")
        assert provider.closed is True

    @pytest.mark.parametrize("operation", sorted(READ_OPERATIONS))
    def test_every_read_operation_is_served(
        self, trading_env, operation: str
    ) -> None:
        extra: dict[str, Any] = {"view": "full"}
        if operation == "historical_ticks":
            extra |= {
                "start_utc": NOW.isoformat(),
                "end_utc": (NOW + timedelta(hours=1)).isoformat(),
            }
        result = query(operation=operation, **extra)
        assert result["ok"] is True, result
        assert result["operation"] == operation

    @pytest.mark.parametrize(
        "operation", sorted(COMPATIBILITY_READ_OPERATIONS)
    )
    def test_the_hourly_aliases_remain_served(
        self, trading_env, operation: str
    ) -> None:
        """Callers written against the H1-only surface keep working."""
        result = query(operation=operation, completed_count=5, view="full")
        assert result["ok"] is True, result
        assert len(result["result"]["completed"]) == 5


class TestProviderErrorClassification:
    def test_disconnected(self, monkeypatch, trading_env) -> None:
        provider = FakeProvider(connected=False)
        monkeypatch.setattr(
            server, "_configured_mt5_provider", lambda: provider
        )
        result = query(operation="tick")
        assert result["ok"] is False
        assert result["status"] == "disconnected"
        assert result["error"] == "MT5 terminal is disconnected"
        assert result["health"]["connected"] is False

    def test_wrong_environment(self, monkeypatch, trading_env) -> None:
        provider = FakeProvider(environment="real")
        monkeypatch.setattr(
            server, "_configured_mt5_provider", lambda: provider
        )
        result = query(operation="tick")
        assert result["ok"] is False
        assert result["status"] == "wrong_environment"

    def test_health_is_reported_even_when_disconnected(
        self, monkeypatch, trading_env
    ) -> None:
        provider = FakeProvider(connected=False)
        monkeypatch.setattr(
            server, "_configured_mt5_provider", lambda: provider
        )
        result = query(operation="health")
        assert result["ok"] is True
        assert result["result"]["connected"] is False

    def test_provider_failure_is_classified(
        self, monkeypatch, trading_env
    ) -> None:
        class Broken(FakeProvider):
            def latest_tick(self, _symbol):
                raise RuntimeError("terminal exploded")

        monkeypatch.setattr(
            server, "_configured_mt5_provider", lambda: Broken()
        )
        result = query(operation="tick")
        assert result["ok"] is False
        assert result["status"] == "provider_error"
        assert "terminal exploded" in result["error"]


class TestDisabledTrading:
    @pytest.mark.parametrize(
        "call",
        [
            lambda: query(operation="health"),
            lambda: query(operation="runtime_status"),
        ],
    )
    def test_query_is_refused(self, disabled_env, call) -> None:
        result = call()
        assert result["ok"] is False
        assert result["status"] == "disabled"
        assert result["error"] == "Trading is disabled"

    def test_action_submit_is_refused(self, disabled_env) -> None:
        from soma.gateway_models import TradingActionSubmitRequest

        result = server.trading_action_submit(
            TradingActionSubmitRequest(
                idempotency_key="k", action_type="market_entry"
            )
        )
        assert result["status"] == "disabled"

    def test_runtime_control_is_refused(self, disabled_env) -> None:
        from soma.gateway_models import TradingRuntimeControlRequest

        result = server.trading_runtime_control(
            TradingRuntimeControlRequest(action="status")
        )
        assert result["status"] == "disabled"

    def test_companion_action_is_refused(self, disabled_env) -> None:
        from soma.gateway_models import TradingCompanionActionRequest
        from pydantic import TypeAdapter

        request = TypeAdapter(TradingCompanionActionRequest).validate_python(
            {
                "action": "start",
                "idempotency_key": "cycle",
                "task_invocation_id": "task",
                "research_summary": "disabled",
            }
        )
        assert server.trading_companion_action(request)["status"] == "disabled"

    def test_signal_submit_is_refused(self, disabled_env) -> None:
        from soma.gateway_models import TradingSignalSubmitRequest

        result = server.trading_signal_submit(
            TradingSignalSubmitRequest(
                idempotency_key="k",
                packet_id="mp_x",
                decision="LONG",
                reason="r",
                model_version="m",
                prompt_version="p",
            )
        )
        assert result["status"] == "disabled"


class TestDeprecatedOperations:
    @pytest.mark.parametrize(
        "operation", sorted(DEPRECATED_QUERY_OPERATIONS)
    )
    def test_compatibility_response_is_preserved(
        self, trading_env, operation: str
    ) -> None:
        result = query(operation=operation)
        assert result["ok"] is False
        assert result["status"] == "deprecated"
        assert result["operation"] == operation
        assert "Runtime virtual portfolios were removed" in result["error"]
        assert "replay_report" in result["error"]

    def test_the_notice_text_comes_from_the_package(self) -> None:
        from trading_lab.service import DEPRECATED_QUERY_NOTICE

        assert server.DEPRECATED_QUERY_NOTICE == DEPRECATED_QUERY_NOTICE

    def test_deprecated_operations_never_touch_the_provider(
        self, trading_env
    ) -> None:
        _config, provider, _tmp = trading_env
        query(operation="portfolio_status")
        assert provider.closed is False


# --------------------------------------------------------------------------
# Journal reads.
# --------------------------------------------------------------------------


class TestJournalReads:
    @pytest.mark.parametrize(
        "operation", sorted(JOURNAL_QUERY_OPERATIONS)
    )
    def test_every_journal_operation_is_served(
        self, trading_env, operation: str
    ) -> None:
        """The completeness gate for journal reads."""
        extra: dict[str, Any] = {"view": "full"}
        if operation in {
            "market_packet_get",
            "outcome_get",
            "action_get",
            "companion_get",
        }:
            pytest.skip("single-record reads are covered by focused tests")
        if operation == "data_quality":
            extra |= {
                "start_utc": NOW.isoformat(),
                "end_utc": (NOW + timedelta(hours=1)).isoformat(),
            }
        result = query(operation=operation, **extra)
        assert result["ok"] is True, result
        assert result["operation"] == operation

    def test_journal_reads_never_connect_to_the_provider(
        self, trading_env
    ) -> None:
        _config, provider, _tmp = trading_env
        query(operation="runtime_status")
        assert provider.closed is False

    def test_market_packet_round_trip(self, trading_env) -> None:
        config, provider, _tmp = trading_env
        packet_id = stored_packet(config, provider)

        listed = query(operation="market_packet_list", view="full")
        assert listed["result"]["total"] == 1
        assert listed["result"]["offset"] == 0
        assert "payload" not in listed["result"]["packets"][0]

        compact = query(operation="market_packet_get", packet_id=packet_id)
        assert compact["ok"] is True

        full = query(
            operation="market_packet_get", packet_id=packet_id, view="full"
        )
        assert full["result"]["packet_id"] == packet_id
        assert "payload" in full["result"]

    def test_missing_record_is_not_found(self, trading_env) -> None:
        for operation, key in (
            ("market_packet_get", "packet_id"),
            ("outcome_get", "signal_id"),
            ("action_get", "action_id"),
        ):
            result = query(operation=operation, **{key: "missing"})
            assert result["ok"] is False, operation
            assert result["status"] == "not_found", operation

    def test_data_quality(self, trading_env) -> None:
        result = query(
            operation="data_quality",
            start_utc=NOW.isoformat(),
            end_utc=(NOW + timedelta(hours=1)).isoformat(),
            view="full",
        )
        assert result["result"]["symbol"] == SYMBOL
        assert result["result"]["tick_count"] == 0
        assert isinstance(result["result"]["gaps"], list)

    def test_runtime_status_shape(self, trading_env) -> None:
        result = query(operation="runtime_status", view="full")
        assert set(result["result"]) == {
            "status",
            "kill_switch",
            "recent_events",
        }
        assert result["result"]["status"]["state"] == "stopped"
        assert result["result"]["kill_switch"]["active"] is False

    def test_calibration_report_shape(self, trading_env) -> None:
        result = query(operation="calibration_report", view="full")
        assert result["result"]["report"] == "signal_confidence_calibration"
        assert result["result"]["selected_signal_count"] == 0

    def test_replay_report_shape(self, trading_env) -> None:
        result = query(
            operation="replay_report",
            threshold_start=70,
            threshold_end=72,
            view="full",
        )
        assert isinstance(result["result"], dict)

    def test_list_pagination_fields(self, trading_env) -> None:
        for operation, key in (
            ("outcome_list", "outcomes"),
            ("action_list", "actions"),
            ("rejection_list", "rejections"),
        ):
            result = query(operation=operation, offset=0, view="full")
            assert result["result"][key] == [], operation
            assert result["result"]["offset"] == 0, operation

    def test_demo_performance_and_reconciliation(self, trading_env) -> None:
        performance = query(operation="demo_performance", view="full")
        assert performance["result"] == {
            "confirmed_demo_actions": [],
            "count": 0,
        }
        reconciliation = query(
            operation="reconciliation_report", view="full"
        )
        assert reconciliation["result"] == {
            "reconciliations": [],
            "offset": 0,
        }


def companion_action(**payload: Any) -> dict:
    from pydantic import TypeAdapter
    from soma.gateway_models import TradingCompanionActionRequest

    request = TypeAdapter(TradingCompanionActionRequest).validate_python(payload)
    return server.trading_companion_action(request)


class TestCompanionCycle:
    def fresh_provider(self, monkeypatch) -> FakeProvider:
        provider = FakeProvider(now=datetime.now(UTC))
        monkeypatch.setattr(server, "_configured_mt5_provider", lambda: provider)
        monkeypatch.setattr(
            trading_lab_adapter,
            "configured_mt5_provider",
            lambda _config: provider,
        )
        return provider

    def start(self, monkeypatch, key: str) -> dict:
        self.fresh_provider(monkeypatch)
        return companion_action(
            action="start",
            idempotency_key=key,
            task_invocation_id=f"task-{key}",
            research_summary="Public research found no integrity blocker.",
            research_sources=[
                {
                    "title": "Research source",
                    "reference": "https://example.test/research",
                    "published_at_utc": datetime.now(UTC).isoformat(),
                }
            ],
            scheduled_for_utc=datetime.now(UTC).isoformat(),
            completed_count=100,
            view="full",
        )

    def test_no_order_dry_cycle(self, monkeypatch, trading_env) -> None:
        started = self.start(monkeypatch, "dry-cycle")
        assert started["ok"] is True
        cycle_id = started["run"]["companion_run_id"]

        decided = companion_action(
            action="decide",
            companion_run_id=cycle_id,
            signal_idempotency_key="dry-signal",
            decision="NO_TRADE",
            reason="No setup survived the model review threshold.",
            model_version="gpt-test",
            prompt_version="decision-v1",
            view="full",
        )
        assert decided["ok"] is True
        assert decided["run"]["status"] == "NO_TRADE"
        assert decided["signal"]["decision"] == "NO_TRADE"

        fetched = query(
            operation="companion_get",
            companion_run_id=cycle_id,
            view="full",
        )
        assert fetched["result"]["status"] == "NO_TRADE"
        assert fetched["result"]["action_id"] is None
        listed = query(operation="companion_list", view="full")
        assert listed["result"]["total"] == 1
        assert listed["result"]["runs"][0]["companion_run_id"] == cycle_id

    def test_model_review_gates_internal_paper_execution(
        self, monkeypatch, trading_env
    ) -> None:
        started = self.start(monkeypatch, "paper-cycle")
        cycle_id = started["run"]["companion_run_id"]
        decided = companion_action(
            action="decide",
            companion_run_id=cycle_id,
            signal_idempotency_key="paper-signal",
            decision="LONG",
            confidence=73,
            stop_loss=63_000.0,
            take_profit=65_000.0,
            reason="Deterministic gateway integration setup.",
            news_context="No contradictory fixture event.",
            model_version="gpt-test",
            prompt_version="decision-v1",
            policy_id="hourly_fixed_bracket_v1",
            execution_mode="internal_paper",
            experiment_id="companion-gateway",
            view="full",
        )
        assert decided["run"]["status"] == "MODEL_REVIEW_PENDING"

        blocked = companion_action(
            action="execute",
            companion_run_id=cycle_id,
            idempotency_key="paper-action",
            volume_lots=0.01,
            view="full",
        )
        assert blocked["ok"] is False
        assert blocked["status"] == "companion_error"
        assert "model approval is required" in blocked["error"]

        reviewed = companion_action(
            action="review",
            companion_run_id=cycle_id,
            approval_idempotency_key="paper-review",
            decision="APPROVED",
            reason="Second pass confirms packet, bracket, and policy binding.",
            model_version="gpt-test",
            prompt_version="review-v1",
            view="full",
        )
        assert reviewed["run"]["status"] == "MODEL_APPROVED"
        assert reviewed["run"]["approval_signal_hash"] == reviewed["signal"]["content_hash"]

        executed = companion_action(
            action="execute",
            companion_run_id=cycle_id,
            idempotency_key="paper-action",
            volume_lots=0.01,
            view="full",
        )
        assert executed["ok"] is True
        assert executed["run"]["status"] == "ACTION_RECONCILED"
        assert executed["trading_action"]["execution_mode"] == "internal_paper"
        assert executed["trading_action"]["symbol"] == SYMBOL
        assert executed["trading_action"]["signal_id"] == decided["signal"]["signal_id"]
        assert executed["trading_action"]["stop_loss"] == 63_000.0
        assert executed["trading_action"]["take_profit"] == 65_000.0

    def test_companion_operation_inventory_is_complete(self) -> None:
        assert set(COMPANION_OPERATIONS) == {
            "companion_start",
            "companion_decide",
            "companion_approve",
            "companion_execute",
        }
        assert callable(server.trading_companion_action)


# --------------------------------------------------------------------------
# Signals.
# --------------------------------------------------------------------------


def submit_signal(packet_id: str, **overrides: Any) -> dict:
    from soma.gateway_models import TradingSignalSubmitRequest

    payload: dict[str, Any] = dict(
        idempotency_key="key-1",
        packet_id=packet_id,
        decision="LONG",
        confidence=73,
        stop_loss=63_400.0,
        take_profit=65_400.0,
        reason="gateway test",
        model_version="model-1",
        prompt_version="prompt-1",
    )
    payload.update(overrides)
    return server.trading_signal_submit(
        TradingSignalSubmitRequest(**payload)
    )


class TestSignalGateways:
    def test_submit_get_list_cancel(self, trading_env) -> None:
        from soma.gateway_models import (
            TradingSignalCancelRequest,
            TradingSignalGetRequest,
            TradingSignalListRequest,
        )

        config, provider, _tmp = trading_env
        packet_id = stored_packet(config, provider)

        submitted = submit_signal(packet_id, view="full")
        assert submitted["ok"] is True
        signal_id = submitted["signal"]["signal_id"]
        assert submitted["signal"]["status"] == "submitted"

        fetched = server.trading_signal_get(
            TradingSignalGetRequest(signal_id=signal_id, view="full")
        )
        assert fetched["signal"]["signal_id"] == signal_id

        listed = server.trading_signal_list(
            TradingSignalListRequest(view="full")
        )
        assert listed["total"] == 1
        assert listed["offset"] == 0

        cancelled = server.trading_signal_cancel_before_entry(
            TradingSignalCancelRequest(
                signal_id=signal_id, reason="withdrawn", view="full"
            )
        )
        assert cancelled["signal"]["status"] == "cancelled"

    def test_submission_is_idempotent(self, trading_env) -> None:
        config, provider, _tmp = trading_env
        packet_id = stored_packet(config, provider)
        first = submit_signal(packet_id, view="full")
        second = submit_signal(packet_id, view="full")
        assert first["signal"]["signal_id"] == second["signal"]["signal_id"]

    def test_rejection_is_reported_and_listed(self, trading_env) -> None:
        result = submit_signal("mp_missing")
        assert result["ok"] is False
        assert result["status"] == "rejected"
        assert result["rejection"]["rejection_id"].startswith("sigrej_")
        assert "does not reference a stored market packet" in (
            result["rejection"]["rejection_reason"]
        )

        listed = query(operation="rejection_list", view="full")
        assert len(listed["result"]["rejections"]) == 1

    def test_compact_signal_truncates_narrative_fields(
        self, trading_env
    ) -> None:
        """Unchanged pre-migration behavior: the compact projection caps the
        two narrative fields at 512 characters and then shrinks them until
        only the immutable record floor remains."""
        config, provider, _tmp = trading_env
        packet_id = stored_packet(config, provider)
        full = submit_signal(
            packet_id,
            reason="R" * 3_000,
            news_context="N" * 3_000,
            view="full",
        )
        assert len(full["signal"]["reason"]) == 3_000

        compact = submit_signal(
            packet_id,
            reason="R" * 3_000,
            news_context="N" * 3_000,
            response_budget_bytes=1024,
        )
        assert compact["truncated"] is True
        assert compact["has_more"] is True
        assert compact["response_budget_bytes"] == 1024
        assert compact["signal"]["reason"] == ""
        assert compact["signal"]["news_context"] == ""
        assert compact["response_bytes"] < response_size(full)

    def test_signal_list_filters(self, trading_env) -> None:
        from soma.gateway_models import TradingSignalListRequest

        config, provider, _tmp = trading_env
        packet_id = stored_packet(config, provider)
        submit_signal(packet_id)

        matching = server.trading_signal_list(
            TradingSignalListRequest(status="submitted", view="full")
        )
        assert matching["total"] == 1

        other = server.trading_signal_list(
            TradingSignalListRequest(status="entered", view="full")
        )
        assert other["total"] == 0

    def test_signal_list_budget(self, trading_env) -> None:
        from soma.gateway_models import TradingSignalListRequest

        config, provider, _tmp = trading_env
        packet_id = stored_packet(config, provider)
        for index in range(5):
            submit_signal(
                packet_id,
                idempotency_key=f"key-{index}",
                reason="R" * 500,
            )
        result = server.trading_signal_list(
            TradingSignalListRequest(response_budget_bytes=1024)
        )
        assert result["response_bytes"] <= 1024
        assert result["truncated"] is True
        assert result["has_more"] is True

    def test_signal_operations_are_all_exercised(self) -> None:
        """The completeness gate for the signal surface."""
        assert set(SIGNAL_OPERATIONS) == {
            "signal_submit",
            "signal_get",
            "signal_list",
            "signal_cancel_before_entry",
        }
        for operation in SIGNAL_OPERATIONS:
            tool = f"trading_{operation}"
            if operation == "signal_cancel_before_entry":
                tool = "trading_signal_cancel_before_entry"
            assert callable(getattr(server, tool)), operation


# --------------------------------------------------------------------------
# Actions.
# --------------------------------------------------------------------------


def submit_action(**overrides: Any) -> dict:
    from soma.gateway_models import TradingActionSubmitRequest

    payload: dict[str, Any] = dict(
        idempotency_key="act-1",
        action_type="market_entry",
        capability_role="internal_paper_agent",
        execution_mode="internal_paper",
        policy_id="agentic_demo_v1",
        symbol=SYMBOL,
        direction="LONG",
        volume_lots=0.01,
        stop_loss=63_000.0,
        take_profit=65_000.0,
        view="full",
    )
    payload.update(overrides)
    return server.trading_action_submit(
        TradingActionSubmitRequest(**payload)
    )


class TestActionGateway:
    def test_market_entry_is_recorded(self, trading_env) -> None:
        result = submit_action()
        assert result["ok"] is True
        assert result["action"]["action_type"] == "market_entry"
        assert result["action"]["state"] in (
            "RECONCILED",
            "BROKER_CONFIRMED",
        )

        listed = query(operation="action_list", view="full")
        assert listed["result"]["total"] == 1

        fetched = query(
            operation="action_get",
            action_id=result["action"]["action_id"],
            view="full",
        )
        assert fetched["result"]["action_id"] == result["action"]["action_id"]

    def test_action_is_idempotent(self, trading_env) -> None:
        first = submit_action()
        second = submit_action()
        assert first["action"]["action_id"] == second["action"]["action_id"]
        assert query(operation="action_list", view="full")["result"][
            "total"
        ] == 1

    @pytest.mark.parametrize("action_type", sorted(ACTION_OPERATIONS))
    def test_every_action_operation_reaches_the_gateway(
        self, trading_env, action_type: str
    ) -> None:
        """The completeness gate: every ActionType is accepted, validated,
        and durably recorded with a terminal state and no crash."""
        result = submit_action(
            idempotency_key=f"sweep-{action_type}",
            action_type=action_type,
        )
        assert "action" in result, result
        record = result["action"]
        assert record["action_type"] == action_type
        assert record["state"] in {
            "REQUESTED",
            "VALIDATED",
            "REJECTED",
            "SUBMITTING",
            "SUBMITTED",
            "BROKER_CONFIRMED",
            "FAILED",
            "RECONCILED",
        }
        assert record["origin"] == "model"

    def test_policy_refusal_is_surfaced(self, trading_env) -> None:
        result = submit_action(
            idempotency_key="policy-refusal",
            action_type="reverse",
            policy_id="hourly_fixed_bracket_v1",
        )
        assert result["ok"] is False
        assert result["action"]["state"] == "REJECTED"
        assert result["action"]["action_type"] == "reverse"
        # The refusal is durable: it is queryable after the fact.
        stored = query(
            operation="action_get",
            action_id=result["action"]["action_id"],
            view="full",
        )
        assert stored["result"]["state"] == "REJECTED"

    def test_research_collector_may_not_act(self, trading_env) -> None:
        """A paper role may not act on the broker.

        The refusal now happens at the request schema rather than inside
        the gateway: the pair is structurally contradictory, so it is
        rejected before anything reaches a provider or a journal.
        """
        from pydantic import ValidationError
        from soma.gateway_models import TradingActionSubmitRequest

        with pytest.raises(ValidationError, match="contradicts"):
            TradingActionSubmitRequest(
                idempotency_key="role-refusal",
                action_type="market_entry",
                capability_role="internal_paper_agent",
                execution_mode="broker_demo",
            )

    def test_broker_demo_requires_a_connected_provider(
        self, monkeypatch, trading_env
    ) -> None:
        result = submit_action(
            idempotency_key="demo-mode",
            capability_role="broker_demo_agent",
            execution_mode="broker_demo",
        )
        # The fake provider has no binding, so the gateway must classify
        # rather than crash.
        assert result["ok"] is False
        assert result["status"] == "gateway_error" or result["action"]

    def test_compact_action_response_carries_the_budget_envelope(
        self, trading_env
    ) -> None:
        """Unchanged pre-migration behavior: the scalar bounder shrinks a
        ``result`` payload, and an action response carries an ``action``
        payload instead, so it reports the budget and its own size without
        being reducible below the record floor."""
        result = submit_action(
            idempotency_key="compact",
            view="compact",
            response_budget_bytes=1024,
        )
        assert result["response_budget_bytes"] == 1024
        assert result["response_bytes"] == len(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key
                    not in {
                        "response_bytes",
                        "server_build_hash",
                        "schema_hash",
                        "capability_epoch",
                    }
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )
        assert result["view"] == "compact"


# --------------------------------------------------------------------------
# Runtime control.
# --------------------------------------------------------------------------


def runtime_control(**overrides: Any) -> dict:
    from soma.gateway_models import TradingRuntimeControlRequest

    payload: dict[str, Any] = {"action": "status", "view": "full"}
    payload.update(overrides)
    return server.trading_runtime_control(
        TradingRuntimeControlRequest(**payload)
    )


class TestRuntimeControl:
    def test_start_status_stop(self, trading_env) -> None:
        started = runtime_control(action="start")
        assert started["ok"] is True
        assert started["result"]["state"] == "running"

        status = runtime_control(action="status")
        assert status["result"]["status"]["state"] == "running"
        assert status["result"]["kill_switch"]["active"] is False

        stopped = runtime_control(action="stop", reason="done")
        assert stopped["result"]["state"] == "stopped"

    def test_kill_switch(self, trading_env) -> None:
        on = runtime_control(action="kill_switch_on", reason="halt")
        assert on["result"]["active"] is True

        status = runtime_control(action="status")
        assert status["result"]["kill_switch"]["active"] is True

        off = runtime_control(action="kill_switch_off", reason="resume")
        assert off["result"]["active"] is False

    def test_stop_requires_a_reason(self, trading_env) -> None:
        from soma.gateway_models import TradingRuntimeControlRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TradingRuntimeControlRequest(action="stop")

    def test_manual_passes_check_the_provider(self, trading_env) -> None:
        for action in ("supervise_now", "analyze_now"):
            result = runtime_control(action=action)
            # The fake provider is connected and demo, so the pass runs and
            # reports rather than being refused on environment grounds.
            assert result["ok"] is True or result["status"] == "runtime_error"

    def test_manual_pass_refuses_a_disconnected_terminal(
        self, monkeypatch, trading_env
    ) -> None:
        provider = FakeProvider(connected=False)
        monkeypatch.setattr(
            server, "_configured_mt5_provider", lambda: provider
        )
        result = runtime_control(action="supervise_now")
        assert result["ok"] is False
        assert result["status"] == "disconnected"
        assert result["health"]["login"] == "[redacted]"

    def test_manual_pass_refuses_a_real_account(
        self, monkeypatch, trading_env
    ) -> None:
        provider = FakeProvider(environment="real")
        monkeypatch.setattr(
            server, "_configured_mt5_provider", lambda: provider
        )
        result = runtime_control(action="analyze_now")
        assert result["ok"] is False
        assert result["status"] == "wrong_environment"

    @pytest.mark.parametrize(
        "action", sorted(RUNTIME_CONTROL_OPERATIONS)
    )
    def test_every_runtime_action_is_accepted(
        self, trading_env, action: str
    ) -> None:
        """The completeness gate for runtime control."""
        result = runtime_control(action=action, reason="completeness gate")
        assert "ok" in result
        assert isinstance(result, dict)


# --------------------------------------------------------------------------
# Public contract invariants that must survive the migration.
# --------------------------------------------------------------------------


class TestPublicContractUnchanged:
    def test_tool_names_are_unchanged(self) -> None:
        for name in (
            "trading_query",
            "trading_signal_submit",
            "trading_signal_get",
            "trading_signal_list",
            "trading_signal_cancel_before_entry",
            "trading_companion_action",
            "trading_action_submit",
            "trading_runtime_control",
        ):
            assert callable(getattr(server, name)), name

    def test_query_operation_inventory_is_unchanged(self) -> None:
        from soma.gateway_models import TradingQueryRequest
        from typing import get_args

        operations: set[str] = set()
        for model in get_args(get_args(TradingQueryRequest)[0]):
            annotation = model.model_fields["operation"].annotation
            operations.update(get_args(annotation))
        from soma.trading_lab_adapter import EXPOSURE_READ_OPERATIONS

        package_operations = (
            set(READ_OPERATIONS)
            | set(EXPOSURE_READ_OPERATIONS)
            | set(JOURNAL_QUERY_OPERATIONS)
            | set(DEPRECATED_QUERY_OPERATIONS)
        )
        # Every operation the package declares is served, and the only
        # host-added read is `configuration`: what Soma resolved from its
        # own configuration is a question the trading domain does not own,
        # so it has no operation for it. Naming it here keeps the gateway
        # from quietly growing a second inventory.
        assert package_operations <= operations
        assert operations - package_operations == {"configuration"}

    def test_action_inventory_matches_the_public_schema(self) -> None:
        from soma.gateway_models import TradingActionSubmitRequest
        from typing import get_args

        annotation = TradingActionSubmitRequest.model_fields[
            "action_type"
        ].annotation
        assert set(get_args(annotation)) == set(ACTION_OPERATIONS)

    def test_runtime_inventory_matches_the_public_schema(self) -> None:
        from soma.gateway_models import TradingRuntimeControlRequest
        from typing import get_args

        annotation = TradingRuntimeControlRequest.model_fields[
            "action"
        ].annotation
        assert set(get_args(annotation)) == set(RUNTIME_CONTROL_OPERATIONS)

    def test_compact_responses_carry_the_projection_envelope(
        self, trading_env
    ) -> None:
        result = query(operation="health")
        for key in (
            "view",
            "projection_version",
            "non_authoritative",
            "notice",
        ):
            assert key in result, key

    def test_every_response_is_json_serializable(self, trading_env) -> None:
        """Whatever the domain returns must survive the transport."""
        for result in (
            query(operation="health"),
            query(operation="runtime_status"),
            query(operation="action_list"),
            runtime_control(action="status"),
            submit_action(idempotency_key="serializable"),
        ):
            encoded = json.dumps(result, ensure_ascii=False)
            assert json.loads(encoded) == result


def _field_maximum(model, field: str) -> int:
    """The declared upper bound of a bounded integer field."""
    for item in model.model_fields[field].metadata:
        maximum = getattr(item, 'le', None)
        if maximum is not None:
            return int(maximum)
    raise AssertionError(f'{model.__name__}.{field} declares no upper bound')


# --------------------------------------------------------------------------
# Effective configuration, configuration-resolved defaults, and the
# runtime-control capability switch.
# --------------------------------------------------------------------------


def trading_query(**payload: Any) -> dict:
    from pydantic import TypeAdapter
    from soma.gateway_models import TradingQueryRequest

    request = TypeAdapter(TradingQueryRequest).validate_python(payload)
    return server.trading_query(request)


def reconfigure(tmp_path: Path, **trading: Any) -> AppConfig:
    """Rebuild the active config so a changed setting is genuinely active."""
    settings: dict[str, Any] = {
        "enabled": True,
        "symbol": SYMBOL,
        "provider_utc_offset_seconds": OFFSET,
        "maximum_tick_age_seconds": 120,
    }
    settings.update(trading)
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        trading=settings,
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    trading_lab_adapter.reset_services_cache()
    return config


class TestEffectiveConfigurationRead:
    def test_configuration_reports_resolved_runtime_settings(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        # "1h" is a caller alias; the domain owns the canonical name.
        reconfigure(
            tmp_path,
            timeframe="1h",
            candle_count=321,
            boundary_probe_bars=7,
            session_calendar="continuous",
        )

        result = trading_query(operation="configuration", view="full")["result"]

        assert result["symbol"] == SYMBOL
        assert result["enabled"] is True
        assert result["timeframe"] == "H1"
        assert result["timeframe_seconds"] == H1
        assert result["candle_count"] == 321
        assert result["boundary_probe_bars"] == 7
        assert result["session_calendar"] == "continuous"
        assert result["maximum_tick_age_seconds"] == 120
        assert result["provider_utc_offset_seconds"] == OFFSET
        assert result["account_environment"] == "demo"
        assert result["configured_account_environment"] == "demo"
        assert result["default_execution_mode"] == "internal_paper"
        assert result["default_policy_id"] == "agentic_demo_v1"
        assert result["runtime_control_mutations_enabled"] is True
        assert "H1" in result["supported_timeframes"]
        assert "continuous" in result["supported_session_calendars"]

    def test_configuration_answers_the_complete_scheduled_read(
        self, trading_env
    ) -> None:
        """Every value a scheduled controller must not guess, in one call."""
        result = trading_query(operation="configuration", view="full")["result"]

        required = {
            "symbol",
            "account_environment",
            "timeframe",
            "timeframe_seconds",
            "candle_count",
            "session_calendar",
            "boundary_probe_bars",
            "maximum_tick_age_seconds",
            "provider_utc_offset_seconds",
            "enabled",
        }
        assert required <= set(result)
        assert not any(
            value == "" for key, value in result.items() if key in required
        )

    def test_configuration_survives_a_disconnected_terminal(
        self, monkeypatch, trading_env
    ) -> None:
        """A controller needs its configuration most when the feed is down."""

        def unreachable() -> FakeProvider:
            raise RuntimeError("MT5 terminal is not running")

        monkeypatch.setattr(server, "_configured_mt5_provider", unreachable)

        response = trading_query(operation="configuration", view="full")

        assert response["ok"] is True
        assert response["result"]["timeframe"] == "H1"
        assert response["result"]["account_environment"] == ""
        assert "not running" in response["result"]["account_environment_error"]

    def test_configuration_carries_no_local_path_or_secret(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, terminal_path="C:/Program Files/MT5/terminal64.exe")

        encoded = json.dumps(trading_query(operation="configuration", view="full"))

        assert "terminal64" not in encoded
        assert "terminal_path" not in encoded

    def test_configuration_is_refused_when_trading_is_disabled(
        self, disabled_env
    ) -> None:
        assert trading_query(operation="configuration")["status"] == "disabled"

    def test_compact_configuration_stays_within_its_budget(
        self, trading_env
    ) -> None:
        response = trading_query(
            operation="configuration", response_budget_bytes=4096
        )
        assert response_size(response) <= 4096


class TestConfigurationResolvedDefaults:
    def test_omitted_candle_count_follows_the_active_configuration(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, candle_count=17)

        candles = trading_query(operation="candles", view="full")
        assert len(candles["result"]["completed"]) == 17

        # Changing configuration must move the default with it: a literal
        # baked into the request model would silently keep the old depth.
        reconfigure(tmp_path, candle_count=23)
        later = trading_query(operation="candles", view="full")
        assert len(later["result"]["completed"]) == 23

    def test_omitted_historical_count_follows_the_active_configuration(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, candle_count=29)

        window = trading_query(operation="historical_candles", view="full")

        assert window["result"]["requested_count"] == 29
        assert len(window["result"]["candles"]) == 29

    def test_omitted_probe_bars_follows_the_active_configuration(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, boundary_probe_bars=5)

        boundary = trading_query(operation="candle_boundary", view="full")

        assert boundary["result"]["probe_bar_count"] == 5

    def test_an_explicit_count_still_overrides_the_configuration(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, candle_count=40)

        candles = trading_query(operation="candles", completed_count=3, view="full")

        assert len(candles["result"]["completed"]) == 3

    def test_public_candle_range_accepts_every_configurable_depth(self) -> None:
        """No configured depth may be unreachable through the public schema."""
        from soma.config import TradingConfig
        from soma.gateway_models import (
            TradingCandlesQuery,
            TradingHistoricalCandlesQuery,
        )

        configured_maximum = _field_maximum(TradingConfig, "candle_count")
        for model, field in (
            (TradingCandlesQuery, "completed_count"),
            (TradingHistoricalCandlesQuery, "count"),
        ):
            assert _field_maximum(model, field) >= configured_maximum, model.__name__

    def test_companion_start_uses_the_configured_analysis_depth(
        self, monkeypatch, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, candle_count=31)
        provider = FakeProvider(now=datetime.now(UTC))
        monkeypatch.setattr(server, "_configured_mt5_provider", lambda: provider)
        monkeypatch.setattr(
            trading_lab_adapter, "configured_mt5_provider", lambda _config: provider
        )

        started = companion_action(
            action="start",
            idempotency_key="configured-depth",
            task_invocation_id="task-configured-depth",
            research_summary="Configured analysis depth is used.",
            scheduled_for_utc=datetime.now(UTC).isoformat(),
            view="full",
        )

        assert started["ok"] is True
        assert len(started["packet"]["payload"]["completed_candles"]) == 31


class TestConfiguredExecutionModeAndPolicy:
    def _started_cycle(self, monkeypatch, key: str) -> dict:
        provider = FakeProvider(now=datetime.now(UTC))
        monkeypatch.setattr(server, "_configured_mt5_provider", lambda: provider)
        monkeypatch.setattr(
            trading_lab_adapter, "configured_mt5_provider", lambda _config: provider
        )
        return companion_action(
            action="start",
            idempotency_key=key,
            task_invocation_id=f"task-{key}",
            research_summary="Configured mode reaches the immutable decision.",
            scheduled_for_utc=datetime.now(UTC).isoformat(),
            completed_count=100,
            view="full",
        )

    def test_decision_stores_the_configured_mode_and_policy(
        self, monkeypatch, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(
            tmp_path,
            default_execution_mode="broker_demo",
            default_policy_id="agentic_demo_v1",
        )
        started = self._started_cycle(monkeypatch, "broker-mode")

        decided = companion_action(
            action="decide",
            companion_run_id=started["run"]["companion_run_id"],
            signal_idempotency_key="broker-mode-signal",
            decision="LONG",
            confidence=70,
            stop_loss=63_000.0,
            take_profit=66_000.0,
            reason="Configured mode must reach the immutable decision.",
            model_version="gpt-test",
            prompt_version="decision-v1",
            view="full",
        )

        # The mode and policy live on the immutable signal, which is what
        # companion execute reads back when it chooses an executor and role.
        assert decided["signal"]["execution_mode"] == "broker_demo"
        assert decided["signal"]["policy_id"] == "agentic_demo_v1"

    def test_an_explicit_request_still_overrides_the_configuration(
        self, monkeypatch, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, default_execution_mode="broker_demo")
        started = self._started_cycle(monkeypatch, "explicit-mode")

        decided = companion_action(
            action="decide",
            companion_run_id=started["run"]["companion_run_id"],
            signal_idempotency_key="explicit-mode-signal",
            decision="NO_TRADE",
            reason="Explicit paper mode overrides configuration.",
            model_version="gpt-test",
            prompt_version="decision-v1",
            execution_mode="internal_paper",
            view="full",
        )

        assert decided["signal"]["execution_mode"] == "internal_paper"

    def test_guarded_action_inherits_the_configured_mode_and_role(
        self, monkeypatch, trading_env
    ) -> None:
        """Broker-demo configuration reaches the executor and the role.

        The fake provider carries no broker binding, so what is asserted
        here is the routing decision itself: which mode the gateway
        resolved and which executor it therefore asked for.
        """
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, default_execution_mode="broker_demo")
        selected: list[str] = []
        original = server._trading_executor_for_mode

        def record(mode: str, provider: Any):
            selected.append(mode)
            return original(mode, provider)

        monkeypatch.setattr(server, "_trading_executor_for_mode", record)

        submit_action(
            idempotency_key="configured-role",
            capability_role=None,
            execution_mode=None,
            policy_id=None,
        )

        assert selected == ["broker_demo"]
        assert server._resolved_trading_execution_mode(None) == "broker_demo"
        assert server._resolved_trading_policy_id(None) == "agentic_demo_v1"
        assert (
            server._resolved_trading_capability_role(None, "broker_demo")
            == "broker_demo_agent"
        )

    def test_paper_configuration_derives_the_paper_role(self, trading_env) -> None:
        result = submit_action(
            idempotency_key="paper-role",
            capability_role=None,
            execution_mode=None,
            policy_id=None,
        )

        assert result["action"]["execution_mode"] == "internal_paper"
        assert result["action"]["capability_role"] == "internal_paper_agent"

    def test_a_contradictory_role_and_mode_are_refused(self) -> None:
        """Guessing which one was meant would decide where a real order goes."""
        from pydantic import ValidationError
        from soma.gateway_models import TradingActionSubmitRequest

        with pytest.raises(ValidationError, match="contradicts"):
            TradingActionSubmitRequest(
                idempotency_key="contradiction",
                action_type="market_entry",
                capability_role="internal_paper_agent",
                execution_mode="broker_demo",
            )


class TestRuntimeControlCapabilitySwitch:
    def test_mutations_are_unavailable_when_configuration_disables_them(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, runtime_control_mutations_enabled=False)

        for action, extra in (
            ("start", {}),
            ("stop", {"reason": "halt"}),
            ("kill_switch_on", {"reason": "halt"}),
            ("kill_switch_off", {"reason": "resume"}),
            ("supervise_now", {}),
            ("analyze_now", {}),
        ):
            result = runtime_control(action=action, **extra)
            assert result["ok"] is False, action
            assert result["status"] == "runtime_control_disabled", action
            assert result["available_actions"] == ["status"], action

    def test_runtime_status_remains_readable_when_mutations_are_disabled(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, runtime_control_mutations_enabled=False)

        status = runtime_control(action="status")

        assert status["ok"] is True
        # A stopped runtime is a valid observation, not a repair request.
        assert status["result"]["status"]["state"] == "stopped"
        assert status["result"]["kill_switch"]["active"] is False

    def test_a_disabled_switch_never_changes_runtime_state(
        self, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, runtime_control_mutations_enabled=False)

        runtime_control(action="start")
        runtime_control(action="kill_switch_on", reason="halt")

        status = runtime_control(action="status")
        assert status["result"]["status"]["state"] == "stopped"
        assert status["result"]["kill_switch"]["active"] is False

    def test_mutations_remain_available_by_default(self, trading_env) -> None:
        assert runtime_control(action="start")["ok"] is True
        assert runtime_control(action="stop", reason="done")["ok"] is True

    def test_configuration_reports_the_switch(self, trading_env) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, runtime_control_mutations_enabled=False)

        result = trading_query(operation="configuration", view="full")["result"]

        assert result["runtime_control_mutations_enabled"] is False


# --------------------------------------------------------------------------
# The live execution book.
# --------------------------------------------------------------------------


class FakeExposureExecutor:
    """An execution backend that reports a book without touching MT5."""

    def __init__(self, positions=(), orders=(), *, mode: str = "broker_demo") -> None:
        self._positions = tuple(positions)
        self._orders = tuple(orders)
        self._mode = mode
        self.calls: list[str | None] = []

    def exposure(self, symbol: str | None = None):
        from trading_lab.provider_models import BrokerExposure

        self.calls.append(symbol)
        positions = tuple(
            item for item in self._positions if symbol is None or item.symbol == symbol
        )
        orders = tuple(
            item for item in self._orders if symbol is None or item.symbol == symbol
        )
        return BrokerExposure(
            mode=self._mode,
            account_environment="demo" if self._mode == "broker_demo" else "internal_paper",
            symbol_filter=symbol,
            positions=positions,
            pending_orders=orders,
            observed_at_utc=datetime.now(UTC),
            complete=symbol is None,
        )


def open_position(ticket: int, **overrides):
    from trading_lab.provider_models import OpenPosition

    payload = {
        "ticket": ticket,
        "symbol": SYMBOL,
        "direction": "LONG",
        "volume_lots": 0.01,
        "entry_price": 64_000.0,
        "stop_loss": 63_000.0,
        "take_profit": 65_000.0,
        "current_price": 64_100.0,
        "unrealized_profit": 1.0,
    }
    payload.update(overrides)
    return OpenPosition(**payload)


def pending_order(ticket: int, **overrides):
    from trading_lab.provider_models import PendingOrder

    payload = {
        "ticket": ticket,
        "symbol": SYMBOL,
        "direction": "LONG",
        "volume_lots": 0.02,
        "price": 62_000.0,
        "order_kind": "buy_limit",
        "stop_loss": None,
        "take_profit": None,
    }
    payload.update(overrides)
    return PendingOrder(**payload)


def use_exposure_executor(monkeypatch, executor: FakeExposureExecutor) -> None:
    monkeypatch.setattr(
        server, "_trading_executor_for_mode", lambda _mode, _provider: executor
    )


class TestBrokerExposureRead:
    def test_open_positions_are_returned_with_every_reviewable_field(
        self, monkeypatch, trading_env
    ) -> None:
        executor = FakeExposureExecutor(positions=[open_position(7001)])
        use_exposure_executor(monkeypatch, executor)

        result = trading_query(operation="broker_exposure", view="full")["result"]

        assert result["position_count"] == 1
        position = result["positions"][0]
        assert position["ticket"] == 7001
        assert position["direction"] == "LONG"
        assert position["volume_lots"] == 0.01
        assert position["entry_price"] == 64_000.0
        assert position["stop_loss"] == 63_000.0
        assert position["take_profit"] == 65_000.0
        assert position["current_price"] == 64_100.0
        assert position["protected"] is True

    def test_pending_orders_are_returned(self, monkeypatch, trading_env) -> None:
        executor = FakeExposureExecutor(orders=[pending_order(8001)])
        use_exposure_executor(monkeypatch, executor)

        result = trading_query(operation="broker_exposure", view="full")["result"]

        assert result["pending_order_count"] == 1
        assert result["pending_orders"][0]["ticket"] == 8001
        assert result["pending_orders"][0]["order_kind"] == "buy_limit"

    def test_the_read_derives_the_totals_a_supervisor_asks_for(
        self, monkeypatch, trading_env
    ) -> None:
        executor = FakeExposureExecutor(
            positions=[
                open_position(7001, volume_lots=0.05),
                open_position(7002, volume_lots=0.02, direction="SHORT"),
                open_position(7003, take_profit=None),
            ],
            orders=[pending_order(8001)],
        )
        use_exposure_executor(monkeypatch, executor)

        result = trading_query(operation="broker_exposure", view="full")["result"]

        assert result["flat"] is False
        assert result["position_count"] == 3
        assert result["pending_order_count"] == 1
        assert result["open_volume_lots"] == pytest.approx(0.08)
        assert result["net_volume_lots"] == pytest.approx(0.04)
        assert result["unprotected_position_tickets"] == [7003]

    def test_a_flat_account_is_reported_as_flat(
        self, monkeypatch, trading_env
    ) -> None:
        use_exposure_executor(monkeypatch, FakeExposureExecutor())

        result = trading_query(operation="broker_exposure", view="full")["result"]

        assert result["flat"] is True
        assert result["position_count"] == 0
        assert result["positions"] == []
        assert result["complete"] is True

    def test_a_symbol_scoped_read_is_marked_incomplete(
        self, monkeypatch, trading_env
    ) -> None:
        executor = FakeExposureExecutor(
            positions=[open_position(7001), open_position(7002, symbol="OTHER_i")]
        )
        use_exposure_executor(monkeypatch, executor)

        scoped = trading_query(
            operation="broker_exposure", symbol=SYMBOL, view="full"
        )["result"]

        assert executor.calls == [SYMBOL]
        assert scoped["symbol_filter"] == SYMBOL
        assert scoped["complete"] is False
        assert scoped["position_count"] == 1

    def test_the_answer_comes_from_the_backend_not_the_journal(
        self, monkeypatch, trading_env
    ) -> None:
        """A position with no action record must still be visible."""
        executor = FakeExposureExecutor(positions=[open_position(9999)])
        use_exposure_executor(monkeypatch, executor)

        result = trading_query(operation="broker_exposure", view="full")["result"]
        actions = trading_query(operation="action_list", view="full")["result"]

        assert [item["ticket"] for item in result["positions"]] == [9999]
        assert actions["actions"] == []
        assert result["exposure_authority"] == "execution_backend"

    def test_the_read_uses_the_configured_execution_mode(
        self, monkeypatch, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, default_execution_mode="broker_demo")
        selected: list[str] = []

        def record(mode: str, _provider):
            selected.append(mode)
            return FakeExposureExecutor()

        monkeypatch.setattr(server, "_trading_executor_for_mode", record)

        trading_query(operation="broker_exposure", view="full")

        assert selected == ["broker_demo"]

    def test_an_explicit_mode_overrides_the_configuration(
        self, monkeypatch, trading_env
    ) -> None:
        selected: list[str] = []

        def record(mode: str, _provider):
            selected.append(mode)
            return FakeExposureExecutor(mode=mode)

        monkeypatch.setattr(server, "_trading_executor_for_mode", record)

        trading_query(
            operation="broker_exposure", execution_mode="internal_paper", view="full"
        )

        assert selected == ["internal_paper"]

    def test_a_provider_failure_is_classified_not_swallowed(
        self, monkeypatch, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, default_execution_mode="broker_demo")

        def unreachable():
            raise RuntimeError("MT5 terminal is not running")

        monkeypatch.setattr(server, "_configured_mt5_provider", unreachable)

        response = trading_query(operation="broker_exposure")

        assert response["ok"] is False
        assert response["status"] == "provider_error"
        assert "not running" in response["error"]

    def test_a_non_demo_account_refuses_the_read(
        self, monkeypatch, trading_env
    ) -> None:
        _config, _provider, tmp_path = trading_env
        reconfigure(tmp_path, default_execution_mode="broker_demo")
        live = FakeProvider(environment="real")
        monkeypatch.setattr(server, "_configured_mt5_provider", lambda: live)

        response = trading_query(operation="broker_exposure")

        assert response["ok"] is False
        assert "demo" in response["error"]

    def test_the_read_is_refused_when_trading_is_disabled(
        self, disabled_env
    ) -> None:
        assert trading_query(operation="broker_exposure")["status"] == "disabled"

    def test_a_truncated_book_never_reads_as_flat(
        self, monkeypatch, trading_env
    ) -> None:
        """Trimming for a budget must not turn exposure into no exposure."""
        executor = FakeExposureExecutor(
            positions=[open_position(7000 + index) for index in range(40)],
            orders=[pending_order(8000 + index) for index in range(10)],
        )
        use_exposure_executor(monkeypatch, executor)

        response = trading_query(
            operation="broker_exposure", response_budget_bytes=4096
        )
        result = response["result"]

        assert response_size(response) <= 4096
        assert response["truncated"] is True
        assert response["has_more"] is True
        # The counts describe the book, not the trimmed list.
        assert result["position_count"] == 40
        assert result["pending_order_count"] == 10
        assert result["flat"] is False
        assert result["returned_position_count"] < 40
        assert len(result["unprotected_position_tickets"]) == 0

    def test_a_budget_below_the_floor_reports_honestly_rather_than_lying(
        self, monkeypatch, trading_env
    ) -> None:
        """The totals are the floor. Below it the response overruns.

        Trimming stops once only the envelope and the derived totals
        remain, so a caller that asks for an impossible budget gets an
        oversized truthful answer rather than a small false one.
        """
        executor = FakeExposureExecutor(
            positions=[open_position(7000 + index) for index in range(40)]
        )
        use_exposure_executor(monkeypatch, executor)

        response = trading_query(
            operation="broker_exposure", response_budget_bytes=1024
        )
        result = response["result"]

        assert response["truncated"] is True
        assert result["returned_position_count"] == 0
        assert result["position_count"] == 40
        assert result["flat"] is False

    def test_positions_are_trimmed_before_orders(
        self, monkeypatch, trading_env
    ) -> None:
        executor = FakeExposureExecutor(
            positions=[open_position(7000 + index) for index in range(30)],
            orders=[pending_order(8001)],
        )
        use_exposure_executor(monkeypatch, executor)

        result = trading_query(
            operation="broker_exposure", response_budget_bytes=2048
        )["result"]

        assert result["returned_pending_order_count"] == 1

    def test_the_full_view_preserves_the_complete_book(
        self, monkeypatch, trading_env
    ) -> None:
        executor = FakeExposureExecutor(
            positions=[open_position(7000 + index) for index in range(40)]
        )
        use_exposure_executor(monkeypatch, executor)

        result = trading_query(operation="broker_exposure", view="full")["result"]

        assert len(result["positions"]) == 40


class TestExposureInventoryContract:
    def test_the_operation_is_served_from_the_package_inventory(self) -> None:
        from soma.trading_lab_adapter import EXPOSURE_READ_OPERATIONS

        assert EXPOSURE_READ_OPERATIONS == ("broker_exposure",)
        assert server._TRADING_EXPOSURE_OPERATIONS == frozenset(
            EXPOSURE_READ_OPERATIONS
        )

    def test_the_exposure_read_is_not_a_market_data_read(self) -> None:
        from soma.trading_lab_adapter import EXPOSURE_READ_OPERATIONS

        assert not set(EXPOSURE_READ_OPERATIONS) & set(READ_OPERATIONS)
        assert not set(EXPOSURE_READ_OPERATIONS) & set(JOURNAL_QUERY_OPERATIONS)
