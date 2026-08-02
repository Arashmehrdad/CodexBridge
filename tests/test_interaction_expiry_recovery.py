"""V3-1A checkpoint expiry, cancellation delegation, and recovery closure."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest

from soma.config import AppConfig
from soma.project_scope.store import ProjectScopeStore
from soma.run_store import TERMINAL_STATUSES, RunStore
from soma.tasks.backends import BackendObservation
from soma.tasks.manager import TaskManager
from soma.tasks.models import (
    TaskCheckpointStatus,
    TaskCommandKind,
    TaskCommandStatus,
    TaskState,
)
from soma.worker_substrate import (
    AttemptClaimBlocked,
    CheckpointExpiryDisposition,
    CheckpointRecoveryWindow,
    DeterministicInteractionTransport,
    ExpiryTransitionConflict,
    InteractionDispatcher,
    InteractionStateConflict,
    MessageDisposition,
    ResumeTransitionConflict,
    TransportAttemptState,
)

from test_interaction_wait_transition import (
    _enter,
    _reserve_input,
    waiting_fixture as _base_waiting_fixture,
)
from test_worker_substrate_foundation import DEFAULT_RUN_ID, PROJECT_ID, RESOURCE_ID


OBSERVED_AT = "2035-08-02T19:00:01+00:00"
TERMINAL_AT = "2035-08-02T19:00:02+00:00"


@pytest.fixture()
def waiting_fixture(tmp_path):
    return _base_waiting_fixture.__wrapped__(tmp_path)


class DeterministicCancellationBackend:
    """Canonical RunStore-backed cancellation authority for focused tests."""

    def __init__(self, run_store: RunStore, *, mode: str = "cancelled") -> None:
        self.run_store = run_store
        self.mode = mode
        self.calls: list[str] = []
        self.terminal_transitions = 0

    def query(self, backend_ref: str) -> BackendObservation:
        try:
            summary = self.run_store.get_run_summary(backend_ref)
        except KeyError:
            return BackendObservation(exists=False, error_code="backend_run_not_found")
        return BackendObservation(
            exists=True,
            status=str(summary.get("status") or ""),
            executor=str(summary.get("tool") or ""),
            repo_name=str(summary.get("repo_name") or ""),
            state_version=int(summary.get("state_version") or 0),
            exit_code=summary.get("exit_code"),
            started_at=summary.get("started_at"),
            ended_at=summary.get("ended_at"),
            result_publication_status=str(
                summary.get("result_publication_status") or ""
            ),
            result_published_hash=str(summary.get("result_published_hash") or ""),
            result_published_at=summary.get("result_published_at"),
        )

    def cancel(self, backend_ref: str) -> dict:
        self.calls.append(backend_ref)
        if self.mode == "raise":
            raise RuntimeError("deterministic backend delegation failure")

        current = self.run_store.get_run(backend_ref)
        if current["status"] in TERMINAL_STATUSES:
            return {
                "ok": True,
                "run_id": backend_ref,
                "status": current["status"],
                "cancelled": current["status"] == "cancelled",
                "termination_confirmed": True,
                "reason": "run already terminal",
            }

        if current["status"] != "cancellation_pending":
            pending = self.run_store.conditional_update(
                backend_ref,
                fields={
                    "status": "cancellation_pending",
                    "current_phase": "cancellation_pending",
                },
                expected_statuses=(str(current["status"]),),
                expected_state_version=int(current["state_version"]),
                expected_lease_token=str(current.get("worker_lease_token") or ""),
                expected_lease_generation=int(current.get("lease_generation") or 1),
                reject_terminal=True,
            )
            current = pending or self.run_store.get_run(backend_ref)

        if self.mode == "pending":
            return {
                "ok": False,
                "run_id": backend_ref,
                "status": "cancellation_pending",
                "cancelled": False,
                "termination_confirmed": False,
                "reason": "termination evidence remains pending; lock retained",
            }

        result = {
            "run_id": backend_ref,
            "status": "cancelled",
            "summary": "deterministic cancellation authority confirmed zero work",
            "ended_at": TERMINAL_AT,
        }
        terminal = self.run_store.transition_terminal(
            backend_ref,
            status="cancelled",
            result=result,
            expected_statuses=("cancellation_pending",),
            expected_state_version=int(current["state_version"]),
            expected_lease_token=str(current.get("worker_lease_token") or ""),
            expected_lease_generation=int(current.get("lease_generation") or 1),
            ended_at=TERMINAL_AT,
            summary="deterministic cancellation authority confirmed zero work",
        )
        if terminal is None:
            terminal = self.run_store.get_run(backend_ref)
        if terminal["status"] == "cancelled":
            self.terminal_transitions += 1
        return {
            "ok": True,
            "run_id": backend_ref,
            "status": terminal["status"],
            "cancelled": terminal["status"] == "cancelled",
            "termination_confirmed": terminal["status"] == "cancelled",
            "reason": "deterministic cancellation authority confirmed termination",
        }


def _manager(waiting_fixture, backend) -> TaskManager:
    return TaskManager(
        AppConfig(repos={}, runs_dir=str(waiting_fixture["runs_dir"])),
        backend=backend,
        store=waiting_fixture["task_store"],
        scope_store=ProjectScopeStore(waiting_fixture["runs_dir"]),
    )


def _policy_expire(waiting_fixture, *, observed_at: str = OBSERVED_AT):
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    return waiting_fixture["policy"].expire_checkpoint(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=waiting_fixture["task_id"],
        run_id=DEFAULT_RUN_ID,
        session_binding_id=waiting_fixture["binding"].session_binding_id,
        checkpoint_id=task.checkpoint_ref,
        idempotency_key=f"deadline:{task.checkpoint_ref}",
        expected_task_state_version=task.state_version,
        expected_run_state_version=int(run["state_version"]),
        observed_at=observed_at,
        reason="controller deadline elapsed",
    )


def _assert_lock_retained(waiting_fixture) -> None:
    with waiting_fixture["run_store"].connect() as conn:
        row = conn.execute(
            "SELECT run_id FROM operation_locks WHERE repo_name = ?",
            ("soma",),
        ).fetchone()
    assert row is not None
    assert str(row["run_id"]) == DEFAULT_RUN_ID


def test_expiry_delegates_cancellation_without_releasing_lock(waiting_fixture):
    waiting = _enter(waiting_fixture)
    backend = DeterministicCancellationBackend(waiting_fixture["run_store"])
    manager = _manager(waiting_fixture, backend)

    result = manager.process_checkpoint_expiry(
        waiting_fixture["task_id"],
        checkpoint_id=waiting.checkpoint.checkpoint_id,
        observed_at=OBSERVED_AT,
        reason="controller did not answer before the bounded deadline",
    )

    assert result["processed"] is True
    assert result["created"] is True
    assert result["recovery_window"] is CheckpointRecoveryWindow.NO_INPUT_RESERVED
    assert result["cancellation_complete"] is True
    assert result["ownership_release_claimed"] is False
    assert result["ownership_authority"] == "durable_backend"
    assert backend.calls == [DEFAULT_RUN_ID]
    assert backend.terminal_transitions == 1
    assert result["task"].state is TaskState.CANCELLED
    assert result["task"].checkpoint_ref == ""
    assert waiting_fixture["task_store"].get_checkpoint(
        waiting.checkpoint.checkpoint_id
    ).status is TaskCheckpointStatus.CANCELLED
    command = waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    )[0]
    assert command.command_kind is TaskCommandKind.CANCEL
    assert command.status is TaskCommandStatus.COMPLETED
    expiries = waiting_fixture["substrate"].list_checkpoint_expiries(
        waiting.checkpoint.checkpoint_id
    )
    assert len(expiries) == 1
    assert expiries[0].disposition is CheckpointExpiryDisposition.RECORDED
    _assert_lock_retained(waiting_fixture)


def test_expiry_replay_reuses_command_and_never_reterminates(waiting_fixture):
    waiting = _enter(waiting_fixture)
    backend = DeterministicCancellationBackend(waiting_fixture["run_store"])
    manager = _manager(waiting_fixture, backend)

    first = manager.process_checkpoint_expiry(
        waiting_fixture["task_id"],
        checkpoint_id=waiting.checkpoint.checkpoint_id,
        observed_at=OBSERVED_AT,
    )
    replay = manager.process_checkpoint_expiry(
        waiting_fixture["task_id"],
        checkpoint_id=waiting.checkpoint.checkpoint_id,
        observed_at="2035-08-02T19:10:00+00:00",
        reason="later recovery pass",
    )

    assert first["created"] is True
    assert replay["created"] is False
    assert replay["expiry"].expiry_id == first["expiry"].expiry_id
    assert replay["command"].command_id == first["command"].command_id
    assert backend.calls == [DEFAULT_RUN_ID, DEFAULT_RUN_ID]
    assert backend.terminal_transitions == 1
    assert len(
        waiting_fixture["substrate"].list_checkpoint_expiries(
            waiting.checkpoint.checkpoint_id
        )
    ) == 1
    cancel_commands = [
        command
        for command in waiting_fixture["task_store"].list_commands(
            waiting_fixture["task_id"]
        )
        if command.command_kind is TaskCommandKind.CANCEL
    ]
    assert len(cancel_commands) == 1


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        ("none", CheckpointRecoveryWindow.NO_INPUT_RESERVED),
        ("reserved", CheckpointRecoveryWindow.PENDING_NEVER_ATTEMPTED),
        ("claimed", CheckpointRecoveryWindow.IN_FLIGHT_AT_EXPIRY),
        ("unknown", CheckpointRecoveryWindow.OUTCOME_UNKNOWN),
        ("acknowledged", CheckpointRecoveryWindow.ACKNOWLEDGED_BEFORE_RESUME),
        ("rejected", CheckpointRecoveryWindow.REJECTED_BEFORE_EXPIRY),
        ("resolved", CheckpointRecoveryWindow.RESOLVED_BEFORE_RUN_RESUME),
    ],
)
def test_expiry_classifies_exact_recovery_window(waiting_fixture, setup, expected):
    if setup == "none":
        _enter(waiting_fixture)
    else:
        waiting, reservation = _reserve_input(waiting_fixture)
        if setup in {"claimed", "unknown", "acknowledged", "rejected"}:
            attempt, created = waiting_fixture["substrate"].claim_transport_attempt(
                reservation.message.message_id,
                claimer_id="transport:expiry-window-test",
            )
            assert created is True
            target = {
                "unknown": TransportAttemptState.OUTCOME_UNKNOWN,
                "acknowledged": TransportAttemptState.ACKNOWLEDGED,
                "rejected": TransportAttemptState.REJECTED,
            }.get(setup)
            if target is not None:
                waiting_fixture["substrate"].record_transport_attempt(
                    attempt.attempt_id,
                    state=target,
                    reason=f"deterministic {target.value}",
                    evidence_ref=(
                        "transport_evidence:expiry-window"
                        if target is TransportAttemptState.ACKNOWLEDGED
                        else ""
                    ),
                )
        if setup == "resolved":
            task = waiting_fixture["task_store"].get_task(
                waiting_fixture["task_id"]
            )
            with waiting_fixture["task_store"].transaction() as conn:
                waiting_fixture["task_store"].resolve_checkpoint_in_connection(
                    conn,
                    waiting.checkpoint.checkpoint_id,
                    task_id=task.task_id,
                    required_state_version=task.state_version,
                )

    result = _policy_expire(waiting_fixture)

    assert result.recovery_window is expected
    if setup == "claimed":
        replay = _policy_expire(waiting_fixture)
        assert replay.recovery_window is CheckpointRecoveryWindow.UNRESOLVED_CLAIM
        assert replay.created is False


def test_deadline_before_due_creates_no_expiry_or_cancel_intent(waiting_fixture):
    waiting = _enter(waiting_fixture)

    with pytest.raises(ExpiryTransitionConflict, match="has not elapsed"):
        _policy_expire(
            waiting_fixture,
            observed_at="2035-08-02T18:59:59+00:00",
        )

    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state is TaskState.AWAITING_CONTROLLER
    assert waiting_fixture["task_store"].get_checkpoint(
        waiting.checkpoint.checkpoint_id
    ).status is TaskCheckpointStatus.OPEN
    assert waiting_fixture["substrate"].list_checkpoint_expiries(
        waiting.checkpoint.checkpoint_id
    ) == []
    assert [
        command
        for command in waiting_fixture["task_store"].list_commands(
            waiting_fixture["task_id"]
        )
        if command.command_kind is TaskCommandKind.CANCEL
    ] == []


def test_expiry_before_send_blocks_transport_claim(waiting_fixture):
    waiting, reservation = _reserve_input(waiting_fixture)

    result = _policy_expire(waiting_fixture)

    assert result.recovery_window is CheckpointRecoveryWindow.PENDING_NEVER_ATTEMPTED
    with pytest.raises(AttemptClaimBlocked):
        waiting_fixture["substrate"].claim_transport_attempt(
            reservation.message.message_id,
            claimer_id="transport:too-late",
        )
    message = waiting_fixture["substrate"].get_message(
        reservation.message.message_id
    )
    assert message.disposition is MessageDisposition.EXPIRED
    assert waiting_fixture["substrate"].list_transport_attempts(
        message_id=reservation.message.message_id
    ) == []
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state is TaskState.CANCELLATION_PENDING
    assert waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)[
        "status"
    ] == "awaiting_controller"
    _assert_lock_retained(waiting_fixture)


def test_expiry_during_send_preserves_late_ack_without_resume_or_resend(
    waiting_fixture,
):
    waiting = _enter(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    claimed = Event()
    release = Event()

    def before_dispatch(_request):
        claimed.set()
        assert release.wait(timeout=10)

    transport = DeterministicInteractionTransport(before_dispatch=before_dispatch)
    dispatcher = InteractionDispatcher(
        waiting_fixture["runs_dir"], transport=transport
    )
    request = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": waiting_fixture["task_id"],
        "run_id": DEFAULT_RUN_ID,
        "session_binding_id": waiting_fixture["binding"].session_binding_id,
        "command_kind": TaskCommandKind.SUPPLY_INPUT,
        "idempotency_key": "expiry-during-send",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "continue after expiry race",
        "requested_task_state_version": task.state_version,
        "expected_run_state_version": int(
            waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)["state_version"]
        ),
        "checkpoint_id": waiting.checkpoint.checkpoint_id,
    }

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(dispatcher.dispatch, **request)
        assert claimed.wait(timeout=10)
        expiry = _policy_expire(waiting_fixture)
        assert expiry.recovery_window is CheckpointRecoveryWindow.IN_FLIGHT_AT_EXPIRY
        release.set()
        with pytest.raises(ResumeTransitionConflict):
            future.result(timeout=10)

    attempts = waiting_fixture["substrate"].list_transport_attempts()
    assert len(attempts) == 1
    assert attempts[0].state is TransportAttemptState.ACKNOWLEDGED
    messages = waiting_fixture["substrate"].list_messages(
        task_id=waiting_fixture["task_id"]
    )
    assert len(messages) == 1
    assert messages[0].disposition is MessageDisposition.EXPIRED
    assert len(transport.requests) == 1
    with pytest.raises(InteractionStateConflict):
        dispatcher.dispatch(**request)
    assert len(transport.requests) == 1
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state is TaskState.CANCELLATION_PENDING
    assert waiting_fixture["task_store"].get_checkpoint(
        waiting.checkpoint.checkpoint_id
    ).status is TaskCheckpointStatus.CANCELLED


def test_backend_pending_retains_lock_and_reports_no_release(waiting_fixture):
    waiting = _enter(waiting_fixture)
    backend = DeterministicCancellationBackend(
        waiting_fixture["run_store"], mode="pending"
    )
    manager = _manager(waiting_fixture, backend)

    result = manager.process_checkpoint_expiry(
        waiting_fixture["task_id"],
        checkpoint_id=waiting.checkpoint.checkpoint_id,
        observed_at=OBSERVED_AT,
    )

    assert result["cancellation_complete"] is False
    assert result["ownership_release_claimed"] is False
    assert result["task"].state is TaskState.CANCELLATION_PENDING
    assert result["task"].checkpoint_ref == ""
    assert waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)[
        "status"
    ] == "cancellation_pending"
    _assert_lock_retained(waiting_fixture)


def test_quiescence_evidence_does_not_release_lock_from_coordinator(waiting_fixture):
    waiting = _enter(waiting_fixture)
    backend = DeterministicCancellationBackend(
        waiting_fixture["run_store"], mode="pending"
    )
    manager = _manager(waiting_fixture, backend)

    result = manager.process_checkpoint_expiry(
        waiting_fixture["task_id"],
        checkpoint_id=waiting.checkpoint.checkpoint_id,
        observed_at=OBSERVED_AT,
        quiescence_proof_ref="descendant_sweep:0_alive",
    )

    assert result["expiry"].disposition is (
        CheckpointExpiryDisposition.QUIESCENT_CONFIRMED
    )
    assert result["ownership_release_claimed"] is False
    _assert_lock_retained(waiting_fixture)


def test_startup_repairs_crash_after_expiry_before_backend_delegation(
    waiting_fixture,
):
    waiting = _enter(waiting_fixture)
    failing_backend = DeterministicCancellationBackend(
        waiting_fixture["run_store"], mode="raise"
    )
    failing_manager = _manager(waiting_fixture, failing_backend)

    with pytest.raises(RuntimeError, match="delegation failure"):
        failing_manager.process_checkpoint_expiry(
            waiting_fixture["task_id"],
            checkpoint_id=waiting.checkpoint.checkpoint_id,
            observed_at=OBSERVED_AT,
        )

    interrupted = waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    )
    assert interrupted.state is TaskState.CANCELLATION_PENDING
    assert interrupted.checkpoint_ref == waiting.checkpoint.checkpoint_id
    assert waiting_fixture["task_store"].get_checkpoint(
        waiting.checkpoint.checkpoint_id
    ).status is TaskCheckpointStatus.CANCELLED
    cancel_command = [
        command
        for command in waiting_fixture["task_store"].list_commands(
            waiting_fixture["task_id"]
        )
        if command.command_kind is TaskCommandKind.CANCEL
    ][0]
    assert cancel_command.status is TaskCommandStatus.ACCEPTED
    assert waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)[
        "status"
    ] == "awaiting_controller"
    _assert_lock_retained(waiting_fixture)

    recovery_backend = DeterministicCancellationBackend(waiting_fixture["run_store"])
    recovery_manager = _manager(waiting_fixture, recovery_backend)
    summary = recovery_manager.reconcile_startup()

    recovered = waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    )
    assert summary["ok"] is True
    assert summary["changed"] == 1
    assert recovery_backend.calls == [DEFAULT_RUN_ID]
    assert recovered.state is TaskState.CANCELLED
    assert recovered.checkpoint_ref == ""
    completed = waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    )
    assert [
        command.status
        for command in completed
        if command.command_kind is TaskCommandKind.CANCEL
    ] == [TaskCommandStatus.COMPLETED]
    assert len(
        waiting_fixture["substrate"].list_checkpoint_expiries(
            waiting.checkpoint.checkpoint_id
        )
    ) == 1
    _assert_lock_retained(waiting_fixture)


def test_recovery_window_observation_is_timezone_aware(waiting_fixture):
    _enter(waiting_fixture)
    with pytest.raises(ValueError, match="timezone"):
        _policy_expire(
            waiting_fixture,
            observed_at=datetime(2035, 8, 2, 19, 0, 1).isoformat(),
        )
    aware = datetime(2035, 8, 2, 19, 0, 1, tzinfo=timezone.utc).isoformat()
    assert _policy_expire(waiting_fixture, observed_at=aware).created is True
