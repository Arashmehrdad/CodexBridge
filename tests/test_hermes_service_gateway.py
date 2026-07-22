from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from typing import Any, Mapping

import pytest

from codexbridge.hermes_service import (
    HermesRegistryIdentity,
    HermesServiceError,
    HermesServiceNotReadyError,
    HermesServiceOwnershipError,
)
from codexbridge.hermes_service_gateway import (
    FALLBACK_EXECUTION_MODE,
    SHARED_EXECUTION_MODE,
    HermesServiceGateway,
)
from codexbridge.hermes_service_supervisor import (
    HermesServiceSupervisor,
    HermesSupervisorConfig,
)
from codexbridge.run_store import RunStore

SCHEMA_HASH = "d" * 64
GENERATION = 33


def identity() -> HermesRegistryIdentity:
    return HermesRegistryIdentity(
        generation=GENERATION,
        effective_schema_hash=SCHEMA_HASH,
        active_toolsets=("fixture",),
    )


class GateWorker:
    def __init__(self, worker_id: str, *, block: bool = False) -> None:
        self._worker_id = worker_id
        self._registry_identity = identity()
        self._ready = True
        self._block = block
        self.closed = False
        self.started = Event()
        self.release = Event()
        self._lock = Lock()
        self._cancelled: set[str] = set()
        self.active_request_id: str | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def process_identity(self) -> str:
        return f"process:{self._worker_id}"

    @property
    def registry_identity(self) -> HermesRegistryIdentity:
        return self._registry_identity

    @property
    def ready(self) -> bool:
        return self._ready and not self.closed

    def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(request)
        request_id = str(payload["request_id"])
        with self._lock:
            self.active_request_id = request_id
        self.started.set()
        try:
            if self._block:
                if not self.release.wait(5):
                    raise TimeoutError("gate worker was never released")
            with self._lock:
                if request_id in self._cancelled:
                    raise HermesServiceError(
                        "worker terminated by exact-request cancellation"
                    )
            return {
                "ok": True,
                "operation": payload["operation"],
                "registry_generation": GENERATION,
                "effective_schema_hash": SCHEMA_HASH,
                "request_id": request_id,
                "served_by": self._worker_id,
            }
        finally:
            with self._lock:
                self.active_request_id = None

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            if self.active_request_id != str(request_id):
                return False
            self._cancelled.add(str(request_id))
            self._ready = False
        self.release.set()
        return True

    def close(self) -> None:
        self.closed = True
        self.release.set()


def make_gateway(
    tmp_path: Path,
    *,
    block: bool = False,
    factory_failures: int = 0,
    fallback: bool = False,
) -> tuple[HermesServiceGateway, dict[str, Any]]:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    store = RunStore(runs_dir)
    store.init_db()
    tracking: dict[str, Any] = {
        "factory_calls": 0,
        "fallback_calls": [],
        "workers": [],
    }

    def worker_factory(worker_id: str) -> GateWorker:
        worker = GateWorker(worker_id, block=block)
        tracking["workers"].append(worker)
        return worker

    def supervisor_factory() -> HermesServiceSupervisor:
        tracking["factory_calls"] += 1
        if tracking["factory_calls"] <= factory_failures:
            raise RuntimeError("no pinned Hermes checkout is available")
        supervisor = HermesServiceSupervisor(
            HermesSupervisorConfig(
                service_instance_id="hermes-shared-test",
                service_build_identity="build-test",
                worker_count=2,
                state_path=tmp_path / "state.json",
            ),
            worker_factory=worker_factory,
        )
        supervisor.start()
        return supervisor

    fallback_starter = None
    if fallback:

        def fallback_starter(**kwargs: Any) -> dict[str, Any]:
            tracking["fallback_calls"].append(dict(kwargs))
            return {
                "ok": True,
                "run_id": f"h1-fallback-{len(tracking['fallback_calls'])}",
                "status": "queued",
            }

    gateway = HermesServiceGateway(
        run_store=store,
        runs_dir=runs_dir,
        supervisor_factory=supervisor_factory,
        fallback_starter=fallback_starter,
    )
    tracking["store"] = store
    return gateway, tracking


def execute(
    gateway: HermesServiceGateway,
    *,
    session_id: str = "Session-A",
    generation: int = GENERATION,
    schema_hash: str = SCHEMA_HASH,
) -> dict[str, Any]:
    return gateway.execute(
        session_id=session_id,
        operation="tool_search",
        payload={"query": "fixture"},
        expected_registry_generation=generation,
        expected_schema_hash=schema_hash,
        worker_wait_timeout_seconds=2,
    )


