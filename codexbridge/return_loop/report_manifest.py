from __future__ import annotations

import hashlib
from pathlib import Path


SENSITIVE_MARKERS = (
    "api key",
    "secret",
    "password",
    "token",
    "private key",
    "credential",
    "authorization:",
    "authorization header",
    "bearer ",
    "bearer token",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def file_size(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    return path.stat().st_size


def sensitivity_flags_for_text(text: str) -> list[str]:
    lowered = text.lower()
    return [
        marker.upper().replace(" ", "_").replace(":", "")
        for marker in SENSITIVE_MARKERS
        if marker in lowered
    ]


def read_stable_bytes(path: Path, *, require_stable: bool = True) -> tuple[bytes, bool]:
    first = path.read_bytes()
    if not require_stable:
        return first, True
    first_stat = path.stat()
    second = path.read_bytes()
    second_stat = path.stat()
    stable = (
        first == second
        and first_stat.st_size == second_stat.st_size
        and first_stat.st_mtime_ns == second_stat.st_mtime_ns
    )
    return second, stable
