from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .demo_execution import DemoExecutionAdapter, DemoExecutionError
from .virtual_position_journal import (
    PositionStatus,
    VirtualPosition,
)

UTC = timezone.utc
DEFAULT_REFERENCE_THRESHOLD = 50
DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1
DEAL_REASON_STOP_LOSS = 4
DEAL_REASON_TAKE_PROFIT = 5


@dataclass(frozen=True)
class MirrorRecord:
    position_id: str
    threshold: int
    symbol: str
    direction: str
    volume: float
    order_ticket: int
    position_ticket: int
    entry_fill_price: float
    requested_stop_loss: float
    requested_take_profit: float
    environment: str
    submitted_at_utc: datetime
    reconciled_at_utc: datetime | None
    reconciliation: dict[str, Any] | None


class DemoMirrorJournal:
    """Durable record of mirrored demo orders keyed by virtual position."""

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
                CREATE TABLE IF NOT EXISTS trading_demo_mirror (
                    position_id TEXT PRIMARY KEY,
                    threshold INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    volume REAL NOT NULL,
                    order_ticket INTEGER NOT NULL,
                    position_ticket INTEGER NOT NULL UNIQUE,
                    entry_fill_price REAL NOT NULL,
                    requested_stop_loss REAL NOT NULL,
                    requested_take_profit REAL NOT NULL,
                    environment TEXT NOT NULL,
                    submitted_at_utc TEXT NOT NULL,
                    reconciled_at_utc TEXT,
                    reconciliation_json TEXT
                )
                """
            )

    def record_submission(
        self,
        position: VirtualPosition,
        *,
        order_ticket: int,
        position_ticket: int,
        volume: float,
        entry_fill_price: float,
        environment: str,
        submitted_at_utc: datetime,
    ) -> MirrorRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO trading_demo_mirror (
                    position_id, threshold, symbol, direction, volume,
                    order_ticket, position_ticket, entry_fill_price,
                    requested_stop_loss, requested_take_profit,
                    environment, submitted_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.position_id,
                    position.threshold,
                    position.symbol,
                    position.decision.value,
                    float(volume),
                    int(order_ticket),
                    int(position_ticket),
                    float(entry_fill_price),
                    float(position.stop_loss),
                    float(position.take_profit),
                    environment,
                    submitted_at_utc.astimezone(UTC).isoformat(),
                ),
            )
        return self.get(position.position_id)

    def get(self, position_id: str) -> MirrorRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_demo_mirror WHERE position_id = ?",
                (str(position_id),),
            ).fetchone()
        if row is None:
            return None
        return MirrorRecord(
            position_id=str(row["position_id"]),
            threshold=int(row["threshold"]),
            symbol=str(row["symbol"]),
            direction=str(row["direction"]),
            volume=float(row["volume"]),
            order_ticket=int(row["order_ticket"]),
            position_ticket=int(row["position_ticket"]),
            entry_fill_price=float(row["entry_fill_price"]),
            requested_stop_loss=float(row["requested_stop_loss"]),
            requested_take_profit=float(row["requested_take_profit"]),
            environment=str(row["environment"]),
            submitted_at_utc=datetime.fromisoformat(
                str(row["submitted_at_utc"])
            ),
            reconciled_at_utc=(
                datetime.fromisoformat(str(row["reconciled_at_utc"]))
                if row["reconciled_at_utc"]
                else None
            ),
            reconciliation=(
                json.loads(str(row["reconciliation_json"]))
                if row["reconciliation_json"]
                else None
            ),
        )

    def record_reconciliation(
        self,
        position_id: str,
        *,
        reconciliation: dict[str, Any],
        reconciled_at_utc: datetime,
    ) -> MirrorRecord:
        with self.connect() as conn:
            updated = conn.execute(
                """
                UPDATE trading_demo_mirror
                SET reconciled_at_utc = ?, reconciliation_json = ?
                WHERE position_id = ?
                """,
                (
                    reconciled_at_utc.astimezone(UTC).isoformat(),
                    json.dumps(
                        reconciliation, sort_keys=True, separators=(",", ":")
                    ),
                    str(position_id),
                ),
            )
            if updated.rowcount != 1:
                raise KeyError(f"Mirror record not found: {position_id}")
        return self.get(position_id)


class DemoMirror:
    """TL7: mirror one reference threshold into the real demo account.

    Every mirrored order carries the virtual position ID as its broker
    client key; duplicate submissions are refused both by the journal's
    primary key and by the broker-side open-position check. All fifty
    virtual portfolios remain authoritative and untouched.
    """

    def __init__(
        self,
        *,
        journal: DemoMirrorJournal,
        adapter: DemoExecutionAdapter,
        reference_threshold: int = DEFAULT_REFERENCE_THRESHOLD,
        volume: float = 0.01,
    ) -> None:
        if reference_threshold not in range(50, 100):
            raise ValueError(
                "reference_threshold must be from 50 through 99"
            )
        if volume <= 0:
            raise ValueError("volume must be positive")
        self.journal = journal
        self.adapter = adapter
        self.reference_threshold = int(reference_threshold)
        self.volume = float(volume)

    def mirror_open(self, position: VirtualPosition) -> MirrorRecord:
        if position.threshold != self.reference_threshold:
            raise DemoExecutionError(
                "only the selected reference threshold is mirrored"
            )
        existing = self.journal.get(position.position_id)
        if existing is not None:
            return existing
        broker_open = self.adapter.find_open_position(
            symbol=position.symbol, client_key=position.position_id
        )
        if broker_open is not None:
            # A prior submission succeeded but the journal write was lost:
            # adopt the broker position instead of duplicating the order.
            return self.journal.record_submission(
                position,
                order_ticket=broker_open.position_ticket,
                position_ticket=broker_open.position_ticket,
                volume=broker_open.volume,
                entry_fill_price=broker_open.price_open,
                environment="demo",
                submitted_at_utc=datetime.now(UTC),
            )
        result = self.adapter.market_order(
            symbol=position.symbol,
            direction=position.decision,
            volume=self.volume,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            client_key=position.position_id,
        )
        return self.journal.record_submission(
            position,
            order_ticket=result.order_ticket,
            position_ticket=result.position_ticket,
            volume=result.volume,
            entry_fill_price=result.fill_price,
            environment=result.environment,
            submitted_at_utc=result.submitted_at_utc,
        )

    def reconcile(self, position: VirtualPosition) -> dict[str, Any]:
        record = self.journal.get(position.position_id)
        if record is None:
            raise KeyError(
                f"no mirror record for position {position.position_id}"
            )
        deals = self.adapter.deals_for_position(record.position_ticket)
        entries = [d for d in deals if d.entry == DEAL_ENTRY_IN]
        exits = [d for d in deals if d.entry == DEAL_ENTRY_OUT]
        still_open = self.adapter.position_is_open(record.position_ticket)

        broker_outcome = "open"
        broker_exit_price: float | None = None
        broker_profit: float | None = None
        if exits:
            exit_deal = exits[-1]
            broker_exit_price = exit_deal.price
            broker_profit = sum(d.profit for d in exits)
            if exit_deal.reason == DEAL_REASON_STOP_LOSS:
                broker_outcome = "stop_loss"
            elif exit_deal.reason == DEAL_REASON_TAKE_PROFIT:
                broker_outcome = "take_profit"
            else:
                broker_outcome = f"other_reason_{exit_deal.reason}"

        virtual_outcome = position.status.value
        outcomes_match = (
            position.status
            in (PositionStatus.STOP_LOSS, PositionStatus.TAKE_PROFIT)
            and broker_outcome == virtual_outcome
        ) or (position.status is PositionStatus.OPEN and still_open)

        entry_fill = entries[0].price if entries else None
        virtual_entry = float(position.entry_price)
        reconciliation = {
            "position_id": position.position_id,
            "position_ticket": record.position_ticket,
            "order_count": len(entries),
            "duplicate_orders": len(entries) > 1,
            "broker_entry_fill": entry_fill,
            "virtual_entry": virtual_entry,
            "entry_spread_difference": (
                round(entry_fill - virtual_entry, 8)
                if entry_fill is not None
                else None
            ),
            "broker_outcome": broker_outcome,
            "virtual_outcome": virtual_outcome,
            "broker_exit_price": broker_exit_price,
            "virtual_exit_price": (
                float(position.exit_price)
                if position.exit_price is not None
                else None
            ),
            "broker_profit": broker_profit,
            "virtual_realized_return": (
                str(position.realized_return)
                if position.realized_return is not None
                else None
            ),
            "still_open_at_broker": still_open,
            "outcomes_match": outcomes_match,
        }
        self.journal.record_reconciliation(
            position.position_id,
            reconciliation=reconciliation,
            reconciled_at_utc=datetime.now(UTC),
        )
        return reconciliation


def mirror_realized_delta(
    reconciliation: dict[str, Any],
) -> Decimal | None:
    """Spread-inclusive broker-vs-virtual outcome delta, when both closed."""
    broker_profit = reconciliation.get("broker_profit")
    virtual_return = reconciliation.get("virtual_realized_return")
    if broker_profit is None or virtual_return is None:
        return None
    return Decimal(str(broker_profit)) - Decimal(str(virtual_return))
