"""Bounded publication for completed production repository reasoning turns."""

from __future__ import annotations

import hashlib

from soma.worker_evidence.models import (
    EVIDENCE_SUBMISSION_SCHEMA_VERSION,
    EvidenceWorkIdentityV1,
)

from .repository_evidence import (
    RepositoryEvidenceError,
    build_evidence_submission,
    parse_semantic_output,
)


def publish_repository_turn(
    *,
    backend,
    spec,
    assignment,
    source_loader,
    task_id: str,
    backend_ref: str,
    operation_ref: str,
    binding_ref: str,
    binding_hash: str,
    binding_value: dict,
    turn,
    wall_time: float,
    usage: dict[str, int],
) -> None:
    event_ref, event_hash = backend._artifact(
        backend_ref, "provider_events.json", list(turn.events)
    )
    usage_ref, usage_hash = backend._artifact(backend_ref, "usage.json", usage)
    if backend._active.get(backend_ref) is not None:
        client = backend._active[backend_ref].client
    else:
        client = None
    if client is not None and client.server_requests:
        backend.store.record_invalid_output(
            backend_ref=backend_ref,
            provider_operation_ref=operation_ref,
            provider_binding_ref=binding_ref,
            provider_binding_hash=binding_hash,
            error_code="provider_requested_disallowed_capability",
        )
        backend.store.record_terminal_evidence(
            backend_ref=backend_ref,
            raw_provider_evidence_root_ref=event_ref,
            raw_provider_evidence_root_hash=event_hash,
            error_code="provider_requested_disallowed_capability",
        )
        return

    try:
        semantic = parse_semantic_output(turn.agent_message)
        provenance_ref, provenance_hash = backend._artifact(
            backend_ref,
            "provider_provenance.json",
            {
                "schema": "soma.reasoning.codex_repository.provenance.v1",
                "provider_operation_ref": operation_ref,
                "provider_binding": binding_value,
                "source_commit": assignment.source_commit,
                "provider_event_count": len(turn.events),
                "provider_event_root_ref": event_ref,
                "provider_event_root_hash": event_hash,
            },
        )
        submission = build_evidence_submission(
            payload=semantic,
            loader=source_loader,
            source_revision_ref=source_loader.source_revision_ref,
            work_identity=EvidenceWorkIdentityV1(
                task_id=task_id,
                backend_ref=backend_ref,
            ),
            assignment_ref=spec.assignment_ref,
            assignment_hash=spec.assignment_hash,
            backend_kind=backend.kind,
            provider="codex",
            model_or_profile=backend.model,
            native_session_ref=binding_value["thread_id"],
            wall_time_seconds=wall_time,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            provenance_refs=(
                (binding_ref, binding_hash),
                (provenance_ref, provenance_hash),
            ),
        )
        submission_ref, submission_hash = backend._artifact(
            backend_ref,
            "evidence_submission.json",
            submission.model_dump(mode="json"),
        )
        evidence_index_ref, evidence_index_hash = backend._artifact(
            backend_ref,
            "evidence_index.json",
            {
                "schema": "soma.reasoning.codex_repository.evidence_index.v1",
                "submission_ref": submission_ref,
                "submission_hash": submission_hash,
                "records": [
                    {
                        "evidence_id": item.evidence_id,
                        "source_ref": item.source_ref,
                        "source_hash": item.source_hash,
                        "locator": item.locator,
                    }
                    for item in submission.evidence
                ],
            },
        )
        backend.store.publish_result(
            backend_ref=backend_ref,
            output_contract_version=EVIDENCE_SUBMISSION_SCHEMA_VERSION,
            evidence_submission_ref=submission_ref,
            evidence_submission_hash=submission_hash,
            evidence_index_ref=evidence_index_ref,
            evidence_index_hash=evidence_index_hash,
            provider_provenance_index_ref=provenance_ref,
            provider_provenance_index_hash=provenance_hash,
            raw_provider_evidence_root_ref=event_ref,
            raw_provider_evidence_root_hash=event_hash,
            usage_ref=usage_ref,
            usage_hash=usage_hash,
            usage_summary=usage,
        )
    except (RepositoryEvidenceError, ValueError) as exc:
        diagnostic_ref, diagnostic_hash = backend._artifact(
            backend_ref,
            "invalid_output_evidence.json",
            {
                "schema": "soma.reasoning.codex_repository.invalid_output.v1",
                "provider_operation_ref": operation_ref,
                "validation_error_type": type(exc).__name__,
                "validation_error": str(exc),
                "agent_message_sha256": hashlib.sha256(
                    turn.agent_message.encode("utf-8")
                ).hexdigest(),
            },
        )
        backend.store.record_invalid_output(
            backend_ref=backend_ref,
            provider_operation_ref=operation_ref,
            provider_binding_ref=binding_ref,
            provider_binding_hash=binding_hash,
            error_code="invalid_repository_output",
        )
        backend.store.record_terminal_evidence(
            backend_ref=backend_ref,
            raw_provider_evidence_root_ref=diagnostic_ref,
            raw_provider_evidence_root_hash=diagnostic_hash,
            error_code="invalid_repository_output",
        )
