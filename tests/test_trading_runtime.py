from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from soma.trading.market_packet import MarketPacketBuilder
from soma.trading.mt5_provider import HistoricalTick
from soma.trading.outcome_resolver import OutcomeStatus, SignalOutcomeJournal
from soma.trading.packet_store import MarketPacketStore
from soma.trading.safety import SafetyLimits, TradingSafetyController
from soma.trading.signal_journal_v2 import (
    SignalDecisionV2,
    SignalJournalV2,
    SignalStatusV2,
    SignalSubmissionV2,
)
from soma.trading.strategy_policy import (
    ActionType,
    CapabilityRole,
    ExecutionMode,
)
from soma.trading.tick_archive import TickArchive
from soma.trading.trading_runtime import TradingRuntime

from tests.trading_lab_fixtures import (
    NOW,
    OFFSET,
    SYMBOL,
    PacketProvider,
    build_packet,
    provider_timestamp,
)

UTC = timezone.utc


class RuntimeProvider(PacketProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.recovered_ticks: list[HistoricalTick] = []
        self.utc_offset_applied: int | None = None
        self.fail_h4 = False
        self.fail_specification = False

    def historical_ticks(self, _symbol, _start, _end):
        return list(self.recovered_ticks)

    def set_utc_offset(self, offset_seconds: int) -> None:
        self.utc_offset_applied = int(offset_seconds)

    def h4_candles(self, symbol, *, completed_count: int = 200):
        if self.fail_h4:
            raise RuntimeError("simulated H4 outage")
        return super().h4_candles(symbol, completed_count=completed_count)

    def symbol_specification(self, symbol):
        if self.fail_specification:
            raise RuntimeError("simulated specification outage")
        return super().symbol_specification(symbol)


def historical_tick(at: datetime, bid: float, ask: float) -> HistoricalTick:
    return HistoricalTick(
        symbol=SYMBOL,
        bid=bid,
        ask=ask,
        last=0.0,
        volume=1.0,
        flags=6,
        timestamp=provider_timestamp(int(at.timestamp()) + OFFSET),
    )


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.quote = Quote(bid=64_000.0, ask=64_064.0, age_seconds=5.0)
        self.executor = PaperExecutor(
            quote_source=lambda _s: self.quote,
            rules_source=lambda s: PacketProvider().symbol_specification(s),
        )
        self.provider = RuntimeProvider()
        self.runtime = self.build_runtime()

    def build_runtime(self) -> TradingRuntime:
        """Fresh objects over the same durable files (a restart)."""
        packet_store = MarketPacketStore(self.tmp_path / "packets.sqlite3")
        return TradingRuntime(
            runtime_db_path=self.tmp_path / "runtime.sqlite3",
            packet_store=packet_store,
            signal_journal=SignalJournalV2(
                self.tmp_path / "signals.sqlite3", packet_store
            ),
            outcome_journal=SignalOutcomeJournal(
                self.tmp_path / "outcomes.sqlite3"
            ),
            tick_archive=TickArchive(
                self.tmp_path / "ticks.sqlite3", self.tmp_path / "archives"
            ),
            action_journal=TradingActionJournal(
                self.tmp_path / "actions.sqlite3"
            ),
            gateway=ActionGateway(
                journal=TradingActionJournal(
                    self.tmp_path / "actions.sqlite3"
                ),
                safety=TradingSafetyController(
                    self.tmp_path / "safety.sqlite3", limits=SafetyLimits()
                ),
            ),
            symbol=SYMBOL,
            packet_builder=MarketPacketBuilder(now=lambda: NOW),
        )

    def submit_signal(
        self,
        key: str = "sig-key-1",
        *,
        execution_mode: str = "internal_paper",
        submitted_at: datetime | None = None,
    ):
        packet = self.runtime.packet_store.store(
            build_packet(), inserted_at_utc=NOW
        )
        return self.runtime.signal_journal.submit(
            key,
            SignalSubmissionV2(
                packet_id=packet.packet_id,
                decision=SignalDecisionV2.LONG,
                confidence=73,
                stop_loss=63_400.0,
                take_profit=65_400.0,
                reason="test",
                news_context="",
                model_version="gpt-test-1",
                prompt_version="prompt-v1",
                policy_id="hourly_fixed_bracket_v1",
                execution_mode=execution_mode,
                experiment_id="exp1",
                submitted_at_utc=submitted_at or (NOW + timedelta(minutes=2)),
            ),
        )


@pytest.fixture()
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_runtime_state_is_durable_and_gates_passes(harness: Harness) -> None:
    assert harness.runtime.status().state == "stopped"
    refused = harness.runtime.supervision_pass(
        harness.provider, harness.executor, now=NOW
    )
    assert refused.ran is False
    assert "stopped" in refused.refusal_reason

    harness.runtime.start(now=NOW)
    # A completely fresh runtime over the same files sees the state.
    reopened = harness.build_runtime()
    assert reopened.status().state == "running"
    reopened.stop("operator stop", now=NOW + timedelta(minutes=1))
    assert harness.runtime.status().state == "stopped"
    analysis = harness.runtime.analysis_pass(
        harness.provider, harness.executor, now=NOW
    )
    assert analysis.ran is False


def test_supervision_continues_when_analysis_and_h4_fail(
    harness: Harness,
) -> None:
    # Audit defect 3: packet/H4/analysis failure must not stop
    # monitoring, ingestion, or existing-position management.
    harness.runtime.start(now=NOW)
    signal = harness.submit_signal()
    harness.runtime.signal_journal.mark_entered(
        signal.signal_id, entered_at_utc=NOW + timedelta(minutes=3)
    )
    harness.provider.fail_h4 = True
    harness.provider.fail_specification = True
    harness.provider.recovered_ticks = [
        historical_tick(NOW + timedelta(minutes=4), 64_010.0, 64_074.0),
        historical_tick(NOW + timedelta(minutes=5), 65_450.0, 65_514.0),
    ]

    analysis = harness.runtime.analysis_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=6)
    )
    assert analysis.ran is True
    assert analysis.packet_id is None
    assert any("packet construction failed" in e for e in analysis.errors)

    report = harness.runtime.supervision_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=6)
    )
    assert report.ran is True
    steps = {step.step: step.ok for step in report.steps}
    assert steps["symbol_rules_refresh"] is False
    assert steps["tick_ingestion"] is True
    assert steps["outcome_resolution"] is True
    # The entered signal resolved take-profit from the recovered ticks
    # even though H4/specification/analysis all failed.
    assert signal.signal_id in report.resolved_signal_ids
    outcome = harness.runtime.outcome_journal.get(signal.signal_id)
    assert outcome.status is OutcomeStatus.RESOLVED_TP
    assert harness.provider.utc_offset_applied == OFFSET


