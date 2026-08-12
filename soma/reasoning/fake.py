"""Deterministic no-provider reasoning backend for protocol and recovery tests."""

from __future__ import annotations

import hashlib
from typing import Literal

from .backends import (
    ReasoningBackendObservationV1,
    ReasoningResultReferenceV1,
    content_hash,
    make_backend_ref,
    reasoning_spec_hash,
    start_request_hash,
)
from .models import ReasoningSpecV1
from .store import ReasoningBackendStore


FakeReasoningCase = Literal[
    "success",
    "provider_rejection",
    "timeout",
    "long_running",
    "malformed_output",
    "result_publication",
    "crash_before_send",
    "ambiguous_ack",
]


class FakeReasoningCrashBeforeSend(RuntimeError):
    """Injected failure after durable claim but before provider-send boundary."""


class FakeReasoningBackend:
    """Scripted backend exercising durable semantics without any external provider."""

    kind = "soma_reasoning"
    executor = "fake_reasoning"

    def __init__(
        self, store: ReasoningBackendStore, *, case: FakeReasoningCase = "success"
    ):
        self.store = store
        self.case = case
        self.provider_create_calls = 0
        self.provider_cancel_calls = 0

    def reserve(self) -> str:
        return make_backend_ref()

    @staticmethod
    def _operation_ref(backend_ref: str, spec: ReasoningSpecV1) -> str:
        digest = hashlib.sha256(
            f"{backend_ref}\0{reasoning_spec_hash(spec)}".encode("utf-8")
        ).hexdigest()
        return f"fakeop_{digest[:32]}"

    @staticmethod
    def _binding(operation_ref: str) -> tuple[str, str]:
        payload = {"provider": "fake", "provider_operation_ref": operation_ref}
        digest = content_hash(payload)
        return f"fake_binding:{operation_ref}", digest

    @staticmethod
    def _evidence(prefix: str, backend_ref: str, detail: str) -> tuple[str, str]:
        digest = content_hash(
            {
                "schema": f"soma.reasoning.fake.{prefix}.v1",
                "backend_ref": backend_ref,
                "detail": detail,
            }
        )
        return f"fake_{prefix}:{digest}", digest

    def start(
        self, spec: ReasoningSpecV1, backend_ref: str
    ) -> ReasoningBackendObservationV1:
        self.store.reserve_run(backend_ref=backend_ref, spec=spec)
        attempt, _created = self.store.claim_start_attempt(
            backend_ref=backend_ref,
            spec=spec,
        )
        disposition = str(attempt["disposition"])
        if disposition in {"accepted_bound", "rejected", "outcome_unknown"}:
            return self.query(backend_ref)

        if self.case == "crash_before_send":
            raise FakeReasoningCrashBeforeSend("injected crash before provider send")

        request_hash = start_request_hash(spec, backend_ref)
        boundary_ref, boundary_hash = self._evidence(
            "send_boundary",
            backend_ref,
            request_hash,
        )
        entered = self.store.enter_send_boundary(
            backend_ref=backend_ref,
            request_hash=request_hash,
            evidence_ref=boundary_ref,
            evidence_hash=boundary_hash,
        )
        if not entered:
            return self.query(backend_ref)

        self.provider_create_calls += 1
        if self.case == "ambiguous_ack":
            return self.query(backend_ref)

        if self.case == "provider_rejection":
            self.store.record_rejected(
                backend_ref=backend_ref,
                error_code="fake_provider_rejected",
                provider_status_raw="rejected",
            )
            return self.query(backend_ref)

        if self.case == "timeout":
            self.store.record_rejected(
                backend_ref=backend_ref,
                error_code="fake_timeout",
                provider_status_raw="timeout",
            )
            return self.query(backend_ref)

        operation_ref = self._operation_ref(backend_ref, spec)
        binding_ref, binding_hash = self._binding(operation_ref)
        if self.case == "malformed_output":
            self.store.record_invalid_output(
                backend_ref=backend_ref,
                provider_operation_ref=operation_ref,
                provider_binding_ref=binding_ref,
                provider_binding_hash=binding_hash,
            )
            return self.query(backend_ref)

        if self.case in {"long_running", "result_publication"}:
            self.store.record_accepted_bound(
                backend_ref=backend_ref,
                provider_operation_ref=operation_ref,
                provider_binding_ref=binding_ref,
                provider_binding_hash=binding_hash,
                provider_status_raw="in_progress",
                provider_terminal_claim="none",
                output_contract_disposition="not_available",
                continuation_ref=f"fake_continuation:{operation_ref}",
                last_event_cursor="0",
            )
            return self.query(backend_ref)

        self.store.record_accepted_bound(
            backend_ref=backend_ref,
            provider_operation_ref=operation_ref,
            provider_binding_ref=binding_ref,
            provider_binding_hash=binding_hash,
            provider_status_raw="completed",
            provider_terminal_claim="success",
            output_contract_disposition="valid",
        )
        self._publish(backend_ref, operation_ref)
        return self.query(backend_ref)

    def _publish(self, backend_ref: str, operation_ref: str) -> None:
        evidence_ref, evidence_hash = self._evidence(
            "evidence_submission",
            backend_ref,
            operation_ref,
        )
        index_ref, index_hash = self._evidence(
            "evidence_index",
            backend_ref,
            operation_ref,
        )
        provenance_ref, provenance_hash = self._evidence(
            "provider_provenance",
            backend_ref,
            operation_ref,
        )
        raw_ref, raw_hash = self._evidence(
            "raw_provider_root",
            backend_ref,
            operation_ref,
        )
        usage_ref, usage_hash = self._evidence(
            "usage",
            backend_ref,
            operation_ref,
        )
        self.store.publish_result(
            backend_ref=backend_ref,
            output_contract_version="evidence_submission.v1",
            evidence_submission_ref=evidence_ref,
            evidence_submission_hash=evidence_hash,
            evidence_index_ref=index_ref,
            evidence_index_hash=index_hash,
            provider_provenance_index_ref=provenance_ref,
            provider_provenance_index_hash=provenance_hash,
            raw_provider_evidence_root_ref=raw_ref,
            raw_provider_evidence_root_hash=raw_hash,
            usage_ref=usage_ref,
            usage_hash=usage_hash,
            usage_summary={"input_tokens": 100, "output_tokens": 25},
        )

    def publish_scripted_result(
        self, backend_ref: str
    ) -> ReasoningBackendObservationV1:
        observation = self.query(backend_ref)
        if (
            not observation.exists
            or observation.provider_binding_disposition != "bound"
            or not observation.provider_operation_ref
        ):
            return observation
        self._publish(backend_ref, observation.provider_operation_ref)
        return self.query(backend_ref)

    def query(self, backend_ref: str) -> ReasoningBackendObservationV1:
        return self.store.query(backend_ref)

    def cancel(self, backend_ref: str) -> ReasoningBackendObservationV1:
        observation = self.query(backend_ref)
        if not observation.exists:
            return observation
        evidence_ref, evidence_hash = self._evidence(
            "cancellation",
            backend_ref,
            observation.provider_operation_ref or "unbound",
        )
        if observation.provider_binding_disposition == "uncertain":
            self.store.record_cancellation_uncertain(
                backend_ref=backend_ref,
                evidence_ref=evidence_ref,
                evidence_hash=evidence_hash,
            )
            return self.query(backend_ref)
        if (
            observation.provider_binding_disposition == "bound"
            and observation.provider_terminal_claim == "none"
        ):
            self.provider_cancel_calls += 1
            self.store.record_cancelled(
                backend_ref=backend_ref,
                evidence_ref=evidence_ref,
                evidence_hash=evidence_hash,
            )
            return self.query(backend_ref)
        self.store.record_cancellation_rejected(
            backend_ref=backend_ref,
            evidence_ref=evidence_ref,
            evidence_hash=evidence_hash,
        )
        return self.query(backend_ref)

    def result_reference(self, backend_ref: str) -> ReasoningResultReferenceV1 | None:
        return self.store.result_reference(backend_ref)
