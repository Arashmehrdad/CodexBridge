from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from soma.trading.demo_execution import (
    MIRROR_MAGIC,
    DemoExecutionAdapter,
    DemoExecutionError,
)
from soma.trading.demo_mirror import (
    DEAL_ENTRY_IN,
    DEAL_ENTRY_OUT,
    DEAL_REASON_STOP_LOSS,
    DEAL_REASON_TAKE_PROFIT,
    DemoMirror,
    DemoMirrorJournal,
)
from soma.trading.mt5_provider import MT5Provider
from soma.trading.signal_journal import SignalDecision
from soma.trading.virtual_position_journal import (
    VirtualPositionJournal,
)

UTC = timezone.utc
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
SYMBOL = "BITCOIN_i"


class FakeBinding:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, *, demo: bool = True) -> None:
        self.demo = demo
        self.orders_sent: list[dict] = []
        self.open_positions: list[SimpleNamespace] = []
        self.deals: dict[int, list[SimpleNamespace]] = {}
        self.next_ticket = 7001
        self.fill_price = 64070.0
        self.reject_first_fok = False

    # -- provider surface --------------------------------------------------
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

    # -- order surface -----------------------------------------------------
    def positions_get(self, symbol=None, ticket=None):
        rows = self.open_positions
        if symbol is not None:
            rows = [r for r in rows if r.symbol == symbol]
        if ticket is not None:
            rows = [r for r in rows if r.ticket == ticket]
        return tuple(rows)

    def order_check(self, request):
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send(self, request):
        if (
            self.reject_first_fok
            and request["type_filling"] == self.ORDER_FILLING_FOK
        ):
            return SimpleNamespace(retcode=10030, comment="unsupported fill")
        self.orders_sent.append(dict(request))
        ticket = self.next_ticket
        self.next_ticket += 1
        self.open_positions.append(
            SimpleNamespace(
                ticket=ticket,
                symbol=request["symbol"],
                volume=request["volume"],
                price_open=self.fill_price,
                sl=request["sl"],
                tp=request["tp"],
                comment=request["comment"],
                magic=request["magic"],
            )
        )
        self.deals[ticket] = [
            SimpleNamespace(
                ticket=ticket * 10,
                order=ticket,
                position_id=ticket,
                price=self.fill_price,
                volume=request["volume"],
                profit=0.0,
                entry=DEAL_ENTRY_IN,
                reason=0,
                comment=request["comment"],
            )
        ]
        return SimpleNamespace(
            retcode=10009,
            order=ticket,
            volume=request["volume"],
            price=self.fill_price,
            comment="done",
        )

    def close_by_boundary(
        self, ticket: int, *, price: float, reason: int, profit: float
    ) -> None:
        self.open_positions = [
            r for r in self.open_positions if r.ticket != ticket
        ]
        self.deals[ticket].append(
            SimpleNamespace(
                ticket=ticket * 10 + 1,
                order=ticket + 500,
                position_id=ticket,
                price=price,
                volume=0.01,
                profit=profit,
                entry=DEAL_ENTRY_OUT,
                reason=reason,
                comment="[sl/tp]",
            )
        )

    def history_deals_get(self, position=None):
        return tuple(self.deals.get(position, ()))


def make_mirror(
    tmp_path: Path, *, demo: bool = True
) -> tuple[DemoMirror, FakeBinding, VirtualPositionJournal]:
    binding = FakeBinding(demo=demo)
    provider = MT5Provider(binding=binding)
    provider.connect()
    adapter = DemoExecutionAdapter(provider=provider, binding=binding)
    mirror = DemoMirror(
        journal=DemoMirrorJournal(tmp_path / "mirror.sqlite3"),
        adapter=adapter,
        reference_threshold=50,
    )
    positions = VirtualPositionJournal(tmp_path / "positions.sqlite3")
    return mirror, binding, positions


def open_reference_position(
    positions: VirtualPositionJournal, *, threshold: int = 50
):
    return positions.open_position(
        idempotency_key=f"mirror-signal:T{threshold}",
        cohort_id="cohort_mirror",
        threshold=threshold,
        signal_id="mirror-signal",
        decision=SignalDecision.LONG,
        symbol=SYMBOL,
        entry_price="64060",
        stop_loss="63000",
        take_profit="66000",
        normalized_stake_usd="1.00",
        opened_at_utc=NOW,
    )


