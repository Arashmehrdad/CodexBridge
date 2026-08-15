from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from soma.repo_patch_resolution import (
    PatchResolutionRequestV1,
    build_resolution_request,
    resolution_child_patch_id,
    resolution_request_hash,
    source_manifest_identity_hash,
)

SOURCE_PATCH_ID = "20260815T010203Z_patch_abcdef12"
SOURCE_MANIFEST = {
    "patch_id": SOURCE_PATCH_ID,
    "bundle_version": 4,
    "created_at": "2026-08-15T01:02:03+00:00",
    "repo_fingerprint": "a" * 64,
    "git_head_at_preview": "b" * 40,
    "status": "preview_resolution_required",
    "operations": [
        {
            "index": 0,
            "action": "modify",
            "path": "example.py",
            "current_sha256": "c" * 64,
            "payload_file": "payload_0.bin",
            "payload_sha256": "d" * 64,
            "payload_size_bytes": 10,
        }
    ],
    "errors": [],
    "warnings": [],
    "commit_title": "Example",
    "commit_description": "",
    "repair_proposal": {
        "proposal_id": "repair_0123456789abcdef",
        "repaired_payload_descriptor": {
            "file": "repair_payload_0123456789abcdef.bin",
            "sha256": "e" * 64,
            "size_bytes": 9,
        },
    },
}


def test_source_identity_excludes_mutable_resolution_lifecycle() -> None:
    original = source_manifest_identity_hash(SOURCE_MANIFEST)
    resolved = dict(SOURCE_MANIFEST)
    resolved["status"] = "resolved"
    resolved["resolved_at"] = "later"
    resolved["resolution"] = {"child_patch_id": "different-lifecycle-field"}
    resolved["applied_at"] = "never-valid-on-source-but-mutable"

    assert source_manifest_identity_hash(resolved) == original


def test_source_identity_binds_payload_and_proposal_material() -> None:
    original = source_manifest_identity_hash(SOURCE_MANIFEST)
    changed = {
        **SOURCE_MANIFEST,
        "operations": [dict(SOURCE_MANIFEST["operations"][0])],
    }
    changed["operations"][0]["payload_sha256"] = "f" * 64
    assert source_manifest_identity_hash(changed) != original

    changed_proposal = {
        **SOURCE_MANIFEST,
        "repair_proposal": dict(SOURCE_MANIFEST["repair_proposal"]),
    }
    changed_proposal["repair_proposal"]["proposal_id"] = "repair_fedcba9876543210"
    assert source_manifest_identity_hash(changed_proposal) != original


def test_accept_repair_requires_exact_proposal_id() -> None:
    with pytest.raises(ValidationError, match="accept_repair requires"):
        PatchResolutionRequestV1(
            source_patch_id=SOURCE_PATCH_ID,
            resolution_request_id="resolve-1",
            decision="accept_repair",
            source_manifest_identity_hash="a" * 64,
        )


def test_accept_original_forbids_proposal_id() -> None:
    with pytest.raises(ValidationError, match="accept_original forbids"):
        PatchResolutionRequestV1(
            source_patch_id=SOURCE_PATCH_ID,
            resolution_request_id="resolve-1",
            decision="accept_original",
            proposal_id="repair_0123456789abcdef",
            source_manifest_identity_hash="a" * 64,
        )


def test_resolution_request_hash_is_deterministic_and_material_sensitive() -> None:
    request, request_hash, child = build_resolution_request(
        source_patch_id=SOURCE_PATCH_ID,
        resolution_request_id="resolve-1",
        decision="accept_repair",
        proposal_id="repair_0123456789abcdef",
        source_manifest=SOURCE_MANIFEST,
    )
    assert resolution_request_hash(request) == request_hash
    assert child == resolution_child_patch_id(SOURCE_PATCH_ID, request_hash)
    assert re.fullmatch(r"20260815T010203Z_patch_[0-9a-f]{8}", child)

    changed = request.model_copy(update={"resolution_request_id": "resolve-2"})
    changed_hash = resolution_request_hash(changed)
    assert changed_hash != request_hash
    assert resolution_child_patch_id(SOURCE_PATCH_ID, changed_hash) != child


def test_child_keeps_source_timestamp_prefix() -> None:
    child = resolution_child_patch_id(SOURCE_PATCH_ID, "f" * 64)
    assert child.startswith("20260815T010203Z_patch_")


def test_invalid_source_patch_shape_and_hash_fail_closed() -> None:
    with pytest.raises(ValueError, match="invalid managed patch shape"):
        resolution_child_patch_id("not-a-patch", "f" * 64)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        resolution_child_patch_id(SOURCE_PATCH_ID, "BAD")
