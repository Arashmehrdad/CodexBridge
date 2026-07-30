"""V3-1A-FOUNDATION-1: shared contracts and additive persistence.

These tests cover the persistence boundary only. No provider process is
launched, no adapter exists yet, and no public gateway is involved. Every case
that matters is a durability or authority claim about what the schema and the
store refuse to do.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    TaskLinkTargetKind,
    TaskLinkType,
    TaskState,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore
from soma.worker_substrate import (
    CheckpointDeadlinePolicy,
    CheckpointExpiryDisposition,
    InteractionConflict,
    InteractionDelivery,
    InteractionKind,
    ProviderChildRole,
    SessionBindingConflict,
    SessionBindingDisposition,
    WORKER_SUBSTRATE_SCHEMA_VERSION,
    WORKER_SUBSTRATE_TABLE_NAMES,
    WorkerSubstrateStore,
    usage_dedupe_key,
)
from soma.worker_substrate import store as substrate_store_module


PROJECT_ID = "proj_11111111-1111-1111-1111-111111111111"
RESOURCE_ID = "res_22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _make_task(task_store: TaskStore, *, controller_request_id: str) -> str:
    task_id = make_task_id()
    normalized = normalize_durable_command_request(
        repo_name="soma", profile_id="pytest", argv=["python", "-m", "pytest", "-q"]
    )
    task_store.reserve_task(
        task_id=task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id=controller_request_id,
        request_hash=normalized_request_hash(normalized),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref="",
        backend_identity={},
    )
    return task_id


@pytest.fixture()
def substrate(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    store = WorkerSubstrateStore(runs_dir)
    task_id = _make_task(task_store, controller_request_id="req-primary")
    return store, task_store, task_id


def _bind(store: WorkerSubstrateStore, task_id: str, **overrides):
    payload = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": task_id,
        "run_id": "20260730T101010Z_worker_aabbccdd",
        "provider": "claude_code",
        "native_session_id": "91F5d23f-AAAA-4bbb-8ccc-DDDDDDDDDDDD",
        "adapter_id": "soma.adapter.claude_code",
        "adapter_version": "0.1.0",
        "protocol_id": "claude_code.stream_json",
        "protocol_version": "1",
    }
    payload.update(overrides)
    return store.bind_provider_session(**payload)


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def test_migration_creates_every_substrate_table(substrate):
    store, _task_store, _task_id = substrate
    state = store.schema_state()
    assert state["schema_version"] == WORKER_SUBSTRATE_SCHEMA_VERSION
    assert state["up_to_date"] is True
    assert state["missing_tables"] == []
    assert sorted(state["tables"]) == sorted(WORKER_SUBSTRATE_TABLE_NAMES)


def test_migration_is_idempotent(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    first = WorkerSubstrateStore(runs_dir)
    assert first.schema_version() == WORKER_SUBSTRATE_SCHEMA_VERSION
    second = WorkerSubstrateStore(runs_dir)
    assert second.schema_version() == WORKER_SUBSTRATE_SCHEMA_VERSION
    with second._read() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM soma_schema_migrations WHERE component = ?",
            ("interactive_worker_substrate",),
        ).fetchone()
    assert int(rows[0]) == 1


# ---------------------------------------------------------------------------
# provider-session binding
# ---------------------------------------------------------------------------


def test_binding_creates_then_replays_idempotently(substrate):
    store, _task_store, task_id = substrate
    binding, created = _bind(store, task_id)
    assert created is True
    assert binding.disposition is SessionBindingDisposition.BOUND

    replay, created_again = _bind(store, task_id)
    assert created_again is False
    assert replay.session_binding_id == binding.session_binding_id


def test_binding_rejects_a_different_native_session_for_the_same_run(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    with pytest.raises(SessionBindingConflict) as excinfo:
        _bind(store, task_id, native_session_id="a-completely-different-session")
    assert excinfo.value.existing.session_binding_id == binding.session_binding_id
    # The original binding is untouched: a conflict never rebinds.
    assert store.find_binding_by_run(binding.run_id).native_session_id == (
        binding.native_session_id
    )


def test_binding_rejects_a_different_adapter_or_protocol_identity(substrate):
    store, _task_store, task_id = substrate
    _bind(store, task_id)
    with pytest.raises(SessionBindingConflict):
        _bind(store, task_id, adapter_id="soma.adapter.codex")
    with pytest.raises(SessionBindingConflict):
        _bind(store, task_id, protocol_id="codex.exec_json")


def test_one_native_session_cannot_be_claimed_by_two_runs(substrate):
    store, task_store, task_id = substrate
    _bind(store, task_id)
    other_task = _make_task(task_store, controller_request_id="req-second")
    with pytest.raises(sqlite3.IntegrityError):
        _bind(
            store,
            other_task,
            run_id="20260730T111111Z_worker_11223344",
        )


def test_provider_identifiers_preserve_exact_casing(substrate):
    store, _task_store, task_id = substrate
    mixed = "91F5d23f-AAAA-4bbb-8ccc-DDDDDDDDDDDD"
    binding, _ = _bind(store, task_id, native_session_id=mixed)
    reloaded = store.get_binding(binding.session_binding_id)
    assert reloaded.native_session_id == mixed

    # A case-folded lookup must not match: the column is explicitly BINARY.
    with store._read() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM worker_provider_sessions WHERE native_session_id = ?",
            (mixed.lower(),),
        ).fetchone()
    assert int(row[0]) == 0


def test_mismatch_disposition_is_recordable_without_a_lifecycle(substrate):
    store, task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    updated = store.set_binding_disposition(
        binding.session_binding_id,
        disposition=SessionBindingDisposition.MISMATCH_DETECTED,
        reason="resume returned a different session_id",
    )
    assert updated.disposition is SessionBindingDisposition.MISMATCH_DETECTED
    assert "different session_id" in updated.disposition_reason
    # The canonical task is unchanged: a binding disposition is not task state.
    assert task_store.get_task(task_id).state is TaskState.ACCEPTED

    # Dispositions are evidence quality, not progress, so they may move back.
    back = store.set_binding_disposition(
        binding.session_binding_id,
        disposition=SessionBindingDisposition.UNVERIFIED,
        reason="provider unreachable",
    )
    assert back.disposition is SessionBindingDisposition.UNVERIFIED


# ---------------------------------------------------------------------------
# interaction delivery
# ---------------------------------------------------------------------------


def test_interaction_commits_before_delivery_and_replays_identically(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    record, created = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.STEER,
        idempotency_key="steer-1",
        payload="stop counting and write STEER.txt",
    )
    assert created is True
    assert record.delivery is InteractionDelivery.PENDING
    assert record.delivered_at is None

    replay, created_again = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.STEER,
        idempotency_key="steer-1",
        payload="stop counting and write STEER.txt",
    )
    assert created_again is False
    assert replay.interaction_id == record.interaction_id
    assert len(store.list_interactions(task_id=task_id)) == 1


def test_same_identity_with_changed_content_is_a_durable_conflict(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    original, _ = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.SUPPLY_INPUT,
        idempotency_key="input-1",
        payload="approve",
    )
    with pytest.raises(InteractionConflict) as excinfo:
        store.commit_interaction(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            interaction_kind=InteractionKind.SUPPLY_INPUT,
            idempotency_key="input-1",
            payload="reject",
        )
    assert excinfo.value.existing.interaction_id == original.interaction_id
    # The committed intent is preserved exactly; the conflicting one is not stored.
    assert store.read_payload(original.payload_ref) == b"approve"
    assert len(store.list_interactions(task_id=task_id)) == 1


def test_payload_is_referenced_and_hashed_not_inlined(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    secret = "api-key=sk-live-should-never-reach-a-command-line"
    record, _ = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.SUPPLY_INPUT,
        idempotency_key="secret-1",
        payload=secret,
    )
    assert record.payload_ref.startswith("worker_payload:")
    assert record.payload_bytes == len(secret.encode("utf-8"))
    assert store.read_payload(record.payload_ref).decode("utf-8") == secret

    # No column of the row carries the content itself.
    with store._read() as conn:
        row = conn.execute(
            "SELECT * FROM worker_interactions WHERE interaction_id = ?",
            (record.interaction_id,),
        ).fetchone()
    assert all(secret not in str(value) for value in dict(row).values())


def test_uncertain_send_window_is_representable(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    record, _ = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.STEER,
        idempotency_key="steer-uncertain",
        payload="steer",
    )
    uncertain = store.record_delivery(
        record.interaction_id,
        delivery=InteractionDelivery.UNCERTAIN,
        reason="crash after write, no acknowledgement observed",
    )
    assert uncertain.delivery is InteractionDelivery.UNCERTAIN
    # Uncertainty is not a delivery: it must not stamp a delivery time.
    assert uncertain.delivered_at is None
    assert store.get_interaction(record.interaction_id).delivery is (
        InteractionDelivery.UNCERTAIN
    )


def test_late_acknowledgement_cannot_override_a_cancelled_task(substrate):
    store, task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    record, _ = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.STEER,
        idempotency_key="steer-late",
        payload="steer",
    )
    task = task_store.get_task(task_id)
    task_store.conditional_update(
        task_id,
        fields={"state": TaskState.CANCELLED.value},
        expected_state_version=task.state_version,
    )

    acknowledged = store.record_delivery(
        record.interaction_id,
        delivery=InteractionDelivery.ACKNOWLEDGED,
        reason="provider acked",
    )
    assert acknowledged.delivery is InteractionDelivery.REJECTED
    assert "task_terminal:cancelled" in acknowledged.delivery_reason
    # The refusal is a persistence-boundary decision; the task is not rewritten.
    assert task_store.get_task(task_id).state is TaskState.CANCELLED


def test_late_acknowledgement_cannot_override_a_superseded_task(substrate):
    store, task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    record, _ = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.SUPPLY_INPUT,
        idempotency_key="input-superseded",
        payload="value",
    )
    successor = _make_task(task_store, controller_request_id="req-successor")
    task_store.add_link(
        successor,
        link_type=TaskLinkType.SUPERSEDES,
        target_kind=TaskLinkTargetKind.TASK,
        target_id=task_id,
    )

    acknowledged = store.record_delivery(
        record.interaction_id, delivery=InteractionDelivery.ACKNOWLEDGED
    )
    assert acknowledged.delivery is InteractionDelivery.REJECTED
    assert acknowledged.delivery_reason == "task_superseded"


def test_acknowledgement_succeeds_while_the_task_is_live(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    record, _ = store.commit_interaction(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        interaction_kind=InteractionKind.STEER,
        idempotency_key="steer-live",
        payload="steer",
    )
    acknowledged = store.record_delivery(
        record.interaction_id,
        delivery=InteractionDelivery.ACKNOWLEDGED,
        evidence_ref="run_event:1234",
    )
    assert acknowledged.delivery is InteractionDelivery.ACKNOWLEDGED
    assert acknowledged.delivered_at is not None
    assert acknowledged.delivery_evidence_ref == "run_event:1234"


# ---------------------------------------------------------------------------
# checkpoint deadlines and expiry evidence
# ---------------------------------------------------------------------------


def test_checkpoint_deadline_survives_store_reopen(substrate, tmp_path: Path):
    store, task_store, task_id = substrate
    checkpoint = task_store.create_checkpoint(
        task_id, kind="controller_input", required_state_version=0, prompt="approve?"
    )
    store.set_checkpoint_deadline(
        checkpoint_id=checkpoint.checkpoint_id,
        task_id=task_id,
        deadline_policy=CheckpointDeadlinePolicy.BOUNDED,
        deadline_at="2026-07-30T12:00:00+00:00",
    )

    reopened = WorkerSubstrateStore(store.runs_dir)
    deadline = reopened.get_checkpoint_deadline(checkpoint.checkpoint_id)
    assert deadline is not None
    assert deadline.deadline_at == "2026-07-30T12:00:00+00:00"
    assert deadline.deadline_policy is CheckpointDeadlinePolicy.BOUNDED

    # The existing checkpoint record is unchanged by attaching a deadline.
    assert task_store.open_checkpoint_count(task_id) == 1
    with task_store._read() as conn:
        row = conn.execute(
            "SELECT * FROM task_checkpoints WHERE checkpoint_id = ?",
            (checkpoint.checkpoint_id,),
        ).fetchone()
    assert dict(row)["prompt"] == "approve?"
    assert "deadline" not in dict(row)


def test_unbounded_deadline_requires_a_named_policy_owner(substrate):
    store, task_store, task_id = substrate
    checkpoint = task_store.create_checkpoint(
        task_id, kind="controller_input", required_state_version=0
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.set_checkpoint_deadline(
            checkpoint_id=checkpoint.checkpoint_id,
            task_id=task_id,
            deadline_policy=CheckpointDeadlinePolicy.EXPLICIT_NONE,
        )
    accepted = store.set_checkpoint_deadline(
        checkpoint_id=checkpoint.checkpoint_id,
        task_id=task_id,
        deadline_policy=CheckpointDeadlinePolicy.EXPLICIT_NONE,
        policy_owner="owner:arash",
    )
    assert accepted.policy_owner == "owner:arash"


def test_expiry_evidence_is_idempotent(substrate):
    store, task_store, task_id = substrate
    checkpoint = task_store.create_checkpoint(
        task_id, kind="controller_input", required_state_version=0
    )
    store.set_checkpoint_deadline(
        checkpoint_id=checkpoint.checkpoint_id,
        task_id=task_id,
        deadline_policy=CheckpointDeadlinePolicy.BOUNDED,
        deadline_at="2026-07-30T12:00:00+00:00",
    )
    first, created = store.record_checkpoint_expiry(
        checkpoint_id=checkpoint.checkpoint_id,
        task_id=task_id,
        idempotency_key="expiry-1",
        deadline_at="2026-07-30T12:00:00+00:00",
        observed_at="2026-07-30T12:00:05+00:00",
        disposition=CheckpointExpiryDisposition.RECORDED,
    )
    assert created is True
    replay, created_again = store.record_checkpoint_expiry(
        checkpoint_id=checkpoint.checkpoint_id,
        task_id=task_id,
        idempotency_key="expiry-1",
        deadline_at="2026-07-30T12:00:00+00:00",
        observed_at="2026-07-30T12:09:99+00:00",
        disposition=CheckpointExpiryDisposition.UNCERTAIN,
    )
    assert created_again is False
    # The first evidence is immutable: a replay never rewrites the disposition.
    assert replay.expiry_id == first.expiry_id
    assert replay.disposition is CheckpointExpiryDisposition.RECORDED
    assert len(store.list_checkpoint_expiries(checkpoint.checkpoint_id)) == 1


def test_release_disposition_requires_a_quiescence_proof(substrate):
    store, task_store, task_id = substrate
    checkpoint = task_store.create_checkpoint(
        task_id, kind="controller_input", required_state_version=0
    )
    with pytest.raises(ValueError, match="quiescence_proof_ref"):
        store.record_checkpoint_expiry(
            checkpoint_id=checkpoint.checkpoint_id,
            task_id=task_id,
            idempotency_key="expiry-release",
            deadline_at="2026-07-30T12:00:00+00:00",
            observed_at="2026-07-30T12:00:05+00:00",
            disposition=CheckpointExpiryDisposition.QUIESCENT_CONFIRMED,
        )
    proven, created = store.record_checkpoint_expiry(
        checkpoint_id=checkpoint.checkpoint_id,
        task_id=task_id,
        idempotency_key="expiry-release",
        deadline_at="2026-07-30T12:00:00+00:00",
        observed_at="2026-07-30T12:00:05+00:00",
        disposition=CheckpointExpiryDisposition.QUIESCENT_CONFIRMED,
        quiescence_proof_ref="descendant_sweep:0_alive",
    )
    assert created is True
    assert proven.quiescence_proof_ref == "descendant_sweep:0_alive"


def test_release_disposition_is_refused_at_the_schema_too(substrate):
    """The store guard is not the only guard; SQL alone cannot bypass the rule."""
    store, task_store, task_id = substrate
    checkpoint = task_store.create_checkpoint(
        task_id, kind="controller_input", required_state_version=0
    )
    with pytest.raises(sqlite3.IntegrityError):
        with store._transaction() as conn:
            conn.execute(
                "INSERT INTO worker_checkpoint_expiries "
                "(expiry_id, checkpoint_id, task_id, idempotency_key, deadline_at, "
                " observed_at, disposition, quiescence_proof_ref, reason, "
                " evidence_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'quiescent_confirmed', '', '', ?, ?)",
                (
                    "wexp_bypass",
                    checkpoint.checkpoint_id,
                    task_id,
                    "bypass",
                    "2026-07-30T12:00:00+00:00",
                    "2026-07-30T12:00:05+00:00",
                    "0" * 64,
                    "2026-07-30T12:00:05+00:00",
                ),
            )


# ---------------------------------------------------------------------------
# raw usage
# ---------------------------------------------------------------------------


CLAUDE_RESULT_EVENT = {
    "type": "result",
    "subtype": "success",
    "session_id": "91F5d23f-AAAA-4bbb-8ccc-DDDDDDDDDDDD",
    "total_cost_usd": 0.1094,
    "num_turns": 3,
}

CODEX_TURN_EVENT = {
    "type": "turn.completed",
    "usage": {"input_tokens": 1200, "cached_input_tokens": 800, "output_tokens": 340},
}


def test_replayed_usage_events_are_deduplicated(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    kwargs = dict(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        provider=binding.provider,
        native_session_id=binding.native_session_id,
        event_kind="result",
        sequence=1,
        raw_event=CLAUDE_RESULT_EVENT,
        provider_reported_cost_usd="0.1094",
    )
    _first, created = store.record_usage_event(**kwargs)
    assert created is True
    # Resume replays the identical event.
    _replay, created_again = store.record_usage_event(**kwargs)
    assert created_again is False
    assert len(store.list_usage_events(session_binding_id=binding.session_binding_id)) == 1


def test_raw_units_and_optional_cost_are_preserved_separately(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)

    claude, _ = store.record_usage_event(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        provider="claude_code",
        native_session_id=binding.native_session_id,
        event_kind="result",
        sequence=1,
        raw_event=CLAUDE_RESULT_EVENT,
        provider_reported_cost_usd="0.1094",
    )
    codex, _ = store.record_usage_event(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        provider="codex",
        native_session_id=binding.native_session_id,
        event_kind="turn.completed",
        sequence=2,
        raw_event=CODEX_TURN_EVENT,
        input_tokens=1200,
        cached_input_tokens=800,
        output_tokens=340,
    )

    # Claude reports money and no token breakdown; Codex the reverse. Neither
    # gap is filled in, and the raw event survives byte-for-byte in meaning.
    assert claude.provider_reported_cost_usd == "0.1094"
    assert claude.input_tokens is None
    assert claude.raw_event == CLAUDE_RESULT_EVENT
    assert codex.provider_reported_cost_usd is None
    assert codex.input_tokens == 1200
    assert codex.raw_event == CODEX_TURN_EVENT


def test_aggregation_reports_missing_figures_rather_than_zeros(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    store.record_usage_event(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        provider="claude_code",
        native_session_id=binding.native_session_id,
        event_kind="result",
        sequence=1,
        raw_event=CLAUDE_RESULT_EVENT,
        provider_reported_cost_usd="0.1094",
    )
    store.record_usage_event(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        provider="codex",
        native_session_id=binding.native_session_id,
        event_kind="turn.completed",
        sequence=2,
        raw_event=CODEX_TURN_EVENT,
        input_tokens=1200,
        output_tokens=340,
    )

    by_task = store.aggregate_usage(task_id=task_id)
    assert by_task["event_count"] == 2
    assert by_task["input_tokens"] == 1200
    assert by_task["input_tokens_missing_events"] == 1
    assert by_task["provider_reported_cost_usd"] == "0.1094"
    assert by_task["provider_reported_cost_missing_events"] == 1
    # A figure no event reported stays None, never a misleading 0.
    assert by_task["total_tokens"] is None

    assert store.aggregate_usage(run_id=binding.run_id)["event_count"] == 2
    assert (
        store.aggregate_usage(session_binding_id=binding.session_binding_id)[
            "event_count"
        ]
        == 2
    )


def test_dedupe_key_is_stable_and_content_sensitive():
    base = dict(
        provider="codex",
        native_session_id="019fa061",
        provider_event_id="",
        sequence=4,
        raw_event_hash="a" * 64,
    )
    assert usage_dedupe_key(**base) == usage_dedupe_key(**base)
    assert usage_dedupe_key(**{**base, "sequence": 5}) != usage_dedupe_key(**base)
    assert usage_dedupe_key(**{**base, "raw_event_hash": "b" * 64}) != usage_dedupe_key(
        **base
    )


# ---------------------------------------------------------------------------
# provider-child identity
# ---------------------------------------------------------------------------


def test_child_pid_and_start_identity_persist_and_compare(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    root, created = store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=15436,
        process_start_identity="15436:windows:133671234567890000",
        image_name="claude.exe",
        observation_source="launch",
    )
    assert created is True
    assert root.pid == 15436

    _replay, created_again = store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=15436,
        process_start_identity="15436:windows:133671234567890000",
    )
    assert created_again is False

    # A reused PID with a different start identity is a different process and
    # must be recordable as such rather than colliding with the original.
    reused, created_reused = store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        role=ProviderChildRole.OWNED_DESCENDANT,
        pid=15436,
        process_start_identity="15436:windows:133679999999999999",
    )
    assert created_reused is True
    assert reused.record_id != root.record_id
    assert reused.process_start_identity != root.process_start_identity
    assert len(store.list_child_processes(binding.session_binding_id)) == 2


def test_child_record_requires_a_start_identity(substrate):
    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    with pytest.raises(ValueError):
        store.record_child_process(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=binding.run_id,
            role=ProviderChildRole.PROVIDER_ROOT,
            pid=15436,
            process_start_identity="",
        )


def test_start_identity_matches_the_process_control_format(substrate):
    """The recorded identity is the value process_control already produces."""
    import os

    from soma.process_control import process_identity

    store, _task_store, task_id = substrate
    binding, _ = _bind(store, task_id)
    identity = process_identity(os.getpid())
    if not identity:
        pytest.skip("process start identity unavailable on this platform")
    record, _ = store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=binding.run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=os.getpid(),
        process_start_identity=identity,
    )
    assert record.process_start_identity == identity
    assert identity.startswith(f"{os.getpid()}:")


# ---------------------------------------------------------------------------
# migration safety on a populated store
# ---------------------------------------------------------------------------


def _snapshot(db_path: Path, table: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return sorted(conn.execute(f"SELECT * FROM {table}").fetchall())
    finally:
        conn.close()


def test_migration_on_a_populated_store_preserves_incumbent_identities(tmp_path: Path):
    source = tmp_path / "populated"
    task_store = TaskStore(source)
    run_store = RunStore(source)
    run_store.create_run(
        run_id="20260730T090000Z_worker_deadbeef",
        repo_name="soma",
        tool="executable_profile",
        run_dir=source / "20260730T090000Z_worker_deadbeef",
        input_data={"profile_id": "pytest"},
    )
    task_id = _make_task(task_store, controller_request_id="req-populated")
    task_store.create_checkpoint(
        task_id, kind="controller_input", required_state_version=0
    )

    # Work on a disposable copy so the populated store itself is never at risk.
    target = tmp_path / "disposable"
    shutil.copytree(source, target)
    db = target / "soma.sqlite3"
    before = {name: _snapshot(db, name) for name in ("tasks", "runs", "task_checkpoints")}

    WorkerSubstrateStore(target)

    after = {name: _snapshot(db, name) for name in ("tasks", "runs", "task_checkpoints")}
    assert after == before

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        present = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        # Every substrate table is new and empty; nothing was backfilled.
        for name in WORKER_SUBSTRATE_TABLE_NAMES:
            assert name in present
            assert int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) == 0
    finally:
        conn.close()


def test_migration_does_not_alter_existing_table_definitions(tmp_path: Path):
    source = tmp_path / "runs"
    TaskStore(source)
    RunStore(source)
    db = source / "soma.sqlite3"

    def definitions() -> dict[str, str]:
        conn = sqlite3.connect(db)
        try:
            return {
                str(row[0]): str(row[1])
                for row in conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            conn.close()

    before = definitions()
    WorkerSubstrateStore(source)
    after = definitions()

    for name, sql in before.items():
        assert after[name] == sql, f"existing table {name} was redefined"
    assert set(after) - set(before) == set(WORKER_SUBSTRATE_TABLE_NAMES)


# ---------------------------------------------------------------------------
# authority audit
# ---------------------------------------------------------------------------


# Columns whose presence would mean this package had taken over a canonical
# responsibility. Each name is owned today by TaskStore or RunStore.
_FORBIDDEN_COLUMNS = frozenset(
    {
        "worker_lease_token",
        "lease_generation",
        "worker_identity",
        "cancellation_requested_at",
        "exit_code",
        "result_json",
        "result_ref",
        "result_hash",
        "result_publication_status",
        "result_published_hash",
        "public_result_json",
        "recovery_state",
        "state_version",
        "controller_request_id",
        "request_hash",
        "backend_kind",
        "backend_ref",
        "phase",
        "state",
        "status",
    }
)


def test_no_substrate_table_owns_a_canonical_lifecycle_column(substrate):
    store, _task_store, _task_id = substrate
    with store._read() as conn:
        for table in WORKER_SUBSTRATE_TABLE_NAMES:
            columns = {
                str(row["name"])
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            overlap = columns & _FORBIDDEN_COLUMNS
            assert not overlap, f"{table} claims canonical columns {sorted(overlap)}"


def test_no_substrate_disposition_reuses_the_task_state_vocabulary(substrate):
    """A disposition must never be projectable as canonical task state."""
    store, _task_store, _task_id = substrate
    task_states = {state.value for state in TaskState}
    with store._read() as conn:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name IN "
            "(" + ", ".join("?" for _ in WORKER_SUBSTRATE_TABLE_NAMES) + ")",
            WORKER_SUBSTRATE_TABLE_NAMES,
        ).fetchall()
    for name, sql in rows:
        literals = set(re.findall(r"'([a-z_]+)'", str(sql)))
        shared = literals & task_states
        # 'uncertain' is required by the interaction-delivery contract and is
        # the single permitted overlap; anything more would be a second
        # lifecycle vocabulary wearing a different column name.
        assert shared <= {"uncertain"}, f"{name} reuses task states {sorted(shared)}"


def test_substrate_store_writes_only_to_substrate_tables():
    source = Path(substrate_store_module.__file__).read_text(encoding="utf-8")
    targets = {
        match.lower()
        for match in re.findall(
            r"(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)",
            source,
            re.IGNORECASE,
        )
    }
    assert targets <= set(WORKER_SUBSTRATE_TABLE_NAMES), (
        f"substrate store writes outside its own tables: "
        f"{sorted(targets - set(WORKER_SUBSTRATE_TABLE_NAMES))}"
    )


def test_substrate_reads_tasks_only_for_the_terminal_guard():
    source = Path(substrate_store_module.__file__).read_text(encoding="utf-8")
    # Case-sensitive: SQL in this module is uppercase, Python imports are not,
    # so a lowercase ``from x import y`` is not mistaken for a table read.
    read_targets = {match.lower() for match in re.findall(r"\bFROM\s+(\w+)", source)}
    allowed = set(WORKER_SUBSTRATE_TABLE_NAMES) | {"tasks", "task_links"}
    assert read_targets <= allowed, (
        f"substrate store reads unexpected tables: {sorted(read_targets - allowed)}"
    )


def test_substrate_adds_no_task_plane_enum_values():
    """This package launches nothing, so it publishes no new execution contract."""
    from soma.tasks.models import BackendKind as Backends
    from soma.tasks.models import TaskCommandKind, TaskKind as Kinds

    assert [kind.value for kind in Kinds] == ["durable_command"]
    assert [kind.value for kind in Backends] == ["soma_durable_run"]
    assert [kind.value for kind in TaskCommandKind] == ["cancel"]


def test_existing_durable_command_request_hash_is_unchanged():
    """A published request hash is a compatibility surface, not an internal value."""
    normalized = normalize_durable_command_request(
        repo_name="soma", profile_id="pytest", argv=["python", "-m", "pytest", "-q"]
    )
    assert normalized_request_hash(normalized) == (
        "279df8af186f2151045dab87252516456f17f922a6ca548cdc62214fb8249b1b"
    )
