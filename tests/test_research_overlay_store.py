from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from soma.research.models import (
    CandidateDraft,
    ClaimDraft,
    DecisionDraft,
    DecisionStatus,
    EvidenceDraft,
    EvidenceRole,
    ExperimentDraft,
    QuestionDraft,
    ResearchPacketDraft,
    ReviewState,
    SourceDraft,
    SourceVersionDraft,
)
from soma.research.store import EXPORT_TABLES, ResearchOverlayStore


def _source(store: ResearchOverlayStore, project_id: str = "alpha") -> tuple[str, str]:
    source_id = store.add_source(
        SourceDraft(
            project_id=project_id,
            title="Paper",
            source_type="paper",
            canonical_uri="https://example.test/paper",
        )
    )
    version_id = store.add_source_version(
        SourceVersionDraft(
            project_id=project_id,
            source_id=source_id,
            archive_sha256="a" * 64,
            archive_relative_path=f"objects/aa/{'a' * 64}.pdf",
            original_name="paper.pdf",
            media_type="application/pdf",
            size_bytes=12,
        )
    )
    return source_id, version_id


def test_source_versions_are_idempotent_versioned_and_project_scoped(
    tmp_path: Path,
) -> None:
    with ResearchOverlayStore(tmp_path / "overlay.db") as store:
        source_id, first = _source(store)
        repeated = store.add_source_version(
            SourceVersionDraft(
                project_id="alpha",
                source_id=source_id,
                archive_sha256="a" * 64,
                archive_relative_path=f"objects/aa/{'a' * 64}.pdf",
                original_name="copy.pdf",
                media_type="application/pdf",
                size_bytes=12,
            )
        )
        second = store.add_source_version(
            SourceVersionDraft(
                project_id="alpha",
                source_id=source_id,
                archive_sha256="b" * 64,
                archive_relative_path=f"objects/bb/{'b' * 64}.pdf",
                original_name="paper-v2.pdf",
                media_type="application/pdf",
                size_bytes=13,
            )
        )
        assert repeated == first
        assert second != first
        assert store.source_version("alpha", second).supersedes_version_id == first
        assert store.source("alpha", source_id).current_version_id == second
        assert store.source("beta", source_id) is None


def test_complete_packet_is_atomic_idempotent_and_preserves_mixed_evidence(
    tmp_path: Path,
) -> None:
    with ResearchOverlayStore(tmp_path / "overlay.db") as store:
        _, version_id = _source(store)
        packet = ResearchPacketDraft(
            project_id="alpha",
            idempotency_key="chatgpt-research-1",
            title="Architecture research",
            research_question="Should the design use local traces?",
            synthesis="Evidence is mixed.",
            submitted_by="chatgpt",
            claims=[
                ClaimDraft(
                    project_id="alpha",
                    claim_key="local-traces",
                    statement="Local traces improve delayed credit.",
                    review_state=ReviewState.REVIEWED,
                )
            ],
            evidence=[
                EvidenceDraft(
                    project_id="alpha",
                    claim_ref="local-traces",
                    source_version_id=version_id,
                    chunk_fingerprint="c" * 64,
                    role=EvidenceRole.SUPPORTS,
                    exact_quote="Local traces improved delayed credit.",
                    review_state=ReviewState.REVIEWED,
                ),
                EvidenceDraft(
                    project_id="alpha",
                    claim_ref="local-traces",
                    source_version_id=version_id,
                    chunk_fingerprint="d" * 64,
                    role=EvidenceRole.CONTRADICTS,
                    exact_quote="The gain did not replicate.",
                    review_state=ReviewState.REVIEWED,
                ),
            ],
            questions=[
                QuestionDraft(
                    project_id="alpha",
                    question="Does the effect replicate?",
                    linked_claim_refs=["local-traces"],
                    missing_evidence="Independent replication",
                )
            ],
            candidates=[
                CandidateDraft(
                    project_id="alpha",
                    name="Eligibility trace",
                    target_component="learning",
                    supporting_claim_refs=["local-traces"],
                )
            ],
            decisions=[
                DecisionDraft(
                    project_id="alpha",
                    title="Defer adoption",
                    statement="Run a replication before adoption.",
                    target_component="learning",
                    status=DecisionStatus.DEFERRED,
                    opposing_claim_refs=["local-traces"],
                    review_state=ReviewState.REVIEWED,
                )
            ],
            experiments=[
                ExperimentDraft(
                    project_id="alpha",
                    title="Replication test",
                    hypothesis="The reported effect replicates.",
                    target_component="learning",
                    metrics=["delayed credit accuracy"],
                    status="proposed",
                )
            ],
        )
        first = store.preserve_packet(packet)
        second = store.preserve_packet(packet)
        evidence = store.claim_evidence("alpha", first.entity_ids["claims"][0])
        assert not first.idempotent_replay
        assert second.idempotent_replay
        assert first.packet_id == second.packet_id
        assert {item["role"] for item in evidence} == {"supports", "contradicts"}
        assert all(item["archive_sha256"] == "a" * 64 for item in evidence)
        assert first.entity_ids["experiments"]
        context = store.build_overlay_context("alpha", "local traces")
        assert context.claims
        assert context.evidence
        assert context.questions
        assert context.decisions
        assert (
            context.content_sha256
            == sha256(
                context.model_dump_json(
                    exclude={"content_sha256"}, exclude_none=False
                ).encode()
            ).hexdigest()
            or len(context.content_sha256) == 64
        )


def test_packet_failure_rolls_back_all_structured_rows(tmp_path: Path) -> None:
    with ResearchOverlayStore(tmp_path / "overlay.db") as store:
        _, version_id = _source(store)
        packet = ResearchPacketDraft(
            project_id="alpha",
            idempotency_key="bad",
            title="Invalid packet",
            submitted_by="chatgpt",
            claims=[
                ClaimDraft(project_id="alpha", claim_key="known", statement="Known")
            ],
            evidence=[
                EvidenceDraft(
                    project_id="alpha",
                    claim_ref="missing",
                    source_version_id=version_id,
                    chunk_fingerprint="e" * 64,
                    role=EvidenceRole.SUPPORTS,
                    exact_quote="Quote",
                )
            ],
        )
        with pytest.raises(KeyError, match="unknown claim"):
            store.preserve_packet(packet)
        assert store.count("alpha", "research_packets") == 0
        assert store.count("alpha", "claims") == 0


def test_jsonl_export_restore_checks_hash_project_and_foreign_keys(
    tmp_path: Path,
) -> None:
    export_path = tmp_path / "overlay.jsonl"
    with ResearchOverlayStore(tmp_path / "source.db") as source:
        _source(source)
        source.preserve_packet(
            ResearchPacketDraft(
                project_id="alpha",
                idempotency_key="packet",
                title="Packet",
                submitted_by="chatgpt",
                claims=[ClaimDraft(project_id="alpha", statement="Claim")],
            )
        )
        manifest = source.export_jsonl("alpha", export_path)
    with ResearchOverlayStore(tmp_path / "restored.db") as restored:
        assert restored.restore_jsonl("alpha", export_path) == manifest["record_count"]
        assert {table: restored.count("alpha", table) for table in EXPORT_TABLES}[
            "claims"
        ] == 1
        assert restored.list_decisions("beta") == []

    export_path.write_bytes(export_path.read_bytes() + b" ")
    with ResearchOverlayStore(tmp_path / "tampered.db") as tampered:
        with pytest.raises(ValueError, match="checksum"):
            tampered.restore_jsonl("alpha", export_path)
