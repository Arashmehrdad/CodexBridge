from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from soma.trading.mt5_provider import ProviderHealth
from soma.trading.signal_journal import (
    SignalDecision,
    SignalDraft,
    SignalJournal,
    SignalStatus,
)
from soma.trading.threshold_simulator import CohortTransition
from soma.trading.trade_supervisor import TradingLabSupervisor
from soma.trading.virtual_position_journal import (
    PositionStatus,
    VirtualPositionJournal,
)

UTC = timezone.utc
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
PACKET_HASH = "f" * 64
SYMBOL = "BITCOIN_i"


def demo_health(equity: float = 1000.0) -> ProviderHealth:
    return ProviderHealth(
        initialized=True,
        connected=True,
        account_environment="demo",
        server="Alpari-MT5-Demo",
        login=100,
        currency="USD",
        balance=equity,
        equity=equity,
        last_error=(0, "ok"),
    )


def draft(
    *,
    decision: SignalDecision = SignalDecision.LONG,
    confidence: int | None = 73,
    bid: float = 64000.0,
    ask: float = 64060.0,
    stop_loss: float | None = 63000.0,
    take_profit: float | None = 66000.0,
) -> SignalDraft:
    return SignalDraft(
        created_at_utc=NOW,
        broker="alpari",
        symbol=SYMBOL,
        analysis_timeframe="4H",
        decision=decision,
        confidence=confidence,
        bid=bid,
        ask=ask,
        market_data_timestamp=NOW,
        latest_completed_4h_candle="2026-07-23T08:00:00Z",
        developing_4h_candle="2026-07-23T12:00:00Z",
        entry_type="MARKET",
        entry_reference_price=(
            None
            if decision is SignalDecision.NO_TRADE
            else (ask if decision is SignalDecision.LONG else bid)
        ),
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason="deterministic fixture",
        news_context="",
        market_snapshot_id=f"mp_{PACKET_HASH[:24]}",
        market_packet_hash=PACKET_HASH,
    )


def make_supervisor(tmp_path: Path) -> TradingLabSupervisor:
    return TradingLabSupervisor(
        signal_journal=SignalJournal(tmp_path / "signals.sqlite3"),
        position_journal=VirtualPositionJournal(
            tmp_path / "positions.sqlite3"
        ),
    )


def submit_signal(supervisor: TradingLabSupervisor, **kwargs) -> str:
    record = supervisor.signals.submit("fixture-key-1", draft(**kwargs))
    return record.signal_id


def initialized_supervisor(
    tmp_path: Path,
) -> tuple[TradingLabSupervisor, str]:
    supervisor = make_supervisor(tmp_path)
    supervisor.initialize_from_health(demo_health(), now=NOW)
    signal_id = submit_signal(supervisor)
    return supervisor, signal_id


def test_initialization_requires_connected_demo_provider(
    tmp_path: Path,
) -> None:
    supervisor = make_supervisor(tmp_path)
    bad = ProviderHealth(
        initialized=True,
        connected=True,
        account_environment="real",
        server="x",
        login=1,
        currency="USD",
        balance=1.0,
        equity=1.0,
        last_error=(),
    )
    with pytest.raises(RuntimeError, match="demo"):
        supervisor.initialize_from_health(bad, now=NOW)
    supervisor.initialize_from_health(demo_health(), now=NOW)
    with pytest.raises(RuntimeError, match="already initialized"):
        supervisor.initialize_from_health(demo_health(), now=NOW)
    cohort = supervisor.active_cohort()
    assert cohort.transition is CohortTransition.INITIAL
    assert cohort.baseline_equity == Decimal("1000.00")


def test_confidence_routes_exact_thresholds_and_marks_entered(
    tmp_path: Path,
) -> None:
    supervisor, signal_id = initialized_supervisor(tmp_path)

    report = supervisor.enter_signal(signal_id, now=NOW)

    assert report.entered_thresholds == tuple(range(50, 74))
    assert report.skipped_busy == ()
    assert len(report.position_ids) == 24
    assert (
        supervisor.signals.get(signal_id).status is SignalStatus.ENTERED
    )
    for position in supervisor.open_positions():
        # Honest entry: LONG opens at ask.
        assert position.entry_price == Decimal("64060.0")

    # Idempotent re-entry: no duplicates, same 24 open positions.
    again = supervisor.enter_signal(signal_id, now=NOW)
    assert again.entered_thresholds == tuple(range(50, 74))
    assert len(supervisor.open_positions()) == 24

    # A second overlapping signal skips busy portfolios entirely.
    second = supervisor.signals.submit(
        "fixture-key-2", draft(confidence=60)
    )
    second_report = supervisor.enter_signal(second.signal_id, now=NOW)
    assert second_report.entered_thresholds == ()
    assert second_report.skipped_busy == tuple(range(50, 61))


