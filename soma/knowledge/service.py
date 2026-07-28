from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .catalog import KnowledgeCatalog
from .models import (
    KnowledgeHealth,
    KnowledgeInput,
    KnowledgeRecord,
    KnowledgeSearchPage,
    RebuildResult,
)
from .vault import MarkdownVault, content_hash, validate_project_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class KnowledgeService:
    def __init__(self, vault_root: Path, db_path: Path):
        self.vault_root = Path(vault_root).resolve()
        self.vault = MarkdownVault(self.vault_root)
        self.catalog = KnowledgeCatalog(db_path)

    def save(self, note: KnowledgeInput) -> KnowledgeRecord:
        validate_project_id(note.project_id)
        self.vault.resolve_path(note.vault_path)
        existing = self.catalog.by_idempotency(note.project_id, note.idempotency_key)
        if existing is not None:
            return existing
        existing_path = self.catalog.by_path(note.project_id, note.vault_path)
        if existing_path is not None:
            raise ValueError(
                f"vault_path is already owned by {existing_path.knowledge_id}"
            )
        self._validate_provenance(note)
        now = _now()
        stable_seed = (
            f"{note.project_id}\0{note.idempotency_key}"
            if note.idempotency_key
            else uuid4().hex
        )
        knowledge_id = "kn_" + hashlib.sha256(stable_seed.encode()).hexdigest()[:32]
        record = KnowledgeRecord(
            **note.model_dump(),
            knowledge_id=knowledge_id,
            revision=1,
            created_at=now,
            updated_at=now,
            content_sha256="",
        )
        record.content_sha256 = content_hash(record)
        self.vault.write(record)
        self.catalog.upsert(record)
        return record

    def get(self, project_id: str, knowledge_id: str) -> KnowledgeRecord:
        validate_project_id(project_id)
        record = self.catalog.get(project_id, knowledge_id)
        canonical = self.vault.read(self.vault.resolve_path(record.vault_path))
        if canonical.project_id != project_id or canonical.knowledge_id != knowledge_id:
            raise PermissionError("canonical knowledge identity does not match request")
        return canonical

    def search(
        self,
        project_id: str,
        query: str,
        *,
        limit: int = 20,
        current_only: bool = True,
        cursor: str | None = None,
    ) -> KnowledgeSearchPage:
        validate_project_id(project_id)
        if not query.strip():
            raise ValueError("query must not be empty")
        maximum = max(1, min(limit, 50))
        offset = self._decode_cursor(cursor, project_id, query, current_only)
        matches = self.catalog.search(project_id, query, current_only)
        page = matches[offset : offset + maximum]
        next_offset = offset + len(page)
        has_more = next_offset < len(matches)
        return KnowledgeSearchPage(
            records=page,
            total=len(matches),
            has_more=has_more,
            next_cursor=(
                self._encode_cursor(project_id, query, current_only, next_offset)
                if has_more
                else None
            ),
        )

    def supersede(
        self, note: KnowledgeInput, supersedes_ids: list[str]
    ) -> KnowledgeRecord:
        validate_project_id(note.project_id)
        if not supersedes_ids:
            raise ValueError("supersedes_ids must not be empty")
        existing = self.catalog.by_idempotency(note.project_id, note.idempotency_key)
        if existing is not None:
            return existing
        old_records = [
            self.catalog.get(note.project_id, knowledge_id)
            for knowledge_id in supersedes_ids
        ]
        payload = note.model_copy(update={"supersedes_ids": list(supersedes_ids)})
        current = self.save(payload)
        for old in old_records:
            old.status = "superseded"
            old.updated_at = _now()
            old.revision += 1
            old.content_sha256 = content_hash(old)
            self.vault.write(old)
            self.catalog.upsert(old)
        return current

    def rebuild(self, project_id: str | None = None) -> RebuildResult:
        if project_id is None:
            raise ValueError("project_id is required for a fail-closed rebuild")
        validate_project_id(project_id)
        records: list[KnowledgeRecord] = []
        malformed = 0
        for path in self.vault.markdown_files():
            try:
                record = self.vault.read(path)
            except (OSError, UnicodeError, ValueError):
                malformed += 1
                continue
            if record.project_id == project_id:
                records.append(record)
        self.catalog.replace_project(
            project_id,
            records,
            canonical_count=len(records) + malformed,
            malformed_count=malformed,
            updated_at=_now(),
        )
        return RebuildResult(
            project_id=project_id,
            indexed_count=len(records),
            malformed_count=malformed,
        )

    def health(self, project_id: str) -> KnowledgeHealth:
        validate_project_id(project_id)
        state = self.catalog.state(project_id)
        if state is None:
            result = self.rebuild(project_id)
            canonical = result.indexed_count + result.malformed_count
            malformed = result.malformed_count
            indexed = result.indexed_count
        else:
            canonical = int(state["canonical_count"])
            indexed = int(state["indexed_count"])
            malformed = int(state["malformed_count"])
        status = (
            "degraded"
            if malformed or indexed != canonical
            else "healthy"
            if canonical
            else "empty"
        )
        return KnowledgeHealth(
            project_id=project_id,
            status=status,
            canonical_count=canonical,
            indexed_count=indexed,
            malformed_count=malformed,
        )

    @staticmethod
    def _validate_provenance(note: KnowledgeInput) -> None:
        source_ids = {source.source_id for source in note.sources}
        missing = {
            locator.source_id
            for locator in note.locators
            if locator.source_id not in source_ids
        }
        if missing:
            raise ValueError(f"locators reference unknown sources: {sorted(missing)}")

    @staticmethod
    def _cursor_fingerprint(project_id: str, query: str, current_only: bool) -> str:
        raw = json.dumps(
            [project_id, query, current_only],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _encode_cursor(
        self, project_id: str, query: str, current_only: bool, offset: int
    ) -> str:
        payload = {
            "f": self._cursor_fingerprint(project_id, query, current_only),
            "o": offset,
        }
        return base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()

    def _decode_cursor(
        self,
        cursor: str | None,
        project_id: str,
        query: str,
        current_only: bool,
    ) -> int:
        if not cursor:
            return 0
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            expected = self._cursor_fingerprint(project_id, query, current_only)
            if payload.get("f") != expected or int(payload.get("o", -1)) < 0:
                raise ValueError
            return int(payload["o"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid or stale knowledge search cursor") from exc
