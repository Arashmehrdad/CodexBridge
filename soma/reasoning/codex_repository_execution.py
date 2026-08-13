"""One durable production Codex repository reasoning execution."""

from __future__ import annotations

import hashlib
import time

from .backends import ReasoningBackendObservationV1, start_request_hash
from .codex_repository_backend_support import ActiveRepositorySession
from .codex_repository_contract import semantic_prompt
from .models import ReasoningSpecV1
from .repository_evidence import semantic_output_schema


def execute_repository_reasoning(
    backend, spec: ReasoningSpecV1, backend_ref: str
) -> ReasoningBackendObservationV1:
    assignment, repository_root, source_loader = backend._validate_spec(spec)
    task_id = backend.task_id_resolver(backend_ref)
    if not task_id:
        from .codex_repository_backend_support import CodexRepositoryBackendError

        raise CodexRepositoryBackendError(
            "canonical task_id resolver returned no task identity"
        )

    backend.store.reserve_run(backend_ref=backend_ref, spec=spec)
    attempt, _created = backend.store.claim_start_attempt(
        backend_ref=backend_ref, spec=spec
    )
    if str(attempt["disposition"]) in {
        "accepted_bound",
        "rejected",
        "outcome_unknown",
    }:
        return backend.query(backend_ref)

    backend._validate_preflight(backend.preflight())
    client = backend.client_factory()
    session: ActiveRepositorySession | None = None
    boundary_entered = False
    bound = False
    try:
        thread_id = backend._thread_id(
            client.start_thread(
                working_directory=str(repository_root),
                model=backend.model,
            )
        )
        session = ActiveRepositorySession(client=client, thread_id=thread_id)
        with backend._active_lock:
            backend._active[backend_ref] = session

        request_hash = start_request_hash(spec, backend_ref)
        client_message_id = "soma-repository-" + hashlib.sha256(
            f"{backend_ref}\0{request_hash}".encode("utf-8")
        ).hexdigest()[:24]
        boundary_ref, boundary_hash = backend._artifact(
            backend_ref,
            "send_boundary.json",
            {
                "schema": "soma.reasoning.codex_repository.send_boundary.v1",
                "backend_ref": backend_ref,
                "start_request_hash": request_hash,
                "thread_id": thread_id,
                "client_user_message_id": client_message_id,
                "assignment_ref": spec.assignment_ref,
                "assignment_hash": spec.assignment_hash,
                "source_commit": assignment.source_commit,
            },
        )
        boundary_entered = backend.store.enter_send_boundary(
            backend_ref=backend_ref,
            request_hash=request_hash,
            evidence_ref=boundary_ref,
            evidence_hash=boundary_hash,
        )
        if not boundary_entered:
            return backend.query(backend_ref)

        client.begin_turn(
            thread_id=thread_id,
            prompt=semantic_prompt(assignment),
            client_user_message_id=client_message_id,
            output_schema=semantic_output_schema(),
            model=backend.model,
            effort=backend.effort,
        )
        turn_id = client.wait_for_turn_started(
            thread_id=thread_id,
            timeout_seconds=min(30.0, float(spec.budgets.wall_time_seconds)),
        )
        session.turn_id = turn_id
        operation_ref = backend._provider_operation_ref(thread_id, turn_id)
        binding_ref, binding_hash, binding_value = backend._binding(
            backend_ref, thread_id, turn_id, client_message_id
        )
        backend.store.record_accepted_bound(
            backend_ref=backend_ref,
            provider_operation_ref=operation_ref,
            provider_binding_ref=binding_ref,
            provider_binding_hash=binding_hash,
            provider_status_raw="in_progress",
            provider_terminal_claim="none",
            output_contract_disposition="not_available",
            continuation_ref=f"codex:thread:{thread_id}",
            last_event_cursor="0",
        )
        bound = True
        session.binding_settled.set()

        started_at = time.monotonic()
        turn = client.wait_for_turn_completed(
            thread_id=thread_id,
            turn_id=turn_id,
            timeout_seconds=float(spec.budgets.wall_time_seconds),
        )
        wall_time = max(0.0, time.monotonic() - started_at)
        usage = backend.extract_usage(turn.token_usage_events)
        if turn.agent_message or usage["total_tokens"] > 0:
            backend._artifact(
                backend_ref,
                "model_generation_observed.json",
                {
                    "schema": "soma.reasoning.codex_repository.model_generation_observed.v1",
                    "provider_operation_ref": operation_ref,
                    "provider_status": turn.status,
                    "agent_message_present": bool(turn.agent_message),
                    "usage": usage,
                },
            )

        if turn.status == "interrupted":
            current = backend.store.query(backend_ref)
            if current.cancellation_disposition == "uncertain":
                session.cancellation_settled.wait(timeout=5)
                current = backend.store.query(backend_ref)
            if current.cancellation_disposition in {"accepted", "uncertain"}:
                return current
            backend._record_terminal_without_result(
                backend_ref=backend_ref,
                operation_ref=operation_ref,
                binding_ref=binding_ref,
                binding_hash=binding_hash,
                provider_status="interrupted",
                terminal_claim="incomplete",
                events=turn.events,
                terminal_error=turn.terminal_error,
            )
            return backend.query(backend_ref)
        if turn.status != "completed":
            backend._record_terminal_without_result(
                backend_ref=backend_ref,
                operation_ref=operation_ref,
                binding_ref=binding_ref,
                binding_hash=binding_hash,
                provider_status=turn.status or "failed",
                terminal_claim="failure",
                events=turn.events,
                terminal_error=turn.terminal_error,
            )
            return backend.query(backend_ref)

        backend.store.record_accepted_bound(
            backend_ref=backend_ref,
            provider_operation_ref=operation_ref,
            provider_binding_ref=binding_ref,
            provider_binding_hash=binding_hash,
            provider_status_raw="completed",
            provider_terminal_claim="success",
            output_contract_disposition="not_available",
            continuation_ref=f"codex:thread:{thread_id}",
            last_event_cursor=str(len(turn.events)),
        )
        from .codex_repository_publication import publish_repository_turn

        publish_repository_turn(
            backend=backend,
            spec=spec,
            assignment=assignment,
            source_loader=source_loader,
            task_id=task_id,
            backend_ref=backend_ref,
            operation_ref=operation_ref,
            binding_ref=binding_ref,
            binding_hash=binding_hash,
            binding_value=binding_value,
            turn=turn,
            wall_time=wall_time,
            usage=usage,
        )
        return backend.query(backend_ref)
    except BaseException:
        if boundary_entered and not bound:
            return backend.query(backend_ref)
        raise
    finally:
        if session is not None:
            session.binding_settled.set()
        with backend._active_lock:
            if backend._active.get(backend_ref) is session:
                backend._active.pop(backend_ref, None)
        client.close()
