from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import redact_and_truncate
from .public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
    PublicView,
)
from .return_loop.atomic_writer import atomic_write_json
from .run_public_result import (
    PUBLIC_QUERY_OK_SEMANTICS,
    PUBLIC_RESULT_SCHEMA_VERSION,
    PUBLIC_RESULT_STATUS_FALLBACK,
    PUBLIC_RESULT_STATUS_READY,
    authoritative_result_sha256,
    build_public_result_fallback,
    build_public_result_projection,
    canonical_public_json_bytes,
    normalized_outcome,
)
from .run_store import TERMINAL_STATUSES, RunStore


MAX_PUBLICATION_ERROR = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_result(result: dict[str, Any]) -> tuple[dict[str, Any], bytes, str]:
    redacted = redact_and_truncate(result)
    content = (json.dumps(redacted, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return redacted, content, hashlib.sha256(content).hexdigest()


def _projection_matches(run: dict[str, Any], source_sha256: str) -> bool:
    return bool(
        run.get("public_result")
        and run.get("public_result_status")
        in {PUBLIC_RESULT_STATUS_READY, PUBLIC_RESULT_STATUS_FALLBACK}
        and run.get("public_result_schema_version") == PUBLIC_RESULT_SCHEMA_VERSION
        and run.get("public_result_source_sha256") == source_sha256
    )


def _emergency_projection(
    run: dict[str, Any], source_sha256: str, error: str
) -> dict[str, Any]:
    """Build a tiny serialization-safe fallback without invoking the projector."""
    outcome = normalized_outcome(run, dict(run.get("result") or {}))
    payload: dict[str, Any] = {
        "ok": True,
        "query_succeeded": True,
        "ok_semantics": PUBLIC_QUERY_OK_SEMANTICS,
        "operation": "terminal",
        "run_id": str(run.get("run_id") or ""),
        "repo_name": str(run.get("repo_name") or ""),
        "tool": str(run.get("tool") or ""),
        "terminal": True,
        "result_available": True,
        "run_ok": outcome.value in {"success", "partial"},
        "run_outcome": outcome.value,
        "projection_degraded": True,
        "result": {
            "status": str(run.get("status") or ""),
            "outcome": outcome.value,
            "summary": str(run.get("summary") or "")[:256],
            "error": str(run.get("error") or "")[:256],
            "safety_failure": bool(run.get("safety_failure")),
        },
        "projection_status": PUBLIC_RESULT_STATUS_FALLBACK,
        "projection_error": str(error)[:1024],
        "source_result_sha256": source_sha256,
        "evidence": {
            "authoritative_operation": "result",
            "run_id": str(run.get("run_id") or ""),
            "source_result_sha256": source_sha256,
        },
        "error": "",
        "view": PublicView.SUMMARY.value,
        "projection_version": PUBLIC_PROJECTION_SCHEMA_VERSION,
        "public_result_schema_version": PUBLIC_RESULT_SCHEMA_VERSION,
        "non_authoritative": True,
        "notice": NON_AUTHORITATIVE_NOTICE,
        "byte_budget": DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result,
        "payload_bytes": 0,
    }
    for _ in range(4):
        measured = len(canonical_public_json_bytes(payload))
        if payload["payload_bytes"] == measured:
            break
        payload["payload_bytes"] = measured
    return payload


def _projection_payload(
    run: dict[str, Any],
) -> tuple[dict[str, Any], str, str, str]:
    source_sha256 = authoritative_result_sha256(str(run.get("result_json") or "{}"))
    try:
        payload = build_public_result_projection(
            run, dict(run.get("result") or {}), source_sha256
        )
        return payload, PUBLIC_RESULT_STATUS_READY, "", source_sha256
    except Exception as exc:
        primary_error = f"{type(exc).__name__}: {exc}"[:MAX_PUBLICATION_ERROR]
        try:
            payload = build_public_result_fallback(run, source_sha256, primary_error)
            return payload, PUBLIC_RESULT_STATUS_FALLBACK, primary_error, source_sha256
        except Exception as fallback_exc:
            fallback_error = (
                f"{primary_error}; fallback {type(fallback_exc).__name__}: {fallback_exc}"
            )[:MAX_PUBLICATION_ERROR]
            return (
                _emergency_projection(run, source_sha256, fallback_error),
                PUBLIC_RESULT_STATUS_FALLBACK,
                fallback_error,
                source_sha256,
            )


def materialize_public_result(store: RunStore, run_id: str) -> dict[str, Any]:
    """Return a current durable projection, lazily materializing legacy rows."""
    snapshot = store.get_result_source_snapshot(run_id)
    if snapshot["status"] not in TERMINAL_STATUSES:
        raise ValueError("Run is not terminal")
    source_sha256 = authoritative_result_sha256(snapshot["result_json"])
    if _projection_matches(snapshot, source_sha256):
        return dict(snapshot["public_result"])

    payload, status, error, source_sha256 = _projection_payload(snapshot)
    recorded = store.record_public_result(
        run_id,
        public_result=payload,
        source_sha256=source_sha256,
        status=status,
        error=error,
        expected_state_version=int(snapshot["state_version"]),
    )
    if recorded is not None:
        return dict(recorded["public_result"])

    current = store.get_public_result_snapshot(run_id)
    if _projection_matches(current, source_sha256):
        return dict(current["public_result"])

    latest = store.get_result_source_snapshot(run_id)
    latest_source_sha256 = authoritative_result_sha256(latest["result_json"])
    if latest_source_sha256 != source_sha256:
        raise RuntimeError("Authoritative terminal result changed during projection")
    retried = store.record_public_result(
        run_id,
        public_result=payload,
        source_sha256=source_sha256,
        status=status,
        error=error,
        expected_state_version=int(latest["state_version"]),
    )
    if retried is not None:
        return dict(retried["public_result"])

    current = store.get_public_result_snapshot(run_id)
    if _projection_matches(current, source_sha256):
        return dict(current["public_result"])
    raise RuntimeError("Could not persist terminal public projection")


def _materialize_best_effort(store: RunStore, run_id: str) -> None:
    try:
        materialize_public_result(store, run_id)
    except Exception:
        # Authoritative publication must remain successful even when compact
        # projection persistence needs later lazy repair.
        return


def _publication_failure(
    store: RunStore,
    run: dict[str, Any],
    error: str,
    content_hash: str,
    public_result: dict[str, Any],
    public_result_status: str,
    public_result_error: str,
    source_sha256: str,
) -> dict[str, Any]:
    bounded_error = str(error)[:MAX_PUBLICATION_ERROR]
    recorded = store.record_result_publication_with_projection(
        run["run_id"],
        status="failed",
        error=bounded_error,
        public_result=public_result,
        public_result_source_sha256=source_sha256,
        public_result_status=public_result_status,
        public_result_error=public_result_error,
        expected_state_version=int(run["state_version"]),
    )
    current = recorded or store.get_run(run["run_id"])
    if (
        current.get("result_publication_status") == "published"
        and (not content_hash or current.get("result_published_hash") == content_hash)
    ):
        if not _projection_matches(current, source_sha256):
            _materialize_best_effort(store, run["run_id"])
            current = store.get_run(run["run_id"])
        return {
            "ok": True,
            "run_id": run["run_id"],
            "status": "published",
            "hash": current.get("result_published_hash", ""),
            "run": current,
        }
    return {
        "ok": False,
        "run_id": run["run_id"],
        "status": current.get("result_publication_status", "failed"),
        "error": bounded_error,
        "run": current,
    }


def terminal_result_publication_needs_repair(
    run: dict[str, Any], *, verify_artifact: bool = True
) -> bool:
    """Return whether a terminal run needs canonical publication repair.

    The check is read-only. Publication metadata and source-bound projection
    identity are always verified; artifact metadata/content checks can be
    bounded by callers so historical filesystem size cannot dominate startup.
    """
    if run.get("status") not in TERMINAL_STATUSES:
        return False
    try:
        _, content, content_hash = _canonical_result(run.get("result") or {})
        if (
            run.get("result_publication_status") != "published"
            or run.get("result_published_hash") != content_hash
        ):
            return True
        result_json = run.get("result_json")
        source_sha256 = (
            authoritative_result_sha256(result_json)
            if isinstance(result_json, str)
            else str(run.get("public_result_source_sha256") or "")
        )
        if not _projection_matches(run, source_sha256):
            return True
        if not verify_artifact:
            return False

        target = Path(str(run["run_dir"])) / "result.json"
        artifact = target.stat()
        if artifact.st_size != len(content):
            return True
        published_at = datetime.fromisoformat(str(run.get("result_published_at") or ""))
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        published_mtime_ns = int(published_at.timestamp() * 1_000_000_000)
        if artifact.st_mtime_ns <= published_mtime_ns:
            return False
        return target.read_bytes() != content
    except Exception:
        return True


def publish_run_result(store: RunStore, run_id: str) -> dict[str, Any]:
    """Publish the terminal winner and persist its source-bound projection."""
    run = store.get_result_source_snapshot(run_id)
    if run["status"] not in TERMINAL_STATUSES:
        return {
            "ok": False,
            "run_id": run_id,
            "status": run.get("result_publication_status", "not_published"),
            "error": "Run is not terminal",
            "run": store.get_run(run_id),
        }

    public_result, public_status, public_error, source_sha256 = _projection_payload(run)
    content_hash = ""
    try:
        _, content, content_hash = _canonical_result(run.get("result") or {})
        target = Path(run["run_dir"]) / "result.json"
        existing = target.read_bytes() if target.exists() else None
        if (
            existing == content
            and run.get("result_publication_status") == "published"
            and run.get("result_published_hash") == content_hash
        ):
            if not _projection_matches(run, source_sha256):
                _materialize_best_effort(store, run_id)
            current = store.get_run(run_id)
            return {
                "ok": True,
                "run_id": run_id,
                "status": "published",
                "hash": content_hash,
                "run": current,
            }
        if existing != content:
            atomic_write_json(target, redact_and_truncate(run.get("result") or {}))
        recorded = store.record_result_publication_with_projection(
            run_id,
            status="published",
            published_hash=content_hash,
            published_at=_utc_now(),
            public_result=public_result,
            public_result_source_sha256=source_sha256,
            public_result_status=public_status,
            public_result_error=public_error,
            expected_state_version=int(run["state_version"]),
        )
        if recorded is not None:
            return {
                "ok": True,
                "run_id": run_id,
                "status": "published",
                "hash": content_hash,
                "run": recorded,
            }

        current = store.get_run(run_id)
        if (
            current["status"] in TERMINAL_STATUSES
            and current.get("result_published_hash") == content_hash
            and current.get("result_publication_status") == "published"
        ):
            if not _projection_matches(current, source_sha256):
                _materialize_best_effort(store, run_id)
                current = store.get_run(run_id)
            return {
                "ok": True,
                "run_id": run_id,
                "status": "published",
                "hash": content_hash,
                "run": current,
            }
        if current["status"] in TERMINAL_STATUSES:
            retried = store.record_result_publication_with_projection(
                run_id,
                status="published",
                published_hash=content_hash,
                published_at=_utc_now(),
                public_result=public_result,
                public_result_source_sha256=source_sha256,
                public_result_status=public_status,
                public_result_error=public_error,
                expected_state_version=int(current["state_version"]),
            )
            if retried is not None:
                return {
                    "ok": True,
                    "run_id": run_id,
                    "status": "published",
                    "hash": content_hash,
                    "run": retried,
                }
        return _publication_failure(
            store,
            current,
            "Result publication metadata changed concurrently",
            content_hash,
            public_result,
            public_status,
            public_error,
            source_sha256,
        )
    except Exception as exc:
        return _publication_failure(
            store,
            run,
            f"Could not publish result artifact: {exc}",
            content_hash,
            public_result,
            public_status,
            public_error,
            source_sha256,
        )
