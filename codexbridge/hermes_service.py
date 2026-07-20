from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Condition, Lock
from time import monotonic
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .hermes_companion_protocol import (
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
    HermesCompanionProtocolError,
    HermesInterfaceDriftError,
)


SUPPORTED_SERVICE_OPERATIONS = frozenset(
    {"tool_search", "tool_describe", "tool_call"}
)
DEFAULT_WORKER_WAIT_TIMEOUT_SECONDS = 30.0
MAX_OPAQUE_ID_LENGTH = 256


class HermesServiceError(RuntimeError):
    """Base error for the shared Hermes service runtime."""


class HermesServiceNotReadyError(HermesServiceError):
    """Raised when no verified service worker can accept a request."""


class HermesServiceOwnershipError(HermesServiceError):
    """Raised when request ownership does not match a control request."""


class HermesServiceReloadError(HermesServiceError):
    """Raised when a registry-generation transition cannot be published."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opaque_id(value: str, field_name: str) -> str:
    normalized = str(value)
    if not normalized or normalized.isspace():
        raise HermesCompanionProtocolError(f"{field_name} must not be empty")
    if len(normalized) > MAX_OPAQUE_ID_LENGTH:
        raise HermesCompanionProtocolError(
            f"{field_name} exceeds {MAX_OPAQUE_ID_LENGTH} characters"
        )
    return normalized


def _sha256_identity(value: str, field_name: str) -> str:
    normalized = str(value)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in normalized
    ):
        raise HermesCompanionProtocolError(
            f"{field_name} must be a 64-character SHA-256 value"
        )
    return normalized.lower()


@dataclass(frozen=True)
class HermesRegistryIdentity:
    generation: int
    effective_schema_hash: str
    active_toolsets: tuple[str, ...] = ()
    hermes_revision: str = PINNED_HERMES_REVISION
    protocol_version: str = HERMES_COMPANION_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise HermesCompanionProtocolError(
                "registry generation must be a non-negative integer"
            )
        object.__setattr__(
            self,
            "effective_schema_hash",
            _sha256_identity(
                self.effective_schema_hash, "effective_schema_hash"
            ),
        )
        if self.hermes_revision != PINNED_HERMES_REVISION:
            raise HermesInterfaceDriftError("Hermes revision drift")
        if self.protocol_version != HERMES_COMPANION_PROTOCOL_VERSION:
            raise HermesInterfaceDriftError("Hermes service protocol drift")
        normalized_toolsets = tuple(
            sorted(
                {
                    _opaque_id(str(toolset), "active_toolset")
                    for toolset in self.active_toolsets
                }
            )
        )
        object.__setattr__(self, "active_toolsets", normalized_toolsets)

    @classmethod
    def from_handshake(
        cls, handshake: Mapping[str, Any]
    ) -> "HermesRegistryIdentity":
        if handshake.get("model_runtime_initialized") is not False:
            raise HermesCompanionProtocolError(
                "model runtime initialization evidence is invalid"
            )
        toolsets = handshake.get("active_toolsets", ())
        if not isinstance(toolsets, (list, tuple, set, frozenset)):
            raise HermesCompanionProtocolError(
                "active_toolsets must be a sequence"
            )
        return cls(
            generation=handshake.get("registry_generation"),
            effective_schema_hash=str(
                handshake.get("effective_schema_hash") or ""
            ),
            active_toolsets=tuple(str(value) for value in toolsets),
            hermes_revision=str(handshake.get("hermes_revision") or ""),
            protocol_version=str(handshake.get("protocol_version") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "hermes_revision": self.hermes_revision,
            "protocol_version": self.protocol_version,
            "registry_generation": self.generation,
            "effective_schema_hash": self.effective_schema_hash,
            "active_toolsets": list(self.active_toolsets),
        }


@dataclass(frozen=True)
class HermesServiceIdentity:
    service_instance_id: str
    service_build_identity: str
    process_id: int
    process_identity: str
    started_at: str
    restarted_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "service_instance_id",
            _opaque_id(self.service_instance_id, "service_instance_id"),
        )
        object.__setattr__(
            self,
            "service_build_identity",
            _opaque_id(
                self.service_build_identity, "service_build_identity"
            ),
        )
        if (
            isinstance(self.process_id, bool)
            or not isinstance(self.process_id, int)
            or self.process_id <= 0
        ):
            raise HermesCompanionProtocolError(
                "service process_id must be a positive integer"
            )
        object.__setattr__(
            self,
            "process_identity",
            _opaque_id(self.process_identity, "process_identity"),
        )
        object.__setattr__(
            self, "started_at", _opaque_id(self.started_at, "started_at")
        )
        if self.restarted_at is not None:
            object.__setattr__(
                self,
                "restarted_at",
                _opaque_id(self.restarted_at, "restarted_at"),
            )

    @classmethod
    def local(
        cls,
        *,
        service_instance_id: str,
        service_build_identity: str,
        process_identity: str,
        started_at: str | None = None,
        restarted_at: str | None = None,
    ) -> "HermesServiceIdentity":
        return cls(
            service_instance_id=service_instance_id,
            service_build_identity=service_build_identity,
            process_id=os.getpid(),
            process_identity=process_identity,
            started_at=started_at or _utc_now(),
            restarted_at=restarted_at,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "service_instance_id": self.service_instance_id,
            "service_build_identity": self.service_build_identity,
            "process_id": self.process_id,
            "process_identity": self.process_identity,
            "started_at": self.started_at,
            "restarted_at": self.restarted_at,
        }


@dataclass(frozen=True)
class HermesServiceRequest:
    run_id: str
    request_id: str
    session_id: str
    operation: str
    payload: Mapping[str, Any]
    expected_registry_generation: int
    expected_schema_hash: str
    worker_wait_timeout_seconds: float = (
        DEFAULT_WORKER_WAIT_TIMEOUT_SECONDS
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _opaque_id(self.run_id, "run_id"))
        object.__setattr__(
            self, "request_id", _opaque_id(self.request_id, "request_id")
        )
        object.__setattr__(
            self, "session_id", _opaque_id(self.session_id, "session_id")
        )
        normalized_operation = str(self.operation).strip()
        if normalized_operation not in SUPPORTED_SERVICE_OPERATIONS:
            raise HermesCompanionProtocolError(
                f"unsupported Hermes service operation: "
                f"{normalized_operation or '<empty>'}"
            )
        object.__setattr__(self, "operation", normalized_operation)
        if not isinstance(self.payload, Mapping):
            raise HermesCompanionProtocolError(
                "Hermes service payload must be a mapping"
            )
        object.__setattr__(self, "payload", dict(self.payload))
        if (
            isinstance(self.expected_registry_generation, bool)
            or not isinstance(self.expected_registry_generation, int)
            or self.expected_registry_generation < 0
        ):
            raise HermesCompanionProtocolError(
                "expected_registry_generation must be non-negative"
            )
        object.__setattr__(
            self,
            "expected_schema_hash",
            _sha256_identity(
                self.expected_schema_hash, "expected_schema_hash"
            ),
        )
        timeout = float(self.worker_wait_timeout_seconds)
        if timeout <= 0 or timeout > 600:
            raise HermesCompanionProtocolError(
                "worker_wait_timeout_seconds must be between 0 and 600"
            )
        object.__setattr__(
            self, "worker_wait_timeout_seconds", timeout
        )

    def companion_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "operation": self.operation,
            **dict(self.payload),
            "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
            "registry_generation": self.expected_registry_generation,
            "effective_schema_hash": self.expected_schema_hash,
        }


@dataclass(frozen=True)
class HermesServiceResult:
    run_id: str
    request_id: str
    session_id: str
    operation: str
    worker_id: str
    worker_process_identity: str
    registry_identity: HermesRegistryIdentity
    response: Mapping[str, Any]
    started_at: str
    ended_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "operation": self.operation,
            "execution_mode": "shared_persistent_service",
            "worker_id": self.worker_id,
            "worker_process_identity": self.worker_process_identity,
            **self.registry_identity.as_dict(),
            "response": dict(self.response),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "model_runtime_initialized": False,
        }


@runtime_checkable
class HermesServiceWorker(Protocol):
    @property
    def worker_id(self) -> str: ...

    @property
    def process_identity(self) -> str: ...

    @property
    def registry_identity(self) -> HermesRegistryIdentity: ...

    @property
    def ready(self) -> bool: ...

    def dispatch(
        self, request: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def cancel(self, request_id: str) -> bool: ...

    def close(self) -> None: ...


@dataclass
class _WorkerSlot:
    worker: HermesServiceWorker
    request_id: str | None = None


@dataclass
class _ActiveRequest:
    request: HermesServiceRequest
    pool: "_GenerationPool"
    slot: _WorkerSlot | None = None
    cancel_requested: bool = False


class _GenerationPool:
    def __init__(
        self,
        identity: HermesRegistryIdentity,
        workers: Sequence[HermesServiceWorker],
    ) -> None:
        self.identity = identity
        self._condition = Condition()
        self._slots: list[_WorkerSlot] = []
        self._references = 0
        self._active = 0
        self._draining = False
        self._closed = False
        try:
            if not workers:
                raise HermesServiceReloadError(
                    "Hermes service generation requires at least one worker"
                )
            worker_ids: set[str] = set()
            process_identities: set[str] = set()
            for worker in workers:
                worker_id = _opaque_id(worker.worker_id, "worker_id")
                process_identity = _opaque_id(
                    worker.process_identity, "worker_process_identity"
                )
                if worker_id in worker_ids:
                    raise HermesServiceReloadError(
                        f"duplicate Hermes worker_id: {worker_id}"
                    )
                if process_identity in process_identities:
                    raise HermesServiceReloadError(
                        "duplicate Hermes worker process identity"
                    )
                if not worker.ready:
                    raise HermesServiceReloadError(
                        f"Hermes worker is not ready: {worker_id}"
                    )
                if worker.registry_identity != identity:
                    raise HermesServiceReloadError(
                        f"Hermes worker registry identity drift: {worker_id}"
                    )
                worker_ids.add(worker_id)
                process_identities.add(process_identity)
                self._slots.append(_WorkerSlot(worker=worker))
        except Exception:
            for worker in workers:
                try:
                    worker.close()
                except Exception:
                    pass
            raise

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    def retain(self) -> None:
        with self._condition:
            if self._closed:
                raise HermesServiceNotReadyError(
                    "Hermes service generation is closed"
                )
            self._references += 1

    def release_reference(self) -> None:
        workers: list[HermesServiceWorker]
        with self._condition:
            if self._references <= 0:
                raise HermesServiceError(
                    "Hermes service generation reference underflow"
                )
            self._references -= 1
            workers = self._collect_closeable_locked()
        self._close_workers(workers)

    def lease(
        self, request_id: str, timeout_seconds: float
    ) -> _WorkerSlot:
        deadline = monotonic() + timeout_seconds
        with self._condition:
            while True:
                if self._closed:
                    raise HermesServiceNotReadyError(
                        "Hermes service generation is closed"
                    )
                for slot in self._slots:
                    if slot.request_id is None and slot.worker.ready:
                        slot.request_id = request_id
                        self._active += 1
                        return slot
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise HermesServiceNotReadyError(
                        "Timed out waiting for a ready Hermes service worker"
                    )
                self._condition.wait(timeout=remaining)

    def release(self, slot: _WorkerSlot, request_id: str) -> None:
        workers: list[HermesServiceWorker]
        with self._condition:
            if slot.request_id != request_id:
                raise HermesServiceOwnershipError(
                    "Hermes worker lease ownership drift"
                )
            slot.request_id = None
            self._active -= 1
            self._condition.notify_all()
            workers = self._collect_closeable_locked()
        self._close_workers(workers)

    def mark_draining(self) -> None:
        workers: list[HermesServiceWorker]
        with self._condition:
            self._draining = True
            workers = self._collect_closeable_locked()
        self._close_workers(workers)

    def close_candidate(self) -> None:
        workers: list[HermesServiceWorker] = []
        with self._condition:
            if self._active or self._references:
                raise HermesServiceError(
                    "Cannot close an active Hermes candidate generation"
                )
            if not self._closed:
                self._closed = True
                workers = [slot.worker for slot in self._slots]
                self._condition.notify_all()
        self._close_workers(workers)

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            busy = sum(
                1 for slot in self._slots if slot.request_id is not None
            )
            return {
                "registry_generation": self.identity.generation,
                "effective_schema_hash": (
                    self.identity.effective_schema_hash
                ),
                "worker_count": len(self._slots),
                "ready_worker_count": sum(
                    1 for slot in self._slots if slot.worker.ready
                ),
                "busy_worker_count": busy,
                "available_worker_count": len(self._slots) - busy,
                "active_request_count": self._active,
                "retained_request_count": self._references,
                "draining": self._draining,
                "closed": self._closed,
            }

    def _collect_closeable_locked(
        self,
    ) -> list[HermesServiceWorker]:
        if (
            self._draining
            and not self._closed
            and self._references == 0
            and self._active == 0
        ):
            self._closed = True
            self._condition.notify_all()
            return [slot.worker for slot in self._slots]
        return []

    @staticmethod
    def _close_workers(
        workers: Sequence[HermesServiceWorker],
    ) -> None:
        for worker in workers:
            worker.close()


class HermesServiceRuntime:
    """Thread-safe generation and ownership core for a shared Hermes service.

    This foundation deliberately does not own process launch or public gateway
    routing yet. A later lifecycle layer can supply persistent companion
    subprocess workers that satisfy ``HermesServiceWorker`` without changing
    the request, cancellation, or registry-transition contracts here.
    """

    def __init__(
        self,
        *,
        service_identity: HermesServiceIdentity,
        registry_identity: HermesRegistryIdentity,
        workers: Sequence[HermesServiceWorker],
    ) -> None:
        self.service_identity = service_identity
        self._state_lock = Lock()
        self._administration_lock = Lock()
        self._active_lock = Lock()
        self._current_pool = _GenerationPool(
            registry_identity, tuple(workers)
        )
        self._retired_pools: list[_GenerationPool] = []
        self._active_requests: dict[str, _ActiveRequest] = {}
        self._state = "ready"
        self._last_registry_reload_at: str | None = None

    def execute(
        self, request: HermesServiceRequest
    ) -> HermesServiceResult:
        if not isinstance(request, HermesServiceRequest):
            raise HermesCompanionProtocolError(
                "request must be a HermesServiceRequest"
            )
        with self._state_lock:
            if self._state != "ready":
                raise HermesServiceNotReadyError(
                    f"Hermes service is not ready: {self._state}"
                )
            pool = self._current_pool
            self._verify_request_identity(request, pool.identity)
            pool.retain()

        active = _ActiveRequest(request=request, pool=pool)
        with self._active_lock:
            if request.request_id in self._active_requests:
                pool.release_reference()
                raise HermesServiceOwnershipError(
                    f"duplicate active Hermes request_id: "
                    f"{request.request_id}"
                )
            self._active_requests[request.request_id] = active

        slot: _WorkerSlot | None = None
        started_at = _utc_now()
        try:
            slot = pool.lease(
                request.request_id,
                request.worker_wait_timeout_seconds,
            )
            with self._active_lock:
                current = self._active_requests.get(request.request_id)
                if current is not active:
                    raise HermesServiceOwnershipError(
                        "Hermes request ownership disappeared before dispatch"
                    )
                active.slot = slot
                cancel_requested = active.cancel_requested
            if cancel_requested:
                raise HermesServiceOwnershipError(
                    "Hermes request was cancelled before dispatch"
                )

            response = slot.worker.dispatch(
                request.companion_payload()
            )
            normalized_response = self._validate_worker_response(
                request, pool.identity, response
            )
            return HermesServiceResult(
                run_id=request.run_id,
                request_id=request.request_id,
                session_id=request.session_id,
                operation=request.operation,
                worker_id=slot.worker.worker_id,
                worker_process_identity=slot.worker.process_identity,
                registry_identity=pool.identity,
                response=normalized_response,
                started_at=started_at,
                ended_at=_utc_now(),
            )
        finally:
            with self._active_lock:
                if (
                    self._active_requests.get(request.request_id)
                    is active
                ):
                    self._active_requests.pop(request.request_id, None)
            if slot is not None:
                pool.release(slot, request.request_id)
            pool.release_reference()

    def cancel(
        self,
        *,
        request_id: str,
        session_id: str,
        run_id: str,
    ) -> bool:
        normalized_request_id = _opaque_id(
            request_id, "request_id"
        )
        normalized_session_id = _opaque_id(
            session_id, "session_id"
        )
        normalized_run_id = _opaque_id(run_id, "run_id")
        worker: HermesServiceWorker | None = None
        with self._active_lock:
            active = self._active_requests.get(normalized_request_id)
            if active is None:
                return False
            if (
                active.request.session_id != normalized_session_id
                or active.request.run_id != normalized_run_id
            ):
                raise HermesServiceOwnershipError(
                    "Hermes cancellation ownership mismatch"
                )
            active.cancel_requested = True
            if active.slot is not None:
                worker = active.slot.worker
        if worker is None:
            return True
        return bool(worker.cancel(normalized_request_id))

    def reload_registry(
        self,
        *,
        registry_identity: HermesRegistryIdentity,
        workers: Sequence[HermesServiceWorker],
    ) -> dict[str, Any]:
        with self._administration_lock:
            candidate: _GenerationPool | None = None
            try:
                candidate = _GenerationPool(
                    registry_identity, tuple(workers)
                )
                with self._state_lock:
                    if self._state != "ready":
                        raise HermesServiceReloadError(
                            "Hermes service is not ready for registry reload"
                        )
                    current = self._current_pool
                    if (
                        registry_identity.generation
                        <= current.identity.generation
                    ):
                        raise HermesServiceReloadError(
                            "candidate registry generation must be newer "
                            "than the active generation"
                        )
                    self._current_pool = candidate
                    self._retired_pools.append(current)
                    self._last_registry_reload_at = _utc_now()
                current.mark_draining()
                return self.health()
            except Exception:
                if candidate is not None:
                    candidate.close_candidate()
                raise

    def health(self) -> dict[str, Any]:
        with self._state_lock:
            current = self._current_pool
            self._retired_pools = [
                pool
                for pool in self._retired_pools
                if not pool.closed
            ]
            retired = tuple(self._retired_pools)
            state = self._state
            reload_at = self._last_registry_reload_at
        with self._active_lock:
            active_count = len(self._active_requests)
        current_snapshot = current.snapshot()
        return {
            "ok": state == "ready",
            "state": state,
            "ready": state == "ready"
            and current_snapshot["ready_worker_count"] > 0,
            **self.service_identity.as_dict(),
            **current.identity.as_dict(),
            "selected_toolsets": list(
                current.identity.active_toolsets
            ),
            "last_registry_reload_at": reload_at,
            "worker_count": current_snapshot["worker_count"],
            "ready_worker_count": current_snapshot[
                "ready_worker_count"
            ],
            "busy_worker_count": current_snapshot[
                "busy_worker_count"
            ],
            "available_worker_count": current_snapshot[
                "available_worker_count"
            ],
            "active_request_count": active_count,
            "retired_generation_count": len(retired),
            "retired_generations": [
                pool.snapshot() for pool in retired
            ],
            "model_runtime_initialized": False,
        }

    def close(self) -> None:
        with self._administration_lock:
            with self._state_lock:
                if self._state == "closed":
                    return
                self._state = "closed"
                pools = (
                    self._current_pool,
                    *self._retired_pools,
                )
            for pool in pools:
                pool.mark_draining()

    @staticmethod
    def _verify_request_identity(
        request: HermesServiceRequest,
        identity: HermesRegistryIdentity,
    ) -> None:
        if (
            request.expected_registry_generation
            != identity.generation
        ):
            raise HermesInterfaceDriftError(
                "stale Hermes registry generation"
            )
        if (
            request.expected_schema_hash
            != identity.effective_schema_hash
        ):
            raise HermesInterfaceDriftError(
                "stale Hermes effective schema"
            )

    @staticmethod
    def _validate_worker_response(
        request: HermesServiceRequest,
        identity: HermesRegistryIdentity,
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(response, Mapping):
            raise HermesCompanionProtocolError(
                "Hermes service worker response must be a mapping"
            )
        normalized = dict(response)
        if normalized.get("ok") is not True:
            return normalized
        if normalized.get("operation") != request.operation:
            raise HermesCompanionProtocolError(
                "Hermes service worker operation drift"
            )
        if (
            normalized.get("registry_generation")
            != identity.generation
        ):
            raise HermesInterfaceDriftError(
                "Hermes service worker registry generation drift"
            )
        if (
            normalized.get("effective_schema_hash")
            != identity.effective_schema_hash
        ):
            raise HermesInterfaceDriftError(
                "Hermes service worker effective schema drift"
            )
        return normalized
