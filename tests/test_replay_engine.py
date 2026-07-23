from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from soma.trading.outcome_resolver import OutcomeStatus, SignalOutcome
from soma.trading.replay_engine import (
    NotionalModel,
    OccupancyPolicy,
    ReplayConfig,
    replay_signals,
    sweep_thresholds,
)
from soma.trading.versions import REPLAY_ENGINE_VERSION, RESOLVER_VERSION

from tests.trading_lab_fixtures import DEVELOPING_RAW_OPEN, SYMBOL, signal_record_v2

UTC = timezone.utc
T0 = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)


def make_signal(index: int, confidence: int, at: datetime, decision: str = "LONG"):
    return signal_record_v2(
        signal_id=f"sig2_replay{index:018d}",
        decision=decision,
        confidence=confidence,
        submitted_at=at,
    )


def make_outcome(
    signal,
    status: OutcomeStatus,
    *,
    fraction: float | None = None,
    exit_after: timedelta | None = timedelta(hours=1),
    evidence: dict | None = None,
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
        evidence=evidence or {},
    )


def test_chronological_replay_records_skips_blocks_and_pnl() -> None:
    s1 = make_signal(1, 80, T0)
    s2 = make_signal(2, 60, T0 + timedelta(minutes=10))
    s3 = make_signal(3, 90, T0 + timedelta(minutes=30))  # while s1 open
    s4 = make_signal(4, 75, T0 + timedelta(hours=2))  # after s1 exit
    outcomes = {
        s1.signal_id: make_outcome(
            s1, OutcomeStatus.RESOLVED_TP, fraction=0.02
        ),
        s3.signal_id: make_outcome(
            s3, OutcomeStatus.RESOLVED_TP, fraction=0.05
        ),
        s4.signal_id: make_outcome(
            s4, OutcomeStatus.RESOLVED_SL, fraction=-0.01
        ),
    }
    config = ReplayConfig(
        threshold=70, notional=NotionalModel(fixed_notional_usd=100.0)
    )
    result = replay_signals([s4, s2, s1, s3], outcomes, config)

    assert result.replay_version == REPLAY_ENGINE_VERSION
    assert result.entered_count == 2
    assert result.skipped_confidence_count == 1
    assert result.blocked_existing_position_count == 1
    events = {event.signal_id: event.event for event in result.events}
    assert events[s2.signal_id] == "SKIPPED_CONFIDENCE"
    assert events[s3.signal_id] == "BLOCKED_EXISTING_POSITION"
    assert result.net_pnl_usd == pytest.approx(0.02 * 100 - 0.01 * 100)
    assert result.win_rate == pytest.approx(0.5)
    assert result.longest_losing_streak == 1
    assert result.final_equity_usd == pytest.approx(1_000.0 + 1.0)

    # Deterministic: identical input produces identical results.
    again = replay_signals([s1, s2, s3, s4], outcomes, config)
    assert again.net_pnl_usd == result.net_pnl_usd
    assert again.events == result.events


def test_stacking_policy_lifts_the_duplicate_exposure_block() -> None:
    s1 = make_signal(1, 80, T0)
    s3 = make_signal(3, 90, T0 + timedelta(minutes=30))
    outcomes = {
        s1.signal_id: make_outcome(
            s1, OutcomeStatus.RESOLVED_TP, fraction=0.02
        ),
        s3.signal_id: make_outcome(
            s3, OutcomeStatus.RESOLVED_TP, fraction=0.05
        ),
    }
    stacked = replay_signals(
        [s1, s3],
        outcomes,
        ReplayConfig(
            threshold=70, occupancy=OccupancyPolicy(allow_stacking=True)
        ),
    )
    assert stacked.blocked_existing_position_count == 0
    assert stacked.entered_count == 2


