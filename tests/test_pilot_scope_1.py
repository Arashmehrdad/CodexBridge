from __future__ import annotations

import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

import soma.hermes_service_gateway as hermes_gateway_module
from soma.gateway_models import TaskDurableCommandStart
from soma.hermes_service import (
    HermesRegistryIdentity,
    HermesServiceRequest,
    HermesServiceResult,
)
from soma.hermes_service_gateway import HermesServiceGateway
from soma.memory.models import MemoryRecord, MemoryType
from soma.memory.search import like_pattern
from soma.memory.store import ProjectMemoryStore
from soma.operation_locks import OperationLockStore
from soma.run_artifacts import resolve_output_artifacts
from soma.run_store import utc_now
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    TaskLinkTargetKind,
    TaskLinkType,
    make_task_id,
)
from soma.tasks.projections import (
    TASK_RESPONSE_BUDGET_BYTES,
    compact_task_status,
    finalize,
    response_bytes,
)
from soma.tasks.schema import TASK_TABLE_NAMES
from soma.tasks.store import TaskStore


PROJECT_ALPHA = "project_alpha"
PROJECT_BETA = "project_beta"
SCOPE_GENERATION = 1
REPO_ALIAS = "mirror-api"
RUN_ALPHA = "20260727T120000Z_executable_profile_aaaaaaaa"
RUN_BETA = "20260727T120001Z_executable_profile_bbbbbbbb"
RUN_HERMES = "20260727T120002Z_hermes_service_cccccccc"
SCHEMA_HASH = "d" * 64


class PilotScopeError(ValueError):
    pass


MAIN_SCOPE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pilot_scope_projects (
    project_id TEXT PRIMARY KEY,
    project_key TEXT NOT NULL UNIQUE,
    lifecycle_state TEXT NOT NULL
        CHECK(lifecycle_state IN ('active', 'suspended', 'archived')),
    scope_generation INTEGER NOT NULL CHECK(scope_generation >= 1),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pilot_scope_resources (
    resource_id TEXT PRIMARY KEY,
    resource_kind TEXT NOT NULL,
    opaque_ref TEXT NOT NULL,
    identity_hash TEXT NOT NULL,
    UNIQUE(resource_kind, identity_hash)
);

CREATE TABLE IF NOT EXISTS pilot_scope_project_resources (
    project_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    access_mode TEXT NOT NULL CHECK(access_mode IN ('exclusive', 'shared')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, resource_id),
    FOREIGN KEY(project_id) REFERENCES pilot_scope_projects(project_id),
    FOREIGN KEY(resource_id) REFERENCES pilot_scope_resources(resource_id)
);

CREATE TABLE IF NOT EXISTS pilot_scope_repository_bindings (
    project_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, repository_id),
    UNIQUE(project_id, repo_name),
    FOREIGN KEY(project_id, repository_id)
        REFERENCES pilot_scope_project_resources(project_id, resource_id)
);

CREATE TABLE IF NOT EXISTS pilot_scope_worktrees (
    worktree_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    root_identity TEXT NOT NULL UNIQUE,
    branch_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id, repository_id)
        REFERENCES pilot_scope_repository_bindings(project_id, repository_id)
);

CREATE TABLE IF NOT EXISTS pilot_scope_task_reservations (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scope_generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'attached', 'quarantined')),
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES pilot_scope_projects(project_id),
    UNIQUE(project_id, task_id)
);

CREATE TABLE IF NOT EXISTS pilot_scope_attempts (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    scope_generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'attached', 'quarantined')),
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id, task_id)
        REFERENCES pilot_scope_task_reservations(project_id, task_id),
    FOREIGN KEY(project_id, resource_id)
        REFERENCES pilot_scope_project_resources(project_id, resource_id),
    UNIQUE(project_id, run_id)
);

