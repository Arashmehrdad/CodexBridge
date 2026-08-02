from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Final

from .public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    NON_AUTHORITATIVE_NOTICE,
    NormalizedOutcome,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
    PublicView,
    truncate_utf8,
)
from .safety import redact_secret_values


PUBLIC_RESULT_SCHEMA_VERSION: Final[str] = "cf1.public-result.v1"
PUBLIC_QUERY_OK_SEMANTICS: Final[str] = "query_success"
PUBLIC_RESULT_STATUS_NOT_MATERIALIZED: Final[str] = "not_materialized"
PUBLIC_RESULT_STATUS_READY: Final[str] = "ready"
PUBLIC_RESULT_STATUS_FALLBACK: Final[str] = "fallback"
PUBLIC_RESULT_STATUSES: Final[frozenset[str]] = frozenset(
    {
        PUBLIC_RESULT_STATUS_NOT_MATERIALIZED,
        PUBLIC_RESULT_STATUS_READY,
        PUBLIC_RESULT_STATUS_FALLBACK,
    }
)

_SUMMARY_BYTES = 2048
_ERROR_BYTES = 2048
_LIST_ITEM_BYTES = 256
_PREVIEW_BYTES = 2048
_MAX_CHANGED_FILES = 20
_MAX_RISKS = 8
_MAX_ARTIFACTS = 12


def _compacted_total_count(value: object) -> int | None:
    """Return the exact original count from a compacted path-list summary.

    Managed repository results replace repository-scale path lists with a
    compact summary that still carries ``total_count``. Older records hold plain
    lists, so both shapes must project to the same public count rather than
    letting the newer shape fall through and disappear from the summary.
    """
    if isinstance(value, dict) and isinstance(value.get("total_count"), int):
        return int(value["total_count"])
    return None


def _managed_apply_summary(run: dict[str, Any], result: dict[str, Any]) -> dict[str, object] | None:
    """Return bounded terminal metadata for managed writes without exposing raw output."""
    if str(run.get("tool") or result.get("tool") or "") != "repo_apply":
        return None

    summary: dict[str, object] = {}
    for key in ("operation", "patch_id", "cleanup_id", "commit_hash", "idempotent_replay"):
        value = result.get(key)
        if value not in (None, "", [], {}):
            summary[key] = value if isinstance(value, (bool, int, float)) else _bounded_text(value, 256)[0]

    rollback_status = result.get("rollback_status")
    if rollback_status in (None, ""):
        rollback = result.get("rollback")
        if isinstance(rollback, dict):
            rollback_status = rollback.get("status") or rollback.get("state")
        elif rollback not in (None, ""):
            rollback_status = rollback
    if rollback_status not in (None, ""):
        summary["rollback_status"] = _bounded_text(rollback_status, 128)[0]

    validation = result.get("validation_results")
    if isinstance(validation, list):
        summary["validation_summary"] = {
            "total": len(validation),
            "passed": sum(1 for item in validation if isinstance(item, dict) and item.get("ok") is True),
            "failed": sum(1 for item in validation if isinstance(item, dict) and item.get("ok") is False),
        }
    elif validation not in (None, "", [], {}):
        summary["validation_summary"] = _canonical_preview(validation, 512)[0]

    preserved = result.get("preserved_preexisting_changes")
    if isinstance(preserved, list):
        summary["preserved_work"] = {"count": len(preserved)}
    elif isinstance(preserved, int):
        summary["preserved_work"] = {"count": preserved}
    elif _compacted_total_count(preserved) is not None:
        summary["preserved_work"] = {"count": _compacted_total_count(preserved)}
    if result.get("remaining_dirty_files") not in (None, "", [], {}):
        remaining = result["remaining_dirty_files"]
        remaining_total = _compacted_total_count(remaining)
        if isinstance(remaining, list):
            summary["remaining_work"] = {"count": len(remaining)}
        elif remaining_total is not None:
            summary["remaining_work"] = {"count": remaining_total}
        else:
            summary["remaining_work"] = _bounded_text(remaining, 256)[0]

    freshness = result.get("wiki_freshness")
    if isinstance(freshness, dict):
        stale = bool(freshness.get("stale", False))
        knowledge_freshness: dict[str, object] = {
            "stale": stale,
            "source_generation": int(freshness.get("source_generation", 0) or 0),
            "indexed_source_generation": int(
                freshness.get("indexed_source_generation", 0) or 0
            ),
            "generation_id": _bounded_text(
                freshness.get("generation_id", ""), 128
            )[0],
            "refresh_recommended": stale,
        }
        stale_reason = freshness.get("stale_reason")
        if stale_reason:
            knowledge_freshness["stale_reason"] = _bounded_text(
                stale_reason, 256
            )[0]
        if stale:
            knowledge_freshness["refresh_action"] = "knowledge_action(refresh_wiki)"
        summary["knowledge_freshness"] = knowledge_freshness

    return summary or {"operation": "managed_write"}


