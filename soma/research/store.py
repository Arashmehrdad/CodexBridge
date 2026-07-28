from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from .models import (
    ContextPacket,
    IngestionStatus,
    OverlayHealth,
    PreservedPacket,
    ResearchPacketDraft,
    SourceDraft,
    SourceRecord,
    SourceVersionDraft,
    SourceVersionRecord,
)

SCHEMA_VERSION = 1
EXPORT_TABLES = (
    "sources",
    "source_versions",
    "analysis_runs",
    "research_packets",
    "claims",
    "evidence_links",
    "research_questions",
    "design_candidates",
    "design_decisions",
    "experiment_proposals",
    "generated_summaries",
    "relationships",
    "audit_events",
    "context_packets",
)


def stable_id(prefix: str, *parts: str) -> str:
    if not prefix.strip() or any(not part.strip() for part in parts):
        raise ValueError("stable identifier parts must not be empty")
    digest = sha256(_json(parts).encode()).hexdigest()[:24]
    return f"{prefix}_{digest}"


class ResearchOverlayStore:
    """Structured, project-scoped authority for reviewed research state."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, timeout=10)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def __enter__(self) -> ResearchOverlayStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @property
    def schema_version(self) -> int:
        row = self._connection.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def add_source(self, draft: SourceDraft) -> str:
        source_id = stable_id("src", draft.project_id, _normal(draft.canonical_uri))
        now = _now()
        payload = draft.model_dump(mode="json")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO sources (
                    source_id, project_id, title, source_type, canonical_uri,
                    authors_json, published_at, metadata_json, current_version_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(project_id, canonical_uri) DO UPDATE SET
                    title=excluded.title, source_type=excluded.source_type,
                    authors_json=excluded.authors_json,
                    published_at=excluded.published_at,
                    metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
                """,
                (
                    source_id,
                    draft.project_id,
                    draft.title,
                    draft.source_type,
                    draft.canonical_uri,
                    _json(payload["authors"]),
                    draft.published_at,
                    _json(payload["metadata"]),
                    now,
                    now,
                ),
            )
        row = self._connection.execute(
            "SELECT source_id FROM sources WHERE project_id=? AND canonical_uri=?",
            (draft.project_id, draft.canonical_uri),
        ).fetchone()
        assert row is not None
        return str(row["source_id"])

    def add_source_version(self, draft: SourceVersionDraft) -> str:
        self._require_source(draft.project_id, draft.source_id)
        version_id = stable_id(
            "ver", draft.project_id, draft.source_id, draft.archive_sha256
        )
        now = _now()
        with self.transaction():
            existing = self._connection.execute(
                """
                SELECT source_version_id FROM source_versions
                WHERE project_id=? AND source_id=? AND archive_sha256=?
                """,
                (draft.project_id, draft.source_id, draft.archive_sha256),
            ).fetchone()
            if existing:
                self._connection.execute(
                    """
                    UPDATE source_versions SET origin_version=?, etag=?,
                      last_modified=?, ragflow_dataset_id=COALESCE(?,ragflow_dataset_id),
                      ragflow_document_id=COALESCE(?,ragflow_document_id),
                      ingestion_status=?, last_error=?, updated_at=?
                    WHERE project_id=? AND source_version_id=?
                    """,
                    (
                        draft.origin_version,
                        draft.etag,
                        draft.last_modified,
                        draft.ragflow_dataset_id,
                        draft.ragflow_document_id,
                        draft.ingestion_status.value,
                        draft.last_error,
                        now,
                        draft.project_id,
                        existing["source_version_id"],
                    ),
                )
                return str(existing["source_version_id"])
            supersedes = draft.supersedes_version_id
            if supersedes is None:
                current = self._connection.execute(
                    "SELECT current_version_id FROM sources WHERE project_id=? AND source_id=?",
                    (draft.project_id, draft.source_id),
                ).fetchone()
                supersedes = current["current_version_id"] if current else None
            values = draft.model_dump(mode="json")
            self._connection.execute(
                """
                INSERT INTO source_versions (
                    source_version_id, project_id, source_id, archive_sha256,
                    archive_relative_path, original_name, media_type, size_bytes,
                    retrieved_at, origin_namespace, origin_key, origin_version,
                    etag, last_modified, supersedes_version_id, ingestion_status,
                    ragflow_dataset_id, ragflow_document_id, last_error,
                    last_indexed_at, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?)
                """,
                (
                    version_id,
                    draft.project_id,
                    draft.source_id,
                    draft.archive_sha256,
                    draft.archive_relative_path,
                    draft.original_name,
                    draft.media_type,
                    draft.size_bytes,
                    draft.retrieved_at,
                    draft.origin_namespace,
                    draft.origin_key,
                    draft.origin_version,
                    draft.etag,
                    draft.last_modified,
                    supersedes,
                    values["ingestion_status"],
                    draft.ragflow_dataset_id,
                    draft.ragflow_document_id,
                    draft.last_error,
                    now,
                    now,
                ),
            )
            self._connection.execute(
                "UPDATE sources SET current_version_id=?,updated_at=? "
                "WHERE project_id=? AND source_id=?",
                (version_id, now, draft.project_id, draft.source_id),
            )
        return version_id

    def source(self, project_id: str, source_id: str) -> SourceRecord | None:
        row = self._connection.execute(
            "SELECT * FROM sources WHERE project_id=? AND source_id=?",
            (project_id, source_id),
        ).fetchone()
        if row is None:
            return None
        return SourceRecord(
            project_id=row["project_id"],
            source_id=row["source_id"],
            title=row["title"],
            source_type=row["source_type"],
            canonical_uri=row["canonical_uri"],
            authors=json.loads(row["authors_json"]),
            published_at=row["published_at"],
            metadata=json.loads(row["metadata_json"]),
            current_version_id=row["current_version_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def source_version(
        self, project_id: str, source_version_id: str
    ) -> SourceVersionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM source_versions WHERE project_id=? AND source_version_id=?",
            (project_id, source_version_id),
        ).fetchone()
        return _source_version(row) if row else None

    def source_version_for_hash(
        self, project_id: str, source_id: str, archive_sha256: str
    ) -> SourceVersionRecord | None:
        row = self._connection.execute(
            """SELECT * FROM source_versions
            WHERE project_id=? AND source_id=? AND archive_sha256=?""",
            (project_id, source_id, archive_sha256.lower()),
        ).fetchone()
        return _source_version(row) if row else None

    def source_version_ids(self, project_id: str, source_id: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            """SELECT source_version_id FROM source_versions
            WHERE project_id=? AND source_id=? ORDER BY created_at,source_version_id""",
            (project_id, source_id),
        )
        return tuple(str(row[0]) for row in rows)

    def source_versions(self, project_id: str) -> list[SourceVersionRecord]:
        rows = self._connection.execute(
            """SELECT * FROM source_versions
            WHERE project_id=? ORDER BY created_at,source_version_id""",
            (project_id,),
        )
        return [_source_version(row) for row in rows]

    def source_id_for_origin(
        self, project_id: str, origin_namespace: str, origin_key: str
    ) -> str | None:
        row = self._connection.execute(
            """SELECT source_id FROM source_versions
            WHERE project_id=? AND origin_namespace=? AND origin_key=?
            ORDER BY created_at LIMIT 1""",
            (project_id, origin_namespace, origin_key),
        ).fetchone()
        return str(row["source_id"]) if row else None

    def update_source_version_status(
        self,
        project_id: str,
        source_version_id: str,
        *,
        status: IngestionStatus,
        last_error: str = "",
        last_indexed_at: str | None = None,
    ) -> None:
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE source_versions SET ingestion_status=?,last_error=?,
                last_indexed_at=?,updated_at=? WHERE project_id=? AND source_version_id=?""",
                (
                    status.value,
                    last_error,
                    last_indexed_at,
                    _now(),
                    project_id,
                    source_version_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown source version: {source_version_id}")

    def update_source_version_mapping(
        self,
        project_id: str,
        source_version_id: str,
        *,
        dataset_id: str,
        document_id: str,
        status: IngestionStatus,
        last_error: str = "",
    ) -> None:
        if not dataset_id.strip() or not document_id.strip():
            raise ValueError("dataset_id and document_id must not be empty")
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE source_versions SET ragflow_dataset_id=?,
                ragflow_document_id=?,ingestion_status=?,last_error=?,
                last_indexed_at=?,updated_at=?
                WHERE project_id=? AND source_version_id=?""",
                (
                    dataset_id,
                    document_id,
                    status.value,
                    last_error,
                    _now() if status is IngestionStatus.INDEXED else None,
                    _now(),
                    project_id,
                    source_version_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown source version: {source_version_id}")

    def preserve_packet(self, packet: ResearchPacketDraft) -> PreservedPacket:
        packet_id = stable_id("pkt", packet.project_id, packet.idempotency_key)
        existing = self._connection.execute(
            """SELECT packet_id,entity_ids_json FROM research_packets
            WHERE project_id=? AND idempotency_key=?""",
            (packet.project_id, packet.idempotency_key),
        ).fetchone()
        if existing:
            return PreservedPacket(
                project_id=packet.project_id,
                packet_id=existing["packet_id"],
                idempotent_replay=True,
                entity_ids=json.loads(existing["entity_ids_json"]),
            )
        entity_ids: dict[str, list[str]] = {
            key: []
            for key in (
                "analysis_runs",
                "claims",
                "evidence",
                "questions",
                "candidates",
                "decisions",
                "experiments",
                "summaries",
                "relationships",
            )
        }
        now = _now()
        with self.transaction():
            analysis_id = None
            if packet.analysis_run:
                analysis_id = stable_id(
                    "ana",
                    packet.project_id,
                    packet.analysis_run.input_hash,
                    packet.analysis_run.analysis_type,
                )
                self._insert_payload(
                    "analysis_runs",
                    "analysis_run_id",
                    analysis_id,
                    packet.analysis_run,
                    now,
                )
                entity_ids["analysis_runs"].append(analysis_id)
            claim_refs: dict[str, str] = {}
            for ordinal, claim in enumerate(packet.claims):
                claim_id = stable_id(
                    "clm",
                    packet.project_id,
                    packet_id,
                    str(ordinal),
                    _normal(claim.statement),
                )
                self._insert_payload(
                    "claims", "claim_id", claim_id, claim, now, packet_id
                )
                claim_refs[f"claim:{ordinal}"] = claim_id
                if claim.claim_key:
                    if claim.claim_key in claim_refs:
                        raise ValueError(f"duplicate claim_key: {claim.claim_key}")
                    claim_refs[claim.claim_key] = claim_id
                claim_refs[claim_id] = claim_id
                entity_ids["claims"].append(claim_id)
            for ordinal, evidence in enumerate(packet.evidence):
                claim_id = claim_refs.get(evidence.claim_ref, evidence.claim_ref)
                self._require_claim(packet.project_id, claim_id)
                self._require_version(packet.project_id, evidence.source_version_id)
                evidence_id = stable_id(
                    "evd",
                    packet.project_id,
                    claim_id,
                    evidence.source_version_id,
                    evidence.chunk_fingerprint,
                    evidence.role.value,
                )
                values = evidence.model_dump(mode="json")
                values["claim_id"] = claim_id
                values["quote_sha256"] = sha256(
                    evidence.exact_quote.encode()
                ).hexdigest()
                self._insert_json_row(
                    "evidence_links",
                    "evidence_id",
                    evidence_id,
                    packet.project_id,
                    packet_id,
                    values,
                    now,
                    extra=(
                        "claim_id,source_version_id,role,review_state",
                        (
                            claim_id,
                            evidence.source_version_id,
                            evidence.role.value,
                            evidence.review_state.value,
                        ),
                    ),
                )
                entity_ids["evidence"].append(evidence_id)
            for key, drafts, prefix, table, id_column in (
                (
                    "questions",
                    packet.questions,
                    "que",
                    "research_questions",
                    "question_id",
                ),
                (
                    "candidates",
                    packet.candidates,
                    "can",
                    "design_candidates",
                    "candidate_id",
                ),
                (
                    "decisions",
                    packet.decisions,
                    "dec",
                    "design_decisions",
                    "decision_id",
                ),
                (
                    "experiments",
                    packet.experiments,
                    "exp",
                    "experiment_proposals",
                    "experiment_id",
                ),
                (
                    "summaries",
                    packet.summaries,
                    "sum",
                    "generated_summaries",
                    "summary_id",
                ),
                (
                    "relationships",
                    packet.relationships,
                    "rel",
                    "relationships",
                    "relationship_id",
                ),
            ):
                for ordinal, draft in enumerate(drafts):
                    entity_id = stable_id(
                        prefix, packet.project_id, packet_id, str(ordinal)
                    )
                    payload = draft.model_dump(mode="json")
                    payload = _resolve_claim_refs(payload, claim_refs)
                    supersedes_id = payload.get(
                        f"supersedes_{id_column.removesuffix('_id')}_id"
                    )
                    if table == "design_decisions" and draft.supersedes_decision_id:
                        supersedes_id = draft.supersedes_decision_id
                    if supersedes_id:
                        previous = self._connection.execute(
                            f"""SELECT payload_json FROM {table}
                            WHERE project_id=? AND {id_column}=?""",
                            (packet.project_id, supersedes_id),
                        ).fetchone()
                        if previous is None:
                            raise KeyError(
                                f"unknown superseded {table} record: {supersedes_id}"
                            )
                        previous_payload = json.loads(previous["payload_json"])
                        previous_payload["status"] = "superseded"
                        self._connection.execute(
                            f"""UPDATE {table} SET payload_json=?
                            WHERE project_id=? AND {id_column}=?""",
                            (
                                _json(previous_payload),
                                packet.project_id,
                                supersedes_id,
                            ),
                        )
                    self._insert_json_row(
                        table,
                        id_column,
                        entity_id,
                        packet.project_id,
                        packet_id,
                        payload,
                        now,
                    )
                    entity_ids[key].append(entity_id)
            self._connection.execute(
                """INSERT INTO research_packets (
                packet_id,project_id,idempotency_key,title,research_question,synthesis,
                submitted_by,review_state,analysis_run_id,entity_ids_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    packet_id,
                    packet.project_id,
                    packet.idempotency_key,
                    packet.title,
                    packet.research_question,
                    packet.synthesis,
                    packet.submitted_by,
                    packet.review_state.value,
                    analysis_id,
                    _json(entity_ids),
                    now,
                ),
            )
            self._connection.execute(
                """INSERT INTO audit_events
                (audit_event_id,project_id,packet_id,operation,actor,entity_type,
                entity_id,details_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    stable_id("aud", packet.project_id, packet_id, "preserve"),
                    packet.project_id,
                    packet_id,
                    "preserve_research_packet",
                    packet.submitted_by,
                    "research_packet",
                    packet_id,
                    _json({"entity_ids": entity_ids}),
                    now,
                ),
            )
        return PreservedPacket(
            project_id=packet.project_id,
            packet_id=packet_id,
            idempotent_replay=False,
            entity_ids=entity_ids,
        )

    def claim_evidence(self, project_id: str, claim_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT e.*,v.archive_sha256,v.archive_relative_path,s.canonical_uri,s.title
            FROM evidence_links e
            JOIN source_versions v ON v.project_id=e.project_id
              AND v.source_version_id=e.source_version_id
            JOIN sources s ON s.project_id=v.project_id AND s.source_id=v.source_id
            WHERE e.project_id=? AND e.claim_id=?
            ORDER BY e.role,e.evidence_id""",
            (project_id, claim_id),
        )
        return [_expanded_row(row) for row in rows]

    def evidence_for_source_version(
        self, project_id: str, source_version_id: str
    ) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT e.*,v.archive_sha256,v.archive_relative_path,
            s.canonical_uri,s.title
            FROM evidence_links e
            JOIN source_versions v ON v.project_id=e.project_id
              AND v.source_version_id=e.source_version_id
            JOIN sources s ON s.project_id=v.project_id AND s.source_id=v.source_id
            WHERE e.project_id=? AND e.source_version_id=?
            ORDER BY e.role,e.evidence_id""",
            (project_id, source_version_id),
        )
        return [_expanded_row(row) for row in rows]

    def list_questions(
        self, project_id: str, *, unresolved_only: bool = True
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM research_questions WHERE project_id=?"
        params: list[Any] = [project_id]
        if unresolved_only:
            sql += " AND json_extract(payload_json,'$.status') NOT IN ('resolved','superseded')"
        sql += " ORDER BY created_at,question_id"
        return [_expanded_row(row) for row in self._connection.execute(sql, params)]

    def list_decisions(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM design_decisions WHERE project_id=? ORDER BY created_at,decision_id",
            (project_id,),
        )
        return [_expanded_row(row) for row in rows]

    def build_overlay_context(
        self,
        project_id: str,
        query: str,
        *,
        retrieved_passages: list[dict[str, Any]] | None = None,
    ) -> ContextPacket:
        like = f"%{_escape_like(_normal(query))}%"
        claims = [
            item
            for item in self._search_payload("claims", project_id, like)
            if item.get("review_state") == "reviewed"
        ]
        passages = retrieved_passages or []
        passage_version_ids = {
            str(item.get("source_version_id") or "")
            for item in passages
            if item.get("source_version_id")
        }
        if passage_version_ids:
            placeholders = ",".join("?" for _ in passage_version_ids)
            linked_claim_ids = {
                str(row["claim_id"])
                for row in self._connection.execute(
                    f"""SELECT DISTINCT claim_id FROM evidence_links
                    WHERE project_id=? AND source_version_id IN ({placeholders})""",
                    (project_id, *sorted(passage_version_ids)),
                )
            }
            existing_claim_ids = {str(item["claim_id"]) for item in claims}
            for claim_id in sorted(linked_claim_ids - existing_claim_ids):
                row = self._connection.execute(
                    "SELECT * FROM claims WHERE project_id=? AND claim_id=?",
                    (project_id, claim_id),
                ).fetchone()
                if row is not None:
                    expanded = _expanded_row(row)
                    if expanded.get("review_state") == "reviewed":
                        claims.append(expanded)
        claim_ids = [item["claim_id"] for item in claims]
        evidence = [
            item
            for claim_id in claim_ids
            for item in self.claim_evidence(project_id, claim_id)
            if item.get("review_state") == "reviewed"
        ]
        questions = self._search_payload("research_questions", project_id, like)
        candidates = self._search_payload("design_candidates", project_id, like)
        decisions = self._search_payload("design_decisions", project_id, like)
        packet_ids = {str(item.get("packet_id") or "") for item in claims} - {""}
        if packet_ids:
            for table, id_column, target in (
                ("research_questions", "question_id", questions),
                ("design_candidates", "candidate_id", candidates),
                ("design_decisions", "decision_id", decisions),
            ):
                placeholders = ",".join("?" for _ in packet_ids)
                existing = {str(item[id_column]) for item in target}
                for row in self._connection.execute(
                    f"""SELECT * FROM {table}
                    WHERE project_id=? AND packet_id IN ({placeholders})
                    ORDER BY created_at,{id_column}""",
                    (project_id, *sorted(packet_ids)),
                ):
                    expanded = _expanded_row(row)
                    if str(expanded[id_column]) not in existing:
                        target.append(expanded)
        citations = [
            passage["citation"]
            for passage in passages
            if isinstance(passage.get("citation"), dict)
        ]
        entity_ids = sorted(
            {
                str(item[key])
                for items, key in (
                    (claims, "claim_id"),
                    (evidence, "evidence_id"),
                    (questions, "question_id"),
                    (candidates, "candidate_id"),
                    (decisions, "decision_id"),
                )
                for item in items
            }
        )
        body: dict[str, Any] = {
            "project_id": project_id,
            "query": query,
            "retrieved_passages": passages,
            "citations": citations,
            "claims": claims,
            "evidence": evidence,
            "questions": questions,
            "candidates": candidates,
            "decisions": decisions,
            "entity_ids": entity_ids,
        }
        content_hash = sha256(_json(body).encode()).hexdigest()
        packet = ContextPacket(**body, content_sha256=content_hash)
        context_id = stable_id("ctx", project_id, content_hash)
        with self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO context_packets
                (context_packet_id,project_id,query,content_sha256,payload_json,created_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    context_id,
                    project_id,
                    query,
                    content_hash,
                    packet.model_dump_json(),
                    _now(),
                ),
            )
        return packet

    def count(self, project_id: str, table: str) -> int:
        if table not in EXPORT_TABLES:
            raise ValueError(f"unsupported table: {table}")
        row = self._connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)
        ).fetchone()
        return int(row[0])

    def health(self, project_id: str) -> OverlayHealth:
        counts = {table: self.count(project_id, table) for table in EXPORT_TABLES}
        ingestion = {
            str(row["ingestion_status"]): int(row["n"])
            for row in self._connection.execute(
                """SELECT ingestion_status,COUNT(*) n FROM source_versions
                WHERE project_id=? GROUP BY ingestion_status""",
                (project_id,),
            )
        }
        status = "empty" if not counts["sources"] else "healthy"
        if ingestion.get(IngestionStatus.FAILED.value, 0):
            status = "degraded"
        return OverlayHealth(
            project_id=project_id,
            status=status,
            counts=counts,
            ingestion_counts=ingestion,
        )

    def export_jsonl(self, project_id: str, path: Path) -> dict[str, Any]:
        lines: list[str] = []
        for table in EXPORT_TABLES:
            for row in self._connection.execute(
                f"SELECT * FROM {table} WHERE project_id=? ORDER BY rowid",
                (project_id,),
            ):
                lines.append(_json({"record_type": table, "payload": dict(row)}))
        content = ("\n".join(lines) + ("\n" if lines else "")).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest = {
            "schema": "soma.research.overlay",
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "record_count": len(lines),
            "jsonl_sha256": sha256(content).hexdigest(),
        }
        path.with_suffix(path.suffix + ".manifest.json").write_text(
            _json(manifest) + "\n", encoding="utf-8"
        )
        return manifest

    def restore_jsonl(
        self, project_id: str, path: Path, *, require_empty: bool = True
    ) -> int:
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        content = path.read_bytes()
        if manifest != {
            "schema": "soma.research.overlay",
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "record_count": manifest.get("record_count"),
            "jsonl_sha256": sha256(content).hexdigest(),
        }:
            raise ValueError("overlay export manifest identity or checksum is invalid")
        records = [json.loads(line) for line in content.decode().splitlines() if line]
        if len(records) != manifest["record_count"]:
            raise ValueError("overlay export record count is invalid")
        if require_empty and any(
            self.count(project_id, table) for table in EXPORT_TABLES
        ):
            raise ValueError("target project overlay is not empty")
        allowed = {
            table: {
                str(row["name"])
                for row in self._connection.execute(f"PRAGMA table_info({table})")
            }
            for table in EXPORT_TABLES
        }
        with self.transaction():
            for record in records:
                table = record.get("record_type")
                payload = record.get("payload")
                if table not in EXPORT_TABLES or not isinstance(payload, dict):
                    raise ValueError("unsupported overlay export record")
                if (
                    payload.get("project_id") != project_id
                    or set(payload) != allowed[table]
                ):
                    raise ValueError(
                        "overlay export payload does not match its schema/project"
                    )
                columns = tuple(payload)
                self._connection.execute(
                    f"INSERT INTO {table} ({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})",
                    tuple(payload[column] for column in columns),
                )
            violations = self._connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError("overlay restore violates foreign keys")
        return len(records)

    def _migrate(self) -> None:
        if self.schema_version > SCHEMA_VERSION:
            raise ValueError("unsupported research overlay schema")
        if self.schema_version == SCHEMA_VERSION:
            return
        with self._connection:
            self._connection.executescript(_SCHEMA)
            self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _require_source(self, project_id: str, source_id: str) -> None:
        if self.source(project_id, source_id) is None:
            raise KeyError(f"unknown source: {source_id}")

    def _require_version(self, project_id: str, source_version_id: str) -> None:
        if self.source_version(project_id, source_version_id) is None:
            raise KeyError(f"unknown source version: {source_version_id}")

    def _require_claim(self, project_id: str, claim_id: str) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM claims WHERE project_id=? AND claim_id=?",
            (project_id, claim_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown claim: {claim_id}")

    def _insert_payload(
        self,
        table: str,
        id_column: str,
        entity_id: str,
        model: Any,
        now: str,
        packet_id: str | None = None,
    ) -> None:
        self._insert_json_row(
            table,
            id_column,
            entity_id,
            model.project_id,
            packet_id,
            model.model_dump(mode="json"),
            now,
        )

    def _insert_json_row(
        self,
        table: str,
        id_column: str,
        entity_id: str,
        project_id: str,
        packet_id: str | None,
        payload: dict[str, Any],
        now: str,
        *,
        extra: tuple[str, tuple[Any, ...]] | None = None,
    ) -> None:
        columns = [id_column, "project_id", "packet_id", "payload_json", "created_at"]
        values: list[Any] = [entity_id, project_id, packet_id, _json(payload), now]
        if extra:
            columns.extend(extra[0].split(","))
            values.extend(extra[1])
        self._connection.execute(
            f"INSERT INTO {table} ({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            values,
        )

    def _search_payload(
        self, table: str, project_id: str, escaped_like: str
    ) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            f"""SELECT * FROM {table} WHERE project_id=?
            AND lower(payload_json) LIKE ? ESCAPE '\\' ORDER BY created_at,rowid""",
            (project_id, escaped_like),
        )
        return [_expanded_row(row) for row in rows]