CREATE TABLE IF NOT EXISTS pilot_scope_external_sessions (
    binding_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    provider_kind TEXT NOT NULL,
    provider_session_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'closed', 'quarantined')),
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id, task_id)
        REFERENCES pilot_scope_task_reservations(project_id, task_id),
    FOREIGN KEY(project_id, run_id)
        REFERENCES pilot_scope_attempts(project_id, run_id),
    UNIQUE(provider_kind, provider_session_id)
);

CREATE TABLE IF NOT EXISTS pilot_scope_quarantine (
    record_kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(record_kind, record_id)
);

CREATE TRIGGER IF NOT EXISTS pilot_scope_tasks_fail_closed
BEFORE INSERT ON tasks
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM pilot_scope_task_reservations
        WHERE task_id = NEW.task_id AND status = 'reserved'
    ) THEN RAISE(ABORT, 'unscoped task')
    END;
END;

CREATE TRIGGER IF NOT EXISTS pilot_scope_task_links_fail_closed
BEFORE INSERT ON task_links
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM pilot_scope_task_reservations
        WHERE task_id = NEW.task_id
    ) THEN RAISE(ABORT, 'unscoped task link')
    WHEN NEW.target_kind = 'task' AND NOT EXISTS (
        SELECT 1
        FROM pilot_scope_task_reservations source
        JOIN pilot_scope_task_reservations target
          ON target.project_id = source.project_id
        WHERE source.task_id = NEW.task_id
          AND target.task_id = NEW.target_id
    ) THEN RAISE(ABORT, 'cross-project task link')
    WHEN NEW.target_kind = 'durable_run' AND NOT EXISTS (
        SELECT 1
        FROM pilot_scope_task_reservations source
        JOIN pilot_scope_attempts target
          ON target.project_id = source.project_id
        WHERE source.task_id = NEW.task_id
          AND target.run_id = NEW.target_id
    ) THEN RAISE(ABORT, 'cross-project backend link')
    END;
END;

CREATE TRIGGER IF NOT EXISTS pilot_scope_runs_fail_closed
BEFORE INSERT ON runs
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM pilot_scope_attempts
        WHERE run_id = NEW.run_id AND status = 'reserved'
    ) THEN RAISE(ABORT, 'unscoped run')
    END;
END;

CREATE TRIGGER IF NOT EXISTS pilot_scope_locks_fail_closed
BEFORE INSERT ON operation_locks
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM pilot_scope_attempts attempt
        JOIN pilot_scope_resources resource
          ON resource.resource_id = attempt.resource_id
        WHERE attempt.run_id = NEW.run_id
          AND resource.opaque_ref = NEW.repo_name
    ) THEN RAISE(ABORT, 'lock resource scope mismatch')
    END;
END;

INSERT OR IGNORE INTO soma_schema_migrations
    (component, version, name, applied_at)
VALUES
    ('pilot_scope_1_fixture', 1, 'project_scope_sidecar', datetime('now'));
"""


MEMORY_SCOPE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pilot_scope_memory_reservations (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scope_generation INTEGER NOT NULL,
    registry_generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'attached', 'quarantined')),
    created_at TEXT NOT NULL,
    UNIQUE(project_id, memory_id)
);

CREATE TRIGGER IF NOT EXISTS pilot_scope_memory_fail_closed
BEFORE INSERT ON memory_records
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM pilot_scope_memory_reservations
        WHERE memory_id = NEW.memory_id AND status = 'reserved'
    ) THEN RAISE(ABORT, 'unscoped memory')
    END;
END;
"""


def _apply_script(conn: sqlite3.Connection, script: str) -> None:
    try:
        conn.executescript(f"BEGIN IMMEDIATE;\n{script}\nCOMMIT;")
    except BaseException:
        conn.rollback()
        raise


