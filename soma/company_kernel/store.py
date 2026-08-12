"""Schema-only facade for the inactive Company Kernel v2 component.

Constructing this class does not touch the filesystem or database. The sole
write operation is explicit additive schema migration; there are deliberately
no Company, Mission, plan, package, attempt, acceptance, or reconciliation
actions in this gate.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import COMPANY_KERNEL_SCHEMA_VERSION
from .schema import (
    COMPANY_KERNEL_INDEX_NAMES,
    COMPANY_KERNEL_TABLE_NAMES,
    COMPANY_KERNEL_TRIGGER_NAMES,
    apply_company_kernel_migrations,
    schema_state,
)


class CompanyKernelStore:
    """Offline schema inspection and migration entry point; runtime stays inactive."""

    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.db_path = self.runs_dir / "soma.sqlite3"

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _read_only(self) -> Iterator[sqlite3.Connection]:
        uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def is_installed(self) -> bool:
        if not self.db_path.exists():
            return False
        try:
            with self._read_only() as conn:
                return bool(schema_state(conn)["up_to_date"])
        except sqlite3.Error:
            return False

    def schema_state(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return self._absent_state()
        try:
            with self._read_only() as conn:
                return dict(schema_state(conn))
        except sqlite3.Error:
            return self._absent_state()

    def init_db(self) -> list[int]:
        """Apply dependencies and the additive kernel migration explicitly.

        The dependency constructors/migrations are existing idempotent schema
        authorities. This method is intended for controlled migration proof and
        a later explicit activation gate; importing or constructing the store
        never invokes it.
        """
        from soma.project_scope.store import ProjectScopeStore
        from soma.run_store import RunStore
        from soma.tasks.store import TaskStore

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        RunStore(self.runs_dir)
        TaskStore(self.runs_dir)
        ProjectScopeStore(self.runs_dir).init_db()
        return apply_company_kernel_migrations(self.connect)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Own one immediate Company Kernel transaction on the shared database."""
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

    def table_counts(self) -> dict[str, int]:
        if not self.is_installed():
            return {name: 0 for name in COMPANY_KERNEL_TABLE_NAMES}
        with self._read_only() as conn:
            return {
                name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                for name in COMPANY_KERNEL_TABLE_NAMES
            }

    @staticmethod
    def _absent_state() -> dict[str, Any]:
        return {
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
