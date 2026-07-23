"""Expanded immutable packet-bound signal journal (schema v2).

A model decision is stored exactly once. Submission references a stored
market packet and derives symbol, bid, ask, timestamps, parent H4 candle
identity, and the packet hash from the retained packet evidence — the
caller cannot supply its own copy of any market fact. Invalid
submissions are persisted as explicit rejected-signal records instead of
vanishing. Accepted payloads are immutable after submission; the model's
fixed stop-loss and take-profit are selected per signal and can never be
edited once stored.

The v1 tables created by ``signal_journal`` are historical evidence and
are never dropped or rewritten; this journal creates its own tables
alongside them.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from .packet_store import MarketPacketStore, StoredMarketPacket
from .versions import KNOWN_POLICY_IDS, SIGNAL_SCHEMA_VERSION

UTC = timezone.utc

DEFAULT_MAX_PACKET_AGE_SECONDS = 900
CLOCK_SKEW_TOLERANCE_SECONDS = 60

# Execution modes are a frozen closed set. ``live`` does not exist here
# and cannot be expressed: any unknown mode is rejected structurally.
EXECUTION_MODES = ("internal_paper", "broker_demo")


class SignalDecisionV2(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class SignalStatusV2(str, Enum):
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    ENTERED = "entered"


class SignalRejectedError(ValueError):
    """Raised after a rejected submission has been durably recorded."""

    def __init__(self, rejection: "SignalRejection") -> None:
        super().__init__(rejection.rejection_reason)
        self.rejection = rejection


@dataclass(frozen=True)
class SignalSubmissionV2:
    """Caller-supplied portion of a v2 signal. Market facts are derived."""

    packet_id: str
    decision: SignalDecisionV2
    confidence: int | None
    stop_loss: float | None
    take_profit: float | None
    reason: str
    news_context: str
    model_version: str
    prompt_version: str
    policy_id: str
    execution_mode: str
    experiment_id: str
    submitted_at_utc: datetime


@dataclass(frozen=True)
class SignalRecordV2:
    signal_id: str
    idempotency_key: str
    content_hash: str
    schema_version: str
    # Packet binding (derived and verified from the stored packet).
    packet_id: str
    packet_hash: str
    symbol: str
    bid: float
    ask: float
    spread: float
    market_data_timestamp: datetime
    tick_raw_epoch_seconds: int
    broker_utc_offset_seconds: int
    parent_h4_raw_open_epoch: int
    parent_h4_open_utc: datetime
    packet_age_seconds: float
    # Decision.
    decision: SignalDecisionV2
    confidence: int | None
    entry_reference_price: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    # Provenance.
    model_version: str
    prompt_version: str
    policy_id: str
    execution_mode: str
    experiment_id: str
    reason: str
    news_context: str
    # Lifecycle.
    status: SignalStatusV2
    submitted_at_utc: datetime
    inserted_at_utc: datetime
    cancelled_at_utc: datetime | None = None
    cancellation_reason: str = ""
    entered_at_utc: datetime | None = None


@dataclass(frozen=True)
class SignalRejection:
    rejection_id: str
    packet_id: str
    idempotency_key: str
    rejection_reason: str
    submission_json: str
    occurred_at_utc: datetime


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bounded_text(
    value: str, field_name: str, *, maximum: int, allow_empty: bool = False
) -> str:
    normalized = str(value).strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return normalized


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware(value, "timestamp").isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_signal_v2_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        _canonical(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


class SignalJournalV2:
    """Durable append-only journal for packet-bound v2 signals."""

    def __init__(
        self,
        db_path: Path,
        packet_store: MarketPacketStore,
        *,
        expected_symbol: str = "BITCOIN_i",
        max_packet_age_seconds: float = DEFAULT_MAX_PACKET_AGE_SECONDS,
    ) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.packets = packet_store
        self.expected_symbol = str(expected_symbol).strip()
        if not self.expected_symbol:
            raise ValueError("expected_symbol must not be empty")
        if max_packet_age_seconds <= 0:
            raise ValueError("max_packet_age_seconds must be positive")
        self.max_packet_age_seconds = float(max_packet_age_seconds)
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
                CREATE TABLE IF NOT EXISTS trading_signals_v2 (
                    signal_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    content_hash TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    packet_id TEXT NOT NULL,
                    packet_hash TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    parent_h4_raw_open_epoch INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    confidence INTEGER,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    submitted_at_utc TEXT NOT NULL,
                    inserted_at_utc TEXT NOT NULL,
                    cancelled_at_utc TEXT,
                    cancellation_reason TEXT NOT NULL DEFAULT '',
                    entered_at_utc TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_signals_v2_submitted"
                " ON trading_signals_v2(submitted_at_utc, signal_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_signals_v2_parent"
                " ON trading_signals_v2(parent_h4_raw_open_epoch)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_signal_v2_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(signal_id) REFERENCES trading_signals_v2(signal_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_signal_rejections (
                    rejection_id TEXT PRIMARY KEY,
                    packet_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    rejection_reason TEXT NOT NULL,
                    submission_json TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL
                )
                """
            )

    # -- submission ---------------------------------------------------------

    def submit(
        self,
        idempotency_key: str,
        submission: SignalSubmissionV2,
    ) -> SignalRecordV2:
        key = _bounded_text(idempotency_key, "idempotency_key", maximum=128)
        try:
            record_payload = self._validated_payload(submission)
        except ValueError as exc:
            raise self._record_rejection(key, submission, str(exc)) from exc

        content_hash = sha256(
            canonical_signal_v2_bytes(record_payload)
        ).hexdigest()
        signal_id = (
            "sig2_"
            + sha256(f"{key}:{content_hash}".encode("utf-8")).hexdigest()[:24]
        )
        inserted = datetime.now(UTC)
        payload_json = canonical_signal_v2_bytes(record_payload).decode("utf-8")

        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM trading_signals_v2 WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                if str(existing["content_hash"]) != content_hash:
                    conn.rollback()
                    raise self._record_rejection(
                        key,
                        submission,
                        "idempotency_key was already used for different"
                        " signal content",
                    )
                conn.commit()
                return self._row_to_record(existing)
            conn.execute(
                """
                INSERT INTO trading_signals_v2 (
                    signal_id, idempotency_key, content_hash, schema_version,
                    packet_id, packet_hash, symbol, experiment_id,
                    parent_h4_raw_open_epoch, decision, confidence, status,
                    payload_json, submitted_at_utc, inserted_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    key,
                    content_hash,
                    SIGNAL_SCHEMA_VERSION,
                    record_payload["packet_id"],
                    record_payload["packet_hash"],
                    record_payload["symbol"],
                    record_payload["experiment_id"],
                    record_payload["parent_h4_raw_open_epoch"],
                    record_payload["decision"],
                    record_payload["confidence"],
                    SignalStatusV2.SUBMITTED.value,
                    payload_json,
                    record_payload["submitted_at_utc"],
                    inserted.isoformat(),
                ),
            )
            self._append_event(
                conn,
                signal_id,
                "signal_submitted",
                inserted,
                {
                    "content_hash": content_hash,
                    "packet_id": record_payload["packet_id"],
                    "packet_hash": record_payload["packet_hash"],
                },
            )
            conn.commit()
        return self.get(signal_id)

    def _validated_payload(
        self, submission: SignalSubmissionV2
    ) -> dict[str, Any]:
        """Derive and validate the immutable payload from the stored packet."""
        submitted_at = _aware(submission.submitted_at_utc, "submitted_at_utc")
        packet_id = _bounded_text(submission.packet_id, "packet_id", maximum=64)
        try:
            packet = self.packets.get(packet_id)
        except KeyError as exc:
            raise ValueError(
                f"packet_id {packet_id!r} does not reference a stored market"
                " packet"
            ) from exc

        self._validate_packet(packet, submitted_at)
        decision = SignalDecisionV2(submission.decision)
        confidence = submission.confidence
        stop = submission.stop_loss
        target = submission.take_profit
        entry: float | None = None
        risk_reward: float | None = None

        if decision is SignalDecisionV2.NO_TRADE:
            if confidence is not None:
                raise ValueError("NO_TRADE confidence must be null")
            if stop is not None or target is not None:
                raise ValueError(
                    "NO_TRADE must not carry stop_loss or take_profit"
                )
        else:
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, int)
                or not 50 <= confidence <= 99
            ):
                raise ValueError(
                    "directional confidence must be an integer from 50"
                    " through 99"
                )
            if stop is None or target is None:
                raise ValueError(
                    "directional signals require model-selected stop_loss"
                    " and take_profit"
                )
            stop = float(stop)
            target = float(target)
            # Honest executable entry from the packet: LONG at ask,
            # SHORT at bid.
            if decision is SignalDecisionV2.LONG:
                entry = float(packet.ask)
                if not stop < entry < target:
                    raise ValueError(
                        "LONG requires stop_loss < packet ask < take_profit"
                    )
                risk_reward = (target - entry) / (entry - stop)
            else:
                entry = float(packet.bid)
                if not target < entry < stop:
                    raise ValueError(
                        "SHORT requires take_profit < packet bid < stop_loss"
                    )
                risk_reward = (entry - target) / (stop - entry)

        mode = _bounded_text(
            submission.execution_mode, "execution_mode", maximum=32
        ).lower()
        if mode not in EXECUTION_MODES:
            raise ValueError(
                f"execution_mode must be one of {EXECUTION_MODES}; live"
                " execution does not exist"
            )
        policy = _bounded_text(submission.policy_id, "policy_id", maximum=64)
        if policy not in KNOWN_POLICY_IDS:
            raise ValueError(f"policy_id must be one of {KNOWN_POLICY_IDS}")

        return {
            "schema_version": SIGNAL_SCHEMA_VERSION,
            "packet_id": packet.packet_id,
            "packet_hash": packet.content_hash,
            "symbol": packet.symbol,
            "bid": packet.bid,
            "ask": packet.ask,
            "spread": packet.ask - packet.bid,
            "market_data_timestamp": packet.tick_normalized_utc.isoformat(),
            "tick_raw_epoch_seconds": packet.tick_raw_epoch_seconds,
            "broker_utc_offset_seconds": packet.broker_utc_offset_seconds,
            "parent_h4_raw_open_epoch": packet.parent_h4_raw_open_epoch,
            "parent_h4_open_utc": packet.parent_h4_open_utc.isoformat(),
            "packet_age_seconds": max(
                0.0, (submitted_at - packet.created_at_utc).total_seconds()
            ),
            "decision": decision.value,
            "confidence": confidence,
            "entry_reference_price": entry,
            "stop_loss": stop,
            "take_profit": target,
            "risk_reward": risk_reward,
            "model_version": _bounded_text(
                submission.model_version, "model_version", maximum=128
            ),
            "prompt_version": _bounded_text(
                submission.prompt_version, "prompt_version", maximum=128
            ),
            "policy_id": policy,
            "execution_mode": mode,
            "experiment_id": _bounded_text(
                submission.experiment_id, "experiment_id", maximum=64
            ),
            "reason": _bounded_text(submission.reason, "reason", maximum=4000),
            "news_context": _bounded_text(
                submission.news_context,
                "news_context",
                maximum=8000,
                allow_empty=True,
            ),
            "submitted_at_utc": submitted_at.isoformat(),
        }

    def _validate_packet(
        self, packet: StoredMarketPacket, submitted_at: datetime
    ) -> None:
        if packet.symbol != self.expected_symbol:
            raise ValueError(
                f"packet symbol {packet.symbol!r} is not the configured"
                f" instrument {self.expected_symbol!r}"
            )
        if packet.account_environment != "demo":
            raise ValueError("packet was not built from a demo account")
        if packet.bid <= 0 or packet.ask <= 0 or packet.ask < packet.bid:
            raise ValueError("packet does not carry a usable bid/ask pair")
        age = (submitted_at - packet.created_at_utc).total_seconds()
        if age < -CLOCK_SKEW_TOLERANCE_SECONDS:
            raise ValueError("submission predates its market packet")
        if age > self.max_packet_age_seconds:
            raise ValueError(
                f"market packet is {age:.0f}s old; the permitted window is"
                f" {self.max_packet_age_seconds:.0f}s"
            )

    def _record_rejection(
        self,
        idempotency_key: str,
        submission: SignalSubmissionV2,
        reason: str,
    ) -> SignalRejectedError:
        occurred = datetime.now(UTC)
        submission_payload = asdict(submission)
        submission_json = canonical_signal_v2_bytes(submission_payload).decode(
            "utf-8"
        )
        rejection_id = (
            "sigrej_"
            + sha256(
                f"{idempotency_key}:{reason}:{submission_json}".encode("utf-8")
            ).hexdigest()[:24]
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO trading_signal_rejections (
                    rejection_id, packet_id, idempotency_key,
                    rejection_reason, submission_json, occurred_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    rejection_id,
                    str(submission.packet_id),
                    idempotency_key,
                    reason,
                    submission_json,
                    occurred.isoformat(),
                ),
            )
            conn.commit()
        rejection = SignalRejection(
            rejection_id=rejection_id,
            packet_id=str(submission.packet_id),
            idempotency_key=idempotency_key,
            rejection_reason=reason,
            submission_json=submission_json,
            occurred_at_utc=occurred,
        )
        return SignalRejectedError(rejection)

    # -- reads --------------------------------------------------------------

    def get(self, signal_id: str) -> SignalRecordV2:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_signals_v2 WHERE signal_id = ?",
                (str(signal_id).strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Signal not found: {signal_id}")
        return self._row_to_record(row)

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: SignalStatusV2 | None = None,
        experiment_id: str | None = None,
        packet_id: str | None = None,
        parent_h4_raw_open_epoch: int | None = None,
    ) -> list[SignalRecordV2]:
        """Paginated journal query over the complete journal.

        There is no silent truncation: callers page with ``limit`` and
        ``offset`` and can count the journal with :meth:`count`.
        """
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must not be negative")
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(SignalStatusV2(status).value)
        if experiment_id is not None:
            clauses.append("experiment_id = ?")
            params.append(str(experiment_id).strip())
        if packet_id is not None:
            clauses.append("packet_id = ?")
            params.append(str(packet_id).strip())
        if parent_h4_raw_open_epoch is not None:
            clauses.append("parent_h4_raw_open_epoch = ?")
            params.append(int(parent_h4_raw_open_epoch))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_signals_v2"
                + where
                + " ORDER BY submitted_at_utc, signal_id LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count(
        self,
        *,
        status: SignalStatusV2 | None = None,
        experiment_id: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(SignalStatusV2(status).value)
        if experiment_id is not None:
            clauses.append("experiment_id = ?")
            params.append(str(experiment_id).strip())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM trading_signals_v2" + where,
                params,
            ).fetchone()
        return int(row["n"])

    def list_rejections(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[SignalRejection]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must not be negative")
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_signal_rejections"
                " ORDER BY occurred_at_utc, rejection_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [
            SignalRejection(
                rejection_id=str(row["rejection_id"]),
                packet_id=str(row["packet_id"]),
                idempotency_key=str(row["idempotency_key"]),
                rejection_reason=str(row["rejection_reason"]),
                submission_json=str(row["submission_json"]),
                occurred_at_utc=_parse_utc(str(row["occurred_at_utc"])),
            )
            for row in rows
        ]

    def events(self, signal_id: str) -> list[dict[str, Any]]:
        self.get(signal_id)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, occurred_at_utc, data_json"
                " FROM trading_signal_v2_events WHERE signal_id = ?"
                " ORDER BY id",
                (signal_id,),
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

    # -- lifecycle ----------------------------------------------------------

    def cancel_before_entry(
        self,
        signal_id: str,
        reason: str,
        *,
        cancelled_at_utc: datetime | None = None,
    ) -> SignalRecordV2:
        cancellation_reason = _bounded_text(reason, "reason", maximum=1000)
        cancelled = _aware(
            cancelled_at_utc or datetime.now(UTC), "cancelled_at_utc"
        )
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM trading_signals_v2 WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError(f"Signal not found: {signal_id}")
            status = SignalStatusV2(str(row["status"]))
            if status is SignalStatusV2.ENTERED:
                conn.rollback()
                raise RuntimeError("Entered signals cannot be cancelled")
            if status is SignalStatusV2.CANCELLED:
                conn.commit()
                return self._row_to_record(row)
            conn.execute(
                "UPDATE trading_signals_v2 SET status = ?, cancelled_at_utc = ?,"
                " cancellation_reason = ? WHERE signal_id = ?",
                (
                    SignalStatusV2.CANCELLED.value,
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
    ) -> SignalRecordV2:
        entered = _aware(entered_at_utc or datetime.now(UTC), "entered_at_utc")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM trading_signals_v2 WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError(f"Signal not found: {signal_id}")
            record = self._row_to_record(row)
            if record.decision is SignalDecisionV2.NO_TRADE:
                conn.rollback()
                raise RuntimeError("NO_TRADE signals cannot enter")
            if record.status is SignalStatusV2.CANCELLED:
                conn.rollback()
                raise RuntimeError("Cancelled signals cannot enter")
            if record.status is SignalStatusV2.ENTERED:
                conn.commit()
                return record
            conn.execute(
                "UPDATE trading_signals_v2 SET status = ?, entered_at_utc = ?"
                " WHERE signal_id = ?",
                (SignalStatusV2.ENTERED.value, entered.isoformat(), signal_id),
            )
            self._append_event(conn, signal_id, "signal_entered", entered, {})
            conn.commit()
        return self.get(signal_id)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _append_event(
        conn: sqlite3.Connection,
        signal_id: str,
        event_type: str,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO trading_signal_v2_events"
            " (signal_id, event_type, occurred_at_utc, data_json)"
            " VALUES (?, ?, ?, ?)",
            (
                signal_id,
                event_type,
                _aware(occurred_at, "occurred_at_utc").isoformat(),
                json.dumps(data, sort_keys=True, separators=(",", ":")),
            ),
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SignalRecordV2:
        payload = json.loads(str(row["payload_json"]))
        return SignalRecordV2(
            signal_id=str(row["signal_id"]),
            idempotency_key=str(row["idempotency_key"]),
            content_hash=str(row["content_hash"]),
            schema_version=str(payload["schema_version"]),
            packet_id=str(payload["packet_id"]),
            packet_hash=str(payload["packet_hash"]),
            symbol=str(payload["symbol"]),
            bid=float(payload["bid"]),
            ask=float(payload["ask"]),
            spread=float(payload["spread"]),
            market_data_timestamp=_parse_utc(
                str(payload["market_data_timestamp"])
            ),
            tick_raw_epoch_seconds=int(payload["tick_raw_epoch_seconds"]),
            broker_utc_offset_seconds=int(
                payload["broker_utc_offset_seconds"]
            ),
            parent_h4_raw_open_epoch=int(
                payload["parent_h4_raw_open_epoch"]
            ),
            parent_h4_open_utc=_parse_utc(str(payload["parent_h4_open_utc"])),
            packet_age_seconds=float(payload["packet_age_seconds"]),
            decision=SignalDecisionV2(payload["decision"]),
            confidence=payload["confidence"],
            entry_reference_price=payload["entry_reference_price"],
            stop_loss=payload["stop_loss"],
            take_profit=payload["take_profit"],
            risk_reward=payload["risk_reward"],
            model_version=str(payload["model_version"]),
            prompt_version=str(payload["prompt_version"]),
            policy_id=str(payload["policy_id"]),
            execution_mode=str(payload["execution_mode"]),
            experiment_id=str(payload["experiment_id"]),
            reason=str(payload["reason"]),
            news_context=str(payload["news_context"]),
            status=SignalStatusV2(str(row["status"])),
            submitted_at_utc=_parse_utc(str(payload["submitted_at_utc"])),
            inserted_at_utc=_parse_utc(str(row["inserted_at_utc"])),
            cancelled_at_utc=(
                _parse_utc(str(row["cancelled_at_utc"]))
                if row["cancelled_at_utc"]
                else None
            ),
            cancellation_reason=str(row["cancellation_reason"]),
            entered_at_utc=(
                _parse_utc(str(row["entered_at_utc"]))
                if row["entered_at_utc"]
                else None
            ),
        )
