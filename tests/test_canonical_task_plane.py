"""TASK-1 canonical task plane: schema, mapping, idempotency, commands,
reconciliation, compatibility, and projection tests.

Most cases use a deterministic fake execution backend so every crash window is
free and repeatable. Two cases use the real durable engine with a fake process
launcher, and one Windows case runs a real local process end to end.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from fastmcp import Client

import soma.server as server
from soma.config import AppConfig, load_config
from soma.job_manager import JobManager
from soma.run_store import RunStore
from soma.tasks.backends import BackendObservation
from soma.tasks.manager import TaskManager
from soma.tasks.models import (
    TASK_SCHEMA_VERSION,
    TaskEventLevel,
    BackendKind,
    TaskPhase,
    TaskRecord,
    TaskState,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.schema import TASK_TABLE_NAMES
from soma.tasks.store import TaskRequestConflict, TaskStore


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


class FakeProcess:
    pid = 4242


def _make_config(tmp_path: Path, *, executable: Path | None = None) -> tuple[AppConfig, Path]:
    """Write a real config file so an out-of-process worker sees the same config."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    exe = executable
    if exe is None:
        exe = tmp_path / "fake-pwsh.exe"
        exe.write_bytes(b"fake-executable-fixture")
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "executable_profiles:",
                "  powershell:",
                '    profile_id: "powershell"',
                "    enabled: true",
                f'    executable_path: "{exe.as_posix()}"',
                '    target: "local"',
                '    autonomy_profile: "permissive"',
                '    working_directory_policy: "arbitrary"',
                '    environment_policy: "arbitrary"',
                '    stdin_mode: "bytes"',
                '    stdout_mode: "protected_artifact"',
                '    stderr_mode: "protected_artifact"',
                "    allow_no_timeout: true",
                "    unrestricted_argv: true",
                "    unrestricted_paths: true",
                "    unrestricted_environment: true",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(config_path), config_path


class FakeBackend:
    """Deterministic stand-in for the durable engine.

    It records launches and exposes exactly the bounded scalar observation the
    canonical task plane consumes, so every crash window can be reproduced by
    mutating a dict rather than by killing a process.
    """

    kind = BackendKind.SOMA_DURABLE_RUN.value
    executor = "executable_profile"

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.reserved: list[str] = []
        self.started: list[str] = []
        self.cancelled: list[str] = []
        self.suppress_start = False
        self._counter = 0

    def reserve(self) -> str:
        self._counter += 1
        ref = f"20260725T000000Z_executable_profile_{self._counter:08x}"
        self.reserved.append(ref)
        return ref

    def start(self, spec, backend_ref: str) -> dict:
        self.started.append(backend_ref)
        if self.suppress_start:
            return {"accepted": True, "run_id": backend_ref, "status": "queued"}
        self.runs[backend_ref] = {
            "status": "queued",
            "tool": self.executor,
            "repo_name": spec.repo_name,
            "started_at": None,
            "ended_at": None,
            "exit_code": None,
            "result_publication_status": "not_published",
            "result_published_hash": "",
            "result_published_at": None,
            "state_version": 1,
        }
        return {"accepted": True, "run_id": backend_ref, "status": "queued"}

    def query(self, backend_ref: str) -> BackendObservation:
        if not backend_ref:
            return BackendObservation(exists=False, error_code="missing_backend_ref")
        run = self.runs.get(backend_ref)
        if run is None:
            return BackendObservation(exists=False, error_code="backend_run_not_found")
        return BackendObservation(
            exists=True,
            status=str(run["status"]),
            executor=str(run["tool"]),
            repo_name=str(run["repo_name"]),
            state_version=int(run["state_version"]),
            exit_code=run["exit_code"],
            started_at=run["started_at"],
            ended_at=run["ended_at"],
            result_publication_status=str(run["result_publication_status"]),
            result_published_hash=str(run["result_published_hash"]),
            result_published_at=run["result_published_at"],
        )

    def cancel(self, backend_ref: str) -> dict:
        self.cancelled.append(backend_ref)
        run = self.runs.get(backend_ref)
        if run is None:
            return {"ok": False, "run_id": backend_ref, "status": "", "cancelled": False}
        if run["status"] in {"completed", "failed", "cancelled", "timed_out"}:
            return {
                "ok": True,
                "run_id": backend_ref,
                "status": run["status"],
                "cancelled": False,
                "termination_confirmed": True,
                "reason": "Run is already terminal",
            }
        if run["status"] == "cancellation_pending":
            return {
                "ok": False,
                "run_id": backend_ref,
                "status": "cancellation_pending",
                "cancelled": False,
                "termination_confirmed": False,
                "reason": "Cancellation is already pending",
            }
        self.finish(backend_ref, status="cancelled", exit_code=None)
        return {
            "ok": True,
            "run_id": backend_ref,
            "status": "cancelled",
            "cancelled": True,
            "termination_confirmed": True,
        }

    def result_reference(self, backend_ref: str) -> dict:
        run = self.runs.get(backend_ref)
        if run is None:
            return {"available": False, "authority": "durable_run", "run_id": backend_ref}
        return {
            "available": True,
            "authority": "durable_run",
            "run_id": backend_ref,
            "backend_status": run["status"],
            "exit_code": run["exit_code"],
            "public_result_schema_version": "cf1.result.v1",
            "public_result_status": (
                "ready" if run["result_published_hash"] else "not_materialized"
            ),
            "public_result_source_sha256": run["result_published_hash"],
        }

    # --- fixture controls -------------------------------------------------

    def advance(self, backend_ref: str, status: str) -> None:
        run = self.runs[backend_ref]
        run["status"] = status
        run["state_version"] = int(run["state_version"]) + 1
        if status == "running" and not run["started_at"]:
            run["started_at"] = "2026-07-25T00:00:01+00:00"

    def finish(
        self, backend_ref: str, *, status: str, exit_code: int | None, published: bool = True
    ) -> None:
        run = self.runs[backend_ref]
        run["status"] = status
        run["exit_code"] = exit_code
        run["ended_at"] = "2026-07-25T00:00:09+00:00"
        run["state_version"] = int(run["state_version"]) + 1
        if published:
            run["result_publication_status"] = "published"
            run["result_published_hash"] = "a" * 64
            run["result_published_at"] = "2026-07-25T00:00:10+00:00"


