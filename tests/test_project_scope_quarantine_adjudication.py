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
