"""Internal Codex App Server reasoning backend for the frozen G6 benchmark.

This backend is subordinate to canonical Task authority. It uses the existing
ReasoningBackendStore create-boundary state machine, binds exact Codex
thread/turn identities as provider provenance, and publishes only bounded
EvidenceSubmission references. Unknown create acknowledgement never causes an
automatic replacement turn.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from soma.worker_evidence.models import (
    EVIDENCE_SUBMISSION_SCHEMA_VERSION,
    EvidenceSubmissionV1,
)

from .backends import (
    ReasoningBackendObservationV1,
    ReasoningResultReferenceV1,
    content_hash,
    make_backend_ref,
    start_request_hash,
)
from .benchmark_evidence import (
    BenchmarkSemanticValidationError,
    build_evidence_submission,
    canonical_json_bytes,
    citation_catalog_contract_hash,
    compact_claim_citations,
    evidence_compaction_contract_hash,
    extract_usage,
    parse_assignment_packet,
    parse_semantic_output,
    semantic_output_schema,
    semantic_payload_hash,
    semantic_prompt,
    semantic_prompt_contract_hash,
    sha256_hex,
)
from .codex_app_server import (
    CodexAppServerClient,
    CodexAppServerRpcError,
    CodexTurnEvidence,
    StdioCodexTransport,
    canonical_schema_manifest_hash,
    resolve_codex_executable,
)
from .models import ReasoningBudgetsV1, ReasoningSpecV1
from .store import ReasoningBackendStore


CODEX_G6_MODEL = "gpt-5.6-luna"
CODEX_G6_EFFORT = "low"
CODEX_G6_PROTOCOL_MANIFEST_SHA256 = (
    "dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc"
)
CODEX_G6_PROVIDER_ROUTE_REF = "provider-route:codex-app-server:g6:v1"
CODEX_G6_EXECUTION_CONTRACT_REF = "execution-contract:codex-app-server:g6:v6"
CODEX_G6_OUTPUT_CONTRACT_REF = "output-contract:soma.agent_worker_benchmark.semantic.v4"
CODEX_G6_TOOL_POLICY_REF = "tool-policy:codex-g6-read-only:v1"
CODEX_G6_AUTHORITY_REF = "authority:codex-g6-read-only:v1"
CODEX_G6_DEFAULT_WALL_TIME_SECONDS = 120
CODEX_G6_DEFAULT_OUTPUT_BYTES = 32 * 1024


def _route_payload(model: str, effort: str) -> dict[str, Any]:
    return {
        "schema": "soma.reasoning.codex_g6.route.v1",
        "provider": "codex",
        "transport": "app_server_stdio",
        "authentication": "chatgpt",
        "model": model,
        "effort": effort,
        "protocol_manifest_sha256": CODEX_G6_PROTOCOL_MANIFEST_SHA256,
        "provider_internal_subagents": False,
    }


def provider_route_hash(
    model: str = CODEX_G6_MODEL, effort: str = CODEX_G6_EFFORT
) -> str:
    return content_hash(_route_payload(model, effort))


def output_contract_hash() -> str:
    return content_hash(semantic_output_schema())


def execution_contract_hash() -> str:
    """Hash the provider-facing execution semantics that may invalidate a trial."""

    return content_hash(
        {
            "schema": "soma.reasoning.codex_g6.execution_contract.v1",
            "provider_route_ref": CODEX_G6_PROVIDER_ROUTE_REF,
            "provider_route_hash": provider_route_hash(),
            "output_contract_ref": CODEX_G6_OUTPUT_CONTRACT_REF,
            "output_contract_hash": output_contract_hash(),
            "citation_catalog_contract_hash": citation_catalog_contract_hash(),
            "evidence_compaction_contract_hash": evidence_compaction_contract_hash(),
            "semantic_prompt_contract_hash": semantic_prompt_contract_hash(),
            "model": CODEX_G6_MODEL,
            "effort": CODEX_G6_EFFORT,
            "protocol_manifest_sha256": CODEX_G6_PROTOCOL_MANIFEST_SHA256,
            "provider_internal_concurrency_limit": 1,
            "mutation_policy": "read_only",
        }
    )


def tool_policy_hash() -> str:
    return content_hash(
        {
            "schema": "soma.reasoning.codex_g6.tool_policy.v1",
            "approval_policy": "never",
            "sandbox": "read_only",
            "tools": False,
            "mcp": False,
            "plugins": False,
            "protected_broker": False,
            "provider_internal_subagents": False,
        }
    )


def authority_hash() -> str:
    return content_hash(
        {
            "schema": "soma.reasoning.codex_g6.authority.v1",
            "mutation_policy": "read_only",
            "external_mutation": False,
            "canonical_task_authority": "soma",
        }
    )


def make_g6_reasoning_spec(
    *,
    assignment_ref: str,
    assignment_hash: str,
    wall_time_seconds: int = CODEX_G6_DEFAULT_WALL_TIME_SECONDS,
    output_bytes: int = CODEX_G6_DEFAULT_OUTPUT_BYTES,
    model: str = CODEX_G6_MODEL,
    effort: str = CODEX_G6_EFFORT,
) -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref=assignment_ref,
        assignment_hash=assignment_hash,
        output_contract_ref=CODEX_G6_OUTPUT_CONTRACT_REF,
        output_contract_hash=output_contract_hash(),
        tool_policy_ref=CODEX_G6_TOOL_POLICY_REF,
        tool_policy_hash=tool_policy_hash(),
        authority_ref=CODEX_G6_AUTHORITY_REF,
        authority_hash=authority_hash(),
        provider_route_ref=CODEX_G6_PROVIDER_ROUTE_REF,
        provider_route_hash=provider_route_hash(model, effort),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=wall_time_seconds,
            output_bytes=output_bytes,
            input_token_limit=None,
            output_token_limit=None,
            cost_limit_usd=None,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


class CodexG6Client(Protocol):
    server_requests: list[dict[str, Any]]

    def start_thread(
        self, *, working_directory: str, model: str = ""
    ) -> dict[str, Any]: ...

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


@dataclass(frozen=True)
class ResolvedG6Assignment:
    packet_bytes: bytes
    assignment_hash: str
    unit_id: str

    @property
    def packet_sha256(self) -> str:
        return sha256_hex(self.packet_bytes)


AssignmentResolver = Callable[[str], bytes | ResolvedG6Assignment]
TaskIdResolver = Callable[[str], str]
ClientFactory = Callable[[], CodexG6Client]
Preflight = Callable[[], Mapping[str, Any]]


@dataclass
class _ActiveSession:
    client: CodexG6Client
    thread_id: str
    turn_id: str = ""
    binding_settled: threading.Event = field(default_factory=threading.Event)
    cancellation_settled: threading.Event = field(default_factory=threading.Event)


class CodexG6BackendError(RuntimeError):
    """Local G6 backend configuration or provider evidence is invalid."""


class CodexG6ReasoningBackend:
    kind = "soma_reasoning"
    executor = "codex_app_server_g6"

    def __init__(
        self,
        store: ReasoningBackendStore,
        *,
        assignment_resolver: AssignmentResolver,
        task_id_resolver: TaskIdResolver,
        client_factory: ClientFactory,
        preflight: Preflight,
        working_directory: Path,
        model: str = CODEX_G6_MODEL,
        effort: str = CODEX_G6_EFFORT,
        artifacts_root: Path | None = None,
    ) -> None:
        self.store = store
        self.assignment_resolver = assignment_resolver
        self.task_id_resolver = task_id_resolver
        self.client_factory = client_factory
        self.preflight = preflight
        self.working_directory = Path(working_directory).resolve()
        self.model = model
        self.effort = effort
        self.artifacts_root = Path(
            artifacts_root or (store.runs_dir / "reasoning_backend_evidence")
        )
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self._active: dict[str, _ActiveSession] = {}
        self._active_lock = threading.RLock()

    def reserve(self) -> str:
        return make_backend_ref()

    def _validate_spec(self, spec: ReasoningSpecV1) -> ResolvedG6Assignment:
        expected = {
            "output_contract_ref": CODEX_G6_OUTPUT_CONTRACT_REF,
            "output_contract_hash": output_contract_hash(),
            "tool_policy_ref": CODEX_G6_TOOL_POLICY_REF,
            "tool_policy_hash": tool_policy_hash(),
            "authority_ref": CODEX_G6_AUTHORITY_REF,
            "authority_hash": authority_hash(),
            "provider_route_ref": CODEX_G6_PROVIDER_ROUTE_REF,
            "provider_route_hash": provider_route_hash(self.model, self.effort),
        }
        for field_name, value in expected.items():
            if getattr(spec, field_name) != value:
                raise CodexG6BackendError(
                    f"G6 reasoning spec {field_name} does not match route freeze"
                )
        if spec.mutation_policy != "read_only":
            raise CodexG6BackendError(
                "G6 Codex route requires read_only mutation policy"
            )
        if spec.continuation_policy != "none":
            raise CodexG6BackendError(
                "G6 screening does not permit provider continuation"
            )
        if spec.budgets.provider_internal_concurrency_limit != 1:
            raise CodexG6BackendError(
                "G6 canonical benchmark requires provider internal concurrency exactly 1"
            )
        if spec.context_refs or spec.dependency_proof_refs:
            raise CodexG6BackendError(
                "G6 screening assignment must not import context or dependency evidence"
            )
        resolved = self.assignment_resolver(spec.assignment_ref)
        if isinstance(resolved, bytes):
            packet_value = parse_assignment_packet(resolved)
            unit = packet_value.get("unit")
            unit_id = (
                str(unit.get("unit_id") or "") if isinstance(unit, Mapping) else ""
            )
            assignment = ResolvedG6Assignment(
                packet_bytes=resolved,
                assignment_hash=sha256_hex(resolved),
                unit_id=unit_id,
            )
        elif isinstance(resolved, ResolvedG6Assignment):
            assignment = resolved
        else:
            raise CodexG6BackendError(
                "assignment resolver returned unsupported material"
            )
        if assignment.assignment_hash != spec.assignment_hash:
            raise CodexG6BackendError(
                "resolved canonical assignment identity does not match ReasoningSpec hash"
            )
        packet_value = parse_assignment_packet(assignment.packet_bytes)
        unit = packet_value.get("unit")
        packet_unit_id = (
            str(unit.get("unit_id") or "") if isinstance(unit, Mapping) else ""
        )
        if not assignment.unit_id or assignment.unit_id != packet_unit_id:
            raise CodexG6BackendError(
                "resolved benchmark unit identity does not match packet"
            )
        return assignment

    def _validate_preflight(self, result: Mapping[str, Any]) -> None:
        if str(result.get("auth_type") or "") != "chatgpt":
            raise CodexG6BackendError(
                "Codex G6 route requires ChatGPT-managed authentication"
            )
        if (
            str(result.get("protocol_manifest_sha256") or "")
            != CODEX_G6_PROTOCOL_MANIFEST_SHA256
        ):
            raise CodexG6BackendError("Codex App Server protocol drift detected")
        models = result.get("models")
        if isinstance(models, (list, tuple, set)) and self.model not in {
            str(item) for item in models
        }:
            raise CodexG6BackendError(f"Codex model {self.model!r} is not available")
        if result.get("model_available") is False:
            raise CodexG6BackendError(f"Codex model {self.model!r} is not available")

    @staticmethod
    def _thread_id(result: Mapping[str, Any]) -> str:
        thread = result.get("thread")
        if not isinstance(thread, Mapping) or not isinstance(thread.get("id"), str):
            raise CodexG6BackendError("thread/start returned no exact thread ID")
        value = str(thread["id"])
        if not value:
            raise CodexG6BackendError("thread/start returned empty thread ID")
        return value

    @staticmethod
    def _provider_operation_ref(thread_id: str, turn_id: str) -> str:
        return f"codex:thread:{thread_id}:turn:{turn_id}"

    @staticmethod
    def _parse_provider_operation_ref(value: str) -> tuple[str, str]:
        prefix = "codex:thread:"
        marker = ":turn:"
        if not value.startswith(prefix) or marker not in value:
            raise CodexG6BackendError("stored Codex provider operation ref is invalid")
        thread_id, turn_id = value[len(prefix) :].split(marker, 1)
        if not thread_id or not turn_id:
            raise CodexG6BackendError(
                "stored Codex provider operation ref is incomplete"
            )
        return thread_id, turn_id

    def _artifact(self, backend_ref: str, name: str, value: Any) -> tuple[str, str]:
        payload = canonical_json_bytes(value)
        digest = sha256_hex(payload)
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

    def _binding(
        self, backend_ref: str, thread_id: str, turn_id: str, client_message_id: str
    ) -> tuple[str, str, dict[str, Any]]:
        value = {
            "schema": "soma.reasoning.codex_g6.provider_binding.v1",
            "backend_ref": backend_ref,
            "provider": "codex",
            "transport": "app_server_stdio",
            "model": self.model,
            "effort": self.effort,
            "protocol_manifest_sha256": CODEX_G6_PROTOCOL_MANIFEST_SHA256,
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
        terminal_evidence = {
            "schema": "soma.reasoning.codex_g6.terminal_evidence.v1",
            "provider_operation_ref": operation_ref,
            "provider_status": provider_status,
            "provider_terminal_claim": terminal_claim,
            "terminal_error": terminal_error,
            "events": list(events),
        }
        terminal_ref, terminal_hash = self._artifact(
            backend_ref, "provider_terminal_evidence.json", terminal_evidence
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
            raw_provider_evidence_root_ref=terminal_ref,
            raw_provider_evidence_root_hash=terminal_hash,
            error_code=f"provider_terminal_{terminal_claim}",
        )

    def start(
        self, spec: ReasoningSpecV1, backend_ref: str
    ) -> ReasoningBackendObservationV1:
        assignment = self._validate_spec(spec)
        packet = assignment.packet_bytes
        task_id = self.task_id_resolver(backend_ref)
        if not task_id:
            raise CodexG6BackendError(
                "canonical task_id resolver returned no task identity"
            )

        self.store.reserve_run(backend_ref=backend_ref, spec=spec)
        attempt, _created = self.store.claim_start_attempt(
            backend_ref=backend_ref, spec=spec
        )
        if str(attempt["disposition"]) in {
            "accepted_bound",
            "rejected",
            "outcome_unknown",
        }:
            return self.query(backend_ref)

        self._validate_preflight(self.preflight())
        client = self.client_factory()
        session: _ActiveSession | None = None
        boundary_entered = False
        bound = False
        try:
            thread_id = self._thread_id(
                client.start_thread(
                    working_directory=str(self.working_directory), model=self.model
                )
            )
            session = _ActiveSession(client=client, thread_id=thread_id)
            with self._active_lock:
                self._active[backend_ref] = session

            request_hash = start_request_hash(spec, backend_ref)
            client_message_id = (
                "soma-g6-"
                + content_hash(
                    {"backend_ref": backend_ref, "request_hash": request_hash}
                )[:24]
            )
            boundary = {
                "schema": "soma.reasoning.codex_g6.send_boundary.v1",
                "backend_ref": backend_ref,
                "start_request_hash": request_hash,
                "thread_id": thread_id,
                "client_user_message_id": client_message_id,
                "assignment_hash": spec.assignment_hash,
            }
            boundary_ref, boundary_hash = self._artifact(
                backend_ref, "send_boundary.json", boundary
            )
            boundary_entered = self.store.enter_send_boundary(
                backend_ref=backend_ref,
                request_hash=request_hash,
                evidence_ref=boundary_ref,
                evidence_hash=boundary_hash,
            )
            if not boundary_entered:
                return self.query(backend_ref)

            client.begin_turn(
                thread_id=thread_id,
                prompt=semantic_prompt(packet),
                client_user_message_id=client_message_id,
                output_schema=semantic_output_schema(),
                model=self.model,
                effort=self.effort,
            )
            turn_id = client.wait_for_turn_started(
                thread_id=thread_id,
                timeout_seconds=min(30.0, float(spec.budgets.wall_time_seconds)),
            )
            session.turn_id = turn_id
            operation_ref = self._provider_operation_ref(thread_id, turn_id)
            binding_ref, binding_hash, binding_value = self._binding(
                backend_ref, thread_id, turn_id, client_message_id
            )
            self.store.record_accepted_bound(
                backend_ref=backend_ref,
                provider_operation_ref=operation_ref,
                provider_binding_ref=binding_ref,
                provider_binding_hash=binding_hash,
                provider_status_raw="in_progress",
                provider_terminal_claim="none",
                output_contract_disposition="not_available",
                continuation_ref=f"codex:thread:{thread_id}",
                last_event_cursor="0",
            )
            bound = True
            session.binding_settled.set()

            started_at = time.monotonic()
            turn = client.wait_for_turn_completed(
                thread_id=thread_id,
                turn_id=turn_id,
                timeout_seconds=float(spec.budgets.wall_time_seconds),
            )
            wall_time = max(0.0, time.monotonic() - started_at)
            usage = extract_usage(turn.token_usage_events)
            if turn.agent_message or usage.total_tokens > 0:
                self._artifact(
                    backend_ref,
                    "model_generation_observed.json",
                    {
                        "schema": "soma.reasoning.codex_g6.model_generation_observed.v1",
                        "provider_operation_ref": operation_ref,
                        "provider_status": turn.status,
                        "agent_message_present": bool(turn.agent_message),
                        "usage": usage.model_dump(mode="json"),
                    },
                )
            if turn.status == "interrupted":
                current = self.store.query(backend_ref)
                if current.cancellation_disposition == "uncertain":
                    session.cancellation_settled.wait(timeout=5)
                    current = self.store.query(backend_ref)
                if current.cancellation_disposition in {"accepted", "uncertain"}:
                    return current
                self._record_terminal_without_result(
                    backend_ref=backend_ref,
                    operation_ref=operation_ref,
                    binding_ref=binding_ref,
                    binding_hash=binding_hash,
                    provider_status="interrupted",
                    terminal_claim="incomplete",
                    events=turn.events,
                    terminal_error=turn.terminal_error,
                )
                return self.query(backend_ref)
            if turn.status != "completed":
                self._record_terminal_without_result(
                    backend_ref=backend_ref,
                    operation_ref=operation_ref,
                    binding_ref=binding_ref,
                    binding_hash=binding_hash,
                    provider_status=turn.status or "failed",
                    terminal_claim="failure",
                    events=turn.events,
                    terminal_error=turn.terminal_error,
                )
                return self.query(backend_ref)

            self.store.record_accepted_bound(
                backend_ref=backend_ref,
                provider_operation_ref=operation_ref,
                provider_binding_ref=binding_ref,
                provider_binding_hash=binding_hash,
                provider_status_raw="completed",
                provider_terminal_claim="success",
                output_contract_disposition="not_available",
                continuation_ref=f"codex:thread:{thread_id}",
                last_event_cursor=str(len(turn.events)),
            )
            event_ref, event_hash = self._artifact(
                backend_ref, "provider_events.json", list(turn.events)
            )
            usage_ref, usage_hash = self._artifact(
                backend_ref, "usage.json", usage.model_dump(mode="json")
            )
            if client.server_requests:
                diagnostic_ref, diagnostic_hash = self._artifact(
                    backend_ref,
                    "invalid_output_evidence.json",
                    {
                        "schema": "soma.reasoning.codex_g6.invalid_output_evidence.v1",
                        "provider_operation_ref": operation_ref,
                        "error_code": "provider_requested_disallowed_capability",
                        "server_request_count": len(client.server_requests),
                        "provider_event_root_ref": event_ref,
                        "provider_event_root_hash": event_hash,
                        "usage": usage.model_dump(mode="json"),
                    },
                )
                self.store.record_invalid_output(
                    backend_ref=backend_ref,
                    provider_operation_ref=operation_ref,
                    provider_binding_ref=binding_ref,
                    provider_binding_hash=binding_hash,
                    error_code="provider_requested_disallowed_capability",
                )
                self.store.record_terminal_evidence(
                    backend_ref=backend_ref,
                    raw_provider_evidence_root_ref=diagnostic_ref,
                    raw_provider_evidence_root_hash=diagnostic_hash,
                    error_code="provider_requested_disallowed_capability",
                )
                return self.query(backend_ref)

            try:
                semantic = parse_semantic_output(turn.agent_message)
                provenance = {
                    "schema": "soma.reasoning.codex_g6.provenance.v1",
                    "provider_operation_ref": operation_ref,
                    "provider_binding": binding_value,
                    "provider_event_count": len(turn.events),
                    "provider_event_root_ref": event_ref,
                    "provider_event_root_hash": event_hash,
                    "server_request_count": len(client.server_requests),
                }
                provenance_ref, provenance_hash = self._artifact(
                    backend_ref, "provider_provenance.json", provenance
                )
                selected_citations, omitted_citation_references = (
                    compact_claim_citations(semantic)
                )
                provider_citation_reference_count = sum(
                    len(claim.supports_citation_ids) + len(claim.opposes_citation_ids)
                    for claim in semantic.claims
                )
                published_evidence_count = sum(
                    len(citation_ids) for citation_ids in selected_citations.values()
                )
                assessment = {
                    "schema": "soma.agent_worker_benchmark.assessment.v1",
                    "unit_id": assignment.unit_id,
                    "assignment_ref": spec.assignment_ref,
                    "assignment_hash": spec.assignment_hash,
                    "packet_sha256": assignment.packet_sha256,
                    "semantic_payload_sha256": semantic_payload_hash(semantic),
                    "submission_disposition": semantic.submission_disposition,
                    "critical_trap": semantic.critical_trap.model_dump(mode="json"),
                    "claim_count": len(semantic.claims),
                    "evidence_count": published_evidence_count,
                    "provider_citation_reference_count": provider_citation_reference_count,
                    "published_evidence_count": published_evidence_count,
                    "omitted_citation_reference_count": omitted_citation_references,
                    "uncertainty_count": len(semantic.uncertainties),
                    "blocker_count": len(semantic.blockers),
                    "claims_without_support": sum(
                        1
                        for claim in semantic.claims
                        if not claim.supports_citation_ids
                    ),
                    "claim_fact_keys": sorted(
                        {claim.subject_key for claim in semantic.claims}
                    ),
                    "evidence_fact_keys": sorted(
                        {
                            claim.subject_key
                            for claim in semantic.claims
                            if claim.supports_citation_ids or claim.opposes_citation_ids
                        }
                    ),
                }
                assessment_ref, assessment_hash = self._artifact(
                    backend_ref, "benchmark_assessment.json", assessment
                )
                submission = build_evidence_submission(
                    payload=semantic,
                    packet_bytes=packet,
                    task_id=task_id,
                    backend_ref=backend_ref,
                    assignment_ref=spec.assignment_ref,
                    assignment_hash=spec.assignment_hash,
                    provider_model=self.model,
                    provider_thread_id=thread_id,
                    usage=usage,
                    wall_time_seconds=wall_time,
                    provenance_refs=(
                        (binding_ref, binding_hash),
                        (provenance_ref, provenance_hash),
                        (assessment_ref, assessment_hash),
                    ),
                    raw_provider_ref=event_ref,
                    raw_provider_hash=event_hash,
                )
                submission_value = submission.model_dump(mode="json")
                submission_ref, submission_hash = self._artifact(
                    backend_ref, "evidence_submission.json", submission_value
                )
                evidence_index = {
                    "schema": "soma.reasoning.codex_g6.evidence_index.v1",
                    "submission_ref": submission_ref,
                    "submission_hash": submission_hash,
                    "benchmark_assessment_ref": assessment_ref,
                    "benchmark_assessment_hash": assessment_hash,
                    "records": [
                        {
                            "evidence_id": item.evidence_id,
                            "source_ref": item.source_ref,
                            "source_hash": item.source_hash,
                            "locator": item.locator,
                            "fact_key": item.fact_key,
                        }
                        for item in submission.evidence
                    ],
                }
                evidence_index_ref, evidence_index_hash = self._artifact(
                    backend_ref, "evidence_index.json", evidence_index
                )
                self.store.publish_result(
                    backend_ref=backend_ref,
                    output_contract_version=EVIDENCE_SUBMISSION_SCHEMA_VERSION,
                    evidence_submission_ref=submission_ref,
                    evidence_submission_hash=submission_hash,
                    evidence_index_ref=evidence_index_ref,
                    evidence_index_hash=evidence_index_hash,
                    provider_provenance_index_ref=provenance_ref,
                    provider_provenance_index_hash=provenance_hash,
                    raw_provider_evidence_root_ref=event_ref,
                    raw_provider_evidence_root_hash=event_hash,
                    usage_ref=usage_ref,
                    usage_hash=usage_hash,
                    usage_summary=usage.model_dump(mode="json"),
                )
            except (BenchmarkSemanticValidationError, ValueError) as exc:
                diagnostic_ref, diagnostic_hash = self._artifact(
                    backend_ref,
                    "invalid_output_evidence.json",
                    {
                        "schema": "soma.reasoning.codex_g6.invalid_output_evidence.v1",
                        "provider_operation_ref": operation_ref,
                        "error_code": "invalid_benchmark_output",
                        "validation_error_type": type(exc).__name__,
                        "validation_error": str(exc),
                        "agent_message_sha256": sha256_hex(
                            turn.agent_message.encode("utf-8")
                        ),
                        "agent_message_characters": len(turn.agent_message),
                        "provider_event_root_ref": event_ref,
                        "provider_event_root_hash": event_hash,
                        "usage": usage.model_dump(mode="json"),
                    },
                )
                self.store.record_invalid_output(
                    backend_ref=backend_ref,
                    provider_operation_ref=operation_ref,
                    provider_binding_ref=binding_ref,
                    provider_binding_hash=binding_hash,
                    error_code="invalid_benchmark_output",
                )
                self.store.record_terminal_evidence(
                    backend_ref=backend_ref,
                    raw_provider_evidence_root_ref=diagnostic_ref,
                    raw_provider_evidence_root_hash=diagnostic_hash,
                    error_code="invalid_benchmark_output",
                )
            return self.query(backend_ref)
        except BaseException:
            # Before the turn send boundary, retry is still mechanically safe. After
            # it, the store deliberately remains outcome_unknown unless exact binding
            # was already recorded. Never synthesize a provider identity here.
            if boundary_entered and not bound:
                return self.query(backend_ref)
            raise
        finally:
            if session is not None:
                session.binding_settled.set()
            with self._active_lock:
                current = self._active.get(backend_ref)
                if current is session:
                    self._active.pop(backend_ref, None)
            client.close()

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
                "schema": "soma.reasoning.codex_g6.cancellation.v1",
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
            evidence_ref, evidence_hash = self._cancellation_evidence(
                backend_ref,
                operation_ref or "unbound",
                "exact_provider_identity_unavailable",
            )
            self.store.record_cancellation_uncertain(
                backend_ref=backend_ref,
                evidence_ref=evidence_ref,
                evidence_hash=evidence_hash,
            )
            return self.query(backend_ref)
        if observation.provider_terminal_claim != "none":
            evidence_ref, evidence_hash = self._cancellation_evidence(
                backend_ref, operation_ref, "already_terminal"
            )
            self.store.record_cancellation_rejected(
                backend_ref=backend_ref,
                evidence_ref=evidence_ref,
                evidence_hash=evidence_hash,
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
                outcome = "interrupt_accepted"
                accepted = True
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
                    outcome = "already_interrupted"
                    accepted = True
                elif status in {"completed", "failed"}:
                    outcome = f"completion_won_race:{status}"
                    accepted = False
                else:
                    outcome = "interrupt_outcome_uncertain"
                    accepted = None
            evidence_ref, evidence_hash = self._cancellation_evidence(
                backend_ref, operation_ref, outcome
            )
            if accepted is True:
                self.store.record_cancelled(
                    backend_ref=backend_ref,
                    evidence_ref=evidence_ref,
                    evidence_hash=evidence_hash,
                )
            elif accepted is False:
                self.store.record_cancellation_rejected(
                    backend_ref=backend_ref,
                    evidence_ref=evidence_ref,
                    evidence_hash=evidence_hash,
                )
            else:
                self.store.record_cancellation_uncertain(
                    backend_ref=backend_ref,
                    evidence_ref=evidence_ref,
                    evidence_hash=evidence_hash,
                )
            return self.query(backend_ref)
        finally:
            if active is not None:
                active.cancellation_settled.set()
            if owns_client:
                client.close()

    def result_reference(self, backend_ref: str) -> ReasoningResultReferenceV1 | None:
        return self.store.result_reference(backend_ref)

    def _read_verified_json_artifact(
        self,
        backend_ref: str,
        name: str,
        *,
        expected_hash: str,
    ) -> dict[str, Any]:
        path = self.artifacts_root / backend_ref / name
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CodexG6BackendError(
                f"missing G6 reasoning artifact {name!r} for {backend_ref!r}"
            ) from exc
        actual = sha256_hex(payload)
        if actual != expected_hash:
            raise CodexG6BackendError(
                f"G6 reasoning artifact hash mismatch for {name!r}: "
                f"expected {expected_hash}, got {actual}"
            )
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CodexG6BackendError(
                f"G6 reasoning artifact {name!r} is not valid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise CodexG6BackendError(
                f"G6 reasoning artifact {name!r} must contain one JSON object"
            )
        return value

    def load_evidence_submission(self, backend_ref: str) -> EvidenceSubmissionV1 | None:
        result = self.result_reference(backend_ref)
        if result is None:
            return None
        value = self._read_verified_json_artifact(
            backend_ref,
            "evidence_submission.json",
            expected_hash=result.evidence_submission_hash,
        )
        return EvidenceSubmissionV1.model_validate(value)

    def load_benchmark_assessment(self, backend_ref: str) -> dict[str, Any] | None:
        result = self.result_reference(backend_ref)
        if result is None:
            return None
        observation = self.query(backend_ref)
        if not observation.evidence_index_hash:
            raise CodexG6BackendError(
                "G6 reasoning observation has no evidence-index hash"
            )
        evidence_index = self._read_verified_json_artifact(
            backend_ref,
            "evidence_index.json",
            expected_hash=observation.evidence_index_hash,
        )
        assessment_hash = evidence_index.get("benchmark_assessment_hash")
        if not isinstance(assessment_hash, str):
            raise CodexG6BackendError(
                "G6 evidence index does not contain benchmark assessment identity"
            )
        return self._read_verified_json_artifact(
            backend_ref,
            "benchmark_assessment.json",
            expected_hash=assessment_hash,
        )


def default_codex_g6_client_factory(working_directory: Path) -> ClientFactory:
    executable = resolve_codex_executable()
    cwd = Path(working_directory).resolve()

    def create() -> CodexAppServerClient:
        transport = StdioCodexTransport(
            codex_executable=executable, working_directory=str(cwd)
        )
        client = CodexAppServerClient(transport)
        client.initialize()
        return client

    return create


def _codex_command(executable: str, *arguments: str) -> list[str]:
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
        return [comspec, "/d", "/s", "/c", executable, *arguments]
    return [executable, *arguments]


def default_codex_g6_preflight(
    working_directory: Path,
    *,
    model: str = CODEX_G6_MODEL,
) -> Preflight:
    executable = resolve_codex_executable()
    cwd = Path(working_directory).resolve()

    def check() -> Mapping[str, Any]:
        with tempfile.TemporaryDirectory(prefix="soma-codex-g6-schema-") as temp_dir:
            completed = subprocess.run(
                _codex_command(
                    executable,
                    "app-server",
                    "generate-json-schema",
                    "--out",
                    temp_dir,
                ),
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            if completed.returncode != 0:
                raise CodexG6BackendError(
                    "Codex App Server schema generation failed: "
                    + completed.stderr[-1000:]
                )
            protocol_hash, schema_count = canonical_schema_manifest_hash(Path(temp_dir))

        client = default_codex_g6_client_factory(cwd)()
        try:
            account = client.account_read()
            models_result = client.model_list(include_hidden=False)
        finally:
            client.close()
        account_value = account.get("account") or account.get("data") or account
        auth_type = ""
        if isinstance(account_value, Mapping):
            auth_type = str(
                account_value.get("type")
                or account_value.get("authType")
                or account_value.get("auth_type")
                or ""
            ).lower()
        models_raw = models_result.get("data") or models_result.get("models") or []
        models: list[str] = []
        if isinstance(models_raw, list):
            for item in models_raw:
                if isinstance(item, Mapping):
                    candidate = item.get("model") or item.get("id") or item.get("slug")
                    if isinstance(candidate, str) and candidate:
                        models.append(candidate)
        return {
            "auth_type": auth_type,
            "protocol_manifest_sha256": protocol_hash,
            "schema_count": schema_count,
            "models": models,
            "model_available": model in set(models),
        }

    return check
