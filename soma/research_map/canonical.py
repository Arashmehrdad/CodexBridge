from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any

_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_canonical_text(value: str | bytes) -> str:
    """Decode strict UTF-8 when needed and normalize all line endings to LF."""
    text = value.decode("utf-8", errors="strict") if isinstance(value, bytes) else value
    return text.replace("\r\n", "\n").replace("\r", "\n")


def canonical_text_sha256(value: str | bytes) -> str:
    text = normalize_canonical_text(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=True, by_alias=True)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes without backend-specific formatting."""
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_repo_relative_path(value: str) -> str:
    """Normalize a repository-relative path and reject traversal/runtime namespaces."""
    if not isinstance(value, str):
        raise TypeError("repository-relative path must be a string")
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise ValueError("path must be repository-relative")
    raw_parts = raw.split("/")
    first = raw_parts[0]
    if ":" in first:
        raise ValueError("path must not contain a drive prefix")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("path must not contain traversal or empty segments")
    candidate = PurePosixPath(raw)
    lowered = {part.casefold() for part in candidate.parts}
    if ".git" in lowered or ".soma" in lowered:
        raise ValueError("path must not enter reserved repository runtime namespaces")
    return candidate.as_posix()


def _hash_identity(prefix: str, *parts: str) -> str:
    payload = "\x00".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


def logical_record_id(source_path: str) -> str:
    return _hash_identity("rrec", normalize_repo_relative_path(source_path))


def record_version_id(logical_id: str, canonical_text_hash: str) -> str:
    if not logical_id.startswith("rrec_"):
        raise ValueError("logical_id must be a research record identity")
    digest = canonical_text_hash.casefold()
    if not _HEX_64_RE.fullmatch(digest):
        raise ValueError("canonical_text_hash must be a SHA-256 digest")
    return _hash_identity("rver", logical_id, digest)


def relation_id(
    source_path: str,
    subject_key: str,
    predicate: str,
    object_key: str,
) -> str:
    normalized_path = normalize_repo_relative_path(source_path)
    values = [subject_key, predicate, object_key]
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError("relation identity fields must be non-empty strings")
    return _hash_identity(
        "rel",
        normalized_path,
        subject_key.strip(),
        predicate.strip(),
        object_key.strip(),
    )
