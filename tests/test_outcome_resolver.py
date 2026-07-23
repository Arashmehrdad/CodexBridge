from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from soma.trading.outcome_resolver import (
    OutcomeStatus,
    PriceRange,
    SignalOutcomeJournal,
    resolve_from_ranges,
    resolve_from_ticks,
)
from soma.trading.versions import RESOLVER_VERSION

from tests.trading_lab_fixtures import archived_tick, signal_record_v2

UTC = timezone.utc
ENTRY_AT = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)


def long_signal(**overrides):
    return signal_record_v2(
        decision="LONG",
        stop_loss=63_400.0,
        take_profit=65_400.0,
        submitted_at=ENTRY_AT,
        **overrides,
    )


def short_signal(**overrides):
    return signal_record_v2(
        decision="SHORT",
        stop_loss=64_700.0,
        take_profit=62_900.0,
        submitted_at=ENTRY_AT,
        **overrides,
    )


def tick(seconds: int, bid: float, ask: float):
    return archived_tick(ENTRY_AT + timedelta(seconds=seconds), bid, ask)


def test_long_resolves_take_profit_with_honest_prices_and_evidence() -> None:
    ticks = [
        tick(1, 64_000.0, 64_064.0),
        tick(60, 64_500.0, 64_564.0),
        tick(120, 65_401.0, 65_465.0),  # bid crosses take-profit
        tick(180, 65_600.0, 65_664.0),
    ]
    outcome = resolve_from_ticks(long_signal(), ticks)

    assert outcome.status is OutcomeStatus.RESOLVED_TP
    # Entry at the first post-entry tick's ask; exit tested on bid.
    assert outcome.entry_price == 64_064.0
    assert outcome.exit_price == 65_401.0
    assert outcome.realized_return_fraction == pytest.approx(
        (65_401.0 - 64_064.0) / 64_064.0
    )
    assert outcome.exit_time_utc == ENTRY_AT + timedelta(seconds=120)
    assert outcome.gap_status == "continuous"
    assert outcome.source == "ticks"
    assert outcome.resolver_version == RESOLVER_VERSION
    assert outcome.observed_tick_count == 4
    assert outcome.evidence["entry_tick"]["ask"] == 64_064.0
    assert outcome.evidence["first_touch_tick"]["bid"] == 65_401.0
    assert outcome.evidence["exit_tick"]["bid"] == 65_401.0
    assert outcome.range_hash


def test_short_enters_bid_and_tests_on_ask() -> None:
    ticks = [
        tick(1, 64_000.0, 64_064.0),
        tick(60, 63_100.0, 63_164.0),
        tick(120, 62_800.0, 62_864.0),  # ask crosses take-profit
    ]
    outcome = resolve_from_ticks(short_signal(), ticks)
    assert outcome.status is OutcomeStatus.RESOLVED_TP
    assert outcome.entry_price == 64_000.0
    assert outcome.exit_price == 62_864.0
    assert outcome.realized_return_fraction == pytest.approx(
        (64_000.0 - 62_864.0) / 64_000.0
    )


def test_pre_entry_observations_are_never_used() -> None:
    # Audit defect 2: a stop-loss touch before entry must not resolve
    # the signal; only post-entry observations count.
    ticks = [
        tick(-3600, 60_000.0, 60_064.0),  # would be a catastrophic SL touch
        tick(-60, 63_000.0, 63_064.0),  # below stop as well
        tick(5, 64_010.0, 64_074.0),
        tick(90, 65_450.0, 65_514.0),  # bid crosses take-profit
    ]
    outcome = resolve_from_ticks(long_signal(), ticks)
    assert outcome.status is OutcomeStatus.RESOLVED_TP
    assert outcome.observed_tick_count == 2
    assert outcome.entry_price == 64_074.0
    assert outcome.evidence["entry_tick"]["normalized_utc"] == (
        (ENTRY_AT + timedelta(seconds=5)).isoformat()
    )


def test_gap_slippage_resolves_at_observed_price_not_bracket_price() -> None:
    ticks = [
        tick(1, 64_000.0, 64_064.0),
        # 20-minute data gap, then the market reopens far through the stop.
        tick(1200, 62_900.0, 62_964.0),
    ]
    outcome = resolve_from_ticks(long_signal(), ticks)
    assert outcome.status is OutcomeStatus.RESOLVED_SL
    assert outcome.exit_price == 62_900.0  # honest observed bid, not 63,400
    assert outcome.gap_status == "gap_before_touch"
    assert outcome.evidence["gaps"][0]["gap_seconds"] == pytest.approx(1199.0)


def test_missing_and_exhausted_coverage_stay_unresolved() -> None:
    empty = resolve_from_ticks(long_signal(), [])
    assert empty.status is OutcomeStatus.UNRESOLVED_DATA_GAP
    assert empty.gap_status == "no_ticks_after_entry"
    assert empty.entry_price is None

    no_touch = resolve_from_ticks(
        long_signal(),
        [tick(1, 64_000.0, 64_064.0), tick(60, 64_100.0, 64_164.0)],
    )
    assert no_touch.status is OutcomeStatus.UNRESOLVED_DATA_GAP
    assert no_touch.gap_status == "coverage_ended_without_boundary"
    assert no_touch.entry_price == 64_064.0


