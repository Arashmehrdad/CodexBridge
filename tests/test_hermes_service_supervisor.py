from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from codexbridge.hermes_service import (
    HermesRegistryIdentity,
    HermesServiceError,
    HermesServiceNotReadyError,
    HermesServiceReloadError,
    HermesServiceRequest,
)
from codexbridge.hermes_service_supervisor import (
    HermesServiceSupervisor,
    HermesSupervisorConfig,
)
from codexbridge.process_control import (
    process_group_popen_kwargs,
    process_identity,
    process_is_running,
)

SCHEMA_HASH = "b" * 64
OTHER_SCHEMA_HASH = "c" * 64


def identity(
    generation: int = 21, schema_hash: str = SCHEMA_HASH
) -> HermesRegistryIdentity:
    return HermesRegistryIdentity(
        generation=generation,
        effective_schema_hash=schema_hash,
        active_toolsets=("fixture",),
    )


class ControlledWorker:
    def __init__(
        self,
        worker_id: str,
        registry_identity: HermesRegistryIdentity,
        *,
        fail_dispatches: int = 0,
    ) -> None:
        self._worker_id = worker_id
        self._registry_identity = registry_identity
        self._ready = True
        self.closed = False
        self.dispatches: list[dict[str, Any]] = []
        self.fail_dispatches = fail_dispatches
        self.pid = 0
        self.service_pid = 0
        self.launcher_process_identity = f"launcher:{worker_id}"

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

    def kill(self) -> None:
        self._ready = False

    def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(request)
        self.dispatches.append(payload)
        if self.fail_dispatches > 0:
            self.fail_dispatches -= 1
            self._ready = False
            raise HermesServiceError("worker crashed mid-dispatch")
        return {
            "ok": True,
            "operation": payload["operation"],
            "registry_generation": self._registry_identity.generation,
            "effective_schema_hash": (
                self._registry_identity.effective_schema_hash
            ),
            "request_id": payload["request_id"],
            "served_by": self._worker_id,
        }

    def cancel(self, request_id: str) -> bool:
        self._ready = False
        return True

    def close(self) -> None:
        self.closed = True


class WorkerFactory:
    def __init__(self, registry_identity: HermesRegistryIdentity) -> None:
        self.registry_identity = registry_identity
        self.created: list[ControlledWorker] = []
        self.fail_next_dispatches = 0

    def __call__(self, worker_id: str) -> ControlledWorker:
        worker = ControlledWorker(
            worker_id,
            self.registry_identity,
            fail_dispatches=self.fail_next_dispatches,
        )
        self.fail_next_dispatches = 0
        self.created.append(worker)
        return worker


def make_supervisor(
    tmp_path: Path,
    factory: WorkerFactory,
    *,
    worker_count: int = 2,
) -> HermesServiceSupervisor:
    return HermesServiceSupervisor(
        HermesSupervisorConfig(
            service_instance_id="hermes-shared-service",
            service_build_identity="build-1",
            worker_count=worker_count,
            state_path=tmp_path / "hermes-service-state.json",
        ),
        worker_factory=factory,
    )


def service_request(request_id: str) -> HermesServiceRequest:
    return HermesServiceRequest(
        run_id=f"Run-{request_id}",
        request_id=request_id,
        session_id=f"Session-{request_id}",
        operation="tool_search",
        payload={"query": "fixture"},
        expected_registry_generation=21,
        expected_schema_hash=SCHEMA_HASH,
        worker_wait_timeout_seconds=2,
    )


def test_start_persists_worker_records_and_serves_requests(
    tmp_path: Path,
) -> None:
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory)
    try:
        started = supervisor.start()
        assert started["ok"] is True
        assert started["worker_count"] == 2
        assert started["restart_adoption"] == []

        state = json.loads(
            (tmp_path / "hermes-service-state.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(state["workers"]) == 2
        assert {
            record["worker_id"] for record in state["workers"]
        } == {"hermes-worker-1", "hermes-worker-2"}

        result = supervisor.execute(service_request("Request-A"))
        assert result.response["request_id"] == "Request-A"
        health = supervisor.health()
        assert health["ready"] is True
        assert health["worker_replacement_count"] == 0
    finally:
        supervisor.close()
    assert supervisor.health()["state"] == "stopped"


def test_dead_worker_is_deterministically_replaced(tmp_path: Path) -> None:
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory)
    try:
        supervisor.start()
        victim = factory.created[0]
        victim.kill()

        replacements = supervisor.restore_capacity()
        assert len(replacements) == 1
        assert replacements[0]["replaced_worker_id"] == victim.worker_id
        assert victim.closed is True

        health = supervisor.health()
        assert health["ready_worker_count"] == 2
        assert health["worker_replacement_count"] == 1

        state = json.loads(
            (tmp_path / "hermes-service-state.json").read_text(
                encoding="utf-8"
            )
        )
        recorded = {record["worker_id"] for record in state["workers"]}
        assert victim.worker_id not in recorded
        assert replacements[0]["replacement_worker_id"] in recorded
    finally:
        supervisor.close()


def test_replacement_registry_drift_fails_closed(tmp_path: Path) -> None:
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory)
    try:
        supervisor.start()
        factory.created[0].kill()
        factory.registry_identity = identity(
            generation=22, schema_hash=OTHER_SCHEMA_HASH
        )
        with pytest.raises(HermesServiceReloadError):
            supervisor.restore_capacity()
        drifted = factory.created[-1]
        assert drifted.closed is True
    finally:
        supervisor.close()


