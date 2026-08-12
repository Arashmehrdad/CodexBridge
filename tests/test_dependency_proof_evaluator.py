"""G3.3 exact dependency-proof evaluator and persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from soma.company_kernel.models import AcceptanceCommit
from soma.company_kernel.store import CompanyKernelStore
from soma.fanin.proofs import (
    DependencyEdgeContextV1,
    DependencyProofEvaluationError,
    EvidenceAvailableCandidateV1,
    PublishedSuccessCandidateV1,
    SettledAttemptFactV1,
    evaluate_accepted_outcome,
    evaluate_evidence_available,
    evaluate_published_success,
    evaluate_settled,
    persist_dependency_proof,
)


COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
UPSTREAM_PACKAGE_ID = "workpkg_" + "4" * 24
DOWNSTREAM_PACKAGE_ID = "workpkg_" + "5" * 24
UPSTREAM_OUTCOME_ID = "outcome_" + "6" * 24
DOWNSTREAM_OUTCOME_ID = "outcome_" + "7" * 24
ATTEMPT_ID = "wpattempt_" + "8" * 24
ACCEPTANCE_ID = "accept_" + "9" * 24
PROJECT_ID = "project_proof_fixture"
RESOURCE_ID = "resource_proof_fixture"
OWNER = "owner-controller:fixture"
NOW = "2026-08-12T05:00:00+00:00"


def _hash(character: str) -> str:
    return character * 64


def _context(requirement: str, *, version: int = 1) -> DependencyEdgeContextV1:
    kwargs = {}
    if requirement == "evidence_available":
        kwargs = {
            "evidence_selector_ref": "selector:required-output",
            "evidence_selector_hash": _hash("e"),
        }
    return DependencyEdgeContextV1(
        mission_id=MISSION_ID,
        plan_revision_id=PLAN_ID,
        edge_id=f"edge-{requirement}",
        edge_hash=_hash("a"),
        requirement=requirement,
        upstream_work_package_id=UPSTREAM_PACKAGE_ID,
        upstream_outcome_id=UPSTREAM_OUTCOME_ID,
        downstream_work_package_id=DOWNSTREAM_PACKAGE_ID,
        observed_kernel_state_version=version,
        **kwargs,
    )


def _acceptance(**overrides) -> AcceptanceCommit:
    values = {
        "acceptance_commit_id": ACCEPTANCE_ID,
        "company_id": COMPANY_ID,
        "mission_id": MISSION_ID,
        "work_package_id": UPSTREAM_PACKAGE_ID,
        "outcome_id": UPSTREAM_OUTCOME_ID,
        "attempt_id": ATTEMPT_ID,
        "task_id": "task_acceptance_fixture",
        "run_id": "run_acceptance_fixture",
        "result_published_hash": _hash("b"),
        "public_result_source_sha256": _hash("c"),
        "acceptance_authority_ref": OWNER,
        "acceptance_basis_ref": "owner accepted exact result",
        "acceptance_basis_hash": _hash("d"),
        "controller_request_id": "acceptance-request-fixture",
        "request_hash": _hash("f"),
        "accepted_at": NOW,
    }
    values.update(overrides)
    return AcceptanceCommit(**values)


def test_accepted_outcome_binds_exact_acceptance_record() -> None:
    proof = evaluate_accepted_outcome(
        _context("accepted_outcome"),
        _acceptance(),
        observed_at=NOW,
    )
    assert proof.requirement == "accepted_outcome"
    assert proof.satisfaction.kind == "accepted_outcome"
    assert proof.satisfaction.acceptance_commit_id == ACCEPTANCE_ID
    assert len(proof.satisfaction.acceptance_commit_hash) == 64

    with pytest.raises(DependencyProofEvaluationError, match="exact upstream"):
        evaluate_accepted_outcome(
            _context("accepted_outcome"),
            _acceptance(work_package_id=DOWNSTREAM_PACKAGE_ID),
        )


def test_published_success_requires_exact_run_backed_candidate_identity() -> None:
    candidate = PublishedSuccessCandidateV1(
        work_package_id=UPSTREAM_PACKAGE_ID,
        outcome_id=UPSTREAM_OUTCOME_ID,
        attempt_id=ATTEMPT_ID,
        task_id="task_durable_fixture",
        run_id="20260812T050000Z_fixture_abcdef12",
        result_published_hash=_hash("1"),
        public_result_source_sha256=_hash("2"),
    )
    proof = evaluate_published_success(
        _context("published_success"), candidate, observed_at=NOW
    )
    assert proof.satisfaction.kind == "published_success"
    assert proof.satisfaction.run_id == candidate.run_id

    with pytest.raises(ValueError):
        PublishedSuccessCandidateV1(
            work_package_id=UPSTREAM_PACKAGE_ID,
            outcome_id=UPSTREAM_OUTCOME_ID,
            attempt_id=ATTEMPT_ID,
            task_id="task_reasoning_fixture",
            run_id="",
            result_published_hash=_hash("1"),
            public_result_source_sha256=_hash("2"),
        )
    with pytest.raises(DependencyProofEvaluationError, match="exact upstream"):
        evaluate_published_success(
            _context("published_success"),
            candidate.model_copy(update={"work_package_id": DOWNSTREAM_PACKAGE_ID}),
        )


def test_evidence_available_requires_exact_selector_binding() -> None:
    candidate = EvidenceAvailableCandidateV1(
        selector_ref="selector:required-output",
        selector_hash=_hash("e"),
        evidence_ref="artifact:evidence",
        evidence_hash=_hash("3"),
    )
    proof = evaluate_evidence_available(
        _context("evidence_available"), candidate, observed_at=NOW
    )
    assert proof.satisfaction.evidence_ref == "artifact:evidence"
    assert proof.satisfaction.evidence_selector_hash == _hash("e")

    with pytest.raises(
        DependencyProofEvaluationError, match="exact dependency selector"
    ):
        evaluate_evidence_available(
            _context("evidence_available"),
            candidate.model_copy(update={"selector_hash": _hash("4")}),
        )


def test_proof_identity_excludes_observation_time_and_kernel_version() -> None:
    candidate = EvidenceAvailableCandidateV1(
        selector_ref="selector:required-output",
        selector_hash=_hash("e"),
        evidence_ref="artifact:evidence",
        evidence_hash=_hash("3"),
    )
    first = evaluate_evidence_available(
        _context("evidence_available", version=1),
        candidate,
        observed_at="2026-08-12T05:00:00+00:00",
    )
    later = evaluate_evidence_available(
        _context("evidence_available", version=99),
        candidate,
        observed_at="2026-08-12T06:00:00+00:00",
    )
    assert first.proof_hash == later.proof_hash
    assert first.observed_at != later.observed_at
    assert first.observed_kernel_state_version != later.observed_kernel_state_version


def test_settled_hashes_exact_known_attempt_set_and_is_order_independent() -> None:
    first = SettledAttemptFactV1(
        attempt_id="wpattempt_" + "a" * 24,
        task_id="task_a",
        task_state="failed",
    )
    second = SettledAttemptFactV1(
        attempt_id="wpattempt_" + "b" * 24,
        task_id="task_b",
        supersedes_attempt_id=first.attempt_id,
        task_state="completed",
    )
    forward = evaluate_settled(_context("settled"), [first, second], observed_at=NOW)
    reversed_input = evaluate_settled(
        _context("settled"), [second, first], observed_at=NOW
    )
    assert forward.proof_hash == reversed_input.proof_hash
    assert (
        forward.satisfaction.attempt_set_hash
        == reversed_input.satisfaction.attempt_set_hash
    )
    assert forward.satisfaction.head_attempt_id == second.attempt_id
    assert forward.satisfaction.settlement_class == "terminal"

    third = SettledAttemptFactV1(
        attempt_id="wpattempt_" + "c" * 24,
        task_id="task_c",
        supersedes_attempt_id=second.attempt_id,
        task_state="completed",
    )
    changed = evaluate_settled(_context("settled"), [first, second, third])
    assert (
        changed.satisfaction.attempt_set_hash != forward.satisfaction.attempt_set_hash
    )
    assert changed.proof_hash != forward.proof_hash


def test_settled_requires_terminal_or_explicit_containment() -> None:
    running = SettledAttemptFactV1(
        attempt_id=ATTEMPT_ID,
        task_id="task_running",
        task_state="running",
    )
    with pytest.raises(DependencyProofEvaluationError, match="not terminal"):
        evaluate_settled(_context("settled"), [running])

    contained = running.model_copy(
        update={
            "containment_evidence_ref": "containment:fixture",
            "containment_evidence_hash": _hash("5"),
        }
    )
    proof = evaluate_settled(_context("settled"), [contained])
    assert proof.satisfaction.settlement_class == "contained"

    uncertain = contained.model_copy(update={"task_state": "uncertain"})
    proof = evaluate_settled(_context("settled"), [uncertain])
    assert proof.satisfaction.settlement_class == "uncertain_contained"


def _store_with_edge(tmp_path: Path) -> CompanyKernelStore:
    store = CompanyKernelStore(tmp_path / "runs")
    assert store.init_db() == [1, 2, 3]
    conn = store.connect()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO companies(company_id, company_key, display_name, executive_authority_ref, creation_request_id, creation_request_hash, created_at) VALUES (?, 'proof-company', 'Proof Company', ?, 'company-request', ?, ?)",
            (COMPANY_ID, OWNER, _hash("1"), NOW),
        )
        conn.execute(
            """
            INSERT INTO missions(
                mission_id, company_id, mission_key, project_id, resource_id,
                scope_generation, mission_contract_json, mission_contract_hash,
                accountable_owner_ref, acceptance_authority_ref,
                current_plan_revision_id, plan_state_version, kernel_state_version,
                creation_request_id, creation_request_hash, created_at, updated_at
            ) VALUES (?, ?, 'proof-mission', ?, ?, 1, '{}', ?, ?, ?, ?, 1, 1, 'mission-request', ?, ?, ?)
            """,
            (
                MISSION_ID,
                COMPANY_ID,
                PROJECT_ID,
                RESOURCE_ID,
                _hash("2"),
                OWNER,
                OWNER,
                PLAN_ID,
                _hash("3"),
                NOW,
                NOW,
            ),
        )
        conn.execute(
            """
            INSERT INTO plan_revisions(
                plan_revision_id, mission_id, revision_number, parent_plan_revision_id,
                plan_contract_json, plan_content_hash, deliberation_ref,
                deliberation_hash, accepted_by_ref, acceptance_basis_ref,
                controller_request_id, request_hash, accepted_at
            ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'proof-plan', 'plan-request', ?, ?)
            """,
            (PLAN_ID, MISSION_ID, _hash("4"), OWNER, _hash("5"), NOW),
        )
        for package_id, package_key, outcome_id in (
            (UPSTREAM_PACKAGE_ID, "upstream", UPSTREAM_OUTCOME_ID),
            (DOWNSTREAM_PACKAGE_ID, "downstream", DOWNSTREAM_OUTCOME_ID),
        ):
            conn.execute(
                """
                INSERT INTO work_packages(
                    work_package_id, mission_id, plan_revision_id, package_key,
                    outcome_id, project_id, target_resource_id, scope_generation,
                    contract_version, contract_json, contract_hash, topology,
                    accountable_owner_ref, acceptance_authority_ref,
                    deliberation_ref, evidence_requirements_ref,
                    evidence_requirements_hash, controller_request_id,
                    request_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'v1', '{}', ?, 'single_active', ?, ?, '', '', '', ?, ?, ?)
                """,
                (
                    package_id,
                    MISSION_ID,
                    PLAN_ID,
                    package_key,
                    outcome_id,
                    PROJECT_ID,
                    RESOURCE_ID,
                    _hash("6"),
                    OWNER,
                    OWNER,
                    f"package:{package_key}",
                    _hash("7"),
                    NOW,
                ),
            )
        conn.execute(
            "INSERT INTO plan_graph_manifests(plan_revision_id, mission_id, schema_version, manifest_json, manifest_hash, package_count, edge_count, created_at) VALUES (?, ?, 'plan_graph_manifest.v1', '{}', ?, 2, 1, ?)",
            (PLAN_ID, MISSION_ID, _hash("8"), NOW),
        )
        conn.execute(
            """
            INSERT INTO work_package_dependencies(
                edge_id, mission_id, plan_revision_id, upstream_work_package_id,
                downstream_work_package_id, requirement, evidence_selector_ref,
                evidence_selector_hash, edge_hash, created_at
            ) VALUES ('edge-accepted_outcome', ?, ?, ?, ?, 'accepted_outcome', '', '', ?, ?)
            """,
            (
                MISSION_ID,
                PLAN_ID,
                UPSTREAM_PACKAGE_ID,
                DOWNSTREAM_PACKAGE_ID,
                _hash("a"),
                NOW,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return store


def test_persistence_is_idempotent_and_replay_returns_durable_audit_metadata(
    tmp_path: Path,
) -> None:
    store = _store_with_edge(tmp_path)
    context = _context("accepted_outcome", version=1)
    first_proof = evaluate_accepted_outcome(context, _acceptance(), observed_at=NOW)
    first = persist_dependency_proof(
        store, context=context, proof=first_proof, created_at=NOW
    )
    assert first.created is True

    later_proof = evaluate_accepted_outcome(
        context.model_copy(update={"observed_kernel_state_version": 99}),
        _acceptance(),
        observed_at="2026-08-12T07:00:00+00:00",
    )
    assert later_proof.proof_hash == first_proof.proof_hash
    replay = persist_dependency_proof(store, context=context, proof=later_proof)
    assert replay.created is False
    assert replay.proof.observed_at == NOW
    assert replay.proof.observed_kernel_state_version == 1
    assert replay.proof.proof_hash == first.proof.proof_hash

    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM dependency_satisfaction_proofs"
            ).fetchone()[0]
            == 1
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
