from __future__ import annotations

import asyncio
import json
import math
import re
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend import ResearchMapBackend, ResearchMapBackendError
from .canonical import (
    canonical_text_sha256,
    normalize_canonical_text,
    normalize_repo_relative_path,
)
from .generation import (
    GENERATION_SCHEMA,
    RELATIONS_FILENAME,
    CurrentGeneration,
    ResearchMapGenerationError,
    generation_directory,
    load_current_generation,
)
from .graphiti_backend import GraphitiFalkorBackend, graphiti_projection_contract_sha256
from .service import ResearchMapHealthState, ResearchMapScan
from .sidecars import MAX_SOURCE_BYTES

RESEARCH_MAP_SEARCH_VERSION = "soma.research-map.search.v2"
_SEARCH_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_BM25_K1 = 1.2
_BM25_B = 0.75
_SEMANTIC_RANK_WEIGHT = 0.5


class ResearchMapSearchError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


BackendFactory = Callable[[str, str], ResearchMapBackend]


@dataclass(frozen=True, slots=True)
class PublishedRelation:
    relation_id: str
    source_key: str
    target_key: str
    predicate: str
    statement: str
    source_path: str
    source_canonical_text_sha256: str
    source_anchor: str
    epistemic_class: str
    lifecycle: str


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    rank: int
    relation_id: str
    score: float | None
    source_key: str
    target_key: str
    predicate: str
    statement: str
    source_path: str
    source_canonical_text_sha256: str
    source_anchor: str
    epistemic_class: str
    lifecycle: str
    source_verification: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "relation_id": self.relation_id,
            "score": self.score,
            "source_key": self.source_key,
            "target_key": self.target_key,
            "predicate": self.predicate,
            "statement": self.statement,
            "source_path": self.source_path,
            "source_canonical_text_sha256": self.source_canonical_text_sha256,
            "source_anchor": self.source_anchor,
            "epistemic_class": self.epistemic_class,
            "lifecycle": self.lifecycle,
            "source_verification": self.source_verification,
        }


def _default_backend_factory(repository_uid: str, database: str) -> ResearchMapBackend:
    return GraphitiFalkorBackend(repository_uid=repository_uid, database=database)


def _search_tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in _SEARCH_TOKEN_RE.findall(text.casefold()) if len(token) > 1)


def _relation_search_text(relation: PublishedRelation) -> str:
    return (
        f"{relation.statement} {relation.source_anchor} {relation.source_key} "
        f"{relation.target_key} {relation.predicate}"
    )


def _rerank_backend_hits(
    query: str,
    hits: tuple[object, ...],
    relations: dict[str, PublishedRelation],
) -> tuple[object, ...]:
    """Blend backend semantic order with deterministic BM25 over immutable relation text."""
    deduped: list[object] = []
    seen: set[str] = set()
    for hit in hits:
        relation_id = str(getattr(hit, "relation_id", "")).casefold()
        if relation_id not in relations:
            raise ResearchMapSearchError(
                "backend_drift",
                f"backend returned a relation outside the published generation: {relation_id}",
            )
        if relation_id in seen:
            continue
        seen.add(relation_id)
        deduped.append(hit)
    if len(deduped) < 2:
        return tuple(deduped)

    query_tokens = _search_tokens(query)
    if not query_tokens:
        return tuple(deduped)

    corpus_tokens = {
        relation_id: _search_tokens(_relation_search_text(relation))
        for relation_id, relation in relations.items()
    }
    document_count = len(corpus_tokens)
    if document_count == 0:
        return tuple(deduped)
    average_length = max(
        sum(len(tokens) for tokens in corpus_tokens.values()) / document_count,
        1.0,
    )
    document_frequency: Counter[str] = Counter()
    for tokens in corpus_tokens.values():
        document_frequency.update(set(tokens))

    lexical_scores: dict[str, float] = {}
    for hit in deduped:
        relation_id = str(hit.relation_id).casefold()
        tokens = corpus_tokens[relation_id]
        term_frequency = Counter(tokens)
        document_length = len(tokens)
        score = 0.0
        for term in query_tokens:
            frequency = term_frequency.get(term, 0)
            if not frequency:
                continue
            frequency_docs = document_frequency.get(term, 0)
            inverse_document_frequency = math.log(
                1.0 + (document_count - frequency_docs + 0.5) / (frequency_docs + 0.5)
            )
            denominator = frequency + _BM25_K1 * (
                1.0 - _BM25_B + _BM25_B * document_length / average_length
            )
            score += inverse_document_frequency * (
                frequency * (_BM25_K1 + 1.0) / denominator
            )
        lexical_scores[relation_id] = score

    maximum_lexical = max(lexical_scores.values(), default=0.0)
    if maximum_lexical <= 0.0:
        return tuple(deduped)

    candidate_count = len(deduped)
    scored: list[tuple[float, int, object]] = []
    for index, hit in enumerate(deduped):
        relation_id = str(hit.relation_id).casefold()
        semantic_rank_score = 1.0 - index / (candidate_count - 1)
        lexical_score = lexical_scores[relation_id] / maximum_lexical
        combined = (
            _SEMANTIC_RANK_WEIGHT * semantic_rank_score
            + (1.0 - _SEMANTIC_RANK_WEIGHT) * lexical_score
        )
        scored.append((combined, index, hit))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(item[2] for item in scored)


