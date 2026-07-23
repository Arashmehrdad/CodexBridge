from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from .mt5_provider import MT5Provider
from .signal_journal import SignalDecision, SignalJournal, SignalStatus
from .threshold_simulator import (
    THRESHOLDS,
    CohortTransition,
    _currency,
    _money,
    _new_cohort,
)
from .virtual_position_journal import (
    HistoricalRange,
    PositionStatus,
    VirtualPosition,
    VirtualPositionJournal,
)

UTC = timezone.utc
NORMALIZED_STAKE_USD = Decimal("1.00")
MAX_COMBINED_ALLOCATION_RATIO = Decimal("0.20")


@dataclass(frozen=True)
class CohortRecord:
    cohort_id: str
    created_at_utc: datetime
    transition: CohortTransition
    baseline_equity: Decimal
    currency: str
    source_cohort_id: str | None


@dataclass(frozen=True)
class PortfolioState:
    threshold: int
    cohort_id: str
    baseline_equity: Decimal
    currency: str
    balance: Decimal
    open_position_id: str | None
    open_signal_id: str | None
    resolved_trades: int
    ambiguous_trades: int


@dataclass(frozen=True)
class EntryReport:
    signal_id: str
    entered_thresholds: tuple[int, ...]
    skipped_busy: tuple[int, ...]
    skipped_allocation_cap: tuple[int, ...]
    position_ids: tuple[str, ...]


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


