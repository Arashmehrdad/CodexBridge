"""Ordered additive Company Kernel migrations.

The component lives in the existing ``runs/soma.sqlite3`` database beside
ProjectScope, canonical Tasks, durable Runs and subordinate reasoning evidence.
It creates only company-domain facts and immutable relationship constraints.
Migrations preserve exact incumbent facts; v4 deterministically translates the
historical durable-Run-only acceptance binding into the provider-neutral Task
backend binding accepted by the Agent/Worker architecture.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final

from .models import COMPANY_KERNEL_SCHEMA_COMPONENT, COMPANY_KERNEL_SCHEMA_VERSION


MIGRATION_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS soma_schema_migrations (
    component TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY (component, version)
)
"""

_MIGRATION_0001: Final[tuple[str, ...]] = (
    """
    CREATE TABLE companies (
        company_id TEXT PRIMARY KEY,
        company_key TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        executive_authority_ref TEXT NOT NULL,
        creation_request_id TEXT NOT NULL UNIQUE,
        creation_request_hash TEXT NOT NULL CHECK(length(creation_request_hash) = 64),
        created_at TEXT NOT NULL,
        UNIQUE(company_id, executive_authority_ref)
    )
    """,
    """
    CREATE TABLE missions (
        mission_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        mission_key TEXT NOT NULL,
        project_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
        mission_contract_json TEXT NOT NULL,
        mission_contract_hash TEXT NOT NULL CHECK(length(mission_contract_hash) = 64),
        accountable_owner_ref TEXT NOT NULL,
        acceptance_authority_ref TEXT NOT NULL,
        current_plan_revision_id TEXT,
        plan_state_version INTEGER NOT NULL DEFAULT 0,
        kernel_state_version INTEGER NOT NULL DEFAULT 0,
        creation_request_id TEXT NOT NULL UNIQUE,
        creation_request_hash TEXT NOT NULL CHECK(length(creation_request_hash) = 64),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(company_id, mission_key),
        UNIQUE(mission_id, company_id),
        UNIQUE(mission_id, project_id, resource_id, scope_generation),
        UNIQUE(mission_id, acceptance_authority_ref),
        UNIQUE(mission_id, accountable_owner_ref, acceptance_authority_ref),
        FOREIGN KEY(company_id) REFERENCES companies(company_id),
        FOREIGN KEY(company_id, accountable_owner_ref)
            REFERENCES companies(company_id, executive_authority_ref),
        FOREIGN KEY(company_id, acceptance_authority_ref)
            REFERENCES companies(company_id, executive_authority_ref),
        FOREIGN KEY(project_id, resource_id)
            REFERENCES project_resource_bindings(project_id, resource_id),
        FOREIGN KEY(mission_id, current_plan_revision_id)
            REFERENCES plan_revisions(mission_id, plan_revision_id)
            DEFERRABLE INITIALLY DEFERRED
    )
    """,
    """
    CREATE TABLE plan_revisions (
        plan_revision_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        revision_number INTEGER NOT NULL CHECK(revision_number >= 1),
        parent_plan_revision_id TEXT,
        plan_contract_json TEXT NOT NULL,
        plan_content_hash TEXT NOT NULL CHECK(length(plan_content_hash) = 64),
        deliberation_ref TEXT NOT NULL DEFAULT '',
        deliberation_hash TEXT NOT NULL DEFAULT '',
        accepted_by_ref TEXT NOT NULL,
        acceptance_basis_ref TEXT NOT NULL DEFAULT '',
        controller_request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        accepted_at TEXT NOT NULL,
        UNIQUE(mission_id, plan_revision_id),
        UNIQUE(mission_id, revision_number),
        UNIQUE(mission_id, plan_content_hash),
        UNIQUE(mission_id, controller_request_id),
        FOREIGN KEY(mission_id) REFERENCES missions(mission_id),
        FOREIGN KEY(mission_id, accepted_by_ref)
            REFERENCES missions(mission_id, acceptance_authority_ref),
        FOREIGN KEY(mission_id, parent_plan_revision_id)
            REFERENCES plan_revisions(mission_id, plan_revision_id)
    )
    """,
    """
    CREATE TABLE work_packages (
        work_package_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        plan_revision_id TEXT NOT NULL,
        package_key TEXT NOT NULL,
        outcome_id TEXT NOT NULL UNIQUE,
        project_id TEXT NOT NULL,
        target_resource_id TEXT NOT NULL,
        scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
        contract_version TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL CHECK(length(contract_hash) = 64),
        topology TEXT NOT NULL DEFAULT 'single_active'
            CHECK(topology IN ('single_active')),
        accountable_owner_ref TEXT NOT NULL,
        acceptance_authority_ref TEXT NOT NULL,
        deliberation_ref TEXT NOT NULL DEFAULT '',
        evidence_requirements_ref TEXT NOT NULL DEFAULT '',
        controller_request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        created_at TEXT NOT NULL,
        UNIQUE(work_package_id, outcome_id),
        UNIQUE(work_package_id, mission_id, outcome_id),
        UNIQUE(work_package_id, mission_id, outcome_id, acceptance_authority_ref),
        UNIQUE(mission_id, plan_revision_id, package_key),
        UNIQUE(mission_id, controller_request_id),
        FOREIGN KEY(mission_id) REFERENCES missions(mission_id),
        FOREIGN KEY(mission_id, accountable_owner_ref, acceptance_authority_ref)
            REFERENCES missions(
                mission_id, accountable_owner_ref, acceptance_authority_ref
            ),
        FOREIGN KEY(mission_id, plan_revision_id)
            REFERENCES plan_revisions(mission_id, plan_revision_id),
        FOREIGN KEY(mission_id, project_id, target_resource_id, scope_generation)
            REFERENCES missions(mission_id, project_id, resource_id, scope_generation),
        FOREIGN KEY(project_id, target_resource_id)
            REFERENCES project_resource_bindings(project_id, resource_id)
    )
    """,
    """
    CREATE TABLE work_package_attempts (
        attempt_id TEXT PRIMARY KEY,
        work_package_id TEXT NOT NULL,
        outcome_id TEXT NOT NULL,
        task_id TEXT NOT NULL UNIQUE,
        route_request_hash TEXT NOT NULL CHECK(length(route_request_hash) = 64),
        route_descriptor_json TEXT NOT NULL,
        supersedes_attempt_id TEXT,
        containment_evidence_ref TEXT NOT NULL DEFAULT '',
        containment_evidence_hash TEXT NOT NULL DEFAULT '',
        controller_request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        created_at TEXT NOT NULL,
        UNIQUE(attempt_id, work_package_id, outcome_id),
        UNIQUE(attempt_id, work_package_id, outcome_id, task_id),
        UNIQUE(outcome_id, controller_request_id),
        FOREIGN KEY(work_package_id, outcome_id)
            REFERENCES work_packages(work_package_id, outcome_id),
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
        FOREIGN KEY(supersedes_attempt_id, work_package_id, outcome_id)
            REFERENCES work_package_attempts(attempt_id, work_package_id, outcome_id)
    )
    """,
    """
    CREATE UNIQUE INDEX idx_work_package_attempt_single_successor
    ON work_package_attempts(supersedes_attempt_id)
    WHERE supersedes_attempt_id IS NOT NULL
    """,
    """
    CREATE TABLE acceptance_commits (
        acceptance_commit_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        mission_id TEXT NOT NULL,
        work_package_id TEXT NOT NULL,
        outcome_id TEXT NOT NULL UNIQUE,
        attempt_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        result_published_hash TEXT NOT NULL
            CHECK(length(result_published_hash) = 64),
        public_result_source_sha256 TEXT NOT NULL
            CHECK(length(public_result_source_sha256) = 64),
        acceptance_authority_ref TEXT NOT NULL,
        acceptance_basis_ref TEXT NOT NULL,
        acceptance_basis_hash TEXT NOT NULL DEFAULT '',
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        accepted_at TEXT NOT NULL,
        FOREIGN KEY(mission_id, company_id)
            REFERENCES missions(mission_id, company_id),
        FOREIGN KEY(
            work_package_id, mission_id, outcome_id, acceptance_authority_ref
        ) REFERENCES work_packages(
            work_package_id, mission_id, outcome_id, acceptance_authority_ref
        ),
        FOREIGN KEY(attempt_id, work_package_id, outcome_id, task_id)
            REFERENCES work_package_attempts(
                attempt_id, work_package_id, outcome_id, task_id
            ),
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    )
    """,
    """
    CREATE TABLE kernel_reconciliation_receipts (
        reconciliation_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        trigger_kind TEXT NOT NULL
            CHECK(trigger_kind IN ('owner_turn', 'package_completion')),
        trigger_ref TEXT NOT NULL,
        observed_kernel_state_version INTEGER NOT NULL,
        selected_transition TEXT NOT NULL CHECK(selected_transition IN (
            'no_op',
            'plan_selected',
            'package_defined',
            'attempt_reserved',
            'acceptance_candidate_ready',
            'outcome_accepted'
        )),
        target_ref TEXT NOT NULL DEFAULT '',
        effect_hash TEXT NOT NULL CHECK(length(effect_hash) = 64),
        created_at TEXT NOT NULL,
        UNIQUE(mission_id, trigger_kind, trigger_ref),
        FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    )
    """,
    """
    CREATE TRIGGER companies_no_update
    BEFORE UPDATE ON companies
    BEGIN SELECT RAISE(ABORT, 'companies are immutable'); END
    """,
    """
    CREATE TRIGGER companies_no_delete
    BEFORE DELETE ON companies
    BEGIN SELECT RAISE(ABORT, 'companies are immutable'); END
    """,
    """
    CREATE TRIGGER plan_revisions_no_update
    BEFORE UPDATE ON plan_revisions
    BEGIN SELECT RAISE(ABORT, 'plan revisions are immutable'); END
    """,
    """
    CREATE TRIGGER plan_revisions_no_delete
    BEFORE DELETE ON plan_revisions
    BEGIN SELECT RAISE(ABORT, 'plan revisions are immutable'); END
    """,
    """
    CREATE TRIGGER work_packages_no_update
    BEFORE UPDATE ON work_packages
    BEGIN SELECT RAISE(ABORT, 'work packages are immutable'); END
    """,
    """
    CREATE TRIGGER work_packages_no_delete
    BEFORE DELETE ON work_packages
    BEGIN SELECT RAISE(ABORT, 'work packages are immutable'); END
    """,
    """
    CREATE TRIGGER work_package_attempts_no_update
    BEFORE UPDATE ON work_package_attempts
    BEGIN SELECT RAISE(ABORT, 'work package attempts are immutable'); END
    """,
    """
    CREATE TRIGGER work_package_attempts_no_delete
    BEFORE DELETE ON work_package_attempts
    BEGIN SELECT RAISE(ABORT, 'work package attempts are immutable'); END
    """,
    """
    CREATE TRIGGER acceptance_commits_no_update
    BEFORE UPDATE ON acceptance_commits
    BEGIN SELECT RAISE(ABORT, 'acceptance commits are immutable'); END
    """,
    """
    CREATE TRIGGER acceptance_commits_no_delete
    BEFORE DELETE ON acceptance_commits
    BEGIN SELECT RAISE(ABORT, 'acceptance commits are immutable'); END
    """,
    """
    CREATE TRIGGER kernel_reconciliation_receipts_no_update
    BEFORE UPDATE ON kernel_reconciliation_receipts
    BEGIN SELECT RAISE(ABORT, 'reconciliation receipts are immutable'); END
    """,
    """
    CREATE TRIGGER kernel_reconciliation_receipts_no_delete
    BEFORE DELETE ON kernel_reconciliation_receipts
    BEGIN SELECT RAISE(ABORT, 'reconciliation receipts are immutable'); END
    """,
    """
    CREATE TRIGGER missions_immutable_identity
    BEFORE UPDATE OF
        company_id, mission_key, project_id, resource_id, scope_generation,
        mission_contract_json, mission_contract_hash,
        accountable_owner_ref, acceptance_authority_ref,
        creation_request_id, creation_request_hash, created_at
    ON missions
    BEGIN SELECT RAISE(ABORT, 'mission identity and contract are immutable'); END
    """,
    """
    CREATE TRIGGER missions_no_delete
    BEFORE DELETE ON missions
    BEGIN SELECT RAISE(ABORT, 'missions are immutable'); END
    """,
)

