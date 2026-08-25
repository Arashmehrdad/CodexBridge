from __future__ import annotations

import threading
from pathlib import Path

import pytest

from soma.continuations import (
    ContinuationClosed,
    ContinuationLifecycle,
    ContinuationRequestConflict,
    ContinuationStore,
    StaleContinuationContract,
)
from soma.continuations.schema import apply_continuation_migrations
from soma.run_store import RunStore


RUN_ID = "20260815T120000Z_executable_profile_abcdef12"


def _open(store: ContinuationStore, request_id: str = "open-1"):
    return store.open_continuation(
        label="C1 test",
        instruction_text="Continue the accepted implementation plan.",
        provenance_class="controller_submitted_text",
        controller_request_id=request_id,
    )


def test_c1_fresh_database_creates_exact_four_continuation_tables(tmp_path: Path) -> None:
    store = ContinuationStore(tmp_path / "runs")
    state = store.schema_state()
    assert state["schema_version"] == 2
    assert state["up_to_date"] is True
    assert state["tables"] == [
        "controller_continuations",
        "continuation_contract_revisions",
        "continuation_handoffs",
        "continuation_effect_links",
    ]
    with store.connect() as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert set(state["tables"]) <= tables


def test_c1_existing_main_database_migrates_additively(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    run_store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="executable_profile",
        run_dir=runs_dir / RUN_ID,
        input_data={"before": "continuation"},
        status="completed",
    )
    before = run_store.get_run(RUN_ID)

    continuation_store = ContinuationStore(runs_dir)
    after = RunStore(runs_dir).get_run(RUN_ID)
    assert after["run_id"] == before["run_id"]
    assert after["input"] == {"before": "continuation"}
    assert continuation_store.db_path == run_store.db_path
    assert continuation_store.schema_state()["up_to_date"] is True


def test_c1_migration_replay_is_empty_and_restart_safe(tmp_path: Path) -> None:
    store = ContinuationStore(tmp_path / "runs")
    assert store.init_db() == []
    assert apply_continuation_migrations(store.connect) == []
    restarted = ContinuationStore(tmp_path / "runs")
    assert restarted.schema_version() == 2


def test_c1_activity_timestamp_migration_backfills_existing_handoff_activity(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, revision, _ = _open(store)
    handoff, _ = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text="newer durable activity",
        controller_request_id="migration-handoff",
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE controller_continuations SET updated_at = ? WHERE continuation_id = ?",
            (continuation.created_at, continuation.continuation_id),
        )
        conn.execute("DELETE FROM soma_schema_migrations WHERE version = 2")
        conn.commit()

    assert apply_continuation_migrations(store.connect) == [2]
    assert store.get_continuation(continuation.continuation_id).updated_at == handoff.created_at


def test_c1_open_continuation_and_first_revision_are_atomic_and_idempotent(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, revision, created = _open(store)
    assert created is True
    assert continuation.lifecycle == ContinuationLifecycle.OPEN
    assert continuation.current_contract_revision_id == revision.contract_revision_id
    assert revision.revision_number == 1
    assert revision.parent_revision_id is None

    replay_continuation, replay_revision, replay_created = _open(store)
    assert replay_created is False
    assert replay_continuation.continuation_id == continuation.continuation_id
    assert replay_revision.contract_revision_id == revision.contract_revision_id

    with pytest.raises(ContinuationRequestConflict):
        store.open_continuation(
            label="different",
            instruction_text="Continue the accepted implementation plan.",
            provenance_class="controller_submitted_text",
            controller_request_id="open-1",
        )
    with store.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM controller_continuations"
        ).fetchone()[0]
        revisions = conn.execute(
            "SELECT COUNT(*) FROM continuation_contract_revisions"
        ).fetchone()[0]
    assert count == 1
    assert revisions == 1