def test_mirror_open_submits_exactly_one_broker_order(
    tmp_path: Path,
) -> None:
    mirror, binding, positions = make_mirror(tmp_path)
    position = open_reference_position(positions)

    record = mirror.mirror_open(position)
    assert record.position_ticket == 7001
    assert record.environment == "demo"
    assert len(binding.orders_sent) == 1
    sent = binding.orders_sent[0]
    assert sent["comment"] == position.position_id
    assert sent["magic"] == MIRROR_MAGIC
    assert sent["sl"] == 63000.0
    assert sent["tp"] == 66000.0

    # Replay: journal short-circuits, no duplicate broker order.
    again = mirror.mirror_open(position)
    assert again.position_ticket == record.position_ticket
    assert len(binding.orders_sent) == 1


def test_lost_journal_adopts_broker_position_without_duplicate(
    tmp_path: Path,
) -> None:
    mirror, binding, positions = make_mirror(tmp_path)
    position = open_reference_position(positions)
    mirror.mirror_open(position)
    assert len(binding.orders_sent) == 1

    # Simulate a lost journal write: fresh journal, same broker state.
    recovered_mirror = DemoMirror(
        journal=DemoMirrorJournal(tmp_path / "mirror-recovered.sqlite3"),
        adapter=mirror.adapter,
        reference_threshold=50,
    )
    adopted = recovered_mirror.mirror_open(position)
    assert adopted.position_ticket == 7001
    assert len(binding.orders_sent) == 1  # no duplicate order


def test_adapter_refuses_duplicates_and_non_demo(tmp_path: Path) -> None:
    mirror, binding, positions = make_mirror(tmp_path)
    position = open_reference_position(positions)
    mirror.mirror_open(position)
    with pytest.raises(DemoExecutionError, match="duplicate demo order"):
        mirror.adapter.market_order(
            symbol=SYMBOL,
            direction=SignalDecision.LONG,
            volume=0.01,
            stop_loss=63000,
            take_profit=66000,
            client_key=position.position_id,
        )

    live_mirror, _, live_positions = make_mirror(
        tmp_path / "live", demo=False
    )
    live_position = open_reference_position(live_positions)
    with pytest.raises(DemoExecutionError, match="not a demo account"):
        live_mirror.mirror_open(live_position)


def test_only_reference_threshold_is_mirrored(tmp_path: Path) -> None:
    mirror, _, positions = make_mirror(tmp_path)
    other = open_reference_position(positions, threshold=60)
    with pytest.raises(DemoExecutionError, match="reference threshold"):
        mirror.mirror_open(other)


def test_fok_rejection_falls_back_to_ioc(tmp_path: Path) -> None:
    mirror, binding, positions = make_mirror(tmp_path)
    binding.reject_first_fok = True
    position = open_reference_position(positions)
    record = mirror.mirror_open(position)
    assert record.position_ticket == 7001
    assert binding.orders_sent[0]["type_filling"] == (
        FakeBinding.ORDER_FILLING_IOC
    )


def test_reconciliation_matches_stop_loss_outcomes(tmp_path: Path) -> None:
    mirror, binding, positions = make_mirror(tmp_path)
    position = open_reference_position(positions)
    record = mirror.mirror_open(position)

    # Virtual side resolves by stop-loss at the honest bid.
    resolved = positions.observe_tick(
        position.position_id,
        bid=63000,
        ask=63060,
        observed_at_utc=NOW,
    )
    # Broker side closes by stop-loss with the spread cost included.
    binding.close_by_boundary(
        record.position_ticket,
        price=63000.0,
        reason=DEAL_REASON_STOP_LOSS,
        profit=-10.7,
    )

    reconciliation = mirror.reconcile(resolved)
    assert reconciliation["outcomes_match"] is True
    assert reconciliation["duplicate_orders"] is False
    assert reconciliation["order_count"] == 1
    assert reconciliation["broker_outcome"] == "stop_loss"
    assert reconciliation["virtual_outcome"] == "stop_loss"
    assert reconciliation["broker_exit_price"] == 63000.0
    assert reconciliation["entry_spread_difference"] == pytest.approx(
        64070.0 - 64060.0
    )
    stored = mirror.journal.get(position.position_id)
    assert stored.reconciliation["outcomes_match"] is True
    assert Decimal(
        stored.reconciliation["virtual_realized_return"]
    ) < 0


def test_reconciliation_flags_outcome_mismatch(tmp_path: Path) -> None:
    mirror, binding, positions = make_mirror(tmp_path)
    position = open_reference_position(positions)
    record = mirror.mirror_open(position)
    resolved = positions.observe_tick(
        position.position_id,
        bid=63000,
        ask=63060,
        observed_at_utc=NOW,
    )
    binding.close_by_boundary(
        record.position_ticket,
        price=66000.0,
        reason=DEAL_REASON_TAKE_PROFIT,
        profit=19.4,
    )
    reconciliation = mirror.reconcile(resolved)
    assert reconciliation["outcomes_match"] is False
    assert reconciliation["broker_outcome"] == "take_profit"
    assert reconciliation["virtual_outcome"] == "stop_loss"
