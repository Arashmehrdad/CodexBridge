"""Execution-backend contract and the first (default) backend.

The existing Soma durable run engine is the first and default backend. This
module adapts it; it does not fork its execution logic. A future optional
engine may be added as another backend, but backend selection is persisted at
task creation and must not change while a task is active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from soma.job_manager import JobManager, make_run_id
from soma.reasoning.backends import ReasoningBackend, ReasoningBackendObservationV1
from soma.reasoning.models import ReasoningSpecV1

from .models import BackendKind, DURABLE_RUN_EXECUTOR, REASONING_EXECUTOR


@dataclass(frozen=True)
class BackendObservation:
    """Bounded scalar view of one backend reference.

    Only scalars a canonical task needs for its own lifecycle decision are
    carried here. Output, result bodies, and diagnostics stay in the durable
    run evidence the task references.
    """

    exists: bool
    status: str = ""
    executor: str = ""
    repo_name: str = ""
    state_version: int = 0
    exit_code: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    result_publication_status: str = ""
    result_published_hash: str = ""
    result_published_at: str | None = None
    error_code: str = ""
    result_ref: str = ""
    evidence_ref: str = ""
    result_authority: str = ""


@dataclass(frozen=True)
class DurableCommandSpec:
    """Normalized launch intent for the durable-run backend."""

    repo_name: str
    profile_id: str
    argv: list[str]
    working_directory: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    stdin_text: str | None = None
    stdin_bytes: bytes | None = None
    timeout_seconds: int | None = None


class ExecutionBackend(Protocol):
    """One contract in front of current and future execution engines."""

    kind: str
    executor: str

    def reserve(self) -> str:
        """Allocate a backend reference without creating any durable work."""

    def start(self, spec: Any, backend_ref: str) -> dict[str, Any]:
        """Delegate to the selected engine using the reserved backend reference."""

    def query(self, backend_ref: str) -> BackendObservation:
        """Return the bounded scalar backend observation."""

    def cancel(self, backend_ref: str) -> dict[str, Any]:
        """Delegate cancellation to the engine that owns the process tree."""

    def result_reference(self, backend_ref: str) -> dict[str, Any]:
        """Return authoritative-result identity and hashes, not the body."""


class ReasoningTaskBackendAdapter:
    """Translate subordinate reasoning evidence into generic Task backend observations."""

    kind = BackendKind.SOMA_REASONING.value
    executor = REASONING_EXECUTOR

    def __init__(self, backend: ReasoningBackend):
        self._backend = backend

    @property
    def backend(self) -> ReasoningBackend:
        return self._backend

    def reserve(self) -> str:
        return self._backend.reserve()

    @staticmethod
    def _status(observation: ReasoningBackendObservationV1) -> str:
        if not observation.exists:
            return ""
        if observation.start_delivery_disposition == "rejected":
            return "failed"
        if observation.start_delivery_disposition == "outcome_unknown":
            return "recovery_pending"
        if observation.start_delivery_disposition in {"not_attempted", "claimed_not_sent"}:
            return "launch_pending"
        if observation.cancellation_disposition == "uncertain":
            return "recovery_pending"
        if observation.provider_terminal_claim == "cancelled":
            return "cancelled"
        if observation.provider_terminal_claim == "failure":
            return "failed"
        if observation.provider_terminal_claim == "incomplete":
            return "recovery_pending"
        if observation.provider_terminal_claim == "success":
            if observation.output_contract_disposition == "invalid":
                return "failed"
            if (
                observation.output_contract_disposition == "valid"
                and observation.result_ref
                and observation.result_hash
            ):
                return "completed"
            return "recovery_pending"
        if observation.provider_binding_disposition == "bound":
            return "running"
        return "recovery_pending"

    def _observation(self, backend_ref: str) -> BackendObservation:
        raw = self._backend.query(backend_ref)
        result = self._backend.result_reference(backend_ref)
        status = self._status(raw)
        published_at = result.published_at if result is not None else None
        result_hash = raw.result_hash or ""
        evidence_ref = raw.evidence_index_ref or raw.result_ref or ""
        return BackendObservation(
            exists=raw.exists,
            status=status,
            executor=self.executor,
            ended_at=(published_at if status in {"completed", "failed", "cancelled"} else None),
            result_publication_status=("published" if result is not None else "not_published"),
            result_published_hash=result_hash,
            result_published_at=published_at,
            error_code=raw.error_code or "",
            result_ref=raw.result_ref or "",
            evidence_ref=evidence_ref,
            result_authority="reasoning_backend",
        )

    def start(self, spec: ReasoningSpecV1, backend_ref: str) -> dict[str, Any]:
        raw = self._backend.start(spec, backend_ref)
        observation = self._observation(backend_ref)
        return {
            "accepted": raw.start_delivery_disposition != "rejected",
            "backend_ref": backend_ref,
            "status": observation.status,
            "reason": observation.error_code,
        }

    def query(self, backend_ref: str) -> BackendObservation:
        return self._observation(backend_ref)

    def cancel(self, backend_ref: str) -> dict[str, Any]:
        raw = self._backend.cancel(backend_ref)
        observation = self._observation(backend_ref)
        cancelled = raw.provider_terminal_claim == "cancelled"
        return {
            "ok": raw.cancellation_disposition in {"accepted", "rejected"},
            "backend_ref": backend_ref,
            "status": observation.status,
            "cancelled": cancelled,
            "termination_confirmed": cancelled,
            "reason": raw.error_code or raw.cancellation_disposition,
        }

    def result_reference(self, backend_ref: str) -> dict[str, Any]:
        result = self._backend.result_reference(backend_ref)
        if result is None:
            return {
                "available": False,
                "authority": "reasoning_backend",
                "backend_ref": backend_ref,
            }
        return {
            "available": True,
            "authority": "reasoning_backend",
            "backend_ref": backend_ref,
            "output_contract_version": result.output_contract_version,
            "evidence_submission_ref": result.evidence_submission_ref,
            "evidence_submission_hash": result.evidence_submission_hash,
            "provider_binding_ref": result.provider_binding_ref,
            "provider_binding_hash": result.provider_binding_hash,
            "provider_provenance_index_ref": result.provider_provenance_index_ref,
            "provider_provenance_index_hash": result.provider_provenance_index_hash,
            "raw_provider_evidence_root_ref": result.raw_provider_evidence_root_ref,
            "raw_provider_evidence_root_hash": result.raw_provider_evidence_root_hash,
            "usage_ref": result.usage_ref or "",
            "usage_hash": result.usage_hash or "",
            "published_at": result.published_at,
        }


class DurableRunBackend:
    """Adapter over the existing durable run engine."""

    kind = BackendKind.SOMA_DURABLE_RUN.value
    executor = DURABLE_RUN_EXECUTOR

    def __init__(self, job_manager: JobManager):
        self._manager = job_manager

    @property
    def manager(self) -> JobManager:
        return self._manager

    def reserve(self) -> str:
        # Reserving the durable run identity before the task row is committed
        # is what makes a restart or retry unable to create a second run for
        # the same task: the identity is already owned by the task.
        return make_run_id(self.executor)

    def start(self, spec: DurableCommandSpec, backend_ref: str) -> dict[str, Any]:
        return self._manager.start_executable_profile(
            spec.repo_name,
            spec.profile_id,
            list(spec.argv),
            working_directory=spec.working_directory,
            environment=dict(spec.environment),
            stdin_text=spec.stdin_text,
            stdin_bytes=spec.stdin_bytes,
            timeout_seconds=spec.timeout_seconds,
            reserved_run_id=backend_ref,
        )

    def query(self, backend_ref: str) -> BackendObservation:
        if not backend_ref:
            return BackendObservation(exists=False, error_code="missing_backend_ref")
        try:
            summary = self._manager.store.get_run_summary(backend_ref)
        except KeyError:
            return BackendObservation(exists=False, error_code="backend_run_not_found")
        except ValueError:
            return BackendObservation(
                exists=False, error_code="invalid_backend_reference"
            )
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

    def cancel(self, backend_ref: str) -> dict[str, Any]:
        return self._manager.cancel_run(backend_ref)

    def result_reference(self, backend_ref: str) -> dict[str, Any]:
        """Return only the authoritative result identity, status, and hashes."""
        try:
            snapshot = self._manager.store.get_public_result_snapshot(backend_ref)
        except (KeyError, ValueError):
            return {
                "available": False,
                "authority": "durable_run",
                "run_id": backend_ref,
            }
        return {
            "available": True,
            "authority": "durable_run",
            "run_id": str(snapshot.get("run_id") or backend_ref),
            "backend_status": str(snapshot.get("status") or ""),
            "exit_code": snapshot.get("exit_code"),
            "public_result_schema_version": str(
                snapshot.get("public_result_schema_version") or ""
            ),
            "public_result_status": str(snapshot.get("public_result_status") or ""),
            "public_result_source_sha256": str(
                snapshot.get("public_result_source_sha256") or ""
            ),
        }