class PilotProjectScopeStore:
    """Test-only production-shaped project identity sidecar."""

    def __init__(self, runs_dir: Path):
        self.db_path = runs_dir / "soma.sqlite3"
        with self.connect() as conn:
            _apply_script(conn, MAIN_SCOPE_SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_project(self, project_id: str, project_key: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_projects VALUES (?, ?, 'active', ?, ?)",
                (project_id, project_key, SCOPE_GENERATION, utc_now()),
            )

    def project_generation(self, project_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT scope_generation FROM pilot_scope_projects "
                "WHERE project_id = ? AND lifecycle_state = 'active'",
                (project_id,),
            ).fetchone()
        if row is None:
            raise PilotScopeError(f"inactive or unknown project: {project_id}")
        return int(row["scope_generation"])

    def register_resource(
        self,
        *,
        resource_id: str,
        resource_kind: str,
        opaque_ref: str,
        identity: str,
    ) -> None:
        identity_hash = sha256(identity.encode("utf-8")).hexdigest()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_resources VALUES (?, ?, ?, ?)",
                (resource_id, resource_kind, opaque_ref, identity_hash),
            )

    def bind_resource(
        self, project_id: str, resource_id: str, *, access_mode: str = "exclusive"
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_project_resources VALUES (?, ?, ?, ?)",
                (project_id, resource_id, access_mode, utc_now()),
            )

    def register_repository(
        self,
        project_id: str,
        repository_id: str,
        *,
        repo_name: str,
        root_identity: str,
    ) -> None:
        self.register_resource(
            resource_id=repository_id,
            resource_kind="repository",
            opaque_ref=repo_name,
            identity=root_identity,
        )
        self.bind_resource(project_id, repository_id)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_repository_bindings VALUES (?, ?, ?, ?)",
                (project_id, repository_id, repo_name, utc_now()),
            )

    def register_worktree(
        self,
        project_id: str,
        repository_id: str,
        worktree_id: str,
        *,
        root_identity: str,
        branch_ref: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_worktrees VALUES (?, ?, ?, ?, ?, ?)",
                (
                    worktree_id,
                    project_id,
                    repository_id,
                    root_identity,
                    branch_ref,
                    utc_now(),
                ),
            )

    def reserve_task_attempt(
        self,
        *,
        project_id: str,
        task_id: str,
        run_id: str,
        resource_id: str,
    ) -> None:
        generation = self.project_generation(project_id)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO pilot_scope_task_reservations "
                    "VALUES (?, ?, ?, 'reserved', ?)",
                    (task_id, project_id, generation, utc_now()),
                )
                conn.execute(
                    "INSERT INTO pilot_scope_attempts "
                    "VALUES (?, ?, ?, ?, ?, 'reserved', ?)",
                    (
                        run_id,
                        project_id,
                        task_id,
                        resource_id,
                        generation,
                        utc_now(),
                    ),
                )
            except BaseException:
                conn.rollback()
                raise
            conn.commit()

    def attach_task_attempt(self, task_id: str, run_id: str) -> None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute(
                "UPDATE pilot_scope_task_reservations SET status = 'attached' "
                "WHERE task_id = ? AND status = 'reserved'",
                (task_id,),
            )
            attempt = conn.execute(
                "UPDATE pilot_scope_attempts SET status = 'attached' "
                "WHERE run_id = ? AND task_id = ? AND status = 'reserved'",
                (run_id, task_id),
            )
            if task.rowcount != 1 or attempt.rowcount != 1:
                conn.rollback()
                raise PilotScopeError("scope attachment lost its reservation")
            conn.commit()

    def project_for_task(self, task_id: str) -> str:
        return self._project_for("pilot_scope_task_reservations", "task_id", task_id)

    def project_for_run(self, run_id: str) -> str:
        return self._project_for("pilot_scope_attempts", "run_id", run_id)

    def _project_for(self, table: str, field: str, value: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT project_id FROM {table} WHERE {field} = ?",
                (value,),
            ).fetchone()
        if row is None:
            raise PilotScopeError(f"unscoped {field}: {value}")
        return str(row["project_id"])

    def require_run(self, project_id: str, run_id: str) -> None:
        if self.project_for_run(run_id) != project_id:
            raise PilotScopeError("run project scope mismatch")

    def resolve_repository(self, project_id: str, repo_name: str) -> str:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT repository_id FROM pilot_scope_repository_bindings "
                "WHERE project_id = ? AND repo_name = ?",
                (project_id, repo_name),
            ).fetchall()
        if len(rows) != 1:
            raise PilotScopeError("repository binding is missing or ambiguous")
        return str(rows[0]["repository_id"])

    def resolve_worktree(self, project_id: str, worktree_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT root_identity FROM pilot_scope_worktrees "
                "WHERE project_id = ? AND worktree_id = ?",
                (project_id, worktree_id),
            ).fetchone()
        if row is None:
            raise PilotScopeError("worktree project scope mismatch")
        return str(row["root_identity"])

    def bind_external_session(
        self,
        *,
        binding_id: str,
        project_id: str,
        task_id: str,
        run_id: str,
        provider_kind: str,
        provider_session_id: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_external_sessions "
                "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
                (
                    binding_id,
                    project_id,
                    task_id,
                    run_id,
                    provider_kind,
                    provider_session_id,
                    utc_now(),
                ),
            )

    def require_resource(
        self, project_id: str, resource_kind: str, resource_id: str
    ) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM pilot_scope_project_resources binding "
                "JOIN pilot_scope_resources resource "
                "ON resource.resource_id = binding.resource_id "
                "WHERE binding.project_id = ? AND resource.resource_kind = ? "
                "AND resource.resource_id = ?",
                (project_id, resource_kind, resource_id),
            ).fetchone()
        if row is None:
            raise PilotScopeError("resource project scope mismatch")

    def scoped_artifacts(
        self, project_id: str, run: dict[str, Any], runs_root: Path
    ) -> dict[str, Any]:
        self.require_run(project_id, str(run["run_id"]))
        return resolve_output_artifacts(run, runs_root)

    def foreign_key_violations(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("PRAGMA foreign_key_check").fetchall())


