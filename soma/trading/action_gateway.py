"""Guarded trading action gateway.

Every model action passes one pipeline:

schema validation -> execution-mode policy -> strategy policy ->
fresh-price validation -> symbol/volume normalization -> risk checks ->
margin/profit calculation -> order_check -> idempotent submission ->
durable persistence -> broker reconciliation.

The model never calls ``MetaTrader5.order_send`` — only executors owned
by this gateway touch broker APIs, and the demo executor re-verifies the
demo environment on every call. Each action persists its full state
history (REQUESTED, VALIDATED, REJECTED, SUBMITTING, SUBMITTED,
BROKER_CONFIRMED, FAILED, RECONCILED) with origin, mode, policy,
experiment, signal, research-dataset eligibility, old/new values, and
broker reconciliation evidence.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from .mt5_provider import SymbolSpecification
from .safety import TradingSafetyController
from .strategy_policy import (
    ActionType,
    CapabilityRole,
    EMERGENCY_ACTIONS,
    ENTRY_ACTIONS,
    ExecutionMode,
    STANDING_POLICY_ACTIONS,
    StrategyPolicy,
    resolve_policy,
    role_may_act,
)
from .versions import POLICY_HOURLY_FIXED_BRACKET_V1

UTC = timezone.utc


class ActionState(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    BROKER_CONFIRMED = "BROKER_CONFIRMED"
    FAILED = "FAILED"
    RECONCILED = "RECONCILED"


TERMINAL_STATES = frozenset(
    {
        ActionState.REJECTED,
        ActionState.BROKER_CONFIRMED,
        ActionState.FAILED,
        ActionState.RECONCILED,
    }
)

# Actions that need a direction and, usually, a volume.
DIRECTIONAL_ACTIONS = frozenset(
    {
        ActionType.MARKET_ENTRY,
        ActionType.PENDING_LIMIT_ENTRY,
        ActionType.PENDING_STOP_ENTRY,
        ActionType.PENDING_STOP_LIMIT_ENTRY,
        ActionType.SCALE_IN,
        ActionType.HEDGE_OPEN,
    }
)

PENDING_ACTIONS = frozenset(
    {
        ActionType.PENDING_LIMIT_ENTRY,
        ActionType.PENDING_STOP_ENTRY,
        ActionType.PENDING_STOP_LIMIT_ENTRY,
    }
)


@dataclass(frozen=True)
class ActionRequest:
    idempotency_key: str
    action_type: ActionType
    origin: str  # model | operator | supervisor
    capability_role: CapabilityRole
    execution_mode: ExecutionMode
    policy_id: str
    experiment_id: str
    symbol: str
    signal_id: str | None = None
    direction: str | None = None  # LONG | SHORT
    volume_lots: float | None = None
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    position_ticket: int | None = None
    order_ticket: int | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    age_seconds: float

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    retcode: int
    comment: str
    margin_estimate: float | None = None
    expected_profit_at_tp: float | None = None
    expected_loss_at_sl: float | None = None


@dataclass(frozen=True)
class ExecutionResult:
    order_ticket: int | None
    position_ticket: int | None
    fill_price: float | None
    old_values: dict[str, Any] = field(default_factory=dict)
    new_values: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedAction:
    request: ActionRequest
    quote: Quote | None
    rules: SymbolSpecification | None
    volume_lots: float | None
    price: float | None
    stop_loss: float | None
    take_profit: float | None


class ActionExecutor(Protocol):
    """Execution backend owned by the gateway; the model never sees it."""

    @property
    def mode(self) -> ExecutionMode: ...

    def fresh_quote(self, symbol: str) -> Quote: ...

    def symbol_rules(self, symbol: str) -> SymbolSpecification: ...

    def open_volume_lots(self, symbol: str | None = None) -> float: ...

    def open_position_count(self, symbol: str) -> int: ...

    def daily_loss_usd(self) -> float: ...

    def order_check(self, normalized: NormalizedAction) -> CheckResult: ...

    def execute(self, normalized: NormalizedAction) -> ExecutionResult: ...

    def reconcile(self, record: "ActionRecord") -> dict[str, Any]: ...


@dataclass(frozen=True)
class ActionRecord:
    action_id: str
    idempotency_key: str
    action_type: ActionType
    origin: str
    capability_role: CapabilityRole
    execution_mode: ExecutionMode
    policy_id: str
    experiment_id: str
    signal_id: str | None
    symbol: str
    direction: str | None
    volume_lots: float | None
    price: float | None
    stop_loss: float | None
    take_profit: float | None
    params: dict[str, Any]
    state: ActionState
    rejection_reason: str
    error: str
    margin_estimate: float | None
    order_check: dict[str, Any]
    broker_order_ticket: int | None
    broker_position_ticket: int | None
    fill_price: float | None
    old_values: dict[str, Any]
    new_values: dict[str, Any]
    reconciliation: dict[str, Any]
    research_dataset_eligible: bool
    requested_at_utc: datetime
    updated_at_utc: datetime


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class TradingActionJournal:
    """Durable append-only journal for gateway actions."""

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
                CREATE TABLE IF NOT EXISTS trading_actions (
                    action_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    action_type TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    capability_role TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    signal_id TEXT,
                    symbol TEXT NOT NULL,
                    direction TEXT,
                    volume_lots REAL,
                    price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    params_json TEXT NOT NULL DEFAULT '{}',
                    state TEXT NOT NULL,
                    rejection_reason TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    margin_estimate REAL,
                    order_check_json TEXT NOT NULL DEFAULT '{}',
                    broker_order_ticket INTEGER,
                    broker_position_ticket INTEGER,
                    fill_price REAL,
                    old_values_json TEXT NOT NULL DEFAULT '{}',
                    new_values_json TEXT NOT NULL DEFAULT '{}',
                    reconciliation_json TEXT NOT NULL DEFAULT '{}',
                    research_dataset_eligible INTEGER NOT NULL DEFAULT 0,
                    requested_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_actions_symbol"
                " ON trading_actions(symbol, state)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_action_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def create(
        self, request: ActionRequest, *, research_dataset_eligible: bool
    ) -> ActionRecord:
        now = datetime.now(UTC)
        action_id = (
            "act_"
            + sha256(request.idempotency_key.encode("utf-8")).hexdigest()[:24]
        )
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM trading_actions WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                conn.commit()
                return self._row_to_record(existing)
            conn.execute(
                """
                INSERT INTO trading_actions (
                    action_id, idempotency_key, action_type, origin,
                    capability_role, execution_mode, policy_id, experiment_id,
                    signal_id, symbol, direction, volume_lots, price,
                    stop_loss, take_profit, params_json, state,
                    research_dataset_eligible, requested_at_utc,
                    updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    request.idempotency_key,
                    request.action_type.value,
                    request.origin,
                    request.capability_role.value,
                    request.execution_mode.value,
                    request.policy_id,
                    request.experiment_id,
                    request.signal_id,
                    request.symbol,
                    request.direction,
                    request.volume_lots,
                    request.price,
                    request.stop_loss,
                    request.take_profit,
                    _json(request.params),
                    ActionState.REQUESTED.value,
                    1 if research_dataset_eligible else 0,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._append_event(
                conn, action_id, "state:REQUESTED", now, {}
            )
            conn.commit()
        return self.get(action_id)

    def transition(
        self,
        action_id: str,
        new_state: ActionState,
        *,
        expected_states: tuple[ActionState, ...] | None = None,
        updates: dict[str, Any] | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> ActionRecord:
        now = datetime.now(UTC)
        columns: dict[str, Any] = {"state": new_state.value}
        for key, value in (updates or {}).items():
            if key in {
                "params",
                "order_check",
                "old_values",
                "new_values",
                "reconciliation",
            }:
                columns[f"{key}_json" if key != "order_check" else "order_check_json"] = _json(value)
            else:
                columns[key] = value
        columns["updated_at_utc"] = now.isoformat()
        assignments = ", ".join(f"{key} = ?" for key in columns)
        params: list[Any] = list(columns.values())
        where = "action_id = ?"
        params.append(action_id)
        if expected_states is not None:
            placeholders = ", ".join("?" for _ in expected_states)
            where += f" AND state IN ({placeholders})"
            params.extend(state.value for state in expected_states)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            updated = conn.execute(
                f"UPDATE trading_actions SET {assignments} WHERE {where}",
                params,
            )
            if updated.rowcount != 1:
                conn.rollback()
                current = self.get(action_id)
                raise RuntimeError(
                    f"action {action_id} could not transition to"
                    f" {new_state.value} from state {current.state.value}"
                )
            self._append_event(
                conn,
                action_id,
                f"state:{new_state.value}",
                now,
                event_data or {},
            )
            conn.commit()
        return self.get(action_id)

    def get(self, action_id: str) -> ActionRecord:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_actions WHERE action_id = ?",
                (str(action_id).strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Action not found: {action_id}")
        return self._row_to_record(row)

    def get_by_key(self, idempotency_key: str) -> ActionRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_actions WHERE idempotency_key = ?",
                (str(idempotency_key).strip(),),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        state: ActionState | None = None,
        action_type: ActionType | None = None,
        symbol: str | None = None,
    ) -> list[ActionRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must not be negative")
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("state = ?")
            params.append(ActionState(state).value)
        if action_type is not None:
            clauses.append("action_type = ?")
            params.append(ActionType(action_type).value)
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(str(symbol))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_actions"
                + where
                + " ORDER BY requested_at_utc DESC, action_id DESC"
                " LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM trading_actions"
            ).fetchone()
        return int(row["n"])

    def events(self, action_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, occurred_at_utc, data_json"
                " FROM trading_action_events WHERE action_id = ?"
                " ORDER BY id",
                (str(action_id).strip(),),
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
        action_id: str,
        event_type: str,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> None:
        conn.execute(
            "INSERT INTO trading_action_events"
            " (action_id, event_type, occurred_at_utc, data_json)"
            " VALUES (?, ?, ?, ?)",
            (action_id, event_type, occurred_at.isoformat(), _json(data)),
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ActionRecord:
        return ActionRecord(
            action_id=str(row["action_id"]),
            idempotency_key=str(row["idempotency_key"]),
            action_type=ActionType(str(row["action_type"])),
            origin=str(row["origin"]),
            capability_role=CapabilityRole(str(row["capability_role"])),
            execution_mode=ExecutionMode(str(row["execution_mode"])),
            policy_id=str(row["policy_id"]),
            experiment_id=str(row["experiment_id"]),
            signal_id=(
                str(row["signal_id"]) if row["signal_id"] is not None else None
            ),
            symbol=str(row["symbol"]),
            direction=(
                str(row["direction"]) if row["direction"] is not None else None
            ),
            volume_lots=(
                float(row["volume_lots"])
                if row["volume_lots"] is not None
                else None
            ),
            price=float(row["price"]) if row["price"] is not None else None,
            stop_loss=(
                float(row["stop_loss"])
                if row["stop_loss"] is not None
                else None
            ),
            take_profit=(
                float(row["take_profit"])
                if row["take_profit"] is not None
                else None
            ),
            params=json.loads(str(row["params_json"])),
            state=ActionState(str(row["state"])),
            rejection_reason=str(row["rejection_reason"]),
            error=str(row["error"]),
            margin_estimate=(
                float(row["margin_estimate"])
                if row["margin_estimate"] is not None
                else None
            ),
            order_check=json.loads(str(row["order_check_json"])),
            broker_order_ticket=(
                int(row["broker_order_ticket"])
                if row["broker_order_ticket"] is not None
                else None
            ),
            broker_position_ticket=(
                int(row["broker_position_ticket"])
                if row["broker_position_ticket"] is not None
                else None
            ),
            fill_price=(
                float(row["fill_price"])
                if row["fill_price"] is not None
                else None
            ),
            old_values=json.loads(str(row["old_values_json"])),
            new_values=json.loads(str(row["new_values_json"])),
            reconciliation=json.loads(str(row["reconciliation_json"])),
            research_dataset_eligible=bool(
                row["research_dataset_eligible"]
            ),
            requested_at_utc=_parse_utc(str(row["requested_at_utc"])),
            updated_at_utc=_parse_utc(str(row["updated_at_utc"])),
        )


def _structural_validation(request: ActionRequest) -> None:
    """Schema validation that must pass before anything is persisted."""
    if not str(request.idempotency_key).strip():
        raise ValueError("idempotency_key must not be empty")
    ActionType(request.action_type)
    CapabilityRole(request.capability_role)
    ExecutionMode(request.execution_mode)  # live cannot be expressed
    if request.origin not in ("model", "operator", "supervisor"):
        raise ValueError("origin must be model, operator, or supervisor")
    if not str(request.symbol).strip() and request.action_type not in (
        ActionType.FLATTEN_ACCOUNT,
        ActionType.EMERGENCY_CLOSE_ALL,
    ):
        raise ValueError("symbol must not be empty")


def _semantic_validation(request: ActionRequest) -> list[str]:
    problems: list[str] = []
    action = request.action_type
    if action in DIRECTIONAL_ACTIONS:
        if request.direction not in ("LONG", "SHORT"):
            problems.append(f"{action.value} requires direction LONG or SHORT")
        if request.volume_lots is None or request.volume_lots <= 0:
            problems.append(f"{action.value} requires a positive volume_lots")
    if action in PENDING_ACTIONS and (
        request.price is None or request.price <= 0
    ):
        problems.append(f"{action.value} requires a positive pending price")
    if action is ActionType.PENDING_STOP_LIMIT_ENTRY and (
        request.params.get("stop_limit_price") is None
    ):
        problems.append(
            "pending_stop_limit_entry requires params.stop_limit_price"
        )
    if action in (ActionType.CANCEL_PENDING, ActionType.REPLACE_PENDING):
        if request.order_ticket is None:
            problems.append(f"{action.value} requires order_ticket")
    if action in (
        ActionType.CLOSE_PARTIAL,
        ActionType.SCALE_OUT,
    ) and (request.volume_lots is None or request.volume_lots <= 0):
        problems.append(f"{action.value} requires a positive volume_lots")
    if action in (
        ActionType.CLOSE_FULL,
        ActionType.CLOSE_PARTIAL,
        ActionType.SCALE_OUT,
        ActionType.SET_SLTP,
        ActionType.MODIFY_SLTP,
        ActionType.REMOVE_SLTP,
        ActionType.BREAK_EVEN,
        ActionType.LOCK_PROFIT,
        ActionType.SET_MULTIPLE_TARGETS,
        ActionType.REVERSE,
        ActionType.HEDGE_CLOSE,
        ActionType.TRAILING_STOP_SET,
    ) and request.position_ticket is None:
        problems.append(f"{action.value} requires position_ticket")
    if action in (ActionType.SET_SLTP, ActionType.MODIFY_SLTP) and (
        request.stop_loss is None and request.take_profit is None
    ):
        problems.append(f"{action.value} requires stop_loss or take_profit")
    if action is ActionType.SET_MULTIPLE_TARGETS:
        targets = request.params.get("targets")
        if not isinstance(targets, list) or not targets:
            problems.append(
                "set_multiple_targets requires a non-empty params.targets list"
            )
    if action is ActionType.TRAILING_STOP_SET:
        distance = request.params.get("trail_distance")
        if not isinstance(distance, (int, float)) or distance <= 0:
            problems.append(
                "trailing_stop_set requires a positive params.trail_distance"
            )
    if action is ActionType.TIME_EXIT:
        deadline = request.params.get("exit_at_utc")
        if not deadline:
            problems.append("time_exit requires params.exit_at_utc")
    if action is ActionType.CONDITION_EXIT and not request.params.get(
        "condition"
    ):
        problems.append("condition_exit requires params.condition")
    for name, value in (
        ("volume_lots", request.volume_lots),
        ("price", request.price),
        ("stop_loss", request.stop_loss),
        ("take_profit", request.take_profit),
    ):
        if value is not None and value <= 0:
            problems.append(f"{name} must be positive when provided")
    return problems


def _normalize_volume(
    volume: float | None, rules: SymbolSpecification
) -> tuple[float | None, str | None]:
    if volume is None:
        return None, None
    step = rules.volume_step or 0.01
    minimum = rules.minimum_volume or step
    maximum = rules.maximum_volume or volume
    steps = int(round(float(volume) / step))
    normalized = round(steps * step, 8)
    if abs(normalized - float(volume)) > 1e-9:
        return None, (
            f"volume {volume} is not a multiple of the broker volume step"
            f" {step}"
        )
    if normalized < minimum:
        return None, (
            f"volume {volume} is below the broker minimum {minimum}"
        )
    if normalized > maximum:
        return None, (
            f"volume {volume} exceeds the broker maximum {maximum}"
        )
    return normalized, None


def _normalize_price(
    value: float | None, rules: SymbolSpecification
) -> float | None:
    if value is None:
        return None
    return round(float(value), int(rules.digits or 2))


class ActionGateway:
    """The only path from a model request to an execution backend."""

    def __init__(
        self,
        *,
        journal: TradingActionJournal,
        safety: TradingSafetyController,
    ) -> None:
        self.journal = journal
        self.safety = safety

    def submit(
        self, request: ActionRequest, executor: ActionExecutor
    ) -> ActionRecord:
        _structural_validation(request)

        existing = self.journal.get_by_key(request.idempotency_key)
        if existing is not None and existing.state in TERMINAL_STATES:
            return existing  # idempotent replay

        eligible = (
            request.origin == "model"
            and request.policy_id == POLICY_HOURLY_FIXED_BRACKET_V1
            and request.action_type is ActionType.MARKET_ENTRY
        )
        record = (
            existing
            if existing is not None
            else self.journal.create(
                request, research_dataset_eligible=eligible
            )
        )

        def reject(reason: str) -> ActionRecord:
            return self.journal.transition(
                record.action_id,
                ActionState.REJECTED,
                updates={"rejection_reason": reason},
                event_data={"reason": reason},
            )

        # 1. Execution-mode policy.
        if not role_may_act(request.capability_role, request.execution_mode):
            return reject(
                f"capability role {request.capability_role.value} may not act"
                f" in execution mode {request.execution_mode.value}"
            )
        if request.execution_mode is not executor.mode:
            return reject(
                f"execution mode {request.execution_mode.value} does not"
                f" match the {executor.mode.value} executor"
            )

        # 2. Strategy policy.
        try:
            policy = resolve_policy(request.policy_id)
        except ValueError as exc:
            return reject(str(exc))
        emergency = request.action_type in EMERGENCY_ACTIONS
        if not emergency and not policy.allows(request.action_type):
            return reject(
                f"strategy {policy.policy_id} does not permit"
                f" {request.action_type.value}"
            )
        problems = _semantic_validation(request)
        if problems:
            return reject("; ".join(problems))
        if (
            policy.requires_fixed_bracket
            and request.action_type is ActionType.MARKET_ENTRY
            and (request.stop_loss is None or request.take_profit is None)
        ):
            return reject(
                f"{policy.policy_id} requires one model-selected stop_loss"
                " and take_profit at entry"
            )
        # Audit defect 4: duplicate exposure for the same symbol/policy is
        # refused unless the strategy explicitly allows stacking, and the
        # check keys on the symbol alone so cohort/experiment transitions
        # cannot bypass it.
        if (
            request.action_type in ENTRY_ACTIONS
            and not policy.allow_stacking
            and executor.open_position_count(request.symbol) > 0
        ):
            return reject(
                f"duplicate exposure refused: {request.symbol} already has an"
                f" open position and {policy.policy_id} does not allow"
                " stacking"
            )

        # 3. Fresh-price validation.
        quote: Quote | None = None
        if request.symbol:
            try:
                quote = executor.fresh_quote(request.symbol)
            except Exception as exc:
                return reject(f"fresh price unavailable: {exc}")

        # 4. Safety limits.
        violations = self.safety.violations(
            symbol=request.symbol,
            spread_usd=quote.spread if quote else None,
            tick_age_seconds=quote.age_seconds if quote else None,
            requested_volume_lots=(
                request.volume_lots
                if request.action_type in ENTRY_ACTIONS
                else None
            ),
            open_volume_lots=executor.open_volume_lots(None),
            daily_loss_usd=executor.daily_loss_usd(),
            emergency=emergency,
        )
        if violations:
            return reject("; ".join(violations))

        # 5. Symbol/volume normalization.
        rules: SymbolSpecification | None = None
        volume = request.volume_lots
        price = request.price
        stop = request.stop_loss
        target = request.take_profit
        if request.symbol:
            try:
                rules = executor.symbol_rules(request.symbol)
            except Exception as exc:
                return reject(f"symbol rules unavailable: {exc}")
            volume, volume_problem = _normalize_volume(volume, rules)
            if volume_problem:
                return reject(volume_problem)
            price = _normalize_price(price, rules)
            stop = _normalize_price(stop, rules)
            target = _normalize_price(target, rules)

        normalized = NormalizedAction(
            request=request,
            quote=quote,
            rules=rules,
            volume_lots=volume,
            price=price,
            stop_loss=stop,
            take_profit=target,
        )

        # 6. Bracket-side risk checks against the fresh quote.
        if (
            request.action_type is ActionType.MARKET_ENTRY
            and quote is not None
            and stop is not None
            and target is not None
        ):
            if request.direction == "LONG" and not (
                stop < quote.ask < target
            ):
                return reject(
                    "LONG bracket must satisfy stop_loss < ask < take_profit"
                    " at the fresh quote"
                )
            if request.direction == "SHORT" and not (
                target < quote.bid < stop
            ):
                return reject(
                    "SHORT bracket must satisfy take_profit < bid < stop_loss"
                    " at the fresh quote"
                )

        # 7. Margin/profit calculation and order_check.
        try:
            check = executor.order_check(normalized)
        except Exception as exc:
            return reject(f"order_check failed: {exc}")
        if not check.ok:
            return reject(
                f"order_check refused: retcode {check.retcode} {check.comment}"
            )
        self.journal.transition(
            record.action_id,
            ActionState.VALIDATED,
            expected_states=(ActionState.REQUESTED,),
            updates={
                "volume_lots": volume,
                "price": price,
                "stop_loss": stop,
                "take_profit": target,
                "margin_estimate": check.margin_estimate,
                "order_check": {
                    "retcode": check.retcode,
                    "comment": check.comment,
                    "margin_estimate": check.margin_estimate,
                    "expected_profit_at_tp": check.expected_profit_at_tp,
                    "expected_loss_at_sl": check.expected_loss_at_sl,
                },
            },
        )

        # 8. Idempotent submission with durable state around execution.
        self.safety.record_action()
        self.journal.transition(
            record.action_id,
            ActionState.SUBMITTING,
            expected_states=(ActionState.VALIDATED,),
        )
        try:
            if request.action_type is ActionType.REVERSE:
                result = self._execute_reverse(record, normalized, executor)
            else:
                result = executor.execute(normalized)
        except Exception as exc:
            return self.journal.transition(
                record.action_id,
                ActionState.FAILED,
                updates={"error": str(exc)},
                event_data={"error": str(exc)},
            )
        submitted = self.journal.transition(
            record.action_id,
            ActionState.SUBMITTED,
            expected_states=(ActionState.SUBMITTING,),
            updates={
                "broker_order_ticket": result.order_ticket,
                "broker_position_ticket": result.position_ticket,
                "fill_price": result.fill_price,
                "old_values": result.old_values,
                "new_values": result.new_values,
            },
            event_data={"details": result.details},
        )
        confirmed = self.journal.transition(
            submitted.action_id,
            ActionState.BROKER_CONFIRMED,
            expected_states=(ActionState.SUBMITTED,),
        )

        # 9. Broker reconciliation.
        try:
            reconciliation = executor.reconcile(confirmed)
        except Exception as exc:
            return self.journal.transition(
                confirmed.action_id,
                ActionState.BROKER_CONFIRMED,
                expected_states=(ActionState.BROKER_CONFIRMED,),
                updates={"error": f"reconciliation failed: {exc}"},
                event_data={"reconciliation_error": str(exc)},
            )
        return self.journal.transition(
            confirmed.action_id,
            ActionState.RECONCILED,
            expected_states=(ActionState.BROKER_CONFIRMED,),
            updates={"reconciliation": reconciliation},
            event_data={"reconciliation": reconciliation},
        )

    def _execute_reverse(
        self,
        record: ActionRecord,
        normalized: NormalizedAction,
        executor: ActionExecutor,
    ) -> ExecutionResult:
        """Close and reconcile first, then revalidate and open opposite.

        Partial failure leaves the account flat and is recorded honestly:
        the close evidence survives in the action's old_values even when
        the reopen fails.
        """
        request = normalized.request
        close_request = ActionRequest(
            idempotency_key=f"{request.idempotency_key}:reverse-close",
            action_type=ActionType.CLOSE_FULL,
            origin="supervisor",
            capability_role=request.capability_role,
            execution_mode=request.execution_mode,
            policy_id=request.policy_id,
            experiment_id=request.experiment_id,
            symbol=request.symbol,
            position_ticket=request.position_ticket,
        )
        close_result = executor.execute(
            NormalizedAction(
                request=close_request,
                quote=normalized.quote,
                rules=normalized.rules,
                volume_lots=None,
                price=None,
                stop_loss=None,
                take_profit=None,
            )
        )
        closed_direction = str(
            close_result.old_values.get("direction", "")
        )
        opposite = "SHORT" if closed_direction == "LONG" else "LONG"
        # Revalidate with a fresh quote before the opposite entry.
        try:
            fresh = executor.fresh_quote(request.symbol)
        except Exception as exc:
            raise RuntimeError(
                "reverse closed the position but could not revalidate a"
                f" fresh price; account left flat: {exc}"
            ) from exc
        reopen_volume = normalized.volume_lots or float(
            close_result.old_values.get("volume_lots", 0) or 0
        )
        if reopen_volume <= 0:
            raise RuntimeError(
                "reverse closed the position but no reopen volume could be"
                " determined; account left flat"
            )
        open_request = ActionRequest(
            idempotency_key=f"{request.idempotency_key}:reverse-open",
            action_type=ActionType.MARKET_ENTRY,
            origin="supervisor",
            capability_role=request.capability_role,
            execution_mode=request.execution_mode,
            policy_id=request.policy_id,
            experiment_id=request.experiment_id,
            symbol=request.symbol,
            direction=opposite,
            volume_lots=reopen_volume,
            stop_loss=normalized.stop_loss,
            take_profit=normalized.take_profit,
        )
        open_normalized = NormalizedAction(
            request=open_request,
            quote=fresh,
            rules=normalized.rules,
            volume_lots=reopen_volume,
            price=None,
            stop_loss=normalized.stop_loss,
            take_profit=normalized.take_profit,
        )
        check = executor.order_check(open_normalized)
        if not check.ok:
            raise RuntimeError(
                "reverse closed the position but the opposite entry failed"
                f" order_check (retcode {check.retcode} {check.comment});"
                " account left flat"
            )
        try:
            open_result = executor.execute(open_normalized)
        except Exception as exc:
            raise RuntimeError(
                "reverse closed the position but the opposite entry failed;"
                f" account left flat: {exc}"
            ) from exc
        return ExecutionResult(
            order_ticket=open_result.order_ticket,
            position_ticket=open_result.position_ticket,
            fill_price=open_result.fill_price,
            old_values={
                "closed_position": close_result.old_values,
                "close_fill_price": close_result.fill_price,
            },
            new_values={
                "direction": opposite,
                "volume_lots": reopen_volume,
                "stop_loss": normalized.stop_loss,
                "take_profit": normalized.take_profit,
            },
            details={"reverse": True},
        )
