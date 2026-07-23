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


def attach_historical_child(
    store: SupervisorStore,
    jobs: FakeChildJobBackend,
    supervisor: dict,
    *,
    kind: str = "plan",
    status: str = "running",
    seed_job: bool = True,
):
    """Model a supervisor whose child predates the Codex-execution removal."""
    if seed_job:
        job = jobs.seed(kind)
        job.status = status
        run_id = job.run_id
    else:
        job = None
        run_id = f"20260428T120099Z_codex_{kind}_task_deadbeef"
    attached = store.attach_child(
        supervisor["supervisor_id"],
        run_id=run_id,
        link_type=kind,
        child_kind=kind,
        target_status="planning" if kind == "plan" else "implementing",
        metadata=dict(supervisor["metadata"]),
        expected_statuses=(supervisor["status"],),
        expected_state_version=int(supervisor["state_version"]),
    )
    assert attached is not None
    return attached, job


def advance_to_needs_input(
    engine: SupervisorEngine, store: SupervisorStore, jobs: FakeChildJobBackend
) -> dict:
    supervisor = create_supervisor(engine)
    attached, job = attach_historical_child(store, jobs, supervisor, kind="plan")
    jobs.complete(
        job.run_id, summary="plan summary", result={"files": ["README.md"]}
    )
    return engine.tick(supervisor["supervisor_id"])


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