_MIGRATION_0002: Final[tuple[str, ...]] = (
    """
    CREATE UNIQUE INDEX idx_work_package_plan_membership
    ON work_packages(work_package_id, mission_id, plan_revision_id)
    """,
    """
    ALTER TABLE work_packages
    ADD COLUMN evidence_requirements_hash TEXT NOT NULL DEFAULT ''
        CHECK(length(evidence_requirements_hash) IN (0, 64))
    """,
    """
    CREATE TABLE plan_graph_manifests (
        plan_revision_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        manifest_json TEXT NOT NULL,
        manifest_hash TEXT NOT NULL CHECK(length(manifest_hash) = 64),
        package_count INTEGER NOT NULL CHECK(package_count BETWEEN 1 AND 32),
        edge_count INTEGER NOT NULL CHECK(edge_count BETWEEN 0 AND 128),
        created_at TEXT NOT NULL,
        UNIQUE(mission_id, manifest_hash),
        FOREIGN KEY(mission_id, plan_revision_id)
            REFERENCES plan_revisions(mission_id, plan_revision_id)
    )
    """,
    """
    CREATE TABLE work_package_dependencies (
        edge_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL,
        plan_revision_id TEXT NOT NULL,
        upstream_work_package_id TEXT NOT NULL,
        downstream_work_package_id TEXT NOT NULL,
        requirement TEXT NOT NULL CHECK(requirement IN (
            'accepted_outcome',
            'published_success',
            'evidence_available',
            'settled'
        )),
        evidence_selector_ref TEXT NOT NULL DEFAULT '',
        evidence_selector_hash TEXT NOT NULL DEFAULT '',
        edge_hash TEXT NOT NULL CHECK(length(edge_hash) = 64),
        created_at TEXT NOT NULL,
        CHECK(upstream_work_package_id <> downstream_work_package_id),
        CHECK(
            (requirement = 'evidence_available'
                AND evidence_selector_ref <> ''
                AND length(evidence_selector_hash) = 64)
            OR
            (requirement <> 'evidence_available'
                AND evidence_selector_ref = ''
                AND evidence_selector_hash = '')
        ),
        UNIQUE(plan_revision_id, edge_hash),
        FOREIGN KEY(mission_id, plan_revision_id)
            REFERENCES plan_revisions(mission_id, plan_revision_id),
        FOREIGN KEY(upstream_work_package_id, mission_id, plan_revision_id)
            REFERENCES work_packages(work_package_id, mission_id, plan_revision_id),
        FOREIGN KEY(downstream_work_package_id, mission_id, plan_revision_id)
            REFERENCES work_packages(work_package_id, mission_id, plan_revision_id)
    )
    """,
    """
    CREATE TRIGGER plan_graph_manifests_no_update
    BEFORE UPDATE ON plan_graph_manifests
    BEGIN SELECT RAISE(ABORT, 'plan graph manifests are immutable'); END
    """,
    """
    CREATE TRIGGER plan_graph_manifests_no_delete
    BEFORE DELETE ON plan_graph_manifests
    BEGIN SELECT RAISE(ABORT, 'plan graph manifests are immutable'); END
    """,
    """
    CREATE TRIGGER work_package_dependencies_no_update
    BEFORE UPDATE ON work_package_dependencies
    BEGIN SELECT RAISE(ABORT, 'work package dependencies are immutable'); END
    """,
    """
    CREATE TRIGGER work_package_dependencies_no_delete
    BEFORE DELETE ON work_package_dependencies
    BEGIN SELECT RAISE(ABORT, 'work package dependencies are immutable'); END
    """,
)

