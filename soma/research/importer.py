"""Manual raw-source import through the canonical archive and research overlay."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .archive import ArchivedObject, SourceArchive
from .models import (
    IngestionStatus,
    SourceDraft,
    SourceVersionDraft,
    SourceVersionRecord,
)
from .ragflow import RagFlowGateway


class ResearchOverlay(Protocol):
    """Importer-facing subset of the authoritative research overlay."""

    def add_source(self, draft: SourceDraft) -> str: ...

    def add_source_version(self, draft: SourceVersionDraft) -> str: ...

    def source(self, project_id: str, source_id: str) -> Any | None: ...

    def source_version(
        self, project_id: str, source_version_id: str
    ) -> SourceVersionRecord | None: ...

    def source_version_for_hash(
        self, project_id: str, source_id: str, archive_sha256: str
    ) -> SourceVersionRecord | None: ...

    def update_source_version_status(
        self,
        project_id: str,
        source_version_id: str,
        *,
        status: IngestionStatus,
        last_error: str = "",
        last_indexed_at: str | None = None,
    ) -> None: ...

    def update_source_version_mapping(
        self,
        project_id: str,
        source_version_id: str,
        *,
        dataset_id: str,
        document_id: str,
        status: IngestionStatus,
        last_error: str = "",
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class SourceImportDraft:
    """Controller-supplied provenance for one explicit manual import."""

    project_id: str
    canonical_uri: str
    title: str
    source_type: str
    retrieved_at: str
    origin_namespace: str = "manual"
    origin_key: str | None = None
    origin_version: int = 0
    authors: tuple[str, ...] = ()
    published_at: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    etag: str | None = None
    last_modified: str | None = None
    supersedes_version_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("project_id", self.project_id),
            ("canonical_uri", self.canonical_uri),
            ("title", self.title),
            ("source_type", self.source_type),
            ("retrieved_at", self.retrieved_at),
            ("origin_namespace", self.origin_namespace),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.origin_key is not None and not self.origin_key.strip():
            raise ValueError("origin_key must not be empty when provided")
        if self.origin_version < 0:
            raise ValueError("origin_version must not be negative")


@dataclass(frozen=True, slots=True)
class ImportResult:
    source_id: str
    source_version_id: str
    archived: ArchivedObject
    ingestion_status: IngestionStatus
    ragflow_document_id: str | None = None


class ResearchSourceImporter:
    """Archive first, then durably record and optionally index one manual source."""

    def __init__(
        self,
        *,
        store: ResearchOverlay,
        archive: SourceArchive,
        ragflow: RagFlowGateway | None = None,
    ) -> None:
        self.store = store
        self.archive = archive
        self.ragflow = ragflow

    def import_file(
        self,
        path: Path,
        draft: SourceImportDraft,
        *,
        ragflow_dataset_id: str | None = None,
        parse: bool = False,
    ) -> ImportResult:
        return self._record(
            self.archive.put_file(path),
            draft,
            ragflow_dataset_id=ragflow_dataset_id,
            parse=parse,
        )

    def import_bytes(
        self,
        content: bytes,
        *,
        original_name: str,
        draft: SourceImportDraft,
        media_type: str | None = None,
        ragflow_dataset_id: str | None = None,
        parse: bool = False,
    ) -> ImportResult:
        return self._record(
            self.archive.put_bytes(
                content, original_name=original_name, media_type=media_type
            ),
            draft,
            ragflow_dataset_id=ragflow_dataset_id,
            parse=parse,
        )

    def import_captured(
        self,
        path: Path,
        draft: SourceImportDraft,
        *,
        ragflow_dataset_id: str | None = None,
        parse: bool = False,
    ) -> ImportResult:
        """Import an already captured URL or other source artifact."""
        return self.import_file(
            path,
            draft,
            ragflow_dataset_id=ragflow_dataset_id,
            parse=parse,
        )

    def reconcile_ragflow_status(
        self, project_id: str, source_version_id: str
    ) -> IngestionStatus:
        if self.ragflow is None:
            raise ValueError("status reconciliation requires a RAGFlow gateway")
        record = self.store.source_version(project_id, source_version_id)
        if record is None:
            raise KeyError(f"unknown source version: {source_version_id}")
        if record.ragflow_dataset_id is None or record.ragflow_document_id is None:
            raise ValueError("source version has no RAGFlow mapping")
        document = next(
            (
                item
                for item in self.ragflow.list_documents(record.ragflow_dataset_id)
                if item.document_id == record.ragflow_document_id
            ),
            None,
        )
        if document is None:
            raise LookupError(
                f"RAGFlow document not found: {record.ragflow_document_id}"
            )
        run = (document.run or "").upper()
        if run == "DONE" or (
            document.progress is not None and document.progress >= 1.0
        ):
            status, error = IngestionStatus.INDEXED, ""
        elif run == "FAIL":
            status = IngestionStatus.FAILED
            error = document.progress_message or "RAGFlow parsing failed"
        elif run == "CANCEL":
            status = IngestionStatus.RETRY
            error = document.progress_message or "RAGFlow parsing was cancelled"
        else:
            status, error = IngestionStatus.PARSING, ""
        self.store.update_source_version_status(
            project_id, source_version_id, status=status, last_error=error
        )
        return status

    def _record(
        self,
        archived: ArchivedObject,
        draft: SourceImportDraft,
        *,
        ragflow_dataset_id: str | None,
        parse: bool,
    ) -> ImportResult:
        if parse and ragflow_dataset_id is None:
            raise ValueError("parse requires ragflow_dataset_id")
        if ragflow_dataset_id is not None and self.ragflow is None:
            raise ValueError("ragflow_dataset_id requires a RAGFlow gateway")
        source_id = self.store.add_source(
            SourceDraft(
                project_id=draft.project_id,
                title=draft.title,
                source_type=draft.source_type,
                canonical_uri=draft.canonical_uri,
                authors=draft.authors,
                published_at=draft.published_at,
                metadata=dict(draft.metadata),
            )
        )
        existing = self.store.source_version_for_hash(
            draft.project_id, source_id, archived.sha256
        )
        if existing is not None:
            return ImportResult(
                source_id=source_id,
                source_version_id=existing.source_version_id,
                archived=archived,
                ingestion_status=existing.ingestion_status,
                ragflow_document_id=existing.ragflow_document_id,
            )
        source = self.store.source(draft.project_id, source_id)
        supersedes = draft.supersedes_version_id or (
            source.current_version_id if source is not None else None
        )
        source_version_id = self.store.add_source_version(
            SourceVersionDraft(
                project_id=draft.project_id,
                source_id=source_id,
                archive_sha256=archived.sha256,
                archive_relative_path=archived.relative_path,
                original_name=archived.original_name,
                media_type=archived.media_type,
                size_bytes=archived.size_bytes,
                retrieved_at=draft.retrieved_at,
                origin_namespace=draft.origin_namespace,
                origin_key=draft.origin_key or draft.canonical_uri,
                origin_version=draft.origin_version,
                etag=draft.etag,
                last_modified=draft.last_modified,
                supersedes_version_id=supersedes,
                ingestion_status=IngestionStatus.STORED,
            )
        )
        if ragflow_dataset_id is None:
            return ImportResult(
                source_id, source_version_id, archived, IngestionStatus.STORED
            )
        assert self.ragflow is not None
        try:
            document = self.ragflow.upload_document(
                ragflow_dataset_id, self.archive.resolve(archived.relative_path)
            )
            status = IngestionStatus.UPLOADED
            if parse:
                self.ragflow.parse_documents(
                    ragflow_dataset_id, (document.document_id,)
                )
                status = IngestionStatus.PARSING
            self.store.update_source_version_mapping(
                draft.project_id,
                source_version_id,
                dataset_id=ragflow_dataset_id,
                document_id=document.document_id,
                status=status,
            )
            return ImportResult(
                source_id,
                source_version_id,
                archived,
                status,
                document.document_id,
            )
        except Exception as error:
            self.store.update_source_version_status(
                draft.project_id,
                source_version_id,
                status=IngestionStatus.FAILED,
                last_error=str(error),
            )
            raise