def test_no_trade_is_a_noop(tmp_path: Path) -> None:
    supervisor = make_supervisor(tmp_path)
    supervisor.initialize_from_health(demo_health(), now=NOW)
    record = supervisor.signals.submit(
        "fixture-no-trade",
        draft(
            decision=SignalDecision.NO_TRADE,
            confidence=None,
            stop_loss=None,
            take_profit=None,
        ),
    )
    report = supervisor.enter_signal(record.signal_id, now=NOW)
    assert report.entered_thresholds == ()
    assert supervisor.open_positions() == ()
    assert (
        supervisor.signals.get(record.signal_id).status
        is SignalStatus.SUBMITTED
    )


def test_tick_resolution_is_honest_and_exactly_once(tmp_path: Path) -> None:
    supervisor, signal_id = initialized_supervisor(tmp_path)
    supervisor.enter_signal(signal_id, now=NOW)

    # Bid above entry but below take-profit: nothing resolves.
    assert (
        supervisor.observe_tick(
            symbol=SYMBOL,
            bid=65000,
            ask=65060,
            observed_at_utc=NOW + timedelta(minutes=1),
        )
        == ()
    )

    # Bid reaches take-profit: every long exits at bid exactly once.
    resolved = supervisor.observe_tick(
        symbol=SYMBOL,
        bid=66000,
        ask=66060,
        observed_at_utc=NOW + timedelta(minutes=2),
    )
    assert len(resolved) == 24
    for position in resolved:
        assert position.status is PositionStatus.TAKE_PROFIT
        assert position.exit_price == Decimal("66000")

    # Second boundary tick is a no-op: no reopening, no double resolution.
    assert (
        supervisor.observe_tick(
            symbol=SYMBOL,
            bid=62000,
            ask=62060,
            observed_at_utc=NOW + timedelta(minutes=3),
        )
        == ()
    )
    events = supervisor.positions.events(resolved[0].position_id)
    assert [event["event_type"] for event in events] == [
        "position_opened",
        "position_resolved",
    ]

    # Balances reconstruct from the journal: entry 64060 -> exit 66000.
    state = {
        s.threshold: s for s in supervisor.portfolio_states()
    }
    expected_gain = (
        (Decimal("66000") - Decimal("64060.0"))
        / Decimal("64060.0")
    ) * Decimal("1.00")
    assert state[50].balance == Decimal("1000.00") + expected_gain
    assert state[74].balance == Decimal("1000.00")
    assert state[50].open_position_id is None


def test_restart_recovers_open_trade_and_resolves_exactly_once(
    tmp_path: Path,
) -> None:
    supervisor, signal_id = initialized_supervisor(tmp_path)
    supervisor.enter_signal(signal_id, now=NOW)
    opened = {p.position_id for p in supervisor.open_positions()}
    assert len(opened) == 24
    del supervisor  # simulate process death without any shutdown hook

    # A fresh supervisor over the same journals recovers the open work.
    restarted = make_supervisor(tmp_path)
    assert {
        p.position_id for p in restarted.open_positions()
    } == opened
    recovered = restarted.recover_with_ticks(
        symbol=SYMBOL,
        ticks=[
            (65000, 65060, NOW + timedelta(minutes=10)),
            (63000, 63060, NOW + timedelta(minutes=11)),  # stop-loss hit
            (66000, 66060, NOW + timedelta(minutes=12)),  # after exit
        ],
    )
    assert len(recovered) == 24
    for position in recovered:
        assert position.status is PositionStatus.STOP_LOSS
        assert position.exit_price == Decimal("63000")
        assert position.resolution_source == "tick"
        events = restarted.positions.events(position.position_id)
        assert [e["event_type"] for e in events] == [
            "position_opened",
            "position_resolved",
        ]
    assert restarted.open_positions() == ()

    # A second recovery pass finds nothing to resolve.
    assert (
        restarted.recover_with_ticks(
            symbol=SYMBOL,
            ticks=[(66000, 66060, NOW + timedelta(minutes=13))],
        )
        == ()
    )