_MIGRATION_0003: Final[tuple[str, ...]] = (
    """
    CREATE UNIQUE INDEX idx_dependency_edge_proof_identity
    ON work_package_dependencies(
        edge_id,
        mission_id,
        plan_revision_id,
        edge_hash,
        upstream_work_package_id,
        downstream_work_package_id,
        requirement
    )
    """,
    """
    CREATE TABLE dependency_satisfaction_proofs (
        proof_id TEXT PRIMARY KEY,
        proof_hash TEXT NOT NULL UNIQUE CHECK(length(proof_hash) = 64),
        mission_id TEXT NOT NULL,
        plan_revision_id TEXT NOT NULL,
        edge_id TEXT NOT NULL,
        edge_hash TEXT NOT NULL CHECK(length(edge_hash) = 64),
        requirement TEXT NOT NULL CHECK(requirement IN (
            'accepted_outcome',
            'published_success',
            'evidence_available',
            'settled'
        )),
        upstream_work_package_id TEXT NOT NULL,
        upstream_outcome_id TEXT NOT NULL,
        downstream_work_package_id TEXT NOT NULL,
        satisfaction_json TEXT NOT NULL,
        observed_kernel_state_version INTEGER NOT NULL
            CHECK(observed_kernel_state_version >= 0),
        observed_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(
            edge_id,
            mission_id,
            plan_revision_id,
            edge_hash,
            upstream_work_package_id,
            downstream_work_package_id,
            requirement
        ) REFERENCES work_package_dependencies(
            edge_id,
            mission_id,
            plan_revision_id,
            edge_hash,
            upstream_work_package_id,
            downstream_work_package_id,
            requirement
        ),
        FOREIGN KEY(upstream_work_package_id, mission_id, upstream_outcome_id)
            REFERENCES work_packages(work_package_id, mission_id, outcome_id),
        FOREIGN KEY(downstream_work_package_id, mission_id, plan_revision_id)
            REFERENCES work_packages(work_package_id, mission_id, plan_revision_id)
    )
    """,
    """
    CREATE TRIGGER dependency_satisfaction_proofs_no_update
    BEFORE UPDATE ON dependency_satisfaction_proofs
    BEGIN SELECT RAISE(ABORT, 'dependency satisfaction proofs are immutable'); END
    """,
    """
    CREATE TRIGGER dependency_satisfaction_proofs_no_delete
    BEFORE DELETE ON dependency_satisfaction_proofs
    BEGIN SELECT RAISE(ABORT, 'dependency satisfaction proofs are immutable'); END
    """,
)

