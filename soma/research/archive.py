"""Immutable, content-addressed raw research archive."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArchivedObject:
    """Identity and metadata for one immutable raw object."""

    sha256: str
    relative_path: str
    size_bytes: int
    media_type: str
    original_name: str

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError(
                "sha256 must be a lowercase 64-character hexadecimal digest"
            )
        relative = Path(self.relative_path)
        if not self.relative_path or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("relative_path must remain inside the archive")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if not self.media_type.strip() or not self.original_name.strip():
            raise ValueError("media_type and original_name must not be empty")


class SourceArchive:
    """Store raw bytes once by SHA-256, outside SQLite and the project repository."""

    def __init__(self, root: Path) -> None:
        if root.name in {"", ".", ".."}:
            raise ValueError("archive root must identify a directory")
        self.root = root.resolve()
        self.objects_root = self.root / "objects"
        self.staging_root = self.root / "staging"
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(exist_ok=True)

    def put_file(self, path: Path, *, media_type: str | None = None) -> ArchivedObject:
        if not path.is_file():
            raise FileNotFoundError(path)
        with path.open("rb") as source:
            return self._put_stream(
                source, original_name=path.name, media_type=media_type
            )

    def put_bytes(
        self,
        content: bytes,
        *,
        original_name: str,
        media_type: str | None = None,
    ) -> ArchivedObject:
        if not original_name.strip():
            raise ValueError("original_name must not be empty")
        return self._put_stream(
            BytesIO(content), original_name=original_name, media_type=media_type
        )

    def register_captured(
        self, path: Path, *, media_type: str | None = None
    ) -> ArchivedObject:
        """Register an already captured source artifact through the same archive path."""
        return self.put_file(path, media_type=media_type)

    def resolve(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if not relative_path or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("relative_path must remain inside the archive")
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("relative_path must remain inside the archive")
        return candidate

    def verify(self, archived: ArchivedObject) -> bool:
        path = self.resolve(archived.relative_path)
        return (
            path.is_file()
            and path.stat().st_size == archived.size_bytes
            and _file_hash(path) == archived.sha256
        )

    def _put_stream(
        self,
        source: BinaryIO,
        *,
        original_name: str,
        media_type: str | None,
    ) -> ArchivedObject:
        digest = sha256()
        size_bytes = 0
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(dir=self.staging_root, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := source.read(_CHUNK_SIZE):
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            digest_hex = digest.hexdigest()
            relative = Path("objects") / digest_hex[:2] / digest_hex
            destination = self.resolve(relative.as_posix())
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if (
                    destination.stat().st_size != size_bytes
                    or _file_hash(destination) != digest_hex
                ):
                    raise OSError(f"archive collision or corruption at {destination}")
                temporary_path.unlink()
            else:
                os.replace(temporary_path, destination)
            temporary_path = None
            return ArchivedObject(
                sha256=digest_hex,
                relative_path=relative.as_posix(),
                size_bytes=size_bytes,
                media_type=(
                    media_type
                    or mimetypes.guess_type(original_name)[0]
                    or "application/octet-stream"
                ),
                original_name=original_name,
            )
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
