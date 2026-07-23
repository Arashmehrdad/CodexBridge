from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from soma.trading.action_gateway import (
    ActionGateway,
    ActionRequest,
    ActionState,
    TradingActionJournal,
)
from soma.trading.executors import DemoExecutor
from soma.trading.mt5_provider import MT5Provider
from soma.trading.safety import SafetyLimits, TradingSafetyController
from soma.trading.strategy_policy import (
    ActionType,
    CapabilityRole,
    ExecutionMode,
)

UTC = timezone.utc
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
SYMBOL = "BITCOIN_i"


class FakeDemoBinding:
    ACCOUNT_TRADE_MODE_DEMO = 0
    TIMEFRAME_H4 = 4
    COPY_TICKS_ALL = 3
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_TYPE_BUY_STOP_LIMIT = 6
    ORDER_TYPE_SELL_STOP_LIMIT = 7
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_SLTP = 6
    TRADE_ACTION_MODIFY = 7
    TRADE_ACTION_REMOVE = 8
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, *, demo: bool = True) -> None:
        self.demo = demo
        self.checks: list[dict] = []
        self.sends: list[dict] = []
        self.margin_calls: list[tuple] = []
        self.open_positions: list[SimpleNamespace] = []
        self.reject_first_fok = False
        self.next_ticket = 9001

    # -- provider surface ---------------------------------------------------
    def initialize(self, *args, **kwargs):
        return True

    def shutdown(self):
        return None

    def last_error(self):
        return (0, "ok")

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def account_info(self):
        return SimpleNamespace(
            trade_mode=0 if self.demo else 2,
            server="Alpari-MT5-Demo",
            login=100,
            currency="USD",
            balance=998.72,
            equity=998.72,
        )

    def symbols_get(self):
        return (
            SimpleNamespace(
                name=SYMBOL,
                description="1 LOT = 1 BITCOIN",
                path=f"Crypto CFD_i\\{SYMBOL}",
                visible=True,
            ),
        )

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(
            digits=2,
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=0.01,
            trade_contract_size=1.0,
            volume_min=0.01,
            volume_max=300.0,
            volume_step=0.01,
            trade_mode=4,
            order_mode=63,
            margin_initial=0.0,
            margin_maintenance=0.0,
            currency_base="USD",
            currency_profit="USD",
            currency_margin="USD",
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(
            bid=64_000.0,
            ask=64_064.0,
            last=0.0,
            volume=1.0,
            time=int((NOW - timedelta(seconds=5)).timestamp()),
        )

    # -- order surface ------------------------------------------------------
    def positions_get(self, symbol=None, ticket=None):
        rows = self.open_positions
        if symbol is not None:
            rows = [r for r in rows if r.symbol == symbol]
        if ticket is not None:
            rows = [r for r in rows if r.ticket == ticket]
        return tuple(rows)

    def history_deals_get(self, *args, **kwargs):
        return ()

    def order_calc_margin(self, order_type, symbol, volume, price):
        self.margin_calls.append((order_type, symbol, volume, price))
        return volume * price / 500.0

    def order_check(self, request):
        self.checks.append(dict(request))
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send(self, request):
        if (
            self.reject_first_fok
            and request.get("type_filling") == self.ORDER_FILLING_FOK
        ):
            self.reject_first_fok = False
            return SimpleNamespace(retcode=10030, comment="unsupported fill")
        self.sends.append(dict(request))
        ticket = self.next_ticket
        self.next_ticket += 1
        if request.get("action") == self.TRADE_ACTION_DEAL and not request.get(
            "position"
        ):
            self.open_positions.append(
                SimpleNamespace(
                    ticket=ticket,
                    symbol=request["symbol"],
                    volume=request["volume"],
                    price_open=64_064.0,
                    sl=request.get("sl", 0.0),
                    tp=request.get("tp", 0.0),
                    type=request["type"],
                    comment=request.get("comment", ""),
                    magic=request.get("magic", 0),
                )
            )
        elif request.get("position"):
            self.open_positions = [
                r
                for r in self.open_positions
                if r.ticket != int(request["position"])
            ]
        elif request.get("action") == self.TRADE_ACTION_SLTP:
            pass
        return SimpleNamespace(
            retcode=10009,
            order=ticket,
            volume=request.get("volume", 0.0),
            price=64_064.0,
            comment="done",
        )


@pytest.fixture()
def binding() -> FakeDemoBinding:
    return FakeDemoBinding()


@pytest.fixture()
def executor(binding: FakeDemoBinding) -> DemoExecutor:
    provider = MT5Provider(binding=binding, now=lambda: NOW)
    provider.connect()
    return DemoExecutor(provider=provider, binding=binding)


@pytest.fixture()
def gateway(tmp_path: Path) -> ActionGateway:
    return ActionGateway(
        journal=TradingActionJournal(tmp_path / "actions.sqlite3"),
        safety=TradingSafetyController(
            tmp_path / "safety.sqlite3", limits=SafetyLimits()
        ),
    )


def demo_request(key: str, **overrides) -> ActionRequest:
    defaults = dict(
        idempotency_key=key,
        action_type=ActionType.MARKET_ENTRY,
        origin="model",
        capability_role=CapabilityRole.BROKER_DEMO_AGENT,
        execution_mode=ExecutionMode.BROKER_DEMO,
        policy_id="agentic_demo_v1",
        experiment_id="exp1",
        symbol=SYMBOL,
        direction="LONG",
        volume_lots=0.01,
        stop_loss=63_400.0,
        take_profit=65_400.0,
    )
    defaults.update(overrides)
    return ActionRequest(**defaults)


def test_demo_market_entry_passes_order_check_before_send(
    gateway: ActionGateway, executor: DemoExecutor, binding: FakeDemoBinding
) -> None:
    record = gateway.submit(demo_request("d-1"), executor)

    assert record.state is ActionState.RECONCILED
    assert binding.checks, "order_check must run before order_send"
    assert binding.sends, "order_send happens only through the executor"
    assert binding.margin_calls  # margin calculation happened
    sent = binding.sends[0]
    assert sent["type_filling"] == binding.ORDER_FILLING_FOK
    assert sent["sl"] == 63_400.0
    assert sent["tp"] == 65_400.0
    assert record.margin_estimate == pytest.approx(
        0.01 * 64_064.0 / 500.0
    )
    assert record.reconciliation["position_open"] is True
    assert record.reconciliation["broker_volume_lots"] == 0.01


def test_demo_fok_falls_back_to_ioc(
    gateway: ActionGateway, executor: DemoExecutor, binding: FakeDemoBinding
) -> None:
    binding.reject_first_fok = True
    record = gateway.submit(demo_request("d-2"), executor)
    assert record.state is ActionState.RECONCILED
    assert binding.sends[0]["type_filling"] == binding.ORDER_FILLING_IOC


def test_demo_refuses_non_demo_account(
    gateway: ActionGateway, tmp_path: Path
) -> None:
    binding = FakeDemoBinding(demo=False)
    provider = MT5Provider(binding=binding, now=lambda: NOW)
    provider.connect()
    executor = DemoExecutor(provider=provider, binding=binding)
    record = gateway.submit(demo_request("d-3"), executor)
    assert record.state is ActionState.REJECTED
    assert "not a demo account" in record.rejection_reason
    assert binding.sends == []


def test_demo_sltp_modify_uses_sltp_action_with_old_new_values(
    gateway: ActionGateway, executor: DemoExecutor, binding: FakeDemoBinding
) -> None:
    opened = gateway.submit(demo_request("d-4"), executor)
    ticket = opened.broker_position_ticket

    record = gateway.submit(
        demo_request(
            "d-5",
            action_type=ActionType.MODIFY_SLTP,
            position_ticket=ticket,
            direction=None,
            volume_lots=None,
            stop_loss=63_900.0,
            take_profit=None,
        ),
        executor,
    )
    assert record.state is ActionState.RECONCILED
    assert record.old_values["stop_loss"] == 63_400.0
    assert record.new_values["stop_loss"] == 63_900.0
    sltp = [
        send
        for send in binding.sends
        if send.get("action") == binding.TRADE_ACTION_SLTP
    ]
    assert sltp and sltp[0]["position"] == ticket


def test_demo_pending_place_and_cancel(
    gateway: ActionGateway, executor: DemoExecutor, binding: FakeDemoBinding
) -> None:
    placed = gateway.submit(
        demo_request(
            "d-6",
            action_type=ActionType.PENDING_LIMIT_ENTRY,
            price=63_000.0,
        ),
        executor,
    )
    assert placed.state is ActionState.RECONCILED
    pending_send = binding.sends[0]
    assert pending_send["action"] == binding.TRADE_ACTION_PENDING
    assert pending_send["type"] == binding.ORDER_TYPE_BUY_LIMIT
    assert pending_send["price"] == 63_000.0

    cancelled = gateway.submit(
        demo_request(
            "d-7",
            action_type=ActionType.CANCEL_PENDING,
            order_ticket=placed.broker_order_ticket,
            direction=None,
            volume_lots=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert cancelled.state is ActionState.RECONCILED
    assert binding.sends[-1]["action"] == binding.TRADE_ACTION_REMOVE
