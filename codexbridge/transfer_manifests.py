from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
import shutil


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_download_cleanup_manifest(requested_name: str) -> dict[str, object]:
    name = PurePosixPath(str(requested_name)).name
    if not name or name in {".", ".."} or name != str(requested_name):
        raise ValueError("Download cleanup manifest requires a single artifact name")
    return {
        "version": 1,
        "cleanup_entries": [f"downloads/.{name}.partial"],
        "protected_entries": [f"downloads/{name}"],
    }


def cleanup_transfer_staging(run_dir: Path, manifest: dict[str, object]) -> list[str]:
    if manifest.get("version") != 1:
        raise ValueError("Transfer cleanup manifest version is unsupported")
    cleanup_entries = manifest.get("cleanup_entries")
    protected_entries = manifest.get("protected_entries")
    if not isinstance(cleanup_entries, list) or not isinstance(protected_entries, list):
        raise ValueError("Transfer cleanup manifest entries are invalid")
    protected = {str(item) for item in protected_entries}
    removed: list[str] = []
    root = run_dir.resolve()
    for raw_entry in cleanup_entries:
        entry = str(raw_entry)
        if entry in protected:
            raise ValueError("Transfer cleanup manifest cannot delete protected evidence")
        relative = PurePosixPath(entry)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Transfer cleanup manifest path escapes the run directory")
        candidate = (run_dir / Path(*relative.parts)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("Transfer cleanup manifest path escapes the run directory") from exc
        if not candidate.exists():
            continue
        if candidate.is_symlink():
            raise ValueError("Transfer cleanup refuses symbolic links")
        if candidate.is_dir():
            for child in candidate.rglob("*"):
                if child.is_symlink():
                    raise ValueError("Transfer cleanup refuses symbolic links")
            shutil.rmtree(candidate)
        elif candidate.is_file():
            candidate.unlink()
        else:
            raise ValueError("Transfer cleanup refuses non-regular artifacts")
        removed.append(entry)
    return removed


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
