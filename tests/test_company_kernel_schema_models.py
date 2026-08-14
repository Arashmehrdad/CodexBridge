"""V3-1B-SCHEMA-MODELS-1: additive schema and immutable model proof.

No test invokes a company action, provider, gateway, scheduler, Task launch, Run
launch, acceptance service, or reconciliation loop. SQL inserts are fixtures for
constraint verification only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from soma.company_kernel import (
    COMPANY_KERNEL_INDEX_NAMES,
    COMPANY_KERNEL_MIGRATIONS,
    COMPANY_KERNEL_SCHEMA_VERSION,
    COMPANY_KERNEL_TABLE_NAMES,
    COMPANY_KERNEL_TRIGGER_NAMES,
    MISSION_ID_DOMAIN,
    PLAN_GRAPH_SCHEMA_VERSION,
    AcceptanceCommit,
    Company,
    CompanyKernelStore,
    Mission,
    WorkPackage,
    canonical_hash,
    canonical_json,
    normalize_work_package_contract,
    outcome_id_for,
    route_request_hash,
    work_package_contract_hash,
)
from soma.company_kernel.schema import apply_company_kernel_migrations
from soma.project_scope.store import ProjectScopeStore
from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore


COMPANY_ID = "company_" + "1" * 24
MISSION_ID = "mission_" + "2" * 24
PLAN_ID = "planrev_" + "3" * 24
PACKAGE_ID = "workpkg_" + "4" * 24
OUTCOME_ID = "outcome_" + "5" * 24
ATTEMPT_ID = "wpattempt_" + "6" * 24
ACCEPTANCE_ID = "accept_" + "7" * 24
RECONCILIATION_ID = "kreconcile_" + "8" * 24
PROJECT_ID = "proj_company_kernel_fixture"
RESOURCE_ID = "resource_company_kernel_fixture"
EXECUTIVE = "owner-controller:arash"
NOW = "2026-08-02T22:00:00+00:00"


def _prepare_dependencies(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    run_store = RunStore(runs_dir)
    task_store = TaskStore(runs_dir)
    scope_store = ProjectScopeStore(runs_dir)
    scope_store.init_db()
    with scope_store.connect() as conn:
        conn.execute(
            "INSERT INTO projects "
            "(project_id, project_key, lifecycle_state, scope_generation, created_at, updated_at) "
            "VALUES (?, 'company-kernel-fixture', 'active', 1, ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO project_resources "
            "(resource_id, resource_kind, opaque_ref, identity_hash, created_at) "
            "VALUES (?, 'repository', 'd:/github/soma', ?, ?)",
            (RESOURCE_ID, "a" * 64, NOW),
        )
        conn.execute(
            "INSERT INTO project_resource_bindings "
            "(project_id, resource_id, access_mode, created_at) "
            "VALUES (?, ?, 'exclusive', ?)",
            (PROJECT_ID, RESOURCE_ID, NOW),
        )
    return runs_dir, run_store, task_store, scope_store


def _make_task_and_run(runs_dir: Path, run_store: RunStore, task_store: TaskStore):
    run_id = "20260802T220000Z_fixture_abcdef12"
    run_dir = runs_dir / run_id
    run_dir.mkdir(exist_ok=True)
    normalized = normalize_durable_command_request(
        repo_name="soma",
        profile_id="powershell",
        argv=["-NoProfile", "-Command", "Write-Output fixture"],
    )
    run_store.create_run(
        run_id=run_id,
        repo_name="soma",
        tool="executable_profile",
        run_dir=run_dir,
        input_data=normalized,
        status="completed",
    )
    task_id = make_task_id()
    task_store.reserve_task(
        task_id=task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id="company-kernel-task-fixture",
        request_hash=normalized_request_hash(normalized),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref=run_id,
        backend_identity={"run_id": run_id},
    )
    return task_id, run_id


def _insert_company_mission_plan_package(
    conn: sqlite3.Connection,
    *,
    company_id: str = COMPANY_ID,
    mission_id: str = MISSION_ID,
    plan_id: str = PLAN_ID,
    package_id: str = PACKAGE_ID,
    outcome_id: str = OUTCOME_ID,
    executive: str = EXECUTIVE,
) -> None:
    conn.execute(
        "INSERT INTO companies VALUES (?, 'soma-company', 'Soma Company', ?, ?, ?, ?)",
        (company_id, executive, f"create:{company_id}", "1" * 64, NOW),
    )
    conn.execute(
        """
        INSERT INTO missions(
            mission_id, company_id, mission_key, project_id, resource_id,
            scope_generation, mission_contract_json, mission_contract_hash,
            accountable_owner_ref, acceptance_authority_ref,
            current_plan_revision_id, plan_state_version, kernel_state_version,
            creation_request_id, creation_request_hash, created_at, updated_at
        ) VALUES (?, ?, 'build-soma', ?, ?, 1, '{}', ?, ?, ?, NULL, 0, 0, ?, ?, ?, ?)
        """,
        (
            mission_id,
            company_id,
            PROJECT_ID,
            RESOURCE_ID,
            "2" * 64,
            executive,
            executive,
            f"create:{mission_id}",
            "3" * 64,
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
        ) VALUES (?, ?, 1, NULL, '{}', ?, '', '', ?, 'owner-decision', ?, ?, ?)
        """,
        (plan_id, mission_id, "4" * 64, executive, f"plan:{plan_id}", "5" * 64, NOW),
    )
    conn.execute(
        "UPDATE missions SET current_plan_revision_id = ?, plan_state_version = 1, "
        "kernel_state_version = 1, updated_at = ? WHERE mission_id = ?",
        (plan_id, NOW, mission_id),
    )
    conn.execute(
        """
        INSERT INTO work_packages(
            work_package_id, mission_id, plan_revision_id, package_key, outcome_id,
            project_id, target_resource_id, scope_generation, contract_version,
            contract_json, contract_hash, topology, accountable_owner_ref,
            acceptance_authority_ref, deliberation_ref, evidence_requirements_ref,
            controller_request_id, request_hash, created_at
        ) VALUES (?, ?, ?, 'schema-models', ?, ?, ?, 1, 'v1', '{}', ?,
                  'single_active', ?, ?, '', 'tests', ?, ?, ?)
        """,
        (
            package_id,
            mission_id,
            plan_id,
            outcome_id,
            PROJECT_ID,
            RESOURCE_ID,
            "6" * 64,
            executive,
            executive,
            f"package:{package_id}",
            "7" * 64,
            NOW,
        ),
    )


