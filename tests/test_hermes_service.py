from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Condition, Event, Lock
from time import monotonic
from typing import Any, Mapping

import pytest

from soma.hermes_companion_protocol import (
    HermesInterfaceDriftError,
)
from soma.hermes_service import (
    HermesRegistryIdentity,
    HermesServiceError,
    HermesServiceIdentity,
    HermesServiceOwnershipError,
    HermesServiceReloadError,
    HermesServiceRequest,
    HermesServiceRuntime,
)


class OverlapProbe:
    def __init__(self) -> None:
        self._condition = Condition()
        self.started = 0
        self.active = 0
        self.max_active = 0

    def enter(self) -> None:
        with self._condition:
            self.started += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self._condition.notify_all()

    def leave(self) -> None:
        with self._condition:
            self.active -= 1
            self._condition.notify_all()

    def wait_started(self, count: int, timeout: float = 3.0) -> None:
        deadline = monotonic() + timeout
        with self._condition:
            while self.started < count:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise AssertionError(
                        f"only {self.started} workers started"
                    )
                self._condition.wait(remaining)


class FakeWorker:
    def __init__(
        self,
        worker_id: str,
        registry_identity: HermesRegistryIdentity,
        *,
        process_identity: str | None = None,
        ready: bool = True,
        block: bool = False,
        probe: OverlapProbe | None = None,
    ) -> None:
        self._worker_id = worker_id
        self._process_identity = (
            process_identity or f"process:{worker_id}"
        )
        self._registry_identity = registry_identity
        self._ready = ready
        self._block = block
        self._probe = probe
        self.started = Event()
        self.release = Event()
        self.closed = False
        self.dispatches: list[dict[str, Any]] = []
        self.cancelled_requests: list[str] = []
        self._lock = Lock()
        self.active_request_id: str | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def process_identity(self) -> str:
        return self._process_identity

    @property
    def registry_identity(self) -> HermesRegistryIdentity:
        return self._registry_identity

    @property
    def ready(self) -> bool:
        return self._ready and not self.closed

    def dispatch(
        self, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        payload = dict(request)
        request_id = str(payload["request_id"])
        with self._lock:
            self.dispatches.append(payload)
            self.active_request_id = request_id
        if self._probe is not None:
            self._probe.enter()
        self.started.set()
        try:
            if self._block:
                if not self.release.wait(5):
                    raise TimeoutError("fake worker was not released")
            if request_id in self.cancelled_requests:
                return {
                    "ok": False,
                    "operation": payload["operation"],
                    "error": "cancelled",
                }
            return {
                "ok": True,
                "operation": payload["operation"],
                "registry_generation": (
                    self.registry_identity.generation
                ),
                "effective_schema_hash": (
                    self.registry_identity.effective_schema_hash
                ),
                "worker": self.worker_id,
                "echo_request_id": request_id,
            }
        finally:
            with self._lock:
                self.active_request_id = None
            if self._probe is not None:
                self._probe.leave()

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            if self.active_request_id != request_id:
                return False
            self.cancelled_requests.append(request_id)
            self.release.set()
            return True

    def close(self) -> None:
        self.closed = True
        self.release.set()


def registry(
    generation: int = 7, hash_character: str = "a"
) -> HermesRegistryIdentity:
    return HermesRegistryIdentity(
        generation=generation,
        effective_schema_hash=hash_character * 64,
        active_toolsets=("mcp-searchconsole", "filesystem"),
        catalog_toolsets=("mcp-searchconsole", "filesystem"),
        catalog_tool_count=12,
        toolset_selection_mode="restricted",
    )


def service_identity() -> HermesServiceIdentity:
    return HermesServiceIdentity(
        service_instance_id="Hermes-Service-A",
        service_build_identity="build:abc123",
        process_id=4321,
        process_identity="4321:windows:999",
        started_at="2026-07-20T19:00:00+00:00",
        restarted_at=None,
    )


def request(
    *,
    request_id: str,
    session_id: str = "Session-A",
    run_id: str = "Run-A",
    identity: HermesRegistryIdentity | None = None,
    operation: str = "tool_search",
) -> HermesServiceRequest:
    bound = identity or registry()
    return HermesServiceRequest(
        run_id=run_id,
        request_id=request_id,
        session_id=session_id,
        operation=operation,
        payload={"query": request_id},
        expected_registry_generation=bound.generation,
        expected_schema_hash=bound.effective_schema_hash,
        worker_wait_timeout_seconds=2,
    )


def test_health_exposes_service_and_registry_identity_without_model_runtime() -> None:
    identity = registry()
    workers = [
        FakeWorker("Worker-A", identity),
        FakeWorker("Worker-B", identity),
    ]
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=workers,
    )

    health = runtime.health()

    assert health["ok"] is True
    assert health["ready"] is True
    assert health["service_instance_id"] == "Hermes-Service-A"
    assert health["service_build_identity"] == "build:abc123"
    assert health["process_id"] == 4321
    assert health["process_identity"] == "4321:windows:999"
    assert health["registry_generation"] == 7
    assert health["effective_schema_hash"] == "a" * 64
    assert health["selected_toolsets"] == [
        "filesystem",
        "mcp-searchconsole",
    ]
    assert health["toolset_selection_mode"] == "restricted"
    assert health["catalog_toolsets"] == [
        "filesystem",
        "mcp-searchconsole",
    ]
    assert health["catalog_tool_count"] == 12
    assert health["worker_count"] == 2
    assert health["model_runtime_initialized"] is False


