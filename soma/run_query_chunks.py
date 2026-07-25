from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .safety import redact_secret_values


RUN_QUERY_CHUNK_CHARACTERS = 16 * 1024
RUN_REFERENCE_PREFIX = "__soma_run_query_run__:"
_CURSOR_VERSION = 2
_LIST_REFERENCE_PREFIX = "__soma_run_query_list__:"
_SNAPSHOT_ROOT = Path(tempfile.gettempdir()) / "soma-run-query-snapshots"
_SNAPSHOT_MAX_AGE_SECONDS = 60 * 60
_SNAPSHOT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOTS: dict[str, "SnapshotMetadata"] = {}


@dataclass(frozen=True)
class ChunkReference:
    resource_id: str
    cursor: str


@dataclass(frozen=True)
class SnapshotMetadata:
    operation: str
    resource_id: str
    payload_sha256: str
    total_characters: int
    path: Path


def _urlsafe_encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_decode(value: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
        ValueError,
        binascii.Error,
    ) as exc:
        raise ValueError("Invalid run-query reference") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid run-query reference")
    return payload


def encode_run_reference(run_id: str, cursor: str = "") -> str:
    return RUN_REFERENCE_PREFIX + _urlsafe_encode(
        {"run_id": run_id, "cursor": cursor}
    )


def decode_run_reference(value: str) -> ChunkReference | None:
    if not value.startswith(RUN_REFERENCE_PREFIX):
        return None
    payload = _urlsafe_decode(value[len(RUN_REFERENCE_PREFIX) :])
    run_id = str(payload.get("run_id") or "")
    cursor = str(payload.get("cursor") or "")
    if not run_id:
        raise ValueError("Run-query reference is missing run_id")
    return ChunkReference(resource_id=run_id, cursor=cursor)


def encode_list_reference(repo_name: str, cursor: str = "") -> str:
    return _LIST_REFERENCE_PREFIX + _urlsafe_encode(
        {"repo_name": repo_name, "cursor": cursor}
    )


def decode_list_reference(value: str | None) -> ChunkReference | None:
    normalized = str(value or "")
    if not normalized.startswith(_LIST_REFERENCE_PREFIX):
        return None
    payload = _urlsafe_decode(normalized[len(_LIST_REFERENCE_PREFIX) :])
    return ChunkReference(
        resource_id=str(payload.get("repo_name") or ""),
        cursor=str(payload.get("cursor") or ""),
    )