class TradingLabSupervisor:
    """Deterministic durable trade supervisor for Trading Lab (TL5).

    This component performs no analysis. It opens eligible virtual
    positions from immutable entered signals, watches honest bid/ask
    prices, resolves each position exactly once through the durable
    position journal, and reconstructs threshold-portfolio state from the
    append-only journals after every restart instead of caching balances
    in memory. Ambiguous historical recovery becomes ``AMBIGUOUS_DATA``;
    the favourable outcome is never chosen silently.
    """

    def __init__(
        self,
        *,
        signal_journal: SignalJournal,
        position_journal: VirtualPositionJournal,
    ) -> None:
        self.signals = signal_journal
        self.positions = position_journal
        self._init_cohort_table()

    # -- cohort persistence -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return self.positions.connect()

    def _init_cohort_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_cohorts (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    cohort_id TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    transition TEXT NOT NULL,
                    baseline_equity TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    source_cohort_id TEXT
                )
                """
            )

    def active_cohort(self) -> CohortRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_cohorts ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return CohortRecord(
            cohort_id=str(row["cohort_id"]),
            created_at_utc=datetime.fromisoformat(
                str(row["created_at_utc"])
            ),
            transition=CohortTransition(str(row["transition"])),
            baseline_equity=Decimal(str(row["baseline_equity"])),
            currency=str(row["currency"]),
            source_cohort_id=(
                str(row["source_cohort_id"])
                if row["source_cohort_id"]
                else None
            ),
        )

    def initialize_from_health(
        self, health, *, now: datetime
    ) -> CohortRecord:
        if self.active_cohort() is not None:
            raise RuntimeError(
                "trading experiment is already initialized; use "
                "start_cohort for deposits, withdrawals, resets, or "
                "baseline changes"
            )
        if not health.initialized or not health.connected:
            raise RuntimeError("provider must be initialized and connected")
        if str(health.account_environment).strip().lower() != "demo":
            raise RuntimeError("threshold experiments require a demo account")
        if health.equity is None:
            raise RuntimeError("provider equity is unavailable")
        return self._persist_cohort(
            baseline_equity=health.equity,
            currency=health.currency,
            created_at_utc=now,
            transition=CohortTransition.INITIAL,
            source_cohort_id=None,
        )

    def start_cohort(
        self,
        *,
        transition: CohortTransition,
        baseline_equity,
        currency: str,
        now: datetime,
    ) -> CohortRecord:
        active = self.active_cohort()
        if active is None:
            raise RuntimeError("initialize the experiment before transitions")
        normalized_transition = CohortTransition(transition)
        if normalized_transition is CohortTransition.INITIAL:
            raise ValueError(
                "INITIAL is only valid for experiment initialization"
            )
        equity = _money(baseline_equity, "baseline_equity")
        normalized_currency = _currency(currency)
        if normalized_transition is CohortTransition.DEPOSIT:
            if (
                normalized_currency != active.currency
                or equity <= active.baseline_equity
            ):
                raise ValueError(
                    "deposit must increase equity without changing currency"
                )
        elif normalized_transition is CohortTransition.WITHDRAWAL:
            if (
                normalized_currency != active.currency
                or equity >= active.baseline_equity
            ):
                raise ValueError(
                    "withdrawal must decrease equity without changing "
                    "currency"
                )
        return self._persist_cohort(
            baseline_equity=equity,
            currency=normalized_currency,
            created_at_utc=now,
            transition=normalized_transition,
            source_cohort_id=active.cohort_id,
        )

    def _persist_cohort(
        self,
        *,
        baseline_equity,
        currency: str,
        created_at_utc: datetime,
        transition: CohortTransition,
        source_cohort_id: str | None,
    ) -> CohortRecord:
        # Reuse the frozen TL4 cohort identity and validation exactly.
        cohort = _new_cohort(
            baseline_equity=baseline_equity,
            currency=currency,
            created_at_utc=created_at_utc,
            transition=transition,
            source_cohort_id=source_cohort_id,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trading_cohorts (
                    cohort_id, created_at_utc, transition,
                    baseline_equity, currency, source_cohort_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cohort.cohort_id,
                    cohort.created_at_utc.isoformat(),
                    cohort.transition.value,
                    str(cohort.baseline_equity),
                    cohort.currency,
                    cohort.source_cohort_id,
                ),
            )
        return CohortRecord(
            cohort_id=cohort.cohort_id,
            created_at_utc=cohort.created_at_utc,
            transition=cohort.transition,
            baseline_equity=cohort.baseline_equity,
            currency=cohort.currency,
            source_cohort_id=cohort.source_cohort_id,
        )

    # -- portfolio reconstruction -------------------------------------------

    def portfolio_states(self) -> tuple[PortfolioState, ...]:
        """Rebuild every threshold portfolio from the append-only journals.

        Balance is baseline plus the sum of realized returns of resolved
        positions; ambiguous outcomes free the portfolio without any P&L.
        Nothing is cached, so a restarted supervisor observes exactly the
        state the journals prove.
        """
        cohort = self.active_cohort()
        if cohort is None:
            return ()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT threshold, status, realized_return, position_id,
                       signal_id
                FROM trading_virtual_positions
                WHERE cohort_id = ?
                ORDER BY opened_at_utc, position_id
                """,
                (cohort.cohort_id,),
            ).fetchall()
        realized: dict[int, Decimal] = {t: Decimal("0") for t in THRESHOLDS}
        resolved_counts: dict[int, int] = {t: 0 for t in THRESHOLDS}
        ambiguous_counts: dict[int, int] = {t: 0 for t in THRESHOLDS}
        open_ids: dict[int, tuple[str, str]] = {}
        for row in rows:
            threshold = int(row["threshold"])
            status = PositionStatus(str(row["status"]))
            if status is PositionStatus.OPEN:
                open_ids[threshold] = (
                    str(row["position_id"]),
                    str(row["signal_id"]),
                )
                continue
            if status is PositionStatus.AMBIGUOUS_DATA:
                ambiguous_counts[threshold] += 1
                resolved_counts[threshold] += 1
                continue
            resolved_counts[threshold] += 1
            if row["realized_return"] is not None:
                realized[threshold] += Decimal(str(row["realized_return"]))
        return tuple(
            PortfolioState(
                threshold=threshold,
                cohort_id=cohort.cohort_id,
                baseline_equity=cohort.baseline_equity,
                currency=cohort.currency,
                balance=cohort.baseline_equity + realized[threshold],
                open_position_id=(
                    open_ids.get(threshold, (None, None))[0]
                ),
                open_signal_id=(
                    open_ids.get(threshold, (None, None))[1]
                ),
                resolved_trades=resolved_counts[threshold],
                ambiguous_trades=ambiguous_counts[threshold],
            )
            for threshold in THRESHOLDS
        )

    # -- signal entry --------------------------------------------------------

    def enter_signal(self, signal_id: str, *, now: datetime) -> EntryReport:
        entered_at = _aware_utc(now, "now")
        record = self.signals.get(signal_id)
        if record.status is SignalStatus.CANCELLED:
            raise RuntimeError("cancelled signals cannot enter")
        if record.draft.decision is SignalDecision.NO_TRADE:
            return EntryReport(
                signal_id=signal_id,
                entered_thresholds=(),
                skipped_busy=(),
                skipped_allocation_cap=(),
                position_ids=(),
            )
        cohort = self.active_cohort()
        if cohort is None:
            raise RuntimeError("initialize the experiment before entries")
        confidence = record.draft.confidence
        if confidence is None:
            raise RuntimeError("trade signals require confidence")

        # Honest executable entry: long opens at ask, short opens at bid.
        entry_price = (
            Decimal(str(record.draft.ask))
            if record.draft.decision is SignalDecision.LONG
            else Decimal(str(record.draft.bid))
        )
        stop_loss = Decimal(str(record.draft.stop_loss))
        take_profit = Decimal(str(record.draft.take_profit))
        states = {
            state.threshold: state for state in self.portfolio_states()
        }

        entered: list[int] = []
        busy: list[int] = []
        capped: list[int] = []
        position_ids: list[str] = []
        for threshold in THRESHOLDS:
            if threshold > confidence:
                continue
            state = states[threshold]
            if state.open_position_id is not None:
                if state.open_signal_id != signal_id:
                    busy.append(threshold)
                    continue
                # Idempotent replay of this signal's own completed entry:
                # the journal returns the identical existing position.
                position = self.positions.get(state.open_position_id)
                entered.append(threshold)
                position_ids.append(position.position_id)
                continue
            if NORMALIZED_STAKE_USD > (
                state.balance * MAX_COMBINED_ALLOCATION_RATIO
            ):
                capped.append(threshold)
                continue
            try:
                position = self.positions.open_position(
                    idempotency_key=f"{signal_id}:T{threshold}",
                    cohort_id=cohort.cohort_id,
                    threshold=threshold,
                    signal_id=signal_id,
                    decision=record.draft.decision,
                    symbol=record.draft.symbol,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    normalized_stake_usd=NORMALIZED_STAKE_USD,
                    opened_at_utc=entered_at,
                )
            except RuntimeError:
                # The unique open-position index closed a race: another
                # entry holds this portfolio's symbol slot.
                busy.append(threshold)
                continue
            entered.append(threshold)
            position_ids.append(position.position_id)
        if entered:
            self.signals.mark_entered(signal_id, entered_at_utc=entered_at)
        return EntryReport(
            signal_id=signal_id,
            entered_thresholds=tuple(entered),
            skipped_busy=tuple(busy),
            skipped_allocation_cap=tuple(capped),
            position_ids=tuple(position_ids),
        )

    # -- monitoring and recovery --------------------------------------------

    def observe_tick(
        self,
        *,
        symbol: str,
        bid,
        ask,
        observed_at_utc: datetime,
    ) -> tuple[VirtualPosition, ...]:
        resolved: list[VirtualPosition] = []
        for position in self.positions.list_open():
            if position.symbol != symbol:
                continue
            outcome = self.positions.observe_tick(
                position.position_id,
                bid=bid,
                ask=ask,
                observed_at_utc=observed_at_utc,
            )
            if outcome.status is not PositionStatus.OPEN:
                resolved.append(outcome)
        return tuple(resolved)

    def recover_with_ticks(
        self,
        *,
        symbol: str,
        ticks: Sequence[tuple],
    ) -> tuple[VirtualPosition, ...]:
        """Replay recovered ticks in order; each is (bid, ask, at_utc)."""
        ordered = sorted(ticks, key=lambda tick: tick[2])
        resolved: dict[str, VirtualPosition] = {}
        for bid, ask, observed_at in ordered:
            for outcome in self.observe_tick(
                symbol=symbol,
                bid=bid,
                ask=ask,
                observed_at_utc=observed_at,
            ):
                resolved[outcome.position_id] = outcome
        return tuple(resolved.values())

    def recover_with_range(
        self,
        *,
        symbol: str,
        low,
        high,
        observed_at_utc: datetime,
    ) -> tuple[VirtualPosition, ...]:
        """Range fallback when tick ordering is unrecoverable.

        A range containing both boundaries resolves as AMBIGUOUS_DATA;
        the favourable outcome is never selected.
        """
        observed = _aware_utc(observed_at_utc, "observed_at_utc")
        historical_range = HistoricalRange(
            low=Decimal(str(low)),
            high=Decimal(str(high)),
            observed_at_utc=observed,
        )
        resolved: list[VirtualPosition] = []
        for position in self.positions.list_open():
            if position.symbol != symbol:
                continue
            outcome = self.positions.observe_historical_range(
                position.position_id, historical_range
            )
            if outcome.status is not PositionStatus.OPEN:
                resolved.append(outcome)
        return tuple(resolved)

    def recover_from_provider(
        self,
        provider: MT5Provider,
        *,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[VirtualPosition, ...]:
        """Recover downtime from provider history: ticks first, then range.

        Recovered ticks carry real bid/ask and preserve ordering. When no
        ticks are available for the window, the H4 candle range is the
        fallback and double-boundary candles surface as AMBIGUOUS_DATA.
        """
        start = _aware_utc(start_utc, "start_utc")
        end = _aware_utc(end_utc, "end_utc")
        if end <= start:
            raise ValueError("end_utc must be after start_utc")
        ticks = provider.historical_ticks(symbol, start, end)
        if ticks:
            return self.recover_with_ticks(
                symbol=symbol,
                ticks=[
                    (
                        tick.bid,
                        tick.ask,
                        tick.timestamp.normalized_utc,
                    )
                    for tick in ticks
                ],
            )
        completed, developing = provider.h4_candles(
            symbol, completed_count=100
        )
        window = [
            candle
            for candle in [*completed, developing]
            if candle is not None
            and start
            <= candle.open_time.normalized_utc
            <= end
        ]
        if not window:
            return ()
        low = min(Decimal(str(candle.low)) for candle in window)
        high = max(Decimal(str(candle.high)) for candle in window)
        return self.recover_with_range(
            symbol=symbol,
            low=low,
            high=high,
            observed_at_utc=end,
        )

    def open_positions(self) -> tuple[VirtualPosition, ...]:
        return tuple(self.positions.list_open())
