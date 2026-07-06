from __future__ import annotations

import json
import os
import time
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from .models import AtomicWriteResult
from .report_manifest import sha256_bytes

_MAX_REPLACE_RETRIES = 5
_RETRYABLE_WINERRORS = {5}


def atomic_write_text(path: Path, text: str) -> AtomicWriteResult:
    data = text.encode("utf-8")
    return _atomic_write_bytes(path, data)


def atomic_write_json(path: Path, data: dict) -> AtomicWriteResult:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    return atomic_write_text(path, text)


def _atomic_write_bytes(path: Path, data: bytes) -> AtomicWriteResult:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        _write_and_fsync(temp_path, data)
        _replace_with_retries(temp_path, path)
        return AtomicWriteResult(
            path=path,
            temp_path=temp_path,
            bytes_written=len(data),
            replaced=True,
            sha256=sha256_bytes(data),
        )
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        finally:
            raise


def _replace_with_retries(temp_path: Path, path: Path) -> None:
    delay_seconds = 0.01
    for attempt in range(_MAX_REPLACE_RETRIES):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            if attempt >= _MAX_REPLACE_RETRIES - 1 or not _is_retryable_replace_error(
                exc
            ):
                raise
        time.sleep(delay_seconds)
        delay_seconds = min(delay_seconds * 2, 0.2)


def _is_retryable_replace_error(exc: PermissionError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror in _RETRYABLE_WINERRORS:
        return True
    return os.name == "nt"


def _write_and_fsync(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    with suppress(OSError):
        if hasattr(os, "O_DIRECTORY"):
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
