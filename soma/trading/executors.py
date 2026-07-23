"""Execution backends owned by the action gateway.

``PaperExecutor`` simulates the complete action surface with honest
bid/ask fills for ``internal_paper`` mode. ``DemoExecutor`` performs
guarded Alpari demo actions through the official MetaTrader5 binding,
re-verifying the demo environment before every call. The model never
receives either object — only the gateway calls them, so raw
``order_send`` is never reachable from a model action.

Standing exit policies (time/condition/news exits, trailing stops) are
durably registered by their confirmed action records in the action
journal; the runtime supervisor derives active policies from the journal
after any restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .action_gateway import (
    ActionRecord,
    CheckResult,
    ExecutionResult,
    NormalizedAction,
    Quote,
)
from .mt5_provider import MT5Provider, SymbolSpecification, _field, _rows
from .strategy_policy import (
    ActionType,
    ExecutionMode,
    STANDING_POLICY_ACTIONS,
)

UTC = timezone.utc
_RETCODE_DONE = 10009
_RETCODE_INVALID_FILL = 10030
DEFAULT_PAPER_LEVERAGE = 500.0


@dataclass
class PaperPosition:
    ticket: int
    symbol: str
    direction: str
    volume_lots: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    targets: list[float] = field(default_factory=list)


@dataclass
class PaperPendingOrder:
    ticket: int
    symbol: str
    direction: str
    volume_lots: float
    price: float
    action_type: ActionType
    stop_loss: float | None
    take_profit: float | None


class PaperExecutor:
    """Deterministic simulated execution with honest bid/ask fills."""

    def __init__(
        self,
        *,
        quote_source: Callable[[str], Quote],
        rules_source: Callable[[str], SymbolSpecification],
    ) -> None:
        self._quotes = quote_source
        self._rules = rules_source
        self.positions: dict[int, PaperPosition] = {}
        self.pending: dict[int, PaperPendingOrder] = {}
        self.realized_today_usd = 0.0
        self._next_ticket = 1000

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.INTERNAL_PAPER

    # -- gateway surface ----------------------------------------------------

    def fresh_quote(self, symbol: str) -> Quote:
        return self._quotes(symbol)

    def symbol_rules(self, symbol: str) -> SymbolSpecification:
        return self._rules(symbol)

    def open_volume_lots(self, symbol: str | None = None) -> float:
        return sum(
            position.volume_lots
            for position in self.positions.values()
            if symbol is None or position.symbol == symbol
        )

    def open_position_count(self, symbol: str) -> int:
        return sum(
            1
            for position in self.positions.values()
            if position.symbol == symbol
        )

    def daily_loss_usd(self) -> float:
        return max(0.0, -self.realized_today_usd)

    def position_snapshot(self, ticket: int) -> dict[str, Any] | None:
        position = self.positions.get(int(ticket))
        if position is None:
            return None
        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "direction": position.direction,
            "volume_lots": position.volume_lots,
            "entry_price": position.entry_price,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
        }

    def order_check(self, normalized: NormalizedAction) -> CheckResult:
        request = normalized.request
        margin: float | None = None
        if (
            normalized.volume_lots is not None
            and normalized.quote is not None
            and normalized.rules is not None
        ):
            reference = (
                normalized.quote.ask
                if request.direction == "LONG"
                else normalized.quote.bid
            )
            margin = (
                normalized.volume_lots
                * reference
                * (normalized.rules.contract_size or 1.0)
                / DEFAULT_PAPER_LEVERAGE
            )
        return CheckResult(
            ok=True, retcode=0, comment="paper", margin_estimate=margin
        )

    def reconcile(self, record: ActionRecord) -> dict[str, Any]:
        known = record.broker_position_ticket in self.positions
        pending_known = record.broker_order_ticket in self.pending
        return {
            "mode": "internal_paper",
            "position_open": known,
            "pending_open": pending_known,
            "open_position_count": len(self.positions),
            "consistent": True,
        }

    # -- execution ----------------------------------------------------------

    def _ticket(self) -> int:
        self._next_ticket += 1
        return self._next_ticket

    def _position(self, ticket: int | None) -> PaperPosition:
        if ticket is None or ticket not in self.positions:
            raise RuntimeError(f"paper position {ticket} does not exist")
        return self.positions[ticket]

    def _close_position(
        self, position: PaperPosition, volume: float | None = None
    ) -> tuple[float, float]:
        quote = self._quotes(position.symbol)
        exit_price = (
            quote.bid if position.direction == "LONG" else quote.ask
        )
        rules = self._rules(position.symbol)
        contract = rules.contract_size or 1.0
        close_volume = min(volume or position.volume_lots, position.volume_lots)
        move = (
            exit_price - position.entry_price
            if position.direction == "LONG"
            else position.entry_price - exit_price
        )
        pnl = move * close_volume * contract
        self.realized_today_usd += pnl
        position.volume_lots = round(position.volume_lots - close_volume, 8)
        if position.volume_lots <= 1e-9:
            self.positions.pop(position.ticket, None)
        return exit_price, pnl

    def execute(self, normalized: NormalizedAction) -> ExecutionResult:
        request = normalized.request
        action = request.action_type

        if action in STANDING_POLICY_ACTIONS:
            return ExecutionResult(
                order_ticket=None,
                position_ticket=request.position_ticket,
                fill_price=None,
                new_values=dict(request.params),
                details={"standing_policy_registered": action.value},
            )

        if action in (
            ActionType.MARKET_ENTRY,
            ActionType.SCALE_IN,
            ActionType.HEDGE_OPEN,
        ):
            quote = normalized.quote or self._quotes(request.symbol)
            fill = quote.ask if request.direction == "LONG" else quote.bid
            ticket = self._ticket()
            self.positions[ticket] = PaperPosition(
                ticket=ticket,
                symbol=request.symbol,
                direction=str(request.direction),
                volume_lots=float(normalized.volume_lots or 0.0),
                entry_price=fill,
                stop_loss=normalized.stop_loss,
                take_profit=normalized.take_profit,
            )
            return ExecutionResult(
                order_ticket=ticket,
                position_ticket=ticket,
                fill_price=fill,
                new_values={
                    "direction": request.direction,
                    "volume_lots": normalized.volume_lots,
                    "stop_loss": normalized.stop_loss,
                    "take_profit": normalized.take_profit,
                },
                details={"paper_fill": True},
            )

        if action in (ActionType.CLOSE_FULL, ActionType.HEDGE_CLOSE):
            position = self._position(request.position_ticket)
            old = {
                "direction": position.direction,
                "volume_lots": position.volume_lots,
                "entry_price": position.entry_price,
            }
            exit_price, pnl = self._close_position(position)
            return ExecutionResult(
                order_ticket=self._ticket(),
                position_ticket=position.ticket,
                fill_price=exit_price,
                old_values=old,
                new_values={"closed": True, "realized_pnl_usd": pnl},
            )

        if action in (ActionType.CLOSE_PARTIAL, ActionType.SCALE_OUT):
            position = self._position(request.position_ticket)
            old = {"volume_lots": position.volume_lots}
            exit_price, pnl = self._close_position(
                position, normalized.volume_lots
            )
            return ExecutionResult(
                order_ticket=self._ticket(),
                position_ticket=request.position_ticket,
                fill_price=exit_price,
                old_values=old,
                new_values={
                    "volume_lots": self.positions.get(
                        request.position_ticket,
                        PaperPosition(0, "", "", 0.0, 0.0, None, None),
                    ).volume_lots,
                    "realized_pnl_usd": pnl,
                },
            )

        if action in (
            ActionType.PENDING_LIMIT_ENTRY,
            ActionType.PENDING_STOP_ENTRY,
            ActionType.PENDING_STOP_LIMIT_ENTRY,
        ):
            ticket = self._ticket()
            self.pending[ticket] = PaperPendingOrder(
                ticket=ticket,
                symbol=request.symbol,
                direction=str(request.direction),
                volume_lots=float(normalized.volume_lots or 0.0),
                price=float(normalized.price or 0.0),
                action_type=action,
                stop_loss=normalized.stop_loss,
                take_profit=normalized.take_profit,
            )
            return ExecutionResult(
                order_ticket=ticket,
                position_ticket=None,
                fill_price=None,
                new_values={
                    "price": normalized.price,
                    "volume_lots": normalized.volume_lots,
                },
            )

        if action is ActionType.CANCEL_PENDING:
            order = self.pending.pop(int(request.order_ticket or 0), None)
            if order is None:
                raise RuntimeError(
                    f"pending order {request.order_ticket} does not exist"
                )
            return ExecutionResult(
                order_ticket=order.ticket,
                position_ticket=None,
                fill_price=None,
                old_values={"price": order.price},
                new_values={"cancelled": True},
            )

        if action is ActionType.REPLACE_PENDING:
            order = self.pending.get(int(request.order_ticket or 0))
            if order is None:
                raise RuntimeError(
                    f"pending order {request.order_ticket} does not exist"
                )
            old = {"price": order.price, "volume_lots": order.volume_lots}
            if normalized.price is not None:
                order.price = normalized.price
            if normalized.volume_lots is not None:
                order.volume_lots = normalized.volume_lots
            if normalized.stop_loss is not None:
                order.stop_loss = normalized.stop_loss
            if normalized.take_profit is not None:
                order.take_profit = normalized.take_profit
            return ExecutionResult(
                order_ticket=order.ticket,
                position_ticket=None,
                fill_price=None,
                old_values=old,
                new_values={
                    "price": order.price,
                    "volume_lots": order.volume_lots,
                },
            )

        if action in (
            ActionType.SET_SLTP,
            ActionType.MODIFY_SLTP,
            ActionType.REMOVE_SLTP,
            ActionType.BREAK_EVEN,
            ActionType.LOCK_PROFIT,
            ActionType.SET_MULTIPLE_TARGETS,
        ):
            position = self._position(request.position_ticket)
            old = {
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "targets": list(position.targets),
            }
            if action is ActionType.REMOVE_SLTP:
                position.stop_loss = None
                position.take_profit = None
            elif action is ActionType.BREAK_EVEN:
                offset = float(request.params.get("offset", 0.0) or 0.0)
                position.stop_loss = position.entry_price + (
                    offset
                    if position.direction == "LONG"
                    else -offset
                )
            elif action is ActionType.LOCK_PROFIT:
                lock_price = request.params.get("lock_price")
                if lock_price is None:
                    raise RuntimeError(
                        "lock_profit requires params.lock_price"
                    )
                position.stop_loss = float(lock_price)
            elif action is ActionType.SET_MULTIPLE_TARGETS:
                position.targets = [
                    float(target)
                    for target in request.params.get("targets", [])
                ]
            else:
                if normalized.stop_loss is not None:
                    position.stop_loss = normalized.stop_loss
                if normalized.take_profit is not None:
                    position.take_profit = normalized.take_profit
            return ExecutionResult(
                order_ticket=None,
                position_ticket=position.ticket,
                fill_price=None,
                old_values=old,
                new_values={
                    "stop_loss": position.stop_loss,
                    "take_profit": position.take_profit,
                    "targets": list(position.targets),
                },
            )

        if action in (
            ActionType.FLATTEN_SYMBOL,
            ActionType.FLATTEN_ACCOUNT,
            ActionType.EMERGENCY_CLOSE_ALL,
        ):
            symbol_filter = (
                request.symbol
                if action is ActionType.FLATTEN_SYMBOL
                else None
            )
            closed: list[dict[str, Any]] = []
            for position in list(self.positions.values()):
                if symbol_filter and position.symbol != symbol_filter:
                    continue
                exit_price, pnl = self._close_position(position)
                closed.append(
                    {
                        "ticket": position.ticket,
                        "exit_price": exit_price,
                        "realized_pnl_usd": pnl,
                    }
                )
            cancelled = [
                ticket
                for ticket, order in list(self.pending.items())
                if symbol_filter is None or order.symbol == symbol_filter
            ]
            for ticket in cancelled:
                self.pending.pop(ticket, None)
            return ExecutionResult(
                order_ticket=None,
                position_ticket=None,
                fill_price=None,
                new_values={
                    "closed_positions": closed,
                    "cancelled_pending": cancelled,
                },
            )

        raise RuntimeError(
            f"paper executor does not implement {action.value}"
        )


class DemoExecutor:
    """Guarded Alpari demo execution through the official binding.

    Every call re-verifies the connected account is a demo account.
    Composite/standing actions confirm by durable registration; primitive
    broker operations go through order_check and order_send with FOK to
    IOC fallback.
    """

    def __init__(
        self,
        *,
        provider: MT5Provider,
        binding: Any,
        magic: int = 5052_0100,
    ) -> None:
        self._provider = provider
        self._mt5 = binding
        self._magic = int(magic)

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.BROKER_DEMO

    def _require_demo(self) -> None:
        health = self._provider.health()
        if not health.initialized or not health.connected:
            raise RuntimeError(
                "demo execution requires an initialized connected terminal"
            )
        if health.account_environment != "demo":
            raise RuntimeError(
                "demo execution refused: account is not a demo account"
            )

    # -- gateway surface ----------------------------------------------------

    def fresh_quote(self, symbol: str) -> Quote:
        self._require_demo()
        tick = self._provider.latest_tick(symbol)
        if not tick.fresh:
            raise RuntimeError(
                f"latest tick for {symbol} is stale"
                f" ({tick.age_seconds:.1f}s old)"
            )
        return Quote(bid=tick.bid, ask=tick.ask, age_seconds=tick.age_seconds)

    def symbol_rules(self, symbol: str) -> SymbolSpecification:
        self._require_demo()
        # symbol_info() is re-read on every call: broker rules are never
        # cached across reconnects.
        return self._provider.symbol_specification(symbol)

    def open_volume_lots(self, symbol: str | None = None) -> float:
        self._require_demo()
        rows = (
            _rows(self._mt5.positions_get(symbol=symbol))
            if symbol
            else _rows(self._mt5.positions_get())
        )
        return sum(float(_field(row, "volume", 0.0) or 0.0) for row in rows)

    def open_position_count(self, symbol: str) -> int:
        self._require_demo()
        return len(_rows(self._mt5.positions_get(symbol=symbol)))

    def daily_loss_usd(self) -> float:
        self._require_demo()
        now = datetime.now(UTC)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = _rows(self._mt5.history_deals_get(midnight, now))
        total = sum(float(_field(row, "profit", 0.0) or 0.0) for row in deals)
        return max(0.0, -total)

    def position_snapshot(self, ticket: int) -> dict[str, Any] | None:
        self._require_demo()
        rows = _rows(self._mt5.positions_get(ticket=int(ticket)))
        if not rows:
            return None
        row = rows[0]
        return {
            "ticket": int(_field(row, "ticket", 0)),
            "symbol": str(_field(row, "symbol", "")),
            "direction": (
                "LONG"
                if int(_field(row, "type", 0)) == self._mt5.ORDER_TYPE_BUY
                else "SHORT"
            ),
            "volume_lots": float(_field(row, "volume", 0.0)),
            "entry_price": float(_field(row, "price_open", 0.0)),
            "stop_loss": float(_field(row, "sl", 0.0) or 0.0) or None,
            "take_profit": float(_field(row, "tp", 0.0) or 0.0) or None,
        }

    # -- request building ---------------------------------------------------

    def _entry_request(self, normalized: NormalizedAction) -> dict[str, Any]:
        request = normalized.request
        action = request.action_type
        long_side = request.direction == "LONG"
        if action in (
            ActionType.MARKET_ENTRY,
            ActionType.SCALE_IN,
            ActionType.HEDGE_OPEN,
        ):
            order_type = (
                self._mt5.ORDER_TYPE_BUY
                if long_side
                else self._mt5.ORDER_TYPE_SELL
            )
            trade_action = self._mt5.TRADE_ACTION_DEAL
            price = None
        elif action is ActionType.PENDING_LIMIT_ENTRY:
            order_type = (
                self._mt5.ORDER_TYPE_BUY_LIMIT
                if long_side
                else self._mt5.ORDER_TYPE_SELL_LIMIT
            )
            trade_action = self._mt5.TRADE_ACTION_PENDING
            price = normalized.price
        elif action is ActionType.PENDING_STOP_ENTRY:
            order_type = (
                self._mt5.ORDER_TYPE_BUY_STOP
                if long_side
                else self._mt5.ORDER_TYPE_SELL_STOP
            )
            trade_action = self._mt5.TRADE_ACTION_PENDING
            price = normalized.price
        else:  # stop-limit
            order_type = (
                self._mt5.ORDER_TYPE_BUY_STOP_LIMIT
                if long_side
                else self._mt5.ORDER_TYPE_SELL_STOP_LIMIT
            )
            trade_action = self._mt5.TRADE_ACTION_PENDING
            price = normalized.price
        built: dict[str, Any] = {
            "action": trade_action,
            "symbol": request.symbol,
            "volume": float(normalized.volume_lots or 0.0),
            "type": order_type,
            "deviation": 50,
            "magic": self._magic,
            "comment": request.idempotency_key[:31],
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_FOK,
        }
        if price is not None:
            built["price"] = float(price)
        if action is ActionType.PENDING_STOP_LIMIT_ENTRY:
            built["stoplimit"] = float(
                request.params.get("stop_limit_price", 0.0)
            )
        if normalized.stop_loss is not None:
            built["sl"] = float(normalized.stop_loss)
        if normalized.take_profit is not None:
            built["tp"] = float(normalized.take_profit)
        return built

    def _close_request(
        self, position: Any, volume: float | None
    ) -> dict[str, Any]:
        position_type = int(_field(position, "type", 0))
        opposite = (
            self._mt5.ORDER_TYPE_SELL
            if position_type == self._mt5.ORDER_TYPE_BUY
            else self._mt5.ORDER_TYPE_BUY
        )
        return {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": str(_field(position, "symbol", "")),
            "volume": float(volume or _field(position, "volume", 0.0)),
            "type": opposite,
            "position": int(_field(position, "ticket", 0)),
            "deviation": 50,
            "magic": self._magic,
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_FOK,
        }

    def _position_by_ticket(self, ticket: int | None) -> Any:
        rows = _rows(self._mt5.positions_get(ticket=int(ticket or 0)))
        if not rows:
            raise RuntimeError(f"broker position {ticket} does not exist")
        return rows[0]

    def _send(self, request: dict[str, Any]) -> Any:
        result = self._mt5.order_send(request)
        retcode = int(_field(result, "retcode", -1))
        if (
            retcode == _RETCODE_INVALID_FILL
            and request.get("type_filling") == self._mt5.ORDER_FILLING_FOK
        ):
            request = dict(request)
            request["type_filling"] = self._mt5.ORDER_FILLING_IOC
            result = self._mt5.order_send(request)
            retcode = int(_field(result, "retcode", -1))
        if retcode != _RETCODE_DONE:
            raise RuntimeError(
                f"demo order_send failed: retcode {retcode}"
                f" {_field(result, 'comment', '')}"
            )
        return result

    # -- order check and execution ------------------------------------------

    def order_check(self, normalized: NormalizedAction) -> CheckResult:
        self._require_demo()
        request = normalized.request
        action = request.action_type
        if action in (
            ActionType.MARKET_ENTRY,
            ActionType.SCALE_IN,
            ActionType.HEDGE_OPEN,
            ActionType.PENDING_LIMIT_ENTRY,
            ActionType.PENDING_STOP_ENTRY,
            ActionType.PENDING_STOP_LIMIT_ENTRY,
        ):
            built = self._entry_request(normalized)
            if built["action"] == self._mt5.TRADE_ACTION_DEAL:
                quote = normalized.quote or self.fresh_quote(request.symbol)
                built["price"] = (
                    quote.ask if request.direction == "LONG" else quote.bid
                )
            margin = None
            calc = getattr(self._mt5, "order_calc_margin", None)
            if calc is not None:
                margin = calc(
                    built["type"],
                    built["symbol"],
                    built["volume"],
                    built.get("price", 0.0),
                )
            check = self._mt5.order_check(built)
            retcode = int(_field(check, "retcode", -1) or 0)
            return CheckResult(
                ok=retcode in (0, _RETCODE_DONE),
                retcode=retcode,
                comment=str(_field(check, "comment", "") or ""),
                margin_estimate=(
                    float(margin) if margin is not None else None
                ),
            )
        # Modifications, closes, and standing registrations are validated
        # structurally by the gateway; the broker validates on execution.
        return CheckResult(ok=True, retcode=0, comment="not an order action")

    def execute(self, normalized: NormalizedAction) -> ExecutionResult:
        self._require_demo()
        request = normalized.request
        action = request.action_type

        if action in STANDING_POLICY_ACTIONS:
            return ExecutionResult(
                order_ticket=None,
                position_ticket=request.position_ticket,
                fill_price=None,
                new_values=dict(request.params),
                details={"standing_policy_registered": action.value},
            )

        if action in (
            ActionType.MARKET_ENTRY,
            ActionType.SCALE_IN,
            ActionType.HEDGE_OPEN,
            ActionType.PENDING_LIMIT_ENTRY,
            ActionType.PENDING_STOP_ENTRY,
            ActionType.PENDING_STOP_LIMIT_ENTRY,
        ):
            built = self._entry_request(normalized)
            result = self._send(built)
            order_ticket = int(_field(result, "order", 0))
            return ExecutionResult(
                order_ticket=order_ticket,
                position_ticket=(
                    order_ticket
                    if built["action"] == self._mt5.TRADE_ACTION_DEAL
                    else None
                ),
                fill_price=float(_field(result, "price", 0.0)) or None,
                new_values={
                    "direction": request.direction,
                    "volume_lots": normalized.volume_lots,
                    "stop_loss": normalized.stop_loss,
                    "take_profit": normalized.take_profit,
                },
            )

        if action in (
            ActionType.CLOSE_FULL,
            ActionType.CLOSE_PARTIAL,
            ActionType.SCALE_OUT,
            ActionType.HEDGE_CLOSE,
        ):
            position = self._position_by_ticket(request.position_ticket)
            old = {
                "direction": (
                    "LONG"
                    if int(_field(position, "type", 0))
                    == self._mt5.ORDER_TYPE_BUY
                    else "SHORT"
                ),
                "volume_lots": float(_field(position, "volume", 0.0)),
                "entry_price": float(_field(position, "price_open", 0.0)),
            }
            volume = (
                normalized.volume_lots
                if action
                in (ActionType.CLOSE_PARTIAL, ActionType.SCALE_OUT)
                else None
            )
            result = self._send(self._close_request(position, volume))
            return ExecutionResult(
                order_ticket=int(_field(result, "order", 0)),
                position_ticket=int(_field(position, "ticket", 0)),
                fill_price=float(_field(result, "price", 0.0)) or None,
                old_values=old,
                new_values={"closed_volume_lots": volume or old["volume_lots"]},
            )

        if action is ActionType.CANCEL_PENDING:
            result = self._send(
                {
                    "action": self._mt5.TRADE_ACTION_REMOVE,
                    "order": int(request.order_ticket or 0),
                }
            )
            return ExecutionResult(
                order_ticket=int(request.order_ticket or 0),
                position_ticket=None,
                fill_price=None,
                new_values={"cancelled": True},
                details={"retcode": int(_field(result, "retcode", 0))},
            )

        if action is ActionType.REPLACE_PENDING:
            built: dict[str, Any] = {
                "action": self._mt5.TRADE_ACTION_MODIFY,
                "order": int(request.order_ticket or 0),
            }
            if normalized.price is not None:
                built["price"] = float(normalized.price)
            if normalized.stop_loss is not None:
                built["sl"] = float(normalized.stop_loss)
            if normalized.take_profit is not None:
                built["tp"] = float(normalized.take_profit)
            self._send(built)
            return ExecutionResult(
                order_ticket=int(request.order_ticket or 0),
                position_ticket=None,
                fill_price=None,
                new_values={
                    "price": normalized.price,
                    "stop_loss": normalized.stop_loss,
                    "take_profit": normalized.take_profit,
                },
            )

        if action in (
            ActionType.SET_SLTP,
            ActionType.MODIFY_SLTP,
            ActionType.REMOVE_SLTP,
            ActionType.BREAK_EVEN,
            ActionType.LOCK_PROFIT,
        ):
            position = self._position_by_ticket(request.position_ticket)
            old = {
                "stop_loss": float(_field(position, "sl", 0.0) or 0.0),
                "take_profit": float(_field(position, "tp", 0.0) or 0.0),
            }
            entry_price = float(_field(position, "price_open", 0.0))
            long_side = (
                int(_field(position, "type", 0)) == self._mt5.ORDER_TYPE_BUY
            )
            if action is ActionType.REMOVE_SLTP:
                new_sl, new_tp = 0.0, 0.0
            elif action is ActionType.BREAK_EVEN:
                offset = float(request.params.get("offset", 0.0) or 0.0)
                new_sl = entry_price + (offset if long_side else -offset)
                new_tp = old["take_profit"]
            elif action is ActionType.LOCK_PROFIT:
                lock_price = request.params.get("lock_price")
                if lock_price is None:
                    raise RuntimeError("lock_profit requires params.lock_price")
                new_sl = float(lock_price)
                new_tp = old["take_profit"]
            else:
                new_sl = (
                    float(normalized.stop_loss)
                    if normalized.stop_loss is not None
                    else old["stop_loss"]
                )
                new_tp = (
                    float(normalized.take_profit)
                    if normalized.take_profit is not None
                    else old["take_profit"]
                )
            self._send(
                {
                    "action": self._mt5.TRADE_ACTION_SLTP,
                    "symbol": str(_field(position, "symbol", "")),
                    "position": int(_field(position, "ticket", 0)),
                    "sl": new_sl,
                    "tp": new_tp,
                }
            )
            return ExecutionResult(
                order_ticket=None,
                position_ticket=int(_field(position, "ticket", 0)),
                fill_price=None,
                old_values=old,
                new_values={"stop_loss": new_sl, "take_profit": new_tp},
            )

        if action is ActionType.SET_MULTIPLE_TARGETS:
            # Multiple targets on one broker position are represented as a
            # durable standing registration; scale-outs execute per target
            # through the runtime supervisor.
            return ExecutionResult(
                order_ticket=None,
                position_ticket=request.position_ticket,
                fill_price=None,
                new_values={"targets": request.params.get("targets", [])},
                details={"standing_policy_registered": action.value},
            )

        if action in (
            ActionType.FLATTEN_SYMBOL,
            ActionType.FLATTEN_ACCOUNT,
            ActionType.EMERGENCY_CLOSE_ALL,
        ):
            symbol_filter = (
                request.symbol
                if action is ActionType.FLATTEN_SYMBOL
                else None
            )
            rows = (
                _rows(self._mt5.positions_get(symbol=symbol_filter))
                if symbol_filter
                else _rows(self._mt5.positions_get())
            )
            closed: list[dict[str, Any]] = []
            failures: list[dict[str, Any]] = []
            for position in rows:
                try:
                    result = self._send(self._close_request(position, None))
                    closed.append(
                        {
                            "ticket": int(_field(position, "ticket", 0)),
                            "price": float(_field(result, "price", 0.0)),
                        }
                    )
                except Exception as exc:  # keep closing the rest
                    failures.append(
                        {
                            "ticket": int(_field(position, "ticket", 0)),
                            "error": str(exc),
                        }
                    )
            if failures:
                raise RuntimeError(
                    f"flatten closed {len(closed)} positions but failed on"
                    f" {failures}"
                )
            return ExecutionResult(
                order_ticket=None,
                position_ticket=None,
                fill_price=None,
                new_values={"closed_positions": closed},
            )

        raise RuntimeError(f"demo executor does not implement {action.value}")

    def reconcile(self, record: ActionRecord) -> dict[str, Any]:
        self._require_demo()
        report: dict[str, Any] = {"mode": "broker_demo"}
        if record.broker_position_ticket is not None:
            rows = _rows(
                self._mt5.positions_get(
                    ticket=int(record.broker_position_ticket)
                )
            )
            report["position_open"] = bool(rows)
            if rows:
                row = rows[0]
                report["broker_volume_lots"] = float(
                    _field(row, "volume", 0.0)
                )
                report["broker_stop_loss"] = float(
                    _field(row, "sl", 0.0) or 0.0
                )
                report["broker_take_profit"] = float(
                    _field(row, "tp", 0.0) or 0.0
                )
            deals = _rows(
                self._mt5.history_deals_get(
                    position=int(record.broker_position_ticket)
                )
            )
            report["deal_count"] = len(deals)
        report["consistent"] = True
        return report
