"""The two Trading Lab reports over the immutable journals.

1. Signal-quality / confidence-calibration report: how well the model's
   stated confidence predicts resolved outcomes, grouped by confidence
   band and correlated by parent H4 candle.
2. Strategy replay report: deterministic offline replay across
   thresholds with occupancy effects, insufficient-sample marking, and
   stable-region preference.

Both reports support explicit historical experiment selection and
explicit period bounds. Period filtering uses a declared basis:
``resolution`` (the default for outcome metrics) includes positions
opened before the period but resolved within it; ``entry`` restricts to
positions entered within the period. Reports are canonical JSON with a
SHA-256 content hash and take no provider or wall-clock input.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .outcome_resolver import OutcomeStatus, SignalOutcome
from .replay_engine import (
    DEFAULT_MINIMUM_SAMPLE,
    ReplayConfig,
    sweep_thresholds,
)
from .signal_journal_v2 import SignalDecisionV2, SignalRecordV2
from .versions import (
    REPLAY_ENGINE_VERSION,
    RESOLVER_VERSION,
    SIGNAL_SCHEMA_VERSION,
)

UTC = timezone.utc
CONFIDENCE_BANDS = ((50, 59), (60, 69), (70, 79), (80, 89), (90, 99))
PERIOD_BASES = ("entry", "resolution")


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _round(value: float | None, digits: int = 8) -> float | None:
    return None if value is None else round(float(value), digits)


def _entry_moment(signal: SignalRecordV2) -> datetime:
    return signal.entered_at_utc or signal.submitted_at_utc


def _canonical_report(report: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    report["content_hash"] = sha256(body).hexdigest()
    return report


def _select_signals(
    signals: Sequence[SignalRecordV2],
    outcomes: Mapping[str, SignalOutcome],
    *,
    experiment_id: str | None,
    period_start_utc: datetime | None,
    period_end_utc: datetime | None,
    period_basis: str,
) -> list[SignalRecordV2]:
    if period_basis not in PERIOD_BASES:
        raise ValueError(f"period_basis must be one of {PERIOD_BASES}")
    start = (
        _aware(period_start_utc, "period_start_utc")
        if period_start_utc is not None
        else None
    )
    end = (
        _aware(period_end_utc, "period_end_utc")
        if period_end_utc is not None
        else None
    )
    if start is not None and end is not None and end <= start:
        raise ValueError("period_end_utc must be after period_start_utc")

    selected: list[SignalRecordV2] = []
    for signal in signals:
        if (
            experiment_id is not None
            and signal.experiment_id != experiment_id
        ):
            continue
        if start is None and end is None:
            selected.append(signal)
            continue
        entry = _entry_moment(signal)
        outcome = outcomes.get(signal.signal_id)
        if period_basis == "entry":
            anchor = entry
        else:
            # Resolution basis: a position opened before the period but
            # resolved within it belongs to the period. Unresolved
            # signals anchor on their entry moment.
            anchor = (
                outcome.exit_time_utc
                if outcome is not None and outcome.exit_time_utc is not None
                else entry
            )
        if start is not None and anchor < start:
            continue
        if end is not None and anchor >= end:
            continue
        selected.append(signal)
    return selected


def build_calibration_report(
    signals: Sequence[SignalRecordV2],
    outcomes: Mapping[str, SignalOutcome],
    *,
    experiment_id: str | None = None,
    rejection_count: int = 0,
    period_start_utc: datetime | None = None,
    period_end_utc: datetime | None = None,
    period_basis: str = "resolution",
) -> dict[str, Any]:
    """Signal-quality and confidence-calibration report."""
    selected = _select_signals(
        signals,
        outcomes,
        experiment_id=experiment_id,
        period_start_utc=period_start_utc,
        period_end_utc=period_end_utc,
        period_basis=period_basis,
    )
    directional = [
        s for s in selected if s.decision is not SignalDecisionV2.NO_TRADE
    ]
    no_trade_count = len(selected) - len(directional)

    bands: list[dict[str, Any]] = []
    for low, high in CONFIDENCE_BANDS:
        members = [
            s
            for s in directional
            if s.confidence is not None and low <= s.confidence <= high
        ]
        tp = sl = ambiguous = unresolved = missing = 0
        realized: list[float] = []
        risk_rewards = [
            s.risk_reward for s in members if s.risk_reward is not None
        ]
        for signal in members:
            outcome = outcomes.get(signal.signal_id)
            if outcome is None:
                missing += 1
            elif outcome.status is OutcomeStatus.RESOLVED_TP:
                tp += 1
                if outcome.realized_return_fraction is not None:
                    realized.append(outcome.realized_return_fraction)
            elif outcome.status is OutcomeStatus.RESOLVED_SL:
                sl += 1
                if outcome.realized_return_fraction is not None:
                    realized.append(outcome.realized_return_fraction)
            elif outcome.status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS:
                ambiguous += 1
            else:
                unresolved += 1
        resolved = tp + sl
        bands.append(
            {
                "band": f"{low}-{high}",
                "signal_count": len(members),
                "resolved_tp": tp,
                "resolved_sl": sl,
                "ambiguous_without_ticks": ambiguous,
                "unresolved_data_gap": unresolved,
                "missing_outcome": missing,
                "tp_rate": _round(tp / resolved) if resolved else None,
                "average_risk_reward": (
                    _round(sum(risk_rewards) / len(risk_rewards))
                    if risk_rewards
                    else None
                ),
                "average_realized_return_fraction": (
                    _round(sum(realized) / len(realized))
                    if realized
                    else None
                ),
            }
        )

    # Parent H4 correlation: several signals sharing one parent candle
    # are correlated observations, not independent samples.
    by_parent: dict[int, int] = {}
    for signal in directional:
        by_parent[signal.parent_h4_raw_open_epoch] = (
            by_parent.get(signal.parent_h4_raw_open_epoch, 0) + 1
        )
    parent_counts = sorted(by_parent.values(), reverse=True)

    report: dict[str, Any] = {
        "report": "signal_confidence_calibration",
        "signal_schema_version": SIGNAL_SCHEMA_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "experiment_id": experiment_id,
        "period_start_utc": (
            _aware(period_start_utc, "period_start_utc").isoformat()
            if period_start_utc
            else None
        ),
        "period_end_utc": (
            _aware(period_end_utc, "period_end_utc").isoformat()
            if period_end_utc
            else None
        ),
        "period_basis": period_basis,
        "selected_signal_count": len(selected),
        "directional_signal_count": len(directional),
        "no_trade_count": no_trade_count,
        "rejected_submission_count": int(rejection_count),
        "confidence_bands": bands,
        "parent_h4_groups": {
            "distinct_parent_candles": len(by_parent),
            "max_signals_per_candle": parent_counts[0] if parent_counts else 0,
            "candles_with_multiple_signals": sum(
                1 for count in parent_counts if count > 1
            ),
        },
    }
    return _canonical_report(report)


def build_replay_report(
    signals: Sequence[SignalRecordV2],
    outcomes: Mapping[str, SignalOutcome],
    *,
    experiment_id: str | None = None,
    base_config: ReplayConfig | None = None,
    thresholds: Sequence[int] = tuple(range(50, 100)),
    minimum_sample: int = DEFAULT_MINIMUM_SAMPLE,
    period_start_utc: datetime | None = None,
    period_end_utc: datetime | None = None,
    period_basis: str = "resolution",
) -> dict[str, Any]:
    """Deterministic strategy replay report with occupancy effects."""
    selected = _select_signals(
        signals,
        outcomes,
        experiment_id=experiment_id,
        period_start_utc=period_start_utc,
        period_end_utc=period_end_utc,
        period_basis=period_basis,
    )
    template = base_config or ReplayConfig(threshold=50)
    sweep = sweep_thresholds(
        selected,
        outcomes,
        base_config=template,
        thresholds=thresholds,
        minimum_sample=minimum_sample,
    )
    rows = [
        {
            "threshold": row.threshold,
            "entered_count": row.entered_count,
            "skipped_confidence_count": row.skipped_confidence_count,
            "blocked_existing_position_count": (
                row.blocked_existing_position_count
            ),
            "net_pnl_usd": _round(row.net_pnl_usd),
            "scenario_conservative_net_pnl_usd": _round(
                row.scenario_conservative_net_pnl_usd
            ),
            "win_rate": _round(row.win_rate),
            "max_drawdown_usd": _round(row.max_drawdown_usd),
            "insufficient_sample": row.insufficient_sample,
            "neighbourhood_net_pnl_usd": _round(
                row.neighbourhood_net_pnl_usd
            ),
        }
        for row in sweep.rows
    ]
    report: dict[str, Any] = {
        "report": "strategy_replay",
        "replay_version": REPLAY_ENGINE_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "cost_model_version": template.cost.version,
        "experiment_id": experiment_id,
        "period_start_utc": (
            _aware(period_start_utc, "period_start_utc").isoformat()
            if period_start_utc
            else None
        ),
        "period_end_utc": (
            _aware(period_end_utc, "period_end_utc").isoformat()
            if period_end_utc
            else None
        ),
        "period_basis": period_basis,
        "occupancy_allow_stacking": template.occupancy.allow_stacking,
        "notional_fixed_usd": _round(template.notional.fixed_notional_usd),
        "per_trade_cost_usd": _round(template.cost.per_trade_cost_usd),
        "initial_equity_usd": _round(template.initial_equity_usd),
        "selected_signal_count": len(selected),
        "minimum_sample": sweep.minimum_sample,
        "recommended_threshold": sweep.recommended_threshold,
        "stable_region": list(sweep.stable_region),
        "thresholds": rows,
        "note": (
            "scenario_conservative_net_pnl_usd treats ambiguous outcomes"
            " as full stop-loss losses; the factual net never does."
        ),
    }
    return _canonical_report(report)