def _manager(tmp_path: Path, backend: FakeBackend | None = None) -> TaskManager:
    config, config_path = _make_config(tmp_path)
    return TaskManager(config, config_path, backend=backend or FakeBackend())


def _started(manager: TaskManager, request_id: str = "req-1", **overrides) -> dict:
    payload = {
        "controller_request_id": request_id,
        "repo_name": "sample",
        "profile_id": "powershell",
        "argv": ["-NoProfile", "-Command", "Write-Output ok"],
        "working_directory": str(Path(manager.config.repos["sample"].path)),
    }
    payload.update(overrides)
    return manager.start_durable_command(**payload)


# ---------------------------------------------------------------------------
# 1-3: schema migration and typed models
# ---------------------------------------------------------------------------


def test_schema_migration_on_fresh_database_creates_every_canonical_table(
    tmp_path: Path,
) -> None:
    store = TaskStore(tmp_path / "runs")

    state = store.schema_state()
    assert state["schema_version"] == TASK_SCHEMA_VERSION
    assert state["up_to_date"] is True
    assert state["missing_tables"] == []
    assert set(state["tables"]) == set(TASK_TABLE_NAMES)

    # Re-initialisation is a no-op, so a restart never re-applies a migration.
    assert store.init_db() == []


def test_schema_migration_on_existing_run_database_is_additive(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    run_dir = runs_dir / "20260725T000000Z_executable_profile_abcdef12"
    run_dir.mkdir(parents=True)
    run_store.create_run(
        run_id="20260725T000000Z_executable_profile_abcdef12",
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data={"repo_name": "sample"},
        risk_level="high",
        requires_human=False,
        status="queued",
    )

    task_store = TaskStore(runs_dir)

    assert task_store.schema_version() == TASK_SCHEMA_VERSION
    # The legacy run remains readable and untouched by the migration.
    legacy = run_store.get_run("20260725T000000Z_executable_profile_abcdef12")
    assert legacy["status"] == "queued"
    assert legacy["tool"] == "executable_profile"
    with sqlite3.connect(runs_dir / "soma.sqlite3") as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"runs", "events"} <= tables
    assert set(TASK_TABLE_NAMES) <= tables


def test_task_state_vocabulary_is_controller_neutral_and_complete() -> None:
    values = {state.value for state in TaskState}
    assert values == {
        "accepted",
        "queued",
        "running",
        "awaiting_controller",
        "paused",
        "cancellation_pending",
        "recovery_pending",
        "completed",
        "failed",
        "cancelled",
        "uncertain",
    }
    forbidden = {"awaiting_chatgpt", "needs_approval", "needs_chatgpt_approval"}
    assert not (values & forbidden)
    assert not any("chatgpt" in value or "approval" in value for value in values)


