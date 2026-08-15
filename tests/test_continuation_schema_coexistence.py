from __future__ import annotations

from pathlib import Path

from soma.continuations import ContinuationStore
from soma.tasks.models import make_task_id
from soma.tasks.store import TaskStore


def test_c1_task_and_continuation_migrations_coexist_in_one_main_database(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    continuation_store = ContinuationStore(runs_dir)
    assert task_store.db_path == continuation_store.db_path

    with continuation_store.connect() as conn:
        rows = conn.execute(
            "SELECT component, version FROM soma_schema_migrations "
            "ORDER BY component, version"
        ).fetchall()
    versions = {(str(row[0]), int(row[1])) for row in rows}
    assert ("canonical_task_plane", 1) in versions
    assert ("canonical_task_plane", 2) in versions
    assert ("sol_semantic_continuation", 1) in versions


def test_c1_effect_link_validates_a_real_canonical_task_in_shared_transaction(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    task_id = make_task_id()
    task, created = task_store.reserve_task(
        task_id=task_id,
        task_kind="reasoning",
        controller_request_id="c1-task-create",
        request_hash="a" * 64,
        backend_kind="soma_reasoning",
        backend_executor="reasoning_backend",
        backend_ref="",
        backend_identity={},
    )
    assert created is True

    continuation_store = ContinuationStore(runs_dir)
    continuation, revision, opened = continuation_store.open_continuation(
        label="Task origin test",
        instruction_text="Track this canonical Task mechanically.",
        provenance_class="controller_submitted_text",
        controller_request_id="c1-task-continuation",
    )
    assert opened is True

    with task_store.transaction() as conn:
        link, linked = continuation_store.insert_effect_link_in_connection(
            conn,
            continuation_context_ref=revision.contract_revision_id,
            effect_kind="task",
            effect_id=task.task_id,
            controller_request_id="c1-task-link",
        )
    assert linked is True
    assert link.effect_id == task.task_id
    assert link.continuation_id == continuation.continuation_id
    assert task_store.get_task(task.task_id) == task
