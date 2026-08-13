"""Scripted G6 Codex reasoning backend tests with zero provider execution."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from soma.agent_worker_benchmark import build_assignment_packet
from soma.reasoning.backends import start_request_hash
from soma.reasoning.benchmark_evidence import (
    BENCHMARK_SEMANTIC_SCHEMA_VERSION,
    citation_catalog,
)
from soma.reasoning.codex_app_server import (
    CodexAppServerTransportError,
    CodexTurnEvidence,
)
from soma.reasoning.codex_g6_backend import (
    CODEX_G6_MODEL,
    CODEX_G6_PROTOCOL_MANIFEST_SHA256,
    CodexG6BackendError,
    CodexG6ReasoningBackend,
    ResolvedG6Assignment,
    make_g6_reasoning_spec,
)
from soma.reasoning.store import ReasoningBackendStore


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT_REF = "benchmark:B01"


def _packet() -> bytes:
    return build_assignment_packet(REPO_ROOT, "B01")


def _citation_for(source_path: str, needle: str) -> str:
    matches = [
        item.citation_id
        for item in citation_catalog(_packet())
        if item.source_path == source_path and needle in item.excerpt
    ]
    assert len(matches) == 1, (source_path, needle, matches)
    return matches[0]


def _semantic_output() -> str:
    packet = json.loads(_packet())
    sources = {source["path"]: source for source in packet["sources"]}
    specs = [
        (
            "e1",
            sources["soma/tasks/models.py"],
            "class TaskState",
            "task.canonical_state_owner",
            "TaskState",
        ),
        (
            "e2",
            sources["soma/tasks/models.py"],
            "class TaskKind",
            "task.current_task_kind_set",
            1,
        ),
        (
            "e3",
            sources["soma/tasks/models.py"],
            "class BackendKind",
            "task.current_backend_kind_set",
            1,
        ),
        (
            "e4",
            sources["soma/tasks/projections.py"],
            "result_reference",
            "task.result_body_policy",
            "reference_only",
        ),
        (
            "e5",
            sources["soma/tasks/backends.py"],
            "class ExecutionBackend",
            "task.backend_protocol_shape",
            "protocol",
        ),
    ]
    claims = []
    citation_ids = []
    for index, (_evidence_id, source, needle, fact_key, _fact_value) in enumerate(
        specs, start=1
    ):
        citation_id = _citation_for(source["path"], needle)
        citation_ids.append(citation_id)
        claims.append(
            {
                "claim_id": f"c{index}",
                "claim_class": "observation",
                "subject_key": fact_key,
                "statement": f"Grounded fixture claim for {fact_key}.",
                "supports_citation_ids": [citation_id],
                "opposes_citation_ids": [],
                "uncertainty_ids": [],
            }
        )
    return json.dumps(
        {
            "schema_version": BENCHMARK_SEMANTIC_SCHEMA_VERSION,
            "submission_disposition": "complete",
            "executive_summary": "Scripted frozen-source evidence.",
            "claims": claims,
            "uncertainties": [],
            "blockers": [],
            "critical_trap": {
                "disposition": "false",
                "statement": "Admission is not substantive outcome acceptance.",
                "supports_citation_ids": [citation_ids[0]],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class ScriptedG6Client:
    def __init__(
        self,
        *,
        behavior: str = "success",
        thread_id: str = "thr_g6",
        turn_id: str = "turn_g6",
    ) -> None:
        self.behavior = behavior
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.server_requests: list[dict] = []
        self.start_thread_calls = 0
        self.begin_turn_calls = 0
        self.interrupt_calls: list[tuple[str, str]] = []
        self.read_calls: list[str] = []
        self.closed = False
        self.turn_started = threading.Event()
        self.interrupted = threading.Event()

    def start_thread(self, *, working_directory: str, model: str = "") -> dict:
        self.start_thread_calls += 1
        assert Path(working_directory).is_absolute()
        assert model == CODEX_G6_MODEL
        return {"thread": {"id": self.thread_id}}

    def begin_turn(self, **kwargs) -> int:
        self.begin_turn_calls += 1
        assert kwargs["thread_id"] == self.thread_id
        assert kwargs["model"] == CODEX_G6_MODEL
        assert kwargs["effort"] == "low"
        output_schema = kwargs["output_schema"]
        assert output_schema["additionalProperties"] is False
        assert "BenchmarkPacketCitationId" in output_schema["$defs"]
        claim_properties = output_schema["$defs"]["BenchmarkSemanticClaimV1"][
            "properties"
        ]
        assert claim_properties["subject_key"].get("enum")
        assert claim_properties["supports_citation_ids"]["items"] == {
            "$ref": "#/$defs/BenchmarkPacketCitationId"
        }
        assert "Do not implement or modify anything" in kwargs["prompt"]
        if self.behavior == "ambiguous_ack":
            raise CodexAppServerTransportError("injected lost acknowledgement")
        return 3

    def wait_for_turn_started(self, *, thread_id: str, timeout_seconds: float) -> str:
        assert thread_id == self.thread_id
        assert timeout_seconds > 0
        self.turn_started.set()
        return self.turn_id

    def wait_for_turn_completed(
        self, *, thread_id: str, turn_id: str, timeout_seconds: float
    ) -> CodexTurnEvidence:
        assert (thread_id, turn_id) == (self.thread_id, self.turn_id)
        terminal_error = None
        if self.behavior == "wait_for_interrupt":
            assert self.interrupted.wait(timeout=5)
            status = "interrupted"
            message = ""
        elif self.behavior == "provider_failed":
            status = "failed"
            message = ""
            terminal_error = {
                "message": "fixture invalid request",
                "code": "invalid_json_schema",
            }
        else:
            status = "completed"
            message = (
                "not-json" if self.behavior == "invalid_output" else _semantic_output()
            )
        token_usage_events = (
            ()
            if self.behavior == "provider_failed"
            else (
                {
                    "tokenUsage": {
                        "total": {
                            "inputTokens": 100,
                            "cachedInputTokens": 10,
                            "outputTokens": 25,
                            "reasoningOutputTokens": 5,
                            "totalTokens": 125,
                        }
                    }
                },
            )
        )
        return CodexTurnEvidence(
            thread_id=self.thread_id,
            turn_id=self.turn_id,
            status=status,
            events=(
                {"method": "turn/started", "params": {"threadId": self.thread_id}},
                {"method": "turn/completed", "params": {"threadId": self.thread_id}},
            ),
            agent_message=message,
            token_usage_events=token_usage_events,
            terminal_error=terminal_error,
        )

    def interrupt_turn(self, *, thread_id: str, turn_id: str) -> dict:
        self.interrupt_calls.append((thread_id, turn_id))
        self.interrupted.set()
        return {}

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> dict:
        self.read_calls.append(thread_id)
        return {
            "thread": {
                "id": thread_id,
                "turns": [{"id": self.turn_id, "status": "interrupted", "items": []}],
            }
        }

    def close(self) -> None:
        self.closed = True


def _preflight() -> dict:
    return {
        "auth_type": "chatgpt",
        "protocol_manifest_sha256": CODEX_G6_PROTOCOL_MANIFEST_SHA256,
        "models": [CODEX_G6_MODEL],
        "model_available": True,
    }


def _spec(packet: bytes | None = None):
    packet = packet or _packet()
    import hashlib

    return make_g6_reasoning_spec(
        assignment_ref=ASSIGNMENT_REF,
        assignment_hash=hashlib.sha256(packet).hexdigest(),
    )


def _backend(tmp_path: Path, client_factory, *, task_id="task_g6"):
    store = ReasoningBackendStore(tmp_path / "runs")
    packet = _packet()
    backend = CodexG6ReasoningBackend(
        store,
        assignment_resolver=lambda ref: packet if ref == ASSIGNMENT_REF else b"",
        task_id_resolver=lambda _backend_ref: task_id,
        client_factory=client_factory,
        preflight=_preflight,
        working_directory=REPO_ROOT,
    )
    return backend, store


def test_success_binds_exact_provider_identity_and_publishes_bounded_result(
    tmp_path: Path,
) -> None:
    client = ScriptedG6Client()
    backend, store = _backend(tmp_path, lambda: client)
    backend_ref = backend.reserve()

    observation = backend.start(_spec(), backend_ref)
    result = backend.result_reference(backend_ref)

    assert observation.start_delivery_disposition == "accepted_bound"
    assert observation.provider_binding_disposition == "bound"
    assert observation.provider_operation_ref == "codex:thread:thr_g6:turn:turn_g6"
    assert observation.provider_terminal_claim == "success"
    assert observation.output_contract_disposition == "valid"
    assert result is not None
    assert result.output_contract_version == "evidence_submission.v1"
    assert client.begin_turn_calls == 1
    assert client.server_requests == []
    assert observation.usage_summary == {
        "cached_input_tokens": 10,
        "input_tokens": 100,
        "output_tokens": 25,
        "reasoning_output_tokens": 5,
        "total_tokens": 125,
    }

    evidence_path = (
        store.runs_dir
        / "reasoning_backend_evidence"
        / backend_ref
        / "evidence_submission.json"
    )
    value = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert value["work_identity"]["task_id"] == "task_g6"
    assert value["work_identity"]["backend_ref"] == backend_ref
    generation_marker = (
        store.runs_dir
        / "reasoning_backend_evidence"
        / backend_ref
        / "model_generation_observed.json"
    )
    assert generation_marker.exists()
    assert value["producer"]["provider"] == "codex"
    assert value["producer"]["native_session_ref"] == "thr_g6"
    assert len(value["claims"]) == 5
    assert len(value["evidence"]) == 5


def test_canonical_work_package_hash_remains_submission_assignment_identity(
    tmp_path: Path,
) -> None:
    import hashlib

    packet = _packet()
    contract_hash = "c" * 64
    assignment_ref = "work-package:workpkg_" + "1" * 24
    client = ScriptedG6Client()
    store = ReasoningBackendStore(tmp_path / "runs")
    backend = CodexG6ReasoningBackend(
        store,
        assignment_resolver=lambda ref: ResolvedG6Assignment(
            packet_bytes=packet,
            assignment_hash=contract_hash,
            unit_id="B01",
        ),
        task_id_resolver=lambda _backend_ref: "task_g6_canonical",
        client_factory=lambda: client,
        preflight=_preflight,
        working_directory=REPO_ROOT,
    )
    backend_ref = backend.reserve()
    spec = make_g6_reasoning_spec(
        assignment_ref=assignment_ref,
        assignment_hash=contract_hash,
    )

    observation = backend.start(spec, backend_ref)

    assert observation.output_contract_disposition == "valid"
    directory = store.runs_dir / "reasoning_backend_evidence" / backend_ref
    submission = json.loads(
        (directory / "evidence_submission.json").read_text(encoding="utf-8")
    )
    assessment = json.loads(
        (directory / "benchmark_assessment.json").read_text(encoding="utf-8")
    )
    assert submission["assignment"] == {
        "contract_ref": assignment_ref,
        "contract_hash": contract_hash,
    }
    assert assessment["assignment_ref"] == assignment_ref
    assert assessment["assignment_hash"] == contract_hash
    assert assessment["packet_sha256"] == hashlib.sha256(packet).hexdigest()
    assert assessment["unit_id"] == "B01"


def test_terminal_replay_never_creates_a_second_provider_turn(tmp_path: Path) -> None:
    client = ScriptedG6Client()
    factories = 0

    def factory():
        nonlocal factories
        factories += 1
        return client

    backend, _store = _backend(tmp_path, factory)
    backend_ref = backend.reserve()
    first = backend.start(_spec(), backend_ref)
    second = backend.start(_spec(), backend_ref)

    assert first == second
    assert factories == 1
    assert client.begin_turn_calls == 1


def test_ambiguous_turn_send_stays_outcome_unknown_and_never_retries(
    tmp_path: Path,
) -> None:
    client = ScriptedG6Client(behavior="ambiguous_ack")
    backend, store = _backend(tmp_path, lambda: client)
    backend_ref = backend.reserve()

    first = backend.start(_spec(), backend_ref)
    second = backend.start(_spec(), backend_ref)

    assert first.start_delivery_disposition == "outcome_unknown"
    assert first.provider_binding_disposition == "uncertain"
    assert second == first
    assert client.begin_turn_calls == 1
    assert store.start_attempt(backend_ref)["disposition"] == "outcome_unknown"
    assert backend.result_reference(backend_ref) is None


def test_provider_terminal_failure_persists_exact_diagnostic_evidence(
    tmp_path: Path,
) -> None:
    client = ScriptedG6Client(behavior="provider_failed")
    backend, store = _backend(tmp_path, lambda: client)
    backend_ref = backend.reserve()

    observation = backend.start(_spec(), backend_ref)

    assert observation.provider_terminal_claim == "failure"
    assert observation.output_contract_disposition == "not_available"
    assert observation.error_code == "provider_terminal_failure"
    assert observation.raw_provider_evidence_root_ref is not None
    assert observation.raw_provider_evidence_root_hash is not None
    evidence_path = (
        store.runs_dir
        / "reasoning_backend_evidence"
        / backend_ref
        / "provider_terminal_evidence.json"
    )
    value = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert value["provider_status"] == "failed"
    assert value["provider_terminal_claim"] == "failure"
    assert value["terminal_error"] == {
        "message": "fixture invalid request",
        "code": "invalid_json_schema",
    }
    assert len(value["events"]) == 2
    generation_marker = (
        store.runs_dir
        / "reasoning_backend_evidence"
        / backend_ref
        / "model_generation_observed.json"
    )
    assert not generation_marker.exists()


def test_invalid_provider_output_is_bound_but_fails_output_contract(
    tmp_path: Path,
) -> None:
    client = ScriptedG6Client(behavior="invalid_output")
    backend, store = _backend(tmp_path, lambda: client)
    backend_ref = backend.reserve()

    observation = backend.start(_spec(), backend_ref)

    assert observation.provider_binding_disposition == "bound"
    assert observation.provider_terminal_claim == "success"
    assert observation.output_contract_disposition == "invalid"
    assert observation.error_code == "invalid_benchmark_output"
    assert observation.raw_provider_evidence_root_ref is not None
    assert observation.raw_provider_evidence_root_hash is not None
    diagnostic = json.loads(
        (
            store.runs_dir
            / "reasoning_backend_evidence"
            / backend_ref
            / "invalid_output_evidence.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostic["error_code"] == "invalid_benchmark_output"
    assert diagnostic["validation_error_type"] == "BenchmarkSemanticValidationError"
    assert "not exact JSON" in diagnostic["validation_error"]
    assert diagnostic["agent_message_characters"] == len("not-json")
    assert len(diagnostic["agent_message_sha256"]) == 64
    assert diagnostic["provider_event_root_ref"].endswith("provider_events.json")
    assert backend.result_reference(backend_ref) is None


def test_cancellation_uses_exact_live_thread_turn_pair(tmp_path: Path) -> None:
    client = ScriptedG6Client(behavior="wait_for_interrupt")
    backend, _store = _backend(tmp_path, lambda: client)
    backend_ref = backend.reserve()
    result_holder = []

    worker = threading.Thread(
        target=lambda: result_holder.append(backend.start(_spec(), backend_ref))
    )
    worker.start()
    assert client.turn_started.wait(timeout=5)

    cancelled = backend.cancel(backend_ref)
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert client.interrupt_calls == [("thr_g6", "turn_g6")]
    assert cancelled.cancellation_disposition == "accepted"
    assert cancelled.provider_terminal_claim == "cancelled"
    assert result_holder[0].provider_terminal_claim == "cancelled"


def test_restart_cancellation_recovers_exact_stored_provider_pair(
    tmp_path: Path,
) -> None:
    first_client = ScriptedG6Client()
    backend, store = _backend(tmp_path, lambda: first_client)
    backend_ref = backend.reserve()
    spec = _spec()
    store.reserve_run(backend_ref=backend_ref, spec=spec)
    attempt, _ = store.claim_start_attempt(backend_ref=backend_ref, spec=spec)
    request_hash = str(attempt["start_request_hash"])
    store.enter_send_boundary(
        backend_ref=backend_ref,
        request_hash=request_hash,
        evidence_ref="test:send-boundary",
        evidence_hash="a" * 64,
    )
    store.record_accepted_bound(
        backend_ref=backend_ref,
        provider_operation_ref="codex:thread:thr_restart:turn:turn_restart",
        provider_binding_ref="test:provider-binding",
        provider_binding_hash="b" * 64,
        provider_status_raw="in_progress",
    )

    restart_client = ScriptedG6Client(thread_id="thr_restart", turn_id="turn_restart")
    restarted = CodexG6ReasoningBackend(
        store,
        assignment_resolver=lambda _ref: _packet(),
        task_id_resolver=lambda _ref: "task_restart",
        client_factory=lambda: restart_client,
        preflight=_preflight,
        working_directory=REPO_ROOT,
    )
    cancelled = restarted.cancel(backend_ref)

    assert restart_client.interrupt_calls == [("thr_restart", "turn_restart")]
    assert cancelled.cancellation_disposition == "accepted"
    assert cancelled.provider_terminal_claim == "cancelled"


def test_missing_task_identity_stops_before_provider_client_creation(
    tmp_path: Path,
) -> None:
    created = 0

    def factory():
        nonlocal created
        created += 1
        return ScriptedG6Client()

    backend, _store = _backend(tmp_path, factory, task_id="")

    with pytest.raises(CodexG6BackendError, match="task_id"):
        backend.start(_spec(), backend.reserve())
    assert created == 0


def test_assignment_hash_mismatch_stops_before_provider_client_creation(
    tmp_path: Path,
) -> None:
    created = 0

    def factory():
        nonlocal created
        created += 1
        return ScriptedG6Client()

    backend, _store = _backend(tmp_path, factory)
    spec = _spec().model_copy(update={"assignment_hash": "f" * 64})

    with pytest.raises(CodexG6BackendError, match="canonical assignment identity"):
        backend.start(spec, backend.reserve())
    assert created == 0


def test_route_rejects_provider_internal_subagent_concurrency(tmp_path: Path) -> None:
    backend, _store = _backend(tmp_path, lambda: ScriptedG6Client())
    spec = _spec()
    spec = spec.model_copy(
        update={
            "budgets": spec.budgets.model_copy(
                update={"provider_internal_concurrency_limit": 2}
            )
        }
    )

    with pytest.raises(CodexG6BackendError, match="internal concurrency exactly 1"):
        backend.start(spec, backend.reserve())


def test_send_boundary_hash_matches_existing_reasoning_store_contract(
    tmp_path: Path,
) -> None:
    client = ScriptedG6Client(behavior="ambiguous_ack")
    backend, store = _backend(tmp_path, lambda: client)
    backend_ref = backend.reserve()
    spec = _spec()

    backend.start(spec, backend_ref)
    attempt = store.start_attempt(backend_ref)

    assert attempt is not None
    assert attempt["start_request_hash"] == start_request_hash(spec, backend_ref)