class PilotScopedMemoryStore(ProjectMemoryStore):
    """Test-only minimal adapter proving project-first memory deduplication."""

    def __init__(self, db_path: Path, scope: PilotProjectScopeStore):
        self.scope = scope
        super().__init__(db_path)
        with self.connect() as conn:
            _apply_script(conn, MEMORY_SCOPE_SCHEMA)

    def create_scoped(self, project_id: str, record: MemoryRecord) -> MemoryRecord:
        generation = self.scope.project_generation(project_id)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pilot_scope_memory_reservations "
                "VALUES (?, ?, ?, ?, 'reserved', ?)",
                (
                    record.memory_id,
                    project_id,
                    generation,
                    generation,
                    utc_now(),
                ),
            )
        try:
            created = super().create(record)
        except BaseException:
            with self.connect() as conn:
                conn.execute(
                    "DELETE FROM pilot_scope_memory_reservations "
                    "WHERE memory_id = ? AND status = 'reserved'",
                    (record.memory_id,),
                )
            raise
        with self.connect() as conn:
            if created.memory_id == record.memory_id:
                conn.execute(
                    "UPDATE pilot_scope_memory_reservations SET status = 'attached' "
                    "WHERE memory_id = ?",
                    (record.memory_id,),
                )
            else:
                conn.execute(
                    "DELETE FROM pilot_scope_memory_reservations "
                    "WHERE memory_id = ? AND status = 'reserved'",
                    (record.memory_id,),
                )
        return created

    def _find_duplicate(
        self, conn: sqlite3.Connection, record: MemoryRecord
    ) -> str | None:
        binding = conn.execute(
            "SELECT project_id FROM pilot_scope_memory_reservations "
            "WHERE memory_id = ?",
            (record.memory_id,),
        ).fetchone()
        if binding is None:
            raise PilotScopeError("memory has no project reservation")
        project_id = str(binding["project_id"])
        if record.source_kind and record.source_id:
            row = conn.execute(
                "SELECT record.memory_id FROM memory_records record "
                "JOIN pilot_scope_memory_reservations scope "
                "ON scope.memory_id = record.memory_id "
                "WHERE scope.project_id = ? AND record.source_kind = ? "
                "AND record.source_id = ? AND record.archived = 0 LIMIT 1",
                (project_id, record.source_kind, record.source_id),
            ).fetchone()
            if row:
                return str(row["memory_id"])
        row = conn.execute(
            "SELECT record.memory_id FROM memory_records record "
            "JOIN pilot_scope_memory_reservations scope "
            "ON scope.memory_id = record.memory_id "
            "WHERE scope.project_id = ? AND record.content_sha256 = ? "
            "AND record.archived = 0 LIMIT 1",
            (project_id, record.content_sha256),
        ).fetchone()
        return str(row["memory_id"]) if row else None

    def search_scoped(
        self, project_id: str, query: str, *, limit: int = 20
    ) -> list[MemoryRecord]:
        self.scope.project_generation(project_id)
        pattern = like_pattern(query)
        return self._fetch_records(
            "SELECT record.* FROM memory_records record "
            "JOIN pilot_scope_memory_reservations scope "
            "ON scope.memory_id = record.memory_id "
            "WHERE scope.project_id = ? AND scope.status = 'attached' "
            "AND record.archived = 0 "
            "AND (record.title LIKE ? OR record.summary LIKE ? "
            "OR record.content LIKE ? OR record.metadata_json LIKE ?) "
            "ORDER BY record.created_at DESC LIMIT ?",
            [
                project_id,
                pattern,
                pattern,
                pattern,
                pattern,
                max(1, min(limit, 200)),
            ],
        )


