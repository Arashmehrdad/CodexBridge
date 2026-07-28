from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from soma.research import (
    CandidateDraft,
    ClaimDraft,
    DecisionDraft,
    EvidenceDraft,
    QuestionDraft,
    ResearchPacketDraft,
    ResearchPlatformService,
    SourceImportDraft,
)
from soma.research.ragflow import RagFlowDocument, RagFlowRetrievedChunk


SOMA_PROJECT_ID = "Soma"
SIBLING_PROJECT_ID = "Sibling"


class FakeRagFlow:
    """Small deterministic derived index used by the recovery acceptance tests."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def upload_document(self, dataset_id: str, path: Path) -> RagFlowDocument:
        content = path.read_text(encoding="utf-8")
        document_id = f"doc-{hashlib.sha256(path.read_bytes()).hexdigest()[:16]}"
        self.documents[document_id] = {
            "dataset_id": dataset_id,
            "name": path.name,
            "content": content,
            "parsed": False,
        }
        return RagFlowDocument(document_id=document_id, name=path.name)

    def parse_documents(self, dataset_id: str, document_ids: tuple[str, ...]) -> None:
        for document_id in document_ids:
            assert self.documents[document_id]["dataset_id"] == dataset_id
            self.documents[document_id]["parsed"] = True

    def list_documents(
        self,
        dataset_id: str,
        *,
        keywords: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[RagFlowDocument, ...]:
        documents = [
            RagFlowDocument(
                document_id=document_id,
                name=item["name"],
                run="DONE" if item["parsed"] else None,
                progress=1.0 if item["parsed"] else 0.0,
            )
            for document_id, item in self.documents.items()
            if item["dataset_id"] == dataset_id
            and (not keywords or keywords.casefold() in item["name"].casefold())
        ]
        start = (page - 1) * page_size
        return tuple(documents[start : start + page_size])

    def retrieve(
        self,
        question: str,
        *,
        dataset_ids: tuple[str, ...] = (),
        document_ids: tuple[str, ...] = (),
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[RagFlowRetrievedChunk, ...]:
        chunks = [
            RagFlowRetrievedChunk(
                chunk_id=f"{document_id}-chunk-1",
                document_id=document_id,
                content=item["content"],
                similarity=1.0,
                document_name=item["name"],
                dataset_id=item["dataset_id"],
                positions=(1,),
            )
            for document_id, item in self.documents.items()
            if item["parsed"]
            and (not dataset_ids or item["dataset_id"] in dataset_ids)
            and (not document_ids or document_id in document_ids)
            and question.casefold() in item["content"].casefold()
        ]
        start = (page - 1) * page_size
        return tuple(chunks[start : start + page_size])

    def delete_all(self) -> None:
        self.documents.clear()


def _source(
    *,
    origin_key: str = "https://example.test/research",
    title: str = "Research source",
) -> SourceImportDraft:
    return SourceImportDraft(
        project_id=SOMA_PROJECT_ID,
        source_type="webpage",
        canonical_uri=origin_key,
        title=title,
        origin_namespace="manual_url",
        origin_key=origin_key,
        retrieved_at="2026-07-28T12:00:00Z",
    )


def _import_source(
    service: ResearchPlatformService,
    *,
    content: bytes = b"Shared leases prevent duplicate ownership.",
):
    return service.import_bytes(
        _source(),
        content,
        original_name="research.txt",
        media_type="text/plain",
    )


def _packet(source_version_id: str) -> ResearchPacketDraft:
    return ResearchPacketDraft(
        project_id=SOMA_PROJECT_ID,
        idempotency_key="chatgpt:shared-leases:2026-07-28",
        title="Shared lease architecture review",
        research_question="Should Soma use one shared durable lease authority?",
        synthesis="The evidence supports one authority, with an operational caveat.",
        submitted_by="chatgpt",
        claims=[
            ClaimDraft(
                project_id=SOMA_PROJECT_ID,
                claim_key="claim:shared-authority",
                statement="One durable lease authority prevents duplicate ownership.",
                status="supported",
                confidence=0.9,
                review_state="reviewed",
            ),
        ],
        evidence=[
            EvidenceDraft(
                project_id=SOMA_PROJECT_ID,
                claim_ref="claim:shared-authority",
                source_version_id=source_version_id,
                role="supports",
                exact_quote="Shared leases prevent duplicate ownership.",
                locator="page 1",
                page_start=1,
                page_end=1,
                chunk_fingerprint=hashlib.sha256(
                    b"Shared leases prevent duplicate ownership."
                ).hexdigest(),
                review_state="reviewed",
            ),
            EvidenceDraft(
                project_id=SOMA_PROJECT_ID,
                claim_ref="claim:shared-authority",
                source_version_id=source_version_id,
                role="contradicts",
                exact_quote="A shared authority can become an availability bottleneck.",
                locator="page 2",
                page_start=2,
                page_end=2,
                chunk_fingerprint=hashlib.sha256(
                    b"A shared authority can become an availability bottleneck."
                ).hexdigest(),
                review_state="reviewed",
            ),
        ],
        questions=[
            QuestionDraft(
                project_id=SOMA_PROJECT_ID,
                question="What failover preserves lease safety?",
                status="open",
                missing_evidence="A deterministic controller failover drill.",
            ),
        ],
        candidates=[
            CandidateDraft(
                project_id=SOMA_PROJECT_ID,
                name="Shared durable controller",
                target_component="execution lifecycle",
                description="Reuse Soma's authoritative run controller.",
                status="accepted",
                supporting_claim_refs=["claim:shared-authority"],
                opposing_claim_refs=["claim:shared-authority"],
            ),
        ],
        decisions=[
            DecisionDraft(
                project_id=SOMA_PROJECT_ID,
                title="Reuse the authoritative controller",
                statement="RAGFlow rebuilds use Soma's existing task/run lifecycle.",
                target_component="execution lifecycle",
                status="accepted",
                supporting_claim_refs=["claim:shared-authority"],
                rationale="A second lifecycle authority would create split ownership.",
                reviewed_by="Arash",
                reviewed_at="2026-07-28T12:30:00Z",
            ),
        ],
    )


def _canonical_overlay_digest(service: ResearchPlatformService, path: Path) -> str:
    service.export_overlay(path)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if row.get("record_type") == "source_versions":
            payload = row["payload"]
            for key in (
                "ragflow_dataset_id",
                "ragflow_document_id",
                "ingestion_status",
                "last_error",
                "last_indexed_at",
                "updated_at",
            ):
                payload.pop(key, None)
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_manual_byte_and_file_imports_are_idempotent_and_version_changed_bytes(
    tmp_path: Path,
) -> None:
    service = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)
    draft = _source()

    first = service.import_bytes(
        draft, b"version one", original_name="source.txt", media_type="text/plain"
    )
    repeated = service.import_bytes(
        draft, b"version one", original_name="source.txt", media_type="text/plain"
    )
    changed_path = tmp_path / "changed-source.txt"
    changed_path.write_bytes(b"version two")
    changed = service.import_file(draft, changed_path)

    assert repeated.source_id == first.source_id
    assert repeated.source_version_id == first.source_version_id
    assert repeated.reused is True
    assert changed.source_id == first.source_id
    assert changed.source_version_id != first.source_version_id
    assert changed.source_sha256 != first.source_sha256
    assert changed.supersedes_source_version_id == first.source_version_id
    assert service.get_source(first.source_id).current_version_id == (
        changed.source_version_id
    )
    database = next((tmp_path / "projects").rglob("research.sqlite3"))
    assert b"version one" not in database.read_bytes()
    assert b"version two" not in database.read_bytes()


def test_archive_is_immutable_verifiable_and_reports_corruption(tmp_path: Path) -> None:
    service = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)
    imported = _import_source(service)
    version = service.get_source_version(imported.source_version_id)

    archive_path = Path(version.archive_path)
    assert archive_path.is_file()
    assert archive_path.read_bytes() == b"Shared leases prevent duplicate ownership."
    assert service.verify_archive(imported.source_version_id).ok is True

    archive_path.write_bytes(b"corrupted")

    verification = service.verify_archive(imported.source_version_id)
    assert verification.ok is False
    assert verification.expected_sha256 == imported.source_sha256
    assert service.health().archive.status == "corrupt"


def test_chatgpt_packet_preserves_research_graph_across_restart(
    tmp_path: Path,
) -> None:
    service = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)
    imported = _import_source(service)

    preserved = service.preserve_packet(_packet(imported.source_version_id))
    restarted = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)

    evidence = restarted.claim_evidence(preserved.entity_ids["claims"][0])
    assert {item.role for item in evidence} == {"supports", "contradicts"}
    assert all(item.exact_quote and item.locator for item in evidence)
    assert [item.status for item in restarted.list_questions()] == ["open"]
    decisions = restarted.list_decisions()
    assert [item.status for item in decisions] == ["accepted"]
    assert decisions[0].reviewed_by == "Arash"
    assert preserved.entity_ids["candidates"]


def test_reviewed_decision_supersession_survives_restart(tmp_path: Path) -> None:
    service = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)
    imported = _import_source(service)
    first = service.preserve_packet(_packet(imported.source_version_id))
    first_decision_id = first.entity_ids["decisions"][0]
    replacement = ResearchPacketDraft(
        project_id=SOMA_PROJECT_ID,
        idempotency_key="chatgpt:shared-leases:replacement",
        title="Lease decision correction",
        submitted_by="chatgpt",
        decisions=[
            DecisionDraft(
                project_id=SOMA_PROJECT_ID,
                title="Replace the lease controller decision",
                statement="Use a replicated authoritative controller.",
                target_component="execution lifecycle",
                status="accepted",
                reviewed_by="Arash",
                reviewed_at="2026-07-28T13:00:00Z",
                supersedes_decision_id=first_decision_id,
            )
        ],
    )

    second = service.preserve_packet(replacement)
    restarted = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)
    decisions = restarted.list_decisions()

    assert second.entity_ids["decisions"]
    assert any(item.supersedes_decision_id == first_decision_id for item in decisions)
    assert (
        next(item for item in decisions if item.decision_id == first_decision_id).status
        == "superseded"
    )


def test_research_state_is_strictly_isolated_between_sibling_projects(
    tmp_path: Path,
) -> None:
    soma = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID)
    sibling = ResearchPlatformService(tmp_path, SIBLING_PROJECT_ID)
    imported = _import_source(soma)
    preserved = soma.preserve_packet(_packet(imported.source_version_id))

    with pytest.raises((KeyError, PermissionError)):
        sibling.get_source(imported.source_id)
    with pytest.raises((KeyError, PermissionError)):
        sibling.claim_evidence(preserved.entity_ids["claims"][0])
    assert sibling.list_questions() == []
    assert sibling.list_decisions() == []
    assert sibling.build_context_packet("shared leases").claims == []


def test_context_packet_is_complete_and_reproducible(tmp_path: Path) -> None:
    ragflow = FakeRagFlow()
    service = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID, ragflow=ragflow)
    imported = _import_source(service)
    service.preserve_packet(_packet(imported.source_version_id))

    first = service.build_context_packet("shared leases", limit=10)
    repeated = service.build_context_packet("shared leases", limit=10)

    assert first.content_sha256 == repeated.content_sha256
    assert (
        first.retrieved_passages[0]["source_version_id"] == imported.source_version_id
    )
    assert first.citations[0]["archive_sha256"] == imported.source_sha256
    assert first.citations[0]["locator"] == "page 1"
    assert {item["role"] for item in first.evidence} == {"supports", "contradicts"}
    assert first.claims and first.questions and first.candidates and first.decisions


def test_ragflow_can_be_deleted_and_rebuilt_without_overlay_loss(
    tmp_path: Path,
) -> None:
    ragflow = FakeRagFlow()
    service = ResearchPlatformService(tmp_path, SOMA_PROJECT_ID, ragflow=ragflow)
    imported = _import_source(service)
    service.preserve_packet(_packet(imported.source_version_id))
    before = _canonical_overlay_digest(service, tmp_path / "before.jsonl")

    ragflow.delete_all()
    assert service.health().index.status in {"degraded", "empty", "partial"}
    rebuilt = service.rebuild_index()
    after = _canonical_overlay_digest(service, tmp_path / "after.jsonl")

    assert rebuilt.indexed_count == 1
    assert rebuilt.failed_count == 0
    assert before == after
    assert service.health().index.status == "healthy"
    assert service.build_context_packet("shared leases").retrieved_passages


def test_overlay_export_restore_preserves_research_state(tmp_path: Path) -> None:
    original_root = tmp_path / "original"
    restored_root = tmp_path / "restored"
    service = ResearchPlatformService(original_root, SOMA_PROJECT_ID)
    imported = _import_source(service)
    preserved = service.preserve_packet(_packet(imported.source_version_id))
    export_path = tmp_path / "research-overlay.jsonl"

    exported = service.export_overlay(export_path)
    restored = ResearchPlatformService(restored_root, SOMA_PROJECT_ID)
    result = restored.restore_overlay(export_path)

    assert exported.record_count == result.record_count
    assert restored.claim_evidence(preserved.entity_ids["claims"][0])
    assert restored.list_questions()[0].question.startswith("What failover")
    assert restored.list_decisions()[0].status == "accepted"
