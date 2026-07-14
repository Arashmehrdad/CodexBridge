from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .safety import redact_secret_values


RUN_QUERY_CHUNK_CHARACTERS = 16 * 1024
_CURSOR_VERSION = 1
_RUN_REFERENCE_PREFIX = "__codexbridge_run_query_run__:"
_LIST_REFERENCE_PREFIX = "__codexbridge_run_query_list__:"


@dataclass(frozen=True)
class ChunkReference:
    resource_id: str
    cursor: str


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
    return _RUN_REFERENCE_PREFIX + _urlsafe_encode(
        {"run_id": run_id, "cursor": cursor}
    )


def decode_run_reference(value: str) -> ChunkReference | None:
    if not value.startswith(_RUN_REFERENCE_PREFIX):
        return None
    payload = _urlsafe_decode(value[len(_RUN_REFERENCE_PREFIX) :])
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


def _encode_cursor(
    operation: str,
    resource_id: str,
    offset: int,
    payload_sha256: str,
) -> str:
    return _urlsafe_encode(
        {
            "version": _CURSOR_VERSION,
            "operation": operation,
            "resource_id": resource_id,
            "offset": int(offset),
            "payload_sha256": payload_sha256,
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
    payload: Any,
    cursor: str = "",
) -> Any:
    safe_payload = _redact_value(payload)
    serialized = json.dumps(
        safe_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    payload_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    offset = 0

    if cursor:
        try:
            state = _decode_cursor(cursor)
            if (
                state.get("operation") != operation
                or state.get("resource_id") != resource_id
            ):
                raise ValueError("Run-query cursor does not match this request")
            offset = int(state.get("offset", -1))
        except (TypeError, ValueError) as exc:
            return _cursor_error(operation, resource_id, "invalid_cursor", str(exc))
        if state.get("payload_sha256") != payload_sha256:
            return _cursor_error(
                operation,
                resource_id,
                "cursor_stale",
                "Run data changed; restart from the first chunk",
            )

    if offset < 0 or offset > len(serialized):
        return _cursor_error(
            operation,
            resource_id,
            "invalid_cursor",
            "Run-query cursor offset is invalid",
        )

    if not cursor and len(serialized) <= RUN_QUERY_CHUNK_CHARACTERS:
        if isinstance(safe_payload, dict):
            inline = dict(safe_payload)
            inline["_transport"] = {
                "mode": "inline",
                "complete": True,
                "payload_sha256": payload_sha256,
                "total_characters": len(serialized),
            }
            return inline
        return safe_payload

    end = min(offset + RUN_QUERY_CHUNK_CHARACTERS, len(serialized))
    complete = end >= len(serialized)
    next_cursor = (
        ""
        if complete
        else _encode_cursor(operation, resource_id, end, payload_sha256)
    )
    return {
        "ok": True,
        "transport": "chunked_json",
        "operation": operation,
        "resource_id": resource_id,
        "chunk": serialized[offset:end],
        "chunk_index": offset // RUN_QUERY_CHUNK_CHARACTERS,
        "offset": offset,
        "next_offset": end,
        "chunk_characters": end - offset,
        "total_characters": len(serialized),
        "payload_sha256": payload_sha256,
        "complete": complete,
        "next_cursor": next_cursor,
        "error": "",
    }