def canonical_public_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def authoritative_result_sha256(result_json: str) -> str:
    return sha256(str(result_json).encode("utf-8")).hexdigest()


def _bounded_text(value: object, maximum_bytes: int) -> tuple[str, dict[str, object] | None]:
    safe = redact_secret_values(str(value or ""))
    truncated = truncate_utf8(safe, maximum_bytes)
    metadata = None
    if truncated.truncated:
        metadata = {
            "original_bytes": truncated.original_bytes,
            "returned_bytes": truncated.returned_bytes,
            "omitted_sha256": truncated.omitted_sha256,
        }
    return truncated.text, metadata


def _canonical_preview(value: object, maximum_bytes: int) -> tuple[str, dict[str, object] | None]:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
    except (TypeError, ValueError):
        encoded = str(value)
    return _bounded_text(encoded, maximum_bytes)


def _source_values(result: dict[str, Any], keys: tuple[str, ...]) -> list[object]:
    values: list[object] = []
    for key in keys:
        value = result.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        else:
            values.append(value)
    return values


def _bounded_list(
    values: list[object],
    *,
    maximum_items: int,
    maximum_item_bytes: int,
) -> tuple[list[str], dict[str, object] | None]:
    selected: list[str] = []
    for value in values[:maximum_items]:
        if isinstance(value, str):
            text, _metadata = _bounded_text(value, maximum_item_bytes)
        else:
            text, _metadata = _canonical_preview(value, maximum_item_bytes)
        selected.append(text)
    if len(values) <= maximum_items:
        return selected, None
    omitted = values[maximum_items:]
    return selected, {
        "original_count": len(values),
        "returned_count": len(selected),
        "omitted_sha256": sha256(canonical_public_json_bytes(omitted)).hexdigest(),
    }


def _artifact_references(result: dict[str, Any], maximum_items: int) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    raw = _source_values(result, ("staged_artifacts", "artifacts", "artifact_refs"))
    selected: list[dict[str, object]] = []
    allowed = (
        "classification",
        "relative_path",
        "path",
        "sha256",
        "size_bytes",
        "stream",
        "media_type",
    )
    for item in raw[:maximum_items]:
        if not isinstance(item, dict):
            text, _metadata = _canonical_preview(item, _LIST_ITEM_BYTES)
            selected.append({"reference": text})
            continue
        projected: dict[str, object] = {}
        for key in allowed:
            if key not in item:
                continue
            value = item[key]
            if isinstance(value, str):
                projected[key] = _bounded_text(value, _LIST_ITEM_BYTES)[0]
            elif isinstance(value, (int, float, bool)) or value is None:
                projected[key] = value
        if projected:
            selected.append(projected)
    if len(raw) <= maximum_items:
        return selected, None
    return selected, {
        "original_count": len(raw),
        "returned_count": len(selected),
        "omitted_sha256": sha256(canonical_public_json_bytes(raw[maximum_items:])).hexdigest(),
    }


