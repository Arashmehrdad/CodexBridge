"""Replaceable retrieval-index contract and deterministic in-memory implementation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RagFlowDocument:
    document_id: str
    name: str
    run: str | None = None
    progress: float | None = None
    progress_message: str = ""
    chunk_count: int | None = None
    token_count: int | None = None


@dataclass(frozen=True, slots=True)
class RagFlowRetrievedChunk:
    chunk_id: str
    document_id: str
    content: str
    similarity: float | None = None
    vector_similarity: float | None = None
    term_similarity: float | None = None
    document_name: str = ""
    dataset_id: str = ""
    positions: tuple[object, ...] = ()


class RagFlowGateway(Protocol):
    """Small disposable-index surface required by manual research preservation."""

    def upload_document(self, dataset_id: str, path: Path) -> RagFlowDocument: ...

    def parse_documents(
        self, dataset_id: str, document_ids: tuple[str, ...]
    ) -> None: ...

    def list_documents(
        self,
        dataset_id: str,
        *,
        keywords: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[RagFlowDocument, ...]: ...

    def retrieve(
        self,
        question: str,
        *,
        dataset_ids: tuple[str, ...] = (),
        document_ids: tuple[str, ...] = (),
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[RagFlowRetrievedChunk, ...]: ...


class InMemoryRagFlowGateway:
    """Fake-friendly index for tests and deployments without live RAGFlow."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, RagFlowDocument]] = {}
        self._content: dict[str, bytes] = {}

    def upload_document(self, dataset_id: str, path: Path) -> RagFlowDocument:
        _require_text("dataset_id", dataset_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        document = RagFlowDocument(document_id=f"doc_{uuid4().hex}", name=path.name)
        self._documents.setdefault(dataset_id, {})[document.document_id] = document
        self._content[document.document_id] = path.read_bytes()
        return document

    def parse_documents(self, dataset_id: str, document_ids: tuple[str, ...]) -> None:
        if not document_ids:
            raise ValueError("document_ids must not be empty")
        documents = self._documents.get(dataset_id, {})
        for document_id in document_ids:
            document = documents.get(document_id)
            if document is None:
                raise KeyError(f"unknown RAGFlow document: {document_id}")
            documents[document_id] = replace(
                document, run="DONE", progress=1.0, chunk_count=1
            )

    def list_documents(
        self,
        dataset_id: str,
        *,
        keywords: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[RagFlowDocument, ...]:
        if page <= 0 or page_size <= 0:
            raise ValueError("page and page_size must be positive")
        documents = tuple(self._documents.get(dataset_id, {}).values())
        if keywords:
            folded = keywords.casefold()
            documents = tuple(
                item for item in documents if folded in item.name.casefold()
            )
        start = (page - 1) * page_size
        return documents[start : start + page_size]

    def retrieve(
        self,
        question: str,
        *,
        dataset_ids: tuple[str, ...] = (),
        document_ids: tuple[str, ...] = (),
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[RagFlowRetrievedChunk, ...]:
        if not question.strip():
            raise ValueError("question must not be empty")
        if not dataset_ids and not document_ids:
            raise ValueError("dataset_ids or document_ids must be provided")
        if page <= 0 or page_size <= 0:
            raise ValueError("page and page_size must be positive")
        selected: list[tuple[str, RagFlowDocument]] = []
        for dataset_id, documents in self._documents.items():
            if dataset_ids and dataset_id not in dataset_ids:
                continue
            for document in documents.values():
                if document_ids and document.document_id not in document_ids:
                    continue
                selected.append((dataset_id, document))
        chunks = [
            RagFlowRetrievedChunk(
                chunk_id=f"chunk_{document.document_id}",
                document_id=document.document_id,
                content=self._content[document.document_id].decode(
                    "utf-8", errors="replace"
                ),
                similarity=1.0,
                document_name=document.name,
                dataset_id=dataset_id,
                positions=(0,),
            )
            for dataset_id, document in selected
        ]
        start = (page - 1) * page_size
        return tuple(chunks[start : start + page_size])


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
