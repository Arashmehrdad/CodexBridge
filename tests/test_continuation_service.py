from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from soma.continuations import ContinuationService, ContinuationStore
from soma.run_store import RunStore
from soma.tasks.models import make_task_id
from soma.tasks.store import TaskStore


RUN_ID = "20260815T130000Z_executable_profile_abcdef12"


def _open(store: ContinuationStore, request_id: str = "c2-open"):
    return store.open_continuation(
        label="C2 service test",
        instruction_text="Continue the accepted continuation implementation plan.",
        provenance_class="controller_submitted_text",
        controller_request_id=request_id,
    )


def _create_run(run_store: RunStore, runs_dir: Path, run_id: str, *, status: str = "completed"):
    return run_store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=runs_dir / run_id,
        input_data={"run_id": run_id},
        status=status,
    )


def _create_task(task_store: TaskStore, *, request_id: str, state: str = "completed") -> str:
    task_id = make_task_id()
    task_store.reserve_task(
        task_id=task_id,
        task_kind="reasoning",
        controller_request_id=request_id,
        request_hash=(request_id.encode("utf-8").hex() + ("0" * 64))[:64],
        backend_kind="soma_reasoning",
        backend_executor="reasoning_backend",
        backend_ref="",
        backend_identity={},
        state=state,
        phase="result_published" if state == "completed" else "accepted",
    )
    return task_id


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_c2_list_orders_by_latest_checkpoint_activity(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    first, first_revision, _ = _open(store, request_id="c2-list-first")
    second, _, _ = _open(store, request_id="c2-list-second")
    service = ContinuationService(runs_dir, continuation_store=store)

    assert service.list_continuations(limit=10)["items"][0]["continuation_id"] == second.continuation_id

    handoff, _ = store.append_handoff(
        continuation_context_ref=first_revision.contract_revision_id,
        handoff_text="first continuation is active again",
        controller_request_id="c2-list-first-checkpoint",
    )
    listed = service.list_continuations(limit=10)["items"]

    assert listed[0]["continuation_id"] == first.continuation_id
    assert listed[0]["updated_at"] == handoff.created_at


def test_c2_resume_empty_continuation_is_bounded_and_mechanical(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    service = ContinuationService(runs_dir, continuation_store=store)

    resume = service.resume(continuation.continuation_id)

    assert resume["continuation"]["continuation_id"] == continuation.continuation_id
    assert resume["continuation"]["lifecycle"] == "open"
    assert resume["continuation_context_ref"] == revision.contract_revision_id
    assert resume["controller_instruction"]["instruction_text"].startswith("Continue")
    assert resume["sol_handoff"] is None
    assert resume["contract_changed_since_handoff"] is False
    assert resume["associated_effects"]["items"] == []
    assert resume["associated_effects"]["has_more"] is False
    assert resume["retrieval"]["handoffs"]["total_count"] == 0
    assert resume["retrieval"]["effects"]["total_count"] == 0


def test_c2_resume_with_handoff_preserves_free_form_text(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    text = "Free-form handoff.\nNo required headings.\nUncertainty: maybe inspect current state."
    handoff, _ = store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text=text,
        controller_request_id="c2-handoff",
    )

    resume = ContinuationService(runs_dir, continuation_store=store).resume(
        continuation.continuation_id
    )

    assert resume["sol_handoff"]["handoff_id"] == handoff.handoff_id
    assert resume["sol_handoff"]["handoff_text"] == text
    assert resume["sol_handoff"]["contract_revision_id"] == revision.contract_revision_id
    assert resume["retrieval"]["handoffs"]["total_count"] == 1


def test_c2_resume_projects_current_canonical_task_truth(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    continuation_store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(continuation_store)
    task_id = _create_task(task_store, request_id="c2-task")
    continuation_store.insert_effect_link(
        continuation_context_ref=revision.contract_revision_id,
        effect_kind="task",
        effect_id=task_id,
        controller_request_id="c2-task-link",
    )
    service = ContinuationService(
        runs_dir,
        continuation_store=continuation_store,
        task_store=task_store,
    )

    effect = service.resume(continuation.continuation_id)["associated_effects"]["items"][0]

    assert effect["effect_kind"] == "task"
    assert effect["effect_id"] == task_id
    assert effect["origin_contract_revision_id"] == revision.contract_revision_id
    assert effect["canonical"]["projection_status"] == "available"
    assert effect["canonical"]["state"] == "completed"
    assert effect["canonical"]["recovery"]["state"] == "none"
    assert "objective_complete" not in effect["canonical"]


def test_c2_resume_projects_current_canonical_run_truth_and_bounded_result(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    _create_run(run_store, runs_dir, RUN_ID)
    continuation_store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(continuation_store)
    continuation_store.insert_effect_link(
        continuation_context_ref=revision.contract_revision_id,
        effect_kind="run",
        effect_id=RUN_ID,
        controller_request_id="c2-run-link",
    )
    service = ContinuationService(
        runs_dir,
        continuation_store=continuation_store,
        run_store=run_store,
    )

    effect = service.resume(continuation.continuation_id)["associated_effects"]["items"][0]

    assert effect["effect_kind"] == "run"
    assert effect["canonical"]["projection_status"] == "available"
    assert effect["canonical"]["status"] == "completed"
    assert effect["canonical"]["result"]["projection_status"] == "available"
    assert "result_json" not in effect["canonical"]["result"]


def test_c2_contract_changed_since_handoff_is_deterministic(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, first, _ = _open(store)
    handoff, _ = store.append_handoff(
        continuation_context_ref=first.contract_revision_id,
        handoff_text="Handoff under revision one.",
        controller_request_id="c2-r1-handoff",
    )
    second, _ = store.append_contract_revision(
        continuation_context_ref=first.contract_revision_id,
        instruction_text="Revision two now governs.",
        provenance_class="controller_submitted_text",
        controller_request_id="c2-r2",
    )

    resume = ContinuationService(runs_dir, continuation_store=store).resume(
        continuation.continuation_id
    )

    assert resume["continuation_context_ref"] == second.contract_revision_id
    assert resume["sol_handoff"]["handoff_id"] == handoff.handoff_id
    assert resume["sol_handoff"]["contract_revision_id"] == first.contract_revision_id
    assert resume["contract_changed_since_handoff"] is True


def test_c2_missing_historical_effect_target_is_preserved_conservatively(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    _create_run(run_store, runs_dir, RUN_ID)
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    link, _ = store.insert_effect_link(
        continuation_context_ref=revision.contract_revision_id,
        effect_kind="run",
        effect_id=RUN_ID,
        controller_request_id="c2-missing-link",
    )
    with run_store.connect() as conn:
        conn.execute("DELETE FROM runs WHERE run_id = ?", (RUN_ID,))

    effect = ContinuationService(runs_dir, continuation_store=store).resume(
        continuation.continuation_id
    )["associated_effects"]["items"][0]

    assert effect["link_id"] == link.link_id
    assert effect["effect_id"] == RUN_ID
    assert effect["canonical"] == {"projection_status": "missing"}


def test_c2_corrupt_historical_task_projection_does_not_destroy_origin_link(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    task_id = _create_task(task_store, request_id="c2-corrupt-task")
    link, _ = store.insert_effect_link(
        continuation_context_ref=revision.contract_revision_id,
        effect_kind="task",
        effect_id=task_id,
        controller_request_id="c2-corrupt-link",
    )
    with task_store.connect() as conn:
        conn.execute("UPDATE tasks SET state = 'historically_corrupt' WHERE task_id = ?", (task_id,))

    effect = ContinuationService(
        runs_dir, continuation_store=store, task_store=task_store
    ).resume(continuation.continuation_id)["associated_effects"]["items"][0]

    assert effect["link_id"] == link.link_id
    assert effect["canonical"]["projection_status"] == "unavailable"
    assert effect["canonical"]["error_type"] == "ValidationError"


def test_c2_many_effects_are_bounded_and_cursor_pages_have_no_duplicates(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    expected_ids: set[str] = set()
    for index in range(12):
        run_id = f"20260815T13{index:02d}00Z_executable_profile_{index:08x}"
        _create_run(run_store, runs_dir, run_id)
        store.insert_effect_link(
            continuation_context_ref=revision.contract_revision_id,
            effect_kind="run",
            effect_id=run_id,
            controller_request_id=f"c2-many-link-{index}",
        )
        expected_ids.add(run_id)
    service = ContinuationService(
        runs_dir, continuation_store=store, run_store=run_store
    )

    resume = service.resume(continuation.continuation_id, effect_limit=5)
    first = resume["associated_effects"]
    assert first["count"] == 5
    assert first["total_count"] == 12
    assert first["has_more"] is True
    assert first["next_cursor"]

    seen = {item["effect_id"] for item in first["items"]}
    cursor = first["next_cursor"]
    page_sizes = [first["count"]]
    while cursor:
        page = service.effect_history(
            continuation.continuation_id, limit=5, cursor=cursor
        )
        page_ids = {item["effect_id"] for item in page["items"]}
        assert seen.isdisjoint(page_ids)
        seen.update(page_ids)
        page_sizes.append(page["count"])
        cursor = page["next_cursor"]
    assert page_sizes == [5, 5, 2]
    assert seen == expected_ids


def test_c2_concurrent_handoffs_are_both_preserved_in_history(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def write(index: int) -> None:
        try:
            barrier.wait()
            store.append_handoff(
                continuation_context_ref=revision.contract_revision_id,
                handoff_text=f"concurrent handoff {index}",
                controller_request_id=f"c2-concurrent-handoff-{index}",
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(index,)) for index in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    service = ContinuationService(runs_dir, continuation_store=store)
    history = service.handoff_history(continuation.continuation_id, limit=10)
    resume = service.resume(continuation.continuation_id)

    assert history["count"] == 2
    assert {item["handoff_text"] for item in history["items"]} == {
        "concurrent handoff 1",
        "concurrent handoff 2",
    }
    assert [item["sequence_number"] for item in history["items"]] == [2, 1]
    assert resume["sol_handoff"]["sequence_number"] == 2


def test_c2_handoff_history_is_bounded_and_cursor_is_identity_bound(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    for index in range(7):
        store.append_handoff(
            continuation_context_ref=revision.contract_revision_id,
            handoff_text=f"handoff {index}",
            controller_request_id=f"c2-page-handoff-{index}",
        )
    other, _, _ = _open(store, request_id="c2-open-other")
    service = ContinuationService(runs_dir, continuation_store=store)

    first = service.handoff_history(continuation.continuation_id, limit=3)
    second = service.handoff_history(
        continuation.continuation_id, limit=3, cursor=first["next_cursor"]
    )
    third = service.handoff_history(
        continuation.continuation_id, limit=3, cursor=second["next_cursor"]
    )

    assert [first["count"], second["count"], third["count"]] == [3, 3, 1]
    assert third["has_more"] is False
    assert third["next_cursor"] == ""
    with pytest.raises(ValueError, match="continuation mismatch"):
        service.handoff_history(
            other.continuation_id, limit=3, cursor=first["next_cursor"]
        )


def test_c2_history_distinguishes_missing_continuation_from_empty_history(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    service = ContinuationService(runs_dir)
    missing_id = "cont_20260815T130000Z_aaaaaaaaaaaa"

    with pytest.raises(KeyError, match="Continuation not found"):
        service.handoff_history(missing_id)
    with pytest.raises(KeyError, match="Continuation not found"):
        service.effect_history(missing_id)


def test_c2_resume_remains_readable_after_continuation_close(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, revision, _ = _open(store)
    store.append_handoff(
        continuation_context_ref=revision.contract_revision_id,
        handoff_text="This remains readable after close.",
        controller_request_id="c2-close-handoff",
    )
    store.close_continuation(
        continuation_id=continuation.continuation_id,
        lifecycle="completed",
        controller_request_id="c2-close",
    )

    resume = ContinuationService(runs_dir, continuation_store=store).resume(
        continuation.continuation_id
    )

    assert resume["continuation"]["lifecycle"] == "completed"
    assert resume["sol_handoff"]["handoff_text"] == "This remains readable after close."
    assert resume["continuation_context_ref"] == revision.contract_revision_id


def test_c2_resume_contains_no_semantic_next_action_contract(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ContinuationStore(runs_dir)
    continuation, _, _ = _open(store)
    resume = ContinuationService(runs_dir, continuation_store=store).resume(
        continuation.continuation_id
    )

    forbidden = {
        "recommended_next_action",
        "next_action",
        "next_step",
        "reasoning_phase",
        "pending_action",
    }
    assert forbidden.isdisjoint(set(_walk_keys(resume)))
