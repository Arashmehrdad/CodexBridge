from __future__ import annotations

from pathlib import Path

import pytest

from soma.trading.action_gateway import (
    ActionGateway,
    ActionRequest,
    ActionState,
    Quote,
    TradingActionJournal,
)
from soma.trading.executors import PaperExecutor
from soma.trading.safety import SafetyLimits, TradingSafetyController
from soma.trading.strategy_policy import (
    ActionType,
    CapabilityRole,
    ExecutionMode,
)

from tests.trading_lab_fixtures import SYMBOL, bitcoin_specification


class QuoteHolder:
    def __init__(self) -> None:
        self.quote = Quote(bid=64_000.0, ask=64_064.0, age_seconds=5.0)

    def __call__(self, _symbol: str) -> Quote:
        return self.quote


@pytest.fixture()
def quotes() -> QuoteHolder:
    return QuoteHolder()


@pytest.fixture()
def executor(quotes: QuoteHolder) -> PaperExecutor:
    return PaperExecutor(
        quote_source=quotes, rules_source=lambda s: bitcoin_specification(s)
    )


@pytest.fixture()
def safety(tmp_path: Path) -> TradingSafetyController:
    return TradingSafetyController(
        tmp_path / "safety.sqlite3", limits=SafetyLimits()
    )


@pytest.fixture()
def journal(tmp_path: Path) -> TradingActionJournal:
    return TradingActionJournal(tmp_path / "actions.sqlite3")


@pytest.fixture()
def gateway(
    journal: TradingActionJournal, safety: TradingSafetyController
) -> ActionGateway:
    return ActionGateway(journal=journal, safety=safety)


def entry_request(
    key: str = "act-1",
    *,
    action_type: ActionType = ActionType.MARKET_ENTRY,
    policy_id: str = "hourly_fixed_bracket_v1",
    role: CapabilityRole = CapabilityRole.INTERNAL_PAPER_AGENT,
    mode: ExecutionMode = ExecutionMode.INTERNAL_PAPER,
    origin: str = "model",
    experiment_id: str = "exp1",
    direction: str = "LONG",
    volume: float | None = 0.01,
    stop_loss: float | None = 63_400.0,
    take_profit: float | None = 65_400.0,
    **extra,
) -> ActionRequest:
    return ActionRequest(
        idempotency_key=key,
        action_type=action_type,
        origin=origin,
        capability_role=role,
        execution_mode=mode,
        policy_id=policy_id,
        experiment_id=experiment_id,
        symbol=SYMBOL,
        direction=direction,
        volume_lots=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        **extra,
    )


def agentic_request(key: str, **overrides) -> ActionRequest:
    overrides.setdefault("policy_id", "agentic_demo_v1")
    return entry_request(key, **overrides)


def test_full_pipeline_reaches_reconciled_with_honest_fill(
    gateway: ActionGateway, executor: PaperExecutor, journal: TradingActionJournal
) -> None:
    record = gateway.submit(entry_request(), executor)

    assert record.state is ActionState.RECONCILED
    assert record.fill_price == 64_064.0  # LONG fills at ask
    assert record.broker_position_ticket is not None
    assert record.margin_estimate == pytest.approx(
        0.01 * 64_064.0 / 500.0
    )
    assert record.order_check["retcode"] == 0
    assert record.reconciliation["consistent"] is True
    assert record.research_dataset_eligible is True
    states = [
        event["event_type"] for event in journal.events(record.action_id)
    ]
    assert states == [
        "state:REQUESTED",
        "state:VALIDATED",
        "state:SUBMITTING",
        "state:SUBMITTED",
        "state:BROKER_CONFIRMED",
        "state:RECONCILED",
    ]

    # Idempotent replay returns the terminal record without re-executing.
    replay = gateway.submit(entry_request(), executor)
    assert replay.action_id == record.action_id
    assert len(executor.positions) == 1