def _insert_attempt(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    attempt_id: str = ATTEMPT_ID,
    package_id: str = PACKAGE_ID,
    outcome_id: str = OUTCOME_ID,
    supersedes_attempt_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO work_package_attempts(
            attempt_id, work_package_id, outcome_id, task_id, route_request_hash,
            route_descriptor_json, supersedes_attempt_id, containment_evidence_ref,
            containment_evidence_hash, controller_request_id, request_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, '{}', ?, '', '', ?, ?, ?)
        """,
        (
            attempt_id,
            package_id,
            outcome_id,
            task_id,
            "8" * 64,
            supersedes_attempt_id,
            f"attempt:{attempt_id}",
            "9" * 64,
            NOW,
        ),
    )


def test_constructor_is_inert_and_absent_schema_is_honest(tmp_path: Path) -> None:
    runs_dir = tmp_path / "missing-runs"
    store = CompanyKernelStore(runs_dir)
    assert not runs_dir.exists()
    assert store.is_installed() is False
    assert store.schema_state() == {
        "component": "company_kernel",
        "schema_version": 0,
        "target_schema_version": COMPANY_KERNEL_SCHEMA_VERSION,
        "up_to_date": False,
        "active_capability": False,
        "tables": [],
        "missing_tables": list(COMPANY_KERNEL_TABLE_NAMES),
        "triggers": [],
        "missing_triggers": list(COMPANY_KERNEL_TRIGGER_NAMES),
        "indexes": [],
        "missing_indexes": list(COMPANY_KERNEL_INDEX_NAMES),
    }


def test_fresh_migration_is_complete_idempotent_and_inactive(tmp_path: Path) -> None:
    store = CompanyKernelStore(tmp_path / "runs")
    assert store.init_db() == [1, 2, 3, 4]
    assert store.init_db() == []
    state = store.schema_state()
    assert state["schema_version"] == COMPANY_KERNEL_SCHEMA_VERSION
    assert state["up_to_date"] is True
    assert state["active_capability"] is False
    assert set(state["tables"]) == set(COMPANY_KERNEL_TABLE_NAMES)
    assert set(state["triggers"]) == set(COMPANY_KERNEL_TRIGGER_NAMES)
    assert set(state["indexes"]) == set(COMPANY_KERNEL_INDEX_NAMES)
    assert state["missing_tables"] == []
    assert state["missing_triggers"] == []
    assert state["missing_indexes"] == []
    assert all(value == 0 for value in store.table_counts().values())
    with store.connect() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_marker_without_objects_is_not_reported_installed(
    tmp_path: Path,
) -> None:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO soma_schema_migrations "
            "(component, version, name, applied_at) VALUES (?, ?, ?, ?)",
            ("company_kernel", 1, "company_kernel_foundation", NOW),
        )
    state = store.schema_state()
    assert store.is_installed() is False
    assert state["schema_version"] == 1
    assert state["up_to_date"] is False
    assert state["missing_tables"] == list(COMPANY_KERNEL_TABLE_NAMES)
    assert state["missing_triggers"] == list(COMPANY_KERNEL_TRIGGER_NAMES)
    assert state["missing_indexes"] == list(COMPANY_KERNEL_INDEX_NAMES)


def test_failed_migration_rolls_back_every_kernel_object(tmp_path: Path) -> None:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    version, name, statements = COMPANY_KERNEL_MIGRATIONS[0]
    broken = ((version, name, (*statements, "SELECT * FROM missing_kernel_table")),)
    with pytest.raises(sqlite3.OperationalError):
        apply_company_kernel_migrations(store.connect, migrations=broken)
    with store.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        marker = conn.execute(
            "SELECT 1 FROM soma_schema_migrations WHERE component = 'company_kernel'"
        ).fetchone()
    assert not (set(COMPANY_KERNEL_TABLE_NAMES) & existing)
    assert marker is None


def test_migration_preserves_incumbent_rows_and_does_no_legacy_backfill(
    tmp_path: Path,
) -> None:
    runs_dir, _run_store, _task_store, scope_store = _prepare_dependencies(tmp_path)
    with scope_store.connect() as conn:
        conn.execute("CREATE TABLE workflows(id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE supervisors(id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute("INSERT INTO workflows VALUES ('workflow-1', 'reported')")
        conn.execute("INSERT INTO supervisors VALUES ('supervisor-1', 'needs_input')")
        before = {
            table: (
                conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0],
                conn.execute(f'SELECT * FROM "{table}"').fetchall(),
            )
            for table in ("projects", "project_resources", "workflows", "supervisors")
        }
    store = CompanyKernelStore(runs_dir)
    assert store.init_db() == [1, 2, 3, 4]
    with store.connect() as conn:
        after = {
            table: (
                conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0],
                conn.execute(f'SELECT * FROM "{table}"').fetchall(),
            )
            for table in before
        }
        assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0] == 0
    assert after == before


def test_v1_to_v2_migration_preserves_kernel_rows_without_graph_backfill(
    tmp_path: Path,
) -> None:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    assert apply_company_kernel_migrations(
        store.connect,
        migrations=(COMPANY_KERNEL_MIGRATIONS[0],),
    ) == [1]
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        before = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("companies", "missions", "plan_revisions", "work_packages")
        }

    assert apply_company_kernel_migrations(
        store.connect,
        migrations=(COMPANY_KERNEL_MIGRATIONS[1],),
    ) == [2]
    with store.connect() as conn:
        after = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in before
        }
        assert conn.execute("SELECT COUNT(*) FROM plan_graph_manifests").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM work_package_dependencies").fetchone()[0]
            == 0
        )
        migrated_package = conn.execute(
            "SELECT evidence_requirements_hash FROM work_packages "
            "WHERE work_package_id = ?",
            (PACKAGE_ID,),
        ).fetchone()
        assert migrated_package[0] == ""
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert after == before


def test_failed_v2_migration_rolls_back_every_graph_object(tmp_path: Path) -> None:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    assert apply_company_kernel_migrations(
        store.connect,
        migrations=(COMPANY_KERNEL_MIGRATIONS[0],),
    ) == [1]
    version, name, statements = COMPANY_KERNEL_MIGRATIONS[1]
    broken = ((version, name, (*statements, "SELECT * FROM missing_graph_table")),)

    with pytest.raises(sqlite3.OperationalError):
        apply_company_kernel_migrations(store.connect, migrations=broken)

    with store.connect() as conn:
        objects = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE type IN ('table', 'trigger', 'index')"
            ).fetchall()
        }
        marker = conn.execute(
            "SELECT 1 FROM soma_schema_migrations "
            "WHERE component = 'company_kernel' AND version = 2"
        ).fetchone()
    assert ("table", "plan_graph_manifests") not in objects
    assert ("table", "work_package_dependencies") not in objects
    assert ("index", "idx_work_package_plan_membership") not in objects
    assert ("trigger", "plan_graph_manifests_no_update") not in objects
    assert ("trigger", "work_package_dependencies_no_update") not in objects
    assert marker is None


def _insert_second_graph_package(conn: sqlite3.Connection) -> tuple[str, str]:
    package_id = "workpkg_" + "9" * 24
    outcome_id = "outcome_" + "9" * 24
    conn.execute(
        """
        INSERT INTO work_packages(
            work_package_id, mission_id, plan_revision_id, package_key, outcome_id,
            project_id, target_resource_id, scope_generation, contract_version,
            contract_json, contract_hash, topology, accountable_owner_ref,
            acceptance_authority_ref, deliberation_ref, evidence_requirements_ref,
            controller_request_id, request_hash, created_at
        ) VALUES (?, ?, ?, 'schema-models-second', ?, ?, ?, 1, 'v1', '{}', ?,
                  'single_active', ?, ?, '', '', 'package-second', ?, ?)
        """,
        (
            package_id,
            MISSION_ID,
            PLAN_ID,
            outcome_id,
            PROJECT_ID,
            RESOURCE_ID,
            "a" * 64,
            EXECUTIVE,
            EXECUTIVE,
            "b" * 64,
            NOW,
        ),
    )
    return package_id, outcome_id


def _insert_graph_dependency(
    conn: sqlite3.Connection,
    *,
    edge_id: str,
    downstream_package_id: str,
    requirement: str,
    edge_hash: str,
    selector_ref: str = "",
    selector_hash: str = "",
    upstream_package_id: str = PACKAGE_ID,
) -> None:
    conn.execute(
        """
        INSERT INTO work_package_dependencies(
            edge_id, mission_id, plan_revision_id, upstream_work_package_id,
            downstream_work_package_id, requirement, evidence_selector_ref,
            evidence_selector_hash, edge_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            MISSION_ID,
            PLAN_ID,
            upstream_package_id,
            downstream_package_id,
            requirement,
            selector_ref,
            selector_hash,
            edge_hash,
            NOW,
        ),
    )