class ImmediateHermesSupervisor:
    def execute(self, request: HermesServiceRequest) -> HermesServiceResult:
        now = utc_now()
        return HermesServiceResult(
            run_id=request.run_id,
            request_id=request.request_id,
            session_id=request.session_id,
            operation=request.operation,
            worker_id="pilot-worker",
            worker_process_identity="pilot-process",
            registry_identity=HermesRegistryIdentity(
                generation=SCOPE_GENERATION,
                effective_schema_hash=SCHEMA_HASH,
                active_toolsets=("pilot",),
            ),
            response={"ok": True, "operation": request.operation},
            started_at=now,
            ended_at=now,
        )

    def cancel(self, *, request_id: str, session_id: str, run_id: str) -> bool:
        return False

    def close(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, "ready": True, "state": "ready"}


def _reserve_real_task(
    task_store: TaskStore,
    scope: PilotProjectScopeStore,
    *,
    project_id: str,
    resource_id: str,
    run_id: str,
    request_id: str,
) -> str:
    task_id = make_task_id()
    scope.reserve_task_attempt(
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        resource_id=resource_id,
    )
    task, created = task_store.reserve_task(
        task_id=task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id=request_id,
        request_hash=sha256(request_id.encode("utf-8")).hexdigest(),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref=run_id,
        backend_identity={
            "repo_name": REPO_ALIAS,
            "project_id": project_id,
        },
        workspace_kind="repository",
        workspace_ref=REPO_ALIAS,
    )
    assert created is True
    assert task.task_id == task_id
    return task_id


def _seed_projects(scope: PilotProjectScopeStore, tmp_path: Path) -> tuple[str, str]:
    scope.create_project(PROJECT_ALPHA, "mirror-api-alpha")
    scope.create_project(PROJECT_BETA, "mirror-api-beta")
    repo_alpha = "repository_alpha"
    repo_beta = "repository_beta"
    scope.register_repository(
        PROJECT_ALPHA,
        repo_alpha,
        repo_name=REPO_ALIAS,
        root_identity=str((tmp_path / "alpha" / REPO_ALIAS).resolve()),
    )
    scope.register_repository(
        PROJECT_BETA,
        repo_beta,
        repo_name=REPO_ALIAS,
        root_identity=str((tmp_path / "beta" / REPO_ALIAS).resolve()),
    )
    scope.register_worktree(
        PROJECT_ALPHA,
        repo_alpha,
        "worktree_alpha",
        root_identity=str((tmp_path / "alpha-worktree").resolve()),
        branch_ref="feature/fix-timeout",
    )
    scope.register_worktree(
        PROJECT_BETA,
        repo_beta,
        "worktree_beta",
        root_identity=str((tmp_path / "beta-worktree").resolve()),
        branch_ref="feature/fix-timeout",
    )
    return repo_alpha, repo_beta


