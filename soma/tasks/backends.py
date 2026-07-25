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

from .models import BackendKind, DURABLE_RUN_EXECUTOR


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

    def start(self, spec: DurableCommandSpec, backend_ref: str) -> dict[str, Any]:
        """Delegate to the engine using the already reserved backend reference."""

    def query(self, backend_ref: str) -> BackendObservation:
        """Return the bounded scalar backend observation."""

    def cancel(self, backend_ref: str) -> dict[str, Any]:
        """Delegate cancellation to the engine that owns the process tree."""

    def result_reference(self, backend_ref: str) -> dict[str, Any]:
        """Return authoritative-result identity and hashes, not the body."""


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
