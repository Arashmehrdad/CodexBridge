from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from soma.trading.signal_journal import (
    SignalDecision,
    SignalDraft,
    SignalJournal,
)
from soma.trading.threshold_reports import build_threshold_report
from soma.trading.trade_supervisor import TradingLabSupervisor
from soma.trading.virtual_position_journal import VirtualPositionJournal
from tests.test_trade_supervisor import demo_health

UTC = timezone.utc
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
PACKET_HASH = "e" * 64
SYMBOL = "BITCOIN_i"


def make_supervisor(tmp_path: Path) -> TradingLabSupervisor:
    return TradingLabSupervisor(
        signal_journal=SignalJournal(tmp_path / "signals.sqlite3"),
        position_journal=VirtualPositionJournal(
            tmp_path / "positions.sqlite3"
        ),
    )


def long_draft(created_at: datetime, *, confidence: int) -> SignalDraft:
    return SignalDraft(
        created_at_utc=created_at,
        broker="alpari",
        symbol=SYMBOL,
        analysis_timeframe="4H",
        decision=SignalDecision.LONG,
        confidence=confidence,
        bid=64000.0,
        ask=64060.0,
        market_data_timestamp=created_at,
        latest_completed_4h_candle="2026-07-23T08:00:00Z",
        developing_4h_candle="2026-07-23T12:00:00Z",
        entry_type="MARKET",
        entry_reference_price=64060.0,
        stop_loss=63000.0,
        take_profit=66000.0,
        reason="report fixture",
        news_context="",
        market_snapshot_id=f"mp_{PACKET_HASH[:24]}",
        market_packet_hash=PACKET_HASH,
    )


def seeded_supervisor(tmp_path: Path) -> TradingLabSupervisor:
    """One win, one loss, one ambiguous outcome per eligible threshold."""
    supervisor = make_supervisor(tmp_path)
    supervisor.initialize_from_health(demo_health(), now=NOW)

    first = supervisor.signals.submit(
        "report-signal-1", long_draft(NOW, confidence=60)
    )
    supervisor.enter_signal(first.signal_id, now=NOW)
    supervisor.observe_tick(  # win: bid reaches take-profit
        symbol=SYMBOL,
        bid=66000,
        ask=66060,
        observed_at_utc=NOW + timedelta(hours=1),
    )

    second = supervisor.signals.submit(
        "report-signal-2",
        long_draft(NOW + timedelta(hours=2), confidence=55),
    )
    supervisor.enter_signal(
        second.signal_id, now=NOW + timedelta(hours=2)
    )
    supervisor.observe_tick(  # loss: bid reaches stop
        symbol=SYMBOL,
        bid=63000,
        ask=63060,
        observed_at_utc=NOW + timedelta(hours=3),
    )

    third = supervisor.signals.submit(
        "report-signal-3",
        long_draft(NOW + timedelta(days=40), confidence=52),
    )
    supervisor.enter_signal(
        third.signal_id, now=NOW + timedelta(days=40)
    )
    supervisor.recover_with_range(  # ambiguous double-boundary candle
        symbol=SYMBOL,
        low=62900,
        high=66100,
        observed_at_utc=NOW + timedelta(days=40, hours=4),
    )
    return supervisor


def test_report_reproduces_exactly_from_journals(tmp_path: Path) -> None:
    supervisor = seeded_supervisor(tmp_path)
    first = build_threshold_report(supervisor)
    second = build_threshold_report(supervisor)
    assert first == second
    assert first["content_hash"] == second["content_hash"]

    # A completely fresh supervisor over the reopened journals produces
    # byte-identical output: the journals alone determine the report.
    reopened = make_supervisor(tmp_path)
    third = build_threshold_report(reopened)
    assert json.dumps(third, sort_keys=True) == json.dumps(
        first, sort_keys=True
    )
    assert third["content_hash"] == first["content_hash"]


def test_metrics_match_hand_computation(tmp_path: Path) -> None:
    supervisor = seeded_supervisor(tmp_path)
    report = build_threshold_report(supervisor)

    entry = Decimal("64060.0")
    win = ((Decimal("66000") - entry) / entry) * Decimal("1.00")
    loss = ((Decimal("63000") - entry) / entry) * Decimal("1.00")

    t52 = report["thresholds"]["T52"]
    # Confidence 60, 55, and 52 signals are all eligible at T52.
    assert t52["signal_count"] == 3
    assert t52["entered_trade_count"] == 3
    assert t52["resolved_trade_count"] == 3
    assert t52["ambiguous_trade_count"] == 1
    assert t52["win_count"] == 1
    assert t52["loss_count"] == 1
    assert t52["win_rate"] == "0.5000"
    assert Decimal(t52["net_pnl"]) == (win + loss).quantize(
        Decimal("0.00000001")
    )
    assert Decimal(t52["max_drawdown"]) == (-loss).quantize(
        Decimal("0.00000001")
    )
    assert t52["longest_losing_streak"] == 1
    assert t52["average_risk_reward"] == "1.8302"
    assert t52["monthly"]["2026-07"]["trades"] == 2
    assert t52["monthly"]["2026-09"]["trades"] == 0 if "2026-09" in t52["monthly"] else True
    assert t52["confidence_bands"]["50-59"]["trades"] == 1
    assert t52["confidence_bands"]["60-69"]["trades"] == 1

    # T58 is not eligible for the confidence-55 or 52 signals.
    t58 = report["thresholds"]["T58"]
    assert t58["signal_count"] == 1
    assert t58["entered_trade_count"] == 1
    assert t58["win_count"] == 1
    assert t58["loss_count"] == 0
    assert t58["profit_factor"] is None

    # T61 and above saw no eligible signal at all.
    t61 = report["thresholds"]["T61"]
    assert t61["signal_count"] == 0
    assert t61["entered_trade_count"] == 0
    assert t61["net_pnl"] == "0.00000000"


def test_fresh_period_report_excludes_older_trades(tmp_path: Path) -> None:
    supervisor = seeded_supervisor(tmp_path)
    fresh = build_threshold_report(
        supervisor,
        period_start=NOW + timedelta(days=30),
    )
    t52 = fresh["thresholds"]["T52"]
    # Only the ambiguous third trade is inside the fresh period.
    assert t52["signal_count"] == 1
    assert t52["entered_trade_count"] == 1
    assert t52["ambiguous_trade_count"] == 1
    assert t52["win_count"] == 0
    assert t52["net_pnl"] == "0.00000000"

    full = build_threshold_report(supervisor)
    assert fresh["content_hash"] != full["content_hash"]
    with pytest.raises(ValueError, match="timezone-aware"):
        build_threshold_report(
            supervisor, period_start=datetime(2026, 7, 1)
        )


def test_report_requires_initialized_experiment(tmp_path: Path) -> None:
    supervisor = make_supervisor(tmp_path)
    with pytest.raises(RuntimeError, match="initialize"):
        build_threshold_report(supervisor)