def test_sidecar_migration_is_additive_idempotent_and_fail_closed(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    lock_store = OperationLockStore(runs_dir)
    scope = PilotProjectScopeStore(runs_dir)

    # Reapplying the migration is a no-op and incumbent task models still read.
    PilotProjectScopeStore(runs_dir)
    assert set(task_store.schema_state()["tables"]) == set(TASK_TABLE_NAMES)
    assert scope.foreign_key_violations() == []

    with pytest.raises(sqlite3.IntegrityError, match="unscoped task"):
        task_store.reserve_task(
            task_id=make_task_id(),
            task_kind=TaskKind.DURABLE_COMMAND.value,
            controller_request_id="unscoped-task",
            request_hash="a" * 64,
            backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
            backend_executor="executable_profile",
            backend_ref=RUN_ALPHA,
            backend_identity={},
        )
    with pytest.raises(sqlite3.IntegrityError, match="unscoped run"):
        lock_store.store.create_run(
            run_id=RUN_ALPHA,
            repo_name=REPO_ALIAS,
            tool="executable_profile",
            run_dir=runs_dir / RUN_ALPHA,
            input_data={},
        )


def test_real_stores_keep_confusing_projects_isolated(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    locks = OperationLockStore(runs_dir)
    scope = PilotProjectScopeStore(runs_dir)
    repo_alpha, repo_beta = _seed_projects(scope, tmp_path)

    task_alpha = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id=repo_alpha,
        run_id=RUN_ALPHA,
        request_id="request-alpha",
    )
    task_beta = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_BETA,
        resource_id=repo_beta,
        run_id=RUN_BETA,
        request_id="request-beta",
    )
    for run_id, task_id, project_id in (
        (RUN_ALPHA, task_alpha, PROJECT_ALPHA),
        (RUN_BETA, task_beta, PROJECT_BETA),
    ):
        locks.store.create_run(
            run_id=run_id,
            repo_name=REPO_ALIAS,
            tool="executable_profile",
            run_dir=runs_dir / run_id,
            input_data={
                "repo_name": REPO_ALIAS,
                "objective": "Fix service/api.py timeout",
            },
        )
        scope.attach_task_attempt(task_id, run_id)
        locks.store.update_run(
            run_id,
            worker_pid=1001 if project_id == PROJECT_ALPHA else 1002,
            worker_identity=(
                "1001:windows:alpha"
                if project_id == PROJECT_ALPHA
                else "1002:windows:beta"
            ),
        )

    assert scope.project_for_task(task_alpha) == PROJECT_ALPHA
    assert scope.project_for_task(task_beta) == PROJECT_BETA
    assert scope.project_for_run(RUN_ALPHA) == PROJECT_ALPHA
    assert scope.project_for_run(RUN_BETA) == PROJECT_BETA
    assert scope.resolve_repository(PROJECT_ALPHA, REPO_ALIAS) == repo_alpha
    assert scope.resolve_repository(PROJECT_BETA, REPO_ALIAS) == repo_beta
    assert scope.resolve_worktree(PROJECT_ALPHA, "worktree_alpha").endswith(
        "alpha-worktree"
    )
    with pytest.raises(PilotScopeError, match="worktree project scope mismatch"):
        scope.resolve_worktree(PROJECT_BETA, "worktree_alpha")

    with pytest.raises(sqlite3.IntegrityError, match="cross-project task link"):
        task_store.add_link(
            task_alpha,
            link_type=TaskLinkType.RELATED,
            target_kind=TaskLinkTargetKind.TASK,
            target_id=task_beta,
        )

    first = locks.acquire(
        repo_name=REPO_ALIAS,
        tool="executable_profile",
        normalized_input={"repo_name": REPO_ALIAS},
        run_id=RUN_ALPHA,
    )
    second = locks.acquire(
        repo_name=REPO_ALIAS,
        tool="executable_profile",
        normalized_input={"repo_name": REPO_ALIAS},
        run_id=RUN_BETA,
    )
    assert first.acquired is True
    assert second.acquired is False
    assert second.duplicate is True
    assert locks.release(REPO_ALIAS, RUN_ALPHA) is True
    assert (
        locks.acquire(
            repo_name=REPO_ALIAS,
            tool="executable_profile",
            normalized_input={"repo_name": REPO_ALIAS},
            run_id=RUN_BETA,
        ).acquired
        is True
    )


