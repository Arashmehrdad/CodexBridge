from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any


PAYLOAD_CHUNK_BYTES = 256 * 1024


def payload_file_name(index: int) -> str:
    return f"payload_{index}.bin"


def payload_chunk_file_name(index: int, chunk_index: int) -> str:
    return f"payload_{index}.part_{chunk_index:04d}.bin"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_payload_parts(
    index: int,
    data: bytes,
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    descriptor: dict[str, Any] = {
        "payload_file": "",
        "payload_chunks": [],
        "payload_sha256": sha256_bytes(data),
        "payload_size_bytes": len(data),
    }
    if len(data) <= PAYLOAD_CHUNK_BYTES:
        name = payload_file_name(index)
        descriptor["payload_file"] = name
        return descriptor, [(name, data)]

    parts: list[tuple[str, bytes]] = []
    chunks: list[dict[str, Any]] = []
    for chunk_index, offset in enumerate(range(0, len(data), PAYLOAD_CHUNK_BYTES)):
        chunk = data[offset : offset + PAYLOAD_CHUNK_BYTES]
        name = payload_chunk_file_name(index, chunk_index)
        parts.append((name, chunk))
        chunks.append(
            {
                "file": name,
                "sha256": sha256_bytes(chunk),
                "size_bytes": len(chunk),
            }
        )
    descriptor["payload_chunks"] = chunks
    return descriptor, parts


def assemble_payload(
    index: int,
    descriptor: dict[str, Any],
    read_file: Callable[[str, str], bytes],
) -> bytes:
    chunks = descriptor.get("payload_chunks")
    if isinstance(chunks, list) and chunks:
        output = bytearray()
        for chunk_index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise ValueError("Invalid payload chunk metadata")
            filename = str(chunk.get("file", ""))
            expected_name = payload_chunk_file_name(index, chunk_index)
            if filename != expected_name:
                raise ValueError("Payload chunk order or filename mismatch")
            data = read_file(filename, expected_name)
            if len(data) != int(chunk.get("size_bytes", -1)):
                raise ValueError("Payload chunk size mismatch")
            if sha256_bytes(data) != str(chunk.get("sha256", "")):
                raise ValueError("Payload chunk hash mismatch")
            output.extend(data)
        payload = bytes(output)
    else:
        filename = str(descriptor.get("payload_file", ""))
        if not filename:
            raise ValueError("Missing payload file metadata")
        if filename != payload_file_name(index):
            raise ValueError("Payload filename mismatch")
        payload = read_file(filename, payload_file_name(index))

    expected_sha = str(descriptor.get("payload_sha256", ""))
    if not expected_sha or sha256_bytes(payload) != expected_sha:
        raise ValueError("Payload hash mismatch")
    expected_size = descriptor.get("payload_size_bytes")
    if expected_size is not None and len(payload) != int(expected_size):
        raise ValueError("Payload size mismatch")
    return payload