def test_entry_is_bound_to_the_exact_packet_and_age_window(
    harness: Harness,
) -> None:
    # Audit defect 1 (runtime side): the hourly cycle may process only
    # signals bound to their exact stored packet inside the age window.
    harness.runtime.start(now=NOW)
    fresh = harness.submit_signal("fresh-key")

    report = harness.runtime.analysis_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=5)
    )
    assert fresh.signal_id in report.entered_signal_ids
    entered = harness.runtime.signal_journal.get(fresh.signal_id)
    assert entered.status is SignalStatusV2.ENTERED
    # The paper entry went through the guarded gateway.
    assert harness.executor.open_position_count(SYMBOL) == 1

    stale = harness.submit_signal("stale-key")
    late = harness.runtime.analysis_pass(
        harness.provider, harness.executor, now=NOW + timedelta(hours=2)
    )
    assert stale.signal_id in late.expired_signal_ids
    cancelled = harness.runtime.signal_journal.get(stale.signal_id)
    assert cancelled.status is SignalStatusV2.CANCELLED
    assert "expired before entry" in cancelled.cancellation_reason


def test_kill_switch_refuses_analysis_but_not_supervision(
    harness: Harness,
) -> None:
    harness.runtime.start(now=NOW)
    harness.runtime.gateway.safety.activate_kill_switch("pause")
    analysis = harness.runtime.analysis_pass(
        harness.provider, harness.executor, now=NOW
    )
    assert analysis.ran is False
    assert "kill switch" in analysis.refusal_reason
    supervision = harness.runtime.supervision_pass(
        harness.provider, harness.executor, now=NOW
    )
    assert supervision.ran is True


