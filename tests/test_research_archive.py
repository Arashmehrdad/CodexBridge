from pathlib import Path

import pytest

from soma.research.archive import SourceArchive


def test_archive_deduplicates_by_bytes_not_filename(tmp_path: Path) -> None:
    archive = SourceArchive(tmp_path / "raw")
    content = b"%PDF-1.7\nsource evidence\n"

    first = archive.put_bytes(content, original_name="paper.pdf")
    second = archive.put_bytes(content, original_name="capture.html")

    assert first.sha256 == second.sha256
    assert first.relative_path == second.relative_path
    assert archive.resolve(first.relative_path).read_bytes() == content
    assert len(tuple((tmp_path / "raw" / "objects").rglob(first.sha256))) == 1


def test_archive_changed_bytes_create_distinct_objects(tmp_path: Path) -> None:
    archive = SourceArchive(tmp_path / "raw")

    first = archive.put_bytes(b"version one", original_name="source.txt")
    second = archive.put_bytes(b"version two", original_name="source.txt")

    assert first.sha256 != second.sha256
    assert first.relative_path != second.relative_path
    assert archive.verify(first)
    assert archive.verify(second)


def test_archive_verification_detects_corruption(tmp_path: Path) -> None:
    archive = SourceArchive(tmp_path / "raw")
    archived = archive.put_bytes(b"trusted bytes", original_name="source.bin")

    archive.resolve(archived.relative_path).write_bytes(b"corrupt bytes")

    assert not archive.verify(archived)
    with pytest.raises(OSError, match="collision or corruption"):
        archive.put_bytes(b"trusted bytes", original_name="other.bin")


def test_archive_rejects_traversal_and_absolute_paths(tmp_path: Path) -> None:
    archive = SourceArchive(tmp_path / "raw")

    with pytest.raises(ValueError, match="inside the archive"):
        archive.resolve("../escape")
    with pytest.raises(ValueError, match="inside the archive"):
        archive.resolve(str((tmp_path / "outside").resolve()))
