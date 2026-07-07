from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from codexbridge.payload_chunks import (
    PAYLOAD_CHUNK_BYTES,
    assemble_payload,
    build_payload_parts,
)
from codexbridge.repo_writer import apply_previewed_repo_change, preview_repo_patch


def test_payload_chunks_round_trip_and_detect_tampering() -> None:
    data = (b"abc123" * ((PAYLOAD_CHUNK_BYTES // 6) + 10)) + b"tail"
    descriptor, parts = build_payload_parts(3, data)
    stored = dict(parts)

    assembled = assemble_payload(
        3,
        descriptor,
        lambda filename, expected: stored[expected] if filename == expected else b"",
    )

    assert len(parts) > 1
    assert assembled == data
    first_name = parts[0][0]
    stored[first_name] = b"changed"
    with pytest.raises(ValueError, match="chunk"):
        assemble_payload(
            3,
            descriptor,
            lambda filename, expected: (
                stored[expected] if filename == expected else b""
            ),
        )


def test_large_preview_bundle_uses_chunks_and_applies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs = tmp_path / "runs"
    path = repo / "large.txt"
    original = "a" * (PAYLOAD_CHUNK_BYTES + 4096)
    updated = "b" * len(original)
    path.write_text(original, encoding="utf-8")
    operation = {
        "path": "large.txt",
        "expected_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "old_text": original,
        "new_text": updated,
    }

    preview = preview_repo_patch(repo, [operation], runs)
    manifest_path = runs / "managed_patches" / preview["patch_id"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    descriptor = manifest["operations"][0]

    assert descriptor["payload_file"] == ""
    assert len(descriptor["payload_chunks"]) > 1
    result = apply_previewed_repo_change(repo, preview["patch_id"], runs)
    assert result["ok"] is True
    assert path.read_text(encoding="utf-8") == updated
