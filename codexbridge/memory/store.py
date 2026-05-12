from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from codexbridge.local_agent.audit import create_audit_event
from codexbridge.run_store import utc_now

from .models import MemoryRecord, MemorySearchResult, MemoryType
from .redaction import detect_sensitivity, redact_sensitive_text
from .schema import initialize_schema
from .search import like_pattern


class ProjectMemoryStore:
    def __init__(
        self,
        db_path: Path,
        *,
        max_content_bytes: int = 20000,
        redact_sensitive: bool = True,
        block_sensitive: bool = True,
    ):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_content_bytes = max_content_bytes
        self.redact_sensitive = redact_sensitive
        self.block_sensitive = block_sensitive
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            initialize_schema(conn)
            self._append_event(conn, None, "memory_store_initialized", "Memory store initialized", {})

    def schema_version(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return int(row["version"])

    def create(self, record: MemoryRecord) -> MemoryRecord:
        now = utc_now()
        record.created_at = record.created_at or now
        record.updated_at = record.updated_at or now
        record.content = _bounded(record.content, self.max_content_bytes)
        combined = "\n".join([record.title, record.summary, record.content])
        flags = sorted(set(record.sensitivity_flags + detect_sensitivity(combined)))
        if flags and self.block_sensitive:
            raise ValueError(f"Sensitive memory content blocked: {flags}")
        if flags and self.redact_sensitive:
            record.title = redact_sensitive_text(record.title)
            record.summary = redact_sensitive_text(record.summary)
            record.content = redact_sensitive_text(record.content)
        record.sensitivity_flags = flags
        record.content_sha256 = _sha256(record.content)
        record.audit_event_id = record.audit_event_id or create_audit_event(task_id=record.memory_id, action="memory_record_created", message="Memory record created").event_id
        with self.connect() as conn:
            existing = self._find_duplicate(conn, record)
            if existing:
                self._append_event(conn, existing, "memory_import_skipped_duplicate", "Duplicate memory skipped", {"source_kind": record.source_kind, "source_id": record.source_id})
                return self.get(existing)
            with conn:
                conn.execute(
                    """
                    INSERT INTO memory_records (
                        memory_id, memory_type, project_key, repo_name, repo_path, title, summary, content,
                        source_kind, source_id, source_path, artifact_paths_json, confidence, created_at,
                        updated_at, expires_at, supersedes_memory_id, metadata_json, sensitivity_flags_json,
                        content_sha256, audit_event_id, archived
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._record_params(record),
                )
                self._replace_tags(conn, record)
                self._append_event(conn, record.memory_id, "memory_record_created", "Memory record created", {"memory_type": record.memory_type.value})
        return record

    def get(self, memory_id: str) -> MemoryRecord:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM memory_records WHERE memory_id = ?", (memory_id,)).fetchone()
            if row is None:
                raise KeyError(f"Memory not found: {memory_id}")
            tags = [item["tag"] for item in conn.execute("SELECT tag FROM memory_tags WHERE memory_id = ? ORDER BY tag", (memory_id,))]
        return self._row_to_record(row, tags)

    def update(self, memory_id: str, **fields: Any) -> MemoryRecord:
        record = self.get(memory_id)
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = utc_now()
        record.content = _bounded(record.content, self.max_content_bytes)
        flags = sorted(set(detect_sensitivity("\n".join([record.title, record.summary, record.content]))))
        if flags and self.block_sensitive:
            raise ValueError(f"Sensitive memory content blocked: {flags}")
        record.sensitivity_flags = flags
        record.content_sha256 = _sha256(record.content)
        with self.connect() as conn:
            with conn:
                assignments = """
                    memory_type=?, project_key=?, repo_name=?, repo_path=?, title=?, summary=?, content=?,
                    source_kind=?, source_id=?, source_path=?, artifact_paths_json=?, confidence=?, created_at=?,
                    updated_at=?, expires_at=?, supersedes_memory_id=?, metadata_json=?, sensitivity_flags_json=?,
                    content_sha256=?, audit_event_id=?, archived=?
                """
                conn.execute(f"UPDATE memory_records SET {assignments} WHERE memory_id=?", (*self._record_params(record)[1:], memory_id))
                self._replace_tags(conn, record)
                self._append_event(conn, memory_id, "memory_record_updated", "Memory record updated", {})
        return record

    def archive(self, memory_id: str) -> MemoryRecord:
        with self.connect() as conn:
            with conn:
                conn.execute("UPDATE memory_records SET archived = 1, updated_at = ? WHERE memory_id = ?", (utc_now(), memory_id))
                self._append_event(conn, memory_id, "memory_record_archived", "Memory record archived", {})
        return self.get(memory_id)

    def list_records(
        self,
        *,
        project_key: str | None = None,
        repo_name: str | None = None,
        memory_type: MemoryType | str | None = None,
        tag: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        where = []
        params: list[Any] = []
        if not include_archived:
            where.append("r.archived = 0")
        if project_key:
            where.append("r.project_key = ?")
            params.append(project_key)
        if repo_name:
            where.append("r.repo_name = ?")
            params.append(repo_name)
        if memory_type:
            where.append("r.memory_type = ?")
            params.append(memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type))
        join = ""
        if tag:
            join = "JOIN memory_tags t ON r.memory_id = t.memory_id"
            where.append("t.tag = ?")
            params.append(tag)
        sql = f"SELECT r.* FROM memory_records r {join}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        return self._fetch_records(sql, params)

    def search(self, query: str, *, limit: int = 20) -> MemorySearchResult:
        pattern = like_pattern(query)
        records = self._fetch_records(
            """
            SELECT * FROM memory_records
            WHERE archived = 0 AND (title LIKE ? OR summary LIKE ? OR content LIKE ? OR metadata_json LIKE ?)
            ORDER BY created_at DESC LIMIT ?
            """,
            [pattern, pattern, pattern, pattern, max(1, min(limit, 200))],
        )
        with self.connect() as conn:
            self._append_event(conn, None, "memory_search_performed", "Memory search performed", {"query": query, "count": len(records)})
        return MemorySearchResult(records=records, query=query, total=len(records))

    def recent(self, *, limit: int = 20) -> list[MemoryRecord]:
        return self.list_records(limit=limit)

    def latest_by_type(self, memory_type: MemoryType) -> MemoryRecord | None:
        records = self.list_records(memory_type=memory_type, limit=1)
        return records[0] if records else None

    def validation_recipes(self, repo_name: str | None = None) -> list[MemoryRecord]:
        return [record for record in self.list_records(repo_name=repo_name, tag="validation_recipe", limit=100)]

    def known_commands(self, repo_name: str | None = None) -> list[MemoryRecord]:
        return [record for record in self.list_records(repo_name=repo_name, tag="known_command", limit=100)]

    def architecture_notes(self, repo_name: str | None = None) -> list[MemoryRecord]:
        return [record for record in self.list_records(repo_name=repo_name, tag="architecture", limit=100)]

    def _fetch_records(self, sql: str, params: list[Any]) -> list[MemoryRecord]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            tags_by_id = {
                row["memory_id"]: [item["tag"] for item in conn.execute("SELECT tag FROM memory_tags WHERE memory_id = ? ORDER BY tag", (row["memory_id"],))]
                for row in rows
            }
        return [self._row_to_record(row, tags_by_id[row["memory_id"]]) for row in rows]

    def _replace_tags(self, conn: sqlite3.Connection, record: MemoryRecord) -> None:
        conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (record.memory_id,))
        conn.executemany("INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)", [(record.memory_id, tag) for tag in sorted(set(record.tags))])

    def _find_duplicate(self, conn: sqlite3.Connection, record: MemoryRecord) -> str | None:
        if record.source_kind and record.source_id:
            row = conn.execute(
                "SELECT memory_id FROM memory_records WHERE source_kind = ? AND source_id = ? AND archived = 0 LIMIT 1",
                (record.source_kind, record.source_id),
            ).fetchone()
            if row:
                return str(row["memory_id"])
        row = conn.execute(
            "SELECT memory_id FROM memory_records WHERE content_sha256 = ? AND archived = 0 LIMIT 1",
            (record.content_sha256,),
        ).fetchone()
        return str(row["memory_id"]) if row else None

    def _append_event(self, conn: sqlite3.Connection, memory_id: str | None, event_type: str, message: str, data: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO memory_events (memory_id, timestamp, event_type, message, data_json) VALUES (?, ?, ?, ?, ?)",
            (memory_id, utc_now(), event_type, message, json.dumps(data, sort_keys=True)),
        )

    def _record_params(self, record: MemoryRecord) -> tuple[Any, ...]:
        return (
            record.memory_id,
            record.memory_type.value,
            record.project_key,
            record.repo_name,
            str(record.repo_path) if record.repo_path else None,
            record.title,
            record.summary,
            record.content,
            record.source_kind,
            record.source_id,
            str(record.source_path) if record.source_path else None,
            json.dumps([str(path) for path in record.artifact_paths], sort_keys=True),
            record.confidence,
            record.created_at,
            record.updated_at,
            record.expires_at,
            record.supersedes_memory_id,
            json.dumps(record.metadata, sort_keys=True),
            json.dumps(record.sensitivity_flags, sort_keys=True),
            record.content_sha256,
            record.audit_event_id,
            int(record.archived),
        )

    def _row_to_record(self, row: sqlite3.Row, tags: list[str]) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            memory_type=MemoryType(row["memory_type"]),
            project_key=row["project_key"],
            repo_name=row["repo_name"],
            repo_path=Path(row["repo_path"]) if row["repo_path"] else None,
            title=row["title"],
            summary=row["summary"],
            content=row["content"],
            tags=tags,
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            source_path=Path(row["source_path"]) if row["source_path"] else None,
            artifact_paths=[Path(path) for path in json.loads(row["artifact_paths_json"] or "[]")],
            confidence=float(row["confidence"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            supersedes_memory_id=row["supersedes_memory_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            sensitivity_flags=json.loads(row["sensitivity_flags_json"] or "[]"),
            content_sha256=row["content_sha256"],
            audit_event_id=row["audit_event_id"],
            archived=bool(row["archived"]),
        )


def _bounded(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n[truncated]"


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
