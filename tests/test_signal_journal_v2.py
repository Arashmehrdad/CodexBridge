from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from soma.trading.packet_store import MarketPacketStore
from soma.trading.signal_journal_v2 import (
    SignalDecisionV2,
    SignalJournalV2,
    SignalRejectedError,
    SignalStatusV2,
    SignalSubmissionV2,
)
from soma.trading.versions import SIGNAL_SCHEMA_VERSION

from tests.trading_lab_fixtures import (
    DEVELOPING_OPEN_UTC,
    DEVELOPING_RAW_OPEN,
    NOW,
    SYMBOL,
    build_packet,
)


@pytest.fixture()
def store(tmp_path: Path) -> MarketPacketStore:
    return MarketPacketStore(tmp_path / "packets.sqlite3")


@pytest.fixture()
def journal(tmp_path: Path, store: MarketPacketStore) -> SignalJournalV2:
    return SignalJournalV2(tmp_path / "signals.sqlite3", store)


def submission(
    packet_id: str,
    *,
    decision: SignalDecisionV2 = SignalDecisionV2.LONG,
    confidence: int | None = 73,
    stop_loss: float | None = 63_400.0,
    take_profit: float | None = 65_400.0,
    execution_mode: str = "internal_paper",
    policy_id: str = "hourly_fixed_bracket_v1",
    submitted_at=NOW + timedelta(minutes=2),
) -> SignalSubmissionV2:
    return SignalSubmissionV2(
        packet_id=packet_id,
        decision=decision,
        confidence=confidence,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason="H4 structure retest",
        news_context="",
        model_version="gpt-test-1",
        prompt_version="prompt-v1",
        policy_id=policy_id,
        execution_mode=execution_mode,
        experiment_id="exp1",
        submitted_at_utc=submitted_at,
    )


def stored_packet(store: MarketPacketStore):
    return store.store(build_packet(), inserted_at_utc=NOW)


