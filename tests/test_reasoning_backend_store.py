"""G2.2 durable reasoning backend store/protocol tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from soma.reasoning.backends import (
    ReasoningBackendObservationV1,
    reasoning_spec_hash,
    start_request_hash,
)
from soma.reasoning.models import ReasoningBudgetsV1, ReasoningSpecV1
from soma.reasoning.schema import (
    REASONING_BACKEND_MIGRATIONS,
    REASONING_BACKEND_SCHEMA_COMPONENT,
    REASONING_BACKEND_SCHEMA_VERSION,
    apply_reasoning_backend_migrations,
)
from soma.reasoning.store import (
    ReasoningBackendConflict,
    ReasoningBackendStore,
)


def _hash(character: str) -> str:
    return character * 64


def _spec(*, route: str = "route:fake") -> ReasoningSpecV1:
    return ReasoningSpecV1(
        assignment_ref="assignment:fixture",
        assignment_hash=_hash("1"),
        output_contract_ref="contract:evidence-submission-v1",
        output_contract_hash=_hash("2"),
        tool_policy_ref="tool-policy:read-only",
        tool_policy_hash=_hash("3"),
        authority_ref="authority:fixture",
        authority_hash=_hash("4"),
        provider_route_ref=route,
        provider_route_hash=_hash("5"),
        budgets=ReasoningBudgetsV1(
            wall_time_seconds=60,
            output_bytes=32 * 1024,
            provider_internal_concurrency_limit=1,
        ),
        continuation_policy="none",
        mutation_policy="read_only",
    )


def _store(tmp_path: Path) -> ReasoningBackendStore:
    return ReasoningBackendStore(tmp_path / "runs")


def test_schema_component_is_additive_idempotent_and_separate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.schema_version() == 1
    assert store.init_db() == []
    assert store.schema_state() == {
        "component": REASONING_BACKEND_SCHEMA_COMPONENT,
        "schema_version": REASONING_BACKEND_SCHEMA_VERSION,
        "target_schema_version": REASONING_BACKEND_SCHEMA_VERSION,
        "up_to_date": True,
        "tables": ["reasoning_backend_runs", "reasoning_backend_start_attempts"],
        "missing_tables": [],
    }
    with store.connect() as conn:
        marker = conn.execute(
            "SELECT name FROM soma_schema_migrations WHERE component = ? AND version = 1",
            (REASONING_BACKEND_SCHEMA_COMPONENT,),
        ).fetchone()
        assert marker[0] == "reasoning_backend_foundation"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_schema_migration_rolls_back_all_reasoning_objects(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    db_path = runs_dir / "soma.sqlite3"

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    version, name, statements = REASONING_BACKEND_MIGRATIONS[0]
    broken = ((version, name, (*statements, "SELECT * FROM missing_reasoning_table")),)
    with pytest.raises(sqlite3.OperationalError):
        apply_reasoning_backend_migrations(connect, migrations=broken)

    conn = connect()
    try:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            ).fetchall()
        }
        marker = conn.execute(
            "SELECT 1 FROM soma_schema_migrations WHERE component = ? AND version = 1",
            (REASONING_BACKEND_SCHEMA_COMPONENT,),
        ).fetchone()
    finally:
        conn.close()
    assert "reasoning_backend_runs" not in names
    assert "reasoning_backend_start_attempts" not in names
    assert marker is None


def test_backend_reservation_is_exact_and_conflicting_rebind_fails(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    spec = _spec()
    backend_ref = "reasoning_fixture"

    assert store.reserve_run(backend_ref=backend_ref, spec=spec) is True
    assert store.reserve_run(backend_ref=backend_ref, spec=spec) is False
    observation = store.query(backend_ref)
    assert observation.start_delivery_disposition == "not_attempted"
    assert observation.provider_binding_disposition == "unbound"

    with pytest.raises(ReasoningBackendConflict, match="different reasoning material"):
        store.reserve_run(backend_ref=backend_ref, spec=_spec(route="route:different"))


def test_single_start_attempt_and_send_boundary_are_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    spec = _spec()
    backend_ref = "reasoning_start_fixture"
    store.reserve_run(backend_ref=backend_ref, spec=spec)

    first, created = store.claim_start_attempt(backend_ref=backend_ref, spec=spec)
    replay, replay_created = store.claim_start_attempt(
        backend_ref=backend_ref, spec=spec
    )
    assert created is True
    assert replay_created is False
    assert replay["start_attempt_id"] == first["start_attempt_id"]
    assert store.table_counts() == {
        "reasoning_backend_runs": 1,
        "reasoning_backend_start_attempts": 1,
    }

    request_hash = start_request_hash(spec, backend_ref)
    assert (
        store.enter_send_boundary(
            backend_ref=backend_ref,
            request_hash=request_hash,
            evidence_ref="evidence:send-boundary",
            evidence_hash=_hash("6"),
        )
        is True
    )
    assert (
        store.enter_send_boundary(
            backend_ref=backend_ref,
            request_hash=request_hash,
            evidence_ref="evidence:send-boundary",
            evidence_hash=_hash("6"),
        )
        is False
    )

    attempt = store.start_attempt(backend_ref)
    observation = store.query(backend_ref)
    assert attempt["disposition"] == "outcome_unknown"
    assert observation.start_delivery_disposition == "outcome_unknown"
    assert observation.provider_binding_disposition == "uncertain"
    assert observation.output_contract_disposition == "uncertain"


def test_start_claim_conflict_uses_complete_spec_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = _spec()
    backend_ref = "reasoning_claim_conflict"
    store.reserve_run(backend_ref=backend_ref, spec=original)
    store.claim_start_attempt(backend_ref=backend_ref, spec=original)

    changed = _spec(route="route:different")
    assert reasoning_spec_hash(changed) != reasoning_spec_hash(original)
    with pytest.raises(ReasoningBackendConflict):
        store.claim_start_attempt(backend_ref=backend_ref, spec=changed)


def test_store_publishes_only_bounded_result_references(tmp_path: Path) -> None:
    store = _store(tmp_path)
    spec = _spec()
    backend_ref = "reasoning_result_fixture"
    store.reserve_run(backend_ref=backend_ref, spec=spec)
    store.claim_start_attempt(backend_ref=backend_ref, spec=spec)
    request_hash = start_request_hash(spec, backend_ref)
    assert store.enter_send_boundary(
        backend_ref=backend_ref,
        request_hash=request_hash,
        evidence_ref="evidence:send-boundary",
        evidence_hash=_hash("7"),
    )
    store.record_accepted_bound(
        backend_ref=backend_ref,
        provider_operation_ref="fakeop_fixture",
        provider_binding_ref="binding:fixture",
        provider_binding_hash=_hash("8"),
        provider_status_raw="completed",
        provider_terminal_claim="success",
        output_contract_disposition="valid",
    )
    store.publish_result(
        backend_ref=backend_ref,
        output_contract_version="evidence_submission.v1",
        evidence_submission_ref="evidence-submission:fixture",
        evidence_submission_hash=_hash("9"),
        evidence_index_ref="evidence-index:fixture",
        evidence_index_hash=_hash("a"),
        provider_provenance_index_ref="provider-provenance:fixture",
        provider_provenance_index_hash=_hash("b"),
        raw_provider_evidence_root_ref="provider-raw-root:fixture",
        raw_provider_evidence_root_hash=_hash("c"),
        usage_ref="usage:fixture",
        usage_hash=_hash("d"),
        usage_summary={"input_tokens": 10, "output_tokens": 5},
        published_at="2026-08-12T04:00:00+00:00",
    )

    observation = store.query(backend_ref)
    result = store.result_reference(backend_ref)
    assert observation.provider_terminal_claim == "success"
    assert observation.output_contract_disposition == "valid"
    assert observation.result_ref == "evidence-submission:fixture"
    assert observation.usage_summary == {"input_tokens": 10, "output_tokens": 5}
    assert result is not None
    assert result.evidence_submission_ref == "evidence-submission:fixture"
    assert result.raw_provider_evidence_root_ref == "provider-raw-root:fixture"
    assert "transcript" not in result.model_dump(mode="python")


def test_observation_is_backend_evidence_not_task_state() -> None:
    fields = set(ReasoningBackendObservationV1.model_fields)
    assert "state" not in fields
    assert "task_state" not in fields
    assert "phase" not in fields
    assert "start_delivery_disposition" in fields
    assert "provider_terminal_claim" in fields


def test_cancellation_evidence_is_paired_and_bounded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    spec = _spec()
    backend_ref = "reasoning_cancel_fixture"
    store.reserve_run(backend_ref=backend_ref, spec=spec)
    store.claim_start_attempt(backend_ref=backend_ref, spec=spec)
    assert store.enter_send_boundary(
        backend_ref=backend_ref,
        request_hash=start_request_hash(spec, backend_ref),
        evidence_ref="evidence:send-boundary",
        evidence_hash=_hash("e"),
    )
    store.record_accepted_bound(
        backend_ref=backend_ref,
        provider_operation_ref="fakeop_cancel",
        provider_binding_ref="binding:cancel",
        provider_binding_hash=_hash("f"),
        provider_status_raw="in_progress",
    )
    store.record_cancelled(
        backend_ref=backend_ref,
        evidence_ref="cancel-evidence:fixture",
        evidence_hash=_hash("1"),
    )
    observation = store.query(backend_ref)
    assert observation.cancellation_disposition == "accepted"
    assert observation.cancellation_evidence_ref == "cancel-evidence:fixture"
    assert observation.provider_terminal_claim == "cancelled"