_MIGRATION_0004: Final[tuple[str, ...]] = (
    "DROP TRIGGER acceptance_commits_no_update",
    "DROP TRIGGER acceptance_commits_no_delete",
    "ALTER TABLE acceptance_commits RENAME TO acceptance_commits_v3",
    """
    CREATE TABLE acceptance_commits (
        acceptance_commit_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        mission_id TEXT NOT NULL,
        work_package_id TEXT NOT NULL,
        outcome_id TEXT NOT NULL UNIQUE,
        attempt_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        backend_kind TEXT NOT NULL CHECK(backend_kind IN (
            'soma_durable_run', 'soma_reasoning'
        )),
        backend_ref TEXT NOT NULL CHECK(length(backend_ref) > 0),
        run_id TEXT,
        result_published_hash TEXT NOT NULL
            CHECK(length(result_published_hash) = 64),
        public_result_source_sha256 TEXT NOT NULL
            CHECK(length(public_result_source_sha256) = 64),
        acceptance_authority_ref TEXT NOT NULL,
        acceptance_basis_ref TEXT NOT NULL,
        acceptance_basis_hash TEXT NOT NULL DEFAULT ''
            CHECK(length(acceptance_basis_hash) IN (0, 64)),
        controller_request_id TEXT NOT NULL UNIQUE,
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        accepted_at TEXT NOT NULL,
        CHECK(
            (backend_kind = 'soma_durable_run' AND run_id = backend_ref)
            OR (backend_kind = 'soma_reasoning' AND run_id IS NULL)
        ),
        FOREIGN KEY(mission_id, company_id)
            REFERENCES missions(mission_id, company_id),
        FOREIGN KEY(
            work_package_id, mission_id, outcome_id, acceptance_authority_ref
        ) REFERENCES work_packages(
            work_package_id, mission_id, outcome_id, acceptance_authority_ref
        ),
        FOREIGN KEY(attempt_id, work_package_id, outcome_id, task_id)
            REFERENCES work_package_attempts(
                attempt_id, work_package_id, outcome_id, task_id
            ),
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    )
    """,
    """
    INSERT INTO acceptance_commits(
        acceptance_commit_id, company_id, mission_id, work_package_id,
        outcome_id, attempt_id, task_id, backend_kind, backend_ref, run_id,
        result_published_hash, public_result_source_sha256,
        acceptance_authority_ref, acceptance_basis_ref, acceptance_basis_hash,
        controller_request_id, request_hash, accepted_at
    )
    SELECT
        acceptance_commit_id, company_id, mission_id, work_package_id,
        outcome_id, attempt_id, task_id, 'soma_durable_run', run_id, run_id,
        result_published_hash, public_result_source_sha256,
        acceptance_authority_ref, acceptance_basis_ref, acceptance_basis_hash,
        controller_request_id, request_hash, accepted_at
    FROM acceptance_commits_v3
    """,
    "DROP TABLE acceptance_commits_v3",
    """
    CREATE TRIGGER acceptance_commits_no_update
    BEFORE UPDATE ON acceptance_commits
    BEGIN SELECT RAISE(ABORT, 'acceptance commits are immutable'); END
    """,
    """
    CREATE TRIGGER acceptance_commits_no_delete
    BEFORE DELETE ON acceptance_commits
    BEGIN SELECT RAISE(ABORT, 'acceptance commits are immutable'); END
    """,
)

