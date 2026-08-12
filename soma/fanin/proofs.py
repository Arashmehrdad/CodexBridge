def persist_dependency_proof_in_connection(
    conn,
    *,
    context: DependencyEdgeContextV1,
    proof: DependencySatisfactionProofV1,
    created_at: str | None = None,
) -> PersistedDependencyProofV1:
    """Persist one proof inside an already-open Company Kernel transaction."""

    if (
        proof.edge_id != context.edge_id
        or proof.edge_hash != context.edge_hash
        or proof.requirement != context.requirement
        or proof.upstream_work_package_id != context.upstream_work_package_id
        or proof.upstream_outcome_id != context.upstream_outcome_id
        or proof.downstream_work_package_id != context.downstream_work_package_id
    ):
        raise DependencyProofPersistenceError(
            "proof envelope does not match exact dependency edge context"
        )
    proof_id = proof_id_for(proof.proof_hash)
    satisfaction_json = canonical_json(proof.satisfaction.model_dump(mode="json"))
    edge = conn.execute(
        "SELECT * FROM work_package_dependencies "
        "WHERE edge_id = ? AND mission_id = ? AND plan_revision_id = ?",
        (context.edge_id, context.mission_id, context.plan_revision_id),
    ).fetchone()
    if edge is None:
        raise DependencyProofPersistenceError("dependency edge does not exist")
    durable = (
        str(edge["edge_hash"]),
        str(edge["requirement"]),
        str(edge["upstream_work_package_id"]),
        str(edge["downstream_work_package_id"]),
        str(edge["evidence_selector_ref"] or "") or None,
        str(edge["evidence_selector_hash"] or "") or None,
    )
    submitted = (
        context.edge_hash,
        context.requirement,
        context.upstream_work_package_id,
        context.downstream_work_package_id,
        context.evidence_selector_ref,
        context.evidence_selector_hash,
    )
    if durable != submitted:
        raise DependencyProofPersistenceError(
            "dependency edge durable identity differs from proof context"
        )
    existing = conn.execute(
        "SELECT * FROM dependency_satisfaction_proofs WHERE proof_id = ?",
        (proof_id,),
    ).fetchone()
    if existing is not None:
        if (
            str(existing["proof_hash"]) != proof.proof_hash
            or str(existing["satisfaction_json"]) != satisfaction_json
        ):
            raise DependencyProofPersistenceError(
                "proof identity already exists with different immutable material"
            )
        return PersistedDependencyProofV1(
            proof_id=proof_id,
            created=False,
            proof=_proof_from_row(existing),
        )
    conn.execute(
        "INSERT INTO dependency_satisfaction_proofs("
        "proof_id, proof_hash, mission_id, plan_revision_id, edge_id, edge_hash, "
        "requirement, upstream_work_package_id, upstream_outcome_id, "
        "downstream_work_package_id, satisfaction_json, observed_kernel_state_version, "
        "observed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            proof_id,
            proof.proof_hash,
            context.mission_id,
            context.plan_revision_id,
            context.edge_id,
            context.edge_hash,
            context.requirement,
            context.upstream_work_package_id,
            context.upstream_outcome_id,
            context.downstream_work_package_id,
            satisfaction_json,
            proof.observed_kernel_state_version,
            proof.observed_at,
            created_at or _utc_now(),
        ),
    )
    return PersistedDependencyProofV1(proof_id=proof_id, created=True, proof=proof)