def normalized_outcome(run: dict[str, Any], result: dict[str, Any]) -> NormalizedOutcome:
    status = str(result.get("status") or run.get("status") or "").strip().lower()
    classification = str(result.get("classification") or "").strip().lower()
    safety_failure = bool(result.get("safety_failure") or run.get("safety_failure"))

    explicit = {
        "partial": NormalizedOutcome.PARTIAL,
        "validation_failure": NormalizedOutcome.VALIDATION_FAILURE,
        "policy_denial": NormalizedOutcome.POLICY_DENIAL,
        "policy_failure": NormalizedOutcome.POLICY_DENIAL,
        "needs_input": NormalizedOutcome.NEEDS_INPUT,
        "cancellation_requested": NormalizedOutcome.CANCELLATION_REQUESTED,
        "cancellation_verified": NormalizedOutcome.CANCELLATION_VERIFIED,
        "cancellation_uncertain": NormalizedOutcome.CANCELLATION_UNCERTAIN,
        "infrastructure_failure": NormalizedOutcome.INFRASTRUCTURE_FAILURE,
        "cleanup_incomplete": NormalizedOutcome.CLEANUP_INCOMPLETE,
        "ambiguous_side_effect": NormalizedOutcome.AMBIGUOUS_SIDE_EFFECT,
        "reconciliation_required": NormalizedOutcome.RECONCILIATION_REQUIRED,
        "success": NormalizedOutcome.SUCCESS,
    }
    if classification in explicit:
        return explicit[classification]
    if safety_failure:
        return NormalizedOutcome.POLICY_DENIAL
    if status == "needs_input":
        return NormalizedOutcome.NEEDS_INPUT
    if status == "partial":
        return NormalizedOutcome.PARTIAL
    if status == "cancelled":
        return NormalizedOutcome.CANCELLATION_VERIFIED
    if status in {"cancellation_pending", "cancellation_requested"}:
        return NormalizedOutcome.CANCELLATION_REQUESTED
    if status == "timed_out":
        return NormalizedOutcome.INFRASTRUCTURE_FAILURE
    if status == "completed":
        if result.get("process_success") is False:
            return NormalizedOutcome.VALIDATION_FAILURE
        return NormalizedOutcome.SUCCESS
    if status in {
        "queued",
        "launch_pending",
        "running",
        "awaiting_controller",
        "recovery_pending",
    }:
        return NormalizedOutcome.PENDING
    if status == "failed":
        return NormalizedOutcome.UNKNOWN_FAILURE
    return NormalizedOutcome.PENDING


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    budget = DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result
    result = dict(payload)
    result["payload_bytes"] = 0
    for _ in range(4):
        measured = len(canonical_public_json_bytes(result))
        if result["payload_bytes"] == measured:
            break
        result["payload_bytes"] = measured
    actual = len(canonical_public_json_bytes(result))
    if actual != result["payload_bytes"]:
        result["payload_bytes"] = actual
        actual = len(canonical_public_json_bytes(result))
    if actual > budget:
        raise ValueError("Compact terminal result exceeds its serialized UTF-8 byte budget")
    return result


