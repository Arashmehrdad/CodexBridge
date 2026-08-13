"""Shared durable mechanics for the production Codex repository backend."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from soma.worker_evidence.models import EvidenceSubmissionV1

from .backends import (
    ReasoningBackendObservationV1,
    ReasoningResultReferenceV1,
    make_backend_ref,
)
from .codex_app_server import CodexAppServerRpcError, CodexTurnEvidence
from .codex_repository_contract import (
    CODEX_REPOSITORY_EFFORT,
    CODEX_REPOSITORY_MODEL,
    CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256,
)
from .repository_assignment import RepositoryReasoningAssignmentV1
from .store import ReasoningBackendStore


class CodexRepositoryClient(Protocol):
    server_requests: list[dict[str, Any]]

    def start_thread(self, *, working_directory: str, model: str = "") -> dict[str, Any]: ...

    def begin_turn(
        self,
        *,
        thread_id: str,
        prompt: str,
        client_user_message_id: str,
        output_schema: dict[str, Any],
        model: str = "",
        effort: str = "",
    ) -> int: ...

    def wait_for_turn_started(
        self, *, thread_id: str, timeout_seconds: float
    ) -> str: ...

    def wait_for_turn_completed(
        self, *, thread_id: str, turn_id: str, timeout_seconds: float
    ) -> CodexTurnEvidence: ...

    def interrupt_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any]: ...

    def read_thread(
        self, thread_id: str, *, include_turns: bool = True
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


AssignmentResolver = Callable[[str], RepositoryReasoningAssignmentV1]
RepositoryRootResolver = Callable[[str], Path]
TaskIdResolver = Callable[[str], str]
ClientFactory = Callable[[], CodexRepositoryClient]
Preflight = Callable[[], Mapping[str, Any]]


@dataclass
class ActiveRepositorySession:
    client: CodexRepositoryClient
    thread_id: str
    turn_id: str = ""
    binding_settled: threading.Event = field(default_factory=threading.Event)
    cancellation_settled: threading.Event = field(default_factory=threading.Event)


class CodexRepositoryBackendError(RuntimeError):
    """Production repository backend configuration or provider evidence is invalid."""


class CodexRepositoryBackendSupport:
    kind = "soma_reasoning"
    executor = "codex_app_server_repository"

    def __init__(
        self,
        store: ReasoningBackendStore,
        *,
        assignment_resolver: AssignmentResolver,
        repository_root_resolver: RepositoryRootResolver,
        task_id_resolver: TaskIdResolver,
        client_factory: ClientFactory,
        preflight: Preflight,
        model: str = CODEX_REPOSITORY_MODEL,
        effort: str = CODEX_REPOSITORY_EFFORT,
        artifacts_root: Path | None = None,
    ) -> None:
        self.store = store
        self.assignment_resolver = assignment_resolver
        self.repository_root_resolver = repository_root_resolver
        self.task_id_resolver = task_id_resolver
        self.client_factory = client_factory
        self.preflight = preflight
        self.model = model
        self.effort = effort
        self.artifacts_root = Path(
            artifacts_root or (store.runs_dir / "reasoning_backend_evidence")
        )
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, ActiveRepositorySession] = {}
        self._active_lock = threading.RLock()

    def reserve(self) -> str:
        return make_backend_ref()

    @staticmethod
    def _json_bytes(value: Any) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def _artifact(self, backend_ref: str, name: str, value: Any) -> tuple[str, str]:
        payload = self._json_bytes(value)
        digest = hashlib.sha256(payload).hexdigest()
        directory = self.artifacts_root / backend_ref
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        temporary = directory / f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return f"reasoning-artifact:{backend_ref}:{name}", digest

    def _validate_preflight(self, result: Mapping[str, Any]) -> None:
        if str(result.get("auth_type") or "") != "chatgpt":
            raise CodexRepositoryBackendError(
                "repository Codex route requires ChatGPT-managed authentication"
            )
        if (
            str(result.get("protocol_manifest_sha256") or "")
            != CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256
        ):
            raise CodexRepositoryBackendError("Codex App Server protocol drift detected")
        models = result.get("models")
        if isinstance(models, (list, tuple, set)) and self.model not in {
            str(item) for item in models
        }:
            raise CodexRepositoryBackendError(
                f"Codex model {self.model!r} is not available"
            )
        if result.get("model_available") is False:
            raise CodexRepositoryBackendError(
                f"Codex model {self.model!r} is not available"
            )

    @staticmethod
    def _thread_id(result: Mapping[str, Any]) -> str:
        thread = result.get("thread")
        if not isinstance(thread, Mapping) or not isinstance(thread.get("id"), str):
            raise CodexRepositoryBackendError("thread/start returned no exact thread ID")
        value = str(thread["id"])
        if not value:
            raise CodexRepositoryBackendError("thread/start returned empty thread ID")
        return value

    @staticmethod
    def _provider_operation_ref(thread_id: str, turn_id: str) -> str:
        return f"codex:thread:{thread_id}:turn:{turn_id}"

    @staticmethod
    def _parse_provider_operation_ref(value: str) -> tuple[str, str]:
        prefix = "codex:thread:"
        marker = ":turn:"
        if not value.startswith(prefix) or marker not in value:
            raise CodexRepositoryBackendError(
                "stored Codex provider operation ref is invalid"
            )
        thread_id, turn_id = value[len(prefix) :].split(marker, 1)
        if not thread_id or not turn_id:
            raise CodexRepositoryBackendError(
                "stored Codex provider operation ref is incomplete"
            )
        return thread_id, turn_id

    def _binding(
        self,
        backend_ref: str,
        thread_id: str,
        turn_id: str,
        client_message_id: str,
    ) -> tuple[str, str, dict[str, Any]]:
        value = {
            "schema": "soma.reasoning.codex_repository.provider_binding.v1",
            "backend_ref": backend_ref,
            "provider": "codex",
            "transport": "app_server_stdio",
            "model": self.model,
            "effort": self.effort,
            "protocol_manifest_sha256": CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "client_user_message_id": client_message_id,
        }
        ref, digest = self._artifact(backend_ref, "provider_binding.json", value)
        return ref, digest, value

    def _record_terminal_without_result(
        self,
        *,
        backend_ref: str,
        operation_ref: str,
        binding_ref: str,
        binding_hash: str,
        provider_status: str,
        terminal_claim: str,
        events: tuple[dict[str, Any], ...],
        terminal_error: Any | None,
    ) -> None:
        value = {
            "schema": "soma.reasoning.codex_repository.terminal_evidence.v1",
            "provider_operation_ref": operation_ref,
            "provider_status": provider_status,
            "provider_terminal_claim": terminal_claim,
            "terminal_error": terminal_error,
            "events": list(events),
        }
        ref, digest = self._artifact(
            backend_ref, "provider_terminal_evidence.json", value
        )
        self.store.record_accepted_bound(
            backend_ref=backend_ref,
            provider_operation_ref=operation_ref,
            provider_binding_ref=binding_ref,
            provider_binding_hash=binding_hash,
            provider_status_raw=provider_status,
            provider_terminal_claim=terminal_claim,
            output_contract_disposition="not_available",
            last_event_cursor=str(len(events)),
        )
        self.store.record_terminal_evidence(
            backend_ref=backend_ref,
            raw_provider_evidence_root_ref=ref,
            raw_provider_evidence_root_hash=digest,
            error_code=f"provider_terminal_{terminal_claim}",
        )

    def query(self, backend_ref: str) -> ReasoningBackendObservationV1:
        return self.store.query(backend_ref)

    @staticmethod
    def _turn_status(thread: Mapping[str, Any], turn_id: str) -> str:
        turns = thread.get("turns")
        if not isinstance(turns, list):
            return ""
        for item in turns:
            if isinstance(item, Mapping) and item.get("id") == turn_id:
                status = item.get("status")
                return str(status) if isinstance(status, str) else ""
        return ""

    def _cancellation_evidence(
        self, backend_ref: str, operation_ref: str, outcome: str
    ) -> tuple[str, str]:
        return self._artifact(
            backend_ref,
            "cancellation.json",
            {
                "schema": "soma.reasoning.codex_repository.cancellation.v1",
                "backend_ref": backend_ref,
                "provider_operation_ref": operation_ref,
                "outcome": outcome,
            },
        )

    def cancel(self, backend_ref: str) -> ReasoningBackendObservationV1:
        observation = self.query(backend_ref)
        if not observation.exists:
            return observation
        with self._active_lock:
            active = self._active.get(backend_ref)
        if (
            observation.provider_binding_disposition != "bound"
            and active is not None
            and not active.binding_settled.is_set()
        ):
            active.binding_settled.wait(timeout=5)
            observation = self.query(backend_ref)
        operation_ref = observation.provider_operation_ref or ""
        if observation.provider_binding_disposition != "bound" or not operation_ref:
            ref, digest = self._cancellation_evidence(
                backend_ref, operation_ref or "unbound", "exact_provider_identity_unavailable"
            )
            self.store.record_cancellation_uncertain(
                backend_ref=backend_ref, evidence_ref=ref, evidence_hash=digest
            )
            return self.query(backend_ref)
        if observation.provider_terminal_claim != "none":
            ref, digest = self._cancellation_evidence(
                backend_ref, operation_ref, "already_terminal"
            )
            self.store.record_cancellation_rejected(
                backend_ref=backend_ref, evidence_ref=ref, evidence_hash=digest
            )
            return self.query(backend_ref)
        thread_id, turn_id = self._parse_provider_operation_ref(operation_ref)
        with self._active_lock:
            active = self._active.get(backend_ref)
        client = active.client if active is not None else self.client_factory()
        owns_client = active is None
        intent_ref, intent_hash = self._cancellation_evidence(
            backend_ref, operation_ref, "interrupt_requested"
        )
        self.store.record_cancellation_uncertain(
            backend_ref=backend_ref,
            evidence_ref=intent_ref,
            evidence_hash=intent_hash,
        )
        try:
            try:
                client.interrupt_turn(thread_id=thread_id, turn_id=turn_id)
                outcome: str = "interrupt_accepted"
                accepted: bool | None = True
            except CodexAppServerRpcError as exc:
                message = (
                    str(exc.error.get("message") or "")
                    if isinstance(exc.error, Mapping)
                    else str(exc.error)
                )
                if "no active turn to interrupt" not in message:
                    raise
                thread_result = client.read_thread(thread_id, include_turns=True)
                thread = thread_result.get("thread")
                status = (
                    self._turn_status(thread, turn_id)
                    if isinstance(thread, Mapping)
                    else ""
                )
                if status == "interrupted":
                    outcome, accepted = "already_interrupted", True
                elif status in {"completed", "failed"}:
                    outcome, accepted = f"completion_won_race:{status}", False
                else:
                    outcome, accepted = "interrupt_outcome_uncertain", None
            ref, digest = self._cancellation_evidence(backend_ref, operation_ref, outcome)
            if accepted is True:
                self.store.record_cancelled(
                    backend_ref=backend_ref, evidence_ref=ref, evidence_hash=digest
                )
            elif accepted is False:
                self.store.record_cancellation_rejected(
                    backend_ref=backend_ref, evidence_ref=ref, evidence_hash=digest
                )
            else:
                self.store.record_cancellation_uncertain(
                    backend_ref=backend_ref, evidence_ref=ref, evidence_hash=digest
                )
            return self.query(backend_ref)
        finally:
            if active is not None:
                active.cancellation_settled.set()
            if owns_client:
                client.close()

    def result_reference(self, backend_ref: str) -> ReasoningResultReferenceV1 | None:
        return self.store.result_reference(backend_ref)

    def load_evidence_submission(self, backend_ref: str) -> EvidenceSubmissionV1 | None:
        result = self.result_reference(backend_ref)
        if result is None:
            return None
        path = self.artifacts_root / backend_ref / "evidence_submission.json"
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CodexRepositoryBackendError(
                "reasoning evidence submission artifact is missing"
            ) from exc
        actual = hashlib.sha256(payload).hexdigest()
        if actual != result.evidence_submission_hash:
            raise CodexRepositoryBackendError(
                "reasoning evidence submission artifact hash mismatch"
            )
        try:
            value = json.loads(payload.decode("utf-8"))
            return EvidenceSubmissionV1.model_validate(value)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise CodexRepositoryBackendError(
                "reasoning evidence submission artifact is invalid"
            ) from exc