def test_c1_contract_revision_replay_conflict_and_atomic_pointer_change(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, first, _ = _open(store)
    second, created = store.append_contract_revision(
        continuation_context_ref=first.contract_revision_id,
        instruction_text="Continue C1, preserving concurrent owner work.",
        provenance_class="controller_submitted_text",
        controller_request_id="contract-2",
    )
    assert created is True
    assert second.parent_revision_id == first.contract_revision_id
    assert second.revision_number == 2
    current = store.get_continuation(continuation.continuation_id)
    assert current.current_contract_revision_id == second.contract_revision_id

    replay, replay_created = store.append_contract_revision(
        continuation_context_ref=first.contract_revision_id,
        instruction_text="Continue C1, preserving concurrent owner work.",
        provenance_class="controller_submitted_text",
        controller_request_id="contract-2",
    )
    assert replay_created is False
    assert replay.contract_revision_id == second.contract_revision_id

    with pytest.raises(ContinuationRequestConflict):
        store.append_contract_revision(
            continuation_context_ref=first.contract_revision_id,
            instruction_text="changed payload",
            provenance_class="controller_submitted_text",
            controller_request_id="contract-2",
        )
    history = store.list_contract_history(continuation.continuation_id)
    assert [item.contract_revision_id for item in history] == [
        first.contract_revision_id,
        second.contract_revision_id,
    ]


def test_c1_old_context_ref_is_stale_for_new_revision_and_checkpoint(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    _, first, _ = _open(store)
    second, _ = store.append_contract_revision(
        continuation_context_ref=first.contract_revision_id,
        instruction_text="new governing instruction",
        provenance_class="controller_submitted_text",
        controller_request_id="contract-new",
    )
    with pytest.raises(StaleContinuationContract):
        store.append_contract_revision(
            continuation_context_ref=first.contract_revision_id,
            instruction_text="stale branch update",
            provenance_class="controller_submitted_text",
            controller_request_id="contract-stale",
        )
    with pytest.raises(StaleContinuationContract):
        store.append_handoff(
            continuation_context_ref=first.contract_revision_id,
            handoff_text="stale checkpoint",
            controller_request_id="handoff-stale",
        )
    current, resolved = store.require_current_open_context(second.contract_revision_id)
    assert current.current_contract_revision_id == second.contract_revision_id
    assert resolved.contract_revision_id == second.contract_revision_id


def test_c1_concurrent_contract_updates_from_same_expected_ref_have_one_winner(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, first, _ = _open(store)
    barrier = threading.Barrier(2)
    successes = []
    stale = []
    lock = threading.Lock()

    def update(index: int) -> None:
        barrier.wait()
        try:
            revision, created = store.append_contract_revision(
                continuation_context_ref=first.contract_revision_id,
                instruction_text=f"branch {index} governing update",
                provenance_class="controller_submitted_text",
                controller_request_id=f"contract-concurrent-{index}",
            )
            with lock:
                successes.append((revision, created))
        except StaleContinuationContract as exc:
            with lock:
                stale.append(exc)

    threads = [threading.Thread(target=update, args=(index,)) for index in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert len(successes) == 1
    assert len(stale) == 1
    history = store.list_contract_history(continuation.continuation_id)
    assert len(history) == 2
    assert store.get_continuation(
        continuation.continuation_id
    ).current_contract_revision_id == successes[0][0].contract_revision_id


def test_c1_handoff_is_free_form_immutable_replayable_and_conflict_safe(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, revision, _ = _open(store)
    before_updated_at = continuation.updated_at
    text = "No headings required. Weird structure is fine.\n- unfinished: C2\n??? uncertainty"
    handoff, created = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text=text,
        controller_request_id="handoff-1",
    )
    assert created is True
    assert handoff.handoff_text == text
    assert handoff.sequence_number == 1
    assert handoff.contract_revision_id == revision.contract_revision_id
    assert store.latest_handoff(continuation.continuation_id) == handoff
    assert store.get_continuation(continuation.continuation_id).updated_at > before_updated_at

    replay, replay_created = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text=text,
        controller_request_id="handoff-1",
    )
    assert replay_created is False
    assert replay.handoff_id == handoff.handoff_id
    with pytest.raises(ContinuationRequestConflict):
        store.append_handoff(
            continuation_context_ref=revision.contract_revision_id,
            handoff_text="different text",
            controller_request_id="handoff-1",
        )


def test_c1_handoffs_are_monotonic_without_semantic_supersession(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, revision, _ = _open(store)
    first, _ = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text="branch A",
        controller_request_id="handoff-a",
    )
    second, _ = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text="branch B",
        controller_request_id="handoff-b",
    )
    assert first.sequence_number == 1
    assert second.sequence_number == 2
    assert [item.handoff_text for item in store.list_handoffs(continuation.continuation_id)] == [
        "branch A",
        "branch B",
    ]


def test_c1_close_is_idempotent_and_rejects_new_contracts_or_checkpoints(
    tmp_path: Path,
) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, revision, _ = _open(store)
    closed, changed = store.close_continuation(
        continuation_id=continuation.continuation_id,
        lifecycle="completed",
        controller_request_id="close-1",
    )
    assert changed is True
    assert closed.lifecycle == ContinuationLifecycle.COMPLETED
    assert closed.closed_at is not None

    replay, replay_changed = store.close_continuation(
        continuation_id=continuation.continuation_id,
        lifecycle="completed",
        controller_request_id="close-1",
    )
    assert replay_changed is False
    assert replay.lifecycle == ContinuationLifecycle.COMPLETED

    with pytest.raises(ContinuationClosed):
        store.append_contract_revision(
            continuation_context_ref=revision.contract_revision_id,
            instruction_text="must be rejected",
            provenance_class="controller_submitted_text",
            controller_request_id="contract-after-close",
        )
    with pytest.raises(ContinuationClosed):
        store.append_handoff(
            continuation_context_ref=revision.contract_revision_id,
            handoff_text="must be rejected",
            controller_request_id="handoff-after-close",
        )


def test_c1_resume_and_history_reads_remain_available_after_cancel(tmp_path: Path) -> None:
    store = ContinuationStore(tmp_path / "runs")
    continuation, revision, _ = _open(store)
    handoff, _ = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text="preserve this after cancellation",
        controller_request_id="handoff-before-cancel",
    )
    store.close_continuation(
        continuation_id=continuation.continuation_id,
        lifecycle="cancelled",
        controller_request_id="cancel-1",
    )
    resolved_continuation, resolved_revision = store.resolve_context_ref(
        revision.contract_revision_id
    )
    assert resolved_continuation.lifecycle == ContinuationLifecycle.CANCELLED
    assert resolved_revision == revision
    assert store.latest_handoff(continuation.continuation_id) == handoff
    assert store.list_contract_history(continuation.continuation_id) == [revision]


def test_c1_effect_link_is_origin_only_and_close_does_not_mutate_run(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    run_store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="executable_profile",
        run_dir=runs_dir / RUN_ID,
        input_data={"effect": True},
        status="completed",
    )
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    before_updated_at = continuation.updated_at
    link, created = store.insert_effect_link(
        continuation_context_ref=revision.contract_revision_id,
        effect_kind="run",
        effect_id=RUN_ID,
        controller_request_id="link-run-1",
    )
    assert created is True
    assert link.effect_id == RUN_ID
    assert link.continuation_id == continuation.continuation_id
    assert not hasattr(link, "status")
    assert store.get_continuation(continuation.continuation_id).updated_at > before_updated_at
    before = run_store.get_run(RUN_ID)

    store.close_continuation(
        continuation_id=continuation.continuation_id,
        lifecycle="completed",
        controller_request_id="close-linked",
    )
    after = run_store.get_run(RUN_ID)
    assert after["status"] == before["status"] == "completed"
    assert after["input"] == before["input"]
    assert store.list_effect_links(continuation.continuation_id) == [link]


def test_c1_effect_link_requires_current_open_context_and_existing_effect(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    run_store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="executable_profile",
        run_dir=runs_dir / RUN_ID,
        input_data={},
        status="completed",
    )
    store = ContinuationStore(runs_dir)
    continuation, first, _ = _open(store)
    second, _ = store.append_contract_revision(
        continuation_context_ref=first.contract_revision_id,
        instruction_text="revision two",
        provenance_class="controller_submitted_text",
        controller_request_id="contract-effect-2",
    )
    with pytest.raises(StaleContinuationContract):
        store.insert_effect_link(
            continuation_context_ref=first.contract_revision_id,
            effect_kind="run",
            effect_id=RUN_ID,
            controller_request_id="link-stale",
        )
    with pytest.raises(KeyError):
        store.insert_effect_link(
            continuation_context_ref=second.contract_revision_id,
            effect_kind="run",
            effect_id="20260815T120001Z_executable_profile_abcdef13",
            controller_request_id="link-missing",
        )
    assert store.list_effect_links(continuation.continuation_id) == []


def test_c1_connection_scoped_effect_link_rolls_back_with_caller_transaction(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    run_store.create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="executable_profile",
        run_dir=runs_dir / RUN_ID,
        input_data={},
        status="completed",
    )
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)

    with pytest.raises(RuntimeError, match="rollback proof"):
        with store.transaction() as conn:
            store.insert_effect_link_in_connection(
                conn,
                continuation_context_ref=revision.contract_revision_id,
                effect_kind="run",
                effect_id=RUN_ID,
                controller_request_id="link-rollback",
            )
            raise RuntimeError("rollback proof")

    assert store.list_effect_links(continuation.continuation_id) == []
    link, created = store.insert_effect_link(
        continuation_context_ref=revision.contract_revision_id,
        effect_kind="run",
        effect_id=RUN_ID,
        controller_request_id="link-rollback",
    )
    assert created is True
    assert link.effect_id == RUN_ID
