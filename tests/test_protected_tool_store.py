"""G4.2 durable protected mutation store/idempotency proofs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from soma.protected_tools.models import (
    ProtectedProviderProvenanceRefV1,
    ProtectedToolCallV1,
    ProtectedToolEffectV1,
)
from soma.protected_tools.schema import (
    PROTECTED_TOOL_SCHEMA_COMPONENT,
    PROTECTED_TOOL_TABLE_NAMES,
    apply_protected_tool_migrations,
)
from soma.protected_tools.store import (
    ProtectedToolConflict,
    ProtectedToolStateError,
    ProtectedToolStore,
)


ATTEMPT_ID = "wpattempt_" + "1" * 24
NOW = datetime(2026, 8, 12, 11, 30, tzinfo=timezone.utc)


def _hash(character: str) -> str:
    return character * 64


def _call(**overrides) -> ProtectedToolCallV1:
    payload = {
        "call_request_id": "protected-call-store-1",
        "task_id": "task-protected-store",
        "attempt_id": ATTEMPT_ID,
        "backend_ref": "reasoning-backend:store",
        "mandate_ref": "mandate:store",
        "mandate_hash": _hash("a"),
        "mandate_version": "v1",
        "project_id": "Project_Protected_Store",
        "resource_id": "Resource_Protected_Store",
        "scope_generation": 2,
        "capability_ref": "capability:repository-write",
        "capability_hash": _hash("b"),
        "tool_operation_ref": "tool-operation:repo-apply-v1",
        "tool_operation_hash": _hash("c"),
        "resource_key": "repository:d:/github/soma",
        "idempotency_key": "soma-slot:protected-store-1",
        "payload_ref": "payload:patch-store-1",
        "payload_hash": _hash("d"),
        "expected_task_state_version": 4,
        "expires_at": NOW + timedelta(minutes=10),
        "mutation_class": "repository",
        "provider_provenance_refs": (
            ProtectedProviderProvenanceRefV1(
                ref="provider-call:first",
                hash=_hash("e"),
            ),
        ),
    }
    payload.update(overrides)
    return ProtectedToolCallV1(**payload)


def _effect(call: ProtectedToolCallV1, **overrides) -> ProtectedToolEffectV1:
    payload = {
        "call_request_id": call.call_request_id,
        "request_hash": call.request_hash,
        "disposition": "acknowledged",
        "external_effect_ref": "repo-commit:store-abc",
        "external_effect_hash": _hash("f"),
        "evidence_ref": "evidence:store-ack",
        "evidence_hash": _hash("0"),
        "completed_at": NOW + timedelta(minutes=1),
    }
    payload.update(overrides)
    return ProtectedToolEffectV1(**payload)


def test_fresh_schema_is_additive_and_complete(tmp_path: Path) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    assert store.schema_version() == 2
    state = store.schema_state()
    assert state["component"] == PROTECTED_TOOL_SCHEMA_COMPONENT
    assert state["up_to_date"] is True
    with store.connect() as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert set(PROTECTED_TOOL_TABLE_NAMES) <= names


def test_migration_rolls_back_atomically_on_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "broken.sqlite3"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(db_path)

    migrations = (
        (
            1,
            "broken_protected_tool_migration",
            (
                "CREATE TABLE should_rollback(id INTEGER PRIMARY KEY)",
                "THIS IS NOT VALID SQLITE",
            ),
        ),
    )
    with pytest.raises(sqlite3.Error):
        apply_protected_tool_migrations(connect, migrations=migrations)
    with connect() as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone()
        migration = conn.execute(
            "SELECT version FROM soma_schema_migrations WHERE component = ?",
            (PROTECTED_TOOL_SCHEMA_COMPONENT,),
        ).fetchone()
    assert table is None
    assert migration is None


def test_same_idempotency_and_identity_replays_canonical_call_and_appends_provenance(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    first, created = store.reserve_call(_call(), now=NOW.isoformat())
    assert created is True

    replay_input = _call(
        call_request_id="protected-call-store-retry",
        provider_provenance_refs=(
            ProtectedProviderProvenanceRefV1(
                ref="provider-thread:retry",
                hash=_hash("9"),
            ),
        ),
    )
    replay, created = store.reserve_call(
        replay_input, now=(NOW + timedelta(seconds=1)).isoformat()
    )
    assert created is False
    assert replay.call_request_id == first.call_request_id
    assert replay.request_hash == first.request_hash
    assert {(item.ref, item.hash) for item in replay.provider_provenance_refs} == {
        ("provider-call:first", _hash("e")),
        ("provider-thread:retry", _hash("9")),
    }


def test_same_idempotency_key_with_changed_authority_or_effect_material_conflicts(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    store.reserve_call(_call())
    for changed in (
        _call(call_request_id="retry-1", payload_hash=_hash("1")),
        _call(call_request_id="retry-2", tool_operation_hash=_hash("2")),
        _call(call_request_id="retry-3", resource_key="repository:d:/github/other"),
        _call(call_request_id="retry-4", mandate_version="v2"),
    ):
        with pytest.raises(ProtectedToolConflict, match="idempotency key"):
            store.reserve_call(changed)


def test_same_call_request_id_cannot_be_rebound_to_another_idempotency_slot(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    store.reserve_call(_call())
    with pytest.raises(ProtectedToolConflict, match="call_request_id"):
        store.reserve_call(_call(idempotency_key="soma-slot:different"))


def test_effect_boundary_can_be_crossed_exactly_once_and_survives_restart(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    store = ProtectedToolStore(runs)
    call, _ = store.reserve_call(_call())
    assert (
        store.claim_effect_boundary(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref="evidence:send-boundary",
            evidence_hash=_hash("7"),
            now=NOW.isoformat(),
        )
        is True
    )

    restarted = ProtectedToolStore(runs)
    assert (
        restarted.claim_effect_boundary(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref="evidence:send-boundary-retry",
            evidence_hash=_hash("6"),
        )
        is False
    )
    observation = restarted.get_observation(call.call_request_id)
    assert observation["delivery_state"] == "effect_begun"
    assert observation["effective_disposition"] == "outcome_unknown"
    assert observation["effect"] is None
    assert observation["begin_evidence_ref"] == "evidence:send-boundary"


def test_acknowledged_effect_requires_effect_boundary_then_replays_exactly(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    call, _ = store.reserve_call(_call())
    effect = _effect(call)
    with pytest.raises(ProtectedToolStateError, match="effect boundary"):
        store.record_effect(effect)

    assert (
        store.claim_effect_boundary(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref="evidence:begin",
            evidence_hash=_hash("7"),
        )
        is True
    )
    stored, created = store.record_effect(effect)
    assert created is True
    assert stored.effect_hash == effect.effect_hash

    replay_input = effect.model_copy(update={"completed_at": NOW + timedelta(hours=1)})
    replay, created = store.record_effect(replay_input)
    assert created is False
    assert replay.effect_hash == effect.effect_hash
    assert replay.completed_at == effect.completed_at
    assert (
        store.claim_effect_boundary(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref="evidence:must-not-resend",
            evidence_hash=_hash("5"),
        )
        is False
    )


def test_conflicting_terminal_effect_is_rejected(tmp_path: Path) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    call, _ = store.reserve_call(_call())
    store.claim_effect_boundary(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        evidence_ref="evidence:begin",
        evidence_hash=_hash("7"),
    )
    store.record_effect(_effect(call))
    with pytest.raises(ProtectedToolConflict, match="different terminal effect"):
        store.record_effect(_effect(call, evidence_hash=_hash("3")))


def test_outcome_unknown_is_terminal_for_automatic_send_retry(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    store = ProtectedToolStore(runs)
    call, _ = store.reserve_call(_call())
    store.claim_effect_boundary(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        evidence_ref="evidence:begin-unknown",
        evidence_hash=_hash("7"),
    )
    unknown = _effect(
        call,
        disposition="outcome_unknown",
        external_effect_ref=None,
        external_effect_hash=None,
        evidence_ref="evidence:ambiguous-outcome",
        evidence_hash=_hash("4"),
    )
    store.record_effect(unknown)

    restarted = ProtectedToolStore(runs)
    observation = restarted.get_observation(call.call_request_id)
    assert observation["delivery_state"] == "resolved"
    assert observation["effective_disposition"] == "outcome_unknown"
    assert (
        restarted.claim_effect_boundary(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref="evidence:no-blind-resend",
            evidence_hash=_hash("5"),
        )
        is False
    )


def test_prevented_may_resolve_before_effect_begins_but_not_after(
    tmp_path: Path,
) -> None:
    first = ProtectedToolStore(tmp_path / "first")
    call, _ = first.reserve_call(_call())
    prevented = _effect(
        call,
        disposition="prevented",
        external_effect_ref=None,
        external_effect_hash=None,
        evidence_ref="evidence:mechanical-prevention",
        evidence_hash=_hash("8"),
    )
    first.record_effect(prevented)
    assert (
        first.get_observation(call.call_request_id)["effective_disposition"]
        == "prevented"
    )

    second = ProtectedToolStore(tmp_path / "second")
    call, _ = second.reserve_call(_call())
    second.claim_effect_boundary(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        evidence_ref="evidence:already-begun",
        evidence_hash=_hash("7"),
    )
    with pytest.raises(ProtectedToolStateError, match="cannot be recorded after"):
        second.record_effect(prevented)


def test_immutable_call_provenance_and_effect_rows_reject_direct_rewrite(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    call, _ = store.reserve_call(_call())
    store.claim_effect_boundary(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        evidence_ref="evidence:begin",
        evidence_hash=_hash("7"),
    )
    store.record_effect(_effect(call))
    with store.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE protected_tool_calls SET request_hash = ? WHERE call_request_id = ?",
                (_hash("1"), call.call_request_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE protected_tool_provider_provenance SET provider_hash = ? "
                "WHERE call_request_id = ?",
                (_hash("2"), call.call_request_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(
                "UPDATE protected_tool_effects SET effect_hash = ? WHERE call_request_id = ?",
                (_hash("3"), call.call_request_id),
            )