def test_ambiguous_is_factual_unknown_and_conservative_only_in_scenario() -> None:
    s1 = make_signal(1, 80, T0)
    s2 = make_signal(2, 85, T0 + timedelta(hours=6))
    range_end = (T0 + timedelta(hours=4)).isoformat()
    outcomes = {
        s1.signal_id: make_outcome(
            s1,
            OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS,
            exit_after=None,
            evidence={"range": {"end_utc": range_end}},
        ),
        s2.signal_id: make_outcome(
            s2, OutcomeStatus.RESOLVED_TP, fraction=0.02
        ),
    }
    config = ReplayConfig(
        threshold=70, notional=NotionalModel(fixed_notional_usd=100.0)
    )
    result = replay_signals([s1, s2], outcomes, config)

    # The ambiguous slot freed at its range end, so s2 entered.
    assert result.entered_count == 2
    assert result.ambiguous_count == 1
    # Factual net excludes the ambiguous trade entirely.
    assert result.net_pnl_usd == pytest.approx(2.0)
    # Scenario-only conservative treatment books the full stop loss:
    # entry 64,064 stop 63,400 on 100 USD notional.
    expected_loss = (64_064.0 - 63_400.0) / 64_064.0 * 100.0
    assert result.scenario_conservative_net_pnl_usd == pytest.approx(
        2.0 - expected_loss
    )


def test_unresolved_signal_keeps_occupying_the_symbol() -> None:
    s1 = make_signal(1, 80, T0)
    s2 = make_signal(2, 85, T0 + timedelta(days=2))
    outcomes = {
        s1.signal_id: make_outcome(
            s1, OutcomeStatus.UNRESOLVED_DATA_GAP, exit_after=None
        ),
        s2.signal_id: make_outcome(
            s2, OutcomeStatus.RESOLVED_TP, fraction=0.02
        ),
    }
    result = replay_signals([s1, s2], outcomes, ReplayConfig(threshold=70))
    assert result.blocked_existing_position_count == 1
    assert result.unresolved_count == 1
    assert result.net_pnl_usd == pytest.approx(0.0)


def test_insufficient_sample_is_marked_and_never_recommended() -> None:
    s1 = make_signal(1, 95, T0)
    outcomes = {
        s1.signal_id: make_outcome(
            s1, OutcomeStatus.RESOLVED_TP, fraction=0.5
        ),
    }
    result = replay_signals(
        [s1], outcomes, ReplayConfig(threshold=90), minimum_sample=30
    )
    assert result.insufficient_sample is True

    sweep = sweep_thresholds(
        [s1], outcomes, thresholds=(90, 91, 92), minimum_sample=30
    )
    assert all(row.insufficient_sample for row in sweep.rows)
    assert sweep.recommended_threshold is None
    assert sweep.stable_region == ()


def test_sweep_prefers_stable_neighbourhood_over_single_maximum() -> None:
    # Confidence-level P&L contributions chosen so the single-threshold
    # maximum (61) sits between deep losses, while 64 has the best
    # neighbourhood mean: nets are 60:-17, 61:14, 62:-10+... cumulative
    # from the top: n(t) = sum of contributions with confidence >= t.
    contributions = {
        60: -0.17,
        61: 0.14,
        62: -0.10,
        63: 0.01,
        64: 0.01,
        65: 0.06,
    }
    signals = []
    outcomes = {}
    at = T0
    for index, (confidence, fraction) in enumerate(contributions.items()):
        signal = make_signal(index, confidence, at)
        signals.append(signal)
        outcomes[signal.signal_id] = make_outcome(
            signal,
            OutcomeStatus.RESOLVED_TP
            if fraction > 0
            else OutcomeStatus.RESOLVED_SL,
            fraction=fraction,
            exit_after=timedelta(minutes=30),
        )
        at += timedelta(hours=1)
    config = ReplayConfig(
        threshold=60, notional=NotionalModel(fixed_notional_usd=100.0)
    )
    sweep = sweep_thresholds(
        signals,
        outcomes,
        base_config=config,
        thresholds=(60, 61, 62, 63, 64, 65),
        minimum_sample=1,
    )
    nets = {row.threshold: row.net_pnl_usd for row in sweep.rows}
    assert nets[61] == pytest.approx(12.0)  # single maximum
    assert nets[64] == pytest.approx(7.0)
    # 61's neighbourhood carries the deep losses beside it; 64 sits in
    # the stable positive region and wins the neighbourhood mean.
    assert sweep.recommended_threshold == 64
    assert 64 in sweep.stable_region


def test_replay_config_validation() -> None:
    with pytest.raises(ValueError, match="50 through 99"):
        ReplayConfig(threshold=49)
    with pytest.raises(ValueError, match="positive"):
        NotionalModel(fixed_notional_usd=0)
