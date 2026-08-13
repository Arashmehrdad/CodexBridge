"""Compact public projections for the canonical task plane.

Task responses are compact projections that *reference* existing authoritative
evidence. They never duplicate stdout, stderr, manifests, durable inputs, or
run result bodies, and they never carry a secret-bearing request payload.
"""

from __future__ import annotations

import json
from typing import Any

from soma.public_projection_contract import (
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
)

from .backends import BackendObservation
from .models import (
    TASK_MODEL_VERSION,
    TASK_SCHEMA_VERSION,
    BackendKind,
    TaskCommandKind,
    TaskKind,
    TaskLink,
    TaskLinkType,
    TaskRecord,
    TaskState,
    TERMINAL_TASK_STATES,
)


TASK_RESPONSE_BUDGET_BYTES = 12 * 1024
TASK_EVENT_DEFAULT_LIMIT = 20
TASK_EVENT_MAX_LIMIT = 500
TASK_LINK_DEFAULT_LIMIT = 50
TASK_LINK_MAX_LIMIT = 200


def response_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _envelope(budget: int) -> dict[str, Any]:
    return {
        "view": "compact",
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "task_model_version": TASK_MODEL_VERSION,
        "task_schema_version": TASK_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "truncated": False,
        "has_more": False,
        "response_budget_bytes": budget,
        "response_bytes": 0,
    }


# Room reserved while trimming so the self-describing ``response_bytes`` value
# can grow without pushing a finalized payload past its declared budget.
_SELF_DESCRIPTION_ALLOWANCE = 16


def finalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Set ``response_bytes`` to the size of the complete serialized payload."""
    payload["response_bytes"] = 0
    for _ in range(4):
        size = response_bytes(payload)
        if payload["response_bytes"] == size:
            break
        payload["response_bytes"] = size
    return payload


def _task_request(operation: str, task_id: str, project_id: str = "") -> dict[str, Any]:
    request = {"operation": operation, "task_id": task_id}
    if project_id:
        request["project_id"] = project_id
    return request


def status_retrieval(task_id: str, project_id: str = "") -> dict[str, Any]:
    return {
        "tool": "task_query",
        "request": _task_request("status", task_id, project_id),
    }


def result_retrieval(task_id: str, project_id: str = "") -> dict[str, Any]:
    return {
        "tool": "task_query",
        "request": _task_request("result", task_id, project_id),
    }


def evidence_retrieval(task_id: str, project_id: str = "") -> dict[str, Any]:
    return {
        "tool": "task_query",
        "request": _task_request("evidence", task_id, project_id),
    }


def _run_request(operation: str, run_id: str, project_id: str = "") -> dict[str, Any]:
    request = {"operation": operation, "run_id": run_id}
    if project_id:
        request["project_id"] = project_id
    return request


def backend_terminal_retrieval(run_id: str, project_id: str = "") -> dict[str, Any]:
    return {
        "tool": "run_query",
        "request": _run_request("terminal", run_id, project_id),
    }


def backend_evidence_retrieval(run_id: str, project_id: str = "") -> dict[str, Any]:
    return {
        "tool": "run_query",
        "request": _run_request("input", run_id, project_id),
    }


def _identity_fields(
    task: TaskRecord,
    observation: BackendObservation | None,
    project_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backend_status = observation.status if observation and observation.exists else ""
    fields = {
        "task_id": task.task_id,
        "parent_task_id": task.parent_task_id,
        "task_kind": task.task_kind.value,
        "controller_request_id": task.controller_request_id,
        "state": task.state.value,
        "phase": task.phase.value,
        "state_version": task.state_version,
        "terminal": task.state in TERMINAL_TASK_STATES,
        "backend_kind": task.backend_kind.value,
        "backend_executor": task.backend_executor,
        "backend_reference": task.backend_ref,
        "backend_status": backend_status,
        "backend_present": bool(observation.exists) if observation else False,
        "workspace_kind": task.workspace_kind,
        "workspace_ref": task.workspace_ref,
        "recovery_state": task.recovery_state.value,
        "recovery_reason": task.recovery_reason,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "ended_at": task.ended_at,
        "reconciled_at": task.reconciled_at,
    }
    fields.update(project_scope or {"project_binding_status": "legacy_unassigned"})
    return fields


def compact_task_status(
    task: TaskRecord,
    *,
    observation: BackendObservation | None = None,
    open_checkpoint_count: int = 0,
    link_counts: dict[str, int] | None = None,
    operation: str = "status",
    budget: int = TASK_RESPONSE_BUDGET_BYTES,
    extra: dict[str, Any] | None = None,
    project_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id = str((project_scope or {}).get("project_id") or "")
    payload: dict[str, Any] = {
        "ok": True,
        "operation": operation,
        **_identity_fields(task, observation, project_scope),
        "checkpoint": {
            "open_count": int(open_checkpoint_count),
            "checkpoint_ref": task.checkpoint_ref,
        },
        "link_counts": dict(link_counts or {}),
        "objective_reference": task.objective_ref,
        "constraints_reference": task.constraints_ref,
        "result_available": bool(task.result_ref),
        "result_retrieval": result_retrieval(task.task_id, project_id),
        "status_retrieval": status_retrieval(task.task_id, project_id),
        "error": "",
        **_envelope(budget),
    }
    if task.backend_ref and task.backend_kind is BackendKind.SOMA_DURABLE_RUN:
        payload["backend_evidence_retrieval"] = backend_evidence_retrieval(
            task.backend_ref, project_id
        )
        payload["authoritative_result_retrieval"] = backend_terminal_retrieval(
            task.backend_ref, project_id
        )
    if extra:
        payload.update(extra)
    return finalize(payload)


def compact_task_result(
    task: TaskRecord,
    *,
    observation: BackendObservation | None,
    result_source: dict[str, Any],
    budget: int = TASK_RESPONSE_BUDGET_BYTES,
    project_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_id = str((project_scope or {}).get("project_id") or "")
    payload: dict[str, Any] = {
        "ok": True,
        "operation": "result",
        **_identity_fields(task, observation, project_scope),
        "result_available": bool(task.result_ref),
        "result_reference": task.result_ref,
        "result_hash": task.result_hash,
        "evidence_reference": task.evidence_ref,
        "result_authority": (
            "durable_run"
            if task.backend_kind is BackendKind.SOMA_DURABLE_RUN
            else "reasoning_backend"
        ),
        "result_source": dict(result_source),
        "result_duplicated_into_task": False,
        "error": "",
        **_envelope(budget),
    }
    if task.backend_ref and task.backend_kind is BackendKind.SOMA_DURABLE_RUN:
        payload["authoritative_result_retrieval"] = backend_terminal_retrieval(
            task.backend_ref, project_id
        )
        complete_request = _run_request("result", task.backend_ref, project_id)
        complete_request["view"] = "full"
        payload["complete_result_retrieval"] = {
            "tool": "run_query",
            "request": complete_request,
        }
    elif task.backend_kind is BackendKind.SOMA_REASONING:
        payload["evidence_submission_retrieval"] = evidence_retrieval(
            task.task_id, project_id
        )
    return finalize(payload)


def compact_task_evidence(
    task: TaskRecord,
    *,
    observation: BackendObservation | None,
    evidence_source: dict[str, Any],
    budget: int,
    project_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a complete bounded EvidenceSubmission or a budget error; never truncate it."""
    submission = evidence_source.get("submission")
    payload: dict[str, Any] = {
        "ok": True,
        "operation": "evidence",
        **_identity_fields(task, observation, project_scope),
        "evidence_available": bool(evidence_source.get("available")),
        "evidence_authority": str(evidence_source.get("authority") or ""),
        "evidence_submission_ref": str(
            evidence_source.get("evidence_submission_ref") or ""
        ),
        "evidence_submission_hash": str(
            evidence_source.get("evidence_submission_hash") or ""
        ),
        "evidence_submission": submission,
        "raw_provider_events_included": False,
        "semantic_adjudication_performed_by_soma": False,
        "error": "",
        **_envelope(budget),
    }
    finalized = finalize(payload)
    required = response_bytes(finalized)
    if required <= budget:
        return finalized
    return task_error(
        operation="evidence",
        error_code="evidence_response_budget_too_small",
        error="EvidenceSubmission is complete-only and will not be semantically truncated",
        task_id=task.task_id,
        state=task.state.value,
        state_version=task.state_version,
        budget=budget,
        extra={
            "required_response_bytes": required,
            "maximum_response_budget_bytes": 64 * 1024,
            "evidence_submission_ref": str(
                evidence_source.get("evidence_submission_ref") or ""
            ),
            "evidence_submission_hash": str(
                evidence_source.get("evidence_submission_hash") or ""
            ),
        },
    )


