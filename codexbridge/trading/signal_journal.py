from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any


UTC = timezone.utc


class SignalDecision(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class SignalStatus(str, Enum):
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    ENTERED = "entered"


@dataclass(frozen=True)
class SignalDraft:
    created_at_utc: datetime
    broker: str
    symbol: str
    analysis_timeframe: str
    decision: SignalDecision
    confidence: int | None
    bid: float
    ask: float
    market_data_timestamp: datetime
    latest_completed_4h_candle: str
    developing_4h_candle: str
    entry_type: str
    entry_reference_price: float | None
    stop_loss: float | None
    take_profit: float | None
    reason: str
    news_context: str
    market_snapshot_id: str
    market_packet_hash: str


@dataclass(frozen=True)
class SignalRecord:
    signal_id: str
    idempotency_key: str
    content_hash: str
    draft: SignalDraft
    spread: float
    risk_reward: float | None
    status: SignalStatus
    inserted_at_utc: datetime
    cancelled_at_utc: datetime | None = None
    cancellation_reason: str = ""
    entered_at_utc: datetime | None = None


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _bounded_text(value: str, field_name: str, *, maximum: int, allow_empty: bool = False) -> str:
    normalized = str(value).strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return normalized


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware_utc(value, "timestamp").isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_signal_bytes(draft: SignalDraft) -> bytes:
    return json.dumps(
        _canonical(asdict(draft)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def signal_content_hash(draft: SignalDraft) -> str:
    return sha256(canonical_signal_bytes(draft)).hexdigest()


def _validate_hash(value: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("market_packet_hash must be a 64-character hexadecimal SHA-256")
    return normalized


def validate_signal_draft(draft: SignalDraft) -> tuple[SignalDraft, float, float | None]:
    created_at = _aware_utc(draft.created_at_utc, "created_at_utc")
    market_timestamp = _aware_utc(draft.market_data_timestamp, "market_data_timestamp")
    broker = _bounded_text(draft.broker, "broker", maximum=64).lower()
    if broker != "alpari":
        raise ValueError("broker must be alpari for the frozen v1 experiment")
    symbol = _bounded_text(draft.symbol, "symbol", maximum=64)
    timeframe = _bounded_text(draft.analysis_timeframe, "analysis_timeframe", maximum=16).upper()
    if timeframe != "4H":
        raise ValueError("analysis_timeframe must be 4H")
    entry_type = _bounded_text(draft.entry_type, "entry_type", maximum=16).upper()
    if entry_type != "MARKET":
        raise ValueError("entry_type must be MARKET")
    reason = _bounded_text(draft.reason, "reason", maximum=4000)
    news_context = _bounded_text(
        draft.news_context, "news_context", maximum=8000, allow_empty=True
    )
    completed_candle = _bounded_text(
        draft.latest_completed_4h_candle,
        "latest_completed_4h_candle",
        maximum=256,
    )
    developing_candle = _bounded_text(
        draft.developing_4h_candle,
        "developing_4h_candle",
        maximum=256,
    )
    packet_hash = _validate_hash(draft.market_packet_hash)
    snapshot_id = _bounded_text(draft.market_snapshot_id, "market_snapshot_id", maximum=64)
    expected_snapshot_id = f"mp_{packet_hash[:24]}"
    if snapshot_id != expected_snapshot_id:
        raise ValueError("market_snapshot_id does not match market_packet_hash")

    bid = float(draft.bid)
    ask = float(draft.ask)
    if bid <= 0 or ask <= 0 or ask < bid:
        raise ValueError("bid and ask must be positive and ask must be at least bid")
    spread = ask - bid

    decision = SignalDecision(draft.decision)
    confidence = draft.confidence
    entry = draft.entry_reference_price
    stop = draft.stop_loss
    target = draft.take_profit
    risk_reward: float | None = None

    if decision is SignalDecision.NO_TRADE:
        if confidence is not None:
            raise ValueError("NO_TRADE confidence must be null")
        if any(value is not None for value in (entry, stop, target)):
            raise ValueError("NO_TRADE must not contain entry, stop-loss, or take-profit")
    else:
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, int)
            or not 50 <= confidence <= 99
        ):
            raise ValueError("LONG and SHORT confidence must be an integer from 50 through 99")
        if any(value is None for value in (entry, stop, target)):
            raise ValueError("LONG and SHORT require entry, stop-loss, and take-profit")
        entry = float(entry)
        stop = float(stop)
        target = float(target)
        executable = ask if decision is SignalDecision.LONG else bid
        if entry != executable:
            side = "ask" if decision is SignalDecision.LONG else "bid"
            raise ValueError(f"{decision.value} entry_reference_price must equal the captured {side}")
        if decision is SignalDecision.LONG:
            if not stop < entry < target:
                raise ValueError("LONG requires stop_loss < entry_reference_price < take_profit")
            risk_reward = (target - entry) / (entry - stop)
        else:
            if not target < entry < stop:
                raise ValueError("SHORT requires take_profit < entry_reference_price < stop_loss")
            risk_reward = (entry - target) / (stop - entry)

    normalized = SignalDraft(
        created_at_utc=created_at,
        broker=broker,
        symbol=symbol,
        analysis_timeframe=timeframe,
        decision=decision,
        confidence=confidence,
        bid=bid,
        ask=ask,
        market_data_timestamp=market_timestamp,
        latest_completed_4h_candle=completed_candle,
        developing_4h_candle=developing_candle,
        entry_type=entry_type,
        entry_reference_price=entry,
        stop_loss=stop,
        take_profit=target,
        reason=reason,
        news_context=news_context,
        market_snapshot_id=snapshot_id,
        market_packet_hash=packet_hash,
    )
    return normalized, spread, risk_reward


class SignalJournal:
    """Durable append-only journal for immutable Trading Lab signals."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_signals (
                    signal_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    spread REAL NOT NULL,
                    risk_reward REAL,
                    status TEXT NOT NULL,
                    inserted_at_utc TEXT NOT NULL,
                    cancelled_at_utc TEXT,
                    cancellation_reason TEXT NOT NULL DEFAULT '',
                    entered_at_utc TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_signal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(signal_id) REFERENCES trading_signals(signal_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_signal_events_signal ON trading_signal_events(signal_id, id)"
            )

    def submit(
        self,
        idempotency_key: str,
        draft: SignalDraft,
        *,
        inserted_at_utc: datetime | None = None,
    ) -> SignalRecord:
        key = _bounded_text(idempotency_key, "idempotency_key", maximum=128)
        normalized, spread, risk_reward = validate_signal_draft(draft)
        content_hash = signal_content_hash(normalized)
        signal_id = "sig_" + sha256(f"{key}:{content_hash}".encode("utf-8")).hexdigest()[:24]
        inserted = _aware_utc(inserted_at_utc or datetime.now(UTC), "inserted_at_utc")
        payload_json = canonical_signal_bytes(normalized).decode("utf-8")

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM trading_signals WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                if str(existing["content_hash"]) != content_hash:
                    conn.rollback()
                    raise ValueError("idempotency_key was already used for different signal content")
                conn.commit()
                return self._row_to_record(existing)
            conn.execute(
                """
                INSERT INTO trading_signals (
                    signal_id, idempotency_key, content_hash, payload_json, spread,
                    risk_reward, status, inserted_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    key,
                    content_hash,
                    payload_json,
                    spread,
                    risk_reward,
                    SignalStatus.SUBMITTED.value,
                    inserted.isoformat(),
                ),
            )
            self._append_event(
                conn,
                signal_id,
                "signal_submitted",
                inserted,
                {"content_hash": content_hash, "market_packet_hash": normalized.market_packet_hash},
            )
            conn.commit()
        return self.get(signal_id)

    def get(self, signal_id: str) -> SignalRecord:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_signals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Signal not found: {signal_id}")
        return self._row_to_record(row)

    def list(self, *, limit: int = 100) -> list[SignalRecord]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_signals ORDER BY inserted_at_utc DESC, signal_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def events(self, signal_id: str) -> list[dict[str, Any]]:
        self.get(signal_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, occurred_at_utc, data_json FROM trading_signal_events WHERE signal_id = ? ORDER BY id",
                (signal_id,),
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

    def cancel_before_entry(
        self,
        signal_id: str,
        reason: str,
        *,
        cancelled_at_utc: datetime | None = None,
    ) -> SignalRecord:
        cancellation_reason = _bounded_text(reason, "reason", maximum=1000)
        cancelled = _aware_utc(cancelled_at_utc or datetime.now(UTC), "cancelled_at_utc")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM trading_signals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError(f"Signal not found: {signal_id}")
            status = SignalStatus(str(row["status"]))
            if status is SignalStatus.ENTERED:
                conn.rollback()
                raise RuntimeError("Entered signals cannot be cancelled")
            if status is SignalStatus.CANCELLED:
                conn.commit()
                return self._row_to_record(row)
            conn.execute(
                "UPDATE trading_signals SET status = ?, cancelled_at_utc = ?, cancellation_reason = ? WHERE signal_id = ?",
                (
                    SignalStatus.CANCELLED.value,
                    cancelled.isoformat(),
                    cancellation_reason,
                    signal_id,
                ),
            )
            self._append_event(
                conn,
                signal_id,
                "signal_cancelled_before_entry",
                cancelled,
                {"reason": cancellation_reason},
            )
            conn.commit()
        return self.get(signal_id)

    def mark_entered(
        self,
        signal_id: str,
        *,
        entered_at_utc: datetime | None = None,
    ) -> SignalRecord:
        entered = _aware_utc(entered_at_utc or datetime.now(UTC), "entered_at_utc")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM trading_signals WHERE signal_id = ?", (signal_id,)
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError(f"Signal not found: {signal_id}")
            record = self._row_to_record(row)
            if record.draft.decision is SignalDecision.NO_TRADE:
                conn.rollback()
                raise RuntimeError("NO_TRADE signals cannot enter")
            if record.status is SignalStatus.CANCELLED:
                conn.rollback()
                raise RuntimeError("Cancelled signals cannot enter")
            if record.status is SignalStatus.ENTERED:
                conn.commit()
                return record
            conn.execute(
                "UPDATE trading_signals SET status = ?, entered_at_utc = ? WHERE signal_id = ?",
                (SignalStatus.ENTERED.value, entered.isoformat(), signal_id),
            )
            self._append_event(conn, signal_id, "signal_entered", entered, {})
            conn.commit()
        return self.get(signal_id)

    @staticmethod
    def _append_event(
        conn: sqlite3.Connection,
        signal_id: str,
        event_type: str,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO trading_signal_events (signal_id, event_type, occurred_at_utc, data_json) VALUES (?, ?, ?, ?)",
            (
                signal_id,
                event_type,
                _aware_utc(occurred_at, "occurred_at_utc").isoformat(),
                json.dumps(data, sort_keys=True, separators=(",", ":")),
            ),
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SignalRecord:
        payload = json.loads(str(row["payload_json"]))
        draft = SignalDraft(
            created_at_utc=datetime.fromisoformat(payload["created_at_utc"].replace("Z", "+00:00")),
            broker=str(payload["broker"]),
            symbol=str(payload["symbol"]),
            analysis_timeframe=str(payload["analysis_timeframe"]),
            decision=SignalDecision(payload["decision"]),
            confidence=payload["confidence"],
            bid=float(payload["bid"]),
            ask=float(payload["ask"]),
            market_data_timestamp=datetime.fromisoformat(payload["market_data_timestamp"].replace("Z", "+00:00")),
            latest_completed_4h_candle=str(payload["latest_completed_4h_candle"]),
            developing_4h_candle=str(payload["developing_4h_candle"]),
            entry_type=str(payload["entry_type"]),
            entry_reference_price=payload["entry_reference_price"],
            stop_loss=payload["stop_loss"],
            take_profit=payload["take_profit"],
            reason=str(payload["reason"]),
            news_context=str(payload["news_context"]),
            market_snapshot_id=str(payload["market_snapshot_id"]),
            market_packet_hash=str(payload["market_packet_hash"]),
        )
        return SignalRecord(
            signal_id=str(row["signal_id"]),
            idempotency_key=str(row["idempotency_key"]),
            content_hash=str(row["content_hash"]),
            draft=draft,
            spread=float(row["spread"]),
            risk_reward=float(row["risk_reward"]) if row["risk_reward"] is not None else None,
            status=SignalStatus(str(row["status"])),
            inserted_at_utc=datetime.fromisoformat(str(row["inserted_at_utc"])),
            cancelled_at_utc=(
                datetime.fromisoformat(str(row["cancelled_at_utc"]))
                if row["cancelled_at_utc"]
                else None
            ),
            cancellation_reason=str(row["cancellation_reason"]),
            entered_at_utc=(
                datetime.fromisoformat(str(row["entered_at_utc"]))
                if row["entered_at_utc"]
                else None
            ),
        )