def test_task_model_rejects_unknown_state_and_extra_fields() -> None:
    base = {
        "task_id": make_task_id(),
        "task_kind": "durable_command",
        "controller_request_id": "req",
        "request_hash": "b" * 64,
        "backend_kind": "soma_durable_run",
        "state": "queued",
        "created_at": "2026-07-25T00:00:00+00:00",
        "updated_at": "2026-07-25T00:00:00+00:00",
    }
    assert TaskRecord.model_validate(base).state is TaskState.QUEUED

    with pytest.raises(Exception):
        TaskRecord.model_validate({**base, "state": "needs_approval"})
    with pytest.raises(Exception):
        TaskRecord.model_validate({**base, "surprise": 1})


# ---------------------------------------------------------------------------
# 4-5: creation, backend mapping, and exact link
# ---------------------------------------------------------------------------


def test_task_creation_maps_to_one_backend_run(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)

    response = _started(manager)

    assert response["ok"] is True
    assert response["created"] is True
    assert response["task_kind"] == "durable_command"
    assert response["backend_kind"] == "soma_durable_run"
    assert response["backend_executor"] == "executable_profile"
    assert response["backend_reference"] == backend.started[0]
    assert response["state"] == "queued"
    assert backend.started == backend.reserved[:1]

    task = manager.store.get_task(response["task_id"])
    assert task.backend_ref == backend.started[0]
    assert task.objective_ref == f"run_input:{task.backend_ref}"
    assert task.workspace_ref == "sample"


def test_task_links_to_its_authoritative_durable_run(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)

    links = manager.store.list_links(response["task_id"])

    assert [link.link_type.value for link in links] == ["backend_run"]
    assert links[0].target_kind.value == "durable_run"
    assert links[0].target_id == response["backend_reference"]

    projection = manager.get_links(response["task_id"])
    assert projection["links"][0]["target_id"] == response["backend_reference"]


