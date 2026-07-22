from __future__ import annotations

from pathlib import Path

import pytest

from soma.supervisor_engine import FakeChildJobBackend, SupervisorEngine
from soma import supervisor_resume_prompt as supervisor_resume_prompt_module
from soma.supervisor_resume_prompt import supervisor_prompt_path, write_resume_prompt
from soma.supervisor_store import SupervisorStore
from soma.policy import BalancedAutonomyProfile


def make_engine(
    tmp_path: Path,
) -> tuple[SupervisorEngine, SupervisorStore, FakeChildJobBackend]:
    store = SupervisorStore(tmp_path / "runs")
    jobs = FakeChildJobBackend()
    return SupervisorEngine(store, jobs), store, jobs


def make_engine_with_profile(
    tmp_path: Path, profile: BalancedAutonomyProfile, profile_name: str = "custom"
) -> tuple[SupervisorEngine, SupervisorStore, FakeChildJobBackend]:
    store = SupervisorStore(tmp_path / "runs")
    jobs = FakeChildJobBackend()
    return (
        SupervisorEngine(
            store, jobs, autonomy_profile=profile, profile_name=profile_name
        ),
        store,
        jobs,
    )


def create_supervisor(engine: SupervisorEngine) -> dict:
    return engine.create_plan_supervisor(
        repo_name="soma",
        objective="make a safe docs change",
        task="inspect README",
        constraints="do not edit",
    )


def create_supervisor_with_task(
    engine: SupervisorEngine, task: str, constraints: str = ""
) -> dict:
    return engine.create_plan_supervisor(
        repo_name="soma",
        objective="policy test",
        task=task,
        constraints=constraints,
    )


def active_run_id(supervisor: dict) -> str:
    return supervisor["metadata"]["active_child"]["run_id"]


def resume_prompt(store: SupervisorStore, supervisor_id: str) -> Path:
    return supervisor_prompt_path(store.runs_dir, supervisor_id)


