"""Internal Gate-3 service for explicit managed-patch resolution.

Resolution is preview construction, never repository apply. A source preview that
requires resolution remains non-applicable forever; one explicit controller
decision selects a deterministic child preview that must pass the incumbent
repository preconditions before it can become ``preview_ok``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from . import repo_writer as rw
from .repo_patch_repair import PatchRepairProposalV1
from .repo_patch_resolution import (
    PatchResolutionDecision,
    build_resolution_request,
)

_RESOLUTION_RECORD_VERSION = "repo_patch_resolution_record.v1"


def _read_manifest(patch_dir: Path, patch_id: str) -> tuple[Path, dict[str, Any]]:
    manifest_path = patch_dir / "manifest.json"
    if (
        not manifest_path.exists()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
    ):
        raise ValueError(f"Patch {patch_id} is missing a regular manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Patch {patch_id} has an invalid manifest") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"Patch {patch_id} has an invalid manifest")
    if manifest.get("patch_id") != patch_id:
        raise ValueError(f"Patch {patch_id} manifest identity mismatch")
    return manifest_path, manifest


def _resolution_record_matches(
    record: dict[str, Any],
    *,
    source_patch_id: str,
    child_patch_id: str,
    resolution_request_id: str,
    request_hash: str,
    source_identity_hash: str,
    decision: PatchResolutionDecision,
    proposal_id: str,
) -> bool:
    return all(
        (
            record.get("schema_version") == _RESOLUTION_RECORD_VERSION,
            record.get("source_patch_id") == source_patch_id,
            record.get("child_patch_id") == child_patch_id,
            record.get("resolution_request_id") == resolution_request_id,
            record.get("resolution_request_hash") == request_hash,
            record.get("source_manifest_identity_hash") == source_identity_hash,
            record.get("decision") == decision,
            record.get("proposal_id", "") == proposal_id,
        )
    )


def _child_result(child_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    patch_id = str(manifest.get("patch_id", ""))
    diff_path = child_dir / "preview.diff"
    diff_text = ""
    if diff_path.exists() and diff_path.is_file() and not diff_path.is_symlink():
        diff_text = diff_path.read_text(encoding="utf-8")
    operations = manifest.get("operations", [])
    resolution = dict(manifest.get("resolution") or {})
    changed_lines = sum(int(item.get("changed_lines", 0)) for item in operations)
    logical_changed_lines = sum(
        int(item.get("logical_changed_lines", item.get("changed_lines", 0)))
        for item in operations
    )
    newline_only_changed_lines = sum(
        int(item.get("newline_only_changed_lines", 0)) for item in operations
    )
    changed_bytes = sum(int(item.get("changed_bytes", 0)) for item in operations)
    return {
        "ok": manifest.get("status") == "preview_ok",
        "applicable": manifest.get("status") == "preview_ok",
        "resolution_required": False,
        "repair_available": False,
        "repair_proposal_id": "",
        "patch_id": patch_id,
        "child_patch_id": patch_id,
        "source_patch_id": str(resolution.get("source_patch_id", "")),
        "resolution_request_id": str(resolution.get("resolution_request_id", "")),
        "resolution_request_hash": str(resolution.get("resolution_request_hash", "")),
        "decision": str(resolution.get("decision", "")),
        "proposal_id": str(resolution.get("proposal_id", "")),
        "repo_name": "",
        "diff": diff_text,
        "changed_files": [
            str(item.get("path", "")) for item in operations if item.get("path")
        ],
        "changed_lines": changed_lines,
        "logical_changed_lines": logical_changed_lines,
        "newline_only_changed_lines": newline_only_changed_lines,
        "changed_bytes": changed_bytes,
        "git_head": str(manifest.get("git_head_at_preview", "")),
        "validation_errors": list(manifest.get("errors") or []),
        "error": "",
        "commit_title": str(manifest.get("commit_title", "")),
        "commit_description": str(manifest.get("commit_description", "")),
        "idempotent_replay": True,
    }


def _load_source_payload(
    source_dir: Path, index: int, op: dict[str, Any], source_patch_id: str
) -> bytes:
    try:
        return rw.assemble_payload(
            index,
            op,
            lambda filename, expected: rw._resolve_bundle_file(
                source_dir, filename, expected, kind="payload"
            ).read_bytes(),
        )
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Patch {source_patch_id} source payload verification failed for "
            f"'{op.get('path', '')}': {exc}"
        ) from exc


def _load_repair_payload(
    source_dir: Path,
    source_patch_id: str,
    source_manifest: dict[str, Any],
    proposal_id: str,
) -> tuple[PatchRepairProposalV1, bytes]:
    raw = source_manifest.get("repair_proposal")
    if not isinstance(raw, dict):
        raise ValueError(f"Patch {source_patch_id} has no repair proposal")
    try:
        proposal = PatchRepairProposalV1.model_validate(raw)
    except Exception as exc:
        raise ValueError(
            f"Patch {source_patch_id} has invalid repair proposal metadata"
        ) from exc
    if proposal.proposal_id != proposal_id:
        raise ValueError(
            f"Patch {source_patch_id} repair proposal mismatch: expected {proposal.proposal_id}"
        )
    descriptor = proposal.repaired_payload_descriptor
    repair_path = rw._resolve_bundle_file(
        source_dir,
        descriptor.file,
        descriptor.file,
        kind="repair payload",
    )
    repair_bytes = repair_path.read_bytes()
    if hashlib.sha256(repair_bytes).hexdigest() != descriptor.sha256:
        raise ValueError(f"Patch {source_patch_id} repair payload hash mismatch")
    if len(repair_bytes) != descriptor.size_bytes:
        raise ValueError(f"Patch {source_patch_id} repair payload size mismatch")
    return proposal, repair_bytes


def _preflight_selected_child(
    *,
    repo_root: Path,
    source_dir: Path,
    source_patch_id: str,
    source_manifest: dict[str, Any],
    decision: PatchResolutionDecision,
    proposal_id: str,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], dict[str, Any] | None]:
    operations = source_manifest.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError(f"Patch {source_patch_id} has no source operations")
    if len(operations) > rw.MAX_PATCH_FILES:
        raise ValueError(
            f"Patch exceeds {rw.MAX_PATCH_FILES} file limit ({len(operations)} files)"
        )

    current_head = rw._git_head(repo_root)
    preview_head = str(source_manifest.get("git_head_at_preview", ""))
    if preview_head and current_head and preview_head != current_head:
        raise ValueError(
            f"Git HEAD has changed since source preview "
            f"(preview: {preview_head[:12]}, current: {current_head[:12]})"
        )

    selected_proposal: PatchRepairProposalV1 | None = None
    repair_bytes: bytes | None = None
    if decision == "accept_repair":
        selected_proposal, repair_bytes = _load_repair_payload(
            source_dir, source_patch_id, source_manifest, proposal_id
        )

    child_ops: list[dict[str, Any]] = []
    source_validations: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    total_changed_lines = 0
    total_changed_bytes = 0
    combined_diff = ""
    validation_budget = rw.CandidateValidationBudget()
    selected_repair_found = False

    for index, source_op in enumerate(operations):
        if not isinstance(source_op, dict) or source_op.get("action") != "modify":
            raise ValueError(
                f"Patch {source_patch_id} has an invalid resolution operation at index {index}"
            )
        path_str = source_op.get("path")
        if not isinstance(path_str, str) or not path_str:
            raise ValueError(f"Patch {source_patch_id} has an invalid operation path")
        absolute = rw._resolve_and_validate_write(repo_root, path_str)
        normalized_path = os.path.normcase(os.path.normpath(str(absolute.resolve())))
        if normalized_path in seen_paths:
            raise ValueError(
                f"Patch {source_patch_id} includes duplicate paths: {path_str}"
            )
        seen_paths.add(normalized_path)
        if not absolute.exists():
            raise ValueError(f"File does not exist: {path_str}")
        if absolute.is_dir():
            raise ValueError(f"Path is a directory: {path_str}")
        if absolute.is_symlink():
            raise ValueError(f"Symlinks are not allowed: {path_str}")
        if rw._is_binary(absolute):
            raise ValueError(f"Binary files are not supported: {path_str}")

        current_bytes = absolute.read_bytes()
        current_sha = hashlib.sha256(current_bytes).hexdigest()
        expected_sha = source_op.get("current_sha256", "")
        if current_sha != expected_sha:
            raise ValueError(
                f"File '{path_str}' has changed since source preview (hash mismatch)"
            )

        original_payload = _load_source_payload(
            source_dir, index, source_op, source_patch_id
        )
        selected_payload = original_payload
        if (
            selected_proposal is not None
            and selected_proposal.path == path_str
            and selected_proposal.operation_index == index
        ):
            if repair_bytes is None:
                raise ValueError(
                    f"Patch {source_patch_id} is missing selected repair bytes"
                )
            if (
                hashlib.sha256(original_payload).hexdigest()
                != selected_proposal.original_candidate_sha256
            ):
                raise ValueError(
                    f"Patch {source_patch_id} proposal/source payload mismatch"
                )
            selected_payload = repair_bytes
            selected_repair_found = True

        try:
            current_text = current_bytes.decode("utf-8")
            selected_text = selected_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Patch {source_patch_id} contains non-UTF-8 patch payload"
            ) from exc

        diff_text = rw._unified_diff_for_op(current_text, selected_text, path_str)
        changed_lines, logical_changed_lines, newline_only_changed_lines = (
            rw._change_line_counts(current_text, selected_text, path_str)
        )
        newline_diagnostic = rw._newline_diagnostic(current_text, selected_text)
        changed_bytes = abs(len(selected_payload) - len(current_bytes))
        total_changed_lines += changed_lines
        total_changed_bytes += changed_bytes
        combined_diff += diff_text

        source_validation = source_op.get("candidate_validation")
        source_validations.append(
            {"path": path_str, "candidate_validation": source_validation}
        )
        child_validation = source_validation
        if Path(path_str).suffix.lower() == ".py" and decision == "accept_repair":
            child_validation = rw.validate_python_candidate(
                path=path_str,
                baseline_bytes=current_bytes,
                candidate_bytes=selected_payload,
                budget=validation_budget,
            ).model_dump(mode="json")
            if child_validation.get("regression_detected"):
                raise ValueError(
                    f"Selected repair for '{path_str}' still regresses Python validation"
                )
            if child_validation.get("candidate_disposition") != "valid":
                raise ValueError(
                    f"Selected repair for '{path_str}' is not a valid Python candidate"
                )

        child_ops.append(
            {
                "action": "modify",
                "path": path_str,
                "current_sha256": current_sha,
                "payload_text": selected_text,
                "changed_lines": changed_lines,
                "logical_changed_lines": logical_changed_lines,
                "newline_only_changed_lines": newline_only_changed_lines,
                "newline_diagnostic": newline_diagnostic,
                "warnings": list(source_op.get("warnings") or []),
                "candidate_validation": child_validation,
                "authored_span_provenance": source_op.get("authored_span_provenance"),
                "changed_bytes": changed_bytes,
            }
        )

    if selected_proposal is not None and not selected_repair_found:
        raise ValueError(
            f"Patch {source_patch_id} repair proposal does not select a source operation"
        )
    if total_changed_lines > rw.MAX_PATCH_LINES:
        raise ValueError(
            f"Patch exceeds {rw.MAX_PATCH_LINES} changed-line limit ({total_changed_lines} lines)"
        )
    if total_changed_bytes > rw.MAX_PATCH_BYTES:
        raise ValueError(
            f"Patch exceeds {rw.MAX_PATCH_BYTES // 1024} KB changed-byte limit"
        )

    proposal_evidence = (
        selected_proposal.model_dump(mode="json")
        if selected_proposal is not None
        else None
    )
    return child_ops, combined_diff, source_validations, proposal_evidence


def _normalized_child_commit_description(
    source_description: str, source_patch_id: str, child_patch_id: str
) -> str:
    marker = f"Preview-ID: {source_patch_id}"
    if marker in source_description:
        return source_description.replace(marker, f"Preview-ID: {child_patch_id}")
    return source_description


def _verify_existing_child(
    child_dir: Path,
    *,
    source_patch_id: str,
    child_patch_id: str,
    resolution_request_id: str,
    request_hash: str,
    source_identity_hash: str,
    decision: PatchResolutionDecision,
    proposal_id: str,
) -> dict[str, Any]:
    _, child_manifest = _read_manifest(child_dir, child_patch_id)
    record = child_manifest.get("resolution")
    if not isinstance(record, dict) or not _resolution_record_matches(
        record,
        source_patch_id=source_patch_id,
        child_patch_id=child_patch_id,
        resolution_request_id=resolution_request_id,
        request_hash=request_hash,
        source_identity_hash=source_identity_hash,
        decision=decision,
        proposal_id=proposal_id,
    ):
        raise ValueError(
            f"Deterministic child collision for {child_patch_id}; existing content differs"
        )
    if child_manifest.get("status") not in {"preview_ok", "applied", "reverted"}:
        raise ValueError(
            f"Deterministic child {child_patch_id} has invalid lifecycle state"
        )
    return child_manifest


def resolve_patch_preview(
    repo_root: Path,
    runs_dir: Path,
    *,
    source_patch_id: str,
    resolution_request_id: str,
    decision: PatchResolutionDecision,
    proposal_id: str = "",
) -> dict[str, Any]:
    """Select one explicit source resolution and create/recover its child preview."""

    source_dir = rw._resolve_managed_patch_dir(runs_dir, source_patch_id)
    if not source_dir.exists():
        raise ValueError(f"Unknown source patch_id: {source_patch_id}")
    source_manifest_path, source_manifest = _read_manifest(source_dir, source_patch_id)
    if source_manifest.get("bundle_version") != 4:
        raise ValueError(
            f"Patch {source_patch_id} is not a resolvable v4 source preview"
        )
    expected_fingerprint = source_manifest.get("repo_fingerprint", "")
    if not expected_fingerprint or expected_fingerprint != rw._repo_fingerprint(
        repo_root
    ):
        raise ValueError(
            f"Patch {source_patch_id} does not belong to the requested repository"
        )

    request, request_hash, child_patch_id = build_resolution_request(
        source_patch_id=source_patch_id,
        resolution_request_id=resolution_request_id,
        decision=decision,
        proposal_id=proposal_id,
        source_manifest=source_manifest,
    )
    source_identity_hash = request.source_manifest_identity_hash
    child_dir = rw._resolve_managed_patch_dir(runs_dir, child_patch_id)

    status = source_manifest.get("status")
    existing_resolution = source_manifest.get("resolution")
    if status == "resolved":
        if not isinstance(existing_resolution, dict) or not _resolution_record_matches(
            existing_resolution,
            source_patch_id=source_patch_id,
            child_patch_id=child_patch_id,
            resolution_request_id=resolution_request_id,
            request_hash=request_hash,
            source_identity_hash=source_identity_hash,
            decision=decision,
            proposal_id=proposal_id,
        ):
            raise ValueError(
                f"Patch {source_patch_id} is already resolved by a different request"
            )
        if not child_dir.exists():
            raise ValueError(
                f"Patch {source_patch_id} resolved child is missing: {child_patch_id}"
            )
        child_manifest = _verify_existing_child(
            child_dir,
            source_patch_id=source_patch_id,
            child_patch_id=child_patch_id,
            resolution_request_id=resolution_request_id,
            request_hash=request_hash,
            source_identity_hash=source_identity_hash,
            decision=decision,
            proposal_id=proposal_id,
        )
        return _child_result(child_dir, child_manifest)
    if status != "preview_resolution_required":
        raise ValueError(
            f"Patch {source_patch_id} is not resolution-required (status: {status})"
        )
    if source_manifest.get("applied_at") or source_manifest.get("apply_result"):
        raise ValueError(
            f"Patch {source_patch_id} source has apply evidence and cannot resolve"
        )

    pending = source_manifest.get("resolution_pending")
    pending_record = {
        "schema_version": _RESOLUTION_RECORD_VERSION,
        "source_patch_id": source_patch_id,
        "child_patch_id": child_patch_id,
        "resolution_request_id": resolution_request_id,
        "resolution_request_hash": request_hash,
        "source_manifest_identity_hash": source_identity_hash,
        "decision": decision,
        "proposal_id": proposal_id,
    }
    if pending is not None:
        if not isinstance(pending, dict) or not _resolution_record_matches(
            pending,
            source_patch_id=source_patch_id,
            child_patch_id=child_patch_id,
            resolution_request_id=resolution_request_id,
            request_hash=request_hash,
            source_identity_hash=source_identity_hash,
            decision=decision,
            proposal_id=proposal_id,
        ):
            raise ValueError(
                f"Patch {source_patch_id} already has a different resolution request in progress"
            )

    child_ops, combined_diff, source_validations, proposal_evidence = (
        _preflight_selected_child(
            repo_root=repo_root,
            source_dir=source_dir,
            source_patch_id=source_patch_id,
            source_manifest=source_manifest,
            decision=decision,
            proposal_id=proposal_id,
        )
    )

    if pending is None:
        source_manifest["resolution_pending"] = pending_record
        rw._atomic_write_text(
            source_manifest_path,
            json.dumps(source_manifest, indent=2),
            ".soma_resolution_source_tmp",
        )

    resolution_record = {
        **pending_record,
        "candidate_validation_override": (
            "accept_original" if decision == "accept_original" else ""
        ),
        "selected_payloads": [
            {
                "path": op["path"],
                "sha256": hashlib.sha256(
                    op["payload_text"].encode("utf-8")
                ).hexdigest(),
                "size_bytes": len(op["payload_text"].encode("utf-8")),
            }
            for op in child_ops
        ],
        "source_candidate_validation": source_validations,
        "source_repair_proposal": proposal_evidence,
    }

    if child_dir.exists():
        child_manifest = _verify_existing_child(
            child_dir,
            source_patch_id=source_patch_id,
            child_patch_id=child_patch_id,
            resolution_request_id=resolution_request_id,
            request_hash=request_hash,
            source_identity_hash=source_identity_hash,
            decision=decision,
            proposal_id=proposal_id,
        )
    else:
        commit_title = str(source_manifest.get("commit_title", ""))
        commit_description = _normalized_child_commit_description(
            str(source_manifest.get("commit_description", "")),
            source_patch_id,
            child_patch_id,
        )
        rw._write_preview_bundle(
            repo_root,
            runs_dir,
            child_patch_id,
            child_ops,
            combined_diff,
            git_head=rw._git_head(repo_root),
            errors=[],
            warnings=list(source_manifest.get("warnings") or []),
            commit_title=commit_title,
            commit_description=commit_description,
            status_override="preview_ok",
        )
        child_manifest_path, child_manifest = _read_manifest(child_dir, child_patch_id)
        child_manifest["resolution_role"] = "child"
        child_manifest["resolution"] = resolution_record
        child_manifest["candidate_validation_override"] = (
            "accept_original" if decision == "accept_original" else ""
        )
        rw._atomic_write_text(
            child_manifest_path,
            json.dumps(child_manifest, indent=2),
            ".soma_resolution_child_tmp",
        )
        _, child_manifest = _read_manifest(child_dir, child_patch_id)

    source_manifest["status"] = "resolved"
    source_manifest["resolved_at"] = rw._utc_now()
    source_manifest["resolution"] = resolution_record
    source_manifest.pop("resolution_pending", None)
    rw._atomic_write_text(
        source_manifest_path,
        json.dumps(source_manifest, indent=2),
        ".soma_resolution_source_tmp",
    )

    result = _child_result(child_dir, child_manifest)
    result["idempotent_replay"] = False
    return result
