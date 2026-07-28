from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import KnowledgeRecord
from .vault import normalize_text


class KnowledgeCatalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_records (
                    knowledge_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    vault_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    search_text TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, vault_path)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_idempotency
                ON knowledge_records(project_id, idempotency_key)
                WHERE idempotency_key != '';
                CREATE INDEX IF NOT EXISTS idx_knowledge_project_status
                ON knowledge_records(project_id, status);
                CREATE TABLE IF NOT EXISTS knowledge_rebuild_state (
                    project_id TEXT PRIMARY KEY,
                    canonical_count INTEGER NOT NULL,
                    indexed_count INTEGER NOT NULL,
                    malformed_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                -- Derived supersession links, rebuildable from the vault. This
                -- is what makes effective lifecycle state link-derived rather
                -- than dependent on every predecessor file being rewritten.
                CREATE TABLE IF NOT EXISTS knowledge_supersessions (
                    project_id TEXT NOT NULL,
                    successor_id TEXT NOT NULL,
                    superseded_id TEXT NOT NULL,
                    PRIMARY KEY (project_id, successor_id, superseded_id)
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_superseded
                ON knowledge_supersessions(project_id, superseded_id);
                """
            )
            self._add_missing_columns(connection)

    @staticmethod
    def _add_missing_columns(connection: sqlite3.Connection) -> None:
        """Additive migration for catalogs created before generation tracking."""
        existing = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(knowledge_rebuild_state)"
            ).fetchall()
        }
        for column, ddl in (
            ("unadopted_count", "INTEGER NOT NULL DEFAULT 0"),
            ("generation", "INTEGER NOT NULL DEFAULT 0"),
            ("unadopted_paths_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("malformed_paths_json", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE knowledge_rebuild_state ADD COLUMN {column} {ddl}"
                )

    def upsert(self, record: KnowledgeRecord) -> None:
        search_text = normalize_text(
            "\n".join(
                [
                    record.title,
                    record.summary,
                    record.body,
                    " ".join(record.tags),
                    json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                ]
            )
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_records (
                    knowledge_id, project_id, vault_path, status, idempotency_key,
                    search_text, record_json, content_sha256, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    vault_path=excluded.vault_path,
                    status=excluded.status,
                    idempotency_key=excluded.idempotency_key,
                    search_text=excluded.search_text,
                    record_json=excluded.record_json,
                    content_sha256=excluded.content_sha256,
                    updated_at=excluded.updated_at
                """,
                (
                    record.knowledge_id,
                    record.project_id,
                    record.vault_path,
                    record.status,
                    record.idempotency_key,
                    search_text,
                    record.model_dump_json(),
                    record.content_sha256,
                    record.updated_at,
                ),
            )
            self._replace_links(connection, record)
            connection.execute(
                "DELETE FROM knowledge_rebuild_state WHERE project_id = ?",
                (record.project_id,),
            )

    @staticmethod
    def _replace_links(
        connection: sqlite3.Connection, record: KnowledgeRecord
    ) -> None:
        connection.execute(
            "DELETE FROM knowledge_supersessions "
            "WHERE project_id = ? AND successor_id = ?",
            (record.project_id, record.knowledge_id),
        )
        for superseded in record.supersedes_ids:
            connection.execute(
                "INSERT OR IGNORE INTO knowledge_supersessions VALUES (?, ?, ?)",
                (record.project_id, record.knowledge_id, superseded),
            )

    def superseded_ids(self, project_id: str) -> set[str]:
        """Every record this project's successors claim to supersede."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT superseded_id FROM knowledge_supersessions "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return {row["superseded_id"] for row in rows}

    def get(self, project_id: str, knowledge_id: str) -> KnowledgeRecord:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM knowledge_records "
                "WHERE project_id = ? AND knowledge_id = ?",
                (project_id, knowledge_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Knowledge not found: {knowledge_id}")
        return KnowledgeRecord.model_validate_json(row["record_json"])

    def by_idempotency(
        self, project_id: str, idempotency_key: str
    ) -> KnowledgeRecord | None:
        if not idempotency_key:
            return None
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM knowledge_records "
                "WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
        return KnowledgeRecord.model_validate_json(row["record_json"]) if row else None

    def by_path(self, project_id: str, vault_path: str) -> KnowledgeRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM knowledge_records "
                "WHERE project_id = ? AND vault_path = ?",
                (project_id, vault_path),
            ).fetchone()
        return KnowledgeRecord.model_validate_json(row["record_json"]) if row else None

    def search(
        self, project_id: str, query: str, current_only: bool
    ) -> list[KnowledgeRecord]:
        """Match every term in the query, in any order and any position.

        This used to be a single `LIKE %<whole phrase>%`, which meant a natural
        multi-word question found nothing unless the words happened to appear
        contiguously: "semantic" returned the right records while "semantic
        retrieval disabled" returned none, reported as zero results with nothing
        omitted. With semantic retrieval disabled, this is the *production*
        retrieval path, so that behaviour made canonical memory unreachable by
        the way controllers actually ask.

        Term-AND substring matching is deliberately as far as this goes. There
        is no scoring, no stemming, no proximity and no ranking: ordering stays
        stable by recency, and building a retrieval engine here is an explicit
        non-goal of the architecture.
        """
        terms = [term for term in normalize_text(query).split() if term]
        if not terms:
            return []
        clauses = " AND ".join(["search_text LIKE ? ESCAPE '\\'"] * len(terms))
        sql = (
            "SELECT record_json FROM knowledge_records "
            f"WHERE project_id = ? AND ({clauses})"
        )
        parameters: list[object] = [project_id, *(_like(term) for term in terms)]
        if current_only:
            sql += " AND status = 'current'"
        sql += " ORDER BY updated_at DESC, knowledge_id"
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [KnowledgeRecord.model_validate_json(row["record_json"]) for row in rows]

    def replace_project(
        self,
        project_id: str,
        records: list[KnowledgeRecord],
        *,
        canonical_count: int,
        malformed_count: int,
        updated_at: str,
        unadopted_count: int = 0,
        unadopted_paths: list[str] | None = None,
        malformed_paths: list[str] | None = None,
    ) -> None:
        with self.connect() as connection:
            previous = connection.execute(
                "SELECT generation FROM knowledge_rebuild_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            generation = (int(previous["generation"]) if previous else 0) + 1
            connection.execute(
                "DELETE FROM knowledge_records WHERE project_id = ?", (project_id,)
            )
            connection.execute(
                "DELETE FROM knowledge_supersessions WHERE project_id = ?",
                (project_id,),
            )
            for record in records:
                search_text = normalize_text(
                    "\n".join(
                        [
                            record.title,
                            record.summary,
                            record.body,
                            " ".join(record.tags),
                        ]
                    )
                )
                connection.execute(
                    "INSERT INTO knowledge_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.knowledge_id,
                        record.project_id,
                        record.vault_path,
                        record.status,
                        record.idempotency_key,
                        search_text,
                        record.model_dump_json(),
                        record.content_sha256,
                        record.updated_at,
                    ),
                )
                self._replace_links(connection, record)
            connection.execute(
                """
                INSERT INTO knowledge_rebuild_state (
                    project_id, canonical_count, indexed_count, malformed_count,
                    updated_at, unadopted_count, generation,
                    unadopted_paths_json, malformed_paths_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  canonical_count=excluded.canonical_count,
                  indexed_count=excluded.indexed_count,
                  malformed_count=excluded.malformed_count,
                  updated_at=excluded.updated_at,
                  unadopted_count=excluded.unadopted_count,
                  generation=excluded.generation,
                  unadopted_paths_json=excluded.unadopted_paths_json,
                  malformed_paths_json=excluded.malformed_paths_json
                """,
                (
                    project_id,
                    canonical_count,
                    len(records),
                    malformed_count,
                    updated_at,
                    unadopted_count,
                    generation,
                    json.dumps(sorted(unadopted_paths or []), ensure_ascii=False),
                    json.dumps(sorted(malformed_paths or []), ensure_ascii=False),
                ),
            )

    def state(self, project_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM knowledge_rebuild_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()


def _like(value: str) -> str:
    return (
        "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    )
