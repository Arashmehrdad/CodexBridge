"""Independent per-signal outcome resolution from retained ticks.

Each directional signal resolves on its own from retained or recovered
historical ticks — there are no runtime portfolios, thresholds, or
occupancy rules here. Resolution never observes a tick or candle earlier
than the signal's entry time, processes observations chronologically,
uses honest prices (LONG enters at ask and exits/tests on bid; SHORT
enters at bid and exits/tests on ask; spread is never subtracted twice),
and produces durable outcome evidence with the entry tick, the first
boundary-touch tick, the exit tick, the tick-range hash, the source, and
the gap status. Ambiguous outcomes stay factual unknowns.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from .signal_journal_v2 import SignalDecisionV2, SignalRecordV2
from .tick_archive import ArchivedTick, _tick_line
from .versions import RESOLVER_VERSION

UTC = timezone.utc
DEFAULT_MAX_GAP_SECONDS = 300.0


class OutcomeStatus(str, Enum):
    RESOLVED_TP = "RESOLVED_TP"
    RESOLVED_SL = "RESOLVED_SL"
    UNRESOLVED_DATA_GAP = "UNRESOLVED_DATA_GAP"
    AMBIGUOUS_WITHOUT_TICKS = "AMBIGUOUS_WITHOUT_TICKS"


RESOLVED_STATUSES = frozenset(
    {OutcomeStatus.RESOLVED_TP, OutcomeStatus.RESOLVED_SL}
)


@dataclass(frozen=True)
class PriceRange:
    """A candle-derived observation window used only as a tick fallback."""

    start_utc: datetime
    end_utc: datetime
    low: float
    high: float


@dataclass(frozen=True)
class SignalOutcome:
    signal_id: str
    symbol: str
    decision: SignalDecisionV2
    experiment_id: str
    parent_h4_raw_open_epoch: int
    entry_time_utc: datetime
    entry_price: float | None
    stop_loss: float
    take_profit: float
    status: OutcomeStatus
    exit_time_utc: datetime | None
    exit_price: float | None
    realized_return_fraction: float | None
    range_hash: str
    observed_tick_count: int
    source: str
    gap_status: str
    resolver_version: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _tick_evidence(tick: ArchivedTick) -> dict[str, Any]:
    return {
        "raw_epoch_seconds": tick.raw_epoch_seconds,
        "broker_utc_offset_seconds": tick.broker_utc_offset_seconds,
        "normalized_utc": tick.normalized_utc.isoformat(),
        "bid": tick.bid,
        "ask": tick.ask,
        "source": tick.source,
    }


def signal_entry_time(signal: SignalRecordV2) -> datetime:
    """The moment a signal is considered entered for resolution purposes."""
    return signal.entered_at_utc or signal.submitted_at_utc


def resolve_from_ticks(
    signal: SignalRecordV2,
    ticks: Sequence[ArchivedTick],
    *,
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS,
) -> SignalOutcome:
    """Resolve one directional signal from chronological retained ticks."""
    decision = SignalDecisionV2(signal.decision)
    if decision is SignalDecisionV2.NO_TRADE:
        raise ValueError("NO_TRADE signals have no outcome to resolve")
    if signal.stop_loss is None or signal.take_profit is None:
        raise ValueError("directional signals require a stored fixed bracket")

    entry_time = signal_entry_time(signal)
    # Audit defect 2: observations earlier than the signal entry time are
    # excluded entirely, then everything is processed chronologically.
    usable = sorted(
        (
            tick
            for tick in ticks
            if tick.symbol == signal.symbol
            and tick.normalized_utc >= entry_time
        ),
        key=lambda tick: (tick.normalized_utc, tick.raw_epoch_seconds),
    )
    digest = sha256()
    for tick in usable:
        digest.update(_tick_line(tick).encode("utf-8"))
        digest.update(b"\n")
    range_hash = digest.hexdigest()

    stop = float(signal.stop_loss)
    target = float(signal.take_profit)

    if not usable:
        return SignalOutcome(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            decision=decision,
            experiment_id=signal.experiment_id,
            parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
            entry_time_utc=entry_time,
            entry_price=None,
            stop_loss=stop,
            take_profit=target,
            status=OutcomeStatus.UNRESOLVED_DATA_GAP,
            exit_time_utc=None,
            exit_price=None,
            realized_return_fraction=None,
            range_hash=range_hash,
            observed_tick_count=0,
            source="ticks",
            gap_status="no_ticks_after_entry",
            resolver_version=RESOLVER_VERSION,
            evidence={"gaps": [], "entry_time_utc": entry_time.isoformat()},
        )

    entry_tick = usable[0]
    # Honest execution: LONG enters at ask, SHORT enters at bid.
    entry_price = (
        entry_tick.ask if decision is SignalDecisionV2.LONG else entry_tick.bid
    )

    gaps: list[dict[str, Any]] = []
    previous = entry_tick.normalized_utc
    touch_tick: ArchivedTick | None = None
    touch_status: OutcomeStatus | None = None
    gap_before_touch = False
    for tick in usable:
        delta = (tick.normalized_utc - previous).total_seconds()
        if delta > max_gap_seconds:
            gaps.append(
                {
                    "start_utc": previous.isoformat(),
                    "end_utc": tick.normalized_utc.isoformat(),
                    "gap_seconds": delta,
                }
            )
        previous = tick.normalized_utc
        # Exits/tests happen on the opposite side of the entry: LONG on
        # bid, SHORT on ask. Spread is embedded exactly once.
        if decision is SignalDecisionV2.LONG:
            observed = tick.bid
            if observed <= stop:
                touch_tick, touch_status = tick, OutcomeStatus.RESOLVED_SL
            elif observed >= target:
                touch_tick, touch_status = tick, OutcomeStatus.RESOLVED_TP
        else:
            observed = tick.ask
            if observed >= stop:
                touch_tick, touch_status = tick, OutcomeStatus.RESOLVED_SL
            elif observed <= target:
                touch_tick, touch_status = tick, OutcomeStatus.RESOLVED_TP
        if touch_tick is not None:
            gap_before_touch = bool(gaps)
            break

    if touch_tick is None or touch_status is None:
        return SignalOutcome(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            decision=decision,
            experiment_id=signal.experiment_id,
            parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
            entry_time_utc=entry_time,
            entry_price=entry_price,
            stop_loss=stop,
            take_profit=target,
            status=OutcomeStatus.UNRESOLVED_DATA_GAP,
            exit_time_utc=None,
            exit_price=None,
            realized_return_fraction=None,
            range_hash=range_hash,
            observed_tick_count=len(usable),
            source="ticks",
            gap_status="coverage_ended_without_boundary",
            resolver_version=RESOLVER_VERSION,
            evidence={
                "entry_tick": _tick_evidence(entry_tick),
                "gaps": gaps,
                "last_observed_utc": usable[-1].normalized_utc.isoformat(),
            },
        )

    # A fixed bracket exits at the first boundary touch; the exit price
    # is the honestly observed opposite-side price of that exact tick,
    # which includes gap slippage instead of pretending the bracket
    # filled at its nominal level.
    exit_price = (
        touch_tick.bid
        if decision is SignalDecisionV2.LONG
        else touch_tick.ask
    )
    realized = (
        (exit_price - entry_price) / entry_price
        if decision is SignalDecisionV2.LONG
        else (entry_price - exit_price) / entry_price
    )
    return SignalOutcome(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        decision=decision,
        experiment_id=signal.experiment_id,
        parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
        entry_time_utc=entry_time,
        entry_price=entry_price,
        stop_loss=stop,
        take_profit=target,
        status=touch_status,
        exit_time_utc=touch_tick.normalized_utc,
        exit_price=exit_price,
        realized_return_fraction=realized,
        range_hash=range_hash,
        observed_tick_count=len(usable),
        source="ticks",
        gap_status="gap_before_touch" if gap_before_touch else "continuous",
        resolver_version=RESOLVER_VERSION,
        evidence={
            "entry_tick": _tick_evidence(entry_tick),
            "first_touch_tick": _tick_evidence(touch_tick),
            "exit_tick": _tick_evidence(touch_tick),
            "gaps": gaps,
        },
    )


def resolve_from_ranges(
    signal: SignalRecordV2,
    ranges: Sequence[PriceRange],
) -> SignalOutcome:
    """Candle-range fallback when no tick evidence exists for a window.

    Ranges overlapping the entry moment cannot order their extremes
    against the entry, so any boundary touch inside them is ambiguous.
    A fully post-entry range containing both boundaries is ambiguous as
    well; only a single-boundary range resolves, at the nominal boundary
    price, and the outcome records that no tick evidence backed it.
    """
    decision = SignalDecisionV2(signal.decision)
    if decision is SignalDecisionV2.NO_TRADE:
        raise ValueError("NO_TRADE signals have no outcome to resolve")
    if signal.stop_loss is None or signal.take_profit is None:
        raise ValueError("directional signals require a stored fixed bracket")

    entry_time = signal_entry_time(signal)
    stop = float(signal.stop_loss)
    target = float(signal.take_profit)
    entry_price = (
        float(signal.ask)
        if decision is SignalDecisionV2.LONG
        else float(signal.bid)
    )
    # Audit defect 2: ranges that end before entry are discarded, and the
    # remainder is processed chronologically.
    usable = sorted(
        (r for r in ranges if _aware(r.end_utc, "end_utc") > entry_time),
        key=lambda r: r.start_utc,
    )

    def outcome(
        status: OutcomeStatus,
        *,
        exit_time: datetime | None,
        exit_price: float | None,
        gap_status: str,
        evidence: dict[str, Any],
    ) -> SignalOutcome:
        realized = None
        if exit_price is not None and status in RESOLVED_STATUSES:
            realized = (
                (exit_price - entry_price) / entry_price
                if decision is SignalDecisionV2.LONG
                else (entry_price - exit_price) / entry_price
            )
        return SignalOutcome(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            decision=decision,
            experiment_id=signal.experiment_id,
            parent_h4_raw_open_epoch=signal.parent_h4_raw_open_epoch,
            entry_time_utc=entry_time,
            entry_price=entry_price,
            stop_loss=stop,
            take_profit=target,
            status=status,
            exit_time_utc=exit_time,
            exit_price=exit_price,
            realized_return_fraction=realized,
            range_hash="",
            observed_tick_count=0,
            source="candle_range",
            gap_status=gap_status,
            resolver_version=RESOLVER_VERSION,
            evidence=evidence,
        )

    for price_range in usable:
        low = float(price_range.low)
        high = float(price_range.high)
        if decision is SignalDecisionV2.LONG:
            stop_hit = low <= stop
            target_hit = high >= target
        else:
            stop_hit = high >= stop
            target_hit = low <= target
        spans_entry = _aware(price_range.start_utc, "start_utc") < entry_time
        range_evidence = {
            "range": {
                "start_utc": price_range.start_utc.isoformat(),
                "end_utc": price_range.end_utc.isoformat(),
                "low": low,
                "high": high,
            }
        }
        if spans_entry and (stop_hit or target_hit):
            return outcome(
                OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS,
                exit_time=None,
                exit_price=None,
                gap_status="entry_spanning_range_touch",
                evidence=range_evidence,
            )
        if stop_hit and target_hit:
            return outcome(
                OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS,
                exit_time=None,
                exit_price=None,
                gap_status="double_boundary_range",
                evidence=range_evidence,
            )
        if stop_hit:
            return outcome(
                OutcomeStatus.RESOLVED_SL,
                exit_time=_aware(price_range.end_utc, "end_utc"),
                exit_price=stop,
                gap_status="range_only",
                evidence=range_evidence,
            )
        if target_hit:
            return outcome(
                OutcomeStatus.RESOLVED_TP,
                exit_time=_aware(price_range.end_utc, "end_utc"),
                exit_price=target,
                gap_status="range_only",
                evidence=range_evidence,
            )
    return outcome(
        OutcomeStatus.UNRESOLVED_DATA_GAP,
        exit_time=None,
        exit_price=None,
        gap_status="no_range_boundary",
        evidence={"ranges_examined": len(usable)},
    )


class SignalOutcomeJournal:
    """Durable exactly-once outcome journal with honest upgrades only.

    A resolved outcome is immutable. ``UNRESOLVED_DATA_GAP`` may be
    upgraded by any later resolution, and ``AMBIGUOUS_WITHOUT_TICKS`` may
    be upgraded only by tick-backed resolution — recovered real ticks
    remove the ambiguity; another candle range never does.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_signal_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    parent_h4_raw_open_epoch INTEGER NOT NULL,
                    entry_time_utc TEXT NOT NULL,
                    entry_price REAL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    status TEXT NOT NULL,
                    exit_time_utc TEXT,
                    exit_price REAL,
                    realized_return_fraction REAL,
                    range_hash TEXT NOT NULL,
                    observed_tick_count INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    gap_status TEXT NOT NULL,
                    resolver_version TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_signal_outcomes_exp"
                " ON trading_signal_outcomes(experiment_id, entry_time_utc)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_signal_outcome_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def record(
        self,
        outcome: SignalOutcome,
        *,
        recorded_at_utc: datetime | None = None,
    ) -> SignalOutcome:
        recorded = _aware(
            recorded_at_utc or datetime.now(UTC), "recorded_at_utc"
        )
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM trading_signal_outcomes WHERE signal_id = ?",
                (outcome.signal_id,),
            ).fetchone()
            if row is not None:
                current = self._row_to_outcome(row)
                if current.status in RESOLVED_STATUSES:
                    conn.rollback()
                    if (
                        outcome.status == current.status
                        and outcome.exit_price == current.exit_price
                    ):
                        return current
                    raise RuntimeError(
                        f"outcome for {outcome.signal_id} is already resolved"
                        " and immutable"
                    )
                if current.status is OutcomeStatus.AMBIGUOUS_WITHOUT_TICKS:
                    upgrade_allowed = (
                        outcome.source == "ticks"
                        and outcome.status in RESOLVED_STATUSES
                    )
                    if not upgrade_allowed:
                        conn.rollback()
                        return current
                # UNRESOLVED_DATA_GAP upgrades freely; the ambiguous case
                # was gated above.
                conn.execute(
                    "DELETE FROM trading_signal_outcomes WHERE signal_id = ?",
                    (outcome.signal_id,),
                )
                self._append_event(
                    conn,
                    outcome.signal_id,
                    "outcome_superseded",
                    recorded,
                    {
                        "previous_status": current.status.value,
                        "new_status": outcome.status.value,
                    },
                )
            outcome_id = (
                "out_"
                + sha256(outcome.signal_id.encode("utf-8")).hexdigest()[:24]
            )
            conn.execute(
                """
                INSERT INTO trading_signal_outcomes (
                    outcome_id, signal_id, symbol, decision, experiment_id,
                    parent_h4_raw_open_epoch, entry_time_utc, entry_price,
                    stop_loss, take_profit, status, exit_time_utc, exit_price,
                    realized_return_fraction, range_hash, observed_tick_count,
                    source, gap_status, resolver_version, evidence_json,
                    recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome_id,
                    outcome.signal_id,
                    outcome.symbol,
                    outcome.decision.value,
                    outcome.experiment_id,
                    outcome.parent_h4_raw_open_epoch,
                    outcome.entry_time_utc.isoformat(),
                    outcome.entry_price,
                    outcome.stop_loss,
                    outcome.take_profit,
                    outcome.status.value,
                    (
                        outcome.exit_time_utc.isoformat()
                        if outcome.exit_time_utc
                        else None
                    ),
                    outcome.exit_price,
                    outcome.realized_return_fraction,
                    outcome.range_hash,
                    outcome.observed_tick_count,
                    outcome.source,
                    outcome.gap_status,
                    outcome.resolver_version,
                    json.dumps(
                        outcome.evidence,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    recorded.isoformat(),
                ),
            )
            self._append_event(
                conn,
                outcome.signal_id,
                "outcome_recorded",
                recorded,
                {"status": outcome.status.value, "source": outcome.source},
            )
            conn.commit()
        return self.get(outcome.signal_id)

    def get(self, signal_id: str) -> SignalOutcome:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_signal_outcomes WHERE signal_id = ?",
                (str(signal_id).strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Outcome not found for signal: {signal_id}")
        return self._row_to_outcome(row)

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: OutcomeStatus | None = None,
        experiment_id: str | None = None,
    ) -> list[SignalOutcome]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must not be negative")
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(OutcomeStatus(status).value)
        if experiment_id is not None:
            clauses.append("experiment_id = ?")
            params.append(str(experiment_id).strip())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_signal_outcomes"
                + where
                + " ORDER BY entry_time_utc, signal_id LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_outcome(row) for row in rows]

    def count(self, *, experiment_id: str | None = None) -> int:
        where = " WHERE experiment_id = ?" if experiment_id is not None else ""
        params = (
            (str(experiment_id).strip(),) if experiment_id is not None else ()
        )
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM trading_signal_outcomes" + where,
                params,
            ).fetchone()
        return int(row["n"])

    def events(self, signal_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, occurred_at_utc, data_json"
                " FROM trading_signal_outcome_events WHERE signal_id = ?"
                " ORDER BY id",
                (str(signal_id).strip(),),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "event_type": str(row["event_type"]),
                "occurred_at_utc": _parse_utc(str(row["occurred_at_utc"])),
                "data": json.loads(str(row["data_json"])),
            }
            for row in rows
        ]

    @staticmethod
    def _append_event(
        conn: sqlite3.Connection,
        signal_id: str,
        event_type: str,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO trading_signal_outcome_events"
            " (signal_id, event_type, occurred_at_utc, data_json)"
            " VALUES (?, ?, ?, ?)",
            (
                signal_id,
                event_type,
                occurred_at.isoformat(),
                json.dumps(data, sort_keys=True, separators=(",", ":")),
            ),
        )

    @staticmethod
    def _row_to_outcome(row: sqlite3.Row) -> SignalOutcome:
        return SignalOutcome(
            signal_id=str(row["signal_id"]),
            symbol=str(row["symbol"]),
            decision=SignalDecisionV2(str(row["decision"])),
            experiment_id=str(row["experiment_id"]),
            parent_h4_raw_open_epoch=int(row["parent_h4_raw_open_epoch"]),
            entry_time_utc=_parse_utc(str(row["entry_time_utc"])),
            entry_price=(
                float(row["entry_price"])
                if row["entry_price"] is not None
                else None
            ),
            stop_loss=float(row["stop_loss"]),
            take_profit=float(row["take_profit"]),
            status=OutcomeStatus(str(row["status"])),
            exit_time_utc=(
                _parse_utc(str(row["exit_time_utc"]))
                if row["exit_time_utc"]
                else None
            ),
            exit_price=(
                float(row["exit_price"])
                if row["exit_price"] is not None
                else None
            ),
            realized_return_fraction=(
                float(row["realized_return_fraction"])
                if row["realized_return_fraction"] is not None
                else None
            ),
            range_hash=str(row["range_hash"]),
            observed_tick_count=int(row["observed_tick_count"]),
            source=str(row["source"]),
            gap_status=str(row["gap_status"]),
            resolver_version=str(row["resolver_version"]),
            evidence=json.loads(str(row["evidence_json"])),
        )