def test_worker_crash_recovers_without_lost_capacity(tmp_path: Path) -> None:
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory, worker_count=1)
    try:
        supervisor.start()
        factory.created[0].fail_dispatches = 1

        with pytest.raises(HermesServiceError):
            supervisor.execute(service_request("Request-Crash"))

        # The crashed worker was replaced by the execute-path supervision
        # hook, so the next request succeeds with a fresh verified worker.
        result = supervisor.execute(service_request("Request-After"))
        assert result.response["request_id"] == "Request-After"
        assert result.response["served_by"] != "hermes-worker-1"
        assert supervisor.health()["worker_replacement_count"] == 1
    finally:
        supervisor.close()


def test_restart_terminates_recorded_live_process(tmp_path: Path) -> None:
    stale = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(120)",
        ],
        **process_group_popen_kwargs(),
    )
    try:
        stale_identity = process_identity(stale.pid)
        assert stale_identity
        state_path = tmp_path / "hermes-service-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "service_instance_id": "hermes-shared-service",
                    "workers": [
                        {
                            "worker_id": "hermes-worker-1",
                            "pid": stale.pid,
                            "service_pid": stale.pid,
                            "launcher_process_identity": stale_identity,
                            "process_identity": stale_identity,
                        },
                        {
                            "worker_id": "hermes-worker-2",
                            "pid": 999_999_997,
                            "service_pid": 999_999_997,
                            "launcher_process_identity": "1:none:0",
                            "process_identity": "1:none:0",
                        },
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        factory = WorkerFactory(identity())
        supervisor = make_supervisor(tmp_path, factory)
        try:
            started = supervisor.start()
            actions = {
                entry["worker_id"]: entry["action"]
                for entry in started["restart_adoption"]
            }
            assert actions["hermes-worker-1"] == "replaced_stale_process"
            assert actions["hermes-worker-2"] == "released"
            assert process_is_running(stale.pid) is False
        finally:
            supervisor.close()
    finally:
        if stale.poll() is None:
            stale.kill()


def test_restart_with_corrupt_state_discards_and_starts(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "hermes-service-state.json"
    state_path.write_text("{not json", encoding="utf-8")
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory)
    try:
        started = supervisor.start()
        assert started["restart_adoption"] == [
            {
                "action": "discarded_corrupt_state",
                "state_path": str(state_path),
            }
        ]
        assert supervisor.health()["ready"] is True
    finally:
        supervisor.close()


def test_execute_requires_started_supervisor(tmp_path: Path) -> None:
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory)
    with pytest.raises(HermesServiceNotReadyError):
        supervisor.execute(service_request("Request-A"))


def test_supervised_reload_publishes_new_generation(tmp_path: Path) -> None:
    factory = WorkerFactory(identity())
    supervisor = make_supervisor(tmp_path, factory)
    try:
        supervisor.start()
        factory.registry_identity = identity(
            generation=22, schema_hash=OTHER_SCHEMA_HASH
        )
        health = supervisor.reload_registry()
        assert health["registry_generation"] == 22
        assert health["effective_schema_hash"] == OTHER_SCHEMA_HASH

        request = HermesServiceRequest(
            run_id="Run-New",
            request_id="Request-New",
            session_id="Session-New",
            operation="tool_search",
            payload={"query": "fixture"},
            expected_registry_generation=22,
            expected_schema_hash=OTHER_SCHEMA_HASH,
            worker_wait_timeout_seconds=2,
        )
        result = supervisor.execute(request)
        assert result.registry_identity.generation == 22
    finally:
        supervisor.close()