def test_unrestricted_registry_identity_cannot_be_read_as_empty_catalog() -> None:
    identity = HermesRegistryIdentity(
        generation=85,
        effective_schema_hash="f" * 64,
        active_toolsets=(),
        catalog_toolsets=("mcp-searchconsole", "filesystem"),
        catalog_tool_count=27,
        toolset_selection_mode="unrestricted",
    )

    payload = identity.as_dict()
    assert payload["active_toolsets"] == []
    assert payload["selected_toolsets"] == []
    assert payload["toolset_selection_mode"] == "unrestricted"
    assert payload["catalog_toolsets"] == [
        "filesystem",
        "mcp-searchconsole",
    ]
    assert payload["catalog_tool_count"] == 27
    assert "not an empty catalog" in payload["active_toolsets_semantics"]


def test_five_sessions_overlap_without_global_execution_serialization() -> None:
    identity = registry()
    probe = OverlapProbe()
    workers = [
        FakeWorker(
            f"Worker-{index}",
            identity,
            block=True,
            probe=probe,
        )
        for index in range(5)
    ]
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=workers,
    )
    requests = [
        request(
            request_id=f"Request-{index}",
            session_id=f"Session-{index}",
            run_id=f"Run-{index}",
            identity=identity,
        )
        for index in range(5)
    ]

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(runtime.execute, item)
            for item in requests
        ]
        probe.wait_started(5)
        health = runtime.health()
        assert health["active_request_count"] == 5
        assert health["busy_worker_count"] == 5
        assert probe.max_active == 5
        for worker in workers:
            worker.release.set()
        results = [future.result(timeout=3) for future in futures]

    assert {result.request_id for result in results} == {
        item.request_id for item in requests
    }
    assert {result.session_id for result in results} == {
        item.session_id for item in requests
    }
    assert len({result.worker_id for result in results}) == 5
    assert all(
        result.response["echo_request_id"] == result.request_id
        for result in results
    )