def compact_task_links(
    task: TaskRecord,
    links: list[TaskLink],
    *,
    limit: int,
    budget: int = TASK_RESPONSE_BUDGET_BYTES,
    project_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    projected = [
        {
            "link_type": link.link_type.value,
            "target_kind": link.target_kind.value,
            "target_id": link.target_id,
            "created_at": link.created_at,
        }
        for link in links
    ]
    payload: dict[str, Any] = {
        "ok": True,
        "operation": "links",
        "task_id": task.task_id,
        "state": task.state.value,
        "state_version": task.state_version,
        **(project_scope or {"project_binding_status": "legacy_unassigned"}),
        "links": projected,
        "returned_count": len(projected),
        "limit": limit,
        "error": "",
        **_envelope(budget),
    }
    limit_bytes = budget - _SELF_DESCRIPTION_ALLOWANCE
    while response_bytes(payload) > limit_bytes and payload["links"]:
        payload["links"].pop()
        payload["returned_count"] = len(payload["links"])
        payload["truncated"] = True
        payload["has_more"] = True
    return finalize(payload)


def compact_task_events(
    task: TaskRecord,
    events: list[Any],
    *,
    limit: int,
    after_id: int | None,
    latest_event_id: int,
    budget: int = TASK_RESPONSE_BUDGET_BYTES,
    project_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    projected = [
        {
            "id": event.id,
            "timestamp": event.timestamp,
            "level": event.level.value,
            "stage": event.stage,
            "message": event.message,
            "state": event.state,
            "state_version": event.state_version,
        }
        for event in events
    ]
    payload: dict[str, Any] = {
        "ok": True,
        "operation": "events",
        "task_id": task.task_id,
        "state": task.state.value,
        "state_version": task.state_version,
        **(project_scope or {"project_binding_status": "legacy_unassigned"}),
        "events": projected,
        "returned_count": len(projected),
        "limit": limit,
        "after_id": after_id,
        "latest_event_id": latest_event_id,
        "next_after_id": projected[-1]["id"] if projected else after_id,
        "error": "",
        **_envelope(budget),
    }
    payload["has_more"] = bool(
        projected and int(projected[-1]["id"]) < int(latest_event_id)
    )
    limit_bytes = budget - _SELF_DESCRIPTION_ALLOWANCE
    while response_bytes(payload) > limit_bytes and payload["events"]:
        payload["events"].pop()
        payload["returned_count"] = len(payload["events"])
        payload["truncated"] = True
        payload["has_more"] = True
        payload["next_after_id"] = (
            payload["events"][-1]["id"] if payload["events"] else after_id
        )
    return finalize(payload)


def task_capabilities(
    *,
    schema_state: dict[str, Any],
    reasoning_enabled: bool = False,
    reasoning_executor: str = "",
    budget: int = TASK_RESPONSE_BUDGET_BYTES,
) -> dict[str, Any]:
    task_kinds = [TaskKind.DURABLE_COMMAND.value]
    link_types = [
        TaskLinkType.PARENT.value,
        TaskLinkType.CHILD.value,
        TaskLinkType.BACKEND_RUN.value,
        TaskLinkType.RELATED.value,
        TaskLinkType.SUPERSEDES.value,
    ]
    backends = [
        {
            "backend_kind": BackendKind.SOMA_DURABLE_RUN.value,
            "executor": "executable_profile",
            "default": True,
            "description": (
                "Existing Soma durable run engine; owns worker, lease, "
                "cancellation, evidence, result, and recovery authority."
            ),
        }
    ]
    if reasoning_enabled:
        task_kinds.append(TaskKind.REASONING.value)
        link_types.append(TaskLinkType.BACKEND.value)
        backends.append(
            {
                "backend_kind": BackendKind.SOMA_REASONING.value,
                "executor": reasoning_executor or "configured_reasoning_backend",
                "default": False,
                "description": (
                    "Activated provider-neutral reasoning backend. The worker owns "
                    "semantic analysis; Soma owns mechanical lifecycle and evidence "
                    "materialization."
                ),
            }
        )

    payload: dict[str, Any] = {
        "ok": True,
        "operation": "capabilities",
        "task_kinds": task_kinds,
        "task_states": [state.value for state in TaskState],
        "terminal_task_states": sorted(state.value for state in TERMINAL_TASK_STATES),
        "link_types": link_types,
        "command_kinds": [command.value for command in TaskCommandKind],
        "backends": backends,
        "default_backend_kind": BackendKind.SOMA_DURABLE_RUN.value,
        "idempotency": {
            "keys": ["controller_request_id", "request_hash"],
            "same_request_returns_existing_task": True,
            "different_request_same_id_rejected": True,
        },
        "version_guarded_commands": [
            "cancel",
            "steer",
            "supply_input",
            "resolve_recovery",
        ],
        "interaction": {
            "public_commands": ["steer", "supply_input"],
            "exact_session_binding_required": True,
            "supply_input_checkpoint_required": True,
            "persist_before_send": True,
            "uncertain_attempts_are_not_resent": True,
            "payload_echoed": False,
            "production_transport_default": "unavailable",
        },
        "schema": dict(schema_state),
        "authority": {
            "task_identity": "task_store",
            "process_lifecycle": "durable_run_store",
            "result": "durable_run_store",
            "evidence": "durable_run_store",
        },
        "error": "",
        **_envelope(budget),
    }
    return finalize(payload)


def task_error(
    *,
    operation: str,
    error_code: str,
    error: str,
    task_id: str = "",
    state: str = "",
    state_version: int | None = None,
    budget: int = TASK_RESPONSE_BUDGET_BYTES,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "operation": operation,
        "task_id": task_id,
        "state": state,
        "error_code": error_code,
        "error": error,
        **_envelope(budget),
    }
    if state_version is not None:
        payload["state_version"] = state_version
    if extra:
        payload.update(extra)
    return finalize(payload)