def _require_published_current(
    repository_root: Path,
    scan: ResearchMapScan,
) -> CurrentGeneration:
    if scan.health_state is ResearchMapHealthState.NOT_ADOPTED:
        raise ResearchMapSearchError("not_adopted", "research map is not adopted")
    if scan.health_state is ResearchMapHealthState.DISABLED:
        raise ResearchMapSearchError("disabled", "research map is disabled")
    if scan.health_state is not ResearchMapHealthState.HEALTHY or scan.issues:
        raise ResearchMapSearchError(
            "semantic_state_degraded",
            "research map semantic state is degraded",
        )
    if not scan.coverage.complete:
        raise ResearchMapSearchError(
            "coverage_incomplete",
            "research map coverage must be complete before semantic search",
        )
    try:
        current = load_current_generation(repository_root)
    except ResearchMapGenerationError as exc:
        raise ResearchMapSearchError("published_generation_degraded", str(exc)) from exc
    if current is None:
        raise ResearchMapSearchError(
            "published_generation_missing",
            "no verified research-map generation is published",
        )
    if (
        current.repository_uid != scan.repository_uid
        or current.semantic_desired_state_sha256 != scan.semantic_desired_state_sha256
        or current.projection_contract_sha256 != graphiti_projection_contract_sha256()
    ):
        raise ResearchMapSearchError(
            "published_generation_stale",
            "published generation does not match the current reviewed semantic state",
        )
    return current


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ResearchMapSearchError(
            "published_relation_artifact_invalid",
            f"published relation is missing a valid {key}",
        )
    return value


def _load_published_relations(
    repository_root: Path,
    current: CurrentGeneration,
) -> dict[str, PublishedRelation]:
    path = generation_directory(repository_root, current.generation) / RELATIONS_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchMapSearchError(
            "published_relation_artifact_invalid",
            "published RELATIONS.json cannot be decoded",
        ) from exc
    if not isinstance(payload, dict):
        raise ResearchMapSearchError(
            "published_relation_artifact_invalid",
            "published RELATIONS.json must be an object",
        )
    expected_metadata = {
        "schema": GENERATION_SCHEMA,
        "repository_uid": current.repository_uid,
        "semantic_desired_state_sha256": current.semantic_desired_state_sha256,
        "projection_contract_sha256": current.projection_contract_sha256,
        "database": current.database,
    }
    for key, expected in expected_metadata.items():
        if payload.get(key) != expected:
            raise ResearchMapSearchError(
                "published_relation_artifact_invalid",
                f"published RELATIONS.json metadata mismatch: {key}",
            )
    raw_relations = payload.get("relations")
    if not isinstance(raw_relations, list) or len(raw_relations) != current.relation_count:
        raise ResearchMapSearchError(
            "published_relation_artifact_invalid",
            "published relation count does not match CURRENT",
        )

    relations: dict[str, PublishedRelation] = {}
    for raw in raw_relations:
        if not isinstance(raw, dict):
            raise ResearchMapSearchError(
                "published_relation_artifact_invalid",
                "published relation entry must be an object",
            )
        relation_id = _required_string(raw, "relation_id").casefold()
        if relation_id in relations:
            raise ResearchMapSearchError(
                "published_relation_artifact_invalid",
                f"duplicate published relation identity: {relation_id}",
            )
        try:
            source_path = normalize_repo_relative_path(
                _required_string(raw, "source_path")
            )
        except (TypeError, ValueError) as exc:
            raise ResearchMapSearchError(
                "published_relation_artifact_invalid",
                f"invalid published source path for {relation_id}",
            ) from exc
        source_hash = _required_string(raw, "source_canonical_text_sha256").casefold()
        if len(source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in source_hash):
            raise ResearchMapSearchError(
                "published_relation_artifact_invalid",
                f"invalid published source hash for {relation_id}",
            )
        relations[relation_id] = PublishedRelation(
            relation_id=relation_id,
            source_key=_required_string(raw, "source_key"),
            target_key=_required_string(raw, "target_key"),
            predicate=_required_string(raw, "predicate"),
            statement=_required_string(raw, "statement"),
            source_path=source_path,
            source_canonical_text_sha256=source_hash,
            source_anchor=_required_string(raw, "source_anchor"),
            epistemic_class=_required_string(raw, "epistemic_class"),
            lifecycle=_required_string(raw, "lifecycle"),
        )
    return relations


