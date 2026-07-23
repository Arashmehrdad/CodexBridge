from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soma.trading.lab_reports import (
    build_calibration_report,
    build_replay_report,
)
from soma.trading.outcome_resolver import OutcomeStatus, SignalOutcome
from soma.trading.replay_engine import ReplayConfig
from soma.trading.versions import RESOLVER_VERSION

from tests.trading_lab_fixtures import signal_record_v2

UTC = timezone.utc
T0 = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)


def make_signal(index: int, confidence: int | None, at: datetime, **overrides):
    decision = overrides.pop("decision", "LONG" if confidence else "NO_TRADE")
    if decision == "NO_TRADE":
        overrides.setdefault("stop_loss", None)
        overrides.setdefault("take_profit", None)
    return signal_record_v2(
        signal_id=f"sig2_report{index:018d}",
        decision=decision,
        confidence=confidence,
        submitted_at=at,
        **overrides,
    )


def make_outcome(
    signal,
    status: OutcomeStatus,
    *,
    fraction: float | None = None,
    exit_after: timedelta | None = timedelta(hours=1),
) -> SignalOutcome:
    entry = signal.submitted_at_utc
    return SignalOutcome(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        decision=signal.decision,
        experiment_id=signal.experiment_id,
        parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
        entry_time_utc=entry,
        entry_price=signal.entry_reference_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        status=status,
        exit_time_utc=(entry + exit_after) if exit_after else None,
        exit_price=None,
        realized_return_fraction=fraction,
        range_hash="",
        observed_tick_count=1,
        source="ticks",
        gap_status="continuous",
        resolver_version=RESOLVER_VERSION,
        evidence={},
    )


def fixture_set():
    s_win = make_signal(1, 72, T0)
    s_loss = make_signal(2, 78, T0 + timedelta(hours=4))
    s_high = make_signal(3, 91, T0 + timedelta(hours=8))
    s_none = make_signal(4, None, T0 + timedelta(hours=12))
    signals = [s_win, s_loss, s_high, s_none]
    outcomes = {
        s_win.signal_id: make_outcome(
            s_win, OutcomeStatus.RESOLVED_TP, fraction=0.02
        ),
        s_loss.signal_id: make_outcome(
            s_loss, OutcomeStatus.RESOLVED_SL, fraction=-0.01
        ),
        s_high.signal_id: make_outcome(
            s_high, OutcomeStatus.UNRESOLVED_DATA_GAP, exit_after=None
        ),
    }
    return signals, outcomes


def test_calibration_report_bands_and_parent_h4_groups() -> None:
    signals, outcomes = fixture_set()
    report = build_calibration_report(
        signals, outcomes, experiment_id="exp1", rejection_count=3
    )

    assert report["report"] == "signal_confidence_calibration"
    assert report["selected_signal_count"] == 4
    assert report["directional_signal_count"] == 3
    assert report["no_trade_count"] == 1
    assert report["rejected_submission_count"] == 3
    bands = {band["band"]: band for band in report["confidence_bands"]}
    assert bands["70-79"]["signal_count"] == 2
    assert bands["70-79"]["resolved_tp"] == 1
    assert bands["70-79"]["resolved_sl"] == 1
    assert bands["70-79"]["tp_rate"] == pytest.approx(0.5)
    assert bands["90-99"]["unresolved_data_gap"] == 1
    assert bands["90-99"]["tp_rate"] is None
    # All fixture signals share one parent H4 candle: correlated, not
    # independent samples.
    assert report["parent_h4_groups"]["distinct_parent_candles"] == 1
    assert report["parent_h4_groups"]["max_signals_per_candle"] == 3
    assert report["content_hash"]

    # Deterministic byte-identical reproduction.
    again = build_calibration_report(
        signals, outcomes, experiment_id="exp1", rejection_count=3
    )
    assert again["content_hash"] == report["content_hash"]


def test_resolution_basis_includes_positions_resolved_within_period() -> None:
    # Audit defect 5: a position opened before the period but resolved
    # within it must appear in resolution-basis reports.
    signals, outcomes = fixture_set()
    period_start = T0 + timedelta(hours=2)
    period_end = T0 + timedelta(days=1)

    resolution = build_calibration_report(
        signals,
        outcomes,
        period_start_utc=period_start,
        period_end_utc=period_end,
        period_basis="resolution",
    )
    # s_win entered at T0 (before the period) but resolved at T0+1h...
    # which is still before period_start, so it is excluded; s_loss
    # resolved at T0+5h inside the period and is included.
    bands = {band["band"]: band for band in resolution["confidence_bands"]}
    assert bands["70-79"]["signal_count"] == 1
    assert bands["70-79"]["resolved_sl"] == 1

    wide = build_calibration_report(
        signals,
        outcomes,
        period_start_utc=T0 + timedelta(minutes=30),
        period_end_utc=period_end,
        period_basis="resolution",
    )
    wide_bands = {band["band"]: band for band in wide["confidence_bands"]}
    # Entry at T0 predates this period too, but resolution at T0+1h is
    # inside it: included on the resolution basis.
    assert wide_bands["70-79"]["signal_count"] == 2

    entry_basis = build_calibration_report(
        signals,
        outcomes,
        period_start_utc=T0 + timedelta(minutes=30),
        period_end_utc=period_end,
        period_basis="entry",
    )
    entry_bands = {
        band["band"]: band for band in entry_basis["confidence_bands"]
    }
    assert entry_bands["70-79"]["signal_count"] == 1

    with pytest.raises(ValueError, match="period_basis"):
        build_calibration_report(
            signals, outcomes, period_basis="favourable"
        )


def test_experiment_selection_is_explicit() -> None:
    signals, outcomes = fixture_set()
    other = make_signal(9, 66, T0, experiment_id="exp2")
    outcomes[other.signal_id] = make_outcome(
        other, OutcomeStatus.RESOLVED_TP, fraction=0.03
    )
    report = build_calibration_report(
        [*signals, other], outcomes, experiment_id="exp2"
    )
    assert report["selected_signal_count"] == 1
    bands = {band["band"]: band for band in report["confidence_bands"]}
    assert bands["60-69"]["signal_count"] == 1


def test_replay_report_is_deterministic_with_occupancy_effects() -> None:
    signals, outcomes = fixture_set()
    report = build_replay_report(
        signals,
        outcomes,
        experiment_id="exp1",
        base_config=ReplayConfig(threshold=50),
        thresholds=(70, 75, 80),
        minimum_sample=1,
    )
    assert report["report"] == "strategy_replay"
    assert report["minimum_sample"] == 1
    rows = {row["threshold"]: row for row in report["thresholds"]}
    assert rows[70]["entered_count"] == 3
    assert rows[75]["skipped_confidence_count"] == 1
    assert rows[80]["entered_count"] == 1
    assert report["recommended_threshold"] in (70, 75, 80)
    assert "scenario_conservative_net_pnl_usd" in rows[70]

    again = build_replay_report(
        signals,
        outcomes,
        experiment_id="exp1",
        base_config=ReplayConfig(threshold=50),
        thresholds=(70, 75, 80),
        minimum_sample=1,
    )
    assert again["content_hash"] == report["content_hash"]