def test_write_resume_prompt_atomically_replaces_existing_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = {
        "supervisor_id": "supervisor-1",
        "repo_name": "soma",
        "status": "completed",
        "summary": "new database-derived content",
    }
    path = supervisor_prompt_path(tmp_path, supervisor["supervisor_id"])
    path.parent.mkdir(parents=True)
    path.write_text("previous prompt", encoding="utf-8")

    original_replace = supervisor_resume_prompt_module.os.replace
    observed: dict[str, str] = {}

    def observe_replace(source: str | Path, destination: str | Path) -> None:
        observed["temporary"] = Path(source).read_text(encoding="utf-8")
        observed["existing"] = Path(destination).read_text(encoding="utf-8")
        original_replace(source, destination)

    monkeypatch.setattr(
        supervisor_resume_prompt_module.os, "replace", observe_replace
    )

    assert write_resume_prompt(tmp_path, supervisor) == path

    published = path.read_text(encoding="utf-8")
    assert observed["existing"] == "previous prompt"
    assert observed["temporary"] == published
    assert "summary: new database-derived content" in published
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_write_resume_prompt_replace_failure_preserves_existing_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = {
        "supervisor_id": "supervisor-1",
        "repo_name": "soma",
        "status": "failed",
        "error": "new database-derived error",
    }
    path = supervisor_prompt_path(tmp_path, supervisor["supervisor_id"])
    path.parent.mkdir(parents=True)
    path.write_text("previous prompt", encoding="utf-8")

    def fail_replace(_source: str | Path, _destination: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(supervisor_resume_prompt_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_resume_prompt(tmp_path, supervisor)

    assert path.read_text(encoding="utf-8") == "previous prompt"
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def advance_to_needs_input(engine: SupervisorEngine, jobs: FakeChildJobBackend) -> dict:
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.complete(
        active_run_id(planning), summary="plan summary", result={"files": ["README.md"]}
    )
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


def test_create_plan_supervisor_records_effective_profile_metadata(
    tmp_path: Path,
) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    assert supervisor["metadata"]["policy"]["profile"]["name"] == "balanced"
    assert supervisor["metadata"]["policy"]["profile"]["max_implementation_tier"] == 2


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
    prompt = resume_prompt(_store, needs_input["supervisor_id"])
    assert prompt.exists()
    assert active_run_id(
        {
            "metadata": {
                "active_child": {
                    "run_id": needs_input["metadata"]["plan_result"]["run_id"]
                }
            }
        }
    ) in prompt.read_text(encoding="utf-8")


def test_plan_hard_stop_before_child_starts_when_policy_rejected(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor_with_task(engine, "use login credentials")
    stopped = engine.tick(supervisor["supervisor_id"])
    assert stopped["status"] == "needs_input"
    assert stopped["requires_human"] is True
    assert stopped["risk_level"] == "high"
    assert stopped["policy_tier"] == 3
    assert stopped["metadata"]["hard_stop"]["stage"] == "plan_policy"
    assert "policy_rejected" in stopped["metadata"]["hard_stop"]["reasons"]
    assert len(jobs.jobs) == 0
    assert store.get_events(stopped["supervisor_id"])[-1]["stage"] == "plan_policy"
    notifications = store.list_notifications(stopped["supervisor_id"])
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "hard_stop"
    assert resume_prompt(store, stopped["supervisor_id"]).exists()


def test_plan_hard_stop_repeated_tick_is_idempotent(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor_with_task(engine, "use login credentials")
    stopped = engine.tick(supervisor["supervisor_id"])
    event_count = len(store.get_events(stopped["supervisor_id"], limit=100))
    again = engine.tick(stopped["supervisor_id"])
    assert again["status"] == "needs_input"
    assert len(jobs.jobs) == 0
    assert len(store.get_events(stopped["supervisor_id"], limit=100)) == event_count
    assert len(store.list_notifications(stopped["supervisor_id"])) == 1


def test_approve_plan_starts_fake_implementation(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    assert implementing["status"] == "implementing"
    assert implementing["metadata"]["active_child"]["kind"] == "implementation"
    ownership = implementing["metadata"]["implementation_lock"]
    assert ownership["authority"] == "operation_locks"
    assert ownership["repo_name"] == "soma"
    assert ownership["run_id"] == active_run_id(implementing)
    assert ownership["lease_generation"] == 1
    assert len(jobs.jobs) == 2


def test_balanced_profile_preserves_supervisor_happy_path(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "edit app", ["app.py"], []
    )
    assert implementing["status"] == "implementing"
    assert implementing["metadata"]["implementation_lock"]["authority"] == "operation_locks"
    jobs.complete(active_run_id(implementing), summary="done")
    completed = engine.tick(needs_input["supervisor_id"])
    assert completed["status"] == "completed"


def test_approval_blocked_when_shared_operation_lock_is_busy(
    tmp_path: Path, monkeypatch
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)

    def refuse_implementation(*args, **kwargs) -> dict:
        return {
            "run_id": "",
            "accepted": False,
            "status": "refused",
            "reason": "repository busy",
        }

    monkeypatch.setattr(jobs, "start_implementation", refuse_implementation)
    blocked = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    assert blocked["status"] == "needs_input"
    blocked_reason = blocked["metadata"]["blocked"]
    assert blocked_reason["reason"] == "repository_operation_lock_unavailable"
    assert blocked_reason["launch_reason"] == "repository busy"
    assert blocked["metadata"]["active_child"] is None
    assert blocked["metadata"]["implementation_lock"] is None
    assert len(jobs.jobs) == 1
    notifications = store.list_notifications(blocked["supervisor_id"])
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "blocked_by_lock"
    assert "repository_operation_lock_unavailable" in resume_prompt(
        store, blocked["supervisor_id"]
    ).read_text(encoding="utf-8")


def test_approve_plan_hard_stops_before_lock_when_profile_disallows_tier_two(
    tmp_path: Path,
) -> None:
    profile = BalancedAutonomyProfile(max_implementation_tier=1)
    engine, store, jobs = make_engine_with_profile(tmp_path, profile, "conservative")
    needs_input = advance_to_needs_input(engine, jobs)
    stopped = engine.approve_plan(
        needs_input["supervisor_id"], "edit app", ["app.py"], ["python -m pytest"]
    )
    assert stopped["status"] == "needs_input"
    assert stopped["policy_tier"] == 2
    assert stopped["risk_level"] == "medium"
    assert stopped["requires_human"] is False
    assert stopped["metadata"]["hard_stop"]["stage"] == "implementation_policy"
    assert (
        "implementation_tier_exceeds_profile"
        in stopped["metadata"]["hard_stop"]["reasons"]
    )
    assert store.operation_locks.list_locks("soma") == []
    assert len(jobs.jobs) == 1
    assert store.list_notifications(stopped["supervisor_id"])[0]["kind"] == "hard_stop"


def test_approve_plan_hard_stops_when_tests_required_for_non_docs_changes(
    tmp_path: Path,
) -> None:
    profile = BalancedAutonomyProfile(
        max_implementation_tier=2, require_tests_for_non_docs_changes=True
    )
    engine, store, jobs = make_engine_with_profile(tmp_path, profile, "conservative")
    needs_input = advance_to_needs_input(engine, jobs)
    stopped = engine.approve_plan(
        needs_input["supervisor_id"], "edit app", ["app.py"], []
    )
    assert stopped["status"] == "needs_input"
    assert (
        "tests_required_for_non_docs_changes"
        in stopped["metadata"]["hard_stop"]["reasons"]
    )
    assert store.operation_locks.list_locks("soma") == []
    assert len(jobs.jobs) == 1


def test_hard_stop_metadata_persists_after_store_reload(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor_with_task(engine, "use login credentials")
    stopped = engine.tick(supervisor["supervisor_id"])
    reloaded = SupervisorStore(tmp_path / "runs").get_supervisor(
        stopped["supervisor_id"]
    )
    assert reloaded["metadata"]["hard_stop"]["stage"] == "plan_policy"
    assert reloaded["requires_human"] is True


def test_approval_only_valid_from_needs_input(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    with pytest.raises(ValueError, match="needs_input"):
        engine.approve_plan(supervisor["supervisor_id"], "approved", ["README.md"], [])


def test_implementing_running_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    again = engine.tick(needs_input["supervisor_id"])
    assert again["status"] == "implementing"
    assert active_run_id(again) == active_run_id(implementing)
    assert len(jobs.jobs) == 2


def test_implementing_queued_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    jobs.get(active_run_id(implementing)).status = "queued"
    again = engine.tick(needs_input["supervisor_id"])
    assert again["status"] == "implementing"
    assert active_run_id(again) == active_run_id(implementing)


def test_completed_implementation_marks_supervisor_completed(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    jobs.complete(
        active_run_id(implementing),
        summary="implementation summary",
        result={"changed_files": []},
    )
    completed = engine.tick(needs_input["supervisor_id"])
    assert completed["status"] == "completed"
    assert completed["summary"] == "implementation summary"
    assert completed["metadata"]["implementation_result"]["changed_files"] == []
    assert completed["metadata"]["implementation_lock"] is None
    assert _store.operation_locks.list_locks("soma") == []
    notifications = _store.list_notifications(completed["supervisor_id"])
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "completed"
    assert "status: completed" in resume_prompt(
        _store, completed["supervisor_id"]
    ).read_text(encoding="utf-8")


def test_plan_failure_marks_supervisor_failed(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.fail(active_run_id(planning), error="plan failed")
    failed = engine.tick(supervisor["supervisor_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "plan failed"
    assert _store.list_notifications(failed["supervisor_id"])[0]["kind"] == "failed"
    assert "status: failed" in resume_prompt(_store, failed["supervisor_id"]).read_text(
        encoding="utf-8"
    )


def test_cancelled_plan_child_marks_supervisor_cancelled(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    jobs.cancel(active_run_id(planning))
    cancelled = engine.tick(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert "status: cancelled" in resume_prompt(
        _store, cancelled["supervisor_id"]
    ).read_text(encoding="utf-8")


def test_implementation_failure_marks_supervisor_failed(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    jobs.fail(active_run_id(implementing), error="implementation failed")
    failed = engine.tick(needs_input["supervisor_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "implementation failed"
    assert failed["metadata"]["implementation_lock"] is None
    assert _store.operation_locks.list_locks("soma") == []


def test_cancelled_implementation_child_clears_ownership_metadata(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    jobs.cancel(active_run_id(implementing))
    cancelled = engine.tick(needs_input["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["metadata"]["implementation_lock"] is None
    assert store.operation_locks.list_locks("soma") == []


def test_cancel_active_plan_marks_cancelled(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    cancelled = engine.cancel(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert jobs.get(active_run_id(planning)).status == "cancelled"
    assert (
        _store.list_notifications(cancelled["supervisor_id"])[0]["kind"] == "cancelled"
    )
    assert resume_prompt(_store, cancelled["supervisor_id"]).exists()


def test_cancel_active_implementation_marks_cancelled(tmp_path: Path) -> None:
    engine, _store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    cancelled = engine.cancel(needs_input["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert jobs.get(active_run_id(implementing)).status == "cancelled"
    assert cancelled["metadata"]["implementation_lock"] is None
    assert _store.operation_locks.list_locks("soma") == []


def test_cancel_with_unowned_child_requires_manual_verification(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    run_id = active_run_id(planning)
    del jobs.jobs[run_id]

    blocked = engine.cancel(supervisor["supervisor_id"])

    assert blocked["status"] == "needs_input"
    assert blocked["ended_at"] is None
    assert blocked["metadata"]["active_child"]["run_id"] == run_id
    assert blocked["metadata"]["blocked"]["reason"] == "child_cancellation_unverified"
    assert store.get_events(supervisor["supervisor_id"], limit=1)[0]["stage"] == "cancellation_unverified"
    assert resume_prompt(store, supervisor["supervisor_id"]).exists()


def test_reloaded_implementation_keeps_same_child_ownership(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    run_id = active_run_id(implementing)

    reloaded = SupervisorEngine(SupervisorStore(tmp_path / "runs"), jobs).tick(
        needs_input["supervisor_id"]
    )

    assert reloaded["status"] == "implementing"
    assert active_run_id(reloaded) == run_id
    assert reloaded["metadata"]["implementation_lock"] == implementing["metadata"][
        "implementation_lock"
    ]
    assert list(jobs.jobs).count(run_id) == 1
    assert store.get_supervisor(needs_input["supervisor_id"])["status"] == "implementing"


def test_terminal_tick_is_noop(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    needs_input = advance_to_needs_input(engine, jobs)
    implementing = engine.approve_plan(
        needs_input["supervisor_id"], "approved", ["README.md"], []
    )
    jobs.complete(active_run_id(implementing), summary="done")
    completed = engine.tick(needs_input["supervisor_id"])
    event_count = len(store.get_events(needs_input["supervisor_id"], limit=100))
    prompt = resume_prompt(store, needs_input["supervisor_id"])
    before_mtime = prompt.stat().st_mtime_ns
    again = engine.tick(needs_input["supervisor_id"])
    assert again["status"] == "completed"
    assert again["summary"] == completed["summary"]
    assert len(store.get_events(needs_input["supervisor_id"], limit=100)) == event_count
    assert prompt.stat().st_mtime_ns == before_mtime


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


def test_reserved_plan_child_relaunches_with_same_run_id(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    run_id = "20260428T120001Z_codex_plan_task_12345678"
    attached = store.attach_child(
        supervisor["supervisor_id"],
        run_id=run_id,
        link_type="plan",
        child_kind="plan",
        target_status="planning",
        metadata=supervisor["metadata"],
        expected_statuses=("queued",),
        expected_state_version=int(supervisor["state_version"]),
        started_at="2026-04-28T12:00:00+00:00",
    )
    assert attached is not None
    assert attached["metadata"]["active_child"]["launch_state"] == "reserved"

    resumed = engine.tick(supervisor["supervisor_id"])

    assert active_run_id(resumed) == run_id
    assert resumed["metadata"]["active_child"]["launch_state"] == "launched"
    assert list(jobs.jobs) == [run_id]
    assert [link["run_id"] for link in store.list_run_links(supervisor["supervisor_id"])] == [run_id]


def test_existing_reserved_plan_child_is_adopted_without_duplicate_launch(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    run_id = "20260428T120001Z_codex_plan_task_87654321"
    attached = store.attach_child(
        supervisor["supervisor_id"],
        run_id=run_id,
        link_type="plan",
        child_kind="plan",
        target_status="planning",
        metadata=supervisor["metadata"],
        expected_statuses=("queued",),
        expected_state_version=int(supervisor["state_version"]),
        started_at="2026-04-28T12:00:00+00:00",
    )
    assert attached is not None
    jobs.start_plan(
        "soma",
        "inspect README",
        "do not edit",
        reserved_run_id=run_id,
    )

    resumed = engine.tick(supervisor["supervisor_id"])

    assert active_run_id(resumed) == run_id
    assert resumed["metadata"]["active_child"]["launch_state"] == "launched"
    assert list(jobs.jobs) == [run_id]


def test_stale_plan_completion_cannot_emit_duplicate_terminal_effects(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    planning = engine.tick(supervisor["supervisor_id"])
    stale_planning = dict(planning)
    stale_planning["metadata"] = dict(planning["metadata"])
    jobs.complete(active_run_id(planning), summary="done")

    completed = engine.tick(supervisor["supervisor_id"])
    event_count = len(store.get_events(supervisor["supervisor_id"], limit=100))
    stale_result = engine._advance_plan(stale_planning)

    assert completed["status"] == "needs_input"
    assert stale_result["status"] == "needs_input"
    assert len(store.get_events(supervisor["supervisor_id"], limit=100)) == event_count