def test_child_task_records_typed_parent_link(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    parent = _started(manager, "req-parent")

    child = _started(manager, "req-child", parent_task_id=parent["task_id"])

    link_types = {
        link.link_type.value for link in manager.store.list_links(child["task_id"])
    }
    assert link_types == {"backend_run", "parent"}
    assert child["parent_task_id"] == parent["task_id"]


# ---------------------------------------------------------------------------
# 6-10: execution outcomes and projections
# ---------------------------------------------------------------------------


def test_successful_task_backed_execution_completes(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    ref = response["backend_reference"]

    backend.advance(ref, "running")
    running = manager.get_status(response["task_id"])
    assert running["state"] == "running"
    assert running["phase"] == "backend_running"

    backend.finish(ref, status="completed", exit_code=0)
    done = manager.get_status(response["task_id"])

    assert done["state"] == "completed"
    assert done["terminal"] is True
    assert done["phase"] == "result_published"
    assert done["result_available"] is True
    assert done["ended_at"]


def test_failed_backend_execution_maps_to_failed_task(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)

    backend.advance(response["backend_reference"], "running")
    backend.finish(response["backend_reference"], status="failed", exit_code=1)

    status = manager.get_status(response["task_id"])
    assert status["state"] == "failed"
    assert status["backend_status"] == "failed"
    assert status["result_available"] is True


def test_backend_timeout_maps_to_failed_task(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)

    backend.advance(response["backend_reference"], "running")
    backend.finish(response["backend_reference"], status="timed_out", exit_code=None)

    status = manager.get_status(response["task_id"])
    assert status["state"] == "failed"
    assert status["backend_status"] == "timed_out"


def test_status_while_backend_is_running_is_not_terminal(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    backend.advance(response["backend_reference"], "running")

    status = manager.get_status(response["task_id"])

    assert status["state"] == "running"
    assert status["terminal"] is False
    assert status["result_available"] is False
    assert status["authoritative_result_retrieval"]["tool"] == "run_query"


def test_task_result_references_the_authoritative_run_result(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    ref = response["backend_reference"]
    backend.advance(ref, "running")
    backend.finish(ref, status="completed", exit_code=0)

    result = manager.get_result(response["task_id"])

    assert result["result_authority"] == "durable_run"
    assert result["result_duplicated_into_task"] is False
    assert result["result_reference"] == ref
    assert result["result_hash"] == "a" * 64
    assert result["evidence_reference"] == f"run_terminal:{ref}"
    assert result["result_source"]["run_id"] == ref
    assert result["result_source"]["public_result_source_sha256"] == "a" * 64
    assert result["result_source"]["result_published_hash"] == "a" * 64
    assert result["authoritative_result_retrieval"] == {
        "tool": "run_query",
        "request": {"operation": "terminal", "run_id": ref},
    }
    # The task response carries no copied run result body.
    assert "stdout" not in result
    assert "stderr" not in result
    assert "result" not in result


# ---------------------------------------------------------------------------
# 11-13: idempotency
# ---------------------------------------------------------------------------


def test_same_controller_request_and_hash_returns_the_existing_task(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)

    first = _started(manager, "req-idem")
    second = _started(manager, "req-idem")

    assert second["task_id"] == first["task_id"]
    assert second["created"] is False
    assert second["idempotent_replay"] is True
    assert backend.started == [first["backend_reference"]]


def test_same_controller_request_with_different_hash_fails_explicitly(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    first = _started(manager, "req-conflict")

    conflict = _started(manager, "req-conflict", argv=["-NoProfile", "-Command", "other"])

    assert conflict["ok"] is False
    assert conflict["error_code"] == "controller_request_hash_conflict"
    assert conflict["task_id"] == first["task_id"]
    assert conflict["existing_request_hash"] != conflict["submitted_request_hash"]
    assert backend.started == [first["backend_reference"]]


def test_concurrent_duplicate_starts_launch_exactly_one_backend_run(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    barrier = threading.Barrier(4)
    responses: list[dict] = []
    lock = threading.Lock()

    def submit() -> None:
        barrier.wait()
        response = _started(manager, "req-concurrent")
        with lock:
            responses.append(response)

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(responses) == 4
    assert {response["task_id"] for response in responses} == {responses[0]["task_id"]}
    assert len(backend.started) == 1
    assert sum(1 for response in responses if response.get("created")) == 1


def test_retry_after_restart_cannot_create_a_second_backend_run(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    config, config_path = _make_config(tmp_path)
    first_manager = TaskManager(config, config_path, backend=backend)
    first = _started(first_manager, "req-restart")

    # A fresh manager models a process restart against the same durable store.
    second_manager = TaskManager(config, config_path, backend=backend)
    replay = _started(second_manager, "req-restart")

    assert replay["task_id"] == first["task_id"]
    assert len(backend.started) == 1


# ---------------------------------------------------------------------------
# 14-16: version-guarded cancellation
# ---------------------------------------------------------------------------


def test_matching_state_version_cancels_through_the_backend(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    backend.advance(response["backend_reference"], "running")
    current = manager.get_status(response["task_id"])

    cancelled = manager.cancel_task(
        response["task_id"], if_state_version=current["state_version"]
    )

    assert cancelled["ok"] is True
    assert cancelled["state"] == "cancelled"
    assert cancelled["cancellation_claimed"] is True
    assert cancelled["backend_cancellation"]["termination_confirmed"] is True
    assert backend.cancelled == [response["backend_reference"]]


def test_stale_state_version_is_rejected_with_the_current_version(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    backend.advance(response["backend_reference"], "running")
    current = manager.get_status(response["task_id"])

    stale = manager.cancel_task(
        response["task_id"], if_state_version=current["state_version"] - 1
    )

    assert stale["ok"] is False
    assert stale["error_code"] == "stale_state_version"
    assert stale["current_state_version"] == current["state_version"]
    assert backend.cancelled == []
    commands = manager.store.list_commands(response["task_id"])
    assert commands[-1].status.value == "rejected_stale_version"


def test_repeated_cancellation_is_idempotent_and_targets_nothing(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    backend.advance(response["backend_reference"], "running")
    first = manager.cancel_task(
        response["task_id"],
        if_state_version=manager.get_status(response["task_id"])["state_version"],
    )
    assert first["state"] == "cancelled"
    cancel_calls = len(backend.cancelled)

    repeat = manager.cancel_task(
        response["task_id"], if_state_version=first["state_version"]
    )

    assert repeat["ok"] is True
    assert repeat["already_terminal"] is True
    assert repeat["state"] == "cancelled"
    # A terminal task never signals the backend again, so no unrelated process
    # can be targeted by a repeated cancellation.
    assert len(backend.cancelled) == cancel_calls


def test_cancellation_is_not_claimed_before_the_backend_proves_it(
    tmp_path: Path,
) -> None:
    class PendingBackend(FakeBackend):
        def cancel(self, backend_ref: str) -> dict:
            self.cancelled.append(backend_ref)
            self.advance(backend_ref, "cancellation_pending")
            return {
                "ok": False,
                "run_id": backend_ref,
                "status": "cancellation_pending",
                "cancelled": False,
                "termination_confirmed": False,
                "reason": "Cancellation recorded; worker owns termination",
            }

    backend = PendingBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    backend.advance(response["backend_reference"], "running")

    pending = manager.cancel_task(
        response["task_id"],
        if_state_version=manager.get_status(response["task_id"])["state_version"],
    )

    assert pending["state"] == "cancellation_pending"
    assert pending["cancellation_claimed"] is False
    assert pending["terminal"] is False


def test_cancellation_without_a_backend_record_does_not_invent_success(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    backend.suppress_start = True
    manager = _manager(tmp_path, backend)
    response = _started(manager)

    result = manager.cancel_task(
        response["task_id"], if_state_version=response["state_version"]
    )

    assert result["ok"] is False
    assert result["error_code"] == "backend_run_not_found"
    assert result["state"] != "cancelled"
    assert result["cancellation_claimed"] is False


# ---------------------------------------------------------------------------
# 17-22: reconciliation and crash windows
# ---------------------------------------------------------------------------


def test_restart_while_backend_remains_active_adopts_the_running_task(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    config, config_path = _make_config(tmp_path)
    manager = TaskManager(config, config_path, backend=backend)
    response = _started(manager, "req-restart-active")
    backend.advance(response["backend_reference"], "running")

    restarted = TaskManager(config, config_path, backend=backend)
    summary = restarted.reconcile_startup()

    assert summary["ok"] is True
    assert summary["examined"] == 1
    assert summary["changed"] == 1
    task = restarted.store.get_task(response["task_id"])
    assert task.state is TaskState.RUNNING
    assert task.recovery_state.value == "none"


def test_completion_between_reconciliation_passes_is_published(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager, "req-between")
    backend.advance(response["backend_reference"], "running")
    manager.reconcile_startup()

    backend.finish(response["backend_reference"], status="completed", exit_code=0)
    second = manager.reconcile_startup()

    assert second["changed"] == 1
    task = manager.store.get_task(response["task_id"])
    assert task.state is TaskState.COMPLETED
    assert task.result_ref == response["backend_reference"]
    assert task.result_hash == "a" * 64


def test_duplicate_reconcilers_converge_without_conflicting_writes(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager, "req-dup-reconcile")
    backend.advance(response["backend_reference"], "running")

    first = manager.reconcile_startup()
    before = manager.store.get_task(response["task_id"]).state_version
    second = manager.reconcile_startup()
    after = manager.store.get_task(response["task_id"])

    assert first["ok"] is True and second["ok"] is True
    assert second["changed"] == 0
    assert after.state_version == before
    assert after.state is TaskState.RUNNING


def test_crash_after_reservation_before_backend_attachment_is_recovery_pending(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    backend.suppress_start = True  # durable run row never came into existence
    manager = _manager(tmp_path, backend)

    response = _started(manager, "req-crash-reserve")

    assert response["state"] == "recovery_pending"
    task = manager.store.get_task(response["task_id"])
    assert task.recovery_state.value == "pending"
    assert task.recovery_reason == "backend_launch_incomplete"
    # No success is invented and no second backend reference is allocated.
    assert task.backend_ref == backend.reserved[0]


def test_crash_after_backend_start_before_task_link_publication_is_repaired(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager, "req-crash-attach")
    task_id = response["task_id"]
    ref = response["backend_reference"]

    # Model the crash window: the durable run advanced but the canonical task
    # projection was never updated after the launch.
    current = manager.store.get_task(task_id)
    manager.store.conditional_update(
        task_id,
        fields={
            "state": TaskState.ACCEPTED.value,
            "phase": TaskPhase.BACKEND_RESERVED.value,
        },
        expected_state_version=current.state_version,
    )
    backend.advance(ref, "running")

    repaired = manager.reconcile_task(task_id)

    assert repaired.state is TaskState.RUNNING
    assert repaired.backend_ref == ref
    assert [
        link.target_id for link in manager.store.list_links(task_id)
    ] == [ref]


def test_result_linkage_is_repaired_when_it_was_never_published(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager, "req-linkage")
    ref = response["backend_reference"]
    backend.advance(ref, "running")
    manager.reconcile_task(response["task_id"])

    # Terminal backend result exists while the task projection is stale.
    backend.finish(ref, status="completed", exit_code=0)
    stale = manager.store.get_task(response["task_id"])
    assert stale.result_ref == ""

    repaired = manager.reconcile_task(response["task_id"])

    assert repaired.state is TaskState.COMPLETED
    assert repaired.result_ref == ref
    assert repaired.result_hash == "a" * 64
    assert repaired.evidence_ref == f"run_terminal:{ref}"


def test_inconsistent_backend_identity_becomes_uncertain(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager, "req-identity")
    backend.runs[response["backend_reference"]]["tool"] = "ssh_reviewed_script"

    reconciled = manager.reconcile_task(response["task_id"])

    assert reconciled.state is TaskState.UNCERTAIN
    assert reconciled.recovery_reason == "backend_identity_mismatch"
    assert reconciled.recovery_state.value == "unresolved"


def test_missing_backend_record_for_a_started_task_becomes_uncertain(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager, "req-missing")
    backend.advance(response["backend_reference"], "running")
    manager.reconcile_task(response["task_id"])

    backend.runs.pop(response["backend_reference"])
    reconciled = manager.reconcile_task(response["task_id"])

    assert reconciled.state is TaskState.UNCERTAIN
    assert reconciled.recovery_reason == "backend_run_record_missing"


def test_startup_reconciliation_records_failures_as_durable_evidence(
    tmp_path: Path,
) -> None:
    class BrokenBackend(FakeBackend):
        def query(self, backend_ref: str) -> BackendObservation:
            raise RuntimeError("backend query exploded")

    backend = FakeBackend()
    config, config_path = _make_config(tmp_path)
    manager = TaskManager(config, config_path, backend=backend)
    response = _started(manager, "req-broken")

    broken = TaskManager(config, config_path, backend=BrokenBackend())
    summary = broken.reconcile_startup()

    assert summary["ok"] is False
    assert summary["failures"][0]["task_id"] == response["task_id"]
    events = manager.store.list_events(response["task_id"], limit=50)
    assert any(event.stage == "startup_recovery" for event in events)


def test_one_active_task_cannot_switch_backend(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    first = _started(manager, "req-a")

    # A second task cannot claim the same durable run identity.
    with pytest.raises(sqlite3.IntegrityError):
        manager.store.reserve_task(
            task_id=make_task_id(),
            task_kind="durable_command",
            controller_request_id="req-b",
            request_hash="c" * 64,
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref=first["backend_reference"],
            backend_identity={},
        )

    # And the task's own backend reference is not a field a caller may update.
    with pytest.raises(ValueError):
        manager.store.conditional_update(
            first["task_id"],
            fields={"backend_kind": "other_engine"},
            expected_state_version=first["state_version"],
        )


def test_conflicting_request_hash_raises_from_the_store(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "runs")
    task_id = make_task_id()
    store.reserve_task(
        task_id=task_id,
        task_kind="durable_command",
        controller_request_id="req",
        request_hash="d" * 64,
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref="20260725T000000Z_executable_profile_11111111",
        backend_identity={},
    )

    with pytest.raises(TaskRequestConflict):
        store.reserve_task(
            task_id=make_task_id(),
            task_kind="durable_command",
            controller_request_id="req",
            request_hash="e" * 64,
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref="20260725T000000Z_executable_profile_22222222",
            backend_identity={},
        )


# ---------------------------------------------------------------------------
# 23-24: real durable engine mapping and legacy compatibility
# ---------------------------------------------------------------------------


def test_real_durable_engine_creates_exactly_one_run_for_one_task(
    tmp_path: Path, monkeypatch
) -> None:
    config, config_path = _make_config(tmp_path)
    monkeypatch.setattr(
        "soma.job_manager.subprocess.Popen", lambda *args, **kwargs: FakeProcess()
    )
    job_manager = JobManager(config, config_path)
    manager = TaskManager(config, config_path, job_manager=job_manager)

    response = manager.start_durable_command(
        controller_request_id="req-real",
        repo_name="sample",
        argv=["-NoProfile", "-Command", "Write-Output ok"],
        working_directory=str(Path(config.repos["sample"].path)),
    )
    replay = manager.start_durable_command(
        controller_request_id="req-real",
        repo_name="sample",
        argv=["-NoProfile", "-Command", "Write-Output ok"],
        working_directory=str(Path(config.repos["sample"].path)),
    )

    assert response["ok"] is True
    assert replay["task_id"] == response["task_id"]
    run_store = RunStore(config.resolve_runs_dir())
    runs = run_store.list_runs(limit=50)
    assert [run["run_id"] for run in runs] == [response["backend_reference"]]
    assert runs[0]["tool"] == "executable_profile"
    assert response["state"] in {"queued", "running"}


def test_legacy_direct_run_apis_are_unchanged_by_the_task_plane(
    tmp_path: Path, monkeypatch
) -> None:
    config, config_path = _make_config(tmp_path)
    monkeypatch.setattr(
        "soma.job_manager.subprocess.Popen", lambda *args, **kwargs: FakeProcess()
    )
    job_manager = JobManager(config, config_path)

    direct = job_manager.start_executable_profile(
        "sample",
        "powershell",
        ["-NoProfile", "-Command", "Write-Output legacy"],
        working_directory=str(Path(config.repos["sample"].path)),
    )

    assert direct["accepted"] is True
    run_id = direct["run_id"]
    summary = job_manager.get_run_summary(run_id)
    assert summary["ok"] is True
    status = job_manager.get_lifecycle_status(run_id)
    assert status["run_id"] == run_id
    # A legacy run has no canonical task and must remain fully readable.
    task_store = TaskStore(config.resolve_runs_dir())
    assert (
        task_store.find_by_backend_ref(BackendKind.SOMA_DURABLE_RUN.value, run_id)
        is None
    )
    assert job_manager.store.get_run(run_id)["tool"] == "executable_profile"


# ---------------------------------------------------------------------------
# 25-28: gateway contract, budgets, transport, and secret containment
# ---------------------------------------------------------------------------


def test_task_gateways_are_discoverable_with_strict_request_unions() -> None:
    async def _list() -> dict:
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        return {
            name: tools[name].to_mcp_tool().model_dump(mode="json")
            for name in ("task_query", "task_action")
        }

    actions = asyncio.run(_list())

    query_ops = set(actions["task_query"]["inputSchema"]["properties"]["operation"]["enum"])
    action_ops = set(
        actions["task_action"]["inputSchema"]["properties"]["operation"]["enum"]
    )
    assert query_ops == {
        "capabilities",
        "status",
        "result",
        "events",
        "links",
        "quarantine",
    }
    assert action_ops == {"start", "cancel", "adjudicate_quarantine"}
    for name in ("task_query", "task_action"):
        for variant in actions[name]["inputSchema"]["oneOf"]:
            assert variant["additionalProperties"] is False


def test_task_capabilities_declare_the_canonical_contract(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    capabilities = manager.capabilities()

    assert capabilities["default_backend_kind"] == "soma_durable_run"
    assert capabilities["backends"][0]["default"] is True
    assert capabilities["version_guarded_commands"] == ["cancel"]
    assert capabilities["idempotency"]["keys"] == [
        "controller_request_id",
        "request_hash",
    ]
    assert capabilities["authority"]["result"] == "durable_run_store"
    assert capabilities["schema"]["schema_version"] == TASK_SCHEMA_VERSION
    assert "needs_approval" not in json.dumps(capabilities)


def test_compact_task_projections_stay_within_their_budget(tmp_path: Path) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    response = _started(manager)
    backend.advance(response["backend_reference"], "running")
    for index in range(80):
        manager.store.append_event(
            response["task_id"],
            level=TaskEventLevel.INFO,
            stage="noise",
            message=f"event {index} " + "x" * 400,
        )

    budget = 4096
    for payload in (
        manager.get_status(response["task_id"], budget=budget),
        manager.get_result(response["task_id"], budget=budget),
        manager.get_links(response["task_id"], budget=budget),
        manager.get_events(response["task_id"], limit=500, budget=budget),
        manager.capabilities(budget=12 * 1024),
    ):
        assert payload["response_budget_bytes"] in {budget, 12 * 1024}
        assert payload["response_bytes"] == len(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        assert payload["view"] == "compact"
        assert payload["non_authoritative"] is True

    events = manager.get_events(response["task_id"], limit=500, budget=budget)
    assert events["response_bytes"] <= budget
    assert events["truncated"] is True
    assert events["has_more"] is True


def test_task_gateway_transport_populates_both_channels(tmp_path: Path) -> None:
    config, config_path = _make_config(tmp_path)
    previous_config = server._config
    previous_path = server._config_path
    server.set_config(config, config_path)

    async def call() -> object:
        async with Client(server.mcp) as client:
            return await client.call_tool(
                "task_query", {"request": {"operation": "capabilities"}}
            )

    try:
        result = asyncio.run(call())
    finally:
        if previous_config is not None:
            server.set_config(previous_config, previous_path)

    assert result.structured_content is not None
    text = "".join(
        block.text
        for block in result.content
        if getattr(block, "type", "") == "text"
    )
    assert text
    assert json.loads(text) == result.structured_content
    assert result.structured_content["default_backend_kind"] == "soma_durable_run"


def test_no_secret_material_reaches_task_records_events_or_projections(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    manager = _manager(tmp_path, backend)
    secret = "hunter2-super-secret-value"

    response = _started(
        manager,
        "req-secret",
        environment={"API_KEY": secret},
        stdin_text=f"password={secret}",
        argv=["-NoProfile", "-Command", f"Write-Output {secret}"],
    )
    task_id = response["task_id"]
    backend.advance(response["backend_reference"], "running")
    backend.finish(response["backend_reference"], status="completed", exit_code=0)

    task = manager.store.get_task(task_id)
    serialized_row = json.dumps(task.to_dict())
    events = json.dumps(
        [event.to_dict() for event in manager.store.list_events(task_id, limit=200)]
    )
    projections = json.dumps(
        [
            response,
            manager.get_status(task_id),
            manager.get_result(task_id),
            manager.get_events(task_id),
            manager.get_links(task_id),
        ]
    )

    for blob in (serialized_row, events, projections):
        assert secret not in blob
        assert "API_KEY" not in blob
    # Only the normalized hash is retained, and it still distinguishes requests.
    assert len(task.request_hash) == 64
    other = normalized_request_hash(
        normalize_durable_command_request(
            repo_name="sample", profile_id="powershell", argv=["different"]
        )
    )
    assert other != task.request_hash


def test_normalized_hash_treats_equivalent_stdin_forms_as_one_request() -> None:
    from base64 import b64encode

    text_form = normalize_durable_command_request(
        repo_name="sample", profile_id="powershell", argv=["a"], stdin_text="payload"
    )
    base64_form = normalize_durable_command_request(
        repo_name="sample",
        profile_id="powershell",
        argv=["a"],
        stdin_base64=b64encode(b"payload").decode("ascii"),
    )

    assert normalized_request_hash(text_form) == normalized_request_hash(base64_form)
    assert text_form["stdin"]["present"] is True
    assert "payload" not in json.dumps(text_form)


# ---------------------------------------------------------------------------
# isolated real local-process acceptance
# ---------------------------------------------------------------------------


def _real_powershell() -> Path:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "PowerShell"
        / "7"
        / "pwsh.exe",
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    pytest.skip("No local PowerShell executable is available")


@pytest.mark.skipif(os.name != "nt", reason="Windows local-process acceptance")
def test_real_local_command_completes_through_the_canonical_task_plane(
    tmp_path: Path,
) -> None:
    config, config_path = _make_config(tmp_path, executable=_real_powershell())
    manager = TaskManager(config, config_path)

    response = manager.start_durable_command(
        controller_request_id="req-live-acceptance",
        repo_name="sample",
        argv=["-NoProfile", "-Command", "Write-Output canonical-task-acceptance"],
        working_directory=str(Path(config.repos["sample"].path)),
        timeout_seconds=120,
    )
    assert response["ok"] is True
    task_id = response["task_id"]

    deadline = time.monotonic() + 180
    status = response
    while time.monotonic() < deadline:
        status = manager.get_status(task_id)
        if status["terminal"]:
            break
        time.sleep(0.5)

    assert status["terminal"] is True, status
    assert status["state"] == "completed", status
    result = manager.get_result(task_id)
    assert result["result_authority"] == "durable_run"
    assert result["result_reference"] == response["backend_reference"]
    assert result["result_source"]["available"] is True

    # The authoritative evidence still comes from the durable run APIs.
    job_manager = JobManager(config, config_path)
    terminal = job_manager.get_terminal_result(response["backend_reference"])
    assert terminal["run_id"] == response["backend_reference"]
    assert terminal["result"]["status"] == "completed"
    assert terminal["result"]["exit_code"] == 0
    # The canonical task references exactly this authoritative projection.
    assert result["result_source"]["public_result_source_sha256"] == (
        terminal["source_result_sha256"]
    )
