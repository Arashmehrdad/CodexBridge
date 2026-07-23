"""Deterministic offline replay over the immutable journals.

Threshold and occupancy analysis happens only here — never at runtime.
The replay walks resolved signal outcomes chronologically under a
configurable confidence threshold, occupancy policy, notional model, and
cost model, recording ``SKIPPED_CONFIDENCE`` and
``BLOCKED_EXISTING_POSITION`` events explicitly. Thresholds with too few
entered trades are marked ``INSUFFICIENT_SAMPLE`` and are never ranked
as winners; stable neighbouring threshold regions are preferred over a
single maximum-profit point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .outcome_resolver import OutcomeStatus, SignalOutcome
from .signal_journal_v2 import (
    SignalDecisionV2,
    SignalRecordV2,
    SignalStatusV2,
)
from .versions import COST_MODEL_VERSION, REPLAY_ENGINE_VERSION

UTC = timezone.utc
DEFAULT_MINIMUM_SAMPLE = 30


@dataclass(frozen=True)
class OccupancyPolicy:
    """Whether one symbol may hold stacked simultaneous positions."""

    allow_stacking: bool = False


@dataclass(frozen=True)
class NotionalModel:
    """Fixed normalized virtual notional per trade at 1x exposure."""

    fixed_notional_usd: float = 1.0

    def __post_init__(self) -> None:
        if self.fixed_notional_usd <= 0:
            raise ValueError("fixed_notional_usd must be positive")


@dataclass(frozen=True)
class CostModel:
    """Per-trade cost beyond the honest bid/ask spread already embedded."""

    per_trade_cost_usd: float = 0.0
    version: str = COST_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.per_trade_cost_usd < 0:
            raise ValueError("per_trade_cost_usd must not be negative")


@dataclass(frozen=True)
class ReplayConfig:
    threshold: int
    occupancy: OccupancyPolicy = OccupancyPolicy()
    notional: NotionalModel = NotionalModel()
    cost: CostModel = CostModel()
    initial_equity_usd: float = 1_000.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, int)
            or not 50 <= self.threshold <= 99
        ):
            raise ValueError("threshold must be an integer from 50 through 99")
        if self.initial_equity_usd <= 0:
            raise ValueError("initial_equity_usd must be positive")


@dataclass(frozen=True)
class ReplayTrade:
    signal_id: str
    decision: SignalDecisionV2
    confidence: int
    entry_time_utc: datetime
    exit_time_utc: datetime | None
    outcome_status: OutcomeStatus
    realized_pnl_usd: float | None
    conservative_loss_usd: float
    parent_h4_raw_open_epoch: int


@dataclass(frozen=True)
class ReplayEvent:
    signal_id: str
    event: str
    detail: str = ""


@dataclass(frozen=True)
class ReplayResult:
    config: ReplayConfig
    replay_version: str
    trades: tuple[ReplayTrade, ...]
    events: tuple[ReplayEvent, ...]
    signal_count: int
    entered_count: int
    skipped_confidence_count: int
    blocked_existing_position_count: int
    resolved_tp_count: int
    resolved_sl_count: int
    unresolved_count: int
    ambiguous_count: int
    net_pnl_usd: float
    scenario_conservative_net_pnl_usd: float
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_usd: float
    longest_losing_streak: int
    final_equity_usd: float
    insufficient_sample: bool = False
    minimum_sample: int = DEFAULT_MINIMUM_SAMPLE


@dataclass(frozen=True)
class ThresholdSweepRow:
    threshold: int
    entered_count: int
    skipped_confidence_count: int
    blocked_existing_position_count: int
    net_pnl_usd: float
    scenario_conservative_net_pnl_usd: float
    win_rate: float | None
    max_drawdown_usd: float
    insufficient_sample: bool
    neighbourhood_net_pnl_usd: float | None = None


@dataclass(frozen=True)
class ThresholdSweep:
    rows: tuple[ThresholdSweepRow, ...]
    minimum_sample: int
    recommended_threshold: int | None
    stable_region: tuple[int, ...] = field(default_factory=tuple)


def _entry_moment(signal: SignalRecordV2) -> datetime:
    return signal.entered_at_utc or signal.submitted_at_utc


def _ambiguous_release_time(outcome: SignalOutcome) -> datetime | None:
    """When an ambiguous outcome provably stopped occupying its slot.

    Ambiguity means a boundary was certainly hit inside the evidence
    window — the position closed, direction unknown — so the slot frees
    at the end of that window.
    """
    range_evidence = outcome.evidence.get("range")
    if isinstance(range_evidence, dict) and range_evidence.get("end_utc"):
        return datetime.fromisoformat(
            str(range_evidence["end_utc"]).replace("Z", "+00:00")
        )
    return None


def _conservative_loss_usd(
    signal: SignalRecordV2, notional: NotionalModel, cost: CostModel
) -> float:
    """The stop-loss loss this trade would take, for scenario reports only."""
    entry = signal.entry_reference_price
    stop = signal.stop_loss
    if entry is None or stop is None or entry <= 0:
        return 0.0
    return (
        abs(entry - stop) / entry * notional.fixed_notional_usd
        + cost.per_trade_cost_usd
    )


def replay_signals(
    signals: Sequence[SignalRecordV2],
    outcomes: Mapping[str, SignalOutcome],
    config: ReplayConfig,
    *,
    minimum_sample: int = DEFAULT_MINIMUM_SAMPLE,
) -> ReplayResult:
    """One deterministic chronological replay pass."""
    if minimum_sample < 1:
        raise ValueError("minimum_sample must be positive")
    ordered = sorted(
        signals, key=lambda signal: (_entry_moment(signal), signal.signal_id)
    )
    trades: list[ReplayTrade] = []
    events: list[ReplayEvent] = []
    # symbol -> release time (None means never provably released).
    open_until: dict[str, datetime | None] = {}
    skipped_confidence = 0
    blocked = 0

    for signal in ordered:
        moment = _entry_moment(signal)
        if signal.status is SignalStatusV2.CANCELLED:
            events.append(
                ReplayEvent(signal.signal_id, "SKIPPED_CANCELLED")
            )
            continue
        if signal.decision is SignalDecisionV2.NO_TRADE:
            events.append(ReplayEvent(signal.signal_id, "NO_TRADE"))
            continue
        confidence = signal.confidence
        if confidence is None or confidence < config.threshold:
            skipped_confidence += 1
            events.append(
                ReplayEvent(
                    signal.signal_id,
                    "SKIPPED_CONFIDENCE",
                    f"confidence={confidence} threshold={config.threshold}",
                )
            )
            continue
        if not config.occupancy.allow_stacking:
            release = open_until.get(signal.symbol, moment)
            occupied = signal.symbol in open_until and (
                release is None or release > moment
            )
            if occupied:
                blocked += 1
                events.append(
                    ReplayEvent(
                        signal.signal_id,
                        "BLOCKED_EXISTING_POSITION",
                        f"symbol={signal.symbol}",
                    )
                )
                continue
        outcome = outcomes.get(signal.signal_id)
        if outcome is None:
            events.append(
                ReplayEvent(
                    signal.signal_id,
                    "ENTERED_WITHOUT_OUTCOME",
                    "no outcome record; occupies slot indefinitely",
                )
            )
            open_until[signal.symbol] = None
            trades.append(
                ReplayTrade(
                    signal_id=signal.signal_id,
                    decision=signal.decision,
                    confidence=confidence,
                    entry_time_utc=moment,
                    exit_time_utc=None,
                    outcome_status=OutcomeStatus.UNRESOLVED_DATA_GAP,
                    realized_pnl_usd=None,
                    conservative_loss_usd=_conservative_loss_usd(
                        signal, config.notional, config.cost
                    ),
                    parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
                )
            )
            continue

        events.append(ReplayEvent(signal.signal_id, "ENTERED"))
        realized: float | None = None
        exit_time = outcome.exit_time_utc
        if outcome.status in (
            OutcomeStatus.RESOLVED_TP,
            OutcomeStatus.RESOLVED_SL,
        ):
            fraction = outcome.realized_return_fraction or 0.0
            realized = (
                fraction * config.notional.fixed_notional_usd
                - config.cost.per_trade_cost_usd
            )
            open_until[signal.symbol] = exit_time
        elif outcome.status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS:
            open_until[signal.symbol] = _ambiguous_release_time(outcome)
        else:  # UNRESOLVED_DATA_GAP: factually still open.
            open_until[signal.symbol] = None
        trades.append(
            ReplayTrade(
                signal_id=signal.signal_id,
                decision=signal.decision,
                confidence=confidence,
                entry_time_utc=moment,
                exit_time_utc=exit_time,
                outcome_status=outcome.status,
                realized_pnl_usd=realized,
                conservative_loss_usd=_conservative_loss_usd(
                    signal, config.notional, config.cost
                ),
                parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
            )
        )

    resolved_tp = sum(
        1 for t in trades if t.outcome_status is OutcomeStatus.RESOLVED_TP
    )
    resolved_sl = sum(
        1 for t in trades if t.outcome_status is OutcomeStatus.RESOLVED_SL
    )
    ambiguous = sum(
        1
        for t in trades
        if t.outcome_status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS
    )
    unresolved = sum(
        1
        for t in trades
        if t.outcome_status is OutcomeStatus.UNRESOLVED_DATA_GAP
    )
    realized_values = [
        t.realized_pnl_usd for t in trades if t.realized_pnl_usd is not None
    ]
    net = sum(realized_values)
    gains = sum(v for v in realized_values if v > 0)
    losses = -sum(v for v in realized_values if v < 0)
    resolved = resolved_tp + resolved_sl
    win_rate = resolved_tp / resolved if resolved else None
    profit_factor = (gains / losses) if losses > 0 else None

    equity = config.initial_equity_usd
    peak = equity
    max_drawdown = 0.0
    losing_streak = 0
    longest_losing_streak = 0
    for trade in trades:
        if trade.realized_pnl_usd is None:
            continue
        equity += trade.realized_pnl_usd
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        if trade.realized_pnl_usd < 0:
            losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, losing_streak)
        else:
            losing_streak = 0

    # Scenario-only conservative treatment: ambiguous outcomes counted as
    # full stop-loss losses. The factual net above never includes this.
    scenario_net = net - sum(
        t.conservative_loss_usd
        for t in trades
        if t.outcome_status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS
    )

    return ReplayResult(
        config=config,
        replay_version=REPLAY_ENGINE_VERSION,
        trades=tuple(trades),
        events=tuple(events),
        signal_count=len(ordered),
        entered_count=len(trades),
        skipped_confidence_count=skipped_confidence,
        blocked_existing_position_count=blocked,
        resolved_tp_count=resolved_tp,
        resolved_sl_count=resolved_sl,
        unresolved_count=unresolved,
        ambiguous_count=ambiguous,
        net_pnl_usd=net,
        scenario_conservative_net_pnl_usd=scenario_net,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown_usd=max_drawdown,
        longest_losing_streak=longest_losing_streak,
        final_equity_usd=equity,
        insufficient_sample=resolved < minimum_sample,
        minimum_sample=minimum_sample,
    )


def sweep_thresholds(
    signals: Sequence[SignalRecordV2],
    outcomes: Mapping[str, SignalOutcome],
    *,
    base_config: ReplayConfig | None = None,
    thresholds: Sequence[int] = tuple(range(50, 100)),
    minimum_sample: int = DEFAULT_MINIMUM_SAMPLE,
) -> ThresholdSweep:
    """Replay every threshold and prefer stable neighbouring regions.

    Thresholds whose resolved sample is below ``minimum_sample`` are
    marked ``INSUFFICIENT_SAMPLE`` and excluded from the recommendation
    entirely — a tiny sample is never ranked as a winner. Among the
    remainder, the recommended threshold maximizes the mean net P&L of
    its neighbourhood (itself plus adjacent swept thresholds), not its
    own single maximum-profit result.
    """
    template = base_config or ReplayConfig(threshold=50)
    rows: list[ThresholdSweepRow] = []
    results: dict[int, ReplayResult] = {}
    for threshold in thresholds:
        config = ReplayConfig(
            threshold=int(threshold),
            occupancy=template.occupancy,
            notional=template.notional,
            cost=template.cost,
            initial_equity_usd=template.initial_equity_usd,
        )
        result = replay_signals(
            signals, outcomes, config, minimum_sample=minimum_sample
        )
        results[int(threshold)] = result
        rows.append(
            ThresholdSweepRow(
                threshold=int(threshold),
                entered_count=result.entered_count,
                skipped_confidence_count=result.skipped_confidence_count,
                blocked_existing_position_count=(
                    result.blocked_existing_position_count
                ),
                net_pnl_usd=result.net_pnl_usd,
                scenario_conservative_net_pnl_usd=(
                    result.scenario_conservative_net_pnl_usd
                ),
                win_rate=result.win_rate,
                max_drawdown_usd=result.max_drawdown_usd,
                insufficient_sample=result.insufficient_sample,
            )
        )

    swept = sorted(results)
    enriched: list[ThresholdSweepRow] = []
    for row in rows:
        index = swept.index(row.threshold)
        neighbourhood = [
            results[swept[i]].net_pnl_usd
            for i in (index - 1, index, index + 1)
            if 0 <= i < len(swept)
        ]
        enriched.append(
            ThresholdSweepRow(
                threshold=row.threshold,
                entered_count=row.entered_count,
                skipped_confidence_count=row.skipped_confidence_count,
                blocked_existing_position_count=(
                    row.blocked_existing_position_count
                ),
                net_pnl_usd=row.net_pnl_usd,
                scenario_conservative_net_pnl_usd=(
                    row.scenario_conservative_net_pnl_usd
                ),
                win_rate=row.win_rate,
                max_drawdown_usd=row.max_drawdown_usd,
                insufficient_sample=row.insufficient_sample,
                neighbourhood_net_pnl_usd=(
                    sum(neighbourhood) / len(neighbourhood)
                    if neighbourhood
                    else None
                ),
            )
        )

    eligible = [row for row in enriched if not row.insufficient_sample]
    recommended: int | None = None
    stable_region: tuple[int, ...] = ()
    if eligible:
        best = max(
            eligible,
            key=lambda row: (
                row.neighbourhood_net_pnl_usd
                if row.neighbourhood_net_pnl_usd is not None
                else row.net_pnl_usd
            ),
        )
        recommended = best.threshold
        stable_region = tuple(
            row.threshold
            for row in eligible
            if abs(row.threshold - best.threshold) <= 2
            and row.net_pnl_usd > 0
        )
    return ThresholdSweep(
        rows=tuple(enriched),
        minimum_sample=minimum_sample,
        recommended_threshold=recommended,
        stable_region=stable_region,
    )
