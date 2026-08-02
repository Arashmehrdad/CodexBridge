"""V3-1A deterministic persist-before-send interaction dispatch."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from soma.run_store import RunStore
from soma.tasks.models import TaskCommandKind, TaskCommandStatus, TaskPhase, TaskState
from soma.tasks.store import TaskStore
from soma.worker_substrate import (
    DeterministicInteractionTransport,
    InteractionCapabilityUnsupported,
    InteractionCoordinator,
    InteractionDispatcher,
    InteractionDispatchUnavailable,
    InteractionTransportRequest,
    InteractionTransportResult,
    MessageClass,
    TransportAttemptState,
    TransportDispatchDisposition,
    UnavailableInteractionTransport,
    WorkerSubstrateStore,
)

from test_interaction_wait_transition import (
    _enter,
    waiting_fixture as _base_waiting_fixture,
)
from test_worker_substrate_foundation import (
    DEFAULT_RUN_ID,
    PROJECT_ID,
    RESOURCE_ID,
    _bind,
    _make_task,
)


@pytest.fixture()
def waiting_fixture(tmp_path: Path):
    """Reuse the accepted wait fixture without import-name fixture magic."""
    return _base_waiting_fixture.__wrapped__(tmp_path)


def _dispatch_input(waiting_fixture, transport, **overrides):
    waiting = _enter(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    request = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": waiting_fixture["task_id"],
        "run_id": DEFAULT_RUN_ID,
        "session_binding_id": waiting_fixture["binding"].session_binding_id,
        "command_kind": TaskCommandKind.SUPPLY_INPUT,
        "idempotency_key": "dispatch-input-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "continue",
        "requested_task_state_version": task.state_version,
        "expected_run_state_version": run["state_version"],
        "message_class": MessageClass.DECISION,
        "checkpoint_id": waiting.checkpoint.checkpoint_id,
    }
    request.update(overrides)
    dispatcher = InteractionDispatcher(
        waiting_fixture["runs_dir"], transport=transport
    )
    return dispatcher, request


def _running_fixture(tmp_path: Path, *, provider: str = "claude_code"):
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    task_id = _make_task(
        task_store,
        controller_request_id=f"running-{provider}-task",
        run_id=DEFAULT_RUN_ID,
    )
    substrate = WorkerSubstrateStore(runs_dir)
    binding_overrides = {}
    if provider == "codex":
        binding_overrides = {
            "provider": "codex",
            "native_session_id": "019c6f98-1234-7abc-8def-1234567890ab",
            "adapter_id": "soma.adapter.codex",
            "protocol_id": "codex.exec_json",
            "protocol_version": "1",
        }
    binding, _created = _bind(substrate, task_id, **binding_overrides)
    task = task_store.get_task(task_id)
    running_task = task_store.conditional_update(
        task_id,
        fields={
            "state": TaskState.RUNNING.value,
            "phase": TaskPhase.BACKEND_RUNNING.value,
            "started_at": "2026-08-02T18:00:00+00:00",
        },
        expected_state_version=task.state_version,
        expected_states=(TaskState.ACCEPTED.value,),
    )
    assert running_task is not None
    run_store = RunStore(runs_dir)
    run = run_store.get_run(DEFAULT_RUN_ID)
    running_run = run_store.conditional_update(
        DEFAULT_RUN_ID,
        fields={
            "status": "running",
            "current_phase": "backend_running",
            "started_at": "2026-08-02T18:00:00+00:00",
            "heartbeat_at": "2026-08-02T18:00:00+00:00",
        },
        expected_statuses=(str(run["status"]),),
        expected_state_version=int(run["state_version"]),
    )
    assert running_run is not None
    return runs_dir, task_store, run_store, substrate, task_id, binding


def test_unavailable_transport_fails_before_reservation(waiting_fixture):
    dispatcher, request = _dispatch_input(
        waiting_fixture, UnavailableInteractionTransport()
    )
    with pytest.raises(InteractionDispatchUnavailable):
        dispatcher.dispatch(**request)
    assert dispatcher.store.list_messages(task_id=waiting_fixture["task_id"]) == []
    assert waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    ) == []


def test_acknowledgement_is_persisted_before_transport_and_resumes(waiting_fixture):
    secret = "secret-input-never-inline"
    observed = {}

    def inspect_durable_state(request):
        observed["request"] = request
        store = WorkerSubstrateStore(waiting_fixture["runs_dir"])
        message = store.get_message(request.message_id)
        attempt = store.get_transport_attempt(request.attempt_id)
        observed["message"] = message
        observed["attempt"] = attempt
        observed["payload"] = store.read_payload(message.payload_ref)

    transport = DeterministicInteractionTransport(before_dispatch=inspect_durable_state)
    dispatcher, request = _dispatch_input(
        waiting_fixture,
        transport,
        payload=secret,
    )
    result = dispatcher.dispatch(**request)

    assert result.acknowledged is True
    assert result.transport_called is True
    assert result.resumed is not None
    assert result.resumed.task.state is TaskState.RUNNING
    assert result.resumed.run["status"] == "running"
    assert observed["attempt"].state is TransportAttemptState.CLAIMED
    assert observed["message"].message_id == observed["request"].message_id
    assert observed["payload"] == secret.encode("utf-8")
    request_values = vars(observed["request"])
    assert secret not in repr(request_values)
    assert "payload" not in request_values
    assert transport.requests == [observed["request"]]


def test_rejected_input_keeps_checkpoint_open_and_completes_command_failed(
    waiting_fixture,
):
    transport = DeterministicInteractionTransport(
        disposition=TransportDispatchDisposition.REJECTED,
        reason="stand-in rejected exact input",
    )
    dispatcher, request = _dispatch_input(waiting_fixture, transport)
    result = dispatcher.dispatch(**request)

    assert result.delivery == TransportAttemptState.REJECTED.value
    assert result.resumed is None
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    assert task.state is TaskState.AWAITING_CONTROLLER
    with waiting_fixture["task_store"]._read() as conn:
        checkpoint = waiting_fixture["task_store"].get_checkpoint_in_connection(
            conn, result.reservation.message.checkpoint_id
        )
    assert checkpoint.status.value == "open"
    command = waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    )[-1]
    assert command.status is TaskCommandStatus.FAILED


def test_outcome_unknown_is_not_resent_on_replay(waiting_fixture):
    transport = DeterministicInteractionTransport(
        disposition=TransportDispatchDisposition.OUTCOME_UNKNOWN,
        reason="stand-in cannot prove dispatch outcome",
    )
    dispatcher, request = _dispatch_input(waiting_fixture, transport)
    first = dispatcher.dispatch(**request)
    replay = dispatcher.dispatch(**request)

    assert first.uncertain is True
    assert replay.uncertain is True
    assert first.attempt is not None and replay.attempt is not None
    assert first.attempt.attempt_id == replay.attempt.attempt_id
    assert replay.transport_called is False
    assert len(transport.requests) == 1
    command = waiting_fixture["task_store"].list_commands(
        waiting_fixture["task_id"]
    )[-1]
    assert command.status is TaskCommandStatus.ACCEPTED
    assert waiting_fixture["task_store"].get_task(
        waiting_fixture["task_id"]
    ).state is TaskState.AWAITING_CONTROLLER


def test_transport_exception_becomes_durable_uncertainty(waiting_fixture):
    transport = DeterministicInteractionTransport(raise_outcome_unknown=True)
    dispatcher, request = _dispatch_input(waiting_fixture, transport)
    result = dispatcher.dispatch(**request)

    assert result.uncertain is True
    assert result.transport_called is True
    assert len(transport.requests) == 1
    assert result.reason == "transport outcome cannot be proven; resend forbidden"


def test_replay_of_prior_claim_never_calls_transport(waiting_fixture):
    waiting = _enter(waiting_fixture)
    task = waiting_fixture["task_store"].get_task(waiting_fixture["task_id"])
    run = waiting_fixture["run_store"].get_run(DEFAULT_RUN_ID)
    transport = DeterministicInteractionTransport()
    coordinator = InteractionCoordinator(waiting_fixture["runs_dir"])
    reservation = coordinator.reserve(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=waiting_fixture["task_id"],
        run_id=DEFAULT_RUN_ID,
        session_binding_id=waiting_fixture["binding"].session_binding_id,
        command_kind=TaskCommandKind.SUPPLY_INPUT,
        idempotency_key="dispatch-input-1",
        sender_ref="controller:chatgpt",
        recipient_ref="worker:provider-session",
        payload="continue",
        requested_state_version=task.state_version,
        message_class=MessageClass.DECISION,
        checkpoint_id=waiting.checkpoint.checkpoint_id,
    )
    attempt, created = waiting_fixture["substrate"].claim_transport_attempt(
        reservation.message.message_id,
        claimer_id=transport.claimer_id,
    )
    assert created is True
    assert attempt.state is TransportAttemptState.CLAIMED

    dispatcher = InteractionDispatcher(
        waiting_fixture["runs_dir"], transport=transport
    )
    result = dispatcher.dispatch(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=waiting_fixture["task_id"],
        run_id=DEFAULT_RUN_ID,
        session_binding_id=waiting_fixture["binding"].session_binding_id,
        command_kind=TaskCommandKind.SUPPLY_INPUT,
        idempotency_key="dispatch-input-1",
        sender_ref="controller:chatgpt",
        recipient_ref="worker:provider-session",
        payload="continue",
        requested_task_state_version=task.state_version,
        expected_run_state_version=run["state_version"],
        message_class=MessageClass.DECISION,
        checkpoint_id=waiting.checkpoint.checkpoint_id,
    )

    assert result.uncertain is False
    assert result.delivery == TransportAttemptState.CLAIMED.value
    assert result.transport_called is False
    assert transport.requests == []
    assert result.attempt is not None
    assert result.attempt.attempt_id == attempt.attempt_id
    assert result.attempt.state is TransportAttemptState.CLAIMED
    assert "prior transport claim is unresolved" in result.reason


def test_ack_before_resume_is_repaired_without_second_dispatch(
    waiting_fixture, monkeypatch
):
    transport = DeterministicInteractionTransport()
    dispatcher, request = _dispatch_input(waiting_fixture, transport)

    def crash_after_ack(**_kwargs):
        raise RuntimeError("simulated crash after acknowledgement")

    monkeypatch.setattr(
        dispatcher.policy,
        "resume_after_acknowledgement",
        crash_after_ack,
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        dispatcher.dispatch(**request)
    assert len(transport.requests) == 1

    repaired = InteractionDispatcher(
        waiting_fixture["runs_dir"], transport=transport
    ).dispatch(**request)
    assert repaired.acknowledged is True
    assert repaired.transport_called is False
    assert repaired.resumed is not None
    assert repaired.resumed.task.state is TaskState.RUNNING
    assert len(transport.requests) == 1


def test_steer_acknowledgement_completes_command_without_state_change(tmp_path):
    runs_dir, task_store, run_store, _substrate, task_id, binding = _running_fixture(
        tmp_path
    )
    task = task_store.get_task(task_id)
    run = run_store.get_run(DEFAULT_RUN_ID)
    transport = DeterministicInteractionTransport()
    result = InteractionDispatcher(runs_dir, transport=transport).dispatch(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=task_id,
        run_id=DEFAULT_RUN_ID,
        session_binding_id=binding.session_binding_id,
        command_kind=TaskCommandKind.STEER,
        idempotency_key="steer-1",
        sender_ref="controller:chatgpt",
        recipient_ref="worker:provider-session",
        payload="focus on the bounded result",
        requested_task_state_version=task.state_version,
        expected_run_state_version=run["state_version"],
    )

    assert result.acknowledged is True
    current_task = task_store.get_task(task_id)
    current_run = run_store.get_run(DEFAULT_RUN_ID)
    assert current_task.state is TaskState.RUNNING
    assert current_task.state_version == task.state_version
    assert current_run["status"] == "running"
    command = task_store.list_commands(task_id)[-1]
    assert command.command_kind is TaskCommandKind.STEER
    assert command.status is TaskCommandStatus.COMPLETED


def test_codex_steering_fails_capability_honestly_before_reservation(tmp_path):
    runs_dir, task_store, run_store, substrate, task_id, binding = _running_fixture(
        tmp_path, provider="codex"
    )
    task = task_store.get_task(task_id)
    run = run_store.get_run(DEFAULT_RUN_ID)
    transport = DeterministicInteractionTransport(
        supported_providers={"codex"},
        supported_command_kinds={"steer"},
    )
    dispatcher = InteractionDispatcher(runs_dir, transport=transport)

    with pytest.raises(InteractionCapabilityUnsupported, match="does not support"):
        dispatcher.dispatch(
            project_id=PROJECT_ID,
            resource_id=RESOURCE_ID,
            task_id=task_id,
            run_id=DEFAULT_RUN_ID,
            session_binding_id=binding.session_binding_id,
            command_kind=TaskCommandKind.STEER,
            idempotency_key="codex-steer-1",
            sender_ref="controller:chatgpt",
            recipient_ref="worker:provider-session",
            payload="steer",
            requested_task_state_version=task.state_version,
            expected_run_state_version=run["state_version"],
        )
    assert substrate.list_messages(task_id=task_id) == []
    assert task_store.list_commands(task_id) == []
    assert transport.requests == []


def test_concurrent_identical_dispatch_calls_transport_once(tmp_path):
    runs_dir, task_store, run_store, substrate, task_id, binding = _running_fixture(
        tmp_path
    )
    task = task_store.get_task(task_id)
    run = run_store.get_run(DEFAULT_RUN_ID)
    transport = DeterministicInteractionTransport()
    request = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": task_id,
        "run_id": DEFAULT_RUN_ID,
        "session_binding_id": binding.session_binding_id,
        "command_kind": TaskCommandKind.STEER,
        "idempotency_key": "concurrent-steer-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "focus on the bounded result",
        "requested_task_state_version": task.state_version,
        "expected_run_state_version": run["state_version"],
    }
    dispatchers = [
        InteractionDispatcher(runs_dir, transport=transport),
        InteractionDispatcher(runs_dir, transport=transport),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(dispatcher.dispatch, **request)
            for dispatcher in dispatchers
        ]
    results = [future.result() for future in futures]

    assert len(transport.requests) == 1
    assert len({result.attempt.attempt_id for result in results if result.attempt}) == 1
    assert sorted(result.transport_called for result in results) == [False, True]
    assert len(
        substrate.list_transport_attempts(
            message_id=results[0].reservation.message.message_id
        )
    ) == 1


class _MissingEvidenceTransport(DeterministicInteractionTransport):
    def dispatch(
        self, request: InteractionTransportRequest
    ) -> InteractionTransportResult:
        self.requests.append(request)
        return InteractionTransportResult(
            disposition=TransportDispatchDisposition.ACKNOWLEDGED,
            reason="acknowledged but evidence was omitted",
            evidence_ref="",
        )


def test_acknowledgement_without_evidence_becomes_uncertain(waiting_fixture):
    transport = _MissingEvidenceTransport()
    dispatcher, request = _dispatch_input(waiting_fixture, transport)

    result = dispatcher.dispatch(**request)

    assert result.uncertain is True
    assert result.attempt is not None
    assert result.attempt.state is TransportAttemptState.OUTCOME_UNKNOWN
    assert result.evidence_ref == ""
    assert "omitted durable evidence" in result.reason


class _ExplodingTransport(DeterministicInteractionTransport):
    def dispatch(self, request: InteractionTransportRequest):
        self.requests.append(request)
        raise RuntimeError("provider leaked secret-value-that-must-not-persist")


def test_transport_exception_does_not_persist_exception_text(waiting_fixture):
    transport = _ExplodingTransport()
    dispatcher, request = _dispatch_input(waiting_fixture, transport)

    result = dispatcher.dispatch(**request)

    assert result.uncertain is True
    assert result.attempt is not None
    assert result.attempt.state is TransportAttemptState.OUTCOME_UNKNOWN
    assert "RuntimeError" in result.reason
    assert "secret-value-that-must-not-persist" not in result.reason
