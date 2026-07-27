"""Derived, disposable index.

Everything here is rebuildable from canonical files alone. The index holds no
information that does not already exist in the vault, which is what makes the
rebuild check meaningful rather than circular.

The retrieval surface refuses an unscoped query. That mirrors the fail-closed
posture ProjectScope enforces for writes, and it is a hard error rather than an
empty result so that a caller cannot mistake refusal for absence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .contract import canonical_json
from .vault import ParsedNote, read_vault

_TOKEN = re.compile(r"[a-z0-9]+")


class UnscopedQueryError(RuntimeError):
    """Raised when a retrieval is attempted without an exact project identity."""


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class ClaimRef:
    note_id: str
    claim_key: str
    value: str
    current: bool
    superseded_by: list[str] = field(default_factory=list)


@dataclass
class MemoryIndex:
    notes: dict[str, ParsedNote]
    by_project: dict[str, list[str]]
    postings: dict[str, dict[str, int]]
    doc_lengths: dict[str, int]
    claims: list[ClaimRef]
    dangling: list[tuple[str, str]]
    malformed: list[str]
    source_status: dict[str, str]

    # -- retrieval ----------------------------------------------------------

    def search(self, query: str, project_id: str | None, limit: int = 5) -> list[str]:
        """Ranked lexical retrieval. Refuses an unscoped call."""
        if not project_id:
            raise UnscopedQueryError(
                "retrieval requires an exact project_id; identity is never inferred"
            )
        scope = set(self.by_project.get(project_id, ()))
        if not scope:
            return []
        return [
            note_id
            for note_id, _ in self._rank(query, scope)[:limit]
        ]

    def _rank(self, query: str, scope: set[str]) -> list[tuple[str, float]]:
        import math

        terms = tokenize(query)
        n = len(scope) or 1
        avg_len = sum(self.doc_lengths[d] for d in scope) / n
        k1, b = 1.5, 0.75
        scores: dict[str, float] = {}
        for term in terms:
            posting = self.postings.get(term)
            if not posting:
                continue
            in_scope = {d: f for d, f in posting.items() if d in scope}
            if not in_scope:
                continue
            idf = math.log(1 + (n - len(in_scope) + 0.5) / (len(in_scope) + 0.5))
            for doc, freq in in_scope.items():
                length = self.doc_lengths[doc] or 1
                denom = freq + k1 * (1 - b + b * length / (avg_len or 1))
                scores[doc] = scores.get(doc, 0.0) + idf * (freq * (k1 + 1)) / denom
        # Deterministic ordering: score desc, then note id asc.
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))

    # -- claim currency -----------------------------------------------------

    def current_claims(self, project_id: str | None, claim_key: str) -> list[ClaimRef]:
        if not project_id:
            raise UnscopedQueryError("claim lookup requires an exact project_id")
        scope = set(self.by_project.get(project_id, ()))
        return [
            c
            for c in self.claims
            if c.claim_key == claim_key and c.current and c.note_id in scope
        ]

    def claim_refs(self, project_id: str | None, claim_key: str) -> list[ClaimRef]:
        if not project_id:
            raise UnscopedQueryError("claim lookup requires an exact project_id")
        scope = set(self.by_project.get(project_id, ()))
        return [c for c in self.claims if c.claim_key == claim_key and c.note_id in scope]

    # -- relations ----------------------------------------------------------

    def related(self, note_id: str, relation_type: str | None = None) -> list[str]:
        note = self.notes.get(note_id)
        if not note:
            return []
        return sorted(
            target
            for rel, target in note.relations
            if relation_type is None or rel == relation_type
        )

    def reachable(self, note_id: str, relation_type: str, depth: int) -> list[str]:
        """Transitive relation walk, used by the multi-hop questions."""
        seen: set[str] = set()
        frontier = [note_id]
        for _ in range(depth):
            nxt: list[str] = []
            for current in frontier:
                for target in self.related(current, relation_type):
                    if target not in seen:
                        seen.add(target)
                        nxt.append(target)
            frontier = nxt
        return sorted(seen)

    def referrers(self, note_id: str) -> list[str]:
        return sorted(
            other.note_id
            for other in self.notes.values()
            if any(target == note_id for _, target in other.relations)
        )

    # -- identity -----------------------------------------------------------

    def fingerprint(self) -> str:
        """Stable digest of the derived structure, for rebuild comparison."""
        payload = {
            "notes": sorted(self.notes),
            "by_project": {k: sorted(v) for k, v in sorted(self.by_project.items())},
            "claims": sorted(
                [c.note_id, c.claim_key, c.value, c.current, sorted(c.superseded_by)]
                for c in self.claims
            ),
            "dangling": sorted([a, b] for a, b in self.dangling),
            "malformed": sorted(self.malformed),
            "source_status": dict(sorted(self.source_status.items())),
            "postings": {
                term: dict(sorted(docs.items()))
                for term, docs in sorted(self.postings.items())
            },
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_index(vault_root: Path, repo_root: Path | None = None) -> MemoryIndex:
    """Build the derived index from canonical files only."""
    parsed = read_vault(vault_root)
    notes = {n.note_id: n for n in parsed}

    by_project: dict[str, list[str]] = {}
    postings: dict[str, dict[str, int]] = {}
    doc_lengths: dict[str, int] = {}
    malformed: list[str] = []

    for note in parsed:
        if not note.frontmatter_ok:
            malformed.append(note.note_id)
        if note.project_id:
            by_project.setdefault(note.project_id, []).append(note.note_id)
        # Indexed text is the note's own content only. Question text and golden
        # answers are never part of this, which is what keeps the index free of
        # an oracle.
        tokens = tokenize(f"{note.title} {note.body}")
        doc_lengths[note.note_id] = len(tokens)
        for token in tokens:
            postings.setdefault(token, {})
            postings[token][note.note_id] = postings[token].get(note.note_id, 0) + 1

    for ids in by_project.values():
        ids.sort()

    # Supersession: full replaces every claim of the predecessor; claim-level
    # replaces exactly one, leaving the rest of that note current.
    fully_superseded: dict[str, list[str]] = {}
    claim_superseded: dict[tuple[str, str], list[str]] = {}
    for note in parsed:
        for target in note.supersedes:
            fully_superseded.setdefault(target, []).append(note.note_id)
        for target, claim_key in note.supersedes_claims:
            claim_superseded.setdefault((target, claim_key), []).append(note.note_id)

    claims: list[ClaimRef] = []
    for note in parsed:
        for key, value in sorted(note.claims.items()):
            killers = list(fully_superseded.get(note.note_id, ()))
            killers += list(claim_superseded.get((note.note_id, key), ()))
            claims.append(
                ClaimRef(
                    note_id=note.note_id,
                    claim_key=key,
                    value=value,
                    current=not killers,
                    superseded_by=sorted(set(killers)),
                )
            )

    known = set(notes)
    dangling: list[tuple[str, str]] = []
    for note in parsed:
        targets = {t for _, t in note.relations} | set(note.wikilink_targets)
        for target in sorted(targets):
            if target not in known:
                dangling.append((note.note_id, target))

    source_status: dict[str, str] = {}
    for note in parsed:
        if not note.source:
            source_status[note.note_id] = "missing"
        elif repo_root is None:
            source_status[note.note_id] = "unchecked"
        elif (repo_root / note.source).exists():
            source_status[note.note_id] = "resolves"
        else:
            source_status[note.note_id] = "unresolved"

    return MemoryIndex(
        notes=notes,
        by_project=by_project,
        postings=postings,
        doc_lengths=doc_lengths,
        claims=claims,
        dangling=sorted(dangling),
        malformed=sorted(malformed),
        source_status=source_status,
    )
