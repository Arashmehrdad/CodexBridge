"""Canonical task store.

Authoritative for canonical public task identity, typed links, task commands,
checkpoints, and task events. It is deliberately *not* authoritative for
worker, process, lease, lock, evidence, or result state: those stay in the
existing durable run store, which this store references by opaque identity.

Every ownership-sensitive update is a compare-and-set on ``state_version``.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import (
    TaskCheckpoint,
    TaskCheckpointStatus,
    TaskCommand,
    TaskCommandKind,
    TaskCommandStatus,
    TaskEvent,
    TaskEventLevel,
    TaskLink,
    TaskLinkTargetKind,
    TaskLinkType,
    TaskPhase,
    TaskRecord,
    TaskRecoveryState,
    TaskState,
    TERMINAL_TASK_STATES,
    make_checkpoint_id,
    make_command_id,
    utc_now,
    validate_task_id,
)
from .schema import (
    apply_task_migrations,
    current_schema_version,
    schema_state,
)


_UPDATABLE_TASK_FIELDS = frozenset(
    {
        "state",
        "phase",
        "backend_ref",
        "backend_executor",
        "backend_identity_json",
        "objective_ref",
        "constraints_ref",
        "workspace_kind",
        "workspace_ref",
        "checkpoint_ref",
        "result_ref",
        "result_hash",
        "evidence_ref",
        "recovery_state",
        "recovery_reason",
        "reconciled_at",
        "started_at",
        "ended_at",
    }
)


class TaskRequestConflict(ValueError):
    """Same controller request ID replayed with a different normalized request."""

    def __init__(self, task: TaskRecord, submitted_hash: str) -> None:
        super().__init__(
            "controller_request_id "
            f"{task.controller_request_id!r} is already bound to task "
            f"{task.task_id} with a different normalized request hash"
        )
        self.task = task
        self.submitted_hash = submitted_hash


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}


class TaskStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "soma.sqlite3"
        self.init_db()

    # ------------------------------------------------------------------
    # connections and schema
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> list[int]:
        return apply_task_migrations(self.connect)

    def schema_version(self) -> int:
        with self._read() as conn:
            return current_schema_version(conn)

    def schema_state(self) -> dict[str, Any]:
        with self._read() as conn:
            return dict(schema_state(conn))

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
        """Public shared-main-store transaction for narrow sidecar coordination."""
        with self._transaction() as conn:
            yield conn

    # ------------------------------------------------------------------
    # row mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> TaskRecord:
        data = dict(row)
        data["backend_identity"] = _loads(data.pop("backend_identity_json", "{}"))
        return TaskRecord.model_validate(data)

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> TaskLink:
        data = dict(row)
        data["metadata"] = _loads(data.pop("metadata_json", "{}"))
        return TaskLink.model_validate(data)

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> TaskEvent:
        data = dict(row)
        data["data"] = _loads(data.pop("data_json", "{}"))
        return TaskEvent.model_validate(data)

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> TaskRecord:
        validate_task_id(task_id)
        with self._read() as conn:
            return self.get_task_in_connection(conn, task_id)

    def get_task_in_connection(
        self, conn: sqlite3.Connection, task_id: str
    ) -> TaskRecord:
        """Read one task inside an existing shared main-store transaction."""
        validate_task_id(task_id)
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Task not found: {task_id}")
        return self._row_to_task(row)

    def find_by_controller_request(
        self, controller_request_id: str
    ) -> TaskRecord | None:
        with self._read() as conn:
            return self.find_by_controller_request_in_connection(
                conn, controller_request_id
            )

    def find_by_controller_request_in_connection(
        self, conn: sqlite3.Connection, controller_request_id: str
    ) -> TaskRecord | None:
        row = conn.execute(
            "SELECT * FROM tasks WHERE controller_request_id = ?",
            (controller_request_id,),
        ).fetchone()
        return None if row is None else self._row_to_task(row)

    def find_by_backend_ref(
        self, backend_kind: str, backend_ref: str
    ) -> TaskRecord | None:
        if not backend_ref:
            return None
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE backend_kind = ? AND backend_ref = ?",
                (backend_kind, backend_ref),
            ).fetchone()
        return None if row is None else self._row_to_task(row)

    def list_active_tasks(self, limit: int = 500) -> list[TaskRecord]:
        terminal = sorted(state.value for state in TERMINAL_TASK_STATES)
        placeholders = ", ".join("?" for _ in terminal)
        with self._read() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE state NOT IN ({placeholders}) "
                "ORDER BY created_at ASC LIMIT ?",
                (*terminal, int(limit)),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_links(self, task_id: str, limit: int = 200) -> list[TaskLink]:
        validate_task_id(task_id)
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM task_links WHERE task_id = ? ORDER BY id ASC LIMIT ?",
                (task_id, int(limit)),
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def list_events(
        self, task_id: str, *, limit: int = 20, after_id: int | None = None
    ) -> list[TaskEvent]:
        validate_task_id(task_id)
        sql = "SELECT * FROM task_events WHERE task_id = ?"
        params: list[Any] = [task_id]
        if after_id is not None:
            sql += " AND id > ?"
            params.append(int(after_id))
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(int(limit))
        with self._read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def latest_event_id(self, task_id: str) -> int:
        validate_task_id(task_id)
        with self._read() as conn:
            row = conn.execute(
                "SELECT MAX(id) FROM task_events WHERE task_id = ?", (task_id,)
            ).fetchone()
        return int(row[0] or 0)

    def list_commands(self, task_id: str, limit: int = 50) -> list[TaskCommand]:
        validate_task_id(task_id)
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM task_commands WHERE task_id = ? "
                "ORDER BY created_at ASC, command_id ASC LIMIT ?",
                (task_id, int(limit)),
            ).fetchall()
        return [TaskCommand.model_validate(dict(row)) for row in rows]

    def open_checkpoint_count(self, task_id: str) -> int:
        validate_task_id(task_id)
        with self._read() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM task_checkpoints "
                "WHERE task_id = ? AND status = ?",
                (task_id, TaskCheckpointStatus.OPEN.value),
            ).fetchone()
        return int(row[0] or 0)

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------

    def reserve_task(
        self,
        *,
        task_id: str,
        task_kind: str,
        controller_request_id: str,
        request_hash: str,
        backend_kind: str,
        backend_executor: str,
        backend_ref: str,
        backend_identity: dict[str, Any],
        objective_ref: str = "",
        constraints_ref: str = "",
        workspace_kind: str = "",
        workspace_ref: str = "",
        parent_task_id: str = "",
        state: str = TaskState.ACCEPTED.value,
        phase: str = TaskPhase.BACKEND_RESERVED.value,
    ) -> tuple[TaskRecord, bool]:
        """Create the task, or return the existing task for a replayed request.

        The whole decision happens in one immediate transaction, so two
        concurrent identical requests cannot both create a task and cannot both
        reserve a backend reference.
        """
        validate_task_id(task_id)
        with self._transaction() as conn:
            return self.reserve_task_in_connection(
                conn,
                task_id=task_id,
                task_kind=task_kind,
                controller_request_id=controller_request_id,
                request_hash=request_hash,
                backend_kind=backend_kind,
                backend_executor=backend_executor,
                backend_ref=backend_ref,
                backend_identity=backend_identity,
                objective_ref=objective_ref,
                constraints_ref=constraints_ref,
                workspace_kind=workspace_kind,
                workspace_ref=workspace_ref,
                parent_task_id=parent_task_id,
                state=state,
                phase=phase,
            )

    def reserve_task_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        task_kind: str,
        controller_request_id: str,
        request_hash: str,
        backend_kind: str,
        backend_executor: str,
        backend_ref: str,
        backend_identity: dict[str, Any],
        objective_ref: str = "",
        constraints_ref: str = "",
        workspace_kind: str = "",
        workspace_ref: str = "",
        parent_task_id: str = "",
        state: str = TaskState.ACCEPTED.value,
        phase: str = TaskPhase.BACKEND_RESERVED.value,
    ) -> tuple[TaskRecord, bool]:
        """Connection-scoped insert used by the ProjectScope coordinator."""
        validate_task_id(task_id)
        existing = self.find_by_controller_request_in_connection(
            conn, controller_request_id
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise TaskRequestConflict(existing, request_hash)
            return existing, False
        now = utc_now()
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, parent_task_id, task_kind, controller_request_id,
                request_hash, objective_ref, constraints_ref, backend_kind,
                backend_executor, backend_ref, backend_identity_json,
                workspace_kind, workspace_ref, state, phase, state_version,
                checkpoint_ref, result_ref, result_hash, evidence_ref,
                recovery_state, recovery_reason, reconciled_at,
                created_at, updated_at, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                      '', '', '', ?, ?, '', NULL, ?, ?, NULL, NULL)
            """,
            (
                task_id,
                parent_task_id,
                task_kind,
                controller_request_id,
                request_hash,
                objective_ref,
                constraints_ref,
                backend_kind,
                backend_executor,
                backend_ref,
                _dumps(backend_identity),
                workspace_kind,
                workspace_ref,
                state,
                phase,
                "",
                TaskRecoveryState.NONE.value,
                now,
                now,
            ),
        )
        if backend_ref:
            self._insert_link(
                conn,
                task_id=task_id,
                link_type=TaskLinkType.BACKEND_RUN.value,
                target_kind=TaskLinkTargetKind.DURABLE_RUN.value,
                target_id=backend_ref,
                metadata={
                    "backend_kind": backend_kind,
                    "backend_executor": backend_executor,
                },
                now=now,
            )
        if parent_task_id:
            self._insert_link(
                conn,
                task_id=task_id,
                link_type=TaskLinkType.PARENT.value,
                target_kind=TaskLinkTargetKind.TASK.value,
                target_id=parent_task_id,
                metadata={},
                now=now,
            )
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return self._row_to_task(row), True

    @staticmethod
    def _insert_link(
        conn: sqlite3.Connection,
        *,
        task_id: str,
        link_type: str,
        target_kind: str,
        target_id: str,
        metadata: dict[str, Any],
        now: str,
    ) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO task_links "
            "(task_id, link_type, target_kind, target_id, created_at, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, link_type, target_kind, target_id, now, _dumps(metadata)),
        )

    def add_link(
        self,
        task_id: str,
        *,
        link_type: TaskLinkType,
        target_kind: TaskLinkTargetKind,
        target_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        validate_task_id(task_id)
        with self._transaction() as conn:
            self._insert_link(
                conn,
                task_id=task_id,
                link_type=link_type.value,
                target_kind=target_kind.value,
                target_id=target_id,
                metadata=metadata or {},
                now=utc_now(),
            )

    def conditional_update_in_connection(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        *,
        fields: dict[str, Any],
        expected_state_version: int,
        expected_states: tuple[str, ...] | None = None,
        bump_state_version: bool = True,
    ) -> TaskRecord | None:
        """Compare-and-set one task inside an existing shared transaction."""
        validate_task_id(task_id)
        unknown = set(fields) - _UPDATABLE_TASK_FIELDS
        if unknown:
            raise ValueError(f"Unsupported task update fields: {sorted(unknown)}")
        assignments = ", ".join(f"{name} = ?" for name in sorted(fields))
        params: list[Any] = [fields[name] for name in sorted(fields)]
        sql = f"UPDATE tasks SET {assignments}, updated_at = ?"
        params.append(utc_now())
        if bump_state_version:
            sql += ", state_version = state_version + 1"
        sql += " WHERE task_id = ? AND state_version = ?"
        params.extend([task_id, int(expected_state_version)])
        if expected_states:
            placeholders = ", ".join("?" for _ in expected_states)
            sql += f" AND state IN ({placeholders})"
            params.extend(expected_states)
        cursor = conn.execute(sql, params)
        if cursor.rowcount != 1:
            return None
        return self.get_task_in_connection(conn, task_id)

    def conditional_update(
        self,
        task_id: str,
        *,
        fields: dict[str, Any],
        expected_state_version: int,
        expected_states: tuple[str, ...] | None = None,
        bump_state_version: bool = True,
    ) -> TaskRecord | None:
        """Compare-and-set update. Returns ``None`` when the guard did not hold."""
        with self._transaction() as conn:
            return self.conditional_update_in_connection(
                conn,
                task_id,
                fields=fields,
                expected_state_version=expected_state_version,
                expected_states=expected_states,
                bump_state_version=bump_state_version,
            )

    def append_event_in_connection(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        *,
        level: TaskEventLevel,
        stage: str,
        message: str,
        state: str = "",
        state_version: int = 0,
        data: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> TaskEvent:
        validate_task_id(task_id)
        now = timestamp or utc_now()
        cursor = conn.execute(
            "INSERT INTO task_events "
            "(task_id, timestamp, level, stage, message, state, state_version, data_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                now,
                level.value,
                stage,
                message,
                state,
                int(state_version),
                _dumps(data or {}),
            ),
        )
        return TaskEvent(
            id=int(cursor.lastrowid or 0),
            task_id=task_id,
            timestamp=now,
            level=level,
            stage=stage,
            message=message,
            state=state,
            state_version=int(state_version),
            data=dict(data or {}),
        )

    def append_event(
        self,
        task_id: str,
        *,
        level: TaskEventLevel,
        stage: str,
        message: str,
        state: str = "",
        state_version: int = 0,
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        with self._transaction() as conn:
            return self.append_event_in_connection(
                conn,
                task_id,
                level=level,
                stage=stage,
                message=message,
                state=state,
                state_version=state_version,
                data=data,
            )

    def find_command_by_controller_request_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        command_kind: TaskCommandKind,
        controller_request_id: str,
    ) -> TaskCommand | None:
        validate_task_id(task_id)
        if not controller_request_id:
            return None
        row = conn.execute(
            "SELECT * FROM task_commands WHERE task_id = ? AND command_kind = ? "
            "AND controller_request_id = ?",
            (task_id, command_kind.value, controller_request_id),
        ).fetchone()
        return None if row is None else TaskCommand.model_validate(dict(row))

    def reserve_command_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        command_kind: TaskCommandKind,
        requested_state_version: int,
        observed_state_version: int,
        status: TaskCommandStatus,
        controller_request_id: str,
        reason: str = "",
    ) -> tuple[TaskCommand, bool]:
        """Reserve one canonical command inside a shared main-store transaction."""
        validate_task_id(task_id)
        existing = self.find_command_by_controller_request_in_connection(
            conn,
            task_id=task_id,
            command_kind=command_kind,
            controller_request_id=controller_request_id,
        )
        if existing is not None:
            submitted = (
                int(requested_state_version),
                int(observed_state_version),
            )
            durable = (
                existing.requested_state_version,
                existing.observed_state_version,
            )
            if submitted != durable:
                raise ValueError(
                    "controller_request_id is already bound to a command with "
                    "different state-version identity"
                )
            return existing, False

        command_id = make_command_id()
        now = utc_now()
        completed_at = (
            now
            if status
            in {
                TaskCommandStatus.COMPLETED,
                TaskCommandStatus.FAILED,
                TaskCommandStatus.REJECTED_STALE_VERSION,
            }
            else None
        )
        conn.execute(
            "INSERT INTO task_commands "
            "(command_id, task_id, command_kind, controller_request_id, "
            " requested_state_version, observed_state_version, status, reason, "
            " created_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                command_id,
                task_id,
                command_kind.value,
                controller_request_id,
                int(requested_state_version),
                int(observed_state_version),
                status.value,
                reason,
                now,
                completed_at,
            ),
        )
        return (
            TaskCommand(
                command_id=command_id,
                task_id=task_id,
                command_kind=command_kind,
                controller_request_id=controller_request_id,
                requested_state_version=int(requested_state_version),
                observed_state_version=int(observed_state_version),
                status=status,
                reason=reason,
                created_at=now,
                completed_at=completed_at,
            ),
            True,
        )

    def record_command(
        self,
        task_id: str,
        *,
        command_kind: TaskCommandKind,
        requested_state_version: int,
        observed_state_version: int,
        status: TaskCommandStatus,
        controller_request_id: str = "",
        reason: str = "",
    ) -> TaskCommand:
        with self._transaction() as conn:
            command, _created = self.reserve_command_in_connection(
                conn,
                task_id=task_id,
                command_kind=command_kind,
                requested_state_version=requested_state_version,
                observed_state_version=observed_state_version,
                status=status,
                controller_request_id=controller_request_id,
                reason=reason,
            )
        return command

    def complete_command_in_connection(
        self,
        conn: sqlite3.Connection,
        command_id: str,
        *,
        status: TaskCommandStatus,
        reason: str = "",
        completed_at: str | None = None,
    ) -> TaskCommand:
        """Complete one exact canonical command inside a shared transaction."""
        row = conn.execute(
            "SELECT * FROM task_commands WHERE command_id = ?", (command_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Task command not found: {command_id}")
        existing = TaskCommand.model_validate(dict(row))
        terminal = {
            TaskCommandStatus.COMPLETED,
            TaskCommandStatus.FAILED,
            TaskCommandStatus.REJECTED_STALE_VERSION,
        }
        if existing.status in terminal:
            if existing.status is not status:
                raise ValueError(
                    f"terminal task command {command_id} is {existing.status.value}, "
                    f"not {status.value}"
                )
            return existing
        now = completed_at or utc_now()
        cursor = conn.execute(
            "UPDATE task_commands SET status = ?, reason = ?, completed_at = ? "
            "WHERE command_id = ? AND status = ?",
            (
                status.value,
                reason,
                now,
                command_id,
                existing.status.value,
            ),
        )
        if int(cursor.rowcount) != 1:
            raise ValueError(f"task command changed during completion: {command_id}")
        updated = conn.execute(
            "SELECT * FROM task_commands WHERE command_id = ?", (command_id,)
        ).fetchone()
        return TaskCommand.model_validate(dict(updated))

    def complete_command(
        self,
        command_id: str,
        *,
        status: TaskCommandStatus,
        reason: str = "",
    ) -> None:
        with self._transaction() as conn:
            self.complete_command_in_connection(
                conn,
                command_id,
                status=status,
                reason=reason,
            )

    def get_checkpoint_in_connection(
        self, conn: sqlite3.Connection, checkpoint_id: str
    ) -> TaskCheckpoint:
        row = conn.execute(
            "SELECT * FROM task_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Checkpoint not found: {checkpoint_id}")
        data = dict(row)
        data["expected_input_schema"] = _loads(
            data.pop("expected_input_schema_json", "{}")
        )
        return TaskCheckpoint.model_validate(data)

    def resolve_checkpoint_in_connection(
        self,
        conn: sqlite3.Connection,
        checkpoint_id: str,
        *,
        task_id: str,
        required_state_version: int,
        resolved_at: str | None = None,
    ) -> TaskCheckpoint:
        """Resolve one exact open checkpoint inside a shared transaction."""
        checkpoint = self.get_checkpoint_in_connection(conn, checkpoint_id)
        if checkpoint.task_id != task_id:
            raise ValueError("checkpoint does not belong to the requested task")
        if checkpoint.required_state_version != int(required_state_version):
            raise ValueError("checkpoint required state version does not match")
        if checkpoint.status is TaskCheckpointStatus.RESOLVED:
            return checkpoint
        if checkpoint.status is not TaskCheckpointStatus.OPEN:
            raise ValueError(
                f"checkpoint {checkpoint_id} is {checkpoint.status.value}, not open"
            )
        now = resolved_at or utc_now()
        cursor = conn.execute(
            "UPDATE task_checkpoints SET status = ?, resolved_at = ? "
            "WHERE checkpoint_id = ? AND task_id = ? AND status = ? "
            "AND required_state_version = ?",
            (
                TaskCheckpointStatus.RESOLVED.value,
                now,
                checkpoint_id,
                task_id,
                TaskCheckpointStatus.OPEN.value,
                int(required_state_version),
            ),
        )
        if int(cursor.rowcount) != 1:
            raise ValueError(f"checkpoint changed during resolution: {checkpoint_id}")
        return self.get_checkpoint_in_connection(conn, checkpoint_id)

    def create_checkpoint_in_connection(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        *,
        checkpoint_id: str,
        kind: str,
        required_state_version: int,
        prompt: str = "",
        expected_input_schema: dict[str, Any] | None = None,
        context_ref: str = "",
        evidence_ref: str = "",
        created_at: str | None = None,
    ) -> TaskCheckpoint:
        validate_task_id(task_id)
        now = created_at or utc_now()
        conn.execute(
            "INSERT INTO task_checkpoints "
            "(checkpoint_id, task_id, kind, prompt, expected_input_schema_json, "
            " context_ref, evidence_ref, required_state_version, status, "
            " created_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                checkpoint_id,
                task_id,
                kind,
                prompt,
                _dumps(expected_input_schema or {}),
                context_ref,
                evidence_ref,
                int(required_state_version),
                TaskCheckpointStatus.OPEN.value,
                now,
            ),
        )
        return self.get_checkpoint_in_connection(conn, checkpoint_id)

    def create_checkpoint(
        self,
        task_id: str,
        *,
        kind: str,
        required_state_version: int,
        prompt: str = "",
        expected_input_schema: dict[str, Any] | None = None,
        context_ref: str = "",
        evidence_ref: str = "",
    ) -> TaskCheckpoint:
        checkpoint_id = make_checkpoint_id()
        with self._transaction() as conn:
            return self.create_checkpoint_in_connection(
                conn,
                task_id,
                checkpoint_id=checkpoint_id,
                kind=kind,
                required_state_version=required_state_version,
                prompt=prompt,
                expected_input_schema=expected_input_schema,
                context_ref=context_ref,
                evidence_ref=evidence_ref,
            )
