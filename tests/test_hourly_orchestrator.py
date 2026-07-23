from __future__ import annotations

from dataclasses import replace
from datetime import timezone
from pathlib import Path

from soma.trading.hourly_orchestrator import HourlyOrchestrator
from soma.trading.market_packet import MarketPacketBuilder
from soma.trading.signal_journal import SignalJournal
from soma.trading.trade_supervisor import TradingLabSupervisor
from soma.trading.virtual_position_journal import VirtualPositionJournal
from tests.test_market_packet import NOW as PACKET_NOW
from tests.test_market_packet import SYMBOL, PacketProvider
from tests.test_trade_supervisor import demo_health, draft

UTC = timezone.utc
CYCLE_NOW = PACKET_NOW


class OrchestratorProvider(PacketProvider):
    """Packet fixture provider extended with recovery-surface methods."""

    def __init__(self) -> None:
        super().__init__()
        self.historical: list = []

    def historical_ticks(self, _symbol, _start, _end):
        self.calls.append("historical_ticks")
        return list(self.historical)


def make_orchestrator(
    tmp_path: Path,
) -> tuple[HourlyOrchestrator, TradingLabSupervisor]:
    supervisor = TradingLabSupervisor(
        signal_journal=SignalJournal(tmp_path / "signals.sqlite3"),
        position_journal=VirtualPositionJournal(
            tmp_path / "positions.sqlite3"
        ),
    )
    supervisor.initialize_from_health(demo_health(), now=CYCLE_NOW)
    orchestrator = HourlyOrchestrator(
        supervisor=supervisor,
        packet_builder=MarketPacketBuilder(now=lambda: CYCLE_NOW),
    )
    return orchestrator, supervisor


def run(orchestrator, provider, *, enabled: bool = True):
    return orchestrator.run_cycle(
        provider,
        symbol=SYMBOL,
        enabled=enabled,
        now=CYCLE_NOW,
        completed_count=100,
    )


def test_cycle_enters_submitted_signal_and_monitors(tmp_path: Path) -> None:
    orchestrator, supervisor = make_orchestrator(tmp_path)
    provider = OrchestratorProvider()
    record = supervisor.signals.submit(
        "cycle-signal-1", draft(confidence=60)
    )

    report = run(orchestrator, provider)

    assert report.proceeded is True
    assert report.refusal_reason == ""
    assert report.packet_id is not None
    assert report.entered_signal_ids == (record.signal_id,)
    # Fixture tick bid 64000 is inside the 63000/66000 boundaries, so
    # the cycle's monitoring pass keeps all eleven positions open.
    assert report.resolved_position_ids == ()
    assert report.open_position_count == 11


def test_kill_switch_blocks_trades_but_still_monitors(
    tmp_path: Path,
) -> None:
    orchestrator, supervisor = make_orchestrator(tmp_path)
    provider = OrchestratorProvider()
    record = supervisor.signals.submit(
        "cycle-signal-1", draft(confidence=60)
    )
    run(orchestrator, provider)  # opens 11 positions

    # Boundary tick while the kill switch is on: no new entries, but the
    # existing open work is still monitored and resolved.
    supervisor.signals.submit("cycle-signal-2", draft(confidence=99))
    provider.tick = replace(provider.tick, bid=66_000.0, ask=66_064.0)
    disabled_report = run(orchestrator, provider, enabled=False)

    assert disabled_report.proceeded is False
    assert "kill switch" in disabled_report.refusal_reason
    assert disabled_report.entered_signal_ids == ()
    assert disabled_report.packet_id is None
    assert len(disabled_report.resolved_position_ids) == 11
    assert disabled_report.open_position_count == 0
    del record


def test_disconnected_terminal_generates_no_trade(tmp_path: Path) -> None:
    orchestrator, supervisor = make_orchestrator(tmp_path)
    provider = OrchestratorProvider()
    supervisor.signals.submit("cycle-signal-1", draft(confidence=60))

    health = provider.health()

    class Disconnected(OrchestratorProvider):
        def health(self):
            return replace(health, connected=False)

    report = run(orchestrator, Disconnected())
    assert report.proceeded is False
    assert report.refusal_reason == "terminal is disconnected"
    assert report.entered_signal_ids == ()
    assert report.open_position_count == 0


def test_stale_market_data_generates_no_trade(tmp_path: Path) -> None:
    orchestrator, supervisor = make_orchestrator(tmp_path)
    provider = OrchestratorProvider()
    provider.tick = replace(provider.tick, fresh=False)
    supervisor.signals.submit("cycle-signal-1", draft(confidence=60))

    report = run(orchestrator, provider)
    assert report.proceeded is False
    assert "validation failed" in report.refusal_reason or (
        report.refusal_reason == "market data is stale"
    )
    assert report.entered_signal_ids == ()
    assert report.open_position_count == 0


def test_no_trade_signal_is_never_forced(tmp_path: Path) -> None:
    from soma.trading.signal_journal import SignalDecision

    orchestrator, supervisor = make_orchestrator(tmp_path)
    provider = OrchestratorProvider()
    record = supervisor.signals.submit(
        "cycle-no-trade",
        draft(
            decision=SignalDecision.NO_TRADE,
            confidence=None,
            stop_loss=None,
            take_profit=None,
        ),
    )

    report = run(orchestrator, provider)
    assert report.proceeded is True
    assert report.entered_signal_ids == ()
    assert report.skipped_signal_ids == (record.signal_id,)
    assert report.open_position_count == 0
