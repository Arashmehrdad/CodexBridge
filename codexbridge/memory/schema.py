from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1


def initialize_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                project_key TEXT NOT NULL,
                repo_name TEXT,
                repo_path TEXT,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_path TEXT,
                artifact_paths_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                supersedes_memory_id TEXT,
                metadata_json TEXT NOT NULL,
                sensitivity_flags_json TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                audit_event_id TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_tags (
                memory_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (memory_id, tag),
                FOREIGN KEY(memory_id) REFERENCES memory_records(memory_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_project_repo ON memory_records(project_key, repo_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_records(memory_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_records(source_kind, source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_records(created_at)")
        existing = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        if existing is None:
            conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, datetime('now'))", (SCHEMA_VERSION,))