def test_trailing_policy_survives_restart(harness: Harness) -> None:
    harness.runtime.start(now=NOW)
    opened = harness.runtime.gateway.submit(
        ActionRequest(
            idempotency_key="t-open",
            action_type=ActionType.MARKET_ENTRY,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            direction="LONG",
            volume_lots=0.01,
            stop_loss=63_400.0,
            take_profit=66_400.0,
        ),
        harness.executor,
    )
    ticket = opened.broker_position_ticket
    trail = harness.runtime.gateway.submit(
        ActionRequest(
            idempotency_key="t-trail",
            action_type=ActionType.TRAILING_STOP_SET,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            position_ticket=ticket,
            params={"trail_distance": 100.0},
        ),
        harness.executor,
    )
    assert trail.state is ActionState.RECONCILED

    # Restart: fresh runtime over the same durable journals, price rises.
    restarted = harness.build_runtime()
    assert restarted.status().state == "running"
    harness.quote = Quote(bid=64_500.0, ask=64_564.0, age_seconds=5.0)
    report = restarted.supervision_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=30)
    )
    assert report.trailing_updates
    snapshot = harness.executor.position_snapshot(ticket)
    assert snapshot["stop_loss"] == pytest.approx(64_400.0)

    # A second pass without price improvement makes no further change.
    second = restarted.supervision_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=31)
    )
    assert second.trailing_updates == ()


def test_time_exit_policy_closes_after_deadline(harness: Harness) -> None:
    harness.runtime.start(now=NOW)
    opened = harness.runtime.gateway.submit(
        ActionRequest(
            idempotency_key="x-open",
            action_type=ActionType.MARKET_ENTRY,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            direction="LONG",
            volume_lots=0.01,
            stop_loss=63_400.0,
            take_profit=66_400.0,
        ),
        harness.executor,
    )
    deadline = (NOW + timedelta(hours=1)).isoformat()
    harness.runtime.gateway.submit(
        ActionRequest(
            idempotency_key="x-time",
            action_type=ActionType.TIME_EXIT,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            position_ticket=opened.broker_position_ticket,
            params={"exit_at_utc": deadline},
        ),
        harness.executor,
    )
    early = harness.runtime.supervision_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=30)
    )
    assert early.time_exits == ()
    assert harness.executor.positions

    late = harness.runtime.supervision_pass(
        harness.provider, harness.executor, now=NOW + timedelta(hours=2)
    )
    assert late.time_exits
    assert harness.executor.positions == {}


def test_crash_window_actions_reconcile_honestly(harness: Harness) -> None:
    harness.runtime.start(now=NOW)
    journal = harness.runtime.action_journal

    # Crash before any broker evidence: recorded as FAILED, not retried.
    ghost = journal.create(
        ActionRequest(
            idempotency_key="crash-ghost",
            action_type=ActionType.MARKET_ENTRY,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            direction="LONG",
            volume_lots=0.01,
        ),
        research_dataset_eligible=False,
    )
    journal.transition(ghost.action_id, ActionState.SUBMITTING)

    # Crash after the broker filled: adopted as BROKER_CONFIRMED.
    opened = harness.runtime.gateway.submit(
        ActionRequest(
            idempotency_key="crash-open",
            action_type=ActionType.MARKET_ENTRY,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            direction="LONG",
            volume_lots=0.01,
            stop_loss=63_400.0,
            take_profit=66_400.0,
        ),
        harness.executor,
    )
    orphan = journal.create(
        ActionRequest(
            idempotency_key="crash-orphan",
            action_type=ActionType.SCALE_IN,
            origin="model",
            capability_role=CapabilityRole.INTERNAL_PAPER_AGENT,
            execution_mode=ExecutionMode.INTERNAL_PAPER,
            policy_id="agentic_demo_v1",
            experiment_id="exp1",
            symbol=SYMBOL,
            direction="LONG",
            volume_lots=0.01,
        ),
        research_dataset_eligible=False,
    )
    journal.transition(
        orphan.action_id,
        ActionState.SUBMITTING,
        updates={
            "broker_position_ticket": opened.broker_position_ticket,
        },
    )

    harness.runtime.supervision_pass(
        harness.provider, harness.executor, now=NOW + timedelta(minutes=5)
    )
    assert journal.get(ghost.action_id).state is ActionState.FAILED
    assert "honestly" in journal.get(ghost.action_id).error
    adopted = journal.get(orphan.action_id)
    assert adopted.state is ActionState.BROKER_CONFIRMED
    assert adopted.reconciliation["recovered"] is True