def list_resource_id(repo_name: str, status: str, limit: int) -> str:
    serialized = json.dumps(
        {"repo_name": repo_name, "status": status, "limit": int(limit)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _redact_value(value: Any, key: str = "") -> Any:
    normalized_key = key.lower().replace("-", "_")
    if isinstance(value, str):
        if any(
            marker in normalized_key
            for marker in ("password", "secret", "token", "credential", "api_key", "apikey")
        ):
            return "[REDACTED]"
        return redact_secret_values(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(item_key): _redact_value(item, str(item_key)) for item_key, item in value.items()}
    return value


def redact_payload(value: Any) -> Any:
    """Return the canonical recursively redacted public representation."""
    return _redact_value(value)


def _snapshot_path(snapshot_id: str) -> Path:
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError("Invalid run-query snapshot identifier")
    return _SNAPSHOT_ROOT / f"{snapshot_id}.json"


def _prune_snapshots_locked(now: float) -> None:
    cutoff = now - _SNAPSHOT_MAX_AGE_SECONDS
    for snapshot_id, metadata in list(_SNAPSHOTS.items()):
        try:
            expired = metadata.path.stat().st_mtime < cutoff
        except OSError:
            expired = True
        if expired:
            _SNAPSHOTS.pop(snapshot_id, None)
            try:
                metadata.path.unlink(missing_ok=True)
            except OSError:
                pass
    if not _SNAPSHOT_ROOT.exists():
        return
    tracked_paths = {metadata.path for metadata in _SNAPSHOTS.values()}
    for path in _SNAPSHOT_ROOT.glob("*.json"):
        if path in tracked_paths:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            pass
    for path in _SNAPSHOT_ROOT.glob("*.tmp"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_snapshot(
    operation: str,
    resource_id: str,
    payload_sha256: str,
    data: bytes,
) -> str:
    snapshot_id = uuid4().hex
    snapshot_path = _snapshot_path(snapshot_id)
    temporary_path = snapshot_path.with_suffix(".tmp")
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
        _prune_snapshots_locked(time.time())
        file_descriptor = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(data)
            os.replace(temporary_path, snapshot_path)
        except Exception:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        _SNAPSHOTS[snapshot_id] = SnapshotMetadata(
            operation=operation,
            resource_id=resource_id,
            payload_sha256=payload_sha256,
            total_characters=len(data),
            path=snapshot_path,
        )
    return snapshot_id


def _read_snapshot_chunk(
    snapshot_id: str,
    operation: str,
    resource_id: str,
    payload_sha256: str,
    total_characters: int,
    offset: int,
) -> bytes:
    with _SNAPSHOT_LOCK:
        metadata = _SNAPSHOTS.get(snapshot_id)
        if metadata is None:
            raise FileNotFoundError("Run-query snapshot expired or is unavailable")
        if (
            metadata.operation != operation
            or metadata.resource_id != resource_id
            or metadata.payload_sha256 != payload_sha256
            or metadata.total_characters != total_characters
        ):
            raise ValueError("Run-query cursor does not match its snapshot")
        if not metadata.path.is_file() or metadata.path.is_symlink():
            raise FileNotFoundError("Run-query snapshot expired or is unavailable")
        if metadata.path.stat().st_size != total_characters:
            raise ValueError("Run-query snapshot size mismatch")
        with metadata.path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(RUN_QUERY_CHUNK_CHARACTERS)


def _delete_snapshot(snapshot_id: str) -> None:
    with _SNAPSHOT_LOCK:
        metadata = _SNAPSHOTS.pop(snapshot_id, None)
        if metadata is None:
            return
        try:
            metadata.path.unlink(missing_ok=True)
        except OSError:
            pass


def _encode_cursor(
    operation: str,
    resource_id: str,
    offset: int,
    payload_sha256: str,
    snapshot_id: str,
    total_characters: int,
) -> str:
    return _urlsafe_encode(
        {
            "version": _CURSOR_VERSION,
            "operation": operation,
            "resource_id": resource_id,
            "offset": int(offset),
            "payload_sha256": payload_sha256,
            "snapshot_id": snapshot_id,
            "total_characters": int(total_characters),
        }
    )


def _decode_cursor(cursor: str) -> dict[str, Any]:
    payload = _urlsafe_decode(cursor)
    if int(payload.get("version", -1)) != _CURSOR_VERSION:
        raise ValueError("Unsupported run-query cursor version")
    return payload


def _cursor_error(
    operation: str,
    resource_id: str,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "transport": "chunked_json",
        "operation": operation,
        "resource_id": resource_id,
        "status": status,
        "restart_required": True,
        "complete": False,
        "next_cursor": "",
        "error": message,
    }


def chunk_payload(
    operation: str,
    resource_id: str,
    payload: Any | Callable[[], Any],
    cursor: str = "",
) -> Any:
    if cursor:
        try:
            state = _decode_cursor(cursor)
            if (
                state.get("operation") != operation
                or state.get("resource_id") != resource_id
            ):
                raise ValueError("Run-query cursor does not match this request")
            offset = int(state.get("offset", -1))
            total_characters = int(state.get("total_characters", -1))
            payload_sha256 = str(state.get("payload_sha256") or "")
            snapshot_id = str(state.get("snapshot_id") or "")
            if offset < 0 or offset > total_characters or total_characters < 0:
                raise ValueError("Run-query cursor offset is invalid")
            chunk_bytes = _read_snapshot_chunk(
                snapshot_id,
                operation,
                resource_id,
                payload_sha256,
                total_characters,
                offset,
            )
        except FileNotFoundError as exc:
            return _cursor_error(
                operation, resource_id, "cursor_expired", str(exc)
            )
        except (OSError, TypeError, ValueError) as exc:
            return _cursor_error(operation, resource_id, "invalid_cursor", str(exc))
        chunk = chunk_bytes.decode("ascii")
        end = offset + len(chunk)
        complete = end >= total_characters
        if complete:
            _delete_snapshot(snapshot_id)
        next_cursor = (
            ""
            if complete
            else _encode_cursor(
                operation,
                resource_id,
                end,
                payload_sha256,
                snapshot_id,
                total_characters,
            )
        )
        return {
            "ok": True,
            "transport": "chunked_json",
            "operation": operation,
            "resource_id": resource_id,
            "chunk": chunk,
            "chunk_index": offset // RUN_QUERY_CHUNK_CHARACTERS,
            "offset": offset,
            "next_offset": end,
            "chunk_characters": len(chunk),
            "total_characters": total_characters,
            "payload_sha256": payload_sha256,
            "complete": complete,
            "next_cursor": next_cursor,
            "error": "",
        }

    raw_payload = payload() if callable(payload) else payload
    safe_payload = _redact_value(raw_payload)
    serialized = json.dumps(
        safe_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    serialized_bytes = serialized.encode("ascii")
    payload_sha256 = hashlib.sha256(serialized_bytes).hexdigest()
    total_characters = len(serialized)

    if total_characters <= RUN_QUERY_CHUNK_CHARACTERS:
        if isinstance(safe_payload, dict):
            inline = dict(safe_payload)
            inline["_transport"] = {
                "mode": "inline",
                "complete": True,
                "payload_sha256": payload_sha256,
                "total_characters": total_characters,
            }
            return inline
        return safe_payload

    try:
        snapshot_id = _write_snapshot(
            operation,
            resource_id,
            payload_sha256,
            serialized_bytes,
        )
    except OSError as exc:
        return _cursor_error(
            operation,
            resource_id,
            "snapshot_failed",
            f"Could not persist run-query snapshot: {exc}",
        )
    end = RUN_QUERY_CHUNK_CHARACTERS
    return {
        "ok": True,
        "transport": "chunked_json",
        "operation": operation,
        "resource_id": resource_id,
        "chunk": serialized[:end],
        "chunk_index": 0,
        "offset": 0,
        "next_offset": end,
        "chunk_characters": end,
        "total_characters": total_characters,
        "payload_sha256": payload_sha256,
        "complete": False,
        "next_cursor": _encode_cursor(
            operation,
            resource_id,
            end,
            payload_sha256,
            snapshot_id,
            total_characters,
        ),
        "error": "",
    }
