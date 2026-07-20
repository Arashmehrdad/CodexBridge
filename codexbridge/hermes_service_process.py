from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Mapping, Sequence, TextIO

from .hermes_companion import MAX_REQUEST_BYTES
from .hermes_companion_client import (
    DEFAULT_COMPANION_TIMEOUT_SECONDS,
    build_companion_launch,
    parse_companion_result,
)
from .hermes_companion_protocol import HermesCompanionProtocolError
from .hermes_service import HermesRegistryIdentity, HermesServiceError
from .process_control import (
    process_group_popen_kwargs,
    process_identity,
    process_matches_identity,
    terminate_process_tree,
)

DEFAULT_STDERR_MAX_BYTES = 64 * 1024


class HermesServiceProcessError(HermesServiceError):
    """Persistent companion launch, transport, or process-identity failure."""


@dataclass(frozen=True)
class PersistentHermesWorkerConfig:
    worker_id: str
    checkout: str | Path
    working_directory: str | Path
    hermes_home: str | Path | None = None
    python_executable: str | Path = sys.executable
    max_output_bytes: int | None = None
    startup_timeout_seconds: int = DEFAULT_COMPANION_TIMEOUT_SECONDS
    stderr_max_bytes: int = DEFAULT_STDERR_MAX_BYTES
    environment: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not str(self.worker_id) or str(self.worker_id).isspace():
            raise HermesCompanionProtocolError("worker_id must not be empty")
        checkout = Path(self.checkout).resolve()
        working_directory = Path(self.working_directory).resolve()
        python_executable = Path(self.python_executable).resolve()
        if not checkout.is_dir() or checkout.is_symlink():
            raise HermesCompanionProtocolError(
                "Hermes checkout must be an existing non-symlink directory"
            )
        if not working_directory.is_dir() or working_directory.is_symlink():
            raise HermesCompanionProtocolError(
                "working_directory must be an existing non-symlink directory"
            )
        if not python_executable.is_file() or python_executable.is_symlink():
            raise HermesCompanionProtocolError(
                "python_executable must be an existing non-symlink file"
            )
        if self.max_output_bytes is not None and self.max_output_bytes <= 0:
            raise HermesCompanionProtocolError("max_output_bytes must be positive")
        if self.startup_timeout_seconds < 1 or self.startup_timeout_seconds > 600:
            raise HermesCompanionProtocolError(
                "startup_timeout_seconds must be between 1 and 600"
            )
        if self.stderr_max_bytes < 0 or self.stderr_max_bytes > 1_000_000:
            raise HermesCompanionProtocolError(
                "stderr_max_bytes must be between 0 and 1000000"
            )
        object.__setattr__(self, "checkout", checkout)
        object.__setattr__(self, "working_directory", working_directory)
        object.__setattr__(self, "python_executable", python_executable)
        if self.hermes_home is not None:
            object.__setattr__(self, "hermes_home", Path(self.hermes_home).resolve())
        object.__setattr__(self, "environment", dict(self.environment or {}))