def _source_version(row: sqlite3.Row) -> SourceVersionRecord:
    return SourceVersionRecord(
        **{
            key: row[key]
            for key in (
                "project_id",
                "source_id",
                "archive_sha256",
                "archive_relative_path",
                "original_name",
                "media_type",
                "size_bytes",
                "retrieved_at",
                "origin_namespace",
                "origin_key",
                "origin_version",
                "etag",
                "last_modified",
                "supersedes_version_id",
                "ragflow_dataset_id",
                "ragflow_document_id",
                "last_error",
                "last_indexed_at",
                "created_at",
                "updated_at",
            )
        },
        source_version_id=row["source_version_id"],
        ingestion_status=row["ingestion_status"],
    )


def _expanded_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    payload = result.pop("payload_json", None)
    if payload:
        result.update(json.loads(payload))
    return result


def _resolve_claim_refs(
    payload: dict[str, Any], refs: dict[str, str]
) -> dict[str, Any]:
    for key in ("linked_claim_refs", "supporting_claim_refs", "opposing_claim_refs"):
        if key in payload:
            payload[key] = [refs.get(item, item) for item in payload[key]]
    return payload


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normal(value: str) -> str:
    return " ".join(value.casefold().split())


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _now() -> str:
    return datetime.now(UTC).isoformat()


