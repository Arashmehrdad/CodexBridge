"""GATE-C-PREREQ-1 — owner-only quarantine adjudication.

Gate A deliberately made quarantine terminal and evidence-preserving, which left
an operational dead end resolvable only by manual SQL. These tests cover the ten
properties the Gate C preparation document requires before Gate C may be
approved.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest

import soma.server as server
from soma.project_scope import ProjectScopeError, ProjectScopeMismatch, ProjectScopeStore
from soma.project_scope.schema import PROJECT_SCOPE_TABLE_NAMES
from soma.tasks.manager import TaskManager
from soma.tasks.models import TaskState
from soma.tasks.store import TaskStore
from test_project_scope_foundation import (
    PROJECT_ALPHA,
    PROJECT_BETA,
    RESOURCE_REPOSITORY,
    StoredRunBackend,
    _bootstrap,
    _make_config,
)


def _scoped_manager(tmp_path: Path):
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")
    scope.set_scoped_writes_enabled(True)
    backend = StoredRunBackend(config.resolve_runs_dir())
    manager = TaskManager(config, config_path, backend=backend, scope_store=scope)
    return config, config_path, repo, scope, backend, manager


def _quarantined_task(manager, scope, *, controller_request_id="q-1"):
    """Create a scoped task and drive it into quarantine the way Soma does."""
    started = manager.start_durable_command(
        controller_request_id=controller_request_id,
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", controller_request_id],
    )
    assert started["ok"], started
    task_id = started["task_id"]
    with scope.transaction() as conn:
        scope._quarantine_task(conn, task_id, "backend_reference_mismatch")
    return started, task_id


def test_schema_v2_is_additive_and_idempotent(tmp_path: Path) -> None:
    scope = ProjectScopeStore(tmp_path)
    first = scope.init_db()
    second = scope.init_db()
    assert first == [1, 2]
    assert second == []

    state = scope.schema_state()
    assert state["schema_version"] == 2
    assert state["target_schema_version"] == 2
    assert state["up_to_date"] is True
    assert state["missing_tables"] == []
    assert "project_scope_adjudications" in PROJECT_SCOPE_TABLE_NAMES

    with scope._read() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(project_scope_adjudications)")
        }
        assert "request_hash" in columns
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM project_scope_adjudications"
                ).fetchone()[0]
            )
            == 0
        )


def test_adjudication_preserves_the_quarantined_record(tmp_path: Path) -> None:
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    started, task_id = _quarantined_task(manager, scope)
    run_id = started["backend_reference"]

    with scope._read() as conn:
        before = dict(
            conn.execute(
                "SELECT * FROM project_scope_quarantine WHERE record_id = ?",
                (task_id,),
            ).fetchone()
        )

    result = scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="owner reviewed the backend reference mismatch",
        idempotency_key="adj-key-1",
    )
    assert result["ok"] is True
    assert result["disposition"] == "acknowledged"
    assert result["quarantine_preserved"] is True
    assert result["replayed"] is False

    with scope._read() as conn:
        after = dict(
            conn.execute(
                "SELECT * FROM project_scope_quarantine WHERE record_id = ?",
                (task_id,),
            ).fetchone()
        )
        task_status = conn.execute(
            "SELECT status FROM project_task_reservations WHERE task_id = ?",
            (task_id,),
        ).fetchone()[0]
        attempt_status = conn.execute(
            "SELECT status FROM project_run_attempts WHERE run_id = ?", (run_id,)
        ).fetchone()[0]

    # The original evidence row is byte-identical and nothing returned to life.
    assert after == before
    assert task_status == "quarantined"
    assert attempt_status == "quarantined"
    assert result["quarantine_evidence_hash"] == before["evidence_hash"]


def test_adjudication_is_idempotent_and_single_shot(tmp_path: Path) -> None:
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)

    first = scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="first decision",
        idempotency_key="adj-key-1",
    )
    replay = scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="first decision",
        idempotency_key="adj-key-1",
    )
    assert replay["adjudication_id"] == first["adjudication_id"]
    assert replay["replayed"] is True

    # A different key must not create a second, competing disposition.
    with pytest.raises(ProjectScopeError, match="single-shot"):
        scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="task_reservation",
            record_id=task_id,
            disposition="acknowledged",
            reason="second decision",
            idempotency_key="adj-key-2",
        )

    with scope._read() as conn:
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM project_scope_adjudications"
                ).fetchone()[0]
            )
            == 1
        )


def test_reused_key_with_a_different_decision_is_rejected(tmp_path: Path) -> None:
    """One key must never replay a decision the caller did not submit.

    Silently returning the stored row here would tell an owner that a different
    decision had been accepted when nothing was recorded.
    """
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)
    successor = manager.start_durable_command(
        controller_request_id="successor-a",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", "successor-a"],
    )
    assert successor["ok"], successor

    first = scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="first decision",
        idempotency_key="shared-key",
    )
    assert first["replayed"] is False

    conflicting = [
        # A materially different disposition under the original key.
        {
            "disposition": "superseded",
            "reason": "conflicting decision",
            "successor_task_id": successor["task_id"],
        },
        # The rationale on the record is itself decision-bearing.
        {"disposition": "acknowledged", "reason": "conflicting decision"},
    ]
    for kwargs in conflicting:
        with pytest.raises(ProjectScopeError, match="already used for a different"):
            scope.adjudicate_quarantine(
                project_id=PROJECT_ALPHA,
                record_kind="task_reservation",
                record_id=task_id,
                idempotency_key="shared-key",
                **kwargs,
            )

    # The original decision is untouched and still the only one on record.
    with scope._read() as conn:
        rows = [
            dict(row)
            for row in conn.execute("SELECT * FROM project_scope_adjudications")
        ]
    assert len(rows) == 1
    assert rows[0]["disposition"] == "acknowledged"
    assert rows[0]["reason"] == "first decision"
    assert rows[0]["successor_task_id"] == ""
    assert rows[0]["request_hash"] == first["request_hash"]

    # The fingerprint is over the *normalized* request, so the same decision
    # written with incidental whitespace is a replay rather than a conflict.
    normalized = scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="   first decision   ",
        idempotency_key="shared-key",
    )
    assert normalized["replayed"] is True
    assert normalized["request_hash"] == first["request_hash"]


def test_reused_key_with_a_different_successor_is_rejected(tmp_path: Path) -> None:
    """successor_task_id alone makes a request a different decision.

    Also pins that the conflict check does not over-reject: an identical
    resubmission is still an idempotent replay.
    """
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)
    chosen, rejected = (
        manager.start_durable_command(
            controller_request_id=f"successor-{label}",
            project_id=PROJECT_ALPHA,
            repo_name="sample",
            argv=["Write-Output", label],
        )
        for label in ("chosen", "rejected")
    )

    decision = dict(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="superseded",
        reason="replaced after owner review",
        idempotency_key="successor-key",
    )
    first = scope.adjudicate_quarantine(
        **decision, successor_task_id=chosen["task_id"]
    )
    assert first["successor_task_id"] == chosen["task_id"]

    with pytest.raises(ProjectScopeError, match="differing fields: successor_task_id"):
        scope.adjudicate_quarantine(
            **decision, successor_task_id=rejected["task_id"]
        )

    replay = scope.adjudicate_quarantine(
        **decision, successor_task_id=chosen["task_id"]
    )
    assert replay["replayed"] is True
    assert replay["adjudication_id"] == first["adjudication_id"]

    with scope._read() as conn:
        stored = conn.execute(
            "SELECT successor_task_id FROM project_scope_adjudications"
        ).fetchall()
    assert [row[0] for row in stored] == [chosen["task_id"]]


def _race(work) -> list[object]:
    """Run two attempts against the same record with a barrier between them."""
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    lock = threading.Lock()

    def attempt(index: int) -> None:
        barrier.wait()
        try:
            result: object = work(index)
        except (ProjectScopeError, sqlite3.IntegrityError) as exc:
            result = exc
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes


def test_concurrent_same_key_requests_resolve_by_request_fingerprint(
    tmp_path: Path,
) -> None:
    """Concurrency does not change the rule: same decision replays, different rejects."""
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, identical_task = _quarantined_task(manager, scope)
    _second, conflicting_task = _quarantined_task(
        manager, scope, controller_request_id="q-conflict"
    )

    def same_decision(_index: int) -> dict:
        return scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="task_reservation",
            record_id=identical_task,
            disposition="acknowledged",
            reason="identical decision",
            idempotency_key="concurrent-key",
        )

    identical = _race(same_decision)
    # Both callers see the same accepted decision; neither is told it failed.
    assert all(isinstance(o, dict) for o in identical), identical
    assert len({o["adjudication_id"] for o in identical}) == 1
    assert len({o["request_hash"] for o in identical}) == 1
    assert sorted(o["replayed"] for o in identical) == [False, True]

    def conflicting_decision(index: int) -> dict:
        return scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="task_reservation",
            record_id=conflicting_task,
            disposition="acknowledged",
            reason=f"decision {index}",
            idempotency_key="concurrent-key",
        )

    conflicting = _race(conflicting_decision)
    assert len([o for o in conflicting if isinstance(o, dict)]) == 1
    assert len([o for o in conflicting if isinstance(o, Exception)]) == 1

    with scope._read() as conn:
        counts = conn.execute(
            "SELECT record_id, COUNT(*) FROM project_scope_adjudications "
            "GROUP BY record_id"
        ).fetchall()
    assert sorted(tuple(row) for row in counts) == sorted(
        [(conflicting_task, 1), (identical_task, 1)]
    )


def test_concurrent_adjudication_yields_exactly_one_replacement(
    tmp_path: Path,
) -> None:
    """Crash or race cannot produce two successors for one quarantined record."""
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)
    successor = manager.start_durable_command(
        controller_request_id="successor-request",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", "successor"],
    )
    assert successor["ok"], successor

    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def attempt(key: str) -> None:
        barrier.wait()
        try:
            outcomes.append(
                scope.adjudicate_quarantine(
                    project_id=PROJECT_ALPHA,
                    record_kind="task_reservation",
                    record_id=task_id,
                    disposition="superseded",
                    reason=f"replacement via {key}",
                    idempotency_key=key,
                    successor_task_id=successor["task_id"],
                )
            )
        except (ProjectScopeError, sqlite3.IntegrityError) as exc:
            outcomes.append(exc)

    threads = [
        threading.Thread(target=attempt, args=("race-a",)),
        threading.Thread(target=attempt, args=("race-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    accepted = [o for o in outcomes if isinstance(o, dict)]
    rejected = [o for o in outcomes if not isinstance(o, dict)]
    assert len(accepted) == 1
    assert len(rejected) == 1
    with scope._read() as conn:
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM project_scope_adjudications WHERE record_id = ?",
                    (task_id,),
                ).fetchone()[0]
            )
            == 1
        )


def test_cross_project_adjudication_fails_without_disclosure(tmp_path: Path) -> None:
    _c, _p, repo, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)
    _bootstrap(
        scope,
        repo,
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        access_mode="shared",
    )

    with pytest.raises(ProjectScopeMismatch) as cross:
        scope.adjudicate_quarantine(
            project_id=PROJECT_BETA,
            record_kind="task_reservation",
            record_id=task_id,
            disposition="acknowledged",
            reason="not mine",
            idempotency_key="beta-key",
        )
    with pytest.raises(ProjectScopeMismatch) as absent:
        scope.adjudicate_quarantine(
            project_id=PROJECT_BETA,
            record_kind="task_reservation",
            record_id="task_does_not_exist",
            disposition="acknowledged",
            reason="not mine",
            idempotency_key="beta-key-2",
        )

    # An existing foreign record and a nonexistent one are indistinguishable,
    # so the error cannot be used to enumerate another project's identities.
    assert str(cross.value) == str(absent.value)
    assert task_id not in str(cross.value)
    with scope._read() as conn:
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM project_scope_adjudications"
                ).fetchone()[0]
            )
            == 0
        )


def test_supersession_requires_an_active_same_project_successor(
    tmp_path: Path,
) -> None:
    _c, _p, repo, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)

    with pytest.raises(ProjectScopeMismatch, match="Successor task"):
        scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="task_reservation",
            record_id=task_id,
            disposition="superseded",
            reason="missing successor",
            idempotency_key="k1",
            successor_task_id="no_such_task",
        )

    # A quarantined record cannot supersede another quarantined record.
    _second, second_task_id = _quarantined_task(
        manager, scope, controller_request_id="q-2"
    )
    with pytest.raises(ProjectScopeMismatch, match="Successor task"):
        scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="task_reservation",
            record_id=task_id,
            disposition="superseded",
            reason="dead successor",
            idempotency_key="k2",
            successor_task_id=second_task_id,
        )

    successor = manager.start_durable_command(
        controller_request_id="good-successor",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", "ok"],
    )
    accepted = scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="superseded",
        reason="replaced after owner review",
        idempotency_key="k3",
        successor_task_id=successor["task_id"],
    )
    assert accepted["disposition"] == "superseded"
    assert accepted["successor_task_id"] == successor["task_id"]


def test_invalid_requests_are_rejected_before_any_write(tmp_path: Path) -> None:
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)

    bad_calls = [
        {"disposition": "released", "reason": "r", "idempotency_key": "k"},
        {"disposition": "acknowledged", "reason": "  ", "idempotency_key": "k"},
        {"disposition": "acknowledged", "reason": "r", "idempotency_key": ""},
        {
            "disposition": "acknowledged",
            "reason": "r",
            "idempotency_key": "k",
            "successor_task_id": "someone",
        },
    ]
    for kwargs in bad_calls:
        with pytest.raises(ProjectScopeError):
            scope.adjudicate_quarantine(
                project_id=PROJECT_ALPHA,
                record_kind="task_reservation",
                record_id=task_id,
                **kwargs,
            )
    with pytest.raises(ProjectScopeError, match="record_kind"):
        scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="not_a_kind",
            record_id=task_id,
            disposition="acknowledged",
            reason="r",
            idempotency_key="k",
        )

    with scope._read() as conn:
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM project_scope_adjudications"
                ).fetchone()[0]
            )
            == 0
        )


def test_evidence_is_queryable_without_manual_sql(tmp_path: Path) -> None:
    _c, _p, _r, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)

    before = manager.list_quarantine(PROJECT_ALPHA)
    assert before["ok"] is True
    assert before["returned_count"] >= 1
    assert before["adjudicated_count"] == 0
    listed = [r for r in before["records"] if r["record_id"] == task_id]
    assert listed and listed[0]["reason_code"] == "backend_reference_mismatch"
    assert listed[0]["adjudicated"] is False

    manager.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="owner accepted the dead record",
        idempotency_key="listing-key",
    )
    after = manager.list_quarantine(PROJECT_ALPHA)
    resolved = [r for r in after["records"] if r["record_id"] == task_id][0]
    assert resolved["adjudicated"] is True
    assert resolved["disposition"] == "acknowledged"
    assert resolved["adjudication_reason"] == "owner accepted the dead record"
    assert after["adjudicated_count"] >= 1


def test_quarantine_listing_is_project_isolated(tmp_path: Path) -> None:
    _c, _p, repo, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)
    _bootstrap(
        scope,
        repo,
        project_id=PROJECT_BETA,
        project_key="beta",
        resource_id=RESOURCE_REPOSITORY,
        access_mode="shared",
    )
    beta = manager.list_quarantine(PROJECT_BETA)
    assert beta["ok"] is True
    assert beta["returned_count"] == 0
    assert task_id not in str(beta["records"])


def test_adjudication_requires_schema_v2(tmp_path: Path) -> None:
    """A v1 store reports the pending activation instead of failing obscurely."""
    from soma.project_scope.schema import PROJECT_SCOPE_MIGRATIONS, apply_project_scope_migrations

    scope = ProjectScopeStore(tmp_path)
    scope.runs_dir.mkdir(parents=True, exist_ok=True)
    applied = apply_project_scope_migrations(
        scope.connect, migrations=PROJECT_SCOPE_MIGRATIONS[:1]
    )
    assert applied == [1]

    state = scope.schema_state()
    assert state["schema_version"] == 1
    assert state["up_to_date"] is False
    assert state["missing_tables"] == ["project_scope_adjudications"]

    with pytest.raises(ProjectScopeError, match="schema v2"):
        scope.list_quarantine(PROJECT_ALPHA)
    with pytest.raises(ProjectScopeError, match="schema v2"):
        scope.adjudicate_quarantine(
            project_id=PROJECT_ALPHA,
            record_kind="task_reservation",
            record_id="anything",
            disposition="acknowledged",
            reason="r",
            idempotency_key="k",
        )


def test_mcp_surface_is_strict_and_scope_mandatory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, config_path, _repo, scope, _b, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_config_path", config_path)

    async def tools() -> dict:
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    discovered = asyncio.run(tools())

    for name, operation, required in (
        ("task_query", "quarantine", "project_id"),
        ("task_action", "adjudicate_quarantine", "project_id"),
    ):
        branch = next(
            b
            for b in discovered[name].parameters["oneOf"]
            if b["properties"]["operation"].get("const") == operation
        )
        assert required in branch["required"]
        assert branch["additionalProperties"] is False

    # project_id is mandatory, so an unscoped adjudication cannot be expressed.
    with pytest.raises(Exception):
        asyncio.run(
            discovered["task_action"].run(
                {
                    "operation": "adjudicate_quarantine",
                    "record_kind": "task_reservation",
                    "record_id": task_id,
                    "disposition": "acknowledged",
                    "reason": "no project",
                    "idempotency_key": "k",
                }
            )
        )

    result = asyncio.run(
        discovered["task_action"].run(
            {
                "operation": "adjudicate_quarantine",
                "project_id": PROJECT_ALPHA,
                "record_kind": "task_reservation",
                "record_id": task_id,
                "disposition": "acknowledged",
                "reason": "adjudicated over MCP",
                "idempotency_key": "mcp-key",
            }
        )
    ).structured_content
    assert result["ok"] is True
    assert result["quarantine_preserved"] is True

    listed = asyncio.run(
        discovered["task_query"].run(
            {"operation": "quarantine", "project_id": PROJECT_ALPHA}
        )
    ).structured_content
    assert listed["ok"] is True
    assert any(r["record_id"] == task_id and r["adjudicated"] for r in listed["records"])


def test_no_second_authority_is_introduced(tmp_path: Path) -> None:
    """Adjudication records a decision; it never creates task or run identity."""
    _c, _p, _r, scope, backend, manager = _scoped_manager(tmp_path)
    _started, task_id = _quarantined_task(manager, scope)

    with scope._read() as conn:
        tasks_before = int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
        runs_before = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    launched_before = len(backend.started)

    scope.adjudicate_quarantine(
        project_id=PROJECT_ALPHA,
        record_kind="task_reservation",
        record_id=task_id,
        disposition="acknowledged",
        reason="no new authority",
        idempotency_key="authority-key",
    )

    with scope._read() as conn:
        assert int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]) == tasks_before
        assert int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]) == runs_before
        assert (
            int(
                conn.execute(
                    "SELECT COUNT(*) FROM project_task_reservations "
                    "WHERE status != 'quarantined'"
                ).fetchone()[0]
            )
            == 0
        )
    assert len(backend.started) == launched_before


class _ToggleRecoveryBackend(StoredRunBackend):
    def __init__(self, runs_dir: Path) -> None:
        super().__init__(runs_dir)
        self.fail_start = True

    def start(self, spec, backend_ref: str) -> dict:
        if self.fail_start:
            self.started.append(backend_ref)
            raise ValueError("fixture launch rejected before run creation")
        return super().start(spec, backend_ref)


def _recovery_fixture(tmp_path: Path):
    config, config_path, repo = _make_config(tmp_path)
    TaskStore(config.resolve_runs_dir())
    scope = ProjectScopeStore(config.resolve_runs_dir())
    scope.init_db()
    _bootstrap(scope, repo, access_mode="shared")
    scope.set_scoped_writes_enabled(True)
    backend = _ToggleRecoveryBackend(config.resolve_runs_dir())
    manager = TaskManager(
        config, config_path, backend=backend, scope_store=scope
    )

    failed = manager.start_durable_command(
        controller_request_id="recovery-target",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", "never-launched"],
        working_directory=str(repo),
    )
    assert failed["ok"] is False
    target = manager.get_status(
        failed["task_id"], project_id=PROJECT_ALPHA
    )
    assert target["state"] == "uncertain"

    backend.fail_start = False
    successor = manager.start_durable_command(
        controller_request_id="recovery-successor",
        project_id=PROJECT_ALPHA,
        repo_name="sample",
        argv=["Write-Output", "successor"],
        working_directory=str(repo),
    )
    assert successor["ok"] is True
    stored = backend.store.get_run(successor["backend_reference"])
    completed = backend.store.transition_terminal(
        successor["backend_reference"],
        status="completed",
        result={"summary": "successor"},
        expected_statuses=(str(stored["status"]),),
        expected_state_version=int(stored["state_version"]),
        exit_code=0,
        summary="successor",
    )
    assert completed is not None
    successor = manager.get_status(
        successor["task_id"], project_id=PROJECT_ALPHA
    )
    assert successor["state"] == "completed"
    return manager, scope, backend, target, successor


def _resolve_recovery(manager, target, successor, **overrides):
    payload = {
        "project_id": PROJECT_ALPHA,
        "task_id": target["task_id"],
        "if_state_version": target["state_version"],
        "successor_task_id": successor["task_id"],
        "reason": "malformed proof request was replaced by the successful proof",
        "idempotency_key": "resolve-recovery-1",
    }
    payload.update(overrides)
    return manager.resolve_recovery(**payload)


def test_recovery_resolution_is_atomic_terminal_and_evidence_preserving(
    tmp_path: Path,
) -> None:
    manager, scope, _backend, target, successor = _recovery_fixture(tmp_path)
    result = _resolve_recovery(manager, target, successor)
    assert result["ok"] is True
    assert result["state"] == "failed"
    assert result["phase"] == "recovery"
    assert result["recovery_state"] == "resolved"
    assert result["task_reservation_status"] == "quarantined"
    assert result["run_attempt_status"] == "quarantined"
    assert result["backend_run_fabricated"] is False
    assert result["replayed"] is False

    task = manager.store.get_task(target["task_id"])
    assert task.state is TaskState.FAILED
    assert task.result_ref == task.result_hash == task.evidence_ref == ""
    with scope._read() as conn:
        reservation = conn.execute(
            "SELECT status FROM project_task_reservations WHERE task_id = ?",
            (target["task_id"],),
        ).fetchone()[0]
        attempt = conn.execute(
            "SELECT status FROM project_run_attempts WHERE task_id = ?",
            (target["task_id"],),
        ).fetchone()[0]
        run = conn.execute(
            "SELECT 1 FROM runs WHERE run_id = ?",
            (target["backend_reference"],),
        ).fetchone()
        adjudication = conn.execute(
            "SELECT disposition, successor_task_id "
            "FROM project_scope_adjudications "
            "WHERE record_kind = 'task_reservation' AND record_id = ?",
            (target["task_id"],),
        ).fetchone()
        link = conn.execute(
            "SELECT 1 FROM task_links WHERE task_id = ? "
            "AND link_type = 'supersedes' AND target_kind = 'task' "
            "AND target_id = ?",
            (successor["task_id"], target["task_id"]),
        ).fetchone()
    assert reservation == attempt == "quarantined"
    assert run is None
    assert tuple(adjudication) == ("superseded", successor["task_id"])
    assert link is not None

    records = manager.list_quarantine(PROJECT_ALPHA)["records"]
    record = next(
        item for item in records if item["record_id"] == target["task_id"]
    )
    assert record["adjudicated"] is True
    assert record["disposition"] == "superseded"


def test_identical_recovery_resolution_replays_without_duplicate_evidence(
    tmp_path: Path,
) -> None:
    manager, scope, _backend, target, successor = _recovery_fixture(tmp_path)
    first = _resolve_recovery(manager, target, successor)
    replay = _resolve_recovery(manager, target, successor)
    assert replay["ok"] is True
    assert replay["replayed"] is True
    assert replay["state_version"] == first["state_version"]
    assert replay["adjudication_id"] == first["adjudication_id"]
    with scope._read() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM project_scope_adjudications"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM task_links WHERE link_type = 'supersedes'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = ? "
            "AND stage = 'recovery_disposition'",
            (target["task_id"],),
        ).fetchone()[0] == 1


def test_recovery_resolution_conflicts_and_scope_fail_closed(
    tmp_path: Path,
) -> None:
    manager, _scope, _backend, target, successor = _recovery_fixture(tmp_path)
    stale = _resolve_recovery(
        manager,
        target,
        successor,
        if_state_version=target["state_version"] + 1,
    )
    assert stale["ok"] is False
    assert stale["error_code"] == "stale_state_version"
    wrong = _resolve_recovery(
        manager, target, successor, project_id=PROJECT_BETA
    )
    assert wrong["ok"] is False
    assert wrong["error_code"] == "project_scope_mismatch"

    first = _resolve_recovery(manager, target, successor)
    assert first["ok"] is True
    changed = _resolve_recovery(
        manager, target, successor, reason="different decision"
    )
    assert changed["ok"] is False
    assert changed["error_code"] == "task_recovery_resolution_rejected"
    other_key = _resolve_recovery(
        manager,
        target,
        successor,
        idempotency_key="resolve-recovery-2",
    )
    assert other_key["ok"] is False
    assert other_key["error_code"] == "task_recovery_resolution_rejected"


def test_existing_backend_row_keeps_normal_reconciliation_authority(
    tmp_path: Path,
) -> None:
    manager, scope, backend, target, successor = _recovery_fixture(tmp_path)
    run_dir = backend.store.runs_dir / target["backend_reference"]
    run_dir.mkdir(parents=True, exist_ok=True)
    backend.store.create_run(
        run_id=target["backend_reference"],
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data={"late": True},
        status="queued",
    )
    rejected = _resolve_recovery(manager, target, successor)
    assert rejected["ok"] is False
    assert rejected["error_code"] == "task_recovery_resolution_rejected"
    with scope._read() as conn:
        assert conn.execute(
            "SELECT status FROM project_task_reservations WHERE task_id = ?",
            (target["task_id"],),
        ).fetchone()[0] == "attached"


def test_recovery_resolution_rolls_back_every_authority_on_failure(
    tmp_path: Path,
) -> None:
    manager, scope, _backend, target, successor = _recovery_fixture(tmp_path)
    with scope.transaction() as conn:
        conn.execute(
            "CREATE TRIGGER fail_recovery_adjudication "
            "BEFORE INSERT ON project_scope_adjudications "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
    failed = _resolve_recovery(manager, target, successor)
    assert failed["ok"] is False
    task = manager.store.get_task(target["task_id"])
    assert task.state is TaskState.UNCERTAIN
    with scope._read() as conn:
        assert conn.execute(
            "SELECT status FROM project_task_reservations WHERE task_id = ?",
            (target["task_id"],),
        ).fetchone()[0] == "attached"
        assert conn.execute(
            "SELECT COUNT(*) FROM project_scope_quarantine"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM task_links WHERE link_type = 'supersedes'"
        ).fetchone()[0] == 0


def test_concurrent_identical_recovery_resolution_converges(
    tmp_path: Path,
) -> None:
    manager, _scope, _backend, target, successor = _recovery_fixture(tmp_path)
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def work() -> None:
        barrier.wait()
        result = _resolve_recovery(manager, target, successor)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(result["ok"] for result in results)
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert len({result["adjudication_id"] for result in results}) == 1


def test_recovery_resolution_mcp_shape_is_strict_and_project_scoped() -> None:
    async def tools() -> dict:
        return {tool.name: tool for tool in await server.mcp.list_tools()}

    discovered = asyncio.run(tools())
    branch = next(
        item
        for item in discovered["task_action"].parameters["oneOf"]
        if item["properties"]["operation"].get("const")
        == "resolve_recovery"
    )
    assert branch["additionalProperties"] is False
    assert set(branch["required"]) == {
        "operation",
        "project_id",
        "task_id",
        "if_state_version",
        "successor_task_id",
        "reason",
        "idempotency_key",
    }
