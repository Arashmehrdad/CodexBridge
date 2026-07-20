from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256

from .signal_journal import SignalDecision


UTC = timezone.utc
NORMALIZED_STAKE_USD = Decimal("1.00")
THRESHOLDS = tuple(range(50, 100))


class CohortTransition(str, Enum):
    INITIAL = "initial"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    ACCOUNT_RESET = "account_reset"
    BASELINE_CHANGE = "baseline_change"


@dataclass(frozen=True)
class ThresholdPortfolio:
    threshold: int
    balance: Decimal
    currency: str
    open_signal_id: str | None = None
    open_decision: SignalDecision | None = None
    normalized_stake_usd: Decimal = Decimal("0.00")

    @property
    def is_free(self) -> bool:
        return self.open_signal_id is None


@dataclass(frozen=True)
class ExperimentCohort:
    cohort_id: str
    created_at_utc: datetime
    transition: CohortTransition
    baseline_equity: Decimal
    currency: str
    portfolios: tuple[ThresholdPortfolio, ...]
    source_cohort_id: str | None = None

    def portfolio(self, threshold: int) -> ThresholdPortfolio:
        if threshold not in THRESHOLDS:
            raise ValueError("threshold must be from 50 through 99")
        return self.portfolios[threshold - THRESHOLDS[0]]


@dataclass(frozen=True)
class ThresholdExperiment:
    cohorts: tuple[ExperimentCohort, ...]

    @property
    def active(self) -> ExperimentCohort:
        if not self.cohorts:
            raise RuntimeError("threshold experiment has no cohort")
        return self.cohorts[-1]


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _money(value: Decimal | int | float | str, field_name: str) -> Decimal:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid monetary amount") from exc
    if not normalized.is_finite() or normalized <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized


def _currency(value: str) -> str:
    normalized = str(value).strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a three-letter alphabetic code")
    return normalized


def _cohort_id(
    *,
    created_at_utc: datetime,
    transition: CohortTransition,
    baseline_equity: Decimal,
    currency: str,
    source_cohort_id: str | None,
) -> str:
    payload = "|".join(
        (
            created_at_utc.isoformat(),
            transition.value,
            format(baseline_equity, "f"),
            currency,
            source_cohort_id or "",
        )
    )
    return "cohort_" + sha256(payload.encode("utf-8")).hexdigest()[:24]


def _new_cohort(
    *,
    baseline_equity: Decimal | int | float | str,
    currency: str,
    created_at_utc: datetime,
    transition: CohortTransition,
    source_cohort_id: str | None,
) -> ExperimentCohort:
    created = _aware_utc(created_at_utc, "created_at_utc")
    equity = _money(baseline_equity, "baseline_equity")
    normalized_currency = _currency(currency)
    portfolios = tuple(
        ThresholdPortfolio(
            threshold=threshold,
            balance=equity,
            currency=normalized_currency,
        )
        for threshold in THRESHOLDS
    )
    return ExperimentCohort(
        cohort_id=_cohort_id(
            created_at_utc=created,
            transition=transition,
            baseline_equity=equity,
            currency=normalized_currency,
            source_cohort_id=source_cohort_id,
        ),
        created_at_utc=created,
        transition=transition,
        baseline_equity=equity,
        currency=normalized_currency,
        portfolios=portfolios,
        source_cohort_id=source_cohort_id,
    )


def initialize_threshold_experiment(
    *,
    baseline_equity: Decimal | int | float | str,
    currency: str,
    created_at_utc: datetime,
) -> ThresholdExperiment:
    return ThresholdExperiment(
        cohorts=(
            _new_cohort(
                baseline_equity=baseline_equity,
                currency=currency,
                created_at_utc=created_at_utc,
                transition=CohortTransition.INITIAL,
                source_cohort_id=None,
            ),
        )
    )


def route_signal(
    experiment: ThresholdExperiment,
    *,
    signal_id: str,
    decision: SignalDecision,
    confidence: int | None,
) -> ThresholdExperiment:
    normalized_signal_id = str(signal_id).strip()
    if not normalized_signal_id:
        raise ValueError("signal_id must not be empty")
    normalized_decision = SignalDecision(decision)
    if normalized_decision is SignalDecision.NO_TRADE:
        if confidence is not None:
            raise ValueError("NO_TRADE confidence must be null")
        return experiment
    if isinstance(confidence, bool) or not isinstance(confidence, int) or confidence not in THRESHOLDS:
        raise ValueError("trade confidence must be an integer from 50 through 99")

    active = experiment.active
    if any(portfolio.open_signal_id == normalized_signal_id for portfolio in active.portfolios):
        return experiment

    portfolios = tuple(
        replace(
            portfolio,
            open_signal_id=normalized_signal_id,
            open_decision=normalized_decision,
            normalized_stake_usd=NORMALIZED_STAKE_USD,
        )
        if portfolio.is_free and portfolio.threshold <= confidence
        else portfolio
        for portfolio in active.portfolios
    )
    return ThresholdExperiment(
        cohorts=experiment.cohorts[:-1] + (replace(active, portfolios=portfolios),)
    )


def start_new_cohort(
    experiment: ThresholdExperiment,
    *,
    transition: CohortTransition,
    baseline_equity: Decimal | int | float | str,
    currency: str,
    created_at_utc: datetime,
) -> ThresholdExperiment:
    normalized_transition = CohortTransition(transition)
    if normalized_transition is CohortTransition.INITIAL:
        raise ValueError("INITIAL is only valid for experiment initialization")
    active = experiment.active
    equity = _money(baseline_equity, "baseline_equity")
    normalized_currency = _currency(currency)
    if normalized_transition is CohortTransition.DEPOSIT:
        if normalized_currency != active.currency or equity <= active.baseline_equity:
            raise ValueError("deposit must increase equity without changing currency")
    elif normalized_transition is CohortTransition.WITHDRAWAL:
        if normalized_currency != active.currency or equity >= active.baseline_equity:
            raise ValueError("withdrawal must decrease equity without changing currency")

    cohort = _new_cohort(
        baseline_equity=equity,
        currency=normalized_currency,
        created_at_utc=created_at_utc,
        transition=normalized_transition,
        source_cohort_id=active.cohort_id,
    )
    return ThresholdExperiment(cohorts=experiment.cohorts + (cohort,))