def _verify_source(repository_root: Path, relation: PublishedRelation) -> None:
    source_path = repository_root / relation.source_path
    try:
        resolved = source_path.resolve(strict=True)
        resolved.relative_to(repository_root)
        if not resolved.is_file():
            raise OSError("source is not a file")
        if resolved.stat().st_size > MAX_SOURCE_BYTES:
            raise OSError("source exceeds the research-map source-size limit")
        raw = resolved.read_bytes()
        text = normalize_canonical_text(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ResearchMapSearchError(
            "source_verification_failed",
            f"published search candidate source is unavailable: {relation.source_path}",
        ) from exc
    if canonical_text_sha256(text) != relation.source_canonical_text_sha256:
        raise ResearchMapSearchError(
            "source_verification_failed",
            f"published search candidate source hash is stale: {relation.source_path}",
        )
    if relation.source_anchor not in text:
        raise ResearchMapSearchError(
            "source_verification_failed",
            f"published search candidate anchor is no longer exact: {relation.source_path}",
        )


async def search_published_generation_async(
    repository_root: str | Path,
    scan: ResearchMapScan,
    *,
    query: str,
    limit: int,
    include_noncurrent: bool,
    backend_factory: BackendFactory | None = None,
) -> tuple[CurrentGeneration, tuple[SearchCandidate, ...]]:
    if not query.strip():
        raise ResearchMapSearchError("invalid_query", "research-map search query must not be blank")
    if limit < 1 or limit > 20:
        raise ResearchMapSearchError("invalid_limit", "research-map search limit must be between 1 and 20")

    root = Path(repository_root).resolve()
    current = _require_published_current(root, scan)
    relations = _load_published_relations(root, current)
    expected_manifest = tuple(sorted(relations))
    backend = (backend_factory or _default_backend_factory)(current.repository_uid, current.database)
    try:
        actual_manifest = tuple(sorted(await backend.read_relation_manifest()))
        if actual_manifest != expected_manifest:
            raise ResearchMapSearchError(
                "backend_drift",
                "live backend relation manifest does not match the published generation",
            )
        fetch_limit = min(100, max(limit * 4, 20))
        hits = await backend.search(query, limit=fetch_limit)
    except ResearchMapSearchError:
        raise
    except ResearchMapBackendError as exc:
        raise ResearchMapSearchError("backend_unavailable", str(exc)) from exc
    except Exception as exc:
        raise ResearchMapSearchError("backend_runtime_failure", str(exc)) from exc
    finally:
        with suppress(ResearchMapBackendError, OSError, RuntimeError):
            await backend.close()

    ordered_hits = _rerank_backend_hits(query, hits, relations)
    selected: list[SearchCandidate] = []
    seen: set[str] = set()
    for hit in ordered_hits:
        relation_id = hit.relation_id.casefold()
        if relation_id in seen:
            continue
        seen.add(relation_id)
        relation = relations.get(relation_id)
        if relation is None:
            raise ResearchMapSearchError(
                "backend_drift",
                f"backend returned a relation outside the published generation: {relation_id}",
            )
        if not include_noncurrent and relation.lifecycle != "current":
            continue
        _verify_source(root, relation)
        selected.append(
            SearchCandidate(
                rank=len(selected) + 1,
                relation_id=relation.relation_id,
                score=hit.score,
                source_key=relation.source_key,
                target_key=relation.target_key,
                predicate=relation.predicate,
                statement=relation.statement,
                source_path=relation.source_path,
                source_canonical_text_sha256=relation.source_canonical_text_sha256,
                source_anchor=relation.source_anchor,
                epistemic_class=relation.epistemic_class,
                lifecycle=relation.lifecycle,
                source_verification="verified",
            )
        )
        if len(selected) >= limit:
            break
    return current, tuple(selected)


def search_published_generation(
    repository_root: str | Path,
    scan: ResearchMapScan,
    *,
    query: str,
    limit: int,
    include_noncurrent: bool,
    backend_factory: BackendFactory | None = None,
) -> tuple[CurrentGeneration, tuple[SearchCandidate, ...]]:
    try:
        return asyncio.run(
            search_published_generation_async(
                repository_root,
                scan,
                query=query,
                limit=limit,
                include_noncurrent=include_noncurrent,
                backend_factory=backend_factory,
            )
        )
    except ResearchMapSearchError:
        raise
    except (ResearchMapBackendError, ResearchMapGenerationError) as exc:
        raise ResearchMapSearchError("backend_or_generation_failure", str(exc)) from exc
    except Exception as exc:
        raise ResearchMapSearchError("backend_runtime_failure", str(exc)) from exc