COMPANY_KERNEL_MIGRATIONS: Final[tuple[tuple[int, str, tuple[str, ...]], ...]] = (
    (1, "company_kernel_foundation", _MIGRATION_0001),
    (2, "company_kernel_plan_graph", _MIGRATION_0002),
    (3, "company_kernel_dependency_proofs", _MIGRATION_0003),
    (4, "company_kernel_provider_neutral_acceptance", _MIGRATION_0004),
)

COMPANY_KERNEL_TABLE_NAMES: Final[tuple[str, ...]] = (
    "companies",
    "missions",
    "plan_revisions",
    "work_packages",
    "work_package_attempts",
    "acceptance_commits",
    "kernel_reconciliation_receipts",
    "plan_graph_manifests",
    "work_package_dependencies",
    "dependency_satisfaction_proofs",
)

COMPANY_KERNEL_TRIGGER_NAMES: Final[tuple[str, ...]] = (
    "companies_no_update",
    "companies_no_delete",
    "plan_revisions_no_update",
    "plan_revisions_no_delete",
    "work_packages_no_update",
    "work_packages_no_delete",
    "work_package_attempts_no_update",
    "work_package_attempts_no_delete",
    "acceptance_commits_no_update",
    "acceptance_commits_no_delete",
    "kernel_reconciliation_receipts_no_update",
    "kernel_reconciliation_receipts_no_delete",
    "missions_immutable_identity",
    "missions_no_delete",
    "plan_graph_manifests_no_update",
    "plan_graph_manifests_no_delete",
    "work_package_dependencies_no_update",
    "work_package_dependencies_no_delete",
    "dependency_satisfaction_proofs_no_update",
    "dependency_satisfaction_proofs_no_delete",
)

