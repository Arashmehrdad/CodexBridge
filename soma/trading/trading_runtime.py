"""Durable Trading Lab runtime with decoupled supervision.

The runtime owns two separate concerns:

* **Supervision** — connected demo-market monitoring, broker offset
  detection, tick ingestion into the durable archive, outcome resolution
  for entered signals, reconciliation of in-flight actions, and the
  standing-policy supervisors (trailing stops, time/condition exits).
  Supervision continues even when packet construction, H4 data, or
  analysis fails: every step runs in its own failure boundary and
  records its error as a durable runtime event.

* **Hourly analysis entry** — entering submitted signals. A signal may
  enter only while its exact stored market packet is inside the
  permitted age window; expired signals are cancelled with an explicit
  reason, never entered against newer prices.

Runtime state (started/stopped, last pass times) is durable and survives
restart. Standing policies are derived from the confirmed action journal
records on every pass, so trailing supervisors survive restart without
any in-memory registry.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .action_gateway import (
    ActionGateway,
    ActionRequest,
    ActionState,
    TradingActionJournal,
)
from .broker_time import OffsetSample, detect_broker_utc_offset
from .market_packet import MarketPacketBuilder
from .outcome_resolver import (
    OutcomeStatus,
    SignalOutcomeJournal,
    resolve_from_ticks,
)
from .packet_store import MarketPacketStore
from .signal_journal_v2 import (
    SignalDecisionV2,
    SignalJournalV2,
    SignalStatusV2,
)
from .strategy_policy import ActionType, CapabilityRole, ExecutionMode
from .tick_archive import TickArchive

UTC = timezone.utc
DEFAULT_ENTRY_WINDOW_SECONDS = 900.0
DEFAULT_DEMO_ENTRY_VOLUME_LOTS = 0.01
DEFAULT_RECOVERY_LOOKBACK = timedelta(hours=2)
OFFSET_SAMPLE_COUNT = 3


@dataclass(frozen=True)
class RuntimeStatus:
    state: str  # running | stopped
    started_at_utc: datetime | None
    stopped_at_utc: datetime | None
    last_supervision_at_utc: datetime | None
    last_analysis_at_utc: datetime | None
    last_ingested_tick_utc: datetime | None


@dataclass(frozen=True)
class StepResult:
    step: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class SupervisionReport:
    ran: bool
    refusal_reason: str
    steps: tuple[StepResult, ...] = ()
    resolved_signal_ids: tuple[str, ...] = ()
    trailing_updates: tuple[str, ...] = ()
    time_exits: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisReport:
    ran: bool
    refusal_reason: str
    packet_id: str | None = None
    entered_signal_ids: tuple[str, ...] = ()
    expired_signal_ids: tuple[str, ...] = ()
    skipped_signal_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass
class TradingRuntime:
    runtime_db_path: Path
    packet_store: MarketPacketStore
    signal_journal: SignalJournalV2
    outcome_journal: SignalOutcomeJournal
    tick_archive: TickArchive
    action_journal: TradingActionJournal
    gateway: ActionGateway
    symbol: str = "BITCOIN_i"
    entry_window_seconds: float = DEFAULT_ENTRY_WINDOW_SECONDS
    demo_entry_volume_lots: float = DEFAULT_DEMO_ENTRY_VOLUME_LOTS
    packet_builder: MarketPacketBuilder = field(
        default_factory=MarketPacketBuilder
    )

    def __post_init__(self) -> None:
        self.runtime_db_path = Path(self.runtime_db_path).resolve()
        self.runtime_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # -- durable state ------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.runtime_db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_runtime_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state TEXT NOT NULL,
                    started_at_utc TEXT,
                    stopped_at_utc TEXT,
                    last_supervision_at_utc TEXT,
                    last_analysis_at_utc TEXT,
                    last_ingested_tick_utc TEXT
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO trading_runtime_state (id, state)"
                " VALUES (1, 'stopped')"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_runtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    occurred_at_utc TEXT NOT NULL
                )
                """
            )

    def _event(self, event_type: str, detail: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trading_runtime_events"
                " (event_type, detail, occurred_at_utc) VALUES (?, ?, ?)",
                (event_type, detail[:2000], datetime.now(UTC).isoformat()),
            )
            conn.commit()

    def _set_state(self, **columns: Any) -> None:
        assignments = ", ".join(f"{key} = ?" for key in columns)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE trading_runtime_state SET {assignments} WHERE id = 1",
                list(columns.values()),
            )
            conn.commit()

    def status(self) -> RuntimeStatus:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_runtime_state WHERE id = 1"
            ).fetchone()

        def parse(name: str) -> datetime | None:
            value = row[name]
            return datetime.fromisoformat(str(value)) if value else None

        return RuntimeStatus(
            state=str(row["state"]),
            started_at_utc=parse("started_at_utc"),
            stopped_at_utc=parse("stopped_at_utc"),
            last_supervision_at_utc=parse("last_supervision_at_utc"),
            last_analysis_at_utc=parse("last_analysis_at_utc"),
            last_ingested_tick_utc=parse("last_ingested_tick_utc"),
        )

    def events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_runtime_events ORDER BY id DESC"
                " LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "event_type": str(row["event_type"]),
                "detail": str(row["detail"]),
                "occurred_at_utc": str(row["occurred_at_utc"]),
            }
            for row in rows
        ]

    def start(self, *, now: datetime | None = None) -> RuntimeStatus:
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        self._set_state(state="running", started_at_utc=moment.isoformat())
        self._event("runtime_started")
        return self.status()

    def stop(self, reason: str, *, now: datetime | None = None) -> RuntimeStatus:
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        self._set_state(state="stopped", stopped_at_utc=moment.isoformat())
        self._event("runtime_stopped", reason)
        return self.status()

    # -- supervision (audit defect 3: independent failure boundaries) -------

    def supervision_pass(
        self,
        provider: Any,
        executor: Any,
        *,
        now: datetime,
        recovery_lookback: timedelta = DEFAULT_RECOVERY_LOOKBACK,
    ) -> SupervisionReport:
        moment = now.astimezone(UTC)
        if self.status().state != "running":
            return SupervisionReport(
                ran=False, refusal_reason="runtime is stopped"
            )
        steps: list[StepResult] = []
        resolved: tuple[str, ...] = ()
        trailing: tuple[str, ...] = ()
        exits: tuple[str, ...] = ()

        def run_step(name: str, func) -> Any:
            try:
                result = func()
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
                steps.append(StepResult(step=name, ok=False, detail=detail))
                self._event(f"supervision_step_failed:{name}", detail)
                return None
            steps.append(StepResult(step=name, ok=True))
            return result

        run_step("offset_detection", lambda: self._detect_offset(provider, moment))
        run_step(
            "symbol_rules_refresh",
            lambda: provider.symbol_specification(self.symbol),
        )
        run_step(
            "tick_ingestion",
            lambda: self._ingest_ticks(provider, moment, recovery_lookback),
        )
        resolved = (
            run_step(
                "outcome_resolution",
                lambda: self._resolve_entered_signals(moment),
            )
            or ()
        )
        run_step(
            "action_reconciliation",
            lambda: self._reconcile_inflight_actions(executor, moment),
        )
        trailing = (
            run_step(
                "trailing_supervision",
                lambda: self._trailing_pass(executor, moment),
            )
            or ()
        )
        exits = (
            run_step(
                "standing_exit_supervision",
                lambda: self._standing_exit_pass(executor, moment),
            )
            or ()
        )
        self._set_state(last_supervision_at_utc=moment.isoformat())
        return SupervisionReport(
            ran=True,
            refusal_reason="",
            steps=tuple(steps),
            resolved_signal_ids=tuple(resolved),
            trailing_updates=tuple(trailing),
            time_exits=tuple(exits),
        )

    def _detect_offset(self, provider: Any, now: datetime) -> None:
        samples = []
        for _ in range(OFFSET_SAMPLE_COUNT):
            tick = provider.latest_tick(self.symbol)
            if not tick.fresh:
                raise RuntimeError("cannot detect offset from a stale tick")
            samples.append(
                OffsetSample(
                    raw_epoch_seconds=tick.timestamp.raw_epoch_seconds,
                    host_utc=now,
                )
            )
        detection = detect_broker_utc_offset(samples, detected_at_utc=now)
        previous = self.packet_store.latest_offset(self.symbol)
        if (
            previous is None
            or previous.offset_seconds != detection.offset_seconds
        ):
            self.packet_store.record_offset_event(
                symbol=self.symbol,
                offset_seconds=detection.offset_seconds,
                sample_count=detection.sample_count,
                max_deviation_seconds=detection.max_deviation_seconds,
                detected_at_utc=now,
            )
            self._event(
                "broker_offset_detected",
                f"offset={detection.offset_seconds}s",
            )
        if hasattr(provider, "set_utc_offset"):
            provider.set_utc_offset(detection.offset_seconds)

    def _ingest_ticks(
        self, provider: Any, now: datetime, lookback: timedelta
    ) -> int:
        status = self.status()
        start = status.last_ingested_tick_utc or (now - lookback)
        start = max(start, now - lookback)
        inserted = 0
        if now > start:
            historical = provider.historical_ticks(self.symbol, start, now)
            inserted += self.tick_archive.ingest(
                historical, source="recovery"
            )
        latest = provider.latest_tick(self.symbol)
        inserted += self.tick_archive.ingest([latest], source="live")
        self._set_state(
            last_ingested_tick_utc=(
                latest.timestamp.normalized_utc.astimezone(UTC).isoformat()
            )
        )
        return inserted

    def _resolve_entered_signals(self, now: datetime) -> list[str]:
        resolved: list[str] = []
        offset = 0
        while True:
            page = self.signal_journal.list(
                status=SignalStatusV2.ENTERED, limit=100, offset=offset
            )
            if not page:
                break
            offset += len(page)
            for signal in page:
                if signal.decision is SignalDecisionV2.NO_TRADE:
                    continue
                try:
                    existing = self.outcome_journal.get(signal.signal_id)
                    if existing.status in (
                        OutcomeStatus.RESOLVED_TP,
                        OutcomeStatus.RESOLVED_SL,
                    ):
                        continue
                except KeyError:
                    pass
                entry_time = signal.entered_at_utc or signal.submitted_at_utc
                ticks = self.tick_archive.ticks_between(
                    signal.symbol, entry_time, now
                )
                outcome = resolve_from_ticks(signal, ticks)
                self.outcome_journal.record(outcome)
                if outcome.status in (
                    OutcomeStatus.RESOLVED_TP,
                    OutcomeStatus.RESOLVED_SL,
                ):
                    resolved.append(signal.signal_id)
        return resolved

    def _reconcile_inflight_actions(
        self, executor: Any, now: datetime
    ) -> list[str]:
        """Crash-window recovery: SUBMITTING/SUBMITTED actions are
        reconciled against the execution backend instead of being
        retried blindly or silently dropped."""
        reconciled: list[str] = []
        for state in (ActionState.SUBMITTING, ActionState.SUBMITTED):
            for record in self.action_journal.list(state=state, limit=100):
                snapshot = None
                if record.broker_position_ticket is not None and hasattr(
                    executor, "position_snapshot"
                ):
                    snapshot = executor.position_snapshot(
                        record.broker_position_ticket
                    )
                if snapshot is not None:
                    self.action_journal.transition(
                        record.action_id,
                        ActionState.BROKER_CONFIRMED,
                        updates={
                            "reconciliation": {
                                "recovered": True,
                                "position": snapshot,
                            }
                        },
                        event_data={"recovered_after_restart": True},
                    )
                else:
                    self.action_journal.transition(
                        record.action_id,
                        ActionState.FAILED,
                        updates={
                            "error": (
                                "crash-window recovery: no broker evidence"
                                " for this submission; recorded as failed"
                                " honestly"
                            )
                        },
                        event_data={"recovered_after_restart": True},
                    )
                reconciled.append(record.action_id)
        return reconciled

    def _active_standing_policies(
        self, action_types: tuple[ActionType, ...]
    ) -> dict[int, Any]:
        """Standing policies derived from the durable action journal.

        A policy is active when its set action confirmed and no later
        cancel confirmed for the same position ticket. This survives any
        restart because it reads only durable records.
        """
        policies: dict[int, Any] = {}
        cancelled: set[int] = set()
        offset = 0
        while True:
            page = self.action_journal.list(limit=100, offset=offset)
            if not page:
                break
            offset += len(page)
            for record in page:
                if record.state not in (
                    ActionState.BROKER_CONFIRMED,
                    ActionState.RECONCILED,
                ):
                    continue
                ticket = record.broker_position_ticket
                if ticket is None:
                    continue
                if record.action_type is ActionType.TRAILING_STOP_CANCEL:
                    cancelled.add(int(ticket))
                elif record.action_type in action_types:
                    policies.setdefault(int(ticket), record)
        return {
            ticket: record
            for ticket, record in policies.items()
            if ticket not in cancelled
        }

    def _trailing_pass(self, executor: Any, now: datetime) -> list[str]:
        updates: list[str] = []
        policies = self._active_standing_policies(
            (ActionType.TRAILING_STOP_SET,)
        )
        for ticket, record in policies.items():
            snapshot = executor.position_snapshot(ticket)
            if snapshot is None:
                continue
            distance = float(record.params.get("trail_distance", 0.0) or 0.0)
            if distance <= 0:
                continue
            quote = executor.fresh_quote(snapshot["symbol"])
            if snapshot["direction"] == "LONG":
                desired = quote.bid - distance
                improves = (
                    snapshot["stop_loss"] is None
                    or desired > float(snapshot["stop_loss"])
                )
            else:
                desired = quote.ask + distance
                improves = (
                    snapshot["stop_loss"] is None
                    or desired < float(snapshot["stop_loss"])
                )
            if not improves:
                continue
            request = ActionRequest(
                idempotency_key=(
                    f"trail:{ticket}:{int(now.timestamp())}"
                ),
                action_type=ActionType.MODIFY_SLTP,
                origin="supervisor",
                capability_role=record.capability_role,
                execution_mode=record.execution_mode,
                policy_id=record.policy_id,
                experiment_id=record.experiment_id,
                symbol=snapshot["symbol"],
                position_ticket=ticket,
                stop_loss=round(desired, 2),
            )
            result = self.gateway.submit(request, executor)
            if result.state is ActionState.RECONCILED:
                updates.append(result.action_id)
        return updates

    def _standing_exit_pass(self, executor: Any, now: datetime) -> list[str]:
        closed: list[str] = []
        policies = self._active_standing_policies(
            (
                ActionType.TIME_EXIT,
                ActionType.CONDITION_EXIT,
                ActionType.NEWS_EXIT,
            )
        )
        for ticket, record in policies.items():
            snapshot = executor.position_snapshot(ticket)
            if snapshot is None:
                continue
            due = False
            deadline = record.params.get("exit_at_utc")
            if deadline:
                due = now >= datetime.fromisoformat(
                    str(deadline).replace("Z", "+00:00")
                )
            condition = record.params.get("condition")
            if not due and isinstance(condition, dict):
                quote = executor.fresh_quote(snapshot["symbol"])
                kind = condition.get("type")
                price = float(condition.get("price", 0.0) or 0.0)
                if kind == "price_below":
                    due = quote.bid <= price
                elif kind == "price_above":
                    due = quote.ask >= price
            if not due:
                continue
            request = ActionRequest(
                idempotency_key=f"standing-exit:{ticket}:{record.action_id}",
                action_type=ActionType.CLOSE_FULL,
                origin="supervisor",
                capability_role=record.capability_role,
                execution_mode=record.execution_mode,
                policy_id=record.policy_id,
                experiment_id=record.experiment_id,
                symbol=snapshot["symbol"],
                position_ticket=ticket,
            )
            result = self.gateway.submit(request, executor)
            if result.state is ActionState.RECONCILED:
                closed.append(result.action_id)
        return closed

    # -- hourly analysis entry (audit defect 1: packet-bound entry) ---------

    def analysis_pass(
        self,
        provider: Any,
        executor: Any,
        *,
        now: datetime,
    ) -> AnalysisReport:
        moment = now.astimezone(UTC)
        if self.status().state != "running":
            return AnalysisReport(
                ran=False, refusal_reason="runtime is stopped"
            )
        kill = self.gateway.safety.kill_switch()
        if kill.active:
            return AnalysisReport(
                ran=False,
                refusal_reason=f"kill switch is active: {kill.reason}",
            )
        packet_id: str | None = None
        errors: list[str] = []
        try:
            packet = self.packet_builder.build(provider, self.symbol)
            stored = self.packet_store.store(packet)
            packet_id = stored.packet_id
        except Exception as exc:
            errors.append(f"packet construction failed: {exc}")
            self._event("analysis_packet_failed", str(exc))

        entered: list[str] = []
        expired: list[str] = []
        skipped: list[str] = []
        offset = 0
        while True:
            page = self.signal_journal.list(
                status=SignalStatusV2.SUBMITTED, limit=100, offset=offset
            )
            if not page:
                break
            offset += len(page)
            for signal in page:
                if signal.decision is SignalDecisionV2.NO_TRADE:
                    skipped.append(signal.signal_id)
                    continue
                if signal.symbol != self.symbol:
                    skipped.append(signal.signal_id)
                    continue
                # The signal may only enter while its exact stored packet
                # is inside the permitted age window; it is never entered
                # against a newer packet's prices.
                try:
                    bound_packet = self.packet_store.get(signal.packet_id)
                except KeyError:
                    self.signal_journal.cancel_before_entry(
                        signal.signal_id,
                        "bound market packet is not stored",
                        cancelled_at_utc=moment,
                    )
                    expired.append(signal.signal_id)
                    continue
                if bound_packet.content_hash != signal.packet_hash:
                    self.signal_journal.cancel_before_entry(
                        signal.signal_id,
                        "stored packet hash does not match the signal binding",
                        cancelled_at_utc=moment,
                    )
                    expired.append(signal.signal_id)
                    continue
                age = (
                    moment - bound_packet.created_at_utc
                ).total_seconds()
                if age > self.entry_window_seconds:
                    self.signal_journal.cancel_before_entry(
                        signal.signal_id,
                        f"packet expired before entry ({age:.0f}s >"
                        f" {self.entry_window_seconds:.0f}s)",
                        cancelled_at_utc=moment,
                    )
                    expired.append(signal.signal_id)
                    continue
                try:
                    self._enter_signal(signal, executor, moment)
                except Exception as exc:
                    errors.append(
                        f"entry failed for {signal.signal_id}: {exc}"
                    )
                    self._event(
                        "analysis_entry_failed",
                        f"{signal.signal_id}: {exc}",
                    )
                    skipped.append(signal.signal_id)
                    continue
                entered.append(signal.signal_id)
        self._set_state(last_analysis_at_utc=moment.isoformat())
        return AnalysisReport(
            ran=True,
            refusal_reason="",
            packet_id=packet_id,
            entered_signal_ids=tuple(entered),
            expired_signal_ids=tuple(expired),
            skipped_signal_ids=tuple(skipped),
            errors=tuple(errors),
        )

    def _enter_signal(
        self, signal: Any, executor: Any, now: datetime
    ) -> None:
        if signal.execution_mode == ExecutionMode.BROKER_DEMO.value:
            request = ActionRequest(
                idempotency_key=f"signal:{signal.signal_id}:entry",
                action_type=ActionType.MARKET_ENTRY,
                origin="model",
                capability_role=CapabilityRole.BROKER_DEMO_AGENT,
                execution_mode=ExecutionMode.BROKER_DEMO,
                policy_id=signal.policy_id,
                experiment_id=signal.experiment_id,
                symbol=signal.symbol,
                signal_id=signal.signal_id,
                direction=signal.decision.value,
                volume_lots=self.demo_entry_volume_lots,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            result = self.gateway.submit(request, executor)
            if result.state is not ActionState.RECONCILED:
                raise RuntimeError(
                    "demo entry did not confirm:"
                    f" {result.state.value}"
                    f" {result.rejection_reason or result.error}"
                )
        else:
            # internal_paper entries need no broker action; the entry is
            # journalled and the resolver settles it from retained ticks.
            request = ActionRequest(
                idempotency_key=f"signal:{signal.signal_id}:entry",
                action_type=ActionType.MARKET_ENTRY,
                origin="model",
                capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
                execution_mode=ExecutionMode.INTERNAL_PAPER,
                policy_id=signal.policy_id,
                experiment_id=signal.experiment_id,
                symbol=signal.symbol,
                signal_id=signal.signal_id,
                direction=signal.decision.value,
                volume_lots=self.demo_entry_volume_lots,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            result = self.gateway.submit(request, executor)
            if result.state is not ActionState.RECONCILED:
                raise RuntimeError(
                    "paper entry did not confirm:"
                    f" {result.state.value}"
                    f" {result.rejection_reason or result.error}"
                )
        self.signal_journal.mark_entered(
            signal.signal_id, entered_at_utc=now
        )