def test_graph_tables_are_immutable_and_dependency_constraints_fail_closed(
    tmp_path: Path,
) -> None:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    store.init_db()
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        second_package_id, _second_outcome_id = _insert_second_graph_package(conn)
        conn.execute(
            """
            INSERT INTO plan_graph_manifests(
                plan_revision_id, mission_id, schema_version, manifest_json,
                manifest_hash, package_count, edge_count, created_at
            ) VALUES (?, ?, ?, '{}', ?, 2, 1, ?)
            """,
            (PLAN_ID, MISSION_ID, PLAN_GRAPH_SCHEMA_VERSION, "c" * 64, NOW),
        )
        _insert_graph_dependency(
            conn,
            edge_id="edge-valid",
            downstream_package_id=second_package_id,
            requirement="accepted_outcome",
            edge_hash="d" * 64,
        )

        for statement in (
            "UPDATE plan_graph_manifests SET manifest_json = '{\"changed\":true}'",
            "DELETE FROM plan_graph_manifests",
            "UPDATE work_package_dependencies SET requirement = 'settled'",
            "DELETE FROM work_package_dependencies",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(statement)

        invalid_rows = (
            dict(
                edge_id="edge-self",
                downstream_package_id=PACKAGE_ID,
                requirement="settled",
                edge_hash="e" * 64,
            ),
            dict(
                edge_id="edge-unknown",
                downstream_package_id=second_package_id,
                requirement="unknown",
                edge_hash="f" * 64,
            ),
            dict(
                edge_id="edge-missing-selector",
                downstream_package_id=second_package_id,
                requirement="evidence_available",
                edge_hash="1" * 64,
            ),
            dict(
                edge_id="edge-forbidden-selector",
                downstream_package_id=second_package_id,
                requirement="settled",
                edge_hash="3" * 64,
                selector_ref="selector:forbidden",
                selector_hash="2" * 64,
            ),
        )
        for values in invalid_rows:
            with pytest.raises(sqlite3.IntegrityError):
                _insert_graph_dependency(conn, **values)

        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_database_enforces_fixed_executive_authority_chain(tmp_path: Path) -> None:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    store.init_db()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO companies VALUES (?, 'soma-company', 'Soma Company', ?, 'create-company', ?, ?)",
            (COMPANY_ID, EXECUTIVE, "1" * 64, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO missions(
                    mission_id, company_id, mission_key, project_id, resource_id,
                    scope_generation, mission_contract_json, mission_contract_hash,
                    accountable_owner_ref, acceptance_authority_ref,
                    current_plan_revision_id, plan_state_version, kernel_state_version,
                    creation_request_id, creation_request_hash, created_at, updated_at
                ) VALUES (?, ?, 'bad', ?, ?, 1, '{}', ?, 'other-owner', ?, NULL, 0, 0,
                          'bad-mission-request', ?, ?, ?)
                """,
                (
                    MISSION_ID,
                    COMPANY_ID,
                    PROJECT_ID,
                    RESOURCE_ID,
                    "2" * 64,
                    EXECUTIVE,
                    "3" * 64,
                    NOW,
                    NOW,
                ),
            )
        conn.rollback()
        # The failed statement rolled back its transaction, including the fixture company.
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO plan_revisions VALUES (
                    ?, ?, 2, NULL, '{}', ?, '', '', 'other-authority', '',
                    'bad-plan-authority', ?, ?
                )
                """,
                ("planrev_" + "a" * 24, MISSION_ID, "a" * 64, "b" * 64, NOW),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO work_packages(
                    work_package_id, mission_id, plan_revision_id, package_key,
                    outcome_id, project_id, target_resource_id, scope_generation,
                    contract_version, contract_json, contract_hash, topology,
                    accountable_owner_ref, acceptance_authority_ref,
                    deliberation_ref, evidence_requirements_ref,
                    controller_request_id, request_hash, created_at
                ) VALUES (?, ?, ?, 'bad-authority', ?, ?, ?, 1, 'v1', '{}', ?,
                          'single_active', ?, 'other-authority', '', '', ?, ?, ?)
                """,
                (
                    "workpkg_" + "b" * 24,
                    MISSION_ID,
                    PLAN_ID,
                    "outcome_" + "b" * 24,
                    PROJECT_ID,
                    RESOURCE_ID,
                    "c" * 64,
                    EXECUTIVE,
                    "bad-package-authority",
                    "d" * 64,
                    NOW,
                ),
            )


def test_attempt_and_acceptance_relationships_and_one_winner_are_enforced(
    tmp_path: Path,
) -> None:
    runs_dir, run_store, task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    store.init_db()
    task_id, run_id = _make_task_and_run(runs_dir, run_store, task_store)
    other_task_id = make_task_id()
    task_store.reserve_task(
        task_id=other_task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id="company-kernel-other-task",
        request_hash="a" * 64,
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref="",
        backend_identity={},
    )
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_attempt(
                conn,
                task_id=task_id,
                outcome_id="outcome_" + "f" * 24,
            )
        _insert_attempt(conn, task_id=task_id)
        acceptance_values = (
            ACCEPTANCE_ID,
            COMPANY_ID,
            MISSION_ID,
            PACKAGE_ID,
            OUTCOME_ID,
            ATTEMPT_ID,
            task_id,
            BackendKind.SOMA_DURABLE_RUN.value,
            run_id,
            run_id,
            "a" * 64,
            "b" * 64,
            EXECUTIVE,
            "owner acceptance",
            "c" * 64,
            "acceptance-request",
            "d" * 64,
            NOW,
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO acceptance_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*acceptance_values[:6], other_task_id, *acceptance_values[7:]),
            )
        conn.execute(
            "INSERT INTO acceptance_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            acceptance_values,
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO acceptance_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "accept_" + "e" * 24,
                    *acceptance_values[1:15],
                    "second-acceptance-request",
                    "e" * 64,
                    NOW,
                ),
            )


def test_immutable_facts_reject_update_delete_but_mission_cas_fields_are_open(
    tmp_path: Path,
) -> None:
    runs_dir, run_store, task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    store.init_db()
    task_id, run_id = _make_task_and_run(runs_dir, run_store, task_store)
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        _insert_attempt(conn, task_id=task_id)
        conn.execute(
            "INSERT INTO acceptance_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ACCEPTANCE_ID,
                COMPANY_ID,
                MISSION_ID,
                PACKAGE_ID,
                OUTCOME_ID,
                ATTEMPT_ID,
                task_id,
                BackendKind.SOMA_DURABLE_RUN.value,
                run_id,
                run_id,
                "a" * 64,
                "b" * 64,
                EXECUTIVE,
                "owner acceptance",
                "c" * 64,
                "acceptance-request",
                "d" * 64,
                NOW,
            ),
        )
        conn.execute(
            "INSERT INTO kernel_reconciliation_receipts VALUES (?, ?, 'owner_turn', "
            "'trigger-1', 1, 'no_op', '', ?, ?)",
            (RECONCILIATION_ID, MISSION_ID, "e" * 64, NOW),
        )
        for statement in (
            "UPDATE companies SET display_name = 'changed'",
            "UPDATE plan_revisions SET acceptance_basis_ref = 'changed'",
            "UPDATE work_packages SET package_key = 'changed'",
            "UPDATE work_package_attempts SET route_descriptor_json = '{\"x\":1}'",
            "UPDATE acceptance_commits SET acceptance_basis_ref = 'changed'",
            "UPDATE kernel_reconciliation_receipts SET target_ref = 'changed'",
            "DELETE FROM companies",
            "DELETE FROM missions",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(statement)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE missions SET accountable_owner_ref = 'other' WHERE mission_id = ?",
                (MISSION_ID,),
            )
        conn.execute(
            "UPDATE missions SET plan_state_version = 2, kernel_state_version = 2, "
            "updated_at = ? WHERE mission_id = ?",
            ("2026-08-02T22:01:00+00:00", MISSION_ID),
        )
        row = conn.execute(
            "SELECT plan_state_version, kernel_state_version FROM missions WHERE mission_id = ?",
            (MISSION_ID,),
        ).fetchone()
    assert tuple(row) == (2, 2)


def test_package_and_attempt_tables_carry_no_execution_authority(tmp_path: Path) -> None:
    store = CompanyKernelStore(tmp_path / "runs")
    store.init_db()
    forbidden = {
        "status",
        "state",
        "pid",
        "process",
        "lease",
        "lock",
        "result",
        "publication",
        "cancellation",
        "recovery",
        "worker",
    }
    with store.connect() as conn:
        columns = {
            row[1]
            for table in ("work_packages", "work_package_attempts")
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
    assert not {
        column
        for column in columns
        if any(fragment in column.lower() for fragment in forbidden)
    }


def test_route_independent_outcome_excludes_route_material() -> None:
    contract = {
        "purpose": "prove schema",
        "expected_outcome": "accepted migration evidence",
        "constraints": ["no provider launch"],
    }
    contract_hash = work_package_contract_hash(contract_version="v1", contract=contract)
    identity = dict(
        mission_id=MISSION_ID,
        plan_revision_id=PLAN_ID,
        package_key="schema-models",
        contract_hash=contract_hash,
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
    )
    outcome = outcome_id_for(**identity)
    route_a = route_request_hash({"provider": "claude_code", "argv": ["one"]})
    route_b = route_request_hash({"provider": "codex", "argv": ["two"]})
    assert route_a != route_b
    assert outcome_id_for(**identity) == outcome
    with pytest.raises(ValueError, match="route-specific"):
        normalize_work_package_contract(
            contract_version="v1",
            contract={**contract, "provider": "claude_code"},
        )
    with pytest.raises(TypeError):
        outcome_id_for(**identity, provider="claude_code")


def test_models_are_strict_frozen_canonical_and_hash_checked() -> None:
    company = Company(
        company_id=COMPANY_ID,
        company_key="soma",
        display_name="Soma",
        executive_authority_ref=EXECUTIVE,
        creation_request_id="company-request",
        creation_request_hash="a" * 64,
        created_at=NOW,
    )
    with pytest.raises(ValidationError):
        Company.model_validate({**company.to_dict(), "surprise": True})
    with pytest.raises(ValidationError):
        company.display_name = "Changed"

    mission_contract = {"purpose": "coordinate Soma"}
    mission_json = canonical_json(mission_contract)
    mission = Mission(
        mission_id=MISSION_ID,
        company_id=COMPANY_ID,
        mission_key="build-soma",
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        scope_generation=1,
        mission_contract_json=mission_json,
        mission_contract_hash=canonical_hash(MISSION_ID_DOMAIN, mission_contract),
        accountable_owner_ref=EXECUTIVE,
        acceptance_authority_ref=EXECUTIVE,
        creation_request_id="mission-request",
        creation_request_hash="b" * 64,
        created_at=NOW,
        updated_at=NOW,
    )
    assert mission.mission_contract_json == mission_json
    with pytest.raises(ValidationError, match="canonical"):
        Mission.model_validate({**mission.to_dict(), "mission_contract_json": '{"z": 1, "a": 2}'})
    with pytest.raises(ValidationError, match="must match"):
        Mission.model_validate({**mission.to_dict(), "acceptance_authority_ref": "other"})
    with pytest.raises(ValidationError, match="does not match"):
        Mission.model_validate({**mission.to_dict(), "mission_contract_hash": "f" * 64})

    package_contract = {"purpose": "schema proof"}
    package_hash = work_package_contract_hash(
        contract_version="v1", contract=package_contract
    )
    package = WorkPackage(
        work_package_id=PACKAGE_ID,
        mission_id=MISSION_ID,
        plan_revision_id=PLAN_ID,
        package_key="schema-models",
        outcome_id=outcome_id_for(
            mission_id=MISSION_ID,
            plan_revision_id=PLAN_ID,
            package_key="schema-models",
            contract_hash=package_hash,
            project_id=PROJECT_ID,
            resource_id=RESOURCE_ID,
            scope_generation=1,
        ),
        project_id=PROJECT_ID,
        target_resource_id=RESOURCE_ID,
        scope_generation=1,
        contract_version="v1",
        contract_json=canonical_json(package_contract),
        contract_hash=package_hash,
        accountable_owner_ref=EXECUTIVE,
        acceptance_authority_ref=EXECUTIVE,
        controller_request_id="package-request",
        request_hash="c" * 64,
        created_at=NOW,
    )
    assert package.topology == "single_active"

    acceptance = AcceptanceCommit(
        acceptance_commit_id=ACCEPTANCE_ID,
        company_id=COMPANY_ID,
        mission_id=MISSION_ID,
        work_package_id=PACKAGE_ID,
        outcome_id=package.outcome_id,
        attempt_id=ATTEMPT_ID,
        task_id="task_20260802T220000Z_abcdefabcdef",
        backend_kind="soma_durable_run",
        backend_ref="20260802T220000Z_fixture_abcdef12",
        run_id="20260802T220000Z_fixture_abcdef12",
        result_published_hash="d" * 64,
        public_result_source_sha256="e" * 64,
        acceptance_authority_ref=EXECUTIVE,
        acceptance_basis_ref="owner acceptance",
        acceptance_basis_hash="f" * 64,
        controller_request_id="acceptance-request",
        request_hash="1" * 64,
        accepted_at=NOW,
    )
    assert acceptance.outcome_id == package.outcome_id


def _prepare_v2_graph_for_proof_migration(
    tmp_path: Path,
) -> tuple[CompanyKernelStore, str]:
    runs_dir, _run_store, _task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    assert apply_company_kernel_migrations(
        store.connect,
        migrations=COMPANY_KERNEL_MIGRATIONS[:2],
    ) == [1, 2]
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        downstream_package_id, _downstream_outcome_id = _insert_second_graph_package(conn)
        conn.execute(
            """
            INSERT INTO plan_graph_manifests(
                plan_revision_id, mission_id, schema_version, manifest_json,
                manifest_hash, package_count, edge_count, created_at
            ) VALUES (?, ?, ?, '{}', ?, 2, 1, ?)
            """,
            (PLAN_ID, MISSION_ID, PLAN_GRAPH_SCHEMA_VERSION, "c" * 64, NOW),
        )
        _insert_graph_dependency(
            conn,
            edge_id="edge-proof-fixture",
            downstream_package_id=downstream_package_id,
            requirement="accepted_outcome",
            edge_hash="d" * 64,
        )
    return store, downstream_package_id


def _insert_dependency_proof(
    conn: sqlite3.Connection,
    *,
    proof_id: str,
    proof_hash: str,
    downstream_package_id: str,
    edge_hash: str = "d" * 64,
    requirement: str = "accepted_outcome",
    upstream_package_id: str = PACKAGE_ID,
) -> None:
    conn.execute(
        """
        INSERT INTO dependency_satisfaction_proofs(
            proof_id, proof_hash, mission_id, plan_revision_id, edge_id,
            edge_hash, requirement, upstream_work_package_id,
            upstream_outcome_id, downstream_work_package_id,
            satisfaction_json, observed_kernel_state_version,
            observed_at, created_at
        ) VALUES (?, ?, ?, ?, 'edge-proof-fixture', ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            proof_id,
            proof_hash,
            MISSION_ID,
            PLAN_ID,
            edge_hash,
            requirement,
            upstream_package_id,
            OUTCOME_ID,
            downstream_package_id,
            '{"kind":"accepted_outcome"}',
            NOW,
            NOW,
        ),
    )


def test_v2_to_v3_migration_preserves_graph_rows_without_proof_backfill(
    tmp_path: Path,
) -> None:
    store, downstream_package_id = _prepare_v2_graph_for_proof_migration(tmp_path)
    with store.connect() as conn:
        before = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in (
                "companies",
                "missions",
                "plan_revisions",
                "work_packages",
                "plan_graph_manifests",
                "work_package_dependencies",
            )
        }

    assert apply_company_kernel_migrations(
        store.connect,
        migrations=(COMPANY_KERNEL_MIGRATIONS[2],),
    ) == [3]
    with store.connect() as conn:
        after = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in before
        }
        assert (
            conn.execute("SELECT COUNT(*) FROM dependency_satisfaction_proofs").fetchone()[0]
            == 0
        )
        _insert_dependency_proof(
            conn,
            proof_id="proof-valid",
            proof_hash="a" * 64,
            downstream_package_id=downstream_package_id,
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert after == before


def test_failed_v3_migration_rolls_back_proof_schema_objects(tmp_path: Path) -> None:
    store, _downstream_package_id = _prepare_v2_graph_for_proof_migration(tmp_path)
    version, name, statements = COMPANY_KERNEL_MIGRATIONS[2]
    broken = ((version, name, (*statements, "SELECT * FROM missing_proof_table")),)

    with pytest.raises(sqlite3.OperationalError):
        apply_company_kernel_migrations(store.connect, migrations=broken)

    with store.connect() as conn:
        objects = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE type IN ('table', 'trigger', 'index')"
            ).fetchall()
        }
        marker = conn.execute(
            "SELECT 1 FROM soma_schema_migrations "
            "WHERE component = 'company_kernel' AND version = 3"
        ).fetchone()
    assert ("table", "dependency_satisfaction_proofs") not in objects
    assert ("index", "idx_dependency_edge_proof_identity") not in objects
    assert ("trigger", "dependency_satisfaction_proofs_no_update") not in objects
    assert ("trigger", "dependency_satisfaction_proofs_no_delete") not in objects
    assert marker is None