def test_queued_tick_generates_handoff_and_moves_to_needs_external_coder(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    parked = engine.tick(supervisor["supervisor_id"])
    assert parked["status"] == "needs_external_coder"
    assert jobs.jobs == {}
    assert parked["metadata"]["active_child"] is None
    handoff = parked["metadata"]["external_coder_handoff"]
    assert handoff["kind"] == "plan"
    assert handoff["status"] == "handoff_ready"
    assert Path(handoff["handoff_json_path"]).is_file()
    assert Path(handoff["prompt_path"]).is_file()
    prompt = Path(handoff["prompt_path"]).read_text(encoding="utf-8")
    assert "Soma external-coder handoff." in prompt
    assert store.list_run_links(parked["supervisor_id"]) == []
    assert resume_prompt(store, parked["supervisor_id"]).is_file()


def test_needs_external_coder_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    parked = engine.tick(supervisor["supervisor_id"])
    again = engine.tick(supervisor["supervisor_id"])
    assert again["status"] == "needs_external_coder"
    assert again["state_version"] == parked["state_version"]
    assert (
        again["metadata"]["external_coder_handoff"]["handoff_id"]
        == parked["metadata"]["external_coder_handoff"]["handoff_id"]
    )


def test_queued_tick_emits_handoff_notification(tmp_path: Path) -> None:
    engine, store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    parked = engine.tick(supervisor["supervisor_id"])
    notes = store.list_notifications(parked["supervisor_id"], None, 10)
    assert any(
        note["kind"] == "external_coder_handoff_plan" for note in notes
    )


def test_create_plan_supervisor_records_effective_profile_metadata(
    tmp_path: Path,
) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    profile = supervisor["metadata"]["policy"]["profile"]
    assert profile["name"] == "balanced"
    assert profile["stop_on_requires_human"] is True


def test_plan_hard_stop_before_handoff_when_policy_rejected(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor_with_task(
        engine, "rewrite production deploy secrets"
    )
    stopped = engine.tick(supervisor["supervisor_id"])
    assert stopped["status"] == "needs_input"
    assert stopped["metadata"]["hard_stop"]["stage"] == "plan_policy"
    assert stopped["metadata"].get("external_coder_handoff") is None
    assert jobs.jobs == {}
    assert resume_prompt(store, stopped["supervisor_id"]).is_file()


def test_plan_hard_stop_repeated_tick_is_idempotent(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor_with_task(
        engine, "rewrite production deploy secrets"
    )
    first = engine.tick(supervisor["supervisor_id"])
    second = engine.tick(supervisor["supervisor_id"])
    assert second["status"] == "needs_input"
    assert second["state_version"] == first["state_version"]


def test_completed_historical_plan_moves_to_needs_input(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    current = advance_to_needs_input(engine, store, jobs)
    assert current["status"] == "needs_input"
    assert current["metadata"]["plan_result"]["summary"] == "plan summary"
    assert current["metadata"]["active_child"] is None


def test_historical_planning_running_tick_is_idempotent(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    attached, _job = attach_historical_child(store, jobs, supervisor, kind="plan")
    still_planning = engine.tick(supervisor["supervisor_id"])
    assert still_planning["status"] == "planning"
    assert still_planning["state_version"] == attached["state_version"]


def test_historical_planning_with_missing_child_fails_without_relaunch(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    attach_historical_child(store, jobs, supervisor, kind="plan", seed_job=False)
    failed = engine.tick(supervisor["supervisor_id"])
    assert failed["status"] == "failed"
    assert "Codex execution" in failed["error"]
    assert jobs.jobs == {}


def test_approve_plan_generates_implementation_handoff(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    current = advance_to_needs_input(engine, store, jobs)
    parked = engine.approve_plan(
        current["supervisor_id"], "approved plan", ["README.md"], ["pytest"]
    )
    assert parked["status"] == "needs_external_coder"
    handoff = parked["metadata"]["external_coder_handoff"]
    assert handoff["kind"] == "implementation"
    assert handoff["status"] == "handoff_ready"
    prompt = Path(handoff["prompt_path"]).read_text(encoding="utf-8")
    assert "approved plan" in prompt
    assert "README.md" in prompt
    assert "pytest" in prompt
    # No implementation child exists or was launched.
    assert [job.kind for job in jobs.jobs.values()] == ["plan"]
    assert parked["metadata"]["approval"]["allowed_files"] == ["README.md"]


def test_approve_plan_hard_stops_when_profile_disallows_tier_two(
    tmp_path: Path,
) -> None:
    profile = BalancedAutonomyProfile(max_implementation_tier=1)
    engine, store, jobs = make_engine_with_profile(tmp_path, profile)
    current = advance_to_needs_input(engine, store, jobs)
    stopped = engine.approve_plan(
        current["supervisor_id"], "approved plan", ["soma/server.py"], ["pytest"]
    )
    assert stopped["status"] == "needs_input"
    assert stopped["metadata"]["hard_stop"]["stage"] == "implementation_policy"
    assert stopped["metadata"].get("external_coder_handoff") is None


def test_approve_plan_hard_stops_when_tests_required_for_non_docs_changes(
    tmp_path: Path,
) -> None:
    profile = BalancedAutonomyProfile(
        max_implementation_tier=2, require_tests_for_non_docs_changes=True
    )
    engine, store, jobs = make_engine_with_profile(tmp_path, profile, "conservative")
    current = advance_to_needs_input(engine, store, jobs)
    stopped = engine.approve_plan(
        current["supervisor_id"], "edit app", ["app.py"], []
    )
    assert stopped["status"] == "needs_input"
    assert (
        "tests_required_for_non_docs_changes"
        in stopped["metadata"]["hard_stop"]["reasons"]
    )
    assert stopped["metadata"].get("external_coder_handoff") is None


def test_hard_stop_metadata_persists_after_store_reload(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor_with_task(engine, "use login credentials")
    stopped = engine.tick(supervisor["supervisor_id"])
    reloaded = SupervisorStore(tmp_path / "runs").get_supervisor(
        stopped["supervisor_id"]
    )
    assert reloaded["metadata"]["hard_stop"]["stage"] == "plan_policy"


def test_approval_only_valid_from_needs_input(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    with pytest.raises(ValueError, match="needs_input"):
        engine.approve_plan(supervisor["supervisor_id"], "plan", ["README.md"], [])


def test_historical_implementing_running_tick_is_idempotent(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    attached, _job = attach_historical_child(
        store, jobs, supervisor, kind="implementation"
    )
    still = engine.tick(supervisor["supervisor_id"])
    assert still["status"] == "implementing"
    assert still["state_version"] == attached["state_version"]


def test_completed_historical_implementation_marks_supervisor_completed(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    attached, job = attach_historical_child(
        store, jobs, supervisor, kind="implementation"
    )
    jobs.complete(job.run_id, summary="implementation done")
    completed = engine.tick(supervisor["supervisor_id"])
    assert completed["status"] == "completed"
    assert completed["summary"] == "implementation done"
    assert completed["metadata"]["implementation_lock"] is None


def test_historical_plan_failure_marks_supervisor_failed(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    _attached, job = attach_historical_child(store, jobs, supervisor, kind="plan")
    jobs.fail(job.run_id, error="plan blew up")
    failed = engine.tick(supervisor["supervisor_id"])
    assert failed["status"] == "failed"
    assert failed["error"] == "plan blew up"


def test_cancelled_historical_plan_child_marks_supervisor_cancelled(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    _attached, job = attach_historical_child(store, jobs, supervisor, kind="plan")
    jobs.cancel(job.run_id)
    cancelled = engine.tick(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"


def test_cancelled_historical_implementation_child_clears_ownership_metadata(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    _attached, job = attach_historical_child(
        store, jobs, supervisor, kind="implementation"
    )
    jobs.cancel(job.run_id)
    cancelled = engine.tick(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["metadata"]["implementation_lock"] is None


def test_cancel_active_historical_child_marks_cancelled(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    _attached, job = attach_historical_child(store, jobs, supervisor, kind="plan")
    cancelled = engine.cancel(supervisor["supervisor_id"])
    assert cancelled["status"] == "cancelled"
    assert jobs.get(job.run_id).cancel_requested is True
    assert resume_prompt(store, cancelled["supervisor_id"]).is_file()


def test_cancel_with_unowned_child_requires_manual_verification(
    tmp_path: Path,
) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    attach_historical_child(store, jobs, supervisor, kind="plan", seed_job=False)
    blocked = engine.cancel(supervisor["supervisor_id"])
    assert blocked["status"] == "needs_input"
    assert blocked["metadata"]["blocked"]["reason"] == "child_cancellation_unverified"


def test_terminal_tick_is_noop(tmp_path: Path) -> None:
    engine, store, jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    _attached, job = attach_historical_child(store, jobs, supervisor, kind="plan")
    jobs.fail(job.run_id)
    failed = engine.tick(supervisor["supervisor_id"])
    assert failed["status"] == "failed"
    again = engine.tick(supervisor["supervisor_id"])
    assert again["state_version"] == failed["state_version"]


def test_state_survives_store_reload(tmp_path: Path) -> None:
    engine, _store, _jobs = make_engine(tmp_path)
    supervisor = create_supervisor(engine)
    parked = engine.tick(supervisor["supervisor_id"])
    reloaded_store = SupervisorStore(tmp_path / "runs")
    reloaded = reloaded_store.get_supervisor(parked["supervisor_id"])
    assert reloaded["status"] == "needs_external_coder"
    assert reloaded["metadata"]["external_coder_handoff"]["handoff_id"]


def test_engine_has_no_child_launch_affordances() -> None:
    source = Path("soma/supervisor_engine.py").read_text(encoding="utf-8")
    assert "start_plan" not in source
    assert "start_implementation" not in source
    assert "_ensure_child_launched" not in source
    assert "make_run_id" not in source
