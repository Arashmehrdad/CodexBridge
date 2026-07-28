"""The canonical memory authority.

SOMA-SHARED-MEMORY-ARCH-1 names `soma/knowledge/` as the implementation
foundation for canonical memory, because it already provides Markdown records,
stable identity, ProjectScope binding, provenance, idempotency, supersession,
rebuildable catalog state and health. `CanonicalMemoryService` wraps
`KnowledgeService` rather than replacing it, and adds exactly what the decision
requires on top: scope-bound access, compare-and-swap correction, the full
lifecycle vocabulary, three-dimensional health and context-packet assembly.

What it deliberately does not own: research claims (a separate authority plane),
task execution (the durable run engine), and retrieval ranking (the replaceable
provider).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import KnowledgeInput, KnowledgeRecord
from .scope import MemoryScope
from .service import KnowledgeService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MemoryWriteRefused(ValueError):
    """A canonical write was refused rather than applied unsafely."""


class MemoryConflict(MemoryWriteRefused):
    """The record changed since the caller last read it."""


#: Lifecycle states excluded from authoritative context unless asked for.
NON_AUTHORITATIVE_STATES: frozenset[str] = frozenset(
    {"superseded", "rejected", "archived"}
)


@dataclass(frozen=True)
class RetrievalOutcome:
    """What was retrieved, and honestly how."""

    scope: MemoryScope
    query: str
    #: `semantic` | `catalog_lexical` | `literal_scan` | `none`
    retrieval_mode: str
    canonical_health: str
    provider_health: str
    records: tuple[KnowledgeRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    omitted_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.to_dict(),
            "query": self.query,
            "retrieval_mode": self.retrieval_mode,
            "canonical_health": self.canonical_health,
            "provider_health": self.provider_health,
            "warnings": list(self.warnings),
            "omitted_count": self.omitted_count,
        }


@dataclass
class ContextPacket:
    """A complete packet, persisted before any controller-specific bounding.

    Bounding is lossy by design, so the full packet is stored and addressed by
    `packet_id`. A controller that receives a truncated projection can always
    retrieve exactly what was omitted instead of guessing whether anything was.
    """

    packet_id: str
    scope: dict[str, Any]
    query: str
    retrieval_mode: str
    canonical_health: str
    provider_health: str
    canonical_generation: int
    created_at: str
    pinned_context: list[dict[str, Any]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    omitted_count: int = 0
    packet_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "scope": self.scope,
            "query": self.query,
            "retrieval_mode": self.retrieval_mode,
            "canonical_health": self.canonical_health,
            "provider_health": self.provider_health,
            "canonical_generation": self.canonical_generation,
            "created_at": self.created_at,
            "pinned_context": self.pinned_context,
            "records": self.records,
            "warnings": self.warnings,
            "omitted_count": self.omitted_count,
            "packet_sha256": self.packet_sha256,
        }


class PacketStore:
    """Durable storage for assembled packets, addressed by packet_id."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, packet: ContextPacket) -> ContextPacket:
        payload = packet.to_dict()
        payload["packet_sha256"] = ""
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        packet.packet_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        target = self.root / f"{packet.packet_id}.json"
        target.write_text(
            json.dumps(packet.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return packet

    def get(self, packet_id: str) -> dict[str, Any]:
        if "/" in packet_id or "\\" in packet_id or ".." in packet_id:
            raise ValueError("packet_id must be an opaque identifier")
        target = self.root / f"{packet_id}.json"
        if not target.is_file():
            raise KeyError(f"context packet not found: {packet_id}")
        return json.loads(target.read_text(encoding="utf-8"))


class CanonicalMemoryService:
    """Scope-bound canonical memory. One authority, one write path."""

    def __init__(
        self,
        knowledge: KnowledgeService,
        scope: MemoryScope,
        *,
        packet_store: PacketStore | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._scope = scope
        self._packets = packet_store

    @property
    def scope(self) -> MemoryScope:
        return self._scope

    @property
    def knowledge(self) -> KnowledgeService:
        return self._knowledge

    @property
    def packets(self) -> PacketStore:
        if self._packets is None:
            raise MemoryWriteRefused("no context-packet store is configured")
        return self._packets

    # ------------------------------------------------------------------
    # writes

    def save(self, note: KnowledgeInput) -> KnowledgeRecord:
        """Create one canonical record inside the bound scope."""
        self._require_scope(note.project_id)
        payload = note.model_copy(
            update={
                "valid_from": note.valid_from or _now(),
            }
        )
        record = self._knowledge.save(payload)
        return self._stamp(record)

    def supersede(
        self, note: KnowledgeInput, supersedes_ids: list[str]
    ) -> KnowledgeRecord:
        self._require_scope(note.project_id)
        return self._knowledge.supersede(note, supersedes_ids)

    def correct(
        self,
        knowledge_id: str,
        *,
        expected_sha256: str,
        changes: dict[str, Any],
    ) -> KnowledgeRecord:
        """Metadata-only correction under compare-and-swap.

        A material change of meaning must create a replacement record instead;
        this path exists for fixing what a record *says about itself*. The
        expected hash makes a concurrent owner edit in Obsidian a refusal rather
        than an overwrite.
        """
        forbidden = {"body", "project_id", "knowledge_id", "vault_path"}
        overlap = forbidden & set(changes)
        if overlap:
            raise MemoryWriteRefused(
                f"correction may not change {sorted(overlap)}; a change of meaning "
                "creates a replacement record through supersede"
            )
        current = self._knowledge.get(self._scope_project(), knowledge_id)
        if current.content_sha256 != expected_sha256:
            raise MemoryConflict(
                f"record {knowledge_id} is at {current.content_sha256[:16]}... but the "
                f"caller expected {expected_sha256[:16]}...; re-read before correcting"
            )
        updated = current.model_copy(update={**changes, "updated_at": _now()})
        updated.revision = current.revision + 1
        from .vault import content_hash

        updated.content_sha256 = content_hash(updated)
        self._knowledge.vault.write(updated)
        self._knowledge.catalog.upsert(updated)
        return updated

    def set_status(
        self, knowledge_id: str, status: str, *, expected_sha256: str
    ) -> KnowledgeRecord:
        """Move a record to `disputed`, `rejected` or `archived`."""
        if status not in {"disputed", "rejected", "archived", "current", "proposed"}:
            raise MemoryWriteRefused(f"unsupported lifecycle transition: {status!r}")
        if status == "superseded":
            raise MemoryWriteRefused(
                "superseded is derived from a successor's link, never set directly"
            )
        changes: dict[str, Any] = {"status": status}
        if status == "archived":
            changes["valid_until"] = _now()
        return self.correct(
            knowledge_id, expected_sha256=expected_sha256, changes=changes
        )

    # ------------------------------------------------------------------
    # reads

    def get(self, knowledge_id: str) -> KnowledgeRecord:
        record = self._knowledge.get(self._scope_project(), knowledge_id)
        return self._stamp(record)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_non_authoritative: bool = False,
        provider_health: str = "degraded",
        retrieval_mode: str = "catalog_lexical",
    ) -> RetrievalOutcome:
        """Retrieve within exactly one scope, saying how the answer was produced."""
        project_id = self._scope_project()
        page = self._knowledge.search(
            project_id,
            query,
            limit=limit,
            current_only=not include_non_authoritative,
        )
        health = self._knowledge.health(project_id)
        superseding = self._knowledge.catalog.superseded_ids(project_id)

        kept: list[KnowledgeRecord] = []
        omitted = 0
        for record in page.records:
            effective = self._knowledge.effective_status(record, superseding)
            if effective in NON_AUTHORITATIVE_STATES and not include_non_authoritative:
                omitted += 1
                continue
            kept.append(self._stamp(record, effective))

        warnings: list[str] = []
        if health.status == "degraded":
            warnings.append(
                f"canonical vault is degraded: {health.malformed_count} malformed "
                f"record(s)"
            )
        if health.unadopted_count:
            warnings.append(
                f"{health.unadopted_count} owner-authored note(s) are not adopted and "
                "are excluded from authoritative context"
            )
        if page.has_more:
            warnings.append("more matches exist than the requested limit returned")

        return RetrievalOutcome(
            scope=self._scope,
            query=query,
            retrieval_mode=retrieval_mode,
            canonical_health=health.status,
            provider_health=provider_health,
            records=tuple(kept),
            warnings=tuple(warnings),
            omitted_count=omitted + (page.total - len(page.records)),
        )

    # ------------------------------------------------------------------
    # packets

    def build_packet(
        self,
        query: str,
        *,
        limit: int = 10,
        provider_health: str = "degraded",
        retrieval_mode: str = "catalog_lexical",
        pinned: list[dict[str, Any]] | None = None,
    ) -> ContextPacket:
        outcome = self.search(
            query,
            limit=limit,
            provider_health=provider_health,
            retrieval_mode=retrieval_mode,
        )
        health = self._knowledge.health(self._scope_project())
        packet = ContextPacket(
            packet_id="pkt_"
            + hashlib.sha256(
                json.dumps(
                    [self._scope.scope_key, query, _now()],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:32],
            scope=self._scope.to_dict(),
            query=query,
            retrieval_mode=outcome.retrieval_mode,
            canonical_health=outcome.canonical_health,
            provider_health=outcome.provider_health,
            canonical_generation=health.generation,
            created_at=_now(),
            pinned_context=list(pinned or []),
            records=[self.project_record(record) for record in outcome.records],
            warnings=list(outcome.warnings),
            omitted_count=outcome.omitted_count,
        )
        if self._packets is not None:
            packet = self._packets.put(packet)
        return packet

    @staticmethod
    def project_record(record: KnowledgeRecord) -> dict[str, Any]:
        """The controller-facing shape: evidence-backed, never a bare blob."""
        return {
            "knowledge_id": record.knowledge_id,
            "title": record.title,
            "kind": record.kind,
            "authority_class": record.authority_class,
            "status": record.metadata.get("effective_status", record.status),
            "declared_status": record.status,
            "review_state": record.review_state,
            "valid_from": record.valid_from,
            "valid_until": record.valid_until,
            "summary": record.summary,
            "excerpt": record.body[:600],
            "vault_path": record.vault_path,
            "content_sha256": record.content_sha256,
            "revision": record.revision,
            "supersedes_ids": list(record.supersedes_ids),
            "sources": [item.model_dump(mode="json") for item in record.sources],
            "locators": [item.model_dump(mode="json") for item in record.locators],
            "updated_at": record.updated_at,
        }

    # ------------------------------------------------------------------
    def _scope_project(self) -> str:
        if self._scope.kind != "project":
            raise MemoryWriteRefused(
                "only project memory scope is active in this lane"
            )
        return self._scope.project_id

    def _require_scope(self, project_id: str) -> None:
        if project_id != self._scope_project():
            raise MemoryWriteRefused(
                f"record claims project {project_id!r} but the bound scope is "
                f"{self._scope_project()!r}"
            )

    def _stamp(
        self, record: KnowledgeRecord, effective: str | None = None
    ) -> KnowledgeRecord:
        """Attach the derived effective status without mutating canonical state."""
        if effective is None:
            effective = self._knowledge.effective_status(record)
        record.metadata = {**record.metadata, "effective_status": effective}
        return record
