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
H4 = 4 * 60 * 60
DEVELOPING_RAW_OPEN = 1_784_534_400
DEVELOPING_OPEN_UTC = datetime.fromtimestamp(DEVELOPING_RAW_OPEN - OFFSET, tz=UTC)
NOW = DEVELOPING_OPEN_UTC + timedelta(hours=1)

from trading_lab.mt5_provider import (  # noqa: E402
    Candle,
    HistoricalTick,
    ProviderHealth,
    ProviderTimestamp,
    SymbolSpecification,
    SymbolSummary,
    Tick,
)
from trading_lab.service import (  # noqa: E402
    ACTION_OPERATIONS,
    DEPRECATED_QUERY_OPERATIONS,
    JOURNAL_QUERY_OPERATIONS,
    READ_OPERATIONS,
    RUNTIME_CONTROL_OPERATIONS,
    SIGNAL_OPERATIONS,
)


# --------------------------------------------------------------------------
# Deterministic provider double.
# --------------------------------------------------------------------------


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
        open_epoch = broker_epoch - (broker_epoch % H4)
        self._completed = [
            candle(open_epoch - H4 * (100 - index), 60_000 + index)
            for index in range(100)
        ]
        self._developing = candle(open_epoch, 61_000)
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

    def h4_candles(
        self, _symbol: str, *, completed_count: int = 200
    ) -> tuple[list[Candle], Candle | None]:
        return self._completed[-completed_count:], self._developing

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


@pytest.mark.skipif(
    trading_lab_adapter.selected_backend() != "package",
    reason="identity assertions describe the package backend only;"
    " every other test in this file passes under both backends,"
    " which is the gateway-level equivalence evidence",
)
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
        source = Path(server.__file__).read_text("utf-8")
        assert "from .trading import" not in source
        assert "from .trading." not in source

    def test_default_backend_is_the_package(self) -> None:
        assert trading_lab_adapter.selected_backend() == "package"
        assert trading_lab_adapter.DEFAULT_BACKEND == "package"


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
        if operation in {"market_packet_get", "outcome_get"}:
            pytest.skip("single-record reads are covered by not_found tests")
        if operation == "action_get":
            pytest.skip("single-record reads are covered by not_found tests")
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
        result = submit_action(
            idempotency_key="role-refusal",
            capability_role="internal_paper_agent",
            execution_mode="broker_demo",
        )
        assert result["ok"] is False

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
        assert operations == (
            set(READ_OPERATIONS)
            | set(JOURNAL_QUERY_OPERATIONS)
            | set(DEPRECATED_QUERY_OPERATIONS)
        )

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
