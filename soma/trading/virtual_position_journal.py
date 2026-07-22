from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from .signal_journal import SignalDecision


UTC = timezone.utc


class PositionStatus(str, Enum):
    OPEN = "open"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    AMBIGUOUS_DATA = "ambiguous_data"


@dataclass(frozen=True)
class VirtualPosition:
    position_id: str
    idempotency_key: str
    cohort_id: str
    threshold: int
    signal_id: str
    decision: SignalDecision
    symbol: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    normalized_stake_usd: Decimal
    opened_at_utc: datetime
    status: PositionStatus
    resolved_at_utc: datetime | None = None
    exit_price: Decimal | None = None
    realized_return: Decimal | None = None
    resolution_source: str = ""


@dataclass(frozen=True)
class HistoricalRange:
    low: Decimal
    high: Decimal
    observed_at_utc: datetime


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _text(value: str, field_name: str, *, maximum: int = 128) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return normalized


def _decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal") from exc
    if not normalized.is_finite() or normalized <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized


def _validate_open_prices(
    decision: SignalDecision,
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
) -> None:
    if decision is SignalDecision.NO_TRADE:
        raise ValueError("NO_TRADE cannot open a virtual position")
    if decision is SignalDecision.LONG and not stop_loss < entry_price < take_profit:
        raise ValueError("LONG requires stop_loss < entry_price < take_profit")
    if decision is SignalDecision.SHORT and not take_profit < entry_price < stop_loss:
        raise ValueError("SHORT requires take_profit < entry_price < stop_loss")