def test_range_fallback_is_conservative() -> None:
    signal = long_signal()

    # A range spanning the entry moment cannot order its extremes
    # against entry: any touch is ambiguous.
    spanning = resolve_from_ranges(
        signal,
        [
            PriceRange(
                start_utc=ENTRY_AT - timedelta(hours=1),
                end_utc=ENTRY_AT + timedelta(hours=1),
                low=63_000.0,
                high=64_500.0,
            )
        ],
    )
    assert spanning.status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS
    assert spanning.gap_status == "entry_spanning_range_touch"

    # Both boundaries inside one post-entry range: ambiguous, never the
    # favourable pick.
    double = resolve_from_ranges(
        signal,
        [
            PriceRange(
                start_utc=ENTRY_AT + timedelta(hours=1),
                end_utc=ENTRY_AT + timedelta(hours=5),
                low=63_000.0,
                high=65_500.0,
            )
        ],
    )
    assert double.status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS
    assert double.gap_status == "double_boundary_range"

    # A pre-entry range is discarded entirely (audit defect 2).
    pre_entry_only = resolve_from_ranges(
        signal,
        [
            PriceRange(
                start_utc=ENTRY_AT - timedelta(hours=5),
                end_utc=ENTRY_AT - timedelta(hours=1),
                low=60_000.0,
                high=61_000.0,
            )
        ],
    )
    assert pre_entry_only.status is OutcomeStatus.UNRESOLVED_DATA_GAP

    # Single boundary in a post-entry range resolves at the boundary.
    single = resolve_from_ranges(
        signal,
        [
            PriceRange(
                start_utc=ENTRY_AT + timedelta(hours=1),
                end_utc=ENTRY_AT + timedelta(hours=5),
                low=63_900.0,
                high=65_500.0,
            )
        ],
    )
    assert single.status is OutcomeStatus.RESOLVED_TP
    assert single.exit_price == 65_400.0
    assert single.source == "candle_range"


def test_outcome_journal_upgrades_are_honest(tmp_path: Path) -> None:
    journal = SignalOutcomeJournal(tmp_path / "outcomes.sqlite3")
    signal = long_signal()

    unresolved = resolve_from_ticks(signal, [])
    journal.record(unresolved)
    assert journal.get(signal.signal_id).status is (
        OutcomeStatus.UNRESOLVED_DATA_GAP
    )

    ambiguous = resolve_from_ranges(
        signal,
        [
            PriceRange(
                start_utc=ENTRY_AT + timedelta(hours=1),
                end_utc=ENTRY_AT + timedelta(hours=5),
                low=63_000.0,
                high=65_500.0,
            )
        ],
    )
    journal.record(ambiguous)
    assert journal.get(signal.signal_id).status is (
        OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS
    )

    # Another candle range can never upgrade an ambiguous outcome.
    single_range = resolve_from_ranges(
        signal,
        [
            PriceRange(
                start_utc=ENTRY_AT + timedelta(hours=1),
                end_utc=ENTRY_AT + timedelta(hours=5),
                low=63_900.0,
                high=65_500.0,
            )
        ],
    )
    still_ambiguous = journal.record(single_range)
    assert still_ambiguous.status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS

    # Recovered real ticks do remove the ambiguity.
    resolved = resolve_from_ticks(
        signal,
        [tick(1, 64_000.0, 64_064.0), tick(60, 65_450.0, 65_514.0)],
    )
    journal.record(resolved)
    final = journal.get(signal.signal_id)
    assert final.status is OutcomeStatus.RESOLVED_TP

    # Resolved outcomes are immutable.
    conflicting = replace(resolved, status=OutcomeStatus.RESOLVED_SL)
    with pytest.raises(RuntimeError, match="immutable"):
        journal.record(conflicting)
    assert journal.record(resolved).status is OutcomeStatus.RESOLVED_TP

    events = [event["event_type"] for event in journal.events(signal.signal_id)]
    assert events.count("outcome_superseded") == 2
    assert events.count("outcome_recorded") == 3


def test_outcome_journal_lists_paginate(tmp_path: Path) -> None:
    journal = SignalOutcomeJournal(tmp_path / "outcomes.sqlite3")
    for index in range(3):
        signal = long_signal(
            signal_id=f"sig2_page{index:022d}",
        )
        journal.record(
            resolve_from_ticks(
                signal,
                [
                    tick(1 + index, 64_000.0, 64_064.0),
                    tick(60 + index, 65_450.0, 65_514.0),
                ],
            )
        )
    assert journal.count() == 3
    assert journal.count(experiment_id="exp1") == 3
    page = journal.list(limit=2, offset=2)
    assert len(page) == 1
    assert journal.list(status=OutcomeStatus.RESOLVED_SL) == []


def test_no_trade_signals_cannot_resolve() -> None:
    signal = signal_record_v2(
        decision="NO_TRADE",
        confidence=None,
        stop_loss=None,
        take_profit=None,
        submitted_at=ENTRY_AT,
    )
    with pytest.raises(ValueError, match="no outcome"):
        resolve_from_ticks(signal, [])
    with pytest.raises(ValueError, match="no outcome"):
        resolve_from_ranges(signal, [])
