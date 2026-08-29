from __future__ import annotations

import hashlib
import sqlite3
import struct
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

EMBEDDING_CACHE_SCHEMA = "soma.research-map.embedding-cache.v1"
EMBEDDING_CACHE_FILENAME = "embedding-cache.sqlite3"


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    vectors: tuple[tuple[float, ...], ...]
    hits: int
    misses: int
    lookup_seconds: float
    compute_seconds: float
    store_seconds: float
    cache_available: bool


class EmbeddingCache:
    """Repo-local deterministic cache for non-authoritative embedding reuse.

    Cache identity is the projection-contract namespace plus the exact UTF-8
    input text hash. Cached values are only a performance optimization: any
    SQLite/cache-shape failure falls back to fresh embedding computation.
    """

    def __init__(self, path: str | Path, *, namespace: str, dimension: int) -> None:
        self.path = Path(path)
        self.namespace = namespace
        self.dimension = dimension

    @staticmethod
    def _text_sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="strict")).hexdigest()

    def _encode(self, vector: Sequence[float]) -> bytes:
        if len(vector) != self.dimension:
            raise ValueError(
                f"embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
            )
        return struct.pack(f"<{self.dimension}f", *(float(value) for value in vector))

    def _decode(self, payload: bytes) -> tuple[float, ...] | None:
        expected_size = self.dimension * 4
        if len(payload) != expected_size:
            return None
        return tuple(struct.unpack(f"<{self.dimension}f", payload))

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            "namespace TEXT NOT NULL, "
            "text_sha256 TEXT NOT NULL, "
            "input_text TEXT NOT NULL, "
            "dimension INTEGER NOT NULL, "
            "vector BLOB NOT NULL, "
            "PRIMARY KEY(namespace, text_sha256)"
            ")"
        )
        return connection

    def _load_namespace(self) -> dict[str, tuple[str, tuple[float, ...]]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT text_sha256, input_text, dimension, vector "
                "FROM embeddings WHERE namespace = ?",
                (self.namespace,),
            ).fetchall()
        finally:
            connection.close()
        loaded: dict[str, tuple[str, tuple[float, ...]]] = {}
        for text_sha256, input_text, dimension, vector_blob in rows:
            if dimension != self.dimension or not isinstance(vector_blob, bytes):
                continue
            decoded = self._decode(vector_blob)
            if decoded is not None:
                loaded[str(text_sha256)] = (str(input_text), decoded)
        return loaded

    def store_many(self, pairs: Sequence[tuple[str, Sequence[float]]]) -> int:
        if not pairs:
            return 0
        rows = [
            (
                self.namespace,
                self._text_sha256(text),
                text,
                self.dimension,
                self._encode(vector),
            )
            for text, vector in pairs
        ]
        connection = self._connect()
        try:
            connection.executemany(
                "INSERT INTO embeddings(namespace, text_sha256, input_text, dimension, vector) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(namespace, text_sha256) DO UPDATE SET "
                "input_text=excluded.input_text, dimension=excluded.dimension, vector=excluded.vector",
                rows,
            )
            connection.commit()
        finally:
            connection.close()
        return len(rows)

    def resolve(
        self,
        texts: Sequence[str],
        compute: Callable[[list[str]], Sequence[Sequence[float]]],
    ) -> EmbeddingBatchResult:
        if not texts:
            return EmbeddingBatchResult((), 0, 0, 0.0, 0.0, 0.0, True)

        lookup_started = time.perf_counter()
        try:
            cached = self._load_namespace()
            cache_available = True
        except sqlite3.DatabaseError:
            cached = {}
            cache_available = False
        lookup_seconds = time.perf_counter() - lookup_started

        resolved: dict[tuple[str, str], tuple[float, ...]] = {}
        missing: dict[tuple[str, str], str] = {}
        hits = 0
        misses = 0
        ordered_keys: list[tuple[str, str]] = []
        for text in texts:
            text_sha256 = self._text_sha256(text)
            key = (text_sha256, text)
            ordered_keys.append(key)
            cached_row = cached.get(text_sha256)
            if cached_row is not None and cached_row[0] == text:
                resolved[key] = cached_row[1]
                hits += 1
            else:
                missing.setdefault(key, text)
                misses += 1

        compute_seconds = 0.0
        store_seconds = 0.0
        if missing:
            missing_items = list(missing.items())
            missing_texts = [text for _key, text in missing_items]
            compute_started = time.perf_counter()
            computed = list(compute(missing_texts))
            compute_seconds = time.perf_counter() - compute_started
            if len(computed) != len(missing_items):
                raise ValueError("embedding provider returned an unexpected vector count")
            new_pairs: list[tuple[str, Sequence[float]]] = []
            for (key, text), vector in zip(missing_items, computed, strict=True):
                encoded = self._encode(vector)
                decoded = self._decode(encoded)
                if decoded is None:
                    raise ValueError("embedding provider returned an invalid vector payload")
                resolved[key] = decoded
                new_pairs.append((text, decoded))
            if cache_available:
                store_started = time.perf_counter()
                try:
                    self.store_many(new_pairs)
                except sqlite3.DatabaseError:
                    cache_available = False
                store_seconds = time.perf_counter() - store_started

        return EmbeddingBatchResult(
            vectors=tuple(resolved[key] for key in ordered_keys),
            hits=hits,
            misses=misses,
            lookup_seconds=lookup_seconds,
            compute_seconds=compute_seconds,
            store_seconds=store_seconds,
            cache_available=cache_available,
        )
