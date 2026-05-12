from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from .models import AtomicWriteResult
from .report_manifest import sha256_bytes


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
        os.replace(temp_path, path)
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


def _write_and_fsync(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