def test_duplicate_request_rejected_and_opaque_ids_preserved_exactly() -> None:
    identity = registry()
    worker = FakeWorker(
        "Worker-MixedCase", identity, block=True
    )
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=[worker],
    )
    original = request(
        request_id="Request-MixedCase",
        session_id="Session-MixedCase",
        run_id="Run-MixedCase",
        identity=identity,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(runtime.execute, original)
        assert worker.started.wait(2)
        with pytest.raises(
            HermesServiceOwnershipError,
            match="duplicate active Hermes request_id",
        ):
            runtime.execute(
                request(
                    request_id="Request-MixedCase",
                    session_id="Different-Session",
                    run_id="Different-Run",
                    identity=identity,
                )
            )
        worker.release.set()
        result = future.result(timeout=3)

    assert result.request_id == "Request-MixedCase"
    assert result.session_id == "Session-MixedCase"
    assert result.run_id == "Run-MixedCase"
    dispatched = worker.dispatches[0]
    assert dispatched["request_id"] == "Request-MixedCase"
    assert dispatched["session_id"] == "Session-MixedCase"
    assert dispatched["run_id"] == "Run-MixedCase"

    authoritative = HermesServiceRequest(
        run_id="Run-Authoritative",
        request_id="Request-Authoritative",
        session_id="Session-Authoritative",
        operation="tool_search",
        payload={
            "run_id": "Injected-Run",
            "request_id": "Injected-Request",
            "session_id": "Injected-Session",
            "operation": "tool_call",
            "query": "safe",
        },
        expected_registry_generation=identity.generation,
        expected_schema_hash=identity.effective_schema_hash,
    )
    runtime.execute(authoritative)
    protected_dispatch = worker.dispatches[-1]
    assert protected_dispatch["run_id"] == "Run-Authoritative"
    assert protected_dispatch["request_id"] == "Request-Authoritative"
    assert protected_dispatch["session_id"] == "Session-Authoritative"
    assert protected_dispatch["operation"] == "tool_search"


def test_cancellation_is_scoped_to_exact_session_run_and_request() -> None:
    identity = registry()
    workers = [
        FakeWorker("Worker-A", identity, block=True),
        FakeWorker("Worker-B", identity, block=True),
    ]
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=workers,
    )
    first = request(
        request_id="Request-A",
        session_id="Session-A",
        run_id="Run-A",
        identity=identity,
    )
    second = request(
        request_id="Request-B",
        session_id="Session-B",
        run_id="Run-B",
        identity=identity,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(runtime.execute, first)
        second_future = executor.submit(runtime.execute, second)
        assert all(worker.started.wait(2) for worker in workers)

        with pytest.raises(
            HermesServiceOwnershipError,
            match="cancellation ownership mismatch",
        ):
            runtime.cancel(
                request_id="Request-B",
                session_id="Session-A",
                run_id="Run-B",
            )

        assert runtime.cancel(
            request_id="Request-A",
            session_id="Session-A",
            run_id="Run-A",
        )
        first_result = first_future.result(timeout=3)
        assert first_result.response["ok"] is False
        assert not second_future.done()

        second_worker = next(
            worker
            for worker in workers
            if worker.active_request_id == "Request-B"
        )
        second_worker.release.set()
        second_result = second_future.result(timeout=3)

    cancelled_worker = next(
        worker
        for worker in workers
        if worker.cancelled_requests
    )
    assert cancelled_worker.cancelled_requests == ["Request-A"]
    assert second_result.response["ok"] is True
    assert all(not worker.closed for worker in workers)


def test_stale_registry_or_schema_is_rejected_before_dispatch() -> None:
    identity = registry()
    worker = FakeWorker("Worker-A", identity)
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=[worker],
    )

    stale_generation = HermesServiceRequest(
        run_id="Run-A",
        request_id="Request-Stale-Generation",
        session_id="Session-A",
        operation="tool_search",
        payload={"query": "x"},
        expected_registry_generation=identity.generation - 1,
        expected_schema_hash=identity.effective_schema_hash,
    )
    stale_schema = HermesServiceRequest(
        run_id="Run-B",
        request_id="Request-Stale-Schema",
        session_id="Session-B",
        operation="tool_search",
        payload={"query": "x"},
        expected_registry_generation=identity.generation,
        expected_schema_hash="f" * 64,
    )

    with pytest.raises(
        HermesInterfaceDriftError,
        match="stale Hermes registry generation",
    ):
        runtime.execute(stale_generation)
    with pytest.raises(
        HermesInterfaceDriftError,
        match="stale Hermes effective schema",
    ):
        runtime.execute(stale_schema)

    assert worker.dispatches == []


