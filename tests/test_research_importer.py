from pathlib import Path

from soma.research.archive import SourceArchive
from soma.research.importer import ResearchSourceImporter, SourceImportDraft
from soma.research.models import (
    IngestionStatus,
    SourceRecord,
    SourceVersionRecord,
)
from soma.research.ragflow import InMemoryRagFlowGateway


class RecordingOverlay:
    """Contract fake that deliberately has no field capable of storing source bytes."""

    def __init__(self) -> None:
        self.sources: dict[str, SourceRecord] = {}
        self.versions: dict[str, SourceVersionRecord] = {}
        self.version_drafts = []

    def add_source(self, draft) -> str:
        source_id = "src_1"
        existing = self.sources.get(source_id)
        if existing is None:
            self.sources[source_id] = SourceRecord(
                **draft.model_dump(),
                source_id=source_id,
                current_version_id=None,
                created_at="now",
                updated_at="now",
            )
        return source_id

    def add_source_version(self, draft) -> str:
        self.version_drafts.append(draft)
        version_id = f"ver_{len(self.versions) + 1}"
        self.versions[version_id] = SourceVersionRecord(
            **draft.model_dump(),
            source_version_id=version_id,
            last_indexed_at=None,
            created_at="now",
            updated_at="now",
        )
        source = self.sources[draft.source_id]
        self.sources[draft.source_id] = source.model_copy(
            update={"current_version_id": version_id}
        )
        return version_id

    def source(self, project_id, source_id):
        source = self.sources.get(source_id)
        return source if source and source.project_id == project_id else None

    def source_version(self, project_id, source_version_id):
        record = self.versions.get(source_version_id)
        return record if record and record.project_id == project_id else None

    def source_version_for_hash(self, project_id, source_id, archive_sha256):
        return next(
            (
                record
                for record in self.versions.values()
                if record.project_id == project_id
                and record.source_id == source_id
                and record.archive_sha256 == archive_sha256
            ),
            None,
        )

    def update_source_version_status(
        self,
        project_id,
        source_version_id,
        *,
        status,
        last_error="",
        last_indexed_at=None,
    ):
        record = self.versions[source_version_id]
        assert record.project_id == project_id
        self.versions[source_version_id] = record.model_copy(
            update={
                "ingestion_status": status,
                "last_error": last_error,
                "last_indexed_at": last_indexed_at,
            }
        )

    def update_source_version_mapping(
        self,
        project_id,
        source_version_id,
        *,
        dataset_id,
        document_id,
        status,
        last_error="",
    ):
        record = self.versions[source_version_id]
        assert record.project_id == project_id
        self.versions[source_version_id] = record.model_copy(
            update={
                "ragflow_dataset_id": dataset_id,
                "ragflow_document_id": document_id,
                "ingestion_status": status,
                "last_error": last_error,
            }
        )


def _draft() -> SourceImportDraft:
    return SourceImportDraft(
        project_id="project-a",
        canonical_uri="https://example.test/research.pdf",
        title="Research source",
        source_type="paper",
        retrieved_at="2026-07-28T00:00:00Z",
    )


def test_import_is_idempotent_and_overlay_receives_only_archive_metadata(
    tmp_path: Path,
) -> None:
    store = RecordingOverlay()
    importer = ResearchSourceImporter(
        store=store, archive=SourceArchive(tmp_path / "raw")
    )
    marker = b"raw source bytes must not enter SQLite"

    first = importer.import_bytes(marker, original_name="paper.pdf", draft=_draft())
    second = importer.import_bytes(marker, original_name="renamed.pdf", draft=_draft())

    assert first.source_version_id == second.source_version_id
    assert len(store.version_drafts) == 1
    serialized = store.version_drafts[0].model_dump_json().encode()
    assert marker not in serialized
    assert store.version_drafts[0].archive_sha256 == first.archived.sha256


def test_changed_bytes_create_linked_source_version(tmp_path: Path) -> None:
    store = RecordingOverlay()
    importer = ResearchSourceImporter(
        store=store, archive=SourceArchive(tmp_path / "raw")
    )

    first = importer.import_bytes(
        b"version one", original_name="paper.pdf", draft=_draft()
    )
    second = importer.import_bytes(
        b"version two", original_name="paper.pdf", draft=_draft()
    )

    assert first.source_version_id != second.source_version_id
    assert store.version_drafts[1].supersedes_version_id == first.source_version_id


def test_importer_records_replaceable_index_lifecycle(tmp_path: Path) -> None:
    store = RecordingOverlay()
    ragflow = InMemoryRagFlowGateway()
    importer = ResearchSourceImporter(
        store=store,
        archive=SourceArchive(tmp_path / "raw"),
        ragflow=ragflow,
    )

    result = importer.import_bytes(
        b"source-grounded passage",
        original_name="research.txt",
        draft=_draft(),
        ragflow_dataset_id="project-a-dataset",
        parse=True,
    )

    assert result.ingestion_status is IngestionStatus.PARSING
    stored = store.source_version("project-a", result.source_version_id)
    assert stored is not None
    assert stored.ragflow_dataset_id == "project-a-dataset"
    assert stored.ragflow_document_id == result.ragflow_document_id
    assert (
        importer.reconcile_ragflow_status("project-a", result.source_version_id)
        is IngestionStatus.INDEXED
    )
