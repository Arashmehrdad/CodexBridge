from __future__ import annotations

from pathlib import Path

from soma.return_loop.atomic_writer import atomic_write_text


def apply_text_atomically(path: Path, text: str) -> None:
    atomic_write_text(path, text)