_SCHEMA = """
CREATE TABLE sources (
 source_id TEXT NOT NULL, project_id TEXT NOT NULL, title TEXT NOT NULL,
 source_type TEXT NOT NULL, canonical_uri TEXT NOT NULL, authors_json TEXT NOT NULL,
 published_at TEXT, metadata_json TEXT NOT NULL, current_version_id TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(project_id,source_id), UNIQUE(project_id,canonical_uri),
 FOREIGN KEY(project_id,current_version_id) REFERENCES source_versions(project_id,source_version_id)
 DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE source_versions (
 source_version_id TEXT NOT NULL, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
 archive_sha256 TEXT NOT NULL, archive_relative_path TEXT NOT NULL,
 original_name TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
 retrieved_at TEXT, origin_namespace TEXT NOT NULL, origin_key TEXT NOT NULL,
 origin_version INTEGER NOT NULL CHECK(origin_version>=0), etag TEXT, last_modified TEXT,
 supersedes_version_id TEXT, ingestion_status TEXT NOT NULL,
 ragflow_dataset_id TEXT, ragflow_document_id TEXT, last_error TEXT NOT NULL,
 last_indexed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(project_id,source_version_id), UNIQUE(project_id,source_id,archive_sha256),
 FOREIGN KEY(project_id,source_id) REFERENCES sources(project_id,source_id),
 FOREIGN KEY(project_id,supersedes_version_id) REFERENCES source_versions(project_id,source_version_id)
);
CREATE TABLE analysis_runs (
 analysis_run_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,analysis_run_id)
);
CREATE TABLE research_packets (
 packet_id TEXT NOT NULL, project_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 title TEXT NOT NULL, research_question TEXT NOT NULL, synthesis TEXT NOT NULL,
 submitted_by TEXT NOT NULL, review_state TEXT NOT NULL, analysis_run_id TEXT,
 entity_ids_json TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(project_id,packet_id), UNIQUE(project_id,idempotency_key),
 FOREIGN KEY(project_id,analysis_run_id) REFERENCES analysis_runs(project_id,analysis_run_id)
);
CREATE TABLE claims (
 claim_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,claim_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE evidence_links (
 evidence_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, claim_id TEXT NOT NULL,
 source_version_id TEXT NOT NULL, role TEXT NOT NULL, review_state TEXT NOT NULL,
 PRIMARY KEY(project_id,evidence_id),
 UNIQUE(project_id,claim_id,source_version_id,role,evidence_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(project_id,claim_id) REFERENCES claims(project_id,claim_id),
 FOREIGN KEY(project_id,source_version_id) REFERENCES source_versions(project_id,source_version_id)
);
CREATE TABLE research_questions (
 question_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,question_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE design_candidates (
 candidate_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,candidate_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE design_decisions (
 decision_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,decision_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE experiment_proposals (
 experiment_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,experiment_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE generated_summaries (
 summary_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,summary_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE relationships (
 relationship_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id,relationship_id),
 FOREIGN KEY(project_id,packet_id) REFERENCES research_packets(project_id,packet_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE audit_events (
 audit_event_id TEXT NOT NULL, project_id TEXT NOT NULL, packet_id TEXT,
 operation TEXT NOT NULL, actor TEXT NOT NULL, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(project_id,audit_event_id)
);
CREATE TABLE context_packets (
 context_packet_id TEXT NOT NULL, project_id TEXT NOT NULL, query TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(project_id,context_packet_id)
);
CREATE INDEX idx_versions_status ON source_versions(project_id,ingestion_status);
CREATE INDEX idx_evidence_claim_role ON evidence_links(project_id,claim_id,role);
"""
