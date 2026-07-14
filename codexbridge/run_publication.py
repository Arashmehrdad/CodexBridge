from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import redact_and_truncate
from .return_loop.atomic_writer import atomic_write_json
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


def _publication_failure(
    store: RunStore,
    run: dict[str, Any],
    error: str,
    content_hash: str = "",
) -> dict[str, Any]:
    bounded_error = str(error)[:MAX_PUBLICATION_ERROR]
    recorded = store.record_result_publication(
        run["run_id"],
        status="failed",
        error=bounded_error,
        expected_state_version=int(run["state_version"]),
    )
    current = recorded or store.get_run(run["run_id"])
    if (
        current.get("result_publication_status") == "published"
        and (not content_hash or current.get("result_published_hash") == content_hash)
    ):
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


def publish_run_result(store: RunStore, run_id: str) -> dict[str, Any]:
    """Publish the database terminal winner as the canonical result artifact."""
    run = store.get_run(run_id)
    if run["status"] not in TERMINAL_STATUSES:
        return {
            "ok": False,
            "run_id": run_id,
            "status": run.get("result_publication_status", "not_published"),
            "error": "Run is not terminal",
            "run": run,
        }

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
            return {
                "ok": True,
                "run_id": run_id,
                "status": "published",
                "hash": content_hash,
                "run": run,
            }
        if existing != content:
            atomic_write_json(target, redact_and_truncate(run.get("result") or {}))
        published_at = _utc_now()
        recorded = store.record_result_publication(
            run_id,
            status="published",
            published_hash=content_hash,
            published_at=published_at,
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

        # Another publisher may have won the metadata CAS after writing the
        # same deterministic bytes. Treat that as an idempotent success.
        current = store.get_run(run_id)
        if (
            current["status"] in TERMINAL_STATUSES
            and current.get("result_published_hash") == content_hash
            and current.get("result_publication_status") == "published"
        ):
            return {
                "ok": True,
                "run_id": run_id,
                "status": "published",
                "hash": content_hash,
                "run": current,
            }
        if current["status"] in TERMINAL_STATUSES:
            retried = store.record_result_publication(
                run_id,
                status="published",
                published_hash=content_hash,
                published_at=_utc_now(),
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
        )
    except Exception as exc:
        return _publication_failure(
            store,
            run,
            f"Could not publish result artifact: {exc}",
            content_hash,
        )
