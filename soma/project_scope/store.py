"""Durable project, resource, canonical-task, and run-attempt scope authority."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from .models import (
    AttemptBindingStatus,
    ProjectScopeError,
    ProjectScopeMismatch,
    RepositoryBinding,
    ScopeProjection,
    TaskBindingStatus,
    canonical_repository_root,
    repository_identity_hash,
    validate_opaque_id,
)
from .schema import (
    BINDING_TABLE_NAMES,
    PROJECT_SCOPE_SCHEMA_VERSION,
    apply_project_scope_migrations,
    schema_state,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class ProjectScopeStore:
    """Sidecar authority; construction never applies a live migration."""

    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.db_path = self.runs_dir / "soma.sqlite3"

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> list[int]:
        """Explicit schema application. Gate A callers use disposable stores only."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        return apply_project_scope_migrations(self.connect)

    def is_installed(self) -> bool:
        if not self.db_path.exists():
            return False
        conn = sqlite3.connect(
            f"file:{self.db_path.resolve().as_posix()}?mode=ro", uri=True
        )
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'project_scope_settings'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def schema_state(self) -> dict[str, Any]:
        if not self.is_installed():
            return {
                "component": "project_scope",
                "schema_version": 0,
                "target_schema_version": PROJECT_SCOPE_SCHEMA_VERSION,
                "up_to_date": False,
                "tables": [],
                "missing_tables": list(BINDING_TABLE_NAMES),
                "scoped_writes_enabled": False,
                "enforcement_state": "inactive",
            }
        with self._read() as conn:
            state = dict(schema_state(conn))
            row = conn.execute(
                "SELECT scoped_writes_enabled, ever_activated "
                "FROM project_scope_settings "
                "WHERE singleton = 1"
            ).fetchone()
        state["scoped_writes_enabled"] = bool(row and row[0])
        state["enforcement_state"] = self._enforcement_state_from_row(row)
        return state

    def scoped_writes_enabled(self) -> bool:
        return self.enforcement_state() == "enforced"

    def enforcement_state(self) -> str:
        if not self.is_installed():
            return "inactive"
        with self._read() as conn:
            row = conn.execute(
                "SELECT scoped_writes_enabled, ever_activated "
                "FROM project_scope_settings "
                "WHERE singleton = 1"
            ).fetchone()
        return self._enforcement_state_from_row(row)

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Expose one owned immediate transaction for recovery fixtures/tools."""
        with self._transaction() as conn:
            yield conn

    # ------------------------------------------------------------------
    # explicit bootstrap and activation
    # ------------------------------------------------------------------

    def preview_bootstrap(
        self,
        *,
        project_id: str,
        project_key: str,
        resource_id: str,
        repo_name: str,
        repository_root: str | Path,
        access_mode: str = "exclusive",
    ) -> dict[str, Any]:
        self._require_installed()
        validate_opaque_id(project_id, "project_id")
        validate_opaque_id(resource_id, "resource_id")
        if not project_key or len(project_key) > 128:
            raise ProjectScopeError("project_key must be a non-empty string")
        if not repo_name or len(repo_name) > 128:
            raise ProjectScopeError("repo_name must be a non-empty string")
        if access_mode not in {"exclusive", "shared"}:
            raise ProjectScopeError("access_mode must be exclusive or shared")
        root = canonical_repository_root(repository_root)
        identity_hash = repository_identity_hash(root)
        conflicts: list[str] = []
        with self._read() as conn:
            project = conn.execute(
                "SELECT * FROM projects WHERE project_id = ? OR project_key = ?",
                (project_id, project_key),
            ).fetchall()
            for row in project:
                if (
                    str(row["project_id"]) != project_id
                    or str(row["project_key"]) != project_key
                ):
                    conflicts.append("project_identity_conflict")
            resource = conn.execute(
                "SELECT * FROM project_resources "
                "WHERE resource_id = ? OR "
                "(resource_kind = 'repository' AND identity_hash = ?)",
                (resource_id, identity_hash),
            ).fetchall()
            for row in resource:
                if (
                    str(row["resource_id"]) != resource_id
                    or str(row["identity_hash"]) != identity_hash
                ):
                    conflicts.append("repository_identity_conflict")
            resource_bindings = conn.execute(
                "SELECT project_id, access_mode FROM project_resource_bindings "
                "WHERE resource_id = ?",
                (resource_id,),
            ).fetchall()
            for row in resource_bindings:
                same_project = str(row["project_id"]) == project_id
                same_mode = str(row["access_mode"]) == access_mode
                if same_project and not same_mode:
                    conflicts.append("resource_access_mode_conflict")
                elif not same_project and (
                    str(row["access_mode"]) != "shared" or access_mode != "shared"
                ):
                    conflicts.append("resource_exclusivity_conflict")
            binding = conn.execute(
                "SELECT * FROM project_repository_bindings "
                "WHERE project_id = ? AND (resource_id = ? OR repo_name = ?)",
                (project_id, resource_id, repo_name),
            ).fetchall()
            for row in binding:
                if (
                    str(row["resource_id"]) != resource_id
                    or str(row["repo_name"]) != repo_name
                    or str(row["identity_hash"]) != identity_hash
                ):
                    conflicts.append("repository_binding_conflict")
        payload = {
            "project_id": project_id,
            "project_key": project_key,
            "resource_id": resource_id,
            "resource_kind": "repository",
            "repo_name": repo_name,
            "repository_root": root,
            "identity_hash": identity_hash,
            "access_mode": access_mode,
        }
        return {
            "ok": not conflicts,
            "preview": payload,
            "input_hash": sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
            "conflicts": sorted(set(conflicts)),
            "would_apply": not conflicts,
        }

    def apply_bootstrap(self, **kwargs: Any) -> dict[str, Any]:
        preview = self.preview_bootstrap(**kwargs)
        if not preview["ok"]:
            raise ProjectScopeError(
                "Bootstrap conflicts: " + ", ".join(preview["conflicts"])
            )
        item = dict(preview["preview"])
        now = _utc_now()
        with self._transaction() as conn:
            other_bindings = conn.execute(
                "SELECT project_id, access_mode FROM project_resource_bindings "
                "WHERE resource_id = ? AND project_id != ?",
                (item["resource_id"], item["project_id"]),
            ).fetchall()
            if other_bindings and (
                item["access_mode"] != "shared"
                or any(str(row["access_mode"]) != "shared" for row in other_bindings)
            ):
                raise ProjectScopeError(
                    "Repository resource has an exclusive project binding"
                )
            conn.execute(
                "INSERT OR IGNORE INTO projects "
                "(project_id, project_key, lifecycle_state, scope_generation, "
                " created_at, updated_at) VALUES (?, ?, 'active', 1, ?, ?)",
                (item["project_id"], item["project_key"], now, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO project_resources "
                "(resource_id, resource_kind, opaque_ref, identity_hash, created_at) "
                "VALUES (?, 'repository', ?, ?, ?)",
                (
                    item["resource_id"],
                    item["repo_name"],
                    item["identity_hash"],
                    now,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO project_resource_bindings "
                "(project_id, resource_id, access_mode, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    item["project_id"],
                    item["resource_id"],
                    item["access_mode"],
                    now,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO project_repository_bindings "
                "(project_id, resource_id, repo_name, repository_root, "
                " identity_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item["project_id"],
                    item["resource_id"],
                    item["repo_name"],
                    item["repository_root"],
                    item["identity_hash"],
                    now,
                ),
            )
            outcome_hash = self._bootstrap_outcome_hash(conn, item)
            event_id = sha256(
                f"{preview['input_hash']}\0{outcome_hash}\0apply".encode("utf-8")
            ).hexdigest()
            conn.execute(
                "INSERT OR IGNORE INTO project_scope_bootstrap_events "
                "(event_id, input_hash, outcome_hash, applied, created_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (event_id, preview["input_hash"], outcome_hash, now),
            )
        return {
            **preview,
            "applied": True,
            "idempotent": True,
            "outcome_hash": outcome_hash,
            "evidence_event_id": event_id,
        }

    def set_scoped_writes_enabled(self, enabled: bool) -> dict[str, Any]:
        self._require_installed()
        with self._transaction() as conn:
            if enabled:
                count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM project_repository_bindings binding "
                        "JOIN projects project ON project.project_id = binding.project_id "
                        "WHERE project.lifecycle_state = 'active'"
                    ).fetchone()[0]
                )
                if count < 1:
                    raise ProjectScopeError(
                        "Cannot enable scoped writes without an active repository binding"
                    )
            conn.execute(
                "UPDATE project_scope_settings "
                "SET scoped_writes_enabled = ?, "
                "ever_activated = CASE WHEN ? = 1 THEN 1 ELSE ever_activated END, "
                "updated_at = ? WHERE singleton = 1",
                (1 if enabled else 0, 1 if enabled else 0, _utc_now()),
            )
        return {
            "ok": True,
            "scoped_writes_enabled": bool(enabled),
            "enforcement_state": self.enforcement_state(),
        }

    # ------------------------------------------------------------------
    # resolution and exact assertions
    # ------------------------------------------------------------------

    def resolve_repository(
        self,
        *,
        project_id: str = "",
        repo_name: str,
        repository_root: str | Path,
        conn: sqlite3.Connection | None = None,
    ) -> RepositoryBinding:
        root = canonical_repository_root(repository_root)
        identity_hash = repository_identity_hash(root)
        close = conn is None
        owned = conn or self.connect()
        try:
            params: list[Any] = [repo_name, identity_hash]
            sql = (
                "SELECT binding.*, resource_binding.access_mode, "
                "project.scope_generation "
                "FROM project_repository_bindings binding "
                "JOIN project_resource_bindings resource_binding "
                "ON resource_binding.project_id = binding.project_id "
                "AND resource_binding.resource_id = binding.resource_id "
                "JOIN projects project ON project.project_id = binding.project_id "
                "WHERE binding.repo_name = ? COLLATE NOCASE "
                "AND binding.identity_hash = ? "
                "AND project.lifecycle_state = 'active'"
            )
            if project_id:
                validate_opaque_id(project_id, "project_id")
                sql += " AND binding.project_id = ?"
                params.append(project_id)
            rows = owned.execute(sql, params).fetchall()
        finally:
            if close:
                owned.close()
        if not rows:
            detail = f" for project {project_id!r}" if project_id else ""
            raise ProjectScopeError(
                f"No active repository binding{detail} matches {repo_name!r}"
            )
        if len(rows) != 1:
            raise ProjectScopeError(
                f"Repository binding for {repo_name!r} is ambiguous across projects"
            )
        row = rows[0]
        return RepositoryBinding(
            project_id=str(row["project_id"]),
            resource_id=str(row["resource_id"]),
            repo_name=str(row["repo_name"]),
            repository_root=str(row["repository_root"]),
            identity_hash=str(row["identity_hash"]),
            scope_generation=int(row["scope_generation"]),
            access_mode=str(row["access_mode"]),
        )

    def scope_for_task(self, task_id: str) -> ScopeProjection:
        if not self.is_installed():
            return ScopeProjection(binding_status="legacy_unassigned")
        with self._read() as conn:
            row = conn.execute(
                "SELECT task.project_id, task.scope_generation, task.status, "
                "attempt.resource_id, attempt.status AS attempt_status "
                "FROM project_task_reservations task "
                "LEFT JOIN project_run_attempts attempt ON attempt.task_id = task.task_id "
                "WHERE task.task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return ScopeProjection(binding_status="legacy_unassigned")
        return ScopeProjection(
            binding_status=str(row["status"]),
            project_id=str(row["project_id"]),
            resource_id=str(row["resource_id"] or ""),
            scope_generation=int(row["scope_generation"]),
            attempt_status=str(row["attempt_status"] or ""),
        )

    def scope_for_run(self, run_id: str) -> ScopeProjection:
        if not self.is_installed():
            return ScopeProjection(binding_status="legacy_unassigned")
        with self._read() as conn:
            row = conn.execute(
                "SELECT attempt.project_id, attempt.resource_id, "
                "attempt.scope_generation, attempt.status, task.status AS task_status "
                "FROM project_run_attempts attempt "
                "JOIN project_task_reservations task ON task.task_id = attempt.task_id "
                "WHERE attempt.run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return ScopeProjection(binding_status="legacy_unassigned")
        return ScopeProjection(
            binding_status=str(row["task_status"]),
            project_id=str(row["project_id"]),
            resource_id=str(row["resource_id"]),
            scope_generation=int(row["scope_generation"]),
            attempt_status=str(row["status"]),
        )

    def require_task(self, project_id: str, task_id: str) -> ScopeProjection:
        validate_opaque_id(project_id, "project_id")
        scope = self.scope_for_task(task_id)
        if not scope.project_id:
            raise ProjectScopeMismatch(f"Task {task_id!r} is legacy_unassigned")
        if scope.project_id != project_id:
            raise ProjectScopeMismatch("Task project scope mismatch")
        return scope

    def require_task_attempt(
        self, project_id: str, task_id: str, run_id: str
    ) -> ScopeProjection:
        scope = self.require_task(project_id, task_id)
        with self._read() as conn:
            row = conn.execute(
                "SELECT 1 FROM project_run_attempts "
                "WHERE project_id = ? AND task_id = ? AND run_id = ? "
                "AND status != 'quarantined'",
                (project_id, task_id, run_id),
            ).fetchone()
        if row is None:
            raise ProjectScopeMismatch(
                "Task backend reference does not match its scoped run attempt"
            )
        return scope

    def require_run(self, project_id: str, run_id: str) -> ScopeProjection:
        validate_opaque_id(project_id, "project_id")
        scope = self.scope_for_run(run_id)
        if not scope.project_id:
            raise ProjectScopeMismatch(f"Run {run_id!r} is legacy_unassigned")
        if scope.project_id != project_id:
            raise ProjectScopeMismatch("Run project scope mismatch")
        return scope

    # ------------------------------------------------------------------
    # canonical task/run reservations
    # ------------------------------------------------------------------

    def reserve_task_attempt(
        self,
        conn: sqlite3.Connection,
        *,
        binding: RepositoryBinding,
        task_id: str,
        run_id: str,
        parent_task_id: str = "",
    ) -> None:
        validate_opaque_id(task_id, "task_id")
        validate_opaque_id(run_id, "run_id")
        current = self.resolve_repository(
            project_id=binding.project_id,
            repo_name=binding.repo_name,
            repository_root=binding.repository_root,
            conn=conn,
        )
        if current != binding:
            raise ProjectScopeError("Repository binding changed before reservation")
        if parent_task_id:
            parent = conn.execute(
                "SELECT project_id FROM project_task_reservations WHERE task_id = ?",
                (parent_task_id,),
            ).fetchone()
            if parent is None:
                raise ProjectScopeMismatch(
                    "Parent task is legacy_unassigned or does not exist"
                )
            if str(parent["project_id"]) != binding.project_id:
                raise ProjectScopeMismatch("Parent task project scope mismatch")
        now = _utc_now()
        conn.execute(
            "INSERT INTO project_task_reservations "
            "(task_id, project_id, scope_generation, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'reserved', ?, ?)",
            (task_id, binding.project_id, binding.scope_generation, now, now),
        )
        conn.execute(
            "INSERT INTO project_run_attempts "
            "(run_id, project_id, task_id, resource_id, scope_generation, status, "
            " recovery_reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'reserved', '', ?, ?)",
            (
                run_id,
                binding.project_id,
                task_id,
                binding.resource_id,
                binding.scope_generation,
                now,
                now,
            ),
        )

    def require_launchable_attempt(
        self,
        *,
        binding: RepositoryBinding,
        task_id: str,
        run_id: str,
    ) -> None:
        """Revalidate the committed reservation immediately before backend handoff."""
        with self._transaction() as conn:
            setting = conn.execute(
                "SELECT scoped_writes_enabled FROM project_scope_settings "
                "WHERE singleton = 1"
            ).fetchone()
            row = conn.execute(
                "SELECT attempt.project_id, attempt.resource_id, "
                "attempt.scope_generation, attempt.status AS attempt_status, "
                "task.status AS task_status, project.lifecycle_state, "
                "project.scope_generation AS current_generation "
                "FROM project_run_attempts attempt "
                "JOIN project_task_reservations task "
                "ON task.task_id = attempt.task_id "
                "JOIN projects project ON project.project_id = attempt.project_id "
                "JOIN project_repository_bindings repository "
                "ON repository.project_id = attempt.project_id "
                "AND repository.resource_id = attempt.resource_id "
                "WHERE attempt.task_id = ? AND attempt.run_id = ? "
                "AND repository.identity_hash = ?",
                (task_id, run_id, binding.identity_hash),
            ).fetchone()
            if not setting or not bool(setting[0]):
                raise ProjectScopeError("ProjectScope writes were paused before launch")
            if row is None:
                raise ProjectScopeError("Scoped launch reservation is missing")
            if (
                str(row["project_id"]) != binding.project_id
                or str(row["resource_id"]) != binding.resource_id
                or int(row["scope_generation"]) != binding.scope_generation
                or int(row["current_generation"]) != binding.scope_generation
                or str(row["lifecycle_state"]) != "active"
                or str(row["task_status"]) != "attached"
                or str(row["attempt_status"]) != "reserved"
            ):
                raise ProjectScopeError(
                    "Scoped launch reservation is stale or not launchable"
                )

    def attach_task(self, conn: sqlite3.Connection, task_id: str) -> None:
        updated = conn.execute(
            "UPDATE project_task_reservations SET status = 'attached', updated_at = ? "
            "WHERE task_id = ? AND status = 'reserved' "
            "AND EXISTS (SELECT 1 FROM tasks WHERE tasks.task_id = ?)",
            (_utc_now(), task_id, task_id),
        )
        if updated.rowcount != 1:
            raise ProjectScopeError("Task scope attachment lost its reservation")

    def attach_attempt(self, run_id: str) -> bool:
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT status FROM project_run_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ProjectScopeError(f"Run attempt is not reserved: {run_id}")
            if str(row["status"]) == AttemptBindingStatus.ATTACHED.value:
                return False
            run = conn.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise ProjectScopeError("Durable run row is not present")
            updated = conn.execute(
                "UPDATE project_run_attempts "
                "SET status = 'attached', recovery_reason = '', updated_at = ? "
                "WHERE run_id = ? AND status IN ('reserved', 'recovery_pending')",
                (_utc_now(), run_id),
            )
            if updated.rowcount != 1:
                raise ProjectScopeError("Run attempt attachment lost its reservation")
        return True

    def mark_attempt_recovery_pending(self, run_id: str, reason: str) -> bool:
        with self._transaction() as conn:
            updated = conn.execute(
                "UPDATE project_run_attempts "
                "SET status = 'recovery_pending', recovery_reason = ?, updated_at = ? "
                "WHERE run_id = ? AND status = 'reserved'",
                (reason[:256], _utc_now(), run_id),
            )
        return updated.rowcount == 1

    def reconcile_startup(self) -> dict[str, Any]:
        if not self.is_installed():
            return {
                "ok": True,
                "available": False,
                "examined": 0,
                "changed": 0,
                "counts": {},
            }
        counts = {
            "task_quarantined": 0,
            "attempt_recovery_pending": 0,
            "attempt_attached": 0,
            "attempt_quarantined": 0,
            "generation_quarantined": 0,
        }
        examined = 0
        with self._transaction() as conn:
            task_rows = conn.execute(
                "SELECT scope.task_id, scope.project_id, scope.scope_generation, "
                "scope.status, task.task_id AS stored_task_id, "
                "project.scope_generation AS current_generation "
                "FROM project_task_reservations scope "
                "JOIN projects project ON project.project_id = scope.project_id "
                "LEFT JOIN tasks task ON task.task_id = scope.task_id "
                "WHERE scope.status != 'quarantined'"
            ).fetchall()
            for row in task_rows:
                examined += 1
                task_id = str(row["task_id"])
                if int(row["scope_generation"]) != int(row["current_generation"]):
                    self._quarantine_task(conn, task_id, "project_generation_mismatch")
                    counts["generation_quarantined"] += 1
                elif row["stored_task_id"] is None:
                    self._quarantine_task(conn, task_id, "task_row_missing")
                    counts["task_quarantined"] += 1

            attempts = conn.execute(
                "SELECT attempt.run_id, attempt.task_id, attempt.project_id, "
                "attempt.scope_generation, attempt.status, "
                "task.status AS task_status, run.run_id AS stored_run_id, "
                "project.scope_generation AS current_generation, "
                "stored_task.backend_ref AS stored_backend_ref "
                "FROM project_run_attempts attempt "
                "JOIN project_task_reservations task ON task.task_id = attempt.task_id "
                "JOIN projects project ON project.project_id = attempt.project_id "
                "LEFT JOIN tasks stored_task ON stored_task.task_id = attempt.task_id "
                "LEFT JOIN runs run ON run.run_id = attempt.run_id "
                "WHERE attempt.status != 'quarantined'"
            ).fetchall()
            for row in attempts:
                examined += 1
                run_id = str(row["run_id"])
                status = str(row["status"])
                if str(row["task_status"]) == TaskBindingStatus.QUARANTINED.value:
                    continue
                if (
                    row["stored_backend_ref"] is not None
                    and str(row["stored_backend_ref"]) != run_id
                ):
                    self._quarantine_task(
                        conn, str(row["task_id"]), "backend_reference_mismatch"
                    )
                    counts["attempt_quarantined"] += 1
                elif int(row["scope_generation"]) != int(row["current_generation"]):
                    self._quarantine_attempt(
                        conn, run_id, "project_generation_mismatch"
                    )
                    counts["generation_quarantined"] += 1
                elif status in {"reserved", "recovery_pending"}:
                    if row["stored_run_id"] is None:
                        if status == "reserved":
                            conn.execute(
                                "UPDATE project_run_attempts "
                                "SET status = 'recovery_pending', "
                                "recovery_reason = 'run_row_missing', updated_at = ? "
                                "WHERE run_id = ? AND status = 'reserved'",
                                (_utc_now(), run_id),
                            )
                            counts["attempt_recovery_pending"] += 1
                    else:
                        conn.execute(
                            "UPDATE project_run_attempts "
                            "SET status = 'attached', recovery_reason = '', "
                            "updated_at = ? WHERE run_id = ? "
                            "AND status IN ('reserved', 'recovery_pending')",
                            (_utc_now(), run_id),
                        )
                        counts["attempt_attached"] += 1
                elif status == "attached" and row["stored_run_id"] is None:
                    self._quarantine_attempt(conn, run_id, "attached_run_row_missing")
                    counts["attempt_quarantined"] += 1
        return {
            "ok": True,
            "available": True,
            "examined": examined,
            "changed": sum(counts.values()),
            "counts": counts,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def table_counts(self) -> dict[str, int]:
        self._require_installed()
        with self._read() as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in BINDING_TABLE_NAMES
            }

    def _require_installed(self) -> None:
        if not self.is_installed():
            raise ProjectScopeError(
                "ProjectScope schema is inactive; live activation requires Gate B"
            )

    @staticmethod
    def _enforcement_state_from_row(row: sqlite3.Row | None) -> str:
        if row is None or not bool(row[1]):
            return "inactive"
        return "enforced" if bool(row[0]) else "paused"

    @staticmethod
    def _bootstrap_outcome_hash(conn: sqlite3.Connection, item: dict[str, Any]) -> str:
        rows = conn.execute(
            "SELECT project.project_id, project.project_key, "
            "project.scope_generation, resource.resource_id, "
            "resource.identity_hash, binding.access_mode, repo.repo_name, "
            "repo.repository_root "
            "FROM projects project "
            "JOIN project_resource_bindings binding "
            "ON binding.project_id = project.project_id "
            "JOIN project_resources resource "
            "ON resource.resource_id = binding.resource_id "
            "JOIN project_repository_bindings repo "
            "ON repo.project_id = binding.project_id "
            "AND repo.resource_id = binding.resource_id "
            "WHERE project.project_id = ? AND resource.resource_id = ?",
            (item["project_id"], item["resource_id"]),
        ).fetchall()
        if len(rows) != 1:
            raise ProjectScopeError(
                "Bootstrap outcome does not resolve to one exact binding"
            )
        row = dict(rows[0])
        expected = {
            "project_id": item["project_id"],
            "project_key": item["project_key"],
            "scope_generation": 1,
            "resource_id": item["resource_id"],
            "identity_hash": item["identity_hash"],
            "access_mode": item["access_mode"],
            "repo_name": item["repo_name"],
            "repository_root": item["repository_root"],
        }
        if row != expected:
            raise ProjectScopeError(
                "Bootstrap outcome differs from the explicit requested identity"
            )
        return sha256(_canonical_json([row]).encode("utf-8")).hexdigest()

    @staticmethod
    def _quarantine(
        conn: sqlite3.Connection,
        record_kind: str,
        record_id: str,
        reason_code: str,
    ) -> None:
        evidence_hash = sha256(
            _canonical_json(
                {
                    "record_kind": record_kind,
                    "record_id": record_id,
                    "reason_code": reason_code,
                }
            ).encode("utf-8")
        ).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO project_scope_quarantine "
            "(record_kind, record_id, reason_code, evidence_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (record_kind, record_id, reason_code, evidence_hash, _utc_now()),
        )

    def _quarantine_task(
        self, conn: sqlite3.Connection, task_id: str, reason_code: str
    ) -> None:
        now = _utc_now()
        conn.execute(
            "UPDATE project_task_reservations "
            "SET status = 'quarantined', updated_at = ? "
            "WHERE task_id = ? AND status != 'quarantined'",
            (now, task_id),
        )
        conn.execute(
            "UPDATE project_run_attempts "
            "SET status = 'quarantined', recovery_reason = ?, updated_at = ? "
            "WHERE task_id = ? AND status != 'quarantined'",
            (reason_code, now, task_id),
        )
        self._quarantine(conn, "task_reservation", task_id, reason_code)

    def _quarantine_attempt(
        self, conn: sqlite3.Connection, run_id: str, reason_code: str
    ) -> None:
        conn.execute(
            "UPDATE project_run_attempts "
            "SET status = 'quarantined', recovery_reason = ?, updated_at = ? "
            "WHERE run_id = ? AND status != 'quarantined'",
            (reason_code, _utc_now(), run_id),
        )
        self._quarantine(conn, "run_attempt", run_id, reason_code)