class PersistentHermesWorker:
    """One verified, reusable Hermes companion subprocess over stdio.

    The worker owns exactly one companion process. Requests are serialized only
    within that process; service-level concurrency comes from multiple workers.
    Cancellation terminates only the process currently executing the exact
    request ID. A later lifecycle layer may replace a terminated worker without
    changing this contract.
    """

    def __init__(
        self,
        config: PersistentHermesWorkerConfig,
        *,
        popen_factory: Any = subprocess.Popen,
    ) -> None:
        self.config = config
        self._state_lock = Lock()
        self._io_lock = Lock()
        self._closed = False
        self._active_request_id: str | None = None
        self._stderr_chunks: deque[bytes] = deque()
        self._stderr_size = 0
        self._termination_report: dict[str, Any] = {}

        handshake_launch = build_companion_launch(
            profile_id="persistent_hermes_service",
            checkout=config.checkout,
            operation="handshake",
            hermes_home=config.hermes_home,
            timeout_seconds=config.startup_timeout_seconds,
        )
        argv = [str(config.python_executable), *handshake_launch.argv]
        if config.max_output_bytes is not None:
            argv.extend(["--max-output-bytes", str(config.max_output_bytes)])
        environment = os.environ.copy()
        environment.update(dict(config.environment or {}))
        environment.update(dict(handshake_launch.environment))

        self._process = popen_factory(
            argv,
            cwd=str(config.working_directory),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            **process_group_popen_kwargs(),
        )
        self._pid = int(self._process.pid)
        self._process_identity = process_identity(self._pid)
        if not self._process_identity:
            self._terminate_unverified_startup()
            raise HermesServiceProcessError(
                "persistent Hermes worker process identity is unavailable"
            )
        if self._process.stdin is None or self._process.stdout is None:
            self.close()
            raise HermesServiceProcessError(
                "persistent Hermes worker stdio pipes are unavailable"
            )
        self._stdin: TextIO = self._process.stdin
        self._stdout: TextIO = self._process.stdout
        self._stderr_thread = Thread(
            target=self._drain_stderr,
            name=f"hermes-stderr-{config.worker_id}",
            daemon=True,
        )
        self._stderr_thread.start()

        try:
            handshake = self._exchange({"operation": "handshake"})
            verified = parse_companion_result(
                json.dumps(handshake, sort_keys=True),
                expected_operation="handshake",
            )
            self._registry_identity = HermesRegistryIdentity.from_handshake(verified)
        except Exception:
            self.close()
            raise

    @property
    def worker_id(self) -> str:
        return str(self.config.worker_id)

    @property
    def process_identity(self) -> str:
        return self._process_identity

    @property
    def registry_identity(self) -> HermesRegistryIdentity:
        return self._registry_identity

    @property
    def ready(self) -> bool:
        with self._state_lock:
            return (
                not self._closed
                and self._process.poll() is None
                and process_matches_identity(self._pid, self._process_identity)
            )

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def active_request_id(self) -> str | None:
        with self._state_lock:
            return self._active_request_id

    @property
    def termination_report(self) -> dict[str, Any]:
        with self._state_lock:
            return dict(self._termination_report)

    def stderr_text(self) -> str:
        with self._state_lock:
            return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def dispatch(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(request, Mapping):
            raise HermesCompanionProtocolError(
                "persistent Hermes request must be a mapping"
            )
        request_id = str(request.get("request_id") or "")
        if not request_id or request_id.isspace():
            raise HermesCompanionProtocolError(
                "persistent Hermes request_id is required"
            )
        with self._state_lock:
            if self._closed or not process_matches_identity(
                self._pid, self._process_identity
            ):
                raise HermesServiceProcessError(
                    "persistent Hermes worker is not ready"
                )
            if self._active_request_id is not None:
                raise HermesServiceProcessError(
                    "persistent Hermes worker already owns an active request"
                )
            self._active_request_id = request_id
        try:
            return self._exchange(request)
        finally:
            with self._state_lock:
                if self._active_request_id == request_id:
                    self._active_request_id = None

    def cancel(self, request_id: str) -> bool:
        normalized = str(request_id)
        with self._state_lock:
            if self._closed or self._active_request_id != normalized:
                return False
            if not process_matches_identity(self._pid, self._process_identity):
                self._closed = True
                return False
            report = terminate_process_tree(self._pid)
            self._termination_report = dict(report)
            self._closed = bool(report.get("terminated"))
            return bool(report.get("terminated"))

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            identity_matches = process_matches_identity(
                self._pid, self._process_identity
            )
            self._closed = True
        report: dict[str, Any]
        if identity_matches:
            report = terminate_process_tree(self._pid)
        else:
            report = {
                "pid": self._pid,
                "method": "identity_mismatch",
                "termination_attempted": False,
                "forced": False,
                "exit_code": 0,
                "terminated": self._process.poll() is not None,
                "error": "",
            }
        with self._state_lock:
            self._termination_report = dict(report)
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def _exchange(self, request: Mapping[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(
            dict(request),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ) + "\n"
        if len(encoded.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise HermesCompanionProtocolError(
                "persistent Hermes request exceeds maximum size"
            )
        with self._io_lock:
            if self._process.poll() is not None:
                raise HermesServiceProcessError(
                    self._dead_process_message("before request dispatch")
                )
            try:
                self._stdin.write(encoded)
                self._stdin.flush()
                raw_line = self._stdout.readline()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise HermesServiceProcessError(
                    self._dead_process_message("during request dispatch")
                ) from exc
        if not raw_line:
            raise HermesServiceProcessError(
                self._dead_process_message("before response publication")
            )
        try:
            response = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise HermesCompanionProtocolError(
                "persistent Hermes response is not valid JSON"
            ) from exc
        if not isinstance(response, dict):
            raise HermesCompanionProtocolError(
                "persistent Hermes response must be a JSON object"
            )
        return response

    def _dead_process_message(self, phase: str) -> str:
        return_code = self._process.poll()
        stderr = self.stderr_text().strip()
        detail = f"; stderr={stderr[-1000:]}" if stderr else ""
        return (
            f"persistent Hermes worker stopped {phase}; "
            f"exit_code={return_code}{detail}"
        )

    def _drain_stderr(self) -> None:
        stream = self._process.stderr
        if stream is None:
            return
        while True:
            try:
                chunk = stream.buffer.read(4096) if hasattr(stream, "buffer") else stream.read(4096)
            except Exception:
                return
            if not chunk:
                return
            data = chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8", errors="replace")
            self._append_stderr(data)

    def _append_stderr(self, data: bytes) -> None:
        limit = int(self.config.stderr_max_bytes)
        if limit <= 0:
            return
        with self._state_lock:
            self._stderr_chunks.append(data)
            self._stderr_size += len(data)
            while self._stderr_size > limit and self._stderr_chunks:
                removed = self._stderr_chunks.popleft()
                self._stderr_size -= len(removed)
            if self._stderr_size > limit and self._stderr_chunks:
                excess = self._stderr_size - limit
                self._stderr_chunks[0] = self._stderr_chunks[0][excess:]
                self._stderr_size = limit

    def _terminate_unverified_startup(self) -> None:
        try:
            terminate_process_tree(int(self._process.pid))
        except Exception:
            pass


def launch_persistent_workers(
    *,
    count: int,
    checkout: str | Path,
    working_directory: str | Path,
    hermes_home: str | Path | None = None,
    python_executable: str | Path = sys.executable,
    worker_id_prefix: str = "hermes-worker",
    max_output_bytes: int | None = None,
    startup_timeout_seconds: int = DEFAULT_COMPANION_TIMEOUT_SECONDS,
    environment: Mapping[str, str] | None = None,
) -> tuple[PersistentHermesWorker, ...]:
    if count < 1 or count > 32:
        raise HermesCompanionProtocolError(
            "persistent Hermes worker count must be between 1 and 32"
        )
    workers: list[PersistentHermesWorker] = []
    try:
        for index in range(count):
            workers.append(
                PersistentHermesWorker(
                    PersistentHermesWorkerConfig(
                        worker_id=f"{worker_id_prefix}-{index + 1}",
                        checkout=checkout,
                        working_directory=working_directory,
                        hermes_home=hermes_home,
                        python_executable=python_executable,
                        max_output_bytes=max_output_bytes,
                        startup_timeout_seconds=startup_timeout_seconds,
                        environment=environment,
                    )
                )
            )
        expected = workers[0].registry_identity
        if any(worker.registry_identity != expected for worker in workers[1:]):
            raise HermesServiceProcessError(
                "persistent Hermes workers published inconsistent registry identities"
            )
        return tuple(workers)
    except Exception:
        for worker in workers:
            worker.close()
        raise