class VirtualPositionJournal:
    """Durable exact-once journal for Trading Lab virtual positions."""

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
                CREATE TABLE IF NOT EXISTS trading_virtual_positions (
                    position_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    cohort_id TEXT NOT NULL,
                    threshold INTEGER NOT NULL,
                    signal_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    entry_price TEXT NOT NULL,
                    stop_loss TEXT NOT NULL,
                    take_profit TEXT NOT NULL,
                    normalized_stake_usd TEXT NOT NULL,
                    opened_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_at_utc TEXT,
                    exit_price TEXT,
                    realized_return TEXT,
                    resolution_source TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_virtual_position_one_open
                ON trading_virtual_positions(cohort_id, threshold, symbol)
                WHERE status = 'open'
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_virtual_position_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(position_id) REFERENCES trading_virtual_positions(position_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_virtual_position_events ON trading_virtual_position_events(position_id, id)"
            )

    def open_position(
        self,
        *,
        idempotency_key: str,
        cohort_id: str,
        threshold: int,
        signal_id: str,
        decision: SignalDecision,
        symbol: str,
        entry_price: Decimal | int | float | str,
        stop_loss: Decimal | int | float | str,
        take_profit: Decimal | int | float | str,
        normalized_stake_usd: Decimal | int | float | str,
        opened_at_utc: datetime,
    ) -> VirtualPosition:
        key = _text(idempotency_key, "idempotency_key")
        cohort = _text(cohort_id, "cohort_id")
        signal = _text(signal_id, "signal_id")
        normalized_symbol = _text(symbol, "symbol", maximum=64)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 50 <= threshold <= 99:
            raise ValueError("threshold must be an integer from 50 through 99")
        normalized_decision = SignalDecision(decision)
        entry = _decimal(entry_price, "entry_price")
        stop = _decimal(stop_loss, "stop_loss")
        target = _decimal(take_profit, "take_profit")
        stake = _decimal(normalized_stake_usd, "normalized_stake_usd")
        opened = _aware_utc(opened_at_utc, "opened_at_utc")
        _validate_open_prices(normalized_decision, entry, stop, target)

        content = "|".join(
            (
                key,
                cohort,
                str(threshold),
                signal,
                normalized_decision.value,
                normalized_symbol,
                str(entry),
                str(stop),
                str(target),
                str(stake),
                opened.isoformat(),
            )
        )
        position_id = "vpos_" + sha256(content.encode("utf-8")).hexdigest()[:24]

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM trading_virtual_positions WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                record = self._row_to_position(existing)
                expected = (
                    cohort,
                    threshold,
                    signal,
                    normalized_decision,
                    normalized_symbol,
                    entry,
                    stop,
                    target,
                    stake,
                    opened,
                )
                actual = (
                    record.cohort_id,
                    record.threshold,
                    record.signal_id,
                    record.decision,
                    record.symbol,
                    record.entry_price,
                    record.stop_loss,
                    record.take_profit,
                    record.normalized_stake_usd,
                    record.opened_at_utc,
                )
                if actual != expected:
                    conn.rollback()
                    raise ValueError("idempotency_key was already used for different position content")
                conn.commit()
                return record
            try:
                conn.execute(
                    """
                    INSERT INTO trading_virtual_positions (
                        position_id, idempotency_key, cohort_id, threshold, signal_id,
                        decision, symbol, entry_price, stop_loss, take_profit,
                        normalized_stake_usd, opened_at_utc, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position_id,
                        key,
                        cohort,
                        threshold,
                        signal,
                        normalized_decision.value,
                        normalized_symbol,
                        str(entry),
                        str(stop),
                        str(target),
                        str(stake),
                        opened.isoformat(),
                        PositionStatus.OPEN.value,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise RuntimeError("portfolio already has an open position for this symbol") from exc
            self._append_event(
                conn,
                position_id,
                "position_opened",
                opened,
                {"signal_id": signal, "entry_price": str(entry)},
            )
            conn.commit()
        return self.get(position_id)

    def get(self, position_id: str) -> VirtualPosition:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_virtual_positions WHERE position_id = ?",
                (_text(position_id, "position_id"),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Virtual position not found: {position_id}")
        return self._row_to_position(row)

    def list_open(self) -> list[VirtualPosition]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_virtual_positions WHERE status = ? ORDER BY opened_at_utc, position_id",
                (PositionStatus.OPEN.value,),
            ).fetchall()
        return [self._row_to_position(row) for row in rows]

    def events(self, position_id: str) -> list[dict[str, Any]]:
        self.get(position_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, occurred_at_utc, data_json FROM trading_virtual_position_events WHERE position_id = ? ORDER BY id",
                (position_id,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "event_type": str(row["event_type"]),
                "occurred_at_utc": datetime.fromisoformat(str(row["occurred_at_utc"])),
                "data": json.loads(str(row["data_json"])),
            }
            for row in rows
        ]

    def observe_tick(
        self,
        position_id: str,
        *,
        bid: Decimal | int | float | str,
        ask: Decimal | int | float | str,
        observed_at_utc: datetime,
    ) -> VirtualPosition:
        normalized_bid = _decimal(bid, "bid")
        normalized_ask = _decimal(ask, "ask")
        if normalized_ask < normalized_bid:
            raise ValueError("ask must be at least bid")
        observed = _aware_utc(observed_at_utc, "observed_at_utc")
        position = self.get(position_id)
        if position.status is not PositionStatus.OPEN:
            return position
        executable_exit = (
            normalized_bid if position.decision is SignalDecision.LONG else normalized_ask
        )
        if position.decision is SignalDecision.LONG:
            status = (
                PositionStatus.STOP_LOSS
                if executable_exit <= position.stop_loss
                else PositionStatus.TAKE_PROFIT
                if executable_exit >= position.take_profit
                else None
            )
        else:
            status = (
                PositionStatus.STOP_LOSS
                if executable_exit >= position.stop_loss
                else PositionStatus.TAKE_PROFIT
                if executable_exit <= position.take_profit
                else None
            )
        if status is None:
            return position
        return self._resolve(
            position_id,
            status=status,
            resolved_at_utc=observed,
            exit_price=executable_exit,
            resolution_source="tick",
        )

    def observe_historical_range(
        self,
        position_id: str,
        historical_range: HistoricalRange,
    ) -> VirtualPosition:
        low = _decimal(historical_range.low, "low")
        high = _decimal(historical_range.high, "high")
        if high < low:
            raise ValueError("historical high must be at least low")
        observed = _aware_utc(historical_range.observed_at_utc, "observed_at_utc")
        position = self.get(position_id)
        if position.status is not PositionStatus.OPEN:
            return position

        stop_hit = low <= position.stop_loss if position.decision is SignalDecision.LONG else high >= position.stop_loss
        target_hit = high >= position.take_profit if position.decision is SignalDecision.LONG else low <= position.take_profit
        if stop_hit and target_hit:
            return self._resolve(
                position_id,
                status=PositionStatus.AMBIGUOUS_DATA,
                resolved_at_utc=observed,
                exit_price=None,
                resolution_source="historical_range",
            )
        if stop_hit:
            return self._resolve(
                position_id,
                status=PositionStatus.STOP_LOSS,
                resolved_at_utc=observed,
                exit_price=position.stop_loss,
                resolution_source="historical_range",
            )
        if target_hit:
            return self._resolve(
                position_id,
                status=PositionStatus.TAKE_PROFIT,
                resolved_at_utc=observed,
                exit_price=position.take_profit,
                resolution_source="historical_range",
            )
        return position

    def _resolve(
        self,
        position_id: str,
        *,
        status: PositionStatus,
        resolved_at_utc: datetime,
        exit_price: Decimal | None,
        resolution_source: str,
    ) -> VirtualPosition:
        resolved = _aware_utc(resolved_at_utc, "resolved_at_utc")
        source = _text(resolution_source, "resolution_source", maximum=64)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM trading_virtual_positions WHERE position_id = ?",
                (position_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError(f"Virtual position not found: {position_id}")
            current = self._row_to_position(row)
            if current.status is not PositionStatus.OPEN:
                conn.commit()
                return current
            realized: Decimal | None = None
            if exit_price is not None:
                move = (
                    exit_price - current.entry_price
                    if current.decision is SignalDecision.LONG
                    else current.entry_price - exit_price
                )
                realized = (move / current.entry_price) * current.normalized_stake_usd
            updated = conn.execute(
                """
                UPDATE trading_virtual_positions
                SET status = ?, resolved_at_utc = ?, exit_price = ?, realized_return = ?, resolution_source = ?
                WHERE position_id = ? AND status = ?
                """,
                (
                    status.value,
                    resolved.isoformat(),
                    str(exit_price) if exit_price is not None else None,
                    str(realized) if realized is not None else None,
                    source,
                    position_id,
                    PositionStatus.OPEN.value,
                ),
            )
            if updated.rowcount != 1:
                conn.commit()
                return self.get(position_id)
            self._append_event(
                conn,
                position_id,
                "position_resolved",
                resolved,
                {
                    "status": status.value,
                    "exit_price": str(exit_price) if exit_price is not None else None,
                    "realized_return": str(realized) if realized is not None else None,
                    "resolution_source": source,
                },
            )
            conn.commit()
        return self.get(position_id)

    @staticmethod
    def _append_event(
        conn: sqlite3.Connection,
        position_id: str,
        event_type: str,
        occurred_at_utc: datetime,
        data: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO trading_virtual_position_events (position_id, event_type, occurred_at_utc, data_json) VALUES (?, ?, ?, ?)",
            (
                position_id,
                event_type,
                _aware_utc(occurred_at_utc, "occurred_at_utc").isoformat(),
                json.dumps(data, sort_keys=True, separators=(",", ":")),
            ),
        )

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> VirtualPosition:
        return VirtualPosition(
            position_id=str(row["position_id"]),
            idempotency_key=str(row["idempotency_key"]),
            cohort_id=str(row["cohort_id"]),
            threshold=int(row["threshold"]),
            signal_id=str(row["signal_id"]),
            decision=SignalDecision(str(row["decision"])),
            symbol=str(row["symbol"]),
            entry_price=Decimal(str(row["entry_price"])),
            stop_loss=Decimal(str(row["stop_loss"])),
            take_profit=Decimal(str(row["take_profit"])),
            normalized_stake_usd=Decimal(str(row["normalized_stake_usd"])),
            opened_at_utc=datetime.fromisoformat(str(row["opened_at_utc"])),
            status=PositionStatus(str(row["status"])),
            resolved_at_utc=(
                datetime.fromisoformat(str(row["resolved_at_utc"]))
                if row["resolved_at_utc"]
                else None
            ),
            exit_price=(Decimal(str(row["exit_price"])) if row["exit_price"] is not None else None),
            realized_return=(
                Decimal(str(row["realized_return"]))
                if row["realized_return"] is not None
                else None
            ),
            resolution_source=str(row["resolution_source"]),
        )