COMPANY_KERNEL_INDEX_NAMES: Final[tuple[str, ...]] = (
    "idx_work_package_attempt_single_successor",
    "idx_work_package_plan_membership",
    "idx_dependency_edge_proof_identity",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migration_table_present(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'soma_schema_migrations'"
        ).fetchone()
        is not None
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    if not _migration_table_present(conn):
        return set()
    rows = conn.execute(
        "SELECT version FROM soma_schema_migrations WHERE component = ?",
        (COMPANY_KERNEL_SCHEMA_COMPONENT,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def current_schema_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn)
    return max(versions) if versions else 0


def apply_company_kernel_migrations(
    connect: Callable[[], sqlite3.Connection],
    *,
    migrations: tuple[tuple[int, str, tuple[str, ...]], ...] | None = None,
) -> list[int]:
    """Apply each pending Company Kernel version atomically and exactly once."""
    selected = COMPANY_KERNEL_MIGRATIONS if migrations is None else migrations
    applied: list[int] = []
    for version, name, statements in selected:
        conn = connect()
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(MIGRATION_TABLE_SQL)
                row = conn.execute(
                    "SELECT 1 FROM soma_schema_migrations "
                    "WHERE component = ? AND version = ?",
                    (COMPANY_KERNEL_SCHEMA_COMPONENT, version),
                ).fetchone()
                if row is not None:
                    conn.commit()
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO soma_schema_migrations "
                    "(component, version, name, applied_at) VALUES (?, ?, ?, ?)",
                    (COMPANY_KERNEL_SCHEMA_COMPONENT, version, name, _utc_now()),
                )
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()
        applied.append(version)
    return applied


def schema_state(conn: sqlite3.Connection) -> dict[str, object]:
    version = current_schema_version(conn)
    objects = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('table', 'trigger', 'index')"
    ).fetchall()
    present = {(str(row[0]), str(row[1])) for row in objects}
    tables = [name for name in COMPANY_KERNEL_TABLE_NAMES if ("table", name) in present]
    triggers = [name for name in COMPANY_KERNEL_TRIGGER_NAMES if ("trigger", name) in present]
    indexes = [name for name in COMPANY_KERNEL_INDEX_NAMES if ("index", name) in present]
    missing_tables = [name for name in COMPANY_KERNEL_TABLE_NAMES if name not in tables]
    missing_triggers = [
        name for name in COMPANY_KERNEL_TRIGGER_NAMES if name not in triggers
    ]
    missing_indexes = [name for name in COMPANY_KERNEL_INDEX_NAMES if name not in indexes]
    complete = not missing_tables and not missing_triggers and not missing_indexes
    return {
        "component": COMPANY_KERNEL_SCHEMA_COMPONENT,
        "schema_version": version,
        "target_schema_version": COMPANY_KERNEL_SCHEMA_VERSION,
        "up_to_date": version == COMPANY_KERNEL_SCHEMA_VERSION and complete,
        "active_capability": False,
        "tables": tables,
        "missing_tables": missing_tables,
        "triggers": triggers,
        "missing_triggers": missing_triggers,
        "indexes": indexes,
        "missing_indexes": missing_indexes,
    }
