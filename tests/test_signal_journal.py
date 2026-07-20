from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from codexbridge.trading.signal_journal import (
    SignalDecision,
    SignalDraft,
    SignalJournal,
    SignalStatus,
    canonical_signal_bytes,
    signal_content_hash,
    validate_signal_draft,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 20, 16, 0, tzinfo=UTC)
PACKET_HASH = "a" * 64
PACKET_ID = f"mp_{PACKET_HASH[:24]}"


def draft(decision: SignalDecision = SignalDecision.LONG) -> SignalDraft:
    common = dict(
        created_at_utc=NOW,
        broker="alpari",
        symbol="BITCOIN_i",
        analysis_timeframe="4H",
        bid=64_000.0,
        ask=64_064.0,
        market_data_timestamp=NOW - timedelta(seconds=10),
        latest_completed_4h_candle="2026-07-20T08:00:00Z",
        developing_4h_candle="2026-07-20T12:00:00Z",
        entry_type="MARKET",
        reason="Trend continuation with defined invalidation.",
        news_context="No material scheduled event in the next hour.",
        market_snapshot_id=PACKET_ID,
        market_packet_hash=PACKET_HASH,
    )
    if decision is SignalDecision.LONG:
        return SignalDraft(
            decision=decision,
            confidence=73,
            entry_reference_price=64_064.0,
            stop_loss=63_500.0,
            take_profit=65_192.0,
            **common,
        )
    if decision is SignalDecision.SHORT:
        return SignalDraft(
            decision=decision,
            confidence=73,
            entry_reference_price=64_000.0,
            stop_loss=64_500.0,
            take_profit=63_000.0,
            **common,
        )
    return SignalDraft(
        decision=decision,
        confidence=None,
        entry_reference_price=None,
        stop_loss=None,
        take_profit=None,
        **common,
    )


def test_exact_signal_contract_calculates_spread_and_risk_reward() -> None:
    long, spread, long_rr = validate_signal_draft(draft())
    short, short_spread, short_rr = validate_signal_draft(draft(SignalDecision.SHORT))
    no_trade, no_trade_spread, no_trade_rr = validate_signal_draft(
        draft(SignalDecision.NO_TRADE)
    )

    assert long.entry_reference_price == long.ask
    assert short.entry_reference_price == short.bid
    assert spread == short_spread == no_trade_spread == 64.0
    assert long_rr == pytest.approx(2.0)
    assert short_rr == pytest.approx(2.0)
    assert no_trade_rr is None
    assert no_trade.confidence is None


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (replace(draft(), entry_reference_price=64_000.0), "captured ask"),
        (replace(draft(), stop_loss=64_100.0), "LONG requires"),
        (replace(draft(SignalDecision.SHORT), entry_reference_price=64_064.0), "captured bid"),
        (replace(draft(SignalDecision.SHORT), take_profit=64_100.0), "SHORT requires"),
        (replace(draft(), confidence=49), "50 through 99"),
        (replace(draft(), confidence=73.5), "integer"),
        (replace(draft(SignalDecision.NO_TRADE), confidence=50), "must be null"),
        (replace(draft(SignalDecision.NO_TRADE), stop_loss=1.0), "must not contain"),
        (replace(draft(), market_snapshot_id="mp_wrong"), "does not match"),
        (replace(draft(), market_packet_hash="bad"), "64-character"),
        (replace(draft(), created_at_utc=NOW.replace(tzinfo=None)), "timezone-aware"),
    ],
)
def test_signal_contract_rejects_invalid_or_unbound_payloads(
    candidate: SignalDraft, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_signal_draft(candidate)


def test_signal_payload_is_immutable_and_hash_deterministic() -> None:
    first, _, _ = validate_signal_draft(draft())
    second, _, _ = validate_signal_draft(draft())

    assert canonical_signal_bytes(first) == canonical_signal_bytes(second)
    assert signal_content_hash(first) == signal_content_hash(second)
    assert signal_content_hash(replace(first, reason="Different")) != signal_content_hash(first)
    with pytest.raises(FrozenInstanceError):
        first.reason = "edited"  # type: ignore[misc]


def test_submission_is_durable_idempotent_and_append_only(tmp_path) -> None:
    db_path = tmp_path / "trading.sqlite3"
    journal = SignalJournal(db_path)
    first = journal.submit("signal-20260720-1600", draft(), inserted_at_utc=NOW)
    replay = journal.submit("signal-20260720-1600", draft(), inserted_at_utc=NOW)

    assert first == replay
    assert first.status is SignalStatus.SUBMITTED
    assert first.signal_id.startswith("sig_")
    assert first.content_hash == signal_content_hash(first.draft)
    assert first.draft.market_packet_hash == PACKET_HASH
    assert [event["event_type"] for event in journal.events(first.signal_id)] == [
        "signal_submitted"
    ]

    reopened = SignalJournal(db_path)
    assert reopened.get(first.signal_id) == first
    assert reopened.list() == [first]

    with pytest.raises(ValueError, match="different signal content"):
        reopened.submit(
            "signal-20260720-1600",
            replace(draft(), reason="Conflicting replay"),
            inserted_at_utc=NOW,
        )
    assert len(reopened.events(first.signal_id)) == 1


def test_cancel_before_entry_is_idempotent_without_editing_payload(tmp_path) -> None:
    journal = SignalJournal(tmp_path / "trading.sqlite3")
    submitted = journal.submit("cancel-me", draft(), inserted_at_utc=NOW)
    cancelled = journal.cancel_before_entry(
        submitted.signal_id,
        "Analyst identified a mistaken premise.",
        cancelled_at_utc=NOW + timedelta(minutes=1),
    )
    replay = journal.cancel_before_entry(
        submitted.signal_id,
        "A different replay reason cannot rewrite history.",
        cancelled_at_utc=NOW + timedelta(minutes=2),
    )

    assert cancelled == replay
    assert cancelled.status is SignalStatus.CANCELLED
    assert cancelled.draft == submitted.draft
    assert cancelled.content_hash == submitted.content_hash
    assert cancelled.cancellation_reason == "Analyst identified a mistaken premise."
    assert [event["event_type"] for event in journal.events(submitted.signal_id)] == [
        "signal_submitted",
        "signal_cancelled_before_entry",
    ]
    with pytest.raises(RuntimeError, match="Cancelled signals cannot enter"):
        journal.mark_entered(submitted.signal_id, entered_at_utc=NOW + timedelta(minutes=3))


def test_entered_signal_cannot_be_cancelled_and_no_trade_cannot_enter(tmp_path) -> None:
    journal = SignalJournal(tmp_path / "trading.sqlite3")
    submitted = journal.submit("entered", draft(), inserted_at_utc=NOW)
    entered = journal.mark_entered(
        submitted.signal_id, entered_at_utc=NOW + timedelta(seconds=30)
    )
    replay = journal.mark_entered(
        submitted.signal_id, entered_at_utc=NOW + timedelta(minutes=1)
    )

    assert entered == replay
    assert entered.status is SignalStatus.ENTERED
    assert entered.draft == submitted.draft
    assert [event["event_type"] for event in journal.events(submitted.signal_id)] == [
        "signal_submitted",
        "signal_entered",
    ]
    with pytest.raises(RuntimeError, match="Entered signals cannot be cancelled"):
        journal.cancel_before_entry(submitted.signal_id, "Too late")

    no_trade = journal.submit(
        "no-trade", draft(SignalDecision.NO_TRADE), inserted_at_utc=NOW
    )
    with pytest.raises(RuntimeError, match="NO_TRADE signals cannot enter"):
        journal.mark_entered(no_trade.signal_id)