def test_ambiguous_candle_range_never_picks_favourable_outcome(
    tmp_path: Path,
) -> None:
    supervisor, signal_id = initialized_supervisor(tmp_path)
    supervisor.enter_signal(signal_id, now=NOW)

    resolved = supervisor.recover_with_range(
        symbol=SYMBOL,
        low=62900,  # below stop-loss
        high=66100,  # above take-profit
        observed_at_utc=NOW + timedelta(hours=4),
    )
    assert len(resolved) == 24
    for position in resolved:
        assert position.status is PositionStatus.AMBIGUOUS_DATA
        assert position.exit_price is None
        assert position.realized_return is None

    # Ambiguity frees the portfolio without inventing P&L.
    state = {s.threshold: s for s in supervisor.portfolio_states()}
    assert state[50].balance == Decimal("1000.00")
    assert state[50].ambiguous_trades == 1
    assert state[50].open_position_id is None


def test_unambiguous_range_resolves_single_boundary(tmp_path: Path) -> None:
    supervisor, signal_id = initialized_supervisor(tmp_path)
    supervisor.enter_signal(signal_id, now=NOW)
    resolved = supervisor.recover_with_range(
        symbol=SYMBOL,
        low=63500,
        high=66100,  # only take-profit inside the range
        observed_at_utc=NOW + timedelta(hours=4),
    )
    assert all(
        p.status is PositionStatus.TAKE_PROFIT for p in resolved
    )
    assert all(p.exit_price == Decimal("66000.0") for p in resolved)


def test_allocation_cap_blocks_entry_for_depleted_portfolio(
    tmp_path: Path,
) -> None:
    supervisor = make_supervisor(tmp_path)
    # Tiny baseline: 20 percent of 4.00 is 0.80, below the 1.00 stake.
    supervisor.initialize_from_health(demo_health(equity=4.0), now=NOW)
    record = supervisor.signals.submit("fixture-cap", draft())
    report = supervisor.enter_signal(record.signal_id, now=NOW)
    assert report.entered_thresholds == ()
    assert report.skipped_allocation_cap == tuple(range(50, 74))
    assert supervisor.open_positions() == ()


def test_cohort_transitions_preserve_history(tmp_path: Path) -> None:
    supervisor, signal_id = initialized_supervisor(tmp_path)
    supervisor.enter_signal(signal_id, now=NOW)
    first_cohort = supervisor.active_cohort()

    later = supervisor.start_cohort(
        transition=CohortTransition.DEPOSIT,
        baseline_equity="1500.00",
        currency="USD",
        now=NOW + timedelta(days=1),
    )
    assert later.source_cohort_id == first_cohort.cohort_id
    # New cohort portfolios start clean; old open positions remain
    # journalled under the previous cohort untouched.
    state = {s.threshold: s for s in supervisor.portfolio_states()}
    assert state[50].cohort_id == later.cohort_id
    assert state[50].balance == Decimal("1500.00")
    assert state[50].open_position_id is None
    assert len(supervisor.positions.list_open()) == 24


def test_position_journal_groundwork_contracts(tmp_path: Path) -> None:
    journal = VirtualPositionJournal(tmp_path / "positions.sqlite3")
    base = dict(
        idempotency_key="key-1",
        cohort_id="cohort_x",
        threshold=60,
        signal_id="sig-1",
        decision=SignalDecision.LONG,
        symbol=SYMBOL,
        entry_price="64060",
        stop_loss="63000",
        take_profit="66000",
        normalized_stake_usd="1.00",
        opened_at_utc=NOW,
    )
    first = journal.open_position(**base)
    # Same key, same content: identical record returned.
    assert journal.open_position(**base) == first
    # Same key, different content: fails closed.
    with pytest.raises(ValueError, match="different position content"):
        journal.open_position(**{**base, "take_profit": "67000"})
    # Same portfolio slot, different key: one-open index rejects.
    with pytest.raises(RuntimeError, match="open position"):
        journal.open_position(
            **{**base, "idempotency_key": "key-2", "signal_id": "sig-2"}
        )
    # NO_TRADE can never open.
    with pytest.raises(ValueError, match="NO_TRADE"):
        journal.open_position(
            **{
                **base,
                "idempotency_key": "key-3",
                "threshold": 61,
                "decision": SignalDecision.NO_TRADE,
            }
        )
    # SHORT price shape is enforced.
    with pytest.raises(ValueError, match="SHORT requires"):
        journal.open_position(
            **{
                **base,
                "idempotency_key": "key-4",
                "threshold": 62,
                "decision": SignalDecision.SHORT,
            }
        )
