from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from hashlib import sha256

from .signal_journal import SignalDecision, SignalJournal, SignalStatus
from .threshold_simulator import THRESHOLDS
from .trade_supervisor import TradingLabSupervisor
from .virtual_position_journal import PositionStatus

UTC = timezone.utc
REPORT_VERSION = "tl6.1"
MONEY_PLACES = Decimal("0.00000001")
RATIO_PLACES = Decimal("0.0001")
CONFIDENCE_BANDS = ((50, 59), (60, 69), (70, 79), (80, 89), (90, 99))


def _quantize(value: Decimal, places: Decimal) -> str:
    return format(value.quantize(places, rounding=ROUND_HALF_EVEN), "f")


def _ratio(numerator: Decimal, denominator: Decimal) -> str | None:
    if denominator == 0:
        return None
    return _quantize(numerator / denominator, RATIO_PLACES)


def _within(
    moment: datetime,
    period_start: datetime | None,
    period_end: datetime | None,
) -> bool:
    if period_start is not None and moment < period_start:
        return False
    if period_end is not None and moment >= period_end:
        return False
    return True


def build_threshold_report(
    supervisor: TradingLabSupervisor,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict:
    """Deterministic evaluation report rebuilt from the append-only journals.

    Identical journal content always produces byte-identical canonical
    output and the same content hash; nothing is read from wall clocks,
    providers, or cached state. Ambiguous outcomes are counted and
    excluded from every P&L metric rather than silently dropped.
    """
    for name, moment in (
        ("period_start", period_start),
        ("period_end", period_end),
    ):
        if moment is not None and moment.tzinfo is None:
            raise ValueError(f"{name} must be timezone-aware")
    cohort = supervisor.active_cohort()
    if cohort is None:
        raise RuntimeError("initialize the experiment before reporting")

    signals = _signal_index(supervisor.signals)
    positions = _cohort_positions(supervisor, cohort.cohort_id)

    thresholds: dict[str, dict] = {}
    for threshold in THRESHOLDS:
        thresholds[f"T{threshold}"] = _threshold_metrics(
            threshold,
            cohort.baseline_equity,
            signals,
            [p for p in positions if p["threshold"] == threshold],
            period_start,
            period_end,
        )

    net_by_threshold = {
        threshold: Decimal(thresholds[f"T{threshold}"]["net_pnl"])
        for threshold in THRESHOLDS
    }
    for threshold in THRESHOLDS:
        neighbours = [
            net_by_threshold[t]
            for t in (threshold - 1, threshold, threshold + 1)
            if t in net_by_threshold
        ]
        thresholds[f"T{threshold}"]["neighbourhood_net_pnl"] = _quantize(
            sum(neighbours, Decimal("0")) / Decimal(len(neighbours)),
            MONEY_PLACES,
        )

    body = {
        "report_version": REPORT_VERSION,
        "cohort_id": cohort.cohort_id,
        "baseline_equity": str(cohort.baseline_equity),
        "currency": cohort.currency,
        "period_start": (
            period_start.astimezone(UTC).isoformat()
            if period_start
            else None
        ),
        "period_end": (
            period_end.astimezone(UTC).isoformat() if period_end else None
        ),
        "thresholds": thresholds,
    }
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    body["content_hash"] = sha256(canonical.encode("utf-8")).hexdigest()
    return body


def _signal_index(journal: SignalJournal) -> list[dict]:
    records = journal.list(limit=1000)
    return [
        {
            "signal_id": record.signal_id,
            "decision": record.draft.decision,
            "confidence": record.draft.confidence,
            "status": record.status,
            "created_at_utc": record.draft.created_at_utc,
        }
        for record in records
    ]


def _cohort_positions(
    supervisor: TradingLabSupervisor, cohort_id: str
) -> list[dict]:
    with supervisor.positions.connect() as conn:
        rows = conn.execute(
            """
            SELECT threshold, signal_id, status, entry_price, stop_loss,
                   take_profit, realized_return, opened_at_utc,
                   resolved_at_utc
            FROM trading_virtual_positions
            WHERE cohort_id = ?
            ORDER BY opened_at_utc, position_id
            """,
            (cohort_id,),
        ).fetchall()
    return [
        {
            "threshold": int(row["threshold"]),
            "signal_id": str(row["signal_id"]),
            "status": PositionStatus(str(row["status"])),
            "entry_price": Decimal(str(row["entry_price"])),
            "stop_loss": Decimal(str(row["stop_loss"])),
            "take_profit": Decimal(str(row["take_profit"])),
            "realized_return": (
                Decimal(str(row["realized_return"]))
                if row["realized_return"] is not None
                else None
            ),
            "opened_at_utc": datetime.fromisoformat(
                str(row["opened_at_utc"])
            ),
            "resolved_at_utc": (
                datetime.fromisoformat(str(row["resolved_at_utc"]))
                if row["resolved_at_utc"]
                else None
            ),
        }
        for row in rows
    ]


def _threshold_metrics(
    threshold: int,
    baseline_equity: Decimal,
    signals: list[dict],
    positions: list[dict],
    period_start: datetime | None,
    period_end: datetime | None,
) -> dict:
    eligible_signals = [
        s
        for s in signals
        if s["decision"] is not SignalDecision.NO_TRADE
        and s["status"] is not SignalStatus.CANCELLED
        and s["confidence"] is not None
        and s["confidence"] >= threshold
        and _within(s["created_at_utc"], period_start, period_end)
    ]
    entered = [
        p
        for p in positions
        if _within(p["opened_at_utc"], period_start, period_end)
    ]
    resolved = [
        p
        for p in entered
        if p["status"] is not PositionStatus.OPEN
        and p["resolved_at_utc"] is not None
        and _within(p["resolved_at_utc"], period_start, period_end)
    ]
    ambiguous = [
        p for p in resolved if p["status"] is PositionStatus.AMBIGUOUS_DATA
    ]
    settled = [
        p
        for p in resolved
        if p["status"] is not PositionStatus.AMBIGUOUS_DATA
        and p["realized_return"] is not None
    ]
    settled.sort(key=lambda p: (p["resolved_at_utc"], p["signal_id"]))

    wins = [p for p in settled if p["realized_return"] > 0]
    losses = [p for p in settled if p["realized_return"] < 0]
    net_pnl = sum(
        (p["realized_return"] for p in settled), Decimal("0")
    )
    gross_profit = sum(
        (p["realized_return"] for p in wins), Decimal("0")
    )
    gross_loss = -sum(
        (p["realized_return"] for p in losses), Decimal("0")
    )

    # Equity walk for drawdown and losing streak, in resolution order.
    equity = baseline_equity
    peak = baseline_equity
    max_drawdown = Decimal("0")
    losing_streak = 0
    longest_losing_streak = 0
    for position in settled:
        equity += position["realized_return"]
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        if position["realized_return"] < 0:
            losing_streak += 1
            longest_losing_streak = max(
                longest_losing_streak, losing_streak
            )
        else:
            losing_streak = 0

    stop_distances = [
        abs(p["entry_price"] - p["stop_loss"]) / p["entry_price"]
        for p in entered
    ]
    target_distances = [
        abs(p["take_profit"] - p["entry_price"]) / p["entry_price"]
        for p in entered
    ]
    risk_rewards = [
        (abs(p["take_profit"] - p["entry_price"]))
        / (abs(p["entry_price"] - p["stop_loss"]))
        for p in entered
        if p["entry_price"] != p["stop_loss"]
    ]

    monthly: dict[str, dict] = {}
    for position in settled:
        month = position["resolved_at_utc"].astimezone(UTC).strftime(
            "%Y-%m"
        )
        bucket = monthly.setdefault(
            month, {"trades": 0, "wins": 0, "losses": 0, "net": Decimal("0")}
        )
        bucket["trades"] += 1
        bucket["net"] += position["realized_return"]
        if position["realized_return"] > 0:
            bucket["wins"] += 1
        elif position["realized_return"] < 0:
            bucket["losses"] += 1

    signal_confidence = {
        s["signal_id"]: s["confidence"] for s in signals
    }
    bands: dict[str, dict] = {}
    for low, high in CONFIDENCE_BANDS:
        band_positions = [
            p
            for p in settled
            if signal_confidence.get(p["signal_id"]) is not None
            and low <= signal_confidence[p["signal_id"]] <= high
        ]
        band_net = sum(
            (p["realized_return"] for p in band_positions), Decimal("0")
        )
        bands[f"{low}-{high}"] = {
            "trades": len(band_positions),
            "net_pnl": _quantize(band_net, MONEY_PLACES),
        }

    return {
        "signal_count": len(eligible_signals),
        "entered_trade_count": len(entered),
        "resolved_trade_count": len(resolved),
        "ambiguous_trade_count": len(ambiguous),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": _ratio(
            Decimal(len(wins)), Decimal(len(wins) + len(losses))
        ),
        "net_pnl": _quantize(net_pnl, MONEY_PLACES),
        "average_return": (
            _quantize(net_pnl / Decimal(len(settled)), MONEY_PLACES)
            if settled
            else None
        ),
        "profit_factor": (
            _ratio(gross_profit, gross_loss) if gross_loss > 0 else None
        ),
        "max_drawdown": _quantize(max_drawdown, MONEY_PLACES),
        "longest_losing_streak": longest_losing_streak,
        "average_stop_distance": (
            _quantize(
                sum(stop_distances, Decimal("0"))
                / Decimal(len(stop_distances)),
                RATIO_PLACES,
            )
            if stop_distances
            else None
        ),
        "average_target_distance": (
            _quantize(
                sum(target_distances, Decimal("0"))
                / Decimal(len(target_distances)),
                RATIO_PLACES,
            )
            if target_distances
            else None
        ),
        "average_risk_reward": (
            _quantize(
                sum(risk_rewards, Decimal("0"))
                / Decimal(len(risk_rewards)),
                RATIO_PLACES,
            )
            if risk_rewards
            else None
        ),
        "monthly": {
            month: {
                "trades": bucket["trades"],
                "wins": bucket["wins"],
                "losses": bucket["losses"],
                "net_pnl": _quantize(bucket["net"], MONEY_PLACES),
            }
            for month, bucket in sorted(monthly.items())
        },
        "confidence_bands": bands,
    }
