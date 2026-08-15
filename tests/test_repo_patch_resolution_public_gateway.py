from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

import soma.server as server
from soma.gateway_models import RepoPreviewRequest


SOURCE_PATCH_ID = "20260815T010203Z_patch_abcdef12"
PROPOSAL_ID = "repair_0123456789abcdef"


def _adapter() -> TypeAdapter:
    return TypeAdapter(RepoPreviewRequest)


def _base_request() -> dict:
    return {
        "operation": "resolve_patch",
        "repo_name": "repo",
        "source_patch_id": SOURCE_PATCH_ID,
        "resolution_request_id": "controller-resolution-1",
    }


def test_resolve_patch_request_contract_accepts_only_valid_cross_fields() -> None:
    adapter = _adapter()
    repaired = adapter.validate_python(
        {
            **_base_request(),
            "decision": "accept_repair",
            "proposal_id": PROPOSAL_ID,
        }
    )
    assert repaired.proposal_id == PROPOSAL_ID
    original = adapter.validate_python(
        {**_base_request(), "decision": "accept_original"}
    )
    assert original.proposal_id == ""
    assert original.response_budget_bytes == 12 * 1024

    invalid_requests = [
        {**_base_request(), "decision": "accept_repair"},
        {
            **_base_request(),
            "decision": "accept_original",
            "proposal_id": PROPOSAL_ID,
        },
        {**_base_request(), "decision": "accept_repair", "proposal_id": "bad"},
        {**_base_request(), "decision": "accept_original", "source_patch_id": "bad"},
        {**_base_request(), "decision": "accept_original", "extra": "forbidden"},
    ]
    for payload in invalid_requests:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_repo_preview_resolve_patch_dispatches_to_accepted_resolution_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    def fake_resolve(*args):
        calls.append(args)
        return {
            "ok": True,
            "patch_id": "20260815T010203Z_patch_12345678",
            "repo_name": "repo",
            "applicable": True,
            "candidate_validation_status": "valid",
            "resolution_required": False,
            "repair_available": False,
            "repair_proposal_id": "",
            "source_patch_id": SOURCE_PATCH_ID,
            "selected_child_patch_id": "20260815T010203Z_patch_12345678",
            "decision": "accept_repair",
            "resolution_request_id": "controller-resolution-1",
            "proposal_id": PROPOSAL_ID,
            "idempotent_replay": False,
            "changed_files": ["sample.py"],
            "diff": "diff body",
            "validation_errors": [],
            "warnings": [],
            "newline_diagnostics": [],
            "error": "",
        }

    monkeypatch.setattr(server, "resolve_repo_patch_preview", fake_resolve)
    request = _adapter().validate_python(
        {
            **_base_request(),
            "decision": "accept_repair",
            "proposal_id": PROPOSAL_ID,
            "response_budget_bytes": 4096,
        }
    )
    result = server.repo_preview(request)

    assert calls == [
        (
            "repo",
            SOURCE_PATCH_ID,
            "controller-resolution-1",
            "accept_repair",
            PROPOSAL_ID,
        )
    ]
    assert result["patch_id"] == "20260815T010203Z_patch_12345678"
    assert result["source_patch_id"] == SOURCE_PATCH_ID
    assert result["selected_child_patch_id"] == result["patch_id"]
    assert result["candidate_validation_status"] == "valid"
    assert result["decision"] == "accept_repair"
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096


def test_patch_status_compact_exposes_resolution_continuity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_id = "20260815T010203Z_patch_12345678"
    monkeypatch.setattr(
        server,
        "_repo_context",
        lambda _repo_name: ("repo", Path("C:/repo"), "repo"),
    )
    monkeypatch.setattr(server, "_get_runs_dir", lambda: Path("C:/runs"))
    monkeypatch.setattr(
        server._repo_writer,
        "get_patch_status",
        lambda *_args: {
            "ok": True,
            "patch_id": SOURCE_PATCH_ID,
            "bundle_version": 4,
            "status": "resolved",
            "applicable": False,
            "resolution_required": False,
            "repair_available": True,
            "repair_proposal_id": PROPOSAL_ID,
            "source_patch_id": SOURCE_PATCH_ID,
            "resolution_decision": "accept_repair",
            "selected_child_patch_id": child_id,
            "candidate_validation_status": "regression_detected",
            "created_at": "2026-08-15T01:02:03+00:00",
            "applied_at": "",
            "reverted_at": "",
            "changed_files": ["sample.py"],
            "apply_result": {},
            "errors": [],
            "error": "",
        },
    )

    result = server.get_patch_status(
        "repo", SOURCE_PATCH_ID, "compact", response_budget_bytes=4096
    )

    assert result["bundle_version"] == 4
    assert result["applicable"] is False
    assert result["repair_available"] is True
    assert result["repair_proposal_id"] == PROPOSAL_ID
    assert result["source_patch_id"] == SOURCE_PATCH_ID
    assert result["resolution_decision"] == "accept_repair"
    assert result["selected_child_patch_id"] == child_id
    assert result["candidate_validation_status"] == "regression_detected"
    assert result["response_bytes"] <= 4096