def test_memory_deduplication_and_retrieval_are_project_first(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    OperationLockStore(runs_dir)
    scope = PilotProjectScopeStore(runs_dir)
    _seed_projects(scope, tmp_path)
    memory = PilotScopedMemoryStore(tmp_path / "memory.sqlite3", scope)

    alpha = memory.create_scoped(
        PROJECT_ALPHA,
        MemoryRecord(
            memory_type=MemoryType.DECISION,
            title="Timeout decision",
            content="service/api.py uses a 30 second timeout",
            source_kind="file",
            source_id="service/api.py",
        ),
    )
    beta = memory.create_scoped(
        PROJECT_BETA,
        MemoryRecord(
            memory_type=MemoryType.DECISION,
            title="Timeout decision",
            content="service/api.py uses a 30 second timeout",
            source_kind="file",
            source_id="service/api.py",
        ),
    )

    assert alpha.memory_id != beta.memory_id
    assert [
        item.memory_id for item in memory.search_scoped(PROJECT_ALPHA, "timeout")
    ] == [alpha.memory_id]
    assert [
        item.memory_id for item in memory.search_scoped(PROJECT_BETA, "timeout")
    ] == [beta.memory_id]
    # The incumbent raw API remains global, proving why worker paths need the
    # scoped adapter rather than post-filtering its result.
    assert {item.memory_id for item in memory.search("timeout").records} == {
        alpha.memory_id,
        beta.memory_id,
    }
    with pytest.raises(PilotScopeError, match="memory has no project reservation"):
        ProjectMemoryStore.create(
            memory,
            MemoryRecord(
                memory_type=MemoryType.STATIC,
                title="Unscoped",
                content="must fail",
            ),
        )


def test_evidence_credentials_and_projection_inherit_exact_scope(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    locks = OperationLockStore(runs_dir)
    scope = PilotProjectScopeStore(runs_dir)
    repo_alpha, _ = _seed_projects(scope, tmp_path)
    task_id = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id=repo_alpha,
        run_id=RUN_ALPHA,
        request_id="request-evidence",
    )
    run_dir = runs_dir / RUN_ALPHA
    run_dir.mkdir(parents=True)
    run = locks.store.create_run(
        run_id=RUN_ALPHA,
        repo_name=REPO_ALIAS,
        tool="executable_profile",
        run_dir=run_dir,
        input_data={"repo_name": REPO_ALIAS},
    )
    scope.attach_task_attempt(task_id, RUN_ALPHA)
    (run_dir / "stdout.txt").write_text("alpha evidence", encoding="utf-8")
    (run_dir / "stderr.txt").write_text("", encoding="utf-8")

    artifacts = scope.scoped_artifacts(PROJECT_ALPHA, run, runs_dir)
    assert artifacts["stdout"].path.read_text(encoding="utf-8") == "alpha evidence"
    with pytest.raises(PilotScopeError, match="run project scope mismatch"):
        scope.scoped_artifacts(PROJECT_BETA, run, runs_dir)

    scope.register_resource(
        resource_id="credential_alpha",
        resource_kind="credential",
        opaque_ref="credential-ref",
        identity="credential-alpha",
    )
    scope.bind_resource(PROJECT_ALPHA, "credential_alpha")
    scope.require_resource(PROJECT_ALPHA, "credential", "credential_alpha")
    with pytest.raises(PilotScopeError, match="resource project scope mismatch"):
        scope.require_resource(PROJECT_BETA, "credential", "credential_alpha")
    scope.bind_resource(PROJECT_BETA, "credential_alpha", access_mode="shared")
    scope.require_resource(PROJECT_BETA, "credential", "credential_alpha")

    task = task_store.get_task(task_id)
    projection = compact_task_status(
        task,
        observation=None,
        open_checkpoint_count=0,
        link_counts={"backend_run": 1},
    )
    projection["project_id"] = PROJECT_ALPHA
    projection["scope_generation"] = SCOPE_GENERATION
    finalize(projection)
    assert projection["response_bytes"] == response_bytes(projection)
    assert projection["response_bytes"] <= TASK_RESPONSE_BUDGET_BYTES

    incumbent = TaskDurableCommandStart.model_validate(
        {
            "operation": "start",
            "controller_request_id": "incumbent-client",
            "repo_name": REPO_ALIAS,
        }
    )
    assert incumbent.repo_name == REPO_ALIAS
    with pytest.raises(PilotScopeError, match="missing or ambiguous"):
        # The same alias belongs to both projects, so omission cannot select one.
        scope.resolve_repository("", incumbent.repo_name)


def test_hermes_session_and_run_are_bound_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    task_store = TaskStore(runs_dir)
    run_store = OperationLockStore(runs_dir).store
    scope = PilotProjectScopeStore(runs_dir)
    scope.create_project(PROJECT_ALPHA, "hermes-alpha")
    scope.create_project(PROJECT_BETA, "hermes-beta")
    scope.register_resource(
        resource_id="hermes_service",
        resource_kind="service",
        opaque_ref="hermes-service",
        identity="hermes-service-instance",
    )
    scope.bind_resource(PROJECT_ALPHA, "hermes_service", access_mode="shared")
    scope.bind_resource(PROJECT_BETA, "hermes_service", access_mode="shared")
    task_id = _reserve_real_task(
        task_store,
        scope,
        project_id=PROJECT_ALPHA,
        resource_id="hermes_service",
        run_id=RUN_HERMES,
        request_id="request-hermes",
    )
    scope.bind_external_session(
        binding_id="binding-hermes-alpha",
        project_id=PROJECT_ALPHA,
        task_id=task_id,
        run_id=RUN_HERMES,
        provider_kind="hermes",
        provider_session_id="Session-A",
    )
    monkeypatch.setattr(hermes_gateway_module, "_make_run_id", lambda: RUN_HERMES)
    gateway = HermesServiceGateway(
        run_store=run_store,
        runs_dir=runs_dir,
        supervisor_factory=ImmediateHermesSupervisor,
    )
    try:
        response = gateway.execute(
            session_id="Session-A",
            operation="tool_search",
            payload={"query": "fixture"},
            expected_registry_generation=SCOPE_GENERATION,
            expected_schema_hash=SCHEMA_HASH,
        )
        scope.attach_task_attempt(task_id, RUN_HERMES)
        assert response["ok"] is True
        assert scope.project_for_run(response["run_id"]) == PROJECT_ALPHA
        scope.require_run(PROJECT_ALPHA, response["run_id"])
        assert (
            gateway.get_result(run_id=response["run_id"], session_id="Session-A")[
                "status"
            ]
            == "completed"
        )
        with pytest.raises(PilotScopeError, match="run project scope mismatch"):
            scope.require_run(PROJECT_BETA, response["run_id"])
    finally:
        gateway.close()
