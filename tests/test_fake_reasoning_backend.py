"""G2.2 deterministic fake reasoning backend behavior and recovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from soma.reasoning.fake import FakeReasoningBackend, FakeReasoningCrashBeforeSend
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.store import ReasoningBackendStore


def _hash(character: str) -> str:
    return character * 64


def _spec() -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:fake-backend",
        assignment_hash=_hash("1"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("2"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("3"),
        authority_ref="authority:fake-backend",
        authority_hash=_hash("4"),
        provider_route_ref="route:fake-reasoning",
        provider_route_hash=_hash("5"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _store(tmp_path: Path) -> ReasoningBackendStore:
    return ReasoningBackendStore(tmp_path / "runs")


def test_success_binds_provider_and_publishes_bounded_result(tmp_path: Path) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="success")
    spec = _spec()
    backend_ref = backend.reserve()

    observation = backend.start(spec, backend_ref)
    result = backend.result_reference(backend_ref)

    assert backend.provider_create_calls == 1
    assert observation.start_delivery_disposition == "accepted_bound"
    assert observation.provider_binding_disposition == "bound"
    assert observation.provider_terminal_claim == "success"
    assert observation.output_contract_disposition == "valid"
    assert observation.result_ref is not None
    assert result is not None
    assert result.output_contract_version == "evidence_submission.v1"
    assert result.evidence_submission_ref == observation.result_ref
    assert "transcript" not in result.model_dump(mode="python")
    assert store.table_counts() == {
        "reasoning_backend_runs": 1,
        "reasoning_backend_start_attempts": 1,
    }


def test_success_start_replay_never_calls_fake_provider_twice(tmp_path: Path) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="success")
    spec = _spec()
    backend_ref = backend.reserve()
    first = backend.start(spec, backend_ref)

    replay = backend.start(spec, backend_ref)

    assert backend.provider_create_calls == 1
    assert replay == first
    assert store.table_counts()["reasoning_backend_start_attempts"] == 1


def test_provider_rejection_is_definite_and_unbound(tmp_path: Path) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="provider_rejection")
    observation = backend.start(_spec(), backend.reserve())

    assert backend.provider_create_calls == 1
    assert observation.start_delivery_disposition == "rejected"
    assert observation.provider_binding_disposition == "unbound"
    assert observation.provider_terminal_claim == "failure"
    assert observation.output_contract_disposition == "not_available"
    assert observation.error_code == "fake_provider_rejected"


def test_long_running_backend_is_cancellable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="long_running")
    backend_ref = backend.reserve()
    running = backend.start(_spec(), backend_ref)

    assert running.provider_status_raw == "in_progress"
    assert running.provider_terminal_claim == "none"
    assert running.continuation_ref is not None

    cancelled = backend.cancel(backend_ref)
    assert backend.provider_cancel_calls == 1
    assert cancelled.cancellation_disposition == "accepted"
    assert cancelled.provider_status_raw == "cancelled"
    assert cancelled.provider_terminal_claim == "cancelled"


def test_malformed_output_never_publishes_success_reference(tmp_path: Path) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="malformed_output")
    backend_ref = backend.reserve()
    observation = backend.start(_spec(), backend_ref)

    assert observation.start_delivery_disposition == "accepted_bound"
    assert observation.provider_binding_disposition == "bound"
    assert observation.provider_terminal_claim == "success"
    assert observation.output_contract_disposition == "invalid"
    assert observation.error_code == "invalid_output_contract"
    assert observation.result_ref is None
    assert backend.result_reference(backend_ref) is None


def test_scripted_result_publication_is_separate_from_provider_acceptance(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="result_publication")
    backend_ref = backend.reserve()
    running = backend.start(_spec(), backend_ref)

    assert running.provider_terminal_claim == "none"
    assert running.result_ref is None
    assert backend.result_reference(backend_ref) is None

    published = backend.publish_scripted_result(backend_ref)
    assert published.provider_terminal_claim == "success"
    assert published.output_contract_disposition == "valid"
    assert published.result_ref is not None
    assert backend.result_reference(backend_ref) is not None


def test_crash_before_send_is_safely_recoverable_with_same_start_attempt(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    spec = _spec()
    crashing = FakeReasoningBackend(store, case="crash_before_send")
    backend_ref = crashing.reserve()

    with pytest.raises(FakeReasoningCrashBeforeSend):
        crashing.start(spec, backend_ref)

    after_crash = crashing.query(backend_ref)
    attempt_before = store.start_attempt(backend_ref)
    assert crashing.provider_create_calls == 0
    assert after_crash.start_delivery_disposition == "claimed_not_sent"
    assert attempt_before["disposition"] == "claimed_not_sent"

    recovered = FakeReasoningBackend(store, case="success")
    result = recovered.start(spec, backend_ref)
    attempt_after = store.start_attempt(backend_ref)

    assert recovered.provider_create_calls == 1
    assert attempt_after["start_attempt_id"] == attempt_before["start_attempt_id"]
    assert result.start_delivery_disposition == "accepted_bound"
    assert result.provider_terminal_claim == "success"
    assert store.table_counts()["reasoning_backend_start_attempts"] == 1


def test_ambiguous_create_ack_is_outcome_unknown_and_never_auto_resubmitted(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="ambiguous_ack")
    spec = _spec()
    backend_ref = backend.reserve()

    first = backend.start(spec, backend_ref)
    replay = backend.start(spec, backend_ref)

    assert backend.provider_create_calls == 1
    assert first.start_delivery_disposition == "outcome_unknown"
    assert first.provider_binding_disposition == "uncertain"
    assert first.provider_operation_ref is None
    assert replay == first
    assert store.start_attempt(backend_ref)["disposition"] == "outcome_unknown"
    assert store.table_counts()["reasoning_backend_start_attempts"] == 1


def test_ambiguous_binding_cancellation_is_uncertain_not_fabricated_success(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    backend = FakeReasoningBackend(store, case="ambiguous_ack")
    backend_ref = backend.reserve()
    backend.start(_spec(), backend_ref)

    cancelled = backend.cancel(backend_ref)
    assert backend.provider_cancel_calls == 0
    assert cancelled.cancellation_disposition == "uncertain"
    assert cancelled.provider_binding_disposition == "uncertain"
    assert cancelled.provider_terminal_claim == "none"


def test_restart_query_recovery_uses_only_backend_ref(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = ReasoningBackendStore(runs_dir)
    backend = FakeReasoningBackend(store, case="long_running")
    spec = _spec()
    backend_ref = backend.reserve()
    before = backend.start(spec, backend_ref)
    assert before.provider_status_raw == "in_progress"

    restarted_store = ReasoningBackendStore(runs_dir)
    restarted_backend = FakeReasoningBackend(restarted_store, case="provider_rejection")
    recovered = restarted_backend.query(backend_ref)

    assert recovered == before
    assert restarted_backend.provider_create_calls == 0
    assert recovered.provider_operation_ref is not None


def test_reserve_allocates_unique_soma_owned_backend_refs(tmp_path: Path) -> None:
    backend = FakeReasoningBackend(_store(tmp_path), case="success")
    first = backend.reserve()
    second = backend.reserve()
    assert first != second
    assert first.startswith("reasoning_")
    assert second.startswith("reasoning_")
