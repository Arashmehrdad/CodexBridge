from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from codexbridge.trading.signal_journal import SignalDecision
from codexbridge.trading.threshold_simulator import (
    NORMALIZED_STAKE_USD,
    CohortTransition,
    initialize_threshold_experiment,
    route_signal,
    start_new_cohort,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def test_initialization_creates_50_independent_clones() -> None:
    experiment = initialize_threshold_experiment(
        baseline_equity="998.72",
        currency="usd",
        created_at_utc=NOW,
    )
    cohort = experiment.active

    assert cohort.transition is CohortTransition.INITIAL
    assert cohort.baseline_equity == Decimal("998.72")
    assert cohort.currency == "USD"
    assert len(cohort.portfolios) == 50
    assert [portfolio.threshold for portfolio in cohort.portfolios] == list(range(50, 100))
    assert all(portfolio.balance == Decimal("998.72") for portfolio in cohort.portfolios)
    assert all(portfolio.currency == "USD" for portfolio in cohort.portfolios)
    assert all(portfolio.is_free for portfolio in cohort.portfolios)
    assert len({id(portfolio) for portfolio in cohort.portfolios}) == 50


def test_confidence_73_enters_exactly_t50_through_t73_when_free() -> None:
    experiment = initialize_threshold_experiment(
        baseline_equity="998.72",
        currency="USD",
        created_at_utc=NOW,
    )
    routed = route_signal(
        experiment,
        signal_id="sig_confidence_73",
        decision=SignalDecision.LONG,
        confidence=73,
    )

    entered = [portfolio.threshold for portfolio in routed.active.portfolios if not portfolio.is_free]
    free = [portfolio.threshold for portfolio in routed.active.portfolios if portfolio.is_free]
    assert entered == list(range(50, 74))
    assert free == list(range(74, 100))
    assert all(
        portfolio.open_signal_id == "sig_confidence_73"
        and portfolio.open_decision is SignalDecision.LONG
        and portfolio.normalized_stake_usd == NORMALIZED_STAKE_USD
        for portfolio in routed.active.portfolios[:24]
    )
    assert all(portfolio.balance == Decimal("998.72") for portfolio in routed.active.portfolios)
    assert all(portfolio.is_free for portfolio in experiment.active.portfolios)


def test_eligibility_and_busy_state_diverge_without_cross_portfolio_mutation() -> None:
    experiment = initialize_threshold_experiment(
        baseline_equity="1000.00",
        currency="USD",
        created_at_utc=NOW,
    )
    first = route_signal(
        experiment,
        signal_id="sig_first",
        decision=SignalDecision.SHORT,
        confidence=60,
    )
    second = route_signal(
        first,
        signal_id="sig_second",
        decision=SignalDecision.LONG,
        confidence=73,
    )

    assert [second.active.portfolio(t).open_signal_id for t in range(50, 61)] == [
        "sig_first"
    ] * 11
    assert [second.active.portfolio(t).open_signal_id for t in range(61, 74)] == [
        "sig_second"
    ] * 13
    assert all(second.active.portfolio(t).is_free for t in range(74, 100))
    assert route_signal(
        second,
        signal_id="sig_second",
        decision=SignalDecision.LONG,
        confidence=73,
    ) == second


def test_no_trade_is_a_noop_and_strict_confidence_is_enforced() -> None:
    experiment = initialize_threshold_experiment(
        baseline_equity="1000",
        currency="USD",
        created_at_utc=NOW,
    )
    assert route_signal(
        experiment,
        signal_id="sig_no_trade",
        decision=SignalDecision.NO_TRADE,
        confidence=None,
    ) is experiment

    with pytest.raises(ValueError, match="must be null"):
        route_signal(
            experiment,
            signal_id="sig_invalid_no_trade",
            decision=SignalDecision.NO_TRADE,
            confidence=50,
        )
    with pytest.raises(ValueError, match="integer from 50 through 99"):
        route_signal(
            experiment,
            signal_id="sig_fractional",
            decision=SignalDecision.LONG,
            confidence=73.5,  # type: ignore[arg-type]
        )


def test_all_account_events_start_new_cohorts_and_preserve_history() -> None:
    initial = initialize_threshold_experiment(
        baseline_equity="998.72",
        currency="USD",
        created_at_utc=NOW,
    )
    traded = route_signal(
        initial,
        signal_id="sig_old_cohort",
        decision=SignalDecision.LONG,
        confidence=73,
    )
    deposit = start_new_cohort(
        traded,
        transition=CohortTransition.DEPOSIT,
        baseline_equity="1098.72",
        currency="USD",
        created_at_utc=NOW + timedelta(minutes=1),
    )
    withdrawal = start_new_cohort(
        deposit,
        transition=CohortTransition.WITHDRAWAL,
        baseline_equity="900.00",
        currency="USD",
        created_at_utc=NOW + timedelta(minutes=2),
    )
    reset = start_new_cohort(
        withdrawal,
        transition=CohortTransition.ACCOUNT_RESET,
        baseline_equity="1000.00",
        currency="USD",
        created_at_utc=NOW + timedelta(minutes=3),
    )
    changed = start_new_cohort(
        reset,
        transition=CohortTransition.BASELINE_CHANGE,
        baseline_equity="1500.00",
        currency="EUR",
        created_at_utc=NOW + timedelta(minutes=4),
    )

    assert [cohort.transition for cohort in changed.cohorts] == [
        CohortTransition.INITIAL,
        CohortTransition.DEPOSIT,
        CohortTransition.WITHDRAWAL,
        CohortTransition.ACCOUNT_RESET,
        CohortTransition.BASELINE_CHANGE,
    ]
    assert [cohort.baseline_equity for cohort in changed.cohorts] == [
        Decimal("998.72"),
        Decimal("1098.72"),
        Decimal("900.00"),
        Decimal("1000.00"),
        Decimal("1500.00"),
    ]
    assert changed.cohorts[0].portfolio(50).open_signal_id == "sig_old_cohort"
    assert all(portfolio.is_free for portfolio in changed.active.portfolios)
    assert changed.active.currency == "EUR"
    assert changed.cohorts[1].source_cohort_id == changed.cohorts[0].cohort_id
    assert changed.cohorts[4].source_cohort_id == changed.cohorts[3].cohort_id


def test_invalid_transition_and_immutable_records_fail_closed() -> None:
    experiment = initialize_threshold_experiment(
        baseline_equity="1000.00",
        currency="USD",
        created_at_utc=NOW,
    )
    with pytest.raises(ValueError, match="deposit must increase"):
        start_new_cohort(
            experiment,
            transition=CohortTransition.DEPOSIT,
            baseline_equity="999.00",
            currency="USD",
            created_at_utc=NOW + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="withdrawal must decrease"):
        start_new_cohort(
            experiment,
            transition=CohortTransition.WITHDRAWAL,
            baseline_equity="1001.00",
            currency="USD",
            created_at_utc=NOW + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        initialize_threshold_experiment(
            baseline_equity="1000.00",
            currency="USD",
            created_at_utc=NOW.replace(tzinfo=None),
        )
    with pytest.raises(FrozenInstanceError):
        experiment.active.baseline_equity = Decimal("1.00")  # type: ignore[misc]
