"""Project-scoped external research platform orchestration."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .archive import ArchivedObject, SourceArchive
from .importer import ResearchSourceImporter, SourceImportDraft
from .models import (
    ContextPacket,
    IngestionStatus,
    PreservedPacket,
    ResearchPacketDraft,
    SourceRecord,
    SourceVersionRecord,
)
from .ragflow import RagFlowGateway
from .store import ResearchOverlayStore


class ImportResult(BaseModel):
    project_id: str
    source_id: str
    source_version_id: str
    source_sha256: str
    archive_relative_path: str
    archive_path: str
    size_bytes: int
    media_type: str
    ingestion_status: str
    reused: bool
    supersedes_source_version_id: str | None = None
    ragflow_document_id: str | None = None


class ArchiveVerification(BaseModel):
    ok: bool
    source_version_id: str
    expected_sha256: str
    expected_size_bytes: int
    archive_path: str


class ComponentHealth(BaseModel):
    status: str
    details: dict[str, Any] = {}


class ResearchHealth(BaseModel):
    project_id: str
    archive: ComponentHealth
    overlay: ComponentHealth
    index: ComponentHealth
    projection: ComponentHealth
    overall_status: str


class RebuildResult(BaseModel):
    project_id: str
    dataset_id: str
    indexed_count: int
    failed_count: int
    failures: list[dict[str, str]]


class OverlayTransferResult(BaseModel):
    project_id: str
    record_count: int
    sha256: str
    path: str


class ResearchPlatformService:
    """Sole consistency boundary for one Soma project's research platform."""

    def __init__(
        self,
        root: Path,
        project_id: str,
        *,
        ragflow: RagFlowGateway | None = None,
    ) -> None:
        if not project_id.strip() or "/" in project_id or "\\" in project_id:
            raise ValueError("project_id must be a non-empty opaque identifier")
        self.root = Path(root).resolve()
        self.project_id = project_id
        project_dir = self.root / "projects" / _project_directory(project_id)
        self.archive = SourceArchive(project_dir / "raw")
        self.store = ResearchOverlayStore(project_dir / "research.sqlite3")
        self.ragflow = ragflow
        self.dataset_id = f"soma-{sha256(project_id.encode()).hexdigest()[:20]}"
        self.importer = ResearchSourceImporter(
            store=self.store,
            archive=self.archive,
            ragflow=ragflow,
        )

    def close(self) -> None:
        self.store.close()

    def import_bytes(
        self,
        draft: SourceImportDraft,
        content: bytes,
        *,
        original_name: str,
        media_type: str | None = None,
        index: bool = True,
    ) -> ImportResult:
        self._require_project(draft.project_id)
        archived = self.archive.put_bytes(
            content, original_name=original_name, media_type=media_type
        )
        existing = self._existing_version(draft, archived.sha256)
        result = self.importer.import_bytes(
            content,
            original_name=original_name,
            draft=draft,
            media_type=media_type,
            ragflow_dataset_id=self.dataset_id if index and self.ragflow else None,
            parse=bool(index and self.ragflow),
        )
        return self._import_result(result, existing is not None)

    def import_file(
        self,
        draft: SourceImportDraft,
        path: Path,
        *,
        index: bool = True,
    ) -> ImportResult:
        self._require_project(draft.project_id)
        archived = self.archive.put_file(path)
        existing = self._existing_version(draft, archived.sha256)
        result = self.importer.import_file(
            path,
            draft,
            ragflow_dataset_id=self.dataset_id if index and self.ragflow else None,
            parse=bool(index and self.ragflow),
        )
        return self._import_result(result, existing is not None)

    def import_captured(
        self,
        draft: SourceImportDraft,
        path: Path,
        *,
        index: bool = True,
    ) -> ImportResult:
        return self.import_file(draft, path, index=index)

    def preserve_packet(self, packet: ResearchPacketDraft) -> PreservedPacket:
        self._require_project(packet.project_id)
        return self.store.preserve_packet(packet)

    def get_source(self, source_id: str) -> SourceRecord:
        record = self.store.source(self.project_id, source_id)
        if record is None:
            raise KeyError(f"unknown research source: {source_id}")
        return record

    def get_source_version(self, source_version_id: str) -> Any:
        record = self._get_version_record(source_version_id)
        values = record.model_dump(mode="json")
        values["archive_path"] = str(self.archive.resolve(record.archive_relative_path))
        return _RecordView(values)

    def _get_version_record(self, source_version_id: str) -> SourceVersionRecord:
        record = self.store.source_version(self.project_id, source_version_id)
        if record is None:
            raise KeyError(f"unknown source version: {source_version_id}")
        return record

    def claim_evidence(self, claim_id: str) -> list[Any]:
        records = self.store.claim_evidence(self.project_id, claim_id)
        if not records:
            raise KeyError(f"unknown claim or evidence: {claim_id}")
        return [_RecordView(item) for item in records]

    def list_questions(self) -> list[Any]:
        return [
            _RecordView(item) for item in self.store.list_questions(self.project_id)
        ]

    def list_decisions(self) -> list[Any]:
        return [
            _RecordView(item) for item in self.store.list_decisions(self.project_id)
        ]

    def verify_archive(self, source_version_id: str) -> ArchiveVerification:
        version = self._get_version_record(source_version_id)
        archived = _archived_object(version)
        return ArchiveVerification(
            ok=self.archive.verify(archived),
            source_version_id=source_version_id,
            expected_sha256=version.archive_sha256,
            expected_size_bytes=version.size_bytes,
            archive_path=str(self.archive.resolve(version.archive_relative_path)),
        )

    def build_context_packet(self, query: str, *, limit: int = 12) -> ContextPacket:
        passages: list[dict[str, Any]] = []
        if self.ragflow is not None:
            versions = {
                version.ragflow_document_id: version
                for version in self.store.source_versions(self.project_id)
                if version.ragflow_document_id
            }
            chunks = self.ragflow.retrieve(
                query,
                dataset_ids=(self.dataset_id,),
                page_size=max(1, min(limit, 50)),
            )
            for chunk in chunks:
                version = versions.get(chunk.document_id)
                if version is None:
                    continue
                evidence = self.store.evidence_for_source_version(
                    self.project_id, version.source_version_id
                )
                anchor = next(
                    (
                        item
                        for item in evidence
                        if item.get("exact_quote", "").casefold()
                        in chunk.content.casefold()
                    ),
                    evidence[0] if evidence else None,
                )
                locator = str((anchor or {}).get("locator") or "")
                passage = {
                    "source_id": version.source_id,
                    "source_version_id": version.source_version_id,
                    "source_sha256": version.archive_sha256,
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "chunk_fingerprint": sha256(chunk.content.encode()).hexdigest(),
                    "content": chunk.content,
                    "positions": list(chunk.positions),
                    "similarity": chunk.similarity,
                    "citation": {
                        "source_id": version.source_id,
                        "source_version_id": version.source_version_id,
                        "archive_sha256": version.archive_sha256,
                        "locator": locator,
                        "page_start": (anchor or {}).get("page_start"),
                        "page_end": (anchor or {}).get("page_end"),
                    },
                }
                passages.append(passage)
        return self.store.build_overlay_context(
            self.project_id, query, retrieved_passages=passages
        )

    def rebuild_index(self) -> RebuildResult:
        if self.ragflow is None:
            raise ValueError("RAGFlow is not configured")
        indexed = 0
        failures: list[dict[str, str]] = []
        for version in self.store.source_versions(self.project_id):
            verification = self.verify_archive(version.source_version_id)
            if not verification.ok:
                failures.append(
                    {
                        "source_version_id": version.source_version_id,
                        "error": "archive verification failed",
                    }
                )
                continue
            try:
                document = self.ragflow.upload_document(
                    self.dataset_id, Path(verification.archive_path)
                )
                self.ragflow.parse_documents(self.dataset_id, (document.document_id,))
                self.store.update_source_version_mapping(
                    self.project_id,
                    version.source_version_id,
                    dataset_id=self.dataset_id,
                    document_id=document.document_id,
                    status=IngestionStatus.PARSING,
                )
                self.importer.reconcile_ragflow_status(
                    self.project_id, version.source_version_id
                )
                indexed += 1
            except Exception as exc:
                failures.append(
                    {
                        "source_version_id": version.source_version_id,
                        "error": str(exc),
                    }
                )
        return RebuildResult(
            project_id=self.project_id,
            dataset_id=self.dataset_id,
            indexed_count=indexed,
            failed_count=len(failures),
            failures=failures,
        )

    def health(self) -> ResearchHealth:
        versions = self.store.source_versions(self.project_id)
        bad = [
            version.source_version_id
            for version in versions
            if not self.archive.verify(_archived_object(version))
        ]
        archive_status = "corrupt" if bad else "healthy" if versions else "empty"
        overlay = self.store.health(self.project_id)
        if self.ragflow is None:
            index_status = "not_configured"
            index_details: dict[str, Any] = {"eligible_count": len(versions)}
        else:
            documents = self.ragflow.list_documents(self.dataset_id)
            document_ids = {item.document_id for item in documents}
            expected = {
                item.ragflow_document_id
                for item in versions
                if item.ragflow_document_id
            }
            indexed = sum(
                1
                for item in documents
                if item.document_id in expected
                and (
                    (item.run or "").upper() == "DONE"
                    or (item.progress is not None and item.progress >= 1)
                )
            )
            if not versions:
                index_status = "empty"
            elif indexed == len(versions) and expected <= document_ids:
                index_status = "healthy"
            elif indexed:
                index_status = "partial"
            else:
                index_status = "degraded"
            index_details = {
                "eligible_count": len(versions),
                "indexed_count": indexed,
            }
        overall = (
            "corrupt"
            if archive_status == "corrupt"
            else "degraded"
            if overlay.status == "degraded" or index_status in {"degraded", "partial"}
            else "healthy"
        )
        return ResearchHealth(
            project_id=self.project_id,
            archive=ComponentHealth(
                status=archive_status,
                details={"object_count": len(versions), "corrupt_ids": bad},
            ),
            overlay=ComponentHealth(
                status=overlay.status,
                details={
                    "counts": overlay.counts,
                    "ingestion_counts": overlay.ingestion_counts,
                },
            ),
            index=ComponentHealth(status=index_status, details=index_details),
            projection=ComponentHealth(
                status="legacy_compatible",
                details={"authoritative": False},
            ),
            overall_status=overall,
        )

    def export_overlay(self, path: Path) -> OverlayTransferResult:
        manifest = self.store.export_jsonl(self.project_id, path)
        return OverlayTransferResult(
            project_id=self.project_id,
            record_count=int(manifest["record_count"]),
            sha256=str(manifest["jsonl_sha256"]),
            path=str(Path(path).resolve()),
        )

    def restore_overlay(self, path: Path) -> OverlayTransferResult:
        count = self.store.restore_jsonl(self.project_id, path)
        manifest_path = Path(path).with_suffix(Path(path).suffix + ".manifest.json")
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return OverlayTransferResult(
            project_id=self.project_id,
            record_count=count,
            sha256=str(manifest["jsonl_sha256"]),
            path=str(Path(path).resolve()),
        )

    def _existing_version(
        self, draft: SourceImportDraft, archive_sha256: str
    ) -> SourceVersionRecord | None:
        source_id = self.store.source_id_for_origin(
            draft.project_id,
            draft.origin_namespace,
            draft.origin_key or draft.canonical_uri,
        )
        if source_id is None:
            return None
        return self.store.source_version_for_hash(
            draft.project_id, source_id, archive_sha256
        )

    def _import_result(self, result: Any, reused: bool) -> ImportResult:
        version = self._get_version_record(result.source_version_id)
        return ImportResult(
            project_id=self.project_id,
            source_id=result.source_id,
            source_version_id=result.source_version_id,
            source_sha256=version.archive_sha256,
            archive_relative_path=version.archive_relative_path,
            archive_path=str(self.archive.resolve(version.archive_relative_path)),
            size_bytes=version.size_bytes,
            media_type=version.media_type,
            ingestion_status=result.ingestion_status.value,
            reused=reused,
            supersedes_source_version_id=version.supersedes_version_id,
            ragflow_document_id=result.ragflow_document_id,
        )

    def _require_project(self, project_id: str) -> None:
        if project_id != self.project_id:
            raise PermissionError("research record belongs to another project")


class _RecordView:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return dict(self._values)


def _project_directory(project_id: str) -> str:
    return sha256(project_id.encode()).hexdigest()


def _archived_object(version: SourceVersionRecord) -> ArchivedObject:
    return ArchivedObject(
        sha256=version.archive_sha256,
        relative_path=version.archive_relative_path,
        size_bytes=version.size_bytes,
        media_type=version.media_type,
        original_name=version.original_name,
    )
