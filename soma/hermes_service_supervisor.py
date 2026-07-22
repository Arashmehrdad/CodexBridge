from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Mapping

from .hermes_companion_protocol import HermesCompanionProtocolError
from .hermes_service import (
    HermesServiceError,
    HermesServiceIdentity,
    HermesServiceNotReadyError,
    HermesServiceRequest,
    HermesServiceResult,
    HermesServiceRuntime,
    HermesServiceWorker,
)
from .process_control import (
    process_identity,
    process_matches_identity,
    terminate_process_tree,
)

MAX_SUPERVISED_WORKERS = 32
MAX_REPLACEMENTS_PER_MAINTENANCE = 8

WorkerFactory = Callable[[str], HermesServiceWorker]


class HermesSupervisionError(HermesServiceError):
    """Supervision, adoption, or worker-replacement failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worker_record(worker: HermesServiceWorker) -> dict[str, Any]:
    pid = int(getattr(worker, "pid", 0) or 0)
    return {
        "worker_id": worker.worker_id,
        "pid": pid,
        "service_pid": int(getattr(worker, "service_pid", pid) or pid),
        "process_identity": worker.process_identity,
        "launcher_process_identity": str(
            getattr(worker, "launcher_process_identity", "")
        ),
        "registry_generation": worker.registry_identity.generation,
        "effective_schema_hash": (
            worker.registry_identity.effective_schema_hash
        ),
    }


@dataclass(frozen=True)
class HermesSupervisorConfig:
    service_instance_id: str
    service_build_identity: str
    worker_count: int
    state_path: str | Path

    def __post_init__(self) -> None:
        if not str(self.service_instance_id).strip():
            raise HermesCompanionProtocolError(
                "service_instance_id must not be empty"
            )
        if not str(self.service_build_identity).strip():
            raise HermesCompanionProtocolError(
                "service_build_identity must not be empty"
            )
        if (
            isinstance(self.worker_count, bool)
            or not isinstance(self.worker_count, int)
            or self.worker_count < 1
            or self.worker_count > MAX_SUPERVISED_WORKERS
        ):
            raise HermesCompanionProtocolError(
                "worker_count must be between 1 and "
                f"{MAX_SUPERVISED_WORKERS}"
            )
        object.__setattr__(self, "state_path", Path(self.state_path))


class HermesServiceSupervisor:
    """Durable supervision for one shared, version-pinned Hermes service.

    The supervisor owns worker launch, restart adoption, deterministic
    replacement of dead workers, and the persisted worker-identity records
    that make adoption decisions auditable across Soma restarts.
    Request, cancellation, ownership, and registry-transition contracts stay
    in :class:`HermesServiceRuntime` unchanged.
    """

    def __init__(
        self,
        config: HermesSupervisorConfig,
        *,
        worker_factory: WorkerFactory,
    ) -> None:
        self.config = config
        self._worker_factory = worker_factory
        self._lifecycle_lock = Lock()
        self._runtime: HermesServiceRuntime | None = None
        self._workers: dict[str, HermesServiceWorker] = {}
        self._replacement_serial = 0
        self._replacement_count = 0
        self._restart_adoption: list[dict[str, Any]] = []
        self._started_at: str | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            if self._runtime is not None:
                raise HermesSupervisionError(
                    "Hermes service supervisor is already started"
                )
            adoption = self._reconcile_previous_state()
            workers: list[HermesServiceWorker] = []
            try:
                for index in range(self.config.worker_count):
                    workers.append(
                        self._worker_factory(f"hermes-worker-{index + 1}")
                    )
                expected = workers[0].registry_identity
                for worker in workers[1:]:
                    if worker.registry_identity != expected:
                        raise HermesSupervisionError(
                            "supervised Hermes workers published "
                            "inconsistent registry identities"
                        )
                runtime = HermesServiceRuntime(
                    service_identity=HermesServiceIdentity.local(
                        service_instance_id=self.config.service_instance_id,
                        service_build_identity=(
                            self.config.service_build_identity
                        ),
                        process_identity=(
                            process_identity(os.getpid()) or "unavailable"
                        ),
                    ),
                    registry_identity=expected,
                    workers=tuple(workers),
                )
            except Exception:
                for worker in workers:
                    try:
                        worker.close()
                    except Exception:
                        pass
                raise
            self._runtime = runtime
            self._workers = {worker.worker_id: worker for worker in workers}
            self._restart_adoption = adoption
            self._started_at = _utc_now()
            self._persist_state()
            return {
                "ok": True,
                "started_at": self._started_at,
                "worker_count": len(workers),
                "restart_adoption": list(adoption),
                **expected.as_dict(),
            }

    def close(self) -> None:
        with self._lifecycle_lock:
            runtime = self._runtime
            self._runtime = None
            workers = list(self._workers.values())
            self._workers = {}
        if runtime is not None:
            runtime.close()
        for worker in workers:
            try:
                worker.close()
            except Exception:
                pass

    # -- request paths -----------------------------------------------------

    def execute(self, request: HermesServiceRequest) -> HermesServiceResult:
        runtime = self._require_runtime()
        try:
            return runtime.execute(request)
        finally:
            self._restore_capacity_quietly()

    def cancel(
        self, *, request_id: str, session_id: str, run_id: str
    ) -> bool:
        runtime = self._require_runtime()
        try:
            return runtime.cancel(
                request_id=request_id,
                session_id=session_id,
                run_id=run_id,
            )
        finally:
            self._restore_capacity_quietly()

    def reload_registry(
        self, *, worker_count: int | None = None
    ) -> dict[str, Any]:
        runtime = self._require_runtime()
        count = int(worker_count or self.config.worker_count)
        if count < 1 or count > MAX_SUPERVISED_WORKERS:
            raise HermesCompanionProtocolError(
                "worker_count must be between 1 and "
                f"{MAX_SUPERVISED_WORKERS}"
            )
        with self._lifecycle_lock:
            self._replacement_serial += 1
            serial = self._replacement_serial
        workers: list[HermesServiceWorker] = []
        try:
            for index in range(count):
                workers.append(
                    self._worker_factory(
                        f"hermes-worker-{index + 1}-g{serial}"
                    )
                )
            identity = workers[0].registry_identity
            health = runtime.reload_registry(
                registry_identity=identity,
                workers=tuple(workers),
            )
        except Exception:
            for worker in workers:
                try:
                    worker.close()
                except Exception:
                    pass
            raise
        with self._lifecycle_lock:
            self._workers = {worker.worker_id: worker for worker in workers}
            self._persist_state()
        return health

    def health(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            runtime = self._runtime
            replacement_count = self._replacement_count
            adoption = list(self._restart_adoption)
            started_at = self._started_at
        if runtime is None:
            return {
                "ok": False,
                "state": "stopped",
                "ready": False,
                "service_instance_id": self.config.service_instance_id,
                "worker_replacement_count": replacement_count,
                "restart_adoption": adoption,
                "supervisor_started_at": started_at,
            }
        return {
            **runtime.health(),
            "worker_replacement_count": replacement_count,
            "restart_adoption": adoption,
            "supervisor_started_at": started_at,
        }

    # -- supervision -------------------------------------------------------

    def restore_capacity(self) -> list[dict[str, Any]]:
        """Deterministically replace dead, unleased workers.

        Every replacement launches a fresh verified worker through the
        factory and requires exact registry-identity equality with the
        published generation; drift fails the replacement rather than
        silently changing the service's schema identity.
        """
        runtime = self._require_runtime()
        replacements: list[dict[str, Any]] = []
        for state in runtime.current_worker_states():
            if state["ready"] or state["leased"]:
                continue
            if len(replacements) >= MAX_REPLACEMENTS_PER_MAINTENANCE:
                break
            with self._lifecycle_lock:
                self._replacement_serial += 1
                serial = self._replacement_serial
            replacement_id = f"{state['worker_id'].split('#')[0]}#{serial}"
            replacement = self._worker_factory(replacement_id)
            try:
                replaced = runtime.replace_worker(
                    worker_id=state["worker_id"],
                    replacement=replacement,
                )
            except Exception:
                try:
                    replacement.close()
                except Exception:
                    pass
                raise
            with self._lifecycle_lock:
                self._replacement_count += 1
                self._workers.pop(replaced.worker_id, None)
                self._workers[replacement.worker_id] = replacement
                self._persist_state()
            replacements.append(
                {
                    "replaced_worker_id": replaced.worker_id,
                    "replacement_worker_id": replacement.worker_id,
                    "replaced_process_identity": (
                        replaced.process_identity
                    ),
                    "replacement_process_identity": (
                        replacement.process_identity
                    ),
                    "replaced_at": _utc_now(),
                }
            )
        return replacements

    # -- internals ---------------------------------------------------------

    def _require_runtime(self) -> HermesServiceRuntime:
        with self._lifecycle_lock:
            runtime = self._runtime
        if runtime is None:
            raise HermesServiceNotReadyError(
                "Hermes service supervisor is not started"
            )
        return runtime

    def _restore_capacity_quietly(self) -> None:
        try:
            self.restore_capacity()
        except Exception:
            # Capacity restoration is best-effort after a request; the next
            # explicit restore_capacity or health probe surfaces the failure.
            pass

    def _reconcile_previous_state(self) -> list[dict[str, Any]]:
        """Adopt-or-replace decision for workers recorded by a prior run.

        A restarted Soma process cannot re-attach the stdio pipes of
        a previous worker, so a recorded process that is still running and
        still matches its recorded start identity is deterministically
        terminated and replaced rather than silently orphaned. A recorded
        process that no longer matches is released without any termination:
        PID reuse must never kill an unrelated process.
        """
        state_path = Path(self.config.state_path)
        try:
            raw = state_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError:
            return []
        try:
            previous = json.loads(raw)
        except json.JSONDecodeError:
            return [
                {
                    "action": "discarded_corrupt_state",
                    "state_path": str(state_path),
                }
            ]
        adoption: list[dict[str, Any]] = []
        for record in previous.get("workers", ()):
            if not isinstance(record, Mapping):
                continue
            entry = {
                "worker_id": str(record.get("worker_id", "")),
                "pid": int(record.get("pid", 0) or 0),
                "service_pid": int(record.get("service_pid", 0) or 0),
            }
            terminated_any = False
            for pid_key, identity_key in (
                ("pid", "launcher_process_identity"),
                ("service_pid", "process_identity"),
            ):
                pid = int(record.get(pid_key, 0) or 0)
                identity = str(record.get(identity_key, "") or "")
                if pid > 0 and process_matches_identity(pid, identity):
                    report = terminate_process_tree(pid)
                    terminated_any = True
                    entry[f"{pid_key}_terminated"] = bool(
                        report.get("terminated")
                    )
            entry["action"] = (
                "replaced_stale_process"
                if terminated_any
                else "released"
            )
            adoption.append(entry)
        return adoption

    def _persist_state(self) -> None:
        """Atomically record current worker identities for restart adoption."""
        state_path = Path(self.config.state_path)
        payload = {
            "service_instance_id": self.config.service_instance_id,
            "service_build_identity": self.config.service_build_identity,
            "updated_at": _utc_now(),
            "workers": [
                _worker_record(worker)
                for worker in self._workers.values()
            ],
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix(state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, state_path)