def test_research_collector_cannot_act(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    record = gateway.submit(
        entry_request("act-rc", role=CapabilityRole.RESEARCH_COLLECTOR),
        executor,
    )
    assert record.state is ActionState.REJECTED
    assert "may not act" in record.rejection_reason
    assert executor.positions == {}


def test_live_execution_mode_cannot_be_expressed() -> None:
    with pytest.raises(ValueError):
        ExecutionMode("live")


def test_fixed_bracket_policy_limits_the_surface(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    # No modification action is available to the fixed-bracket strategy.
    record = gateway.submit(
        entry_request(
            "act-mod",
            action_type=ActionType.MODIFY_SLTP,
            position_ticket=1,
            volume=None,
        ),
        executor,
    )
    assert record.state is ActionState.REJECTED
    assert "does not permit modify_sltp" in record.rejection_reason

    # Entry without the model-selected bracket is refused.
    record = gateway.submit(
        entry_request("act-nobracket", stop_loss=None, take_profit=None),
        executor,
    )
    assert record.state is ActionState.REJECTED
    assert "model-selected stop_loss" in record.rejection_reason


def test_duplicate_exposure_is_refused_across_experiments(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    first = gateway.submit(entry_request("act-a"), executor)
    assert first.state is ActionState.RECONCILED

    # Audit defect 4: a new cohort/experiment must not bypass the
    # duplicate-exposure rule for the same symbol/policy.
    second = gateway.submit(
        entry_request("act-b", experiment_id="exp2"), executor
    )
    assert second.state is ActionState.REJECTED
    assert "duplicate exposure refused" in second.rejection_reason
    assert len(executor.positions) == 1

    # A strategy that explicitly allows stacking may stack.
    stacked = gateway.submit(agentic_request("act-c"), executor)
    assert stacked.state is ActionState.RECONCILED
    assert len(executor.positions) == 2


def test_kill_switch_blocks_entries_but_not_emergency_close(
    gateway: ActionGateway,
    executor: PaperExecutor,
    safety: TradingSafetyController,
) -> None:
    opened = gateway.submit(agentic_request("act-open"), executor)
    assert opened.state is ActionState.RECONCILED
    safety.activate_kill_switch("manual pause")

    blocked = gateway.submit(
        agentic_request("act-blocked", experiment_id="exp9"), executor
    )
    assert blocked.state is ActionState.REJECTED
    assert "kill switch" in blocked.rejection_reason

    emergency = gateway.submit(
        ActionRequest(
            idempotency_key="act-emergency",
            action_type=ActionType.EMERGENCY_CLOSE_ALL,
            origin="operator",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="hourly_fixed_bracket_v1",
            experiment_id="exp1",
            symbol="",
        ),
        executor,
    )
    assert emergency.state is ActionState.RECONCILED
    assert executor.positions == {}


def test_stale_price_and_wide_spread_are_refused(
    gateway: ActionGateway, executor: PaperExecutor, quotes: QuoteHolder
) -> None:
    quotes.quote = Quote(bid=64_000.0, ask=64_064.0, age_seconds=500.0)
    stale = gateway.submit(entry_request("act-stale"), executor)
    assert stale.state is ActionState.REJECTED
    assert "stale" in stale.rejection_reason

    quotes.quote = Quote(bid=64_000.0, ask=64_500.0, age_seconds=5.0)
    wide = gateway.submit(entry_request("act-wide"), executor)
    assert wide.state is ActionState.REJECTED
    assert "spread" in wide.rejection_reason


def test_volume_normalization_and_limits(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    off_step = gateway.submit(
        entry_request("act-step", volume=0.013), executor
    )
    assert off_step.state is ActionState.REJECTED
    assert "volume step" in off_step.rejection_reason

    below_min = gateway.submit(
        entry_request("act-min", volume=0.005), executor
    )
    assert below_min.state is ActionState.REJECTED

    over_limit = gateway.submit(
        entry_request("act-limit", volume=0.06), executor
    )
    assert over_limit.state is ActionState.REJECTED
    assert "per-position" in over_limit.rejection_reason


def test_action_rate_limit(
    tmp_path: Path, executor: PaperExecutor
) -> None:
    safety = TradingSafetyController(
        tmp_path / "rate.sqlite3",
        limits=SafetyLimits(maximum_actions_per_hour=1),
    )
    gateway = ActionGateway(
        journal=TradingActionJournal(tmp_path / "rate-actions.sqlite3"),
        safety=safety,
    )
    first = gateway.submit(agentic_request("act-r1"), executor)
    assert first.state is ActionState.RECONCILED
    second = gateway.submit(agentic_request("act-r2"), executor)
    assert second.state is ActionState.REJECTED
    assert "rate limit" in second.rejection_reason


def test_bracket_sides_revalidated_against_fresh_quote(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    inverted = gateway.submit(
        entry_request("act-sides", stop_loss=64_100.0), executor
    )
    assert inverted.state is ActionState.REJECTED
    assert "stop_loss < ask" in inverted.rejection_reason


def test_agentic_management_surface(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    opened = gateway.submit(agentic_request("m-open"), executor)
    ticket = opened.broker_position_ticket

    modified = gateway.submit(
        agentic_request(
            "m-modify",
            action_type=ActionType.MODIFY_SLTP,
            position_ticket=ticket,
            volume=None,
            stop_loss=63_800.0,
            take_profit=None,
        ),
        executor,
    )
    assert modified.state is ActionState.RECONCILED
    assert modified.old_values["stop_loss"] == 63_400.0
    assert modified.new_values["stop_loss"] == 63_800.0

    break_even = gateway.submit(
        agentic_request(
            "m-be",
            action_type=ActionType.BREAK_EVEN,
            position_ticket=ticket,
            volume=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert break_even.state is ActionState.RECONCILED
    assert break_even.new_values["stop_loss"] == 64_064.0  # entry price

    pending = gateway.submit(
        agentic_request(
            "m-pending",
            action_type=ActionType.PENDING_LIMIT_ENTRY,
            price=63_000.0,
        ),
        executor,
    )
    assert pending.state is ActionState.RECONCILED
    assert pending.broker_order_ticket in executor.pending

    cancelled = gateway.submit(
        agentic_request(
            "m-cancel",
            action_type=ActionType.CANCEL_PENDING,
            order_ticket=pending.broker_order_ticket,
            volume=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert cancelled.state is ActionState.RECONCILED
    assert executor.pending == {}

    trailing = gateway.submit(
        agentic_request(
            "m-trail",
            action_type=ActionType.TRAILING_STOP_SET,
            position_ticket=ticket,
            volume=None,
            stop_loss=None,
            take_profit=None,
            params={"trail_distance": 150.0},
        ),
        executor,
    )
    assert trailing.state is ActionState.RECONCILED

    partial = gateway.submit(
        agentic_request(
            "m-partial",
            action_type=ActionType.CLOSE_PARTIAL,
            position_ticket=ticket,
            volume=0.01,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert partial.state is ActionState.RECONCILED

    flat = gateway.submit(
        agentic_request(
            "m-flatten",
            action_type=ActionType.FLATTEN_ACCOUNT,
            volume=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert flat.state is ActionState.RECONCILED
    assert executor.positions == {}


def test_reverse_closes_reconciles_and_reopens_opposite(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    opened = gateway.submit(
        agentic_request("rev-open", volume=0.02), executor
    )
    ticket = opened.broker_position_ticket
    assert executor.positions[ticket].direction == "LONG"

    reversed_record = gateway.submit(
        agentic_request(
            "rev-flip",
            action_type=ActionType.REVERSE,
            position_ticket=ticket,
            volume=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert reversed_record.state is ActionState.RECONCILED
    assert reversed_record.old_values["closed_position"]["direction"] == "LONG"
    assert reversed_record.new_values["direction"] == "SHORT"
    remaining = list(executor.positions.values())
    assert len(remaining) == 1
    assert remaining[0].direction == "SHORT"
    assert remaining[0].volume_lots == pytest.approx(0.02)


def test_reverse_partial_failure_leaves_flat_and_records_honestly(
    gateway: ActionGateway, executor: PaperExecutor
) -> None:
    opened = gateway.submit(
        agentic_request("rvf-open", volume=0.02), executor
    )
    ticket = opened.broker_position_ticket

    original_execute = executor.execute

    def failing_execute(normalized):
        if normalized.request.action_type is ActionType.MARKET_ENTRY:
            raise RuntimeError("simulated reopen outage")
        return original_execute(normalized)

    executor.execute = failing_execute  # type: ignore[method-assign]
    record = gateway.submit(
        agentic_request(
            "rvf-flip",
            action_type=ActionType.REVERSE,
            position_ticket=ticket,
            volume=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert record.state is ActionState.FAILED
    assert "account left flat" in record.error
    assert executor.positions == {}  # honestly flat


def test_paginated_action_listing(
    gateway: ActionGateway,
    executor: PaperExecutor,
    journal: TradingActionJournal,
) -> None:
    gateway.submit(agentic_request("p-1"), executor)
    gateway.submit(
        agentic_request(
            "p-2",
            action_type=ActionType.FLATTEN_ACCOUNT,
            volume=None,
            stop_loss=None,
            take_profit=None,
        ),
        executor,
    )
    assert journal.count() == 2
    assert len(journal.list(limit=1, offset=0)) == 1
    assert len(journal.list(limit=1, offset=1)) == 1
    assert (
        len(journal.list(action_type=ActionType.FLATTEN_ACCOUNT)) == 1
    )
