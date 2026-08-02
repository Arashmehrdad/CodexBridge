"""V3-1A interaction message reservation and transport-attempt foundation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from soma.tasks.models import (
    TaskCommandKind,
    TaskState,
)
from soma.tasks.store import TaskStore
from soma.worker_substrate import (
    AttemptClaimBlocked,
    CanonicalBindingMismatch,
    EvidenceConflict,
    InteractionCoordinator,
    InteractionStateConflict,
    MessageClass,
    MessageConflict,
    MessageDisposition,
    TransportAttemptState,
    WorkerSubstrateStore,
)

from test_worker_substrate_foundation import (
    DEFAULT_RUN_ID,
    PROJECT_ID,
    RESOURCE_ID,
    _bind,
    _make_task,
)


@pytest.fixture()
def coordinated(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    task_id = _make_task(
        task_store,
        controller_request_id="interaction-primary-task",
        run_id=DEFAULT_RUN_ID,
    )
    substrate = WorkerSubstrateStore(runs_dir)
    binding, _created = _bind(substrate, task_id)
    coordinator = InteractionCoordinator(runs_dir)
    return coordinator, coordinator.task_store, coordinator.substrate_store, task_id, binding


def _reserve(coordinator, task_id, binding, **overrides):
    payload = {
        "project_id": PROJECT_ID,
        "resource_id": RESOURCE_ID,
        "task_id": task_id,
        "run_id": DEFAULT_RUN_ID,
        "session_binding_id": binding.session_binding_id,
        "command_kind": TaskCommandKind.STEER,
        "idempotency_key": "interaction-1",
        "sender_ref": "controller:chatgpt",
        "recipient_ref": "worker:provider-session",
        "payload": "write the bounded result",
        "requested_state_version": 0,
        "message_class": MessageClass.COMMAND,
    }
    payload.update(overrides)
    return coordinator.reserve(**payload)


def test_content_addressed_payload_put_is_concurrent_and_exact(coordinated):
    _coordinator, _task_store, substrate, _task_id, _binding = coordinated
    payload = "same immutable payload from concurrent senders"

    with ThreadPoolExecutor(max_workers=4) as pool:
        references = list(pool.map(substrate.put_payload, [payload] * 8))

    assert len({reference.ref for reference in references}) == 1
    assert len({reference.payload_hash for reference in references}) == 1
    assert substrate.read_payload(references[0].ref) == payload.encode("utf-8")
    payload_dir = substrate.payload_path(references[0].ref).parent
    assert [path for path in payload_dir.iterdir() if path.suffix == ".tmp"] == []


def test_atomic_reservation_creates_one_command_and_one_message(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated

    reservation = _reserve(coordinator, task_id, binding)

    assert reservation.created is True
    assert reservation.command.command_kind is TaskCommandKind.STEER
    assert reservation.message.command_id == reservation.command.command_id
    assert reservation.message.disposition is MessageDisposition.RESERVED
    assert len(reservation.message.contract_hash) == 64
    assert len(task_store.list_commands(task_id)) == 1
    assert len(substrate.list_messages(task_id=task_id)) == 1

    replay = _reserve(coordinator, task_id, binding)
    assert replay.created is False
    assert replay.command.command_id == reservation.command.command_id
    assert replay.message.message_id == reservation.message.message_id


def test_conflicting_replay_uses_the_complete_contract_hash(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated
    original = _reserve(coordinator, task_id, binding)

    with pytest.raises(MessageConflict) as raised:
        _reserve(
            coordinator,
            task_id,
            binding,
            recipient_ref="worker:different-session",
        )

    assert raised.value.existing.message_id == original.message.message_id
    assert len(task_store.list_commands(task_id)) == 1
    assert len(substrate.list_messages(task_id=task_id)) == 1


def test_message_failure_rolls_back_the_new_canonical_command(
    coordinated, monkeypatch
):
    coordinator, task_store, substrate, task_id, binding = coordinated

    def fail_message(*_args, **_kwargs):
        raise RuntimeError("simulated subordinate reservation failure")

    monkeypatch.setattr(substrate, "reserve_message_in_connection", fail_message)
    with pytest.raises(RuntimeError, match="simulated subordinate"):
        _reserve(coordinator, task_id, binding)

    assert task_store.list_commands(task_id) == []
    assert substrate.list_messages(task_id=task_id) == []


def test_concurrent_identical_requests_converge_on_one_identity(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_reserve, coordinator, task_id, binding)
            for _index in range(2)
        ]
    results = [future.result() for future in futures]

    assert sorted(result.created for result in results) == [False, True]
    assert len({result.command.command_id for result in results}) == 1
    assert len({result.message.message_id for result in results}) == 1
    assert len(task_store.list_commands(task_id)) == 1
    assert len(substrate.list_messages(task_id=task_id)) == 1


def test_one_message_has_one_durable_transport_claim(coordinated):
    coordinator, _task_store, substrate, task_id, binding = coordinated
    reservation = _reserve(coordinator, task_id, binding)

    attempt, created = substrate.claim_transport_attempt(
        reservation.message.message_id,
        claimer_id="sender:deterministic-stand-in",
    )
    assert created is True
    assert attempt.state is TransportAttemptState.CLAIMED

    replay, created_again = substrate.claim_transport_attempt(
        reservation.message.message_id,
        claimer_id="sender:deterministic-stand-in",
    )
    assert created_again is False
    assert replay.attempt_id == attempt.attempt_id

    with pytest.raises(EvidenceConflict):
        substrate.claim_transport_attempt(
            reservation.message.message_id,
            claimer_id="sender:competing-worker",
        )
    assert len(substrate.list_transport_attempts()) == 1


def test_outcome_unknown_attempt_is_not_reclaimed_or_resent(coordinated):
    coordinator, _task_store, substrate, task_id, binding = coordinated
    reservation = _reserve(coordinator, task_id, binding)
    attempt, _created = substrate.claim_transport_attempt(
        reservation.message.message_id,
        claimer_id="sender:stand-in",
    )

    uncertain = substrate.record_transport_attempt(
        attempt.attempt_id,
        state=TransportAttemptState.OUTCOME_UNKNOWN,
        reason="crash after claim; dispatch outcome cannot be proven",
    )
    assert uncertain.state is TransportAttemptState.OUTCOME_UNKNOWN
    assert substrate.get_message(reservation.message.message_id).disposition is (
        MessageDisposition.UNCERTAIN
    )

    replay, created_again = substrate.claim_transport_attempt(
        reservation.message.message_id,
        claimer_id="sender:stand-in",
    )
    assert created_again is False
    assert replay.attempt_id == attempt.attempt_id
    assert replay.state is TransportAttemptState.OUTCOME_UNKNOWN
    assert len(substrate.list_transport_attempts()) == 1


def test_cancellation_pending_blocks_a_new_attempt_claim(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated
    reservation = _reserve(coordinator, task_id, binding)
    task = task_store.get_task(task_id)
    updated = task_store.conditional_update(
        task_id,
        fields={"state": TaskState.CANCELLATION_PENDING.value},
        expected_state_version=task.state_version,
    )
    assert updated is not None

    with pytest.raises(AttemptClaimBlocked) as raised:
        substrate.claim_transport_attempt(
            reservation.message.message_id,
            claimer_id="sender:stand-in",
        )
    assert raised.value.reason == "task_not_dispatchable:cancellation_pending"
    assert substrate.list_transport_attempts() == []


def test_stale_state_version_leaves_no_command_or_message(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated

    with pytest.raises(InteractionStateConflict):
        _reserve(
            coordinator,
            task_id,
            binding,
            requested_state_version=1,
        )

    assert task_store.list_commands(task_id) == []
    assert substrate.list_messages(task_id=task_id) == []


def test_supply_input_preserves_exact_checkpoint_identity(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated
    checkpoint = task_store.create_checkpoint(
        task_id,
        kind="controller_input",
        required_state_version=0,
    )

    reservation = _reserve(
        coordinator,
        task_id,
        binding,
        command_kind=TaskCommandKind.SUPPLY_INPUT,
        message_class=MessageClass.DECISION,
        checkpoint_id=checkpoint.checkpoint_id,
        idempotency_key="input-1",
        payload="approve bounded continuation",
    )
    assert reservation.message.checkpoint_id == checkpoint.checkpoint_id
    assert reservation.message.message_class is MessageClass.DECISION

    with pytest.raises(CanonicalBindingMismatch):
        _reserve(
            coordinator,
            task_id,
            binding,
            command_kind=TaskCommandKind.SUPPLY_INPUT,
            message_class=MessageClass.DECISION,
            checkpoint_id="taskckpt_20260802T000000Z_000000000000",
            idempotency_key="input-wrong-checkpoint",
        )
    assert len(substrate.list_messages(task_id=task_id)) == 1


def test_secret_payload_never_enters_command_or_message_rows(coordinated):
    coordinator, task_store, substrate, task_id, binding = coordinated
    secret = "secret-token-do-not-inline"
    reservation = _reserve(
        coordinator,
        task_id,
        binding,
        payload=secret,
    )

    with substrate._read() as conn:
        command = conn.execute(
            "SELECT * FROM task_commands WHERE command_id = ?",
            (reservation.command.command_id,),
        ).fetchone()
        message = conn.execute(
            "SELECT * FROM worker_messages WHERE message_id = ?",
            (reservation.message.message_id,),
        ).fetchone()
    assert all(secret not in str(value) for value in dict(command).values())
    assert all(secret not in str(value) for value in dict(message).values())
    assert substrate.read_payload(reservation.message.payload_ref) == secret.encode()
    assert len(task_store.list_commands(task_id)) == 1