def test_submission_derives_all_market_facts_from_the_stored_packet(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    record = journal.submit("key-1", submission(packet.packet_id))

    # Audit defect 1: every market fact is derived from the stored packet.
    assert record.packet_id == packet.packet_id
    assert record.packet_hash == packet.content_hash
    assert record.symbol == SYMBOL
    assert record.bid == 64_000.0
    assert record.ask == 64_064.0
    assert record.spread == pytest.approx(64.0)
    assert record.tick_raw_epoch_seconds == packet.tick_raw_epoch_seconds
    assert record.broker_utc_offset_seconds == packet.broker_utc_offset_seconds
    assert record.parent_h4_raw_open_epoch == DEVELOPING_RAW_OPEN
    assert record.parent_h4_open_utc == DEVELOPING_OPEN_UTC
    # Honest LONG entry is the packet ask.
    assert record.entry_reference_price == 64_064.0
    assert record.risk_reward == pytest.approx(
        (65_400.0 - 64_064.0) / (64_064.0 - 63_400.0)
    )
    assert record.schema_version == SIGNAL_SCHEMA_VERSION
    assert record.model_version == "gpt-test-1"
    assert record.policy_id == "hourly_fixed_bracket_v1"
    assert record.status is SignalStatusV2.SUBMITTED

    # Idempotent replay returns the identical record.
    replay = journal.submit("key-1", submission(packet.packet_id))
    assert replay.signal_id == record.signal_id
    assert replay.content_hash == record.content_hash


def test_short_entry_is_the_packet_bid(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    record = journal.submit(
        "key-short",
        submission(
            packet.packet_id,
            decision=SignalDecisionV2.SHORT,
            stop_loss=64_700.0,
            take_profit=62_900.0,
        ),
    )
    assert record.entry_reference_price == 64_000.0
    assert record.risk_reward == pytest.approx(
        (64_000.0 - 62_900.0) / (64_700.0 - 64_000.0)
    )


def test_unknown_packet_is_rejected_with_a_durable_record(
    journal: SignalJournalV2,
) -> None:
    with pytest.raises(SignalRejectedError, match="stored market packet"):
        journal.submit("key-2", submission("mp_missing"))
    rejections = journal.list_rejections()
    assert len(rejections) == 1
    assert rejections[0].packet_id == "mp_missing"
    assert "stored market packet" in rejections[0].rejection_reason


def test_stale_packet_window_is_enforced(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    with pytest.raises(SignalRejectedError, match="permitted window"):
        journal.submit(
            "key-3",
            submission(
                packet.packet_id, submitted_at=NOW + timedelta(hours=2)
            ),
        )
    with pytest.raises(SignalRejectedError, match="predates its market packet"):
        journal.submit(
            "key-4",
            submission(
                packet.packet_id, submitted_at=NOW - timedelta(minutes=10)
            ),
        )
    assert len(journal.list_rejections()) == 2


def test_directional_validation_rejects_bad_brackets_and_confidence(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    with pytest.raises(SignalRejectedError, match="stop_loss < packet ask"):
        journal.submit(
            "key-5",
            submission(packet.packet_id, stop_loss=64_100.0),
        )
    with pytest.raises(SignalRejectedError, match="integer from 50"):
        journal.submit(
            "key-6",
            submission(packet.packet_id, confidence=49),
        )
    with pytest.raises(SignalRejectedError, match="integer from 50"):
        journal.submit(
            "key-7",
            submission(packet.packet_id, confidence=True),
        )
    with pytest.raises(SignalRejectedError, match="model-selected stop_loss"):
        journal.submit(
            "key-8",
            submission(packet.packet_id, stop_loss=None),
        )


def test_no_trade_rejects_confidence_and_brackets(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    record = journal.submit(
        "key-9",
        submission(
            packet.packet_id,
            decision=SignalDecisionV2.NO_TRADE,
            confidence=None,
            stop_loss=None,
            take_profit=None,
        ),
    )
    assert record.decision is SignalDecisionV2.NO_TRADE
    assert record.entry_reference_price is None
    with pytest.raises(SignalRejectedError, match="NO_TRADE confidence"):
        journal.submit(
            "key-10",
            submission(
                packet.packet_id,
                decision=SignalDecisionV2.NO_TRADE,
                stop_loss=None,
                take_profit=None,
            ),
        )


def test_live_execution_mode_is_structurally_impossible(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    with pytest.raises(SignalRejectedError, match="live execution does not exist"):
        journal.submit(
            "key-11",
            submission(packet.packet_id, execution_mode="live"),
        )
    with pytest.raises(SignalRejectedError, match="policy_id"):
        journal.submit(
            "key-12",
            submission(packet.packet_id, policy_id="unknown_policy"),
        )


def test_idempotency_conflict_is_recorded_and_refused(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    journal.submit("key-13", submission(packet.packet_id))
    with pytest.raises(SignalRejectedError, match="different signal content"):
        journal.submit(
            "key-13", submission(packet.packet_id, confidence=88)
        )
    reasons = [r.rejection_reason for r in journal.list_rejections()]
    assert any("different signal content" in reason for reason in reasons)


def test_paginated_listing_and_parent_h4_grouping(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    ids = [
        journal.submit(f"key-l{i}", submission(packet.packet_id)).signal_id
        if i == 0
        else journal.submit(
            f"key-l{i}",
            submission(packet.packet_id, confidence=50 + i),
        ).signal_id
        for i in range(5)
    ]
    assert journal.count() == 5
    page_one = journal.list(limit=2, offset=0)
    page_two = journal.list(limit=2, offset=2)
    page_three = journal.list(limit=2, offset=4)
    paged = [r.signal_id for r in (*page_one, *page_two, *page_three)]
    assert sorted(paged) == sorted(ids)
    by_parent = journal.list(
        parent_h4_raw_open_epoch=DEVELOPING_RAW_OPEN, limit=10
    )
    assert len(by_parent) == 5
    assert journal.list(parent_h4_raw_open_epoch=DEVELOPING_RAW_OPEN + 14_400) == []


def test_lifecycle_transitions_preserve_immutability(
    store: MarketPacketStore, journal: SignalJournalV2
) -> None:
    packet = stored_packet(store)
    record = journal.submit("key-14", submission(packet.packet_id))

    entered = journal.mark_entered(record.signal_id, entered_at_utc=NOW + timedelta(minutes=3))
    assert entered.status is SignalStatusV2.ENTERED
    assert entered.content_hash == record.content_hash
    with pytest.raises(RuntimeError, match="cannot be cancelled"):
        journal.cancel_before_entry(record.signal_id, "too late")

    other = journal.submit(
        "key-15", submission(packet.packet_id, confidence=61)
    )
    cancelled = journal.cancel_before_entry(other.signal_id, "packet went stale")
    assert cancelled.status is SignalStatusV2.CANCELLED
    assert cancelled.content_hash == other.content_hash
    with pytest.raises(RuntimeError, match="Cancelled signals cannot enter"):
        journal.mark_entered(other.signal_id)