def test_shared_execution_creates_isolated_durable_run(tmp_path: Path) -> None:
    gateway, tracking = make_gateway(tmp_path)
    try:
        response = execute(gateway)
        assert response["ok"] is True
        assert response["status"] == "completed"
        assert response["execution_mode"] == SHARED_EXECUTION_MODE
        assert response["run_id"].startswith("2")
        assert response["request_id"].startswith("hsr-")

        stored = tracking["store"].get_run(response["run_id"])
        assert stored["status"] == "completed"
        assert stored["result"]["response"]["served_by"].startswith(
            "hermes-worker-"
        )

        owned = gateway.get_result(
            run_id=response["run_id"], session_id="Session-A"
        )
        assert owned["status"] == "completed"
        with pytest.raises(HermesServiceOwnershipError):
            gateway.get_result(
                run_id=response["run_id"], session_id="Session-B"
            )
    finally:
        gateway.close()


def test_sessions_receive_distinct_runs_and_requests(tmp_path: Path) -> None:
    gateway, _ = make_gateway(tmp_path)
    try:
        first = execute(gateway, session_id="Session-A")
        second = execute(gateway, session_id="Session-B")
        assert first["run_id"] != second["run_id"]
        assert first["request_id"] != second["request_id"]
        assert first["session_id"] == "Session-A"
        assert second["session_id"] == "Session-B"
    finally:
        gateway.close()


def test_cross_session_cancel_is_rejected_and_owner_cancel_succeeds(
    tmp_path: Path,
) -> None:
    gateway, tracking = make_gateway(tmp_path, block=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                execute, gateway, session_id="Session-A"
            )
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and not tracking["workers"]:
                time.sleep(0.01)
            worker = tracking["workers"][0]
            assert worker.started.wait(3)
            with gateway._state_lock:
                request_id = next(iter(gateway._active))
                run_id = gateway._active[request_id]["run_id"]

            with pytest.raises(HermesServiceOwnershipError):
                gateway.cancel(
                    run_id=run_id,
                    request_id=request_id,
                    session_id="Session-Intruder",
                )

            cancelled = gateway.cancel(
                run_id=run_id,
                request_id=request_id,
                session_id="Session-A",
            )
            assert cancelled["cancelled"] is True

            response = future.result(timeout=5)
        assert response["ok"] is False
        assert response["status"] == "cancelled"
        stored = tracking["store"].get_run(response["run_id"])
        assert stored["status"] == "cancelled"
    finally:
        gateway.close()


def test_service_unavailable_uses_bounded_fallback(tmp_path: Path) -> None:
    gateway, tracking = make_gateway(
        tmp_path, factory_failures=100, fallback=True
    )
    first = execute(gateway)
    assert first["execution_mode"] == FALLBACK_EXECUTION_MODE
    assert "failed to start" in first["fallback_reason"]
    assert first["run_id"] == "h1-fallback-1"

    second = execute(gateway)
    assert second["execution_mode"] == FALLBACK_EXECUTION_MODE
    assert second["run_id"] == "h1-fallback-2"

    # The failed service start is remembered: one factory attempt total,
    # one bounded fallback per request.
    assert tracking["factory_calls"] == 1
    assert len(tracking["fallback_calls"]) == 2
    assert tracking["fallback_calls"][0]["operation"] == "tool_search"


def test_service_unavailable_without_fallback_raises(tmp_path: Path) -> None:
    gateway, _ = make_gateway(tmp_path, factory_failures=100)
    with pytest.raises(HermesServiceNotReadyError, match="no fallback"):
        execute(gateway)


def test_stale_identity_fails_closed_without_fallback(tmp_path: Path) -> None:
    gateway, tracking = make_gateway(tmp_path, fallback=True)
    try:
        response = execute(gateway, generation=GENERATION - 1)
        assert response["ok"] is False
        assert response["error_type"] == "stale_identity"
        assert "fallback" not in response
        assert tracking["fallback_calls"] == []
        stored = tracking["store"].get_run(response["run_id"])
        assert stored["status"] == "failed"
    finally:
        gateway.close()


def test_retry_service_recovers_after_start_failure(tmp_path: Path) -> None:
    gateway, tracking = make_gateway(
        tmp_path, factory_failures=1, fallback=True
    )
    try:
        first = execute(gateway)
        assert first["execution_mode"] == FALLBACK_EXECUTION_MODE

        retried = gateway.retry_service()
        assert retried["ok"] is True
        assert "failed to start" in retried["previous_error"]

        second = execute(gateway)
        assert second["execution_mode"] == SHARED_EXECUTION_MODE
        assert second["status"] == "completed"
        assert tracking["factory_calls"] == 2
    finally:
        gateway.close()


def test_health_reports_unavailable_service_and_fallback(
    tmp_path: Path,
) -> None:
    gateway, _ = make_gateway(
        tmp_path, factory_failures=100, fallback=True
    )
    execute(gateway)
    health = gateway.health()
    assert health["ok"] is False
    assert health["state"] == "unavailable"
    assert health["fallback_available"] is True
    assert "failed to start" in health["service_error"]