def test_atomic_reload_publishes_new_generation_while_old_request_drains() -> None:
    old_identity = registry(7, "a")
    new_identity = registry(8, "b")
    old_worker = FakeWorker(
        "Worker-Old", old_identity, block=True
    )
    new_worker = FakeWorker("Worker-New", new_identity)
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=old_identity,
        workers=[old_worker],
    )
    old_request = request(
        request_id="Request-Old",
        identity=old_identity,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        old_future = executor.submit(
            runtime.execute, old_request
        )
        assert old_worker.started.wait(2)

        reload_health = runtime.reload_registry(
            registry_identity=new_identity,
            workers=[new_worker],
        )
        assert reload_health["registry_generation"] == 8
        assert reload_health["retired_generation_count"] == 1
        assert old_worker.closed is False

        with pytest.raises(
            HermesInterfaceDriftError,
            match="stale Hermes registry generation",
        ):
            runtime.execute(
                request(
                    request_id="Request-Stale",
                    identity=old_identity,
                )
            )

        new_result = runtime.execute(
            request(
                request_id="Request-New",
                session_id="Session-New",
                run_id="Run-New",
                identity=new_identity,
            )
        )
        assert new_result.worker_id == "Worker-New"

        old_worker.release.set()
        old_result = old_future.result(timeout=3)

    assert old_result.worker_id == "Worker-Old"
    assert old_worker.closed is True
    assert new_worker.closed is False
    assert runtime.health()["retired_generation_count"] == 0


def test_invalid_reload_keeps_last_known_good_generation() -> None:
    old_identity = registry(7, "a")
    candidate_identity = registry(8, "b")
    old_worker = FakeWorker("Worker-Old", old_identity)
    invalid_worker = FakeWorker(
        "Worker-Invalid", old_identity
    )
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=old_identity,
        workers=[old_worker],
    )

    with pytest.raises(
        HermesServiceReloadError,
        match="worker registry identity drift",
    ):
        runtime.reload_registry(
            registry_identity=candidate_identity,
            workers=[invalid_worker],
        )

    health = runtime.health()
    assert health["registry_generation"] == 7
    assert health["effective_schema_hash"] == "a" * 64
    assert old_worker.closed is False
    assert invalid_worker.closed is True

    result = runtime.execute(
        request(
            request_id="Request-After-Failed-Reload",
            identity=old_identity,
        )
    )
    assert result.worker_id == "Worker-Old"


def test_replace_worker_swaps_only_dead_unleased_workers() -> None:
    identity = registry()
    dead = FakeWorker("Worker-Dead", identity)
    healthy = FakeWorker("Worker-Healthy", identity)
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=[dead, healthy],
    )
    dead._ready = False
    replacement = FakeWorker("Worker-Replacement", identity)

    replaced = runtime.replace_worker(
        worker_id="Worker-Dead", replacement=replacement
    )

    assert replaced is dead
    assert dead.closed is True
    result = runtime.execute(request(request_id="Request-A"))
    assert result.worker_id in {"Worker-Healthy", "Worker-Replacement"}
    health = runtime.health()
    assert health["ready_worker_count"] == 2


def test_replace_worker_rejects_ready_or_unknown_targets() -> None:
    identity = registry()
    healthy = FakeWorker("Worker-Healthy", identity)
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=[healthy],
    )
    replacement = FakeWorker("Worker-Replacement", identity)

    with pytest.raises(HermesServiceError, match="ready Hermes worker"):
        runtime.replace_worker(
            worker_id="Worker-Healthy", replacement=replacement
        )
    with pytest.raises(HermesServiceError, match="unknown Hermes worker_id"):
        runtime.replace_worker(
            worker_id="Worker-Missing", replacement=replacement
        )


def test_replace_worker_rejects_registry_identity_drift() -> None:
    identity = registry()
    dead = FakeWorker("Worker-Dead", identity)
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=[dead],
    )
    dead._ready = False
    drifted = FakeWorker(
        "Worker-Drifted", registry(generation=8, hash_character="d")
    )

    with pytest.raises(
        HermesServiceReloadError, match="registry identity drift"
    ):
        runtime.replace_worker(
            worker_id="Worker-Dead", replacement=drifted
        )
    assert dead.closed is False


def test_replace_worker_rejects_leased_target() -> None:
    identity = registry()
    blocked = FakeWorker("Worker-Blocked", identity, block=True)
    runtime = HermesServiceRuntime(
        service_identity=service_identity(),
        registry_identity=identity,
        workers=[blocked],
    )
    replacement = FakeWorker("Worker-Replacement", identity)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            runtime.execute, request(request_id="Request-Blocked")
        )
        blocked.started.wait(3)
        try:
            with pytest.raises(
                HermesServiceError, match="active lease"
            ):
                runtime.replace_worker(
                    worker_id="Worker-Blocked",
                    replacement=replacement,
                )
        finally:
            blocked.release.set()
            future.result(timeout=5)