def _candidate(
    run: dict[str, Any],
    result: dict[str, Any],
    source_sha256: str,
    *,
    divisor: int,
) -> dict[str, Any]:
    text_divisor = max(1, divisor)
    item_limit_divisor = max(1, divisor)
    truncated_fields: dict[str, dict[str, object]] = {}

    summary, summary_meta = _bounded_text(
        result.get("summary") or run.get("summary") or "",
        max(32, _SUMMARY_BYTES // text_divisor),
    )
    error, error_meta = _bounded_text(
        result.get("error") or run.get("error") or "",
        max(32, _ERROR_BYTES // text_divisor),
    )
    if summary_meta:
        truncated_fields["summary"] = summary_meta
    if error_meta:
        truncated_fields["error"] = error_meta

    changed_files, changed_meta = _bounded_list(
        _source_values(result, ("changed_files", "introduced_changes", "workspace_changes")),
        maximum_items=max(1, _MAX_CHANGED_FILES // item_limit_divisor),
        maximum_item_bytes=max(64, _LIST_ITEM_BYTES // text_divisor),
    )
    risks, risks_meta = _bounded_list(
        _source_values(result, ("remaining_risks", "risks")),
        maximum_items=max(1, _MAX_RISKS // item_limit_divisor),
        maximum_item_bytes=max(64, _LIST_ITEM_BYTES // text_divisor),
    )
    artifacts, artifacts_meta = _artifact_references(
        result, max(1, _MAX_ARTIFACTS // item_limit_divisor)
    )

    tests_source = {
        key: result[key]
        for key in ("tests_run", "test_results", "validation_results")
        if result.get(key) not in (None, "", [], {})
    }
    tests_preview = ""
    tests_meta = None
    if tests_source:
        tests_preview, tests_meta = _canonical_preview(
            tests_source, max(128, _PREVIEW_BYTES // text_divisor)
        )

    diagnostics_source = {
        key: result[key]
        for key in (
            "diagnostics",
            "validation_errors",
            "commit_error",
            "termination",
            "result_publication_error",
        )
        if result.get(key) not in (None, "", [], {})
    }
    diagnostics_preview = ""
    diagnostics_meta = None
    if diagnostics_source:
        diagnostics_preview, diagnostics_meta = _canonical_preview(
            diagnostics_source, max(128, _PREVIEW_BYTES // text_divisor)
        )

    validation_preview = ""
    validation_meta = None
    if result.get("validation") not in (None, "", [], {}):
        validation_preview, validation_meta = _canonical_preview(
            result["validation"], max(256, _PREVIEW_BYTES // text_divisor)
        )

    collection_truncation = {
        key: value
        for key, value in {
            "changed_files": changed_meta,
            "risks": risks_meta,
            "artifacts": artifacts_meta,
            "tests": tests_meta,
            "diagnostics": diagnostics_meta,
            "validation": validation_meta,
        }.items()
        if value
    }
    outcome = normalized_outcome(run, result)
    compact_result = {
        "status": result.get("status") or run.get("status"),
        "classification": result.get("classification") or "",
        "outcome": outcome.value,
        "process_success": result.get("process_success"),
        "exit_code": result.get("exit_code", run.get("exit_code")),
        "summary": summary,
        "error": error,
        "safety_failure": bool(result.get("safety_failure") or run.get("safety_failure")),
        "started_at": result.get("started_at", run.get("started_at")),
        "ended_at": result.get("ended_at", run.get("ended_at")),
        "duration_seconds": result.get("duration_seconds", run.get("duration_seconds")),
        "changed_files": changed_files,
        "risks": risks,
        "artifacts": artifacts,
        "tests": tests_preview,
        "diagnostics": diagnostics_preview,
        "validation": validation_preview,
    }
    managed_apply = _managed_apply_summary(run, result)
    if managed_apply is not None:
        compact_result["managed_apply"] = managed_apply
    if truncated_fields:
        compact_result["truncated_fields"] = truncated_fields
    if collection_truncation:
        compact_result["truncated_collections"] = collection_truncation

    run_ok = outcome in {NormalizedOutcome.SUCCESS, NormalizedOutcome.PARTIAL}
    return {
        "ok": True,
        "query_succeeded": True,
        "ok_semantics": PUBLIC_QUERY_OK_SEMANTICS,
        "operation": "terminal",
        "run_id": run["run_id"],
        "repo_name": run["repo_name"],
        "tool": run["tool"],
        "terminal": True,
        "result_available": True,
        "run_ok": run_ok,
        "run_outcome": outcome.value,
        "result": compact_result,
        "projection_status": PUBLIC_RESULT_STATUS_READY,
        "source_result_sha256": source_sha256,
        "evidence": {
            "authoritative_operation": "result",
            "run_id": run["run_id"],
            "source_result_sha256": source_sha256,
        },
        "error": "",
        "view": PublicView.SUMMARY.value,
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "public_result_schema_version": PUBLIC_RESULT_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "byte_budget": DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result,
    }


def build_public_result_projection(
    run: dict[str, Any], result: dict[str, Any], source_sha256: str
) -> dict[str, Any]:
    for divisor in (1, 2, 4, 8, 16, 32, 64, 128):
        try:
            return _finalize(_candidate(run, result, source_sha256, divisor=divisor))
        except ValueError:
            continue
    raise ValueError("Terminal public projection cannot fit its public byte budget")


def build_pending_public_result(run: dict[str, Any]) -> dict[str, Any]:
    """Build the bounded response used when a run is not terminal yet."""
    summary, summary_meta = _bounded_text(run.get("summary") or "", 512)
    error, error_meta = _bounded_text(run.get("error") or "", 512)
    compact_result: dict[str, Any] = {
        "status": run.get("status"),
        "outcome": NormalizedOutcome.PENDING.value,
        "summary": summary,
        "error": error,
        "safety_failure": bool(run.get("safety_failure")),
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "duration_seconds": run.get("duration_seconds"),
    }
    truncation = {
        key: value
        for key, value in {"summary": summary_meta, "error": error_meta}.items()
        if value
    }
    if truncation:
        compact_result["truncated_fields"] = truncation
    return _finalize(
        {
            "ok": True,
            "query_succeeded": True,
            "ok_semantics": PUBLIC_QUERY_OK_SEMANTICS,
            "operation": "terminal",
            "run_id": run["run_id"],
            "repo_name": run["repo_name"],
            "tool": run["tool"],
            "terminal": False,
            "result_available": False,
            "run_ok": None,
            "run_outcome": NormalizedOutcome.PENDING.value,
            "result": compact_result,
            "projection_status": "pending",
            "source_result_sha256": "",
            "evidence": {
                "authoritative_operation": "control",
                "run_id": run["run_id"],
            },
            "error": "",
            "view": PublicView.SUMMARY.value,
            "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
            "public_result_schema_version": PUBLIC_RESULT_SCHEMA_VERSION,
            "non_authoritative": True,
            "notice": NON_AUTHORITATIVE_NOTICE,
            "byte_budget": DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result,
        }
    )


def build_public_result_fallback(
    run: dict[str, Any], source_sha256: str, error: str
) -> dict[str, Any]:
    bounded_error, metadata = _bounded_text(error, 1024)
    outcome = normalized_outcome(run, dict(run.get("result") or {}))
    payload: dict[str, Any] = {
        "ok": True,
        "query_succeeded": True,
        "ok_semantics": PUBLIC_QUERY_OK_SEMANTICS,
        "operation": "terminal",
        "run_id": run["run_id"],
        "repo_name": run["repo_name"],
        "tool": run["tool"],
        "terminal": True,
        "result_available": True,
        "run_ok": outcome in {NormalizedOutcome.SUCCESS, NormalizedOutcome.PARTIAL},
        "run_outcome": outcome.value,
        "projection_degraded": True,
        "result": {
            "status": run.get("status"),
            "outcome": outcome.value,
            "summary": _bounded_text(run.get("summary") or "", 512)[0],
            "error": _bounded_text(run.get("error") or "", 512)[0],
            "safety_failure": bool(run.get("safety_failure")),
        },
        "projection_status": PUBLIC_RESULT_STATUS_FALLBACK,
        "projection_error": bounded_error,
        "source_result_sha256": source_sha256,
        "evidence": {
            "authoritative_operation": "result",
            "run_id": run["run_id"],
            "source_result_sha256": source_sha256,
        },
        "error": "",
        "view": PublicView.SUMMARY.value,
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "public_result_schema_version": PUBLIC_RESULT_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "byte_budget": DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result,
    }
    if metadata:
        payload["projection_error_truncation"] = metadata
    return _finalize(payload)
