from __future__ import annotations

import json
from pathlib import Path

import pytest

from soma.return_loop import atomic_writer
from soma.return_loop.atomic_writer import atomic_write_json, atomic_write_text


def test_atomic_text_write_creates_complete_final_file(tmp_path: Path) -> None:
    path = tmp_path / "resume_prompt.txt"

    result = atomic_write_text(path, "complete content")

    assert path.read_text(encoding="utf-8") == "complete content"
    assert result.path == path
    assert result.replaced is True
    assert not result.temp_path.exists()


def test_atomic_json_write_is_parseable(tmp_path: Path) -> None:
    path = tmp_path / "pulse_manifest.json"

    atomic_write_json(path, {"b": 2, "a": 1})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_atomic_write_failure_does_not_create_partial_final_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "report.md"

    def fail_write(temp_path: Path, data: bytes) -> None:
        temp_path.write_bytes(b"partial")
        raise OSError("simulated write failure")

    monkeypatch.setattr(atomic_writer, "_write_and_fsync", fail_write)
    with pytest.raises(OSError):
        atomic_write_text(path, "full")

    assert not path.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_retries_permission_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "retry.txt"
    attempts = {"count": 0}
    original_replace = atomic_writer.os.replace

    def flaky_replace(src, dst):
        attempts["count"] += 1
        if attempts["count"] < 3:
            error = PermissionError("busy")
            error.winerror = 5
            raise error
        return original_replace(src, dst)

    monkeypatch.setattr(atomic_writer.os, "replace", flaky_replace)

    result = atomic_write_text(path, "eventual")

    assert result.replaced is True
    assert path.read_text(encoding="utf-8") == "eventual"
    assert attempts["count"] == 3
