from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Callable, Mapping
from uuid import uuid4

from .hermes_companion_protocol import (
    PINNED_HERMES_REVISION,
    HermesCompanionProtocolError,
    HermesInterfaceDriftError,
)
from .hermes_service import (
    HermesServiceError,
    HermesServiceNotReadyError,
    HermesServiceOwnershipError,
    HermesServiceRequest,
)
from .hermes_service_process import (
    PersistentHermesWorker,
    PersistentHermesWorkerConfig,
)
from .hermes_service_supervisor import (
    HermesServiceSupervisor,
    HermesSupervisorConfig,
)

SHARED_EXECUTION_MODE = "shared_persistent_service"
FALLBACK_EXECUTION_MODE = "one_request_companion_fallback"

FallbackStarter = Callable[..., Mapping[str, Any]]
SupervisorFactory = Callable[[], HermesServiceSupervisor]


def _make_run_id() -> str:
    # Local import avoids a module cycle at import time.
    from .job_manager import make_run_id

    return make_run_id("hermes_service")


class HermesServiceGateway:
    """Public routing for the shared persistent Hermes service.

    Every invocation gets a distinct durable CodexBridge run ID plus a
    distinct Hermes request ID bound to the caller's session. Results,
    cancellation, and publication are isolated per run: reads and cancels
    require the owning (run_id, request_id, session_id) triple. When the
    shared service is unavailable, the gateway takes exactly one explicit,
    bounded fallback to the H1 one-request companion path and labels the
    response with the fallback execution mode and reason.
    """

    def __init__(
        self,
        *,
        run_store: Any,
        runs_dir: str | Path,
        supervisor_factory: SupervisorFactory,
        fallback_starter: FallbackStarter | None = None,
    ) -> None:
        self._run_store = run_store
        self._runs_dir = Path(runs_dir)
        self._supervisor_factory = supervisor_factory
        self._fallback_starter = fallback_starter
        self._state_lock = Lock()
        self._creation_lock = Lock()
        self._supervisor: HermesServiceSupervisor | None = None
        self._service_error = ""
        self._active: dict[str, dict[str, Any]] = {}

    # -- service lifecycle -------------------------------------------------

    def _ensure_service(
        self,
    ) -> tuple[HermesServiceSupervisor | None, str]:
        with self._state_lock:
            if self._supervisor is not None:
                return self._supervisor, ""
            if self._service_error:
                return None, self._service_error
        with self._creation_lock:
            with self._state_lock:
                if self._supervisor is not None:
                    return self._supervisor, ""
                if self._service_error:
                    return None, self._service_error
            try:
                supervisor = self._supervisor_factory()
            except Exception as exc:
                reason = f"shared Hermes service failed to start: {exc}"
                with self._state_lock:
                    self._service_error = reason
                return None, reason
            with self._state_lock:
                self._supervisor = supervisor
            return supervisor, ""

    def retry_service(self) -> dict[str, Any]:
        """Administrative reset of a recorded service-start failure."""
        with self._state_lock:
            previous_error = self._service_error
            self._service_error = ""
        supervisor, reason = self._ensure_service()
        return {
            "ok": supervisor is not None,
            "previous_error": previous_error,
            "service_error": reason,
        }

    def close(self) -> None:
        with self._state_lock:
            supervisor = self._supervisor
            self._supervisor = None
        if supervisor is not None:
            supervisor.close()

    # -- public request path -----------------------------------------------

    def execute(
        self,
        *,
        session_id: str,
        operation: str,
        payload: Mapping[str, Any],
        expected_registry_generation: int,
        expected_schema_hash: str,
        worker_wait_timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        supervisor, unavailable_reason = self._ensure_service()
        if supervisor is None:
            return self._fallback(
                reason=unavailable_reason,
                operation=operation,
                payload=payload,
                expected_registry_generation=expected_registry_generation,
                expected_schema_hash=expected_schema_hash,
            )

        run_id = _make_run_id()
        request_id = f"hsr-{uuid4().hex}"
        request = HermesServiceRequest(
            run_id=run_id,
            request_id=request_id,
            session_id=session_id,
            operation=operation,
            payload=payload,
            expected_registry_generation=expected_registry_generation,
            expected_schema_hash=expected_schema_hash,
            worker_wait_timeout_seconds=worker_wait_timeout_seconds,
        )
        run_dir = self._runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        created = self._run_store.create_run(
            run_id=run_id,
            repo_name="hermes-service",
            tool="hermes_service",
            run_dir=run_dir,
            input_data={
                "session_id": session_id,
                "request_id": request_id,
                "operation": operation,
                "expected_registry_generation": (
                    expected_registry_generation
                ),
                "expected_schema_hash": expected_schema_hash,
                "execution_mode": SHARED_EXECUTION_MODE,
            },
            status="running",
        )
        with self._state_lock:
            self._active[request_id] = {
                "run_id": run_id,
                "session_id": session_id,
                "cancelled": False,
            }
        try:
            result = supervisor.execute(request)
        except HermesServiceNotReadyError as exc:
            self._finish_failed(created, error=str(exc))
            response = self._error_response(
                request, error=str(exc), error_type="service_not_ready"
            )
            if self._fallback_starter is not None:
                response["fallback"] = self._fallback(
                    reason=str(exc),
                    operation=operation,
                    payload=payload,
                    expected_registry_generation=(
                        expected_registry_generation
                    ),
                    expected_schema_hash=expected_schema_hash,
                )
            return response
        except HermesInterfaceDriftError as exc:
            # Stale schema-bound requests fail closed; no fallback may
            # execute a request the shared service just refused.
            self._finish_failed(created, error=str(exc))
            return self._error_response(
                request, error=str(exc), error_type="stale_identity"
            )
        except HermesServiceOwnershipError as exc:
            status = (
                "cancelled" if self._was_cancelled(request_id) else "failed"
            )
            self._finish_failed(created, error=str(exc), status=status)
            return self._error_response(
                request,
                error=str(exc),
                error_type="ownership",
                status=status,
            )
        except (HermesServiceError, HermesCompanionProtocolError) as exc:
            cancelled = self._was_cancelled(request_id)
            status = "cancelled" if cancelled else "failed"
            self._finish_failed(created, error=str(exc), status=status)
            return self._error_response(
                request,
                error=str(exc),
                error_type="cancelled" if cancelled else "service_error",
                status=status,
            )
        finally:
            with self._state_lock:
                self._active.pop(request_id, None)

        result_dict = result.as_dict()
        self._run_store.transition_terminal(
            run_id,
            status="completed",
            result=result_dict,
            expected_statuses=("running",),
            expected_state_version=int(created["state_version"]),
            exit_code=0,
            summary=f"hermes {operation} served by shared service",
        )
        return {
            "ok": True,
            "run_id": run_id,
            "request_id": request_id,
            "session_id": session_id,
            "status": "completed",
            **result_dict,
        }

    def cancel(
        self, *, run_id: str, request_id: str, session_id: str
    ) -> dict[str, Any]:
        with self._state_lock:
            supervisor = self._supervisor
            entry = self._active.get(request_id)
            if (
                entry is not None
                and entry["run_id"] == run_id
                and entry["session_id"] == session_id
            ):
                entry["cancelled"] = True
        if supervisor is None:
            return {
                "cancelled": False,
                "error": "shared Hermes service is not running",
            }
        cancelled = supervisor.cancel(
            request_id=request_id,
            session_id=session_id,
            run_id=run_id,
        )
        return {"cancelled": bool(cancelled)}

    def get_result(
        self, *, run_id: str, session_id: str
    ) -> dict[str, Any]:
        run = self._run_store.get_run(run_id)
        input_data = run.get("input") or {}
        if not isinstance(input_data, Mapping):
            input_data = {}
        owner = str(input_data.get("session_id", ""))
        if not owner or owner != str(session_id):
            raise HermesServiceOwnershipError(
                "Hermes service result ownership mismatch"
            )
        return {
            "run_id": run["run_id"],
            "status": run["status"],
            "session_id": owner,
            "result": run.get("result") or {},
            "error": run.get("error") or "",
            "created_at": run.get("created_at"),
            "ended_at": run.get("ended_at"),
        }

    def health(self) -> dict[str, Any]:
        with self._state_lock:
            supervisor = self._supervisor
            service_error = self._service_error
        if supervisor is None:
            return {
                "ok": False,
                "state": "unavailable",
                "ready": False,
                "service_error": service_error,
                "fallback_available": self._fallback_starter is not None,
            }
        return {
            **supervisor.health(),
            "fallback_available": self._fallback_starter is not None,
        }

    def reload_registry(self) -> dict[str, Any]:
        supervisor, reason = self._ensure_service()
        if supervisor is None:
            raise HermesServiceNotReadyError(reason)
        return supervisor.reload_registry()

    # -- internals ---------------------------------------------------------

    def _was_cancelled(self, request_id: str) -> bool:
        with self._state_lock:
            entry = self._active.get(request_id)
            return bool(entry and entry["cancelled"])

    def _finish_failed(
        self,
        created: Mapping[str, Any],
        *,
        error: str,
        status: str = "failed",
    ) -> None:
        try:
            self._run_store.transition_terminal(
                str(created["run_id"]),
                status=status,
                result={"ok": False, "error": error},
                expected_statuses=("running",),
                expected_state_version=int(created["state_version"]),
                error=error,
            )
        except Exception:
            # Result-record failure must not mask the original error.
            pass

    @staticmethod
    def _error_response(
        request: HermesServiceRequest,
        *,
        error: str,
        error_type: str,
        status: str = "failed",
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "run_id": request.run_id,
            "request_id": request.request_id,
            "session_id": request.session_id,
            "status": status,
            "error": error,
            "error_type": error_type,
            "execution_mode": SHARED_EXECUTION_MODE,
        }

    def _fallback(
        self,
        *,
        reason: str,
        operation: str,
        payload: Mapping[str, Any],
        expected_registry_generation: int,
        expected_schema_hash: str,
    ) -> dict[str, Any]:
        if self._fallback_starter is None:
            raise HermesServiceNotReadyError(
                "shared Hermes service is unavailable and no fallback "
                f"companion path is configured: {reason}"
            )
        response = dict(
            self._fallback_starter(
                operation=operation,
                payload=dict(payload),
                expected_registry_generation=expected_registry_generation,
                expected_schema_hash=expected_schema_hash,
            )
        )
        response["execution_mode"] = FALLBACK_EXECUTION_MODE
        response["fallback_reason"] = reason
        return response


def build_supervisor_from_config(config: Any) -> HermesServiceSupervisor:
    """Launch and start the production shared-service supervisor."""
    service_config = config.hermes_service
    if not service_config.enabled:
        raise HermesServiceNotReadyError(
            "hermes_service is disabled in configuration"
        )
    if not service_config.checkout or not service_config.python_executable:
        raise HermesServiceNotReadyError(
            "hermes_service requires checkout and python_executable"
        )
    working_directory = Path(config.config_dir).resolve()

    def factory(worker_id: str) -> PersistentHermesWorker:
        return PersistentHermesWorker(
            PersistentHermesWorkerConfig(
                worker_id=worker_id,
                checkout=service_config.checkout,
                working_directory=working_directory,
                hermes_home=service_config.hermes_home or None,
                python_executable=service_config.python_executable,
                max_output_bytes=service_config.max_output_bytes,
                startup_timeout_seconds=(
                    service_config.startup_timeout_seconds
                ),
            )
        )

    supervisor = HermesServiceSupervisor(
        HermesSupervisorConfig(
            service_instance_id=f"hermes-shared-{uuid4().hex[:12]}",
            service_build_identity=PINNED_HERMES_REVISION,
            worker_count=service_config.worker_count,
            state_path=config.resolve_hermes_service_state_path(),
        ),
        worker_factory=factory,
    )
    supervisor.start()
    return supervisor
