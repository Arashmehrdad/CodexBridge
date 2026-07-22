from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Final


PUBLIC_FOOTPRINT_MEASUREMENT_VERSION: Final[str] = "cf1.0.measurement.v1"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


@dataclass(frozen=True)
class PublicFootprintMeasurement:
    version: str
    request_bytes: int
    server_projection_bytes: int
    mcp_structured_content_bytes: int
    mcp_text_content_bytes: int
    connector_wrapper_bytes: int
    duplicated_representation_bytes: int
    conversation_visible_bytes: int
    authoritative_sha256: str

    @property
    def transport_overhead_bytes(self) -> int:
        return self.conversation_visible_bytes - self.server_projection_bytes


def measure_public_footprint(
    *,
    request_arguments: Any,
    server_projection: Any,
    mcp_structured_content: Any,
    mcp_text_content: str,
    connector_envelope: Any,
    authoritative_record: Any,
) -> PublicFootprintMeasurement:
    request_payload = _json_bytes(request_arguments)
    server_payload = _json_bytes(server_projection)
    structured_payload = _json_bytes(mcp_structured_content)
    text_payload = str(mcp_text_content).encode("utf-8")
    connector_payload = _json_bytes(connector_envelope)
    authoritative_payload = _json_bytes(authoritative_record)

    duplicated = 0
    if structured_payload == server_payload:
        duplicated += len(structured_payload)
    if text_payload == server_payload:
        duplicated += len(text_payload)

    return PublicFootprintMeasurement(
        version=PUBLIC_FOOTPRINT_MEASUREMENT_VERSION,
        request_bytes=len(request_payload),
        server_projection_bytes=len(server_payload),
        mcp_structured_content_bytes=len(structured_payload),
        mcp_text_content_bytes=len(text_payload),
        connector_wrapper_bytes=max(0, len(connector_payload) - len(structured_payload) - len(text_payload)),
        duplicated_representation_bytes=duplicated,
        conversation_visible_bytes=len(connector_payload),
        authoritative_sha256=sha256(authoritative_payload).hexdigest(),
    )
