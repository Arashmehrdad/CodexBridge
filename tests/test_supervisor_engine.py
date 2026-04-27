from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.supervisor_engine import FakeChildJobBackend, SupervisorEngine
from codexbridge.supervisor_store import SupervisorStore


def make_engine(tmp_path: Path) -> tuple[SupervisorEngine, SupervisorStore, FakeChildJobBackend]:
    store = SupervisorStore(tmp_path / "runs")
    jobs = FakeChildJobBackend()
    return SupervisorEngine(store, jobs), store, jobs


def create_supervisor(engine: SupervisorEngine) -> dict:
    return engine.create_plan_supervisor(
        repo_name="codexbridge",
        objective="make a safe docs change",
        task="inspect README",
        constraints="do not edit",
    )


def active_run_id(supervisor: dict) -> str:
    return supervisor["metadata"]["active_child"]["run_id"]


def advance_to_needs_input(engine: SupervisorEngine, jobs: FakeChildJobBackend) -> dict:
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.complete(active_run_id(planning), summary="plan summary", result={"files": ["README.md"]})
    return engine.tick(supervisor["supervisor_id"])


def test_queued_tick_starts_fake_plan_and_moves_to_planning(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    assert planning["status"] == "planning"
    assert len(jobs.jobs) == 1
    assert planning["metadata"]["active_child"]["kind"] == "plan"
    assert planning["metadata"]["active_child"]["run_id"]
    links = _store.list_run_links(planning["supervisor_id"])
    assert links[0]["run_id"] == active_run_id(planning)


def test_planning_running_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    again = engine.tick(supervisor["supervisor_id"])
    assert again["status"] == "planning"
    assert active_run_id(again) == active_run_id(planning)
    assert len(jobs.jobs) == 1


def test_planning_queued_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.get(active_run_id(planning)).status = "queued"
    again = engine.tick(supervisor["supervisor_id"])
    assert again["status"] == "planning"
    assert active_run_id(again) == active_run_id(planning)


def test_completed_plan_moves_to_needs_input(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    assert needs_input["status"] == "needs_input"
    assert needs_input["summary"] == "plan summary"
    assert needs_input["metadata"]["plan_result"]["files"] == ["README.md"]


def test_approve_plan_starts_fake_implementation(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    assert implementing["status"] == "implementing"
    assert implementing["metadata"]["active_child"]["kind"] == "implementation"
    assert implementing["metadata"]["implementation_lock"]["repo_name"] == "codexbridge"
    assert len(jobs.jobs) == 2


def test_approval_blocked_when_repo_lock_exists(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    existing = store.acquire_repo_lock("codexbridge", owner_id="other", reason="busy")
    assert existing is not None
    blocked = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    assert blocked["status"] == "needs_input"
    assert blocked["metadata"]["blocked"]["reason"] == "repo_write_lock_unavailable"
    assert blocked["metadata"]["active_child"] is None
    assert len(jobs.jobs) == 1


def test_approval_only_valid_from_needs_input(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    with pytest.raises(ValueError, match="needs_input"):
        engine.approve_plan(supervisor["supervisor_id"], "approved", ["README.md"], [])


def test_implementing_running_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    again = engine.tick(needs_input["supervisor_id"])
    assert again["status"] == "implementing"
    assert active_run_id(again) == active_run_id(implementing)
    assert len(jobs.jobs) == 2


def test_implementing_queued_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    jobs.get(active_run_id(implementing)).status = "queued"
    again = engine.tick(needs_input["supervisor_id"])
    assert again["status"] == "implementing"
    assert active_run_id(again) == active_run_id(implementing)


def test_completed_implementation_marks_supervisor_completed(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    jobs.complete(active_run_id(implementing), summary="implementation summary", result={"changed_files": []})
    completed = engine.tick(needs_input["supervisor_id"])
    assert completed["status"] == "completed"
    assert completed["summary"] == "implementation summary"
    assert completed["metadata"]["implementation_result"]["changed_files"] == []
    assert completed["metadata"]["implementation_lock"] is None
    assert _store.get_repo_lock("codexbridge") is None


def test_plan_failure_marks_supervisor_failed(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.fail(active_run_id(planning), error="plan failed")
    failed = engine.tick(supervisor["supervisor_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "plan failed"


def test_cancelled_plan_child_marks_supervisor_cancelled(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.cancel(active_run_id(planning))
    cancelled = engine.tick(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"


def test_implementation_failure_marks_supervisor_failed(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    jobs.fail(active_run_id(implementing), error="implementation failed")
    failed = engine.tick(needs_input["supervisor_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "implementation failed"
    assert _store.get_repo_lock("codexbridge") is None


def test_cancelled_implementation_child_releases_lock(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    jobs.cancel(active_run_id(implementing))
    cancelled = engine.tick(needs_input["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert store.get_repo_lock("codexbridge") is None


def test_cancel_active_plan_marks_cancelled(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    cancelled = engine.cancel(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert jobs.get(active_run_id(planning)).status == "cancelled"


def test_cancel_active_implementation_marks_cancelled(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    cancelled = engine.cancel(needs_input["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert jobs.get(active_run_id(implementing)).status == "cancelled"
    assert _store.get_repo_lock("codexbridge") is None


def test_terminal_tick_is_noop(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(needs_input["supervisor_id"], "approved", ["README.md"], [])
    jobs.complete(active_run_id(implementing), summary="done")
    completed = engine.tick(needs_input["supervisor_id"])
    event_count = len(store.get_events(needs_input["supervisor_id"], limit=100))
    again = engine.tick(needs_input["supervisor_id"])
    assert again["status"] == "completed"
    assert again["summary"] == completed["summary"]
    assert len(store.get_events(needs_input["supervisor_id"], limit=100)) == event_count


def test_state_survives_store_reload(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])

    reloaded_store = SupervisorStore(tmp_path / "runs")
    reloaded_engine = SupervisorEngine(reloaded_store, jobs)
    jobs.complete(active_run_id(planning), summary="reloaded plan")
    needs_input = reloaded_engine.tick(supervisor["supervisor_id"])
    assert needs_input["status"] == "needs_input"
    assert needs_input["summary"] == "reloaded plan"
    assert needs_input["metadata"]["plan_result"]["run_id"] == active_run_id(planning)
