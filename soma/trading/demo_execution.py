from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .mt5_provider import MT5Provider, _field, _rows
from .signal_journal import SignalDecision

UTC = timezone.utc
MIRROR_MAGIC = 5052_0099
MAX_COMMENT_LENGTH = 31
_RETCODE_DONE = 10009
_RETCODE_INVALID_FILL = 10030


class DemoExecutionError(RuntimeError):
    """Demo order submission, lookup, or environment failure."""


@dataclass(frozen=True)
class DemoOrderResult:
    client_key: str
    order_ticket: int
    position_ticket: int
    symbol: str
    direction: SignalDecision
    volume: float
    requested_stop_loss: float
    requested_take_profit: float
    fill_price: float
    retcode: int
    environment: str
    submitted_at_utc: datetime


@dataclass(frozen=True)
class BrokerPositionView:
    position_ticket: int
    symbol: str
    volume: float
    price_open: float
    stop_loss: float
    take_profit: float
    comment: str


@dataclass(frozen=True)
class BrokerDealView:
    deal_ticket: int
    order_ticket: int
    position_ticket: int
    price: float
    volume: float
    profit: float
    entry: int
    reason: int
    comment: str


class DemoExecutionAdapter:
    """Demo-only MT5 order adapter for the TL7 mirror.

    Every operation re-verifies the connected account is a demo account
    before touching order APIs; there is no path to live execution.
    Client keys ride in the order comment and the mirror magic number so
    duplicate submissions are detectable directly at the broker.
    """

    def __init__(self, *, provider: MT5Provider, binding: Any) -> None:
        self._provider = provider
        self._mt5 = binding

    def _require_demo(self) -> None:
        health = self._provider.health()
        if not health.initialized or not health.connected:
            raise DemoExecutionError(
                "demo execution requires an initialized connected terminal"
            )
        if health.account_environment != "demo":
            raise DemoExecutionError(
                "demo execution refused: account is not a demo account"
            )

    @staticmethod
    def _client_comment(client_key: str) -> str:
        normalized = str(client_key).strip()
        if not normalized:
            raise DemoExecutionError("client_key must not be empty")
        if len(normalized) > MAX_COMMENT_LENGTH:
            raise DemoExecutionError(
                f"client_key exceeds {MAX_COMMENT_LENGTH} characters and "
                "would be truncated by the broker"
            )
        return normalized

    def find_open_position(
        self, *, symbol: str, client_key: str
    ) -> BrokerPositionView | None:
        self._require_demo()
        comment = self._client_comment(client_key)
        for row in _rows(self._mt5.positions_get(symbol=symbol)):
            row_comment = str(_field(row, "comment", "") or "")
            row_magic = int(_field(row, "magic", 0) or 0)
            if row_magic == MIRROR_MAGIC and row_comment == comment:
                return BrokerPositionView(
                    position_ticket=int(_field(row, "ticket", 0)),
                    symbol=str(_field(row, "symbol", "")),
                    volume=float(_field(row, "volume", 0.0)),
                    price_open=float(_field(row, "price_open", 0.0)),
                    stop_loss=float(_field(row, "sl", 0.0) or 0.0),
                    take_profit=float(_field(row, "tp", 0.0) or 0.0),
                    comment=row_comment,
                )
        return None

    def market_order(
        self,
        *,
        symbol: str,
        direction: SignalDecision,
        volume: float,
        stop_loss: Decimal | float | str,
        take_profit: Decimal | float | str,
        client_key: str,
    ) -> DemoOrderResult:
        self._require_demo()
        comment = self._client_comment(client_key)
        normalized_direction = SignalDecision(direction)
        if normalized_direction is SignalDecision.NO_TRADE:
            raise DemoExecutionError("NO_TRADE cannot submit a demo order")
        existing = self.find_open_position(
            symbol=symbol, client_key=client_key
        )
        if existing is not None:
            raise DemoExecutionError(
                "duplicate demo order refused: client_key already has an "
                f"open broker position {existing.position_ticket}"
            )
        order_type = (
            self._mt5.ORDER_TYPE_BUY
            if normalized_direction is SignalDecision.LONG
            else self._mt5.ORDER_TYPE_SELL
        )
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": 50,
            "magic": MIRROR_MAGIC,
            "comment": comment,
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_FOK,
        }
        check = self._mt5.order_check(request)
        check_retcode = int(_field(check, "retcode", -1) or 0)
        if check_retcode not in (0, _RETCODE_DONE):
            raise DemoExecutionError(
                f"order_check refused the demo order: retcode "
                f"{check_retcode} {_field(check, 'comment', '')}"
            )
        result = self._mt5.order_send(request)
        retcode = int(_field(result, "retcode", -1))
        if retcode == _RETCODE_INVALID_FILL:
            request["type_filling"] = self._mt5.ORDER_FILLING_IOC
            result = self._mt5.order_send(request)
            retcode = int(_field(result, "retcode", -1))
        if retcode != _RETCODE_DONE:
            raise DemoExecutionError(
                f"demo order_send failed: retcode {retcode} "
                f"{_field(result, 'comment', '')}"
            )
        position_ticket = int(
            _field(result, "order", 0)
        )  # for market deals MT5 opens position with the order ticket
        deal_position = self.find_open_position(
            symbol=symbol, client_key=client_key
        )
        if deal_position is not None:
            position_ticket = deal_position.position_ticket
        return DemoOrderResult(
            client_key=comment,
            order_ticket=int(_field(result, "order", 0)),
            position_ticket=position_ticket,
            symbol=symbol,
            direction=normalized_direction,
            volume=float(_field(result, "volume", volume)),
            requested_stop_loss=float(stop_loss),
            requested_take_profit=float(take_profit),
            fill_price=float(_field(result, "price", 0.0)),
            retcode=retcode,
            environment="demo",
            submitted_at_utc=datetime.now(UTC),
        )

    def deals_for_position(
        self, position_ticket: int
    ) -> list[BrokerDealView]:
        self._require_demo()
        deals = _rows(
            self._mt5.history_deals_get(position=int(position_ticket))
        )
        return [
            BrokerDealView(
                deal_ticket=int(_field(row, "ticket", 0)),
                order_ticket=int(_field(row, "order", 0)),
                position_ticket=int(_field(row, "position_id", 0)),
                price=float(_field(row, "price", 0.0)),
                volume=float(_field(row, "volume", 0.0)),
                profit=float(_field(row, "profit", 0.0)),
                entry=int(_field(row, "entry", 0)),
                reason=int(_field(row, "reason", 0)),
                comment=str(_field(row, "comment", "") or ""),
            )
            for row in deals
        ]

    def position_is_open(self, position_ticket: int) -> bool:
        self._require_demo()
        rows = _rows(self._mt5.positions_get(ticket=int(position_ticket)))
        return bool(rows)
