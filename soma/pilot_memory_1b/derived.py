"""Optional local derived retrieval, reported separately from lexical.

This is a corpus-only association expansion: term co-occurrence is learned from
note bodies and used to widen a query. No network call, no hosted model, no
downloaded weights, and nothing derived from the question set. It is optional,
disposable, and rebuildable like every other derived structure here.

It exists to answer one narrow question honestly: can a purely local method,
with no external semantics, close the paraphrase gap that plain lexical
matching leaves open? If it cannot, that is a finding rather than a defect.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .index import MemoryIndex, UnscopedQueryError, tokenize

#: Terms this common carry no discriminating signal and would blur expansion.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    to was were which with without not no than then this these those there their
    they can could should would will may might must do does did done been being
    into over under after before during while when where what who whom how why
    all any both each few more most other some such only own same so too very
    one two three run runs record records note notes""".split()
)


@dataclass
class AssociationModel:
    """Term -> related terms, learned from note bodies only."""

    neighbours: dict[str, list[tuple[str, float]]]
    expansion_width: int
    expansion_weight: float

    def expand(self, query: str) -> Counter[str]:
        weights: Counter[str] = Counter()
        terms = [t for t in tokenize(query) if t not in _STOPWORDS]
        for term in terms:
            weights[term] += 1.0
        for term in terms:
            for neighbour, strength in self.neighbours.get(term, ())[: self.expansion_width]:
                if neighbour in weights:
                    continue
                weights[neighbour] += self.expansion_weight * strength
        return weights


def build_association_model(
    index: MemoryIndex,
    *,
    expansion_width: int = 4,
    expansion_weight: float = 0.35,
    min_document_frequency: int = 2,
) -> AssociationModel:
    """Learn term association from the indexed corpus. Deterministic."""
    doc_terms: dict[str, set[str]] = {}
    for note_id, note in index.notes.items():
        terms = {
            t for t in tokenize(f"{note.title} {note.body}") if t not in _STOPWORDS
        }
        doc_terms[note_id] = terms

    document_frequency: Counter[str] = Counter()
    for terms in doc_terms.values():
        document_frequency.update(terms)

    vocabulary = {
        t for t, df in document_frequency.items() if df >= min_document_frequency
    }
    total_docs = len(doc_terms) or 1

    co: dict[str, Counter[str]] = {}
    for terms in doc_terms.values():
        scoped = sorted(terms & vocabulary)
        for i, left in enumerate(scoped):
            bucket = co.setdefault(left, Counter())
            for right in scoped[i + 1:]:
                bucket[right] += 1
                co.setdefault(right, Counter())[left] += 1

    neighbours: dict[str, list[tuple[str, float]]] = {}
    for term, bucket in co.items():
        df_term = document_frequency[term]
        scored: list[tuple[str, float]] = []
        for other, joint in bucket.items():
            df_other = document_frequency[other]
            # Normalized pointwise mutual information keeps very common terms
            # from dominating every expansion.
            p_joint = joint / total_docs
            p_term = df_term / total_docs
            p_other = df_other / total_docs
            if p_joint <= 0 or p_term <= 0 or p_other <= 0:
                continue
            pmi = math.log(p_joint / (p_term * p_other))
            denom = -math.log(p_joint)
            if denom <= 0:
                continue
            npmi = pmi / denom
            if npmi > 0:
                scored.append((other, npmi))
        # Deterministic: strength desc, then term asc.
        neighbours[term] = sorted(scored, key=lambda kv: (-kv[1], kv[0]))

    return AssociationModel(
        neighbours=neighbours,
        expansion_width=expansion_width,
        expansion_weight=expansion_weight,
    )


def derived_search(
    index: MemoryIndex,
    model: AssociationModel,
    query: str,
    project_id: str | None,
    limit: int = 5,
) -> list[str]:
    """Expanded retrieval. Fails closed exactly like the lexical surface."""
    if not project_id:
        raise UnscopedQueryError(
            "retrieval requires an exact project_id; identity is never inferred"
        )
    scope = set(index.by_project.get(project_id, ()))
    if not scope:
        return []

    weights = model.expand(query)
    n = len(scope)
    avg_len = sum(index.doc_lengths[d] for d in scope) / (n or 1)
    k1, b = 1.5, 0.75
    scores: dict[str, float] = {}
    for term, weight in weights.items():
        posting = index.postings.get(term)
        if not posting:
            continue
        in_scope = {d: f for d, f in posting.items() if d in scope}
        if not in_scope:
            continue
        idf = math.log(1 + (n - len(in_scope) + 0.5) / (len(in_scope) + 0.5))
        for doc, freq in in_scope.items():
            length = index.doc_lengths[doc] or 1
            denom = freq + k1 * (1 - b + b * length / (avg_len or 1))
            scores[doc] = scores.get(doc, 0.0) + weight * idf * (freq * (k1 + 1)) / denom
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [note_id for note_id, _ in ranked[:limit]]
