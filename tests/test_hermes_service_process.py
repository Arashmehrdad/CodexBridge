from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codexbridge.hermes_companion_protocol import (
    HERMES_COMPANION_PROTOCOL_VERSION,
    PINNED_HERMES_REVISION,
)
from codexbridge.hermes_service_process import (
    HermesServiceProcessError,
    PersistentHermesWorker,
    PersistentHermesWorkerConfig,
)
from codexbridge.process_control import process_is_running

SCHEMA_HASH = "a" * 64

FAKE_COMPANION = textwrap.dedent(
    f"""
    import json
    import os
    import sys
    import time

    handshake = {{
        "ok": True,
        "operation": "handshake",
        "protocol_version": {HERMES_COMPANION_PROTOCOL_VERSION!r},
        "hermes_revision": {PINNED_HERMES_REVISION!r},
        "registry_generation": 17,
        "effective_schema_hash": {SCHEMA_HASH!r},
        "active_toolsets": ["fixture"],
        "python_identity": {{"executable": sys.executable}},
        "model_runtime_initialized": False,
        "initialization_warnings": [],
        "encoded_bytes": 1,
    }}

    for raw_line in sys.stdin:
        request = json.loads(raw_line)
        operation = request.get("operation")
        if operation == "handshake":
            response = handshake
        else:
            if request.get("query") == "block":
                time.sleep(30)
            response = {{
                "ok": True,
                "operation": operation,
                "registry_generation": 17,
                "effective_schema_hash": {SCHEMA_HASH!r},
                "request_id": request.get("request_id"),
                "pid": os.getpid(),
            }}
        sys.stdout.write(json.dumps(response, sort_keys=True) + "\\n")
        sys.stdout.flush()
    """
)


def fake_companion_popen(_argv: list[str], **kwargs):
    return subprocess.Popen(
        [sys.executable, "-u", "-c", FAKE_COMPANION],
        **kwargs,
    )


def make_worker(tmp_path: Path, worker_id: str = "Worker-A") -> PersistentHermesWorker:
    checkout = tmp_path / "hermes"
    checkout.mkdir(parents=True)
    return PersistentHermesWorker(
        PersistentHermesWorkerConfig(
            worker_id=worker_id,
            checkout=checkout,
            working_directory=tmp_path,
            python_executable=sys.executable,
        ),
        popen_factory=fake_companion_popen,
    )


def bound_request(request_id: str, *, query: str = "normal") -> dict:
    return {
        "run_id": f"Run-{request_id}",
        "request_id": request_id,
        "session_id": f"Session-{request_id}",
        "operation": "tool_search",
        "query": query,
        "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
        "registry_generation": 17,
        "effective_schema_hash": SCHEMA_HASH,
    }


def wait_for_active(worker: PersistentHermesWorker, request_id: str) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if worker.active_request_id == request_id:
            return
        time.sleep(0.01)
    raise AssertionError(f"worker never claimed {request_id}")


def test_one_verified_process_serves_multiple_bound_requests(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    try:
        original_pid = worker.pid
        original_identity = worker.process_identity

        first = worker.dispatch(bound_request("Request-A"))
        second = worker.dispatch(bound_request("Request-B"))

        assert first["request_id"] == "Request-A"
        assert second["request_id"] == "Request-B"
        assert first["pid"] == original_pid
        assert second["pid"] == original_pid
        assert worker.pid == original_pid
        assert worker.process_identity == original_identity
        assert worker.registry_identity.generation == 17
        assert worker.registry_identity.effective_schema_hash == SCHEMA_HASH
        assert worker.registry_identity.active_toolsets == ("fixture",)
        assert worker.ready is True
    finally:
        pid = worker.pid
        worker.close()
    assert process_is_running(pid) is False


def test_exact_request_cancellation_terminates_only_owned_worker(tmp_path: Path) -> None:
    worker = make_worker(tmp_path)
    other = make_worker(tmp_path / "other", worker_id="Worker-B")
    request_id = "Request-Block"
    pid = worker.pid
    other_pid = other.pid
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                worker.dispatch,
                bound_request(request_id, query="block"),
            )
            wait_for_active(worker, request_id)

            assert worker.cancel("Different-Request") is False
            assert process_is_running(pid) is True
            assert other.ready is True

            assert worker.cancel(request_id) is True
            with pytest.raises(HermesServiceProcessError):
                future.result(timeout=5)

        assert process_is_running(pid) is False
        assert worker.ready is False
        assert worker.termination_report["terminated"] is True
        assert process_is_running(other_pid) is True
        assert other.ready is True
    finally:
        worker.close()
        other.close()


def test_worker_rejects_missing_request_identity_without_killing_process(
    tmp_path: Path,
) -> None:
    worker = make_worker(tmp_path)
    try:
        with pytest.raises(ValueError, match="request_id is required"):
            worker.dispatch(
                {
                    "operation": "tool_search",
                    "query": "x",
                    "protocol_version": HERMES_COMPANION_PROTOCOL_VERSION,
                    "registry_generation": 17,
                    "effective_schema_hash": SCHEMA_HASH,
                }
            )
        assert worker.ready is True
    finally:
        worker.close()
