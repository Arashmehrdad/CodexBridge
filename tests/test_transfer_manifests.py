from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from codexbridge.transfer_manifests import (
    build_download_cleanup_manifest,
    build_upload_transfer_manifest,
    cleanup_transfer_staging,
)


def test_download_cleanup_manifest_is_retry_safe_and_preserves_publication(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    downloads = run_dir / "downloads"
    downloads.mkdir(parents=True)
    partial = downloads / ".artifact.bin.partial"
    published = downloads / "artifact.bin"
    partial.write_bytes(b"partial")
    published.write_bytes(b"published")
    manifest = build_download_cleanup_manifest("artifact.bin")

    assert cleanup_transfer_staging(run_dir, manifest) == [
        "downloads/.artifact.bin.partial"
    ]
    assert cleanup_transfer_staging(run_dir, manifest) == []
    assert not partial.exists()
    assert published.read_bytes() == b"published"
    assert manifest["protected_entries"] == ["downloads/artifact.bin"]


def test_transfer_cleanup_manifest_rejects_escape_and_protected_deletion(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        cleanup_transfer_staging(
            run_dir,
            {"version": 1, "cleanup_entries": ["../outside"], "protected_entries": []},
        )
    with pytest.raises(ValueError, match="protected evidence"):
        cleanup_transfer_staging(
            run_dir,
            {
                "version": 1,
                "cleanup_entries": ["downloads/artifact.bin"],
                "protected_entries": ["downloads/artifact.bin"],
            },
        )


def test_recursive_upload_manifest_is_stable_and_binary_safe(tmp_path: Path) -> None:
    source = tmp_path / "payload"
    (source / "zeta").mkdir(parents=True)
    (source / "alpha").mkdir()
    first = b"first\x00\xff"
    second = b"second\r\n"
    (source / "zeta" / "two.bin").write_bytes(second)
    (source / "alpha" / "one.bin").write_bytes(first)

    assert build_upload_transfer_manifest(source) == {
        "version": 1,
        "source_kind": "directory",
        "source_file_count": 2,
        "source_size_bytes": len(first) + len(second),
        "entries": [
            {
                "relative_path": "alpha/one.bin",
                "size_bytes": len(first),
                "sha256": sha256(first).hexdigest(),
            },
            {
                "relative_path": "zeta/two.bin",
                "size_bytes": len(second),
                "sha256": sha256(second).hexdigest(),
            },
        ],
    }


def test_recursive_upload_manifest_records_empty_directory(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    source.mkdir()

    assert build_upload_transfer_manifest(source) == {
        "version": 1,
        "source_kind": "directory",
        "source_file_count": 0,
        "source_size_bytes": 0,
        "entries": [],
    }


def test_recursive_upload_manifest_rejects_symbolic_links(tmp_path: Path) -> None:
    source = tmp_path / "payload"
    source.mkdir()
    target = tmp_path / "outside.bin"
    target.write_bytes(b"outside")
    link = source / "link.bin"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symbolic-link creation is unavailable for this Windows account")

    with pytest.raises(ValueError, match="does not support symbolic links"):
        build_upload_transfer_manifest(source)
