"""Deterministic internal contracts for resolving managed patch previews.

This module contains no repository mutation and no repair search. It only
normalizes a controller resolution request, binds it to immutable source-preview
material, and derives the deterministic child patch identity used by Gate 3.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PATCH_RESOLUTION_REQUEST_SCHEMA_VERSION: Final[str] = "repo_patch_resolution_request.v1"
PATCH_RESOLUTION_RECORD_SCHEMA_VERSION: Final[str] = "repo_patch_resolution_record.v1"
_PATCH_ID_RE = re.compile(r"^\d{8}T\d{6}Z_patch_[0-9a-f]{8}$")
_PROPOSAL_ID_RE = re.compile(r"^repair_[0-9a-f]{16}$")
_SHA256_RE = r"^[a-f0-9]{64}$"

PatchResolutionDecision = Literal["accept_repair", "accept_original"]


class _FrozenResolutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PatchResolutionRequestV1(_FrozenResolutionModel):
    schema_version: Literal[PATCH_RESOLUTION_REQUEST_SCHEMA_VERSION] = (
        PATCH_RESOLUTION_REQUEST_SCHEMA_VERSION
    )
    source_patch_id: str = Field(min_length=1, max_length=128)
    resolution_request_id: str = Field(min_length=1, max_length=128)
    decision: PatchResolutionDecision
    proposal_id: str = Field(default="", max_length=128)
    source_manifest_identity_hash: str = Field(pattern=_SHA256_RE)

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "PatchResolutionRequestV1":
        if not _PATCH_ID_RE.fullmatch(self.source_patch_id):
            raise ValueError("source_patch_id has invalid managed patch shape")
        if self.decision == "accept_repair":
            if not _PROPOSAL_ID_RE.fullmatch(self.proposal_id):
                raise ValueError("accept_repair requires an exact proposal_id")
        elif self.proposal_id:
            raise ValueError("accept_original forbids proposal_id")
        return self


def canonical_source_manifest_material(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable source material bound into a resolution request.

    Lifecycle fields such as ``status`` and ``resolution`` are intentionally
    excluded so marking a source ``resolved`` does not invalidate exact replay.
    """

    return {
        "patch_id": manifest.get("patch_id", ""),
        "bundle_version": manifest.get("bundle_version"),
        "repo_fingerprint": manifest.get("repo_fingerprint", ""),
        "git_head_at_preview": manifest.get("git_head_at_preview", ""),
        "operations": manifest.get("operations", []),
        "errors": manifest.get("errors", []),
        "warnings": manifest.get("warnings", []),
        "commit_title": manifest.get("commit_title", ""),
        "commit_description": manifest.get("commit_description", ""),
        "repair_proposal": manifest.get("repair_proposal"),
    }


def source_manifest_identity_hash(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        canonical_source_manifest_material(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(
        b"soma.repo_patch.source_manifest_identity.v1\0" + encoded
    ).hexdigest()


def resolution_request_hash(request: PatchResolutionRequestV1) -> str:
    material = {
        "source_patch_id": request.source_patch_id,
        "resolution_request_id": request.resolution_request_id,
        "decision": request.decision,
        "proposal_id": request.proposal_id,
        "source_manifest_identity_hash": request.source_manifest_identity_hash,
    }
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(
        b"soma.repo_patch.resolution_request.v1\0" + encoded
    ).hexdigest()


def resolution_child_patch_id(source_patch_id: str, request_hash: str) -> str:
    if not _PATCH_ID_RE.fullmatch(source_patch_id):
        raise ValueError("source_patch_id has invalid managed patch shape")
    if not re.fullmatch(_SHA256_RE, request_hash):
        raise ValueError("resolution request hash must be lowercase SHA-256")
    timestamp_prefix = source_patch_id.split("_patch_", 1)[0]
    suffix = hashlib.sha256(
        (
            "soma.repo_patch.resolution_child.v1\0"
            + source_patch_id
            + "\0"
            + request_hash
        ).encode("utf-8")
    ).hexdigest()[:8]
    return f"{timestamp_prefix}_patch_{suffix}"


def build_resolution_request(
    *,
    source_patch_id: str,
    resolution_request_id: str,
    decision: PatchResolutionDecision,
    proposal_id: str = "",
    source_manifest: dict[str, Any],
) -> tuple[PatchResolutionRequestV1, str, str]:
    identity_hash = source_manifest_identity_hash(source_manifest)
    request = PatchResolutionRequestV1(
        source_patch_id=source_patch_id,
        resolution_request_id=resolution_request_id,
        decision=decision,
        proposal_id=proposal_id,
        source_manifest_identity_hash=identity_hash,
    )
    request_hash = resolution_request_hash(request)
    child_patch_id = resolution_child_patch_id(source_patch_id, request_hash)
    return request, request_hash, child_patch_id
