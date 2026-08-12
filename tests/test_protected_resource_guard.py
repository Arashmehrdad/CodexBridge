"""G4.4 durable protected-resource serialization and containment proofs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from soma.protected_tools.models import ProtectedToolCallV1, ProtectedToolEffectV1
from soma.protected_tools.resource_guard import (
    DurableProtectedResourceGuard,
    ProtectedResourceContainmentError,
)
from soma.protected_tools.schema import (
    PROTECTED_TOOL_MIGRATIONS,
    PROTECTED_TOOL_SCHEMA_COMPONENT,
    apply_protected_tool_migrations,
)
from soma.protected_tools.store import ProtectedToolStateError, ProtectedToolStore


NOW = datetime(2026, 8, 12, 11, 45, tzinfo=timezone.utc)


def _hash(character: str) -> str:
    return character * 64


def _call(index: int, *, resource_key: str = "resource:shared") -> ProtectedToolCallV1:
    return ProtectedToolCallV1(
        call_request_id=f"protected-resource-call-{index}",
        task_id=f"task-protected-resource-{index}",
        attempt_id="wpattempt_" + f"{index:024x}",
        backend_ref=f"reasoning-backend:resource-{index}",
        mandate_ref="mandate:resource-guard",
        mandate_hash=_hash("a"),
        mandate_version="v1",
        project_id="Project_Protected_Resource",
        resource_id="Resource_Protected_Resource",
        scope_generation=1,
        capability_ref="capability:protected-write",
        capability_hash=_hash("b"),
        tool_operation_ref="tool-operation:fake-write",
        tool_operation_hash=_hash("c"),
        resource_key=resource_key,
        idempotency_key=f"soma-slot:resource-guard-{index}",
        payload_ref=f"payload:resource-guard-{index}",
        payload_hash=_hash("d"),
        expected_task_state_version=1,
        expires_at=NOW + timedelta(hours=1),
        mutation_class="generic",
    )


def _effect(
    call: ProtectedToolCallV1,
    *,
    disposition: str = "acknowledged",
    evidence_character: str = "e",
) -> ProtectedToolEffectV1:
    kwargs = {}
    if disposition == "acknowledged":
        kwargs = {
            "external_effect_ref": f"fake-effect:{call.call_request_id}",
            "external_effect_hash": _hash("f"),
        }
    return ProtectedToolEffectV1(
        call_request_id=call.call_request_id,
        request_hash=call.request_hash,
        disposition=disposition,
        evidence_ref=f"evidence:{disposition}:{call.call_request_id}",
        evidence_hash=_hash(evidence_character),
        completed_at=NOW + timedelta(minutes=1),
        **kwargs,
    )


def _reserve(store: ProtectedToolStore, *calls: ProtectedToolCallV1) -> None:
    for call in calls:
        store.reserve_call(call, now=NOW.isoformat())


def _record_after_boundary(
    store: ProtectedToolStore,
    lease,
    call: ProtectedToolCallV1,
    effect: ProtectedToolEffectV1,
) -> None:
    assert (
        store.claim_effect_boundary(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref=lease.evidence_ref,
            evidence_hash=lease.evidence_hash,
            now=NOW.isoformat(),
        )
        is True
    )
    store.record_effect(effect, now=(NOW + timedelta(minutes=1)).isoformat())


def test_v1_to_v2_upgrade_is_additive_and_preserves_incumbent_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runs" / "soma.sqlite3"
    db_path.parent.mkdir(parents=True)

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    assert apply_protected_tool_migrations(
        connect, migrations=(PROTECTED_TOOL_MIGRATIONS[0],)
    ) == [1]
    call = _call(1)
    with connect() as conn:
        conn.execute(
            "INSERT INTO protected_tool_calls(call_request_id, idempotency_key, request_hash, call_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                call.call_request_id,
                call.idempotency_key,
                call.request_hash,
                call.model_copy(
                    update={"provider_provenance_refs": ()}
                ).model_dump_json(),
                NOW.isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO protected_tool_delivery(call_request_id, delivery_state, updated_at) "
            "VALUES (?, 'reserved', ?)",
            (call.call_request_id, NOW.isoformat()),
        )
    assert apply_protected_tool_migrations(connect) == [2]
    with connect() as conn:
        row = conn.execute(
            "SELECT request_hash FROM protected_tool_calls WHERE call_request_id = ?",
            (call.call_request_id,),
        ).fetchone()
        lease_count = conn.execute(
            "SELECT COUNT(*) FROM protected_resource_leases"
        ).fetchone()[0]
        versions = [
            int(row[0])
            for row in conn.execute(
                "SELECT version FROM soma_schema_migrations WHERE component = ? ORDER BY version",
                (PROTECTED_TOOL_SCHEMA_COMPONENT,),
            ).fetchall()
        ]
    assert str(row["request_hash"]) == call.request_hash
    assert lease_count == 0
    assert versions == [1, 2]


def test_same_resource_serializes_and_independent_resources_coexist(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    guard = DurableProtectedResourceGuard(store)
    first = _call(1, resource_key="resource:A")
    same = _call(2, resource_key="resource:A")
    independent = _call(3, resource_key="resource:B")
    _reserve(store, first, same, independent)

    lease_a = guard.acquire(first)
    blocked = guard.acquire(same)
    lease_b = guard.acquire(independent)

    assert lease_a.acquired is True
    assert lease_b.acquired is True
    assert blocked.acquired is False
    assert "another protected writer" in blocked.reason
    assert lease_a.resource_key == "resource:A"
    assert lease_b.resource_key == "resource:B"
    with store.connect() as conn:
        active = conn.execute(
            "SELECT resource_key, state FROM protected_resource_leases "
            "WHERE state IN ('held', 'uncertain') ORDER BY resource_key"
        ).fetchall()
    assert [(str(row[0]), str(row[1])) for row in active] == [
        ("resource:A", "held"),
        ("resource:B", "held"),
    ]


def test_same_call_replays_exact_held_lease_after_restart(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    store = ProtectedToolStore(runs)
    call = _call(1)
    _reserve(store, call)
    first = DurableProtectedResourceGuard(store).acquire(call)

    restarted = DurableProtectedResourceGuard(ProtectedToolStore(runs))
    second = restarted.acquire(call)
    assert second.acquired is True
    assert second.lease_ref == first.lease_ref
    assert second.evidence_hash == first.evidence_hash
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM protected_resource_leases WHERE call_request_id = ?",
                (call.call_request_id,),
            ).fetchone()[0]
            == 1
        )


def test_acknowledged_or_rejected_effect_releases_resource_for_next_writer(
    tmp_path: Path,
) -> None:
    for disposition in ("acknowledged", "rejected"):
        store = ProtectedToolStore(tmp_path / disposition)
        guard = DurableProtectedResourceGuard(store)
        first = _call(1)
        second = _call(2)
        _reserve(store, first, second)
        lease = guard.acquire(first)
        effect = _effect(first, disposition=disposition)
        _record_after_boundary(store, lease, first, effect)
        guard.reconcile(first, effect)

        assert guard.get_lease(first.call_request_id)["state"] == "released"
        next_lease = guard.acquire(second)
        assert next_lease.acquired is True


def test_reconcile_requires_exact_durable_effect_evidence(tmp_path: Path) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    guard = DurableProtectedResourceGuard(store)
    call = _call(1)
    _reserve(store, call)
    guard.acquire(call)
    with pytest.raises(ProtectedToolStateError, match="durable protected effect"):
        guard.reconcile(call, _effect(call))


def test_outcome_unknown_retains_uncertain_lease_across_restart_and_blocks_writer(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    store = ProtectedToolStore(runs)
    guard = DurableProtectedResourceGuard(store)
    first = _call(1)
    second = _call(2)
    _reserve(store, first, second)
    lease = guard.acquire(first)
    unknown = _effect(first, disposition="outcome_unknown")
    _record_after_boundary(store, lease, first, unknown)
    guard.reconcile(first, unknown)
    assert guard.get_lease(first.call_request_id)["state"] == "uncertain"

    restarted = DurableProtectedResourceGuard(ProtectedToolStore(runs))
    blocked = restarted.acquire(second)
    assert blocked.acquired is False
    assert "unresolved effect" in blocked.reason
    own = restarted.acquire(first)
    assert own.acquired is False
    assert "unresolved protected-effect uncertainty" in own.reason


def test_uncertain_lease_requires_exact_mechanical_containment_before_new_writer(
    tmp_path: Path,
) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    guard = DurableProtectedResourceGuard(store)
    first = _call(1)
    second = _call(2)
    _reserve(store, first, second)
    lease = guard.acquire(first)
    unknown = _effect(first, disposition="outcome_unknown")
    _record_after_boundary(store, lease, first, unknown)
    guard.reconcile(first, unknown)

    with pytest.raises(ProtectedResourceContainmentError, match="request_hash"):
        guard.contain_uncertainty(
            call_request_id=first.call_request_id,
            request_hash=_hash("1"),
            evidence_ref="containment:wrong",
            evidence_hash=_hash("2"),
        )
    assert guard.acquire(second).acquired is False

    contained = guard.contain_uncertainty(
        call_request_id=first.call_request_id,
        request_hash=first.request_hash,
        evidence_ref="containment:operator-confirmed-no-effect",
        evidence_hash=_hash("3"),
    )
    assert contained["state"] == "contained"
    assert len(contained["containment_hash"]) == 64
    assert guard.get_lease(first.call_request_id)["state"] == "contained"
    assert guard.acquire(second).acquired is True


def test_containment_is_only_for_durable_outcome_unknown(tmp_path: Path) -> None:
    store = ProtectedToolStore(tmp_path / "runs")
    guard = DurableProtectedResourceGuard(store)
    call = _call(1)
    _reserve(store, call)
    guard.acquire(call)
    with pytest.raises(ProtectedResourceContainmentError, match="only uncertain"):
        guard.contain_uncertainty(
            call_request_id=call.call_request_id,
            request_hash=call.request_hash,
            evidence_ref="containment:not-unknown",
            evidence_hash=_hash("4"),
        )


def test_many_provider_provenance_refs_still_create_one_resource_lease(
    tmp_path: Path,
) -> None:
    from soma.protected_tools.models import ProtectedProviderProvenanceRefV1

    store = ProtectedToolStore(tmp_path / "runs")
    guard = DurableProtectedResourceGuard(store)
    baseline = _call(1)
    store.reserve_call(baseline)
    replay = baseline.model_copy(
        update={
            "call_request_id": "provider-child-replay-record",
            "provider_provenance_refs": tuple(
                ProtectedProviderProvenanceRefV1(
                    ref=f"provider-child:{index}",
                    hash=f"{index + 1:x}" * 64 if index < 15 else _hash("f"),
                )
                for index in range(16)
            ),
        }
    )
    # Normalize test hashes to valid 64-char values while keeping all provider refs distinct.
    replay = replay.model_copy(
        update={
            "provider_provenance_refs": tuple(
                ProtectedProviderProvenanceRefV1(
                    ref=f"provider-child:{index}",
                    hash=(f"{index:064x}"[-64:]),
                )
                for index in range(1, 17)
            )
        }
    )
    canonical, created = store.reserve_call(replay)
    assert created is False
    assert canonical.request_hash == baseline.request_hash
    assert guard.acquire(canonical).acquired is True
    with store.connect() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM protected_resource_leases").fetchone()[0]
            == 1
        )
