from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_upload_transfer_manifest(source: Path) -> dict[str, object]:
    if source.is_file():
        return {
            "version": 1,
            "source_kind": "file",
            "source_size_bytes": source.stat().st_size,
            "source_sha256": sha256_file(source),
        }
    if not source.is_dir():
        raise ValueError("SSH upload source must be a regular file or directory")

    entries: list[dict[str, object]] = []
    total_size = 0
    for candidate in source.rglob("*"):
        if candidate.is_symlink():
            raise ValueError("Recursive SSH upload does not support symbolic links")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ValueError("Recursive SSH upload contains a non-regular file")
        relative_path = candidate.relative_to(source).as_posix()
        size_bytes = candidate.stat().st_size
        entries.append(
            {
                "relative_path": relative_path,
                "size_bytes": size_bytes,
                "sha256": sha256_file(candidate),
            }
        )
        total_size += size_bytes
    entries.sort(key=lambda item: str(item["relative_path"]))
    return {
        "version": 1,
        "source_kind": "directory",
        "source_file_count": len(entries),
        "source_size_bytes": total_size,
        "entries": entries,
    }
