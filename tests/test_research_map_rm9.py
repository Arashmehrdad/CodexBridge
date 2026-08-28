from __future__ import annotations

from soma.research_map.backend import BackendSearchHit
from soma.research_map.search import PublishedRelation, _rerank_backend_hits


def _relation(index: int, statement: str) -> PublishedRelation:
    relation_id = f"rel_{index:064x}"
    return PublishedRelation(
        relation_id=relation_id,
        source_key=f"source:{index}",
        target_key=f"target:{index}",
        predicate="QUALIFIES",
        statement=statement,
        source_path=f"docs/research/{index:03d}.md",
        source_canonical_text_sha256="a" * 64,
        source_anchor=f"anchor {index}",
        epistemic_class="observed",
        lifecycle="current",
    )


def test_rm9_full_corpus_rerank_promotes_lexically_governing_fact() -> None:
    query = "Does bounded recurrent state alone justify calling the implementation efficient?"
    relations = {
        relation.relation_id: relation
        for relation in [
            _relation(1, "bounded recurrent state budget for addressability experiments"),
            _relation(2, "bounded state memory geometry experiment"),
            _relation(3, "recurrent mechanism capacity study"),
            _relation(4, "implementation parity before timing"),
            _relation(5, "bounded retrieval benchmark"),
            _relation(6, "state allocation experiment"),
            _relation(7, "recurrent routing requirement"),
            _relation(8, "implementation performance observation"),
            _relation(9, "bounded state control"),
            _relation(
                10,
                "The implementation must not be called efficient merely because its recurrent state is bounded.",
            ),
        ]
    }
    backend_order = tuple(
        BackendSearchHit(relation_id=f"rel_{index:064x}", score=None)
        for index in range(1, 11)
    )

    first = _rerank_backend_hits(query, backend_order, relations)
    second = _rerank_backend_hits(query, backend_order, relations)
    ranked_ids = [hit.relation_id for hit in first]

    assert ranked_ids.index(f"rel_{10:064x}") < 5
    assert ranked_ids == [hit.relation_id for hit in second]
    assert set(ranked_ids) == set(relations)


def test_rm9_rerank_preserves_backend_order_without_lexical_signal() -> None:
    relations = {
        relation.relation_id: relation
        for relation in [
            _relation(1, "alpha beta"),
            _relation(2, "gamma delta"),
            _relation(3, "epsilon zeta"),
        ]
    }
    backend_order = tuple(
        BackendSearchHit(relation_id=f"rel_{index:064x}", score=None)
        for index in range(1, 4)
    )

    ranked = _rerank_backend_hits("unrelated vocabulary", backend_order, relations)

    assert [hit.relation_id for hit in ranked] == [hit.relation_id for hit in backend_order]
