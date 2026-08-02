"""V3-1A central non-terminal controller-wait transition."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import soma.worker_substrate.transitions as transitions_module
from soma.operation_locks import OperationLockStore
from soma.run_public_result import NormalizedOutcome, normalized_outcome
from soma.run_publication import materialize_public_result
from soma.run_store import NON_TERMINAL_WAITING_STATUSES, TERMINAL_STATUSES, RunStore
from soma.tasks.models import (
    TaskCommandKind,
    TaskCommandStatus,
    TaskLinkTargetKind,
    TaskLinkType,
    TaskPhase,
    TaskState,
)
from soma.tasks.store import TaskStore
from soma.worker_substrate import (
    CanonicalBindingMismatch,
    CheckpointExpiryDisposition,
    InteractionCoordinator,
    InteractionTransitionPolicy,
    MessageClass,
    ResumeTransitionConflict,
    SessionBindingDisposition,
    TransportAttemptState,
    WaitTransitionConflict,
    WorkerSubstrateStore,
)

from test_worker_substrate_foundation import (
    DEFAULT_RUN_ID,
    PROJECT_ID,
    RESOURCE_ID,
    _bind,
    _make_task,
)


DEADLINE = "2035-08-02T19:00:00+00:00"
STARTED_AT = "2026-08-02T18:00:00+00:00"


@pytest.fixture()
def waiting_fixture(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    task_id = _make_task(
        task_store,
        controller_request_id="wait-transition-primary",
        run_id=DEFAULT_RUN_ID,
    )
    substrate = WorkerSubstrateStore(runs_dir)
    binding, _created = _bind(substrate, task_id)
    run_store = RunStore(runs_dir)

    task = task_store.get_task(task_id)
    running_task = task_store.conditional_update(
        task_id,
        fields={
            "state": TaskState.RUNNING.value,
            "phase": TaskPhase.BACKEND_RUNNING.value,
            "started_at": STARTED_AT,
        },
        expected_state_version=task.state_version,
        expected_states=(TaskState.ACCEPTED.value,),
    )
    assert running_task is not None

    run = run_store.get_run(DEFAULT_RUN_ID)
    running_run = run_store.conditional_update(
        DEFAULT_RUN_ID,
        fields={
            "status": "running",
            "current_phase": "backend_running",
            "started_at": STARTED_AT,
            "heartbeat_at": STARTED_AT,
            "worker_pid": 54321,
            "worker_identity": "54321:windows:1785693600000000000",
            "worker_lease_token": "worker-lease-token",
            "lease_generation": 1,
            "worker_claimed_at": STARTED_AT,
        },
        expected_statuses=(str(run["status"]),),
        expected_state_version=int(run["state_version"]),
    )
    assert running_run is not None

    locks = OperationLockStore(runs_dir)
    acquired = locks.acquire(
        repo_name="soma",
        tool="executable_profile",
        normalized_input={"task_id": task_id, "run_id": DEFAULT_RUN_ID},
        run_id=DEFAULT_RUN_ID,
        owner_pid=12345,
        owner_token="wait-owner-token",
        lease_generation=1,
    )
    assert acquired.acquired is True

    policy = InteractionTransitionPolicy(runs_dir)
    return {
        "runs_dir": runs_dir,
        "policy": policy,
        "task_store": policy.task_store,
        "run_store": policy.run_store,
        "substrate": policy.substrate_store,
        "locks": locks,
        "task_id": task_id,
        "binding": binding,
    }


def _enter(fixture, **overrides):
    task = fixture["task_store"].get_task(fixture["task_id"])
    run = fixture["run_store"].get_run(DEFAULT_RUN_ID)
    request = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": fixture["task_id"],
        "run_id": DEFAULT_RUN_ID,
        "session_binding_id": fixture["binding"].session_binding_id,
        "idempotency_key": "wait-request-1",
        "expected_task_state_version": task.state_version,
        "expected_run_state_version": run["state_version"],
        "deadline_at": DEADLINE,
        "policy_owner": "controller:chatgpt",
        "prompt": "Choose the bounded continuation",
        "expected_input_schema": {"type": "string", "enum": ["continue", "stop"]},
        "context_ref": "evidence:controller-question-1",
    }
    request.update(overrides)
    return fixture["policy"].enter_waiting(**request)


def _reserve_input(waiting_fixture, **message_overrides):
    waiting = _enter(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    coordinator = InteractionCoordinator(waiting_fixture["runs_dir"])
    request = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": waiting_fixture["task_id"],
        "run_id": DEFAULT_RUN_ID,
        "session_binding_id": waiting_fixture["binding"].session_binding_id,
        "command_kind": TaskCommandKind.SUPPLY_INPUT,
        "idempotency_key": "supply-input-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "continue",
        "requested_state_version": task.state_version,
        "message_class": MessageClass.DECISION,
        "checkpoint_id": waiting.checkpoint.checkpoint_id,
    }
    request.update(message_overrides)
    return waiting, coordinator.reserve(**request)


def _wait_and_acknowledge(waiting_fixture, **message_overrides):
    waiting, reservation = _reserve_input(waiting_fixture, **message_overrides)
    attempt, created = waiting_fixture["substrate"].claim_transport_attempt(
        reservation.message.message_id,
        claimer_id="sender:deterministic-stand-in",
    )
    assert created is True
    acknowledged = waiting_fixture["substrate"].record_transport_attempt(
        attempt.attempt_id,
        state=TransportAttemptState.ACKNOWLEDGED,
        reason="deterministic stand-in accepted exact input",
        evidence_ref="transport_ack:stand-in:1",
    )
    return waiting, reservation, acknowledged


def test_waiting_is_distinct_from_historical_terminal_needs_input() -> None:
    assert "needs_input" in TERMINAL_STATUSES
    assert "awaiting_controller" not in TERMINAL_STATUSES
    assert NON_TERMINAL_WAITING_STATUSES == frozenset({"awaiting_controller"})


def test_enter_waiting_atomically_preserves_identity_lock_and_nonterminal_state(
    waiting_fixture,
):
    before_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    before_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    before_result = dict(before_run["result"])
    before_publication = {
        key: before_run[key]
        for key in (
            "result_publication_status",
            "result_published_hash",
            "result_published_at",
            "public_result_status",
            "public_result_source_sha256",
        )
    }

    result = _enter(
        waiting_fixture,
        expected_task_state_version=before_task.state_version,
        expected_run_state_version=before_run["state_version"],
    )

    assert result.created is True
    assert result.task.task_id == before_task.task_id
    assert result.task.backend_ref == DEFAULT_RUN_ID
    assert result.task.state is TaskState.AWAITING_CONTROLLER
    assert result.task.phase is TaskPhase.AWAITING_CONTROLLER
    assert result.task.state_version == before_task.state_version + 1
    assert result.task.checkpoint_ref == result.checkpoint.checkpoint_id

    assert result.run["run_id"] == DEFAULT_RUN_ID
    assert result.run["status"] == "awaiting_controller"
    assert result.run["current_phase"] == "awaiting_controller"
    assert result.run["requires_human"] is True
    assert result.run["state_version"] == before_run["state_version"] + 1
    assert result.run["ended_at"] is None
    assert result.run["result"] == before_result == {}
    assert {
        key: result.run[key] for key in before_publication
    } == before_publication
    assert normalized_outcome(result.run, result.run["result"]) is NormalizedOutcome.PENDING

    assert result.checkpoint.status.value == "open"
    assert result.checkpoint.required_state_version == result.task.state_version
    assert result.deadline.deadline_at == DEADLINE
    assert result.deadline.session_binding_id == (
        waiting_fixture["binding"].session_binding_id
    )

    lock = waiting_fixture["locks"].find_lock("soma", DEFAULT_RUN_ID)
    assert lock is not None
    assert lock["run_id"] == DEFAULT_RUN_ID

    with pytest.raises(ValueError, match="Run is not terminal"):
        materialize_public_result(waiting_fixture["run_store"], DEFAULT_RUN_ID)

    task_events = waiting_fixture["task_store"].list_events(
        waiting_fixture["task_id"], limit=20
    )
    run_events = waiting_fixture["run_store"].get_events(DEFAULT_RUN_ID, limit=20)
    assert task_events[-1].stage == "awaiting_controller"
    assert run_events[-1]["stage"] == "awaiting_controller"
    assert task_events[-1].data["contract_hash"] == result.contract_hash
    assert run_events[-1]["data"]["contract_hash"] == result.contract_hash


def test_identical_replay_returns_the_same_checkpoint_without_new_events(
    waiting_fixture,
):
    before_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    before_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    first = _enter(
        waiting_fixture,
        expected_task_state_version=before_task.state_version,
        expected_run_state_version=before_run["state_version"],
    )
    task_event_count = len(
        waiting_fixture["task_store"].list_events(waiting_fixture["task_id"], limit=50)
    )
    run_event_count = len(
        waiting_fixture["run_store"].get_events(DEFAULT_RUN_ID, limit=50)
    )

    replay = _enter(
        waiting_fixture,
        expected_task_state_version=before_task.state_version,
        expected_run_state_version=before_run["state_version"],
    )

    assert replay.created is False
    assert replay.checkpoint.checkpoint_id == first.checkpoint.checkpoint_id
    assert replay.contract_hash == first.contract_hash
    assert len(
        waiting_fixture["task_store"].list_events(waiting_fixture["task_id"], limit=50)
    ) == task_event_count
    assert len(
        waiting_fixture["run_store"].get_events(DEFAULT_RUN_ID, limit=50)
    ) == run_event_count


def test_concurrent_identical_wait_requests_converge_on_one_checkpoint(
    waiting_fixture,
):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                _enter,
                waiting_fixture,
                expected_task_state_version=task.state_version,
                expected_run_state_version=run["state_version"],
            )
            for _index in range(2)
        ]
    results = [future.result() for future in futures]

    assert sorted(item.created for item in results) == [False, True]
    assert len({item.checkpoint.checkpoint_id for item in results}) == 1
    with waiting_fixture["task_store"]._read() as conn:
        checkpoint_count = conn.execute(
            "SELECT COUNT(*) FROM task_checkpoints WHERE task_id = ?",
            (waiting_fixture["task_id"],),
        ).fetchone()[0]
        deadline_count = conn.execute(
            "SELECT COUNT(*) FROM worker_checkpoint_deadlines"
        ).fetchone()[0]
    assert checkpoint_count == 1
    assert deadline_count == 1


def test_conflicting_replay_is_explicit_and_preserves_original_wait(waiting_fixture):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    original = _enter(
        waiting_fixture,
        expected_task_state_version=task.state_version,
        expected_run_state_version=run["state_version"],
    )

    with pytest.raises(WaitTransitionConflict, match="idempotent wait replay"):
        _enter(
            waiting_fixture,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
            prompt="A conflicting prompt",
        )

    current = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    assert current.checkpoint_ref == original.checkpoint.checkpoint_id


def test_different_wait_request_cannot_create_a_second_open_checkpoint(
    waiting_fixture,
):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    _enter(
        waiting_fixture,
        expected_task_state_version=task.state_version,
        expected_run_state_version=run["state_version"],
    )

    with pytest.raises(WaitTransitionConflict, match="task must be running"):
        _enter(
            waiting_fixture,
            idempotency_key="wait-request-2",
            expected_task_state_version=task.state_version + 1,
            expected_run_state_version=run["state_version"] + 1,
        )

    with waiting_fixture["task_store"]._read() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM task_checkpoints WHERE task_id = ?",
            (waiting_fixture["task_id"],),
        ).fetchone()[0]
    assert count == 1


def test_wrong_session_or_project_scope_rolls_back_without_checkpoint(waiting_fixture):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    with pytest.raises(CanonicalBindingMismatch):
        _enter(
            waiting_fixture,
            session_binding_id="wsession_20260802T000000Z_000000000000",
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )
    with pytest.raises(CanonicalBindingMismatch):
        _enter(
            waiting_fixture,
            project_id="proj_99999999-9999-9999-9999-999999999999",
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )

    current_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    current_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    assert current_task.state is TaskState.RUNNING
    assert current_run["status"] == "running"
    with waiting_fixture["task_store"]._read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_checkpoints").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM worker_checkpoint_deadlines"
            ).fetchone()[0]
            == 0
        )


def test_failure_after_checkpoint_creation_rolls_back_every_authority(
    waiting_fixture, monkeypatch
):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    def fail_run_update(*_args, **_kwargs):
        raise RuntimeError("simulated run transition failure")

    monkeypatch.setattr(
        waiting_fixture["policy"].run_store,
        "conditional_update_in_connection",
        fail_run_update,
    )
    with pytest.raises(RuntimeError, match="simulated run transition failure"):
        _enter(
            waiting_fixture,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )

    current_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    current_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    assert current_task.state is TaskState.RUNNING
    assert current_task.state_version == task.state_version
    assert current_run["status"] == "running"
    assert current_run["state_version"] == run["state_version"]
    with waiting_fixture["task_store"]._read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_checkpoints").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM worker_checkpoint_deadlines"
            ).fetchone()[0]
            == 0
        )
        assert conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert waiting_fixture["locks"].find_lock("soma", DEFAULT_RUN_ID) is not None


def test_stale_versions_and_terminal_result_evidence_fail_closed(waiting_fixture):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    with pytest.raises(WaitTransitionConflict, match="task state version changed"):
        _enter(
            waiting_fixture,
            expected_task_state_version=task.state_version + 1,
            expected_run_state_version=run["state_version"],
        )

    waiting_fixture["run_store"].update_run(
        DEFAULT_RUN_ID,
        result_json={"status": "completed", "summary": "impossible running result"},
    )
    with pytest.raises(WaitTransitionConflict, match="terminal result evidence"):
        _enter(
            waiting_fixture,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )


def test_historical_needs_input_run_is_not_reinterpreted(waiting_fixture):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    waiting_fixture["run_store"].update_run(
        DEFAULT_RUN_ID,
        status="needs_input",
        current_phase="result",
        ended_at="2026-08-02T18:30:00+00:00",
    )

    with pytest.raises(WaitTransitionConflict, match="run must be running"):
        _enter(
            waiting_fixture,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )
    assert waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)["status"] == (
        "needs_input"
    )


def test_acknowledged_input_resumes_the_same_task_run_session_and_lock(
    waiting_fixture,
):
    _waiting, reservation, acknowledged = _wait_and_acknowledge(waiting_fixture)
    waiting_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    waiting_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    identity = {
        key: waiting_run[key]
        for key in (
            "worker_pid",
            "worker_identity",
            "worker_lease_token",
            "lease_generation",
            "launcher_pid",
            "launcher_identity",
        )
    }

    resumed = waiting_fixture["policy"].resume_after_acknowledgement(
        message_id=reservation.message.message_id,
        expected_task_state_version=waiting_task.state_version,
        expected_run_state_version=waiting_run["state_version"],
    )

    assert resumed.created is True
    assert resumed.task.task_id == waiting_task.task_id
    assert resumed.task.backend_ref == DEFAULT_RUN_ID
    assert resumed.task.state is TaskState.RUNNING
    assert resumed.task.phase is TaskPhase.BACKEND_RUNNING
    assert resumed.task.checkpoint_ref == ""
    assert resumed.task.state_version == waiting_task.state_version + 1
    assert resumed.run["run_id"] == DEFAULT_RUN_ID
    assert resumed.run["status"] == "running"
    assert resumed.run["current_phase"] == "backend_running"
    assert resumed.run["requires_human"] is False
    assert resumed.run["state_version"] == waiting_run["state_version"] + 1
    assert resumed.run["ended_at"] is None
    assert resumed.run["result"] == {}
    assert resumed.run["result_publication_status"] == "not_published"
    assert {key: resumed.run[key] for key in identity} == identity
    assert resumed.checkpoint.status.value == "resolved"
    assert resumed.message_id == reservation.message.message_id
    assert resumed.attempt_id == acknowledged.attempt_id
    assert resumed.acknowledgement_evidence_ref == "transport_ack:stand-in:1"

    command = waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    )[-1]
    assert command.command_id == reservation.command.command_id
    assert command.status is TaskCommandStatus.COMPLETED
    assert waiting_fixture["locks"].find_lock("soma", DEFAULT_RUN_ID) is not None
    assert len(
        waiting_fixture["substrate"].list_transport_attempts(
            message_id=reservation.message.message_id
        )
    ) == 1
    with pytest.raises(ValueError, match="Run is not terminal"):
        materialize_public_result(waiting_fixture["run_store"], DEFAULT_RUN_ID)


def test_resume_replay_is_idempotent_and_never_resends(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    waiting_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    waiting_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    first = waiting_fixture["policy"].resume_after_acknowledgement(
        message_id=reservation.message.message_id,
        expected_task_state_version=waiting_task.state_version,
        expected_run_state_version=waiting_run["state_version"],
    )
    task_event_count = len(
        waiting_fixture["task_store"].list_events(waiting_fixture["task_id"], limit=50)
    )
    run_event_count = len(
        waiting_fixture["run_store"].get_events(DEFAULT_RUN_ID, limit=50)
    )

    replay = waiting_fixture["policy"].resume_after_acknowledgement(
        message_id=reservation.message.message_id,
        expected_task_state_version=waiting_task.state_version,
        expected_run_state_version=waiting_run["state_version"],
    )

    assert first.created is True
    assert replay.created is False
    assert replay.attempt_id == first.attempt_id
    assert len(
        waiting_fixture["substrate"].list_transport_attempts(
            message_id=reservation.message.message_id
        )
    ) == 1
    assert len(
        waiting_fixture["task_store"].list_events(waiting_fixture["task_id"], limit=50)
    ) == task_event_count
    assert len(
        waiting_fixture["run_store"].get_events(DEFAULT_RUN_ID, limit=50)
    ) == run_event_count


def test_concurrent_duplicate_resume_calls_converge_without_duplicate_events(
    waiting_fixture,
):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    waiting_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    waiting_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                waiting_fixture["policy"].resume_after_acknowledgement,
                message_id=reservation.message.message_id,
                expected_task_state_version=waiting_task.state_version,
                expected_run_state_version=waiting_run["state_version"],
            )
            for _index in range(2)
        ]
    results = [future.result() for future in futures]

    assert sorted(result.created for result in results) == [False, True]
    assert len({result.attempt_id for result in results}) == 1
    task_events = [
        event
        for event in waiting_fixture["task_store"].list_events(
            waiting_fixture["task_id"], limit=50
        )
        if event.stage == "controller_resumed"
    ]
    run_events = [
        event
        for event in waiting_fixture["run_store"].get_events(
            DEFAULT_RUN_ID, limit=50
        )
        if event["stage"] == "controller_resumed"
    ]
    assert len(task_events) == 1
    assert len(run_events) == 1


def test_restart_after_acknowledgement_repairs_only_local_resume(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    waiting_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    waiting_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    restarted_policy = InteractionTransitionPolicy(waiting_fixture["runs_dir"])
    resumed = restarted_policy.resume_after_acknowledgement(
        message_id=reservation.message.message_id,
        expected_task_state_version=waiting_task.state_version,
        expected_run_state_version=waiting_run["state_version"],
    )

    assert resumed.created is True
    assert resumed.task.state is TaskState.RUNNING
    assert len(
        restarted_policy.substrate_store.list_transport_attempts(
            message_id=reservation.message.message_id
        )
    ) == 1


def test_outcome_unknown_and_informational_messages_cannot_resume(waiting_fixture):
    _waiting, reservation = _reserve_input(waiting_fixture)
    attempt, _created = waiting_fixture["substrate"].claim_transport_attempt(
        reservation.message.message_id,
        claimer_id="sender:deterministic-stand-in",
    )
    waiting_fixture["substrate"].record_transport_attempt(
        attempt.attempt_id,
        state=TransportAttemptState.OUTCOME_UNKNOWN,
        reason="dispatch outcome cannot be proven",
    )
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    with pytest.raises(ResumeTransitionConflict, match="not acknowledged"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )

    # A fresh fixture proves that durable acknowledgement does not make an
    # informational report resumptive.


def test_acknowledged_progress_report_is_lifecycle_inert(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(
        waiting_fixture,
        message_class=MessageClass.PROGRESS_REPORT,
    )
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    with pytest.raises(ResumeTransitionConflict, match="informational"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state is TaskState.AWAITING_CONTROLLER


def test_cancellation_after_acknowledgement_outranks_resume(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    cancelled_task = waiting_fixture["task_store"].conditional_update(
        waiting_fixture["task_id"],
        fields={"state": TaskState.CANCELLATION_PENDING.value},
        expected_state_version=task.state_version,
        expected_states=(TaskState.AWAITING_CONTROLLER.value,),
    )
    cancelled_run = waiting_fixture["run_store"].conditional_update(
        DEFAULT_RUN_ID,
        fields={"status": "cancellation_pending"},
        expected_statuses=("awaiting_controller",),
        expected_state_version=run["state_version"],
    )
    assert cancelled_task is not None and cancelled_run is not None

    with pytest.raises(ResumeTransitionConflict, match="cancellation_pending"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=cancelled_task.state_version,
            expected_run_state_version=cancelled_run["state_version"],
        )
    with waiting_fixture["task_store"]._read() as conn:
        checkpoint = waiting_fixture["task_store"].get_checkpoint_in_connection(
            conn, reservation.message.checkpoint_id
        )
    assert checkpoint.status.value == "open"


def test_expiry_and_supersession_outrank_acknowledgement(
    waiting_fixture, monkeypatch
):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    monkeypatch.setattr(
        transitions_module,
        "utc_now",
        lambda: "2036-08-02T19:00:00+00:00",
    )
    with pytest.raises(ResumeTransitionConflict, match="deadline expired"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )


def test_durable_expiry_evidence_outranks_acknowledgement(waiting_fixture):
    waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    expiry, created = waiting_fixture["substrate"].record_checkpoint_expiry(
        checkpoint_id=waiting.checkpoint.checkpoint_id,
        task_id=waiting_fixture["task_id"],
        idempotency_key="expiry-observation-1",
        deadline_at=DEADLINE,
        observed_at="2035-08-02T19:00:01+00:00",
        disposition=CheckpointExpiryDisposition.UNCERTAIN,
        reason="deadline elapsed while transport acknowledgement was pending",
    )
    assert created is True
    assert expiry.checkpoint_id == waiting.checkpoint.checkpoint_id

    with pytest.raises(ResumeTransitionConflict, match="expiry evidence"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )


def test_supersession_after_acknowledgement_blocks_resume(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    successor = _make_task(
        waiting_fixture["task_store"],
        controller_request_id="wait-transition-successor",
        run_id="20260802T190000Z_worker_deadbeef",
    )
    waiting_fixture["task_store"].add_link(
        successor,
        link_type=TaskLinkType.SUPERSEDES,
        target_kind=TaskLinkTargetKind.TASK,
        target_id=waiting_fixture["task_id"],
    )

    with pytest.raises(ResumeTransitionConflict, match="supersession"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )


def test_unbound_session_and_lost_worker_identity_block_resume(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    waiting_fixture["substrate"].set_binding_disposition(
        waiting_fixture["binding"].session_binding_id,
        disposition=SessionBindingDisposition.UNVERIFIED,
        reason="provider session cannot be proven after restart",
    )
    with pytest.raises(ResumeTransitionConflict, match="not durably bound"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )


def test_lost_worker_start_identity_blocks_resume(waiting_fixture):
    _waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    waiting_fixture["run_store"].update_run(DEFAULT_RUN_ID, worker_identity="")

    with pytest.raises(ResumeTransitionConflict, match="worker identity"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )


def test_stale_resume_versions_fail_without_resolving_checkpoint(waiting_fixture):
    waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    with pytest.raises(ResumeTransitionConflict, match="task state version changed"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version + 1,
            expected_run_state_version=run["state_version"],
        )
    with waiting_fixture["task_store"]._read() as conn:
        checkpoint = waiting_fixture["task_store"].get_checkpoint_in_connection(
            conn, waiting.checkpoint.checkpoint_id
        )
    assert checkpoint.status.value == "open"


def test_resume_failure_after_checkpoint_resolution_rolls_back_everything(
    waiting_fixture, monkeypatch
):
    waiting, reservation, _acknowledged = _wait_and_acknowledge(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)

    def fail_run_update(*_args, **_kwargs):
        raise RuntimeError("simulated run resume failure")

    monkeypatch.setattr(
        waiting_fixture["policy"].run_store,
        "conditional_update_in_connection",
        fail_run_update,
    )
    with pytest.raises(RuntimeError, match="simulated run resume failure"):
        waiting_fixture["policy"].resume_after_acknowledgement(
            message_id=reservation.message.message_id,
            expected_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )

    current_task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    current_run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    command = waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    )[-1]
    with waiting_fixture["task_store"]._read() as conn:
        checkpoint = waiting_fixture["task_store"].get_checkpoint_in_connection(
            conn, waiting.checkpoint.checkpoint_id
        )
    assert current_task.state is TaskState.AWAITING_CONTROLLER
    assert current_task.state_version == task.state_version
    assert current_run["status"] == "awaiting_controller"
    assert current_run["state_version"] == run["state_version"]
    assert checkpoint.status.value == "open"
    assert command.status is TaskCommandStatus.ACCEPTED
    assert waiting_fixture["locks"].find_lock("soma", DEFAULT_RUN_ID) is not None