def test_dependency_proof_schema_is_immutable_and_fails_closed_on_identity_drift(
    tmp_path: Path,
) -> None:
    store, downstream_package_id = _prepare_v2_graph_for_proof_migration(tmp_path)
    assert apply_company_kernel_migrations(
        store.connect,
        migrations=(COMPANY_KERNEL_MIGRATIONS[2],),
    ) == [3]
    with store.connect() as conn:
        _insert_dependency_proof(
            conn,
            proof_id="proof-valid",
            proof_hash="a" * 64,
            downstream_package_id=downstream_package_id,
        )
        for statement in (
            "UPDATE dependency_satisfaction_proofs SET observed_at = 'changed'",
            "DELETE FROM dependency_satisfaction_proofs",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(statement)

        with pytest.raises(sqlite3.IntegrityError):
            _insert_dependency_proof(
                conn,
                proof_id="proof-edge-hash-mismatch",
                proof_hash="b" * 64,
                downstream_package_id=downstream_package_id,
                edge_hash="e" * 64,
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_dependency_proof(
                conn,
                proof_id="proof-requirement-mismatch",
                proof_hash="c" * 64,
                downstream_package_id=downstream_package_id,
                requirement="settled",
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_dependency_proof(
                conn,
                proof_id="proof-upstream-mismatch",
                proof_hash="d" * 64,
                downstream_package_id=downstream_package_id,
                upstream_package_id=downstream_package_id,
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_dependency_proof(
                conn,
                proof_id="proof-duplicate-hash",
                proof_hash="a" * 64,
                downstream_package_id=downstream_package_id,
            )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def _prepare_v3_acceptance_for_provider_neutral_migration(
    tmp_path: Path,
) -> tuple[CompanyKernelStore, str, str]:
    runs_dir, run_store, task_store, _scope_store = _prepare_dependencies(tmp_path)
    store = CompanyKernelStore(runs_dir)
    assert apply_company_kernel_migrations(
        store.connect,
        migrations=COMPANY_KERNEL_MIGRATIONS[:3],
    ) == [1, 2, 3]
    task_id, run_id = _make_task_and_run(runs_dir, run_store, task_store)
    with store.connect() as conn:
        _insert_company_mission_plan_package(conn)
        _insert_attempt(conn, task_id=task_id)
        conn.execute(
            "INSERT INTO acceptance_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ACCEPTANCE_ID,
                COMPANY_ID,
                MISSION_ID,
                PACKAGE_ID,
                OUTCOME_ID,
                ATTEMPT_ID,
                task_id,
                run_id,
                "a" * 64,
                "b" * 64,
                EXECUTIVE,
                "legacy owner acceptance",
                "",
                "legacy-acceptance-request",
                "d" * 64,
                NOW,
            ),
        )
    return store, task_id, run_id


def test_v3_to_v4_migration_preserves_acceptance_and_binds_durable_backend(
    tmp_path: Path,
) -> None:
    store, task_id, run_id = _prepare_v3_acceptance_for_provider_neutral_migration(
        tmp_path
    )
    with store.connect() as conn:
        before = dict(
            conn.execute(
                "SELECT * FROM acceptance_commits WHERE acceptance_commit_id = ?",
                (ACCEPTANCE_ID,),
            ).fetchone()
        )
        task_count_before = int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
        run_count_before = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    assert apply_company_kernel_migrations(
        store.connect,
        migrations=(COMPANY_KERNEL_MIGRATIONS[3],),
    ) == [4]

    with store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM acceptance_commits WHERE acceptance_commit_id = ?",
            (ACCEPTANCE_ID,),
        ).fetchone()
        assert row is not None
        migrated = dict(row)
        assert migrated["task_id"] == task_id == before["task_id"]
        assert migrated["backend_kind"] == "soma_durable_run"
        assert migrated["backend_ref"] == run_id
        assert migrated["run_id"] == run_id == before["run_id"]
        assert migrated["result_published_hash"] == before["result_published_hash"]
        assert (
            migrated["public_result_source_sha256"]
            == before["public_result_source_sha256"]
        )
        assert migrated["acceptance_authority_ref"] == before["acceptance_authority_ref"]
        assert migrated["acceptance_basis_ref"] == before["acceptance_basis_ref"]
        # V1-v3 permitted this historical field to be empty; v4 preserves the
        # immutable fact instead of inventing a hash during migration.
        assert migrated["acceptance_basis_hash"] == before["acceptance_basis_hash"] == ""
        assert migrated["controller_request_id"] == before["controller_request_id"]
        assert migrated["request_hash"] == before["request_hash"]
        assert migrated["accepted_at"] == before["accepted_at"]
        reconstructed = AcceptanceCommit.model_validate(migrated)
        assert reconstructed.backend_kind == "soma_durable_run"
        assert reconstructed.backend_ref == run_id
        assert reconstructed.run_id == run_id
        assert reconstructed.acceptance_basis_hash == ""
        assert int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]) == task_count_before
        assert int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]) == run_count_before
        assert (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'acceptance_commits_v3'"
            ).fetchone()
            is None
        )
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_v4_migration_restores_exact_v3_acceptance_schema_and_row(
    tmp_path: Path,
) -> None:
    store, _task_id, run_id = _prepare_v3_acceptance_for_provider_neutral_migration(
        tmp_path
    )
    with store.connect() as conn:
        before = dict(
            conn.execute(
                "SELECT * FROM acceptance_commits WHERE acceptance_commit_id = ?",
                (ACCEPTANCE_ID,),
            ).fetchone()
        )
    version, name, statements = COMPANY_KERNEL_MIGRATIONS[3]
    broken = ((version, name, (*statements, "SELECT * FROM missing_v4_table")),)

    with pytest.raises(sqlite3.OperationalError):
        apply_company_kernel_migrations(store.connect, migrations=broken)

    with store.connect() as conn:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(acceptance_commits)").fetchall()
        }
        after = dict(
            conn.execute(
                "SELECT * FROM acceptance_commits WHERE acceptance_commit_id = ?",
                (ACCEPTANCE_ID,),
            ).fetchone()
        )
        marker = conn.execute(
            "SELECT 1 FROM soma_schema_migrations "
            "WHERE component = 'company_kernel' AND version = 4"
        ).fetchone()
        v3_shadow = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'acceptance_commits_v3'"
        ).fetchone()
        triggers = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'acceptance_commits_%'"
            ).fetchall()
        }
        assert "backend_kind" not in columns
        assert "backend_ref" not in columns
        assert after == before
        assert after["run_id"] == run_id
        assert marker is None
        assert v3_shadow is None
        assert {
            "acceptance_commits_no_update",
            "acceptance_commits_no_delete",
        } <= triggers
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_store_exposes_schema_only_not_company_actions() -> None:
    public = {name for name in dir(CompanyKernelStore) if not name.startswith("_")}
    assert public == {
        "connect",
        "init_db",
        "is_installed",
        "schema_state",
        "table_counts",
        "transaction",
    }
