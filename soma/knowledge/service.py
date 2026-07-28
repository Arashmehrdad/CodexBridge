from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .catalog import KnowledgeCatalog
from .models import (
    KnowledgeHealth,
    KnowledgeInput,
    KnowledgeRecord,
    KnowledgeSearchPage,
    RebuildResult,
)
from .vault import MarkdownVault, UnadoptedNote, content_hash, validate_project_id


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
        page = [
            self._canonical(record)
            for record in matches[offset : offset + maximum]
        ]
        if current_only:
            # The catalog filters on the *declared* status, which can lag a
            # successor that was written while a predecessor's own file had not
            # yet been rewritten. The link is authoritative, so apply it here.
            superseding = self.catalog.superseded_ids(project_id)
            page = [
                record
                for record in page
                if self.effective_status(record, superseding) in {"current", "proposed"}
            ]
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
        """Replace one or more records, crash-safely.

        The successor is written first and its `supersedes_ids` link is what
        makes the predecessors superseded -- see `effective_status`. Rewriting
        each predecessor afterwards is a *projection* that makes the state
        visible in the file itself; correctness never depends on it completing.
        Previously an interruption partway through that loop left some
        predecessors still reading `current`, and a rebuild adopted that.
        """
        validate_project_id(note.project_id)
        if not supersedes_ids:
            raise ValueError("supersedes_ids must not be empty")
        existing = self.catalog.by_idempotency(note.project_id, note.idempotency_key)
        if existing is not None:
            return existing
        # Resolve every predecessor before writing anything: an unknown id must
        # refuse the whole operation rather than leave a dangling successor.
        old_records = [
            self.catalog.get(note.project_id, knowledge_id)
            for knowledge_id in supersedes_ids
        ]
        payload = note.model_copy(update={"supersedes_ids": list(supersedes_ids)})
        current = self.save(payload)

        for old in old_records:
            try:
                self._project_superseded(old)
            except OSError:
                # The link already carries the truth. A failed projection is
                # reported by health as dirty, not treated as a lost write.
                continue
        return current

    def _canonical(self, record: KnowledgeRecord) -> KnowledgeRecord:
        """Prefer the file over the index.

        The catalog stores a projection that an out-of-band Obsidian edit can
        outdate. Search used to return that projection directly, so a controller
        could be handed a body the owner had already changed.
        """
        try:
            fresh = self.vault.read(self.vault.resolve_path(record.vault_path))
        except (OSError, UnicodeError, ValueError, UnadoptedNote, ValidationError):
            # A record that no longer reads cleanly is reported through health;
            # search returns the last known projection rather than dropping the
            # hit silently, which would be indistinguishable from "no match".
            return record
        if (
            fresh.knowledge_id != record.knowledge_id
            or fresh.project_id != record.project_id
        ):
            return record
        return fresh

    def _project_superseded(self, record: KnowledgeRecord) -> None:
        """Write the derived `superseded` status into the predecessor's file."""
        record.status = "superseded"
        record.updated_at = _now()
        record.revision += 1
        record.content_sha256 = content_hash(record)
        self.vault.write(record)
        self.catalog.upsert(record)

    def effective_status(
        self, record: KnowledgeRecord, superseding_ids: set[str] | None = None
    ) -> str:
        """The record's real lifecycle state, derived from links.

        A declared status can be stale -- the successor may have been written
        while the predecessor's own file had not yet been rewritten. An incoming
        supersession link always wins over a declared `current`.
        """
        if superseding_ids is None:
            superseding_ids = self.catalog.superseded_ids(record.project_id)
        if record.knowledge_id in superseding_ids and record.status in {
            "current",
            "proposed",
        }:
            return "superseded"
        return record.status

    def rebuild(self, project_id: str | None = None) -> RebuildResult:
        """Reconstruct the catalog from canonical Markdown alone.

        Three outcomes per file, never two: a valid Soma record, an owner note
        Soma does not manage, or a Soma-owned record that will not parse. Only
        the third is corruption.
        """
        if project_id is None:
            raise ValueError("project_id is required for a fail-closed rebuild")
        validate_project_id(project_id)
        records: list[KnowledgeRecord] = []
        malformed: list[str] = []
        unadopted: list[str] = []
        for path in self.vault.markdown_files():
            relative = path.resolve().relative_to(self.vault.root).as_posix()
            try:
                record = self.vault.read(path)
            except UnadoptedNote:
                unadopted.append(relative)
                continue
            except (OSError, UnicodeError, ValueError, ValidationError):
                malformed.append(relative)
                continue
            if record.project_id == project_id:
                records.append(record)
        self.catalog.replace_project(
            project_id,
            records,
            canonical_count=len(records) + len(malformed),
            malformed_count=len(malformed),
            updated_at=_now(),
            unadopted_count=len(unadopted),
            unadopted_paths=unadopted,
            malformed_paths=malformed,
        )
        return RebuildResult(
            project_id=project_id,
            indexed_count=len(records),
            malformed_count=len(malformed),
            unadopted_count=len(unadopted),
        )

    def health(self, project_id: str) -> KnowledgeHealth:
        """Canonical-vault health. Never speaks for the semantic provider."""
        validate_project_id(project_id)
        if self.catalog.state(project_id) is None:
            self.rebuild(project_id)
        state = self.catalog.state(project_id)
        canonical = int(state["canonical_count"])
        indexed = int(state["indexed_count"])
        malformed = int(state["malformed_count"])
        unadopted = int(state["unadopted_count"])
        unadopted_paths = json.loads(state["unadopted_paths_json"] or "[]")
        malformed_paths = json.loads(state["malformed_paths_json"] or "[]")

        if malformed or indexed != canonical:
            status = "degraded"
        elif not canonical:
            # Unadopted owner notes mean the vault is not empty even when Soma
            # manages nothing in it yet.
            status = "dirty" if unadopted else "empty"
        else:
            status = "healthy"

        return KnowledgeHealth(
            project_id=project_id,
            status=status,
            canonical_count=canonical,
            indexed_count=indexed,
            malformed_count=malformed,
            unadopted_count=unadopted,
            unadopted_paths=list(unadopted_paths),
            malformed_paths=list(malformed_paths),
            generation=int(state["generation"]),
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
