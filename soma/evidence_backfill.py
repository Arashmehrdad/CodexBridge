"""Resumable, hash-verified backfill for amplified managed-repository results.

Historical ``repo_apply`` runs stored repository-scale bodies inline in
``runs.result_json``: two full stage manifests, Git status, and repeated
dirty-file inventories. New runs no longer do this, but existing rows still
hold that evidence and it is the only complete copy — the ``result.json``
artifact written beside each run is redacted and truncated, so it cannot serve
as the authoritative body.

This module moves each amplified body into a complete, unredacted, immutable
``commit_evidence.json`` artifact in the run's own directory, verifies it by
SHA-256, proves the public projection is unchanged, and only then rewrites the
row to the compact form.

Invariants:

* Nothing is deleted. The full body is written and verified *before* the row is
  compacted; a failure at any step leaves the row exactly as it was.
* Opaque identity is never rewritten. Only ``result_json`` changes; ``run_id``,
  ``run_dir``, published hashes, and every other column are untouched.
* Progress is durable. An interrupted run resumes without redoing work and
  without double-writing.
* Old and migrated rows stay readable together. The compact record carries a
  ``commit_evidence_ref`` and the public projection is proven equivalent.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from . import git_tools
from .run_public_result import build_public_result_projection

BACKFILL_COMPONENT = "evidence_backfill"
BACKFILL_VERSION = 1
EVIDENCE_ARTIFACT = "commit_evidence.json"

STATE_MIGRATED = "migrated"
STATE_ALREADY_COMPACT = "already_compact"
STATE_SKIPPED = "skipped"
STATE_FAILED = "failed"

PROGRESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_backfill_progress (
    run_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    backfill_version INTEGER NOT NULL,
    artifact_sha256 TEXT NOT NULL DEFAULT '',
    artifact_bytes INTEGER NOT NULL DEFAULT 0,
    original_bytes INTEGER NOT NULL DEFAULT 0,
    compact_bytes INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL
)
"""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _connect(database: Path, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(database.as_posix())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _write_verified_artifact(run_dir: Path, body: dict[str, Any]) -> tuple[str, int]:
    """Atomically write the complete body and verify it by reading it back.

    The payload is written unredacted and untruncated: this is the authoritative
    evidence, not a projection. The digest is computed from what is actually on
    disk after the rename, so a partial or altered write cannot be reported as a
    success.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(body, sort_keys=True, ensure_ascii=False)
    encoded = payload.encode("utf-8")
    expected = sha256(encoded).hexdigest()

    handle, temporary_name = tempfile.mkstemp(
        dir=run_dir.as_posix(), prefix=".commit_evidence-", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, run_dir / EVIDENCE_ARTIFACT)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    written = (run_dir / EVIDENCE_ARTIFACT).read_bytes()
    actual = sha256(written).hexdigest()
    if actual != expected or len(written) != len(encoded):
        raise OSError(
            f"Evidence artifact verification failed: expected {expected}, read {actual}"
        )
    return actual, len(written)


def _projection_for(row: sqlite3.Row, result: dict[str, Any]) -> dict[str, Any]:
    run = dict(row)
    run["result"] = result
    return build_public_result_projection(run, result, "backfill-equivalence-probe")


def _compact_result(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    commit_result = result.get("commit_result")
    if not isinstance(commit_result, dict):
        return result, {}
    compact_commit, full_body = git_tools.compact_commit_result(commit_result)
    preserved = result.get("preserved_preexisting_changes")
    compact = dict(result)
    if isinstance(preserved, list):
        full_body["preserved_preexisting_changes"] = preserved
        compact["preserved_preexisting_changes"] = git_tools._compact_path_list(
            preserved
        )
    if not full_body:
        return result, {}
    compact["commit_result"] = compact_commit
    return compact, full_body


def iter_candidates(
    connection: sqlite3.Connection, *, minimum_bytes: int
) -> Iterator[sqlite3.Row]:
    query = (
        "SELECT * FROM runs "
        "WHERE result_json IS NOT NULL AND length(result_json) >= ? "
        "ORDER BY length(result_json) DESC"
    )
    yield from connection.execute(query, (minimum_bytes,))


def _resolve_run_dir(run_dir: Path, artifact_root: Path | None) -> Path:
    """Redirect artifact writes under ``artifact_root`` for isolated rehearsal.

    A rehearsal against a copied database must not write into the live run
    directories, because ``run_dir`` still points at the real ones.
    """
    if artifact_root is None:
        return run_dir
    return artifact_root / run_dir.name


def backfill_run(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    apply_changes: bool,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    run_id = str(row["run_id"])
    original = str(row["result_json"] or "")
    outcome: dict[str, Any] = {
        "run_id": run_id,
        "state": STATE_SKIPPED,
        "original_bytes": len(original.encode("utf-8")),
        "compact_bytes": 0,
        "artifact_sha256": "",
        "artifact_bytes": 0,
        "detail": "",
    }

    try:
        result = json.loads(original)
    except (TypeError, ValueError) as exc:
        outcome["detail"] = f"unparsable result_json: {exc}"[:500]
        return outcome
    if not isinstance(result, dict):
        outcome["detail"] = "result_json is not an object"
        return outcome

    compact, full_body = _compact_result(result)
    if not full_body:
        outcome["state"] = STATE_ALREADY_COMPACT
        outcome["detail"] = "no repository-scale body present"
        return outcome

    run_dir_value = str(row["run_dir"] or "")
    if not run_dir_value:
        outcome["detail"] = "run has no run_dir; refusing to externalize evidence"
        return outcome
    run_dir = Path(run_dir_value)
    if not run_dir.is_dir():
        outcome["detail"] = f"run_dir missing: {run_dir_value}"
        return outcome
    target_dir = _resolve_run_dir(run_dir, artifact_root)

    # Reconstructability gate: the compacted row must project to the same public
    # result as the inline row, or it is not a safe replacement.
    try:
        before = _projection_for(row, result)
        after = _projection_for(row, compact)
    except Exception as exc:  # projection must never be assumed to succeed
        outcome["state"] = STATE_FAILED
        outcome["detail"] = f"projection failed: {type(exc).__name__}: {exc}"[:500]
        return outcome
    if before != after:
        outcome["state"] = STATE_FAILED
        outcome["detail"] = "public projection would change; row left untouched"
        return outcome

    compact_json = json.dumps(compact, sort_keys=True, ensure_ascii=False)
    outcome["compact_bytes"] = len(compact_json.encode("utf-8"))

    if not apply_changes:
        outcome["state"] = STATE_MIGRATED
        outcome["detail"] = "dry-run"
        outcome["artifact_bytes"] = len(
            json.dumps(full_body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        return outcome

    try:
        digest, artifact_bytes = _write_verified_artifact(target_dir, full_body)
    except OSError as exc:
        outcome["state"] = STATE_FAILED
        outcome["detail"] = f"artifact write/verify failed: {exc}"[:500]
        return outcome

    compact["commit_evidence_ref"] = {
        "artifact": EVIDENCE_ARTIFACT,
        "fields": sorted(full_body),
        "available": True,
        "sha256": digest,
        "size_bytes": artifact_bytes,
        "backfilled": True,
        "backfill_version": BACKFILL_VERSION,
    }
    compact_json = json.dumps(compact, sort_keys=True, ensure_ascii=False)
    outcome["compact_bytes"] = len(compact_json.encode("utf-8"))
    outcome["artifact_sha256"] = digest
    outcome["artifact_bytes"] = artifact_bytes

    # The row is only rewritten after the complete body is on disk and verified.
    with connection:
        connection.execute(
            "UPDATE runs SET result_json = ? WHERE run_id = ? AND result_json = ?",
            (compact_json, run_id, original),
        )
        connection.execute(
            "INSERT OR REPLACE INTO evidence_backfill_progress "
            "(run_id, state, backfill_version, artifact_sha256, artifact_bytes, "
            " original_bytes, compact_bytes, detail, recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                STATE_MIGRATED,
                BACKFILL_VERSION,
                digest,
                artifact_bytes,
                outcome["original_bytes"],
                outcome["compact_bytes"],
                "",
                _utc_now(),
            ),
        )
    outcome["state"] = STATE_MIGRATED
    return outcome


def run_backfill(
    database: Path,
    *,
    apply_changes: bool = False,
    minimum_bytes: int = 64 * 1024,
    limit: int | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    connection = _connect(database, read_only=not apply_changes)
    try:
        if apply_changes:
            connection.execute(PROGRESS_SCHEMA)
            connection.commit()
            done = {
                str(row["run_id"])
                for row in connection.execute(
                    "SELECT run_id FROM evidence_backfill_progress WHERE state = ?",
                    (STATE_MIGRATED,),
                )
            }
        else:
            done = set()

        summary: dict[str, Any] = {
            "database": database.as_posix(),
            "apply_changes": apply_changes,
            "artifact_root": artifact_root.as_posix() if artifact_root else "",
            "resumed_from": len(done),
            "examined": 0,
            "states": {},
            "original_bytes": 0,
            "compact_bytes": 0,
            "artifact_bytes": 0,
            "failures": [],
        }
        for row in list(iter_candidates(connection, minimum_bytes=minimum_bytes)):
            if str(row["run_id"]) in done:
                continue
            if limit is not None and summary["examined"] >= limit:
                break
            outcome = backfill_run(
                connection,
                row,
                apply_changes=apply_changes,
                artifact_root=artifact_root,
            )
            summary["examined"] += 1
            state = outcome["state"]
            summary["states"][state] = summary["states"].get(state, 0) + 1
            if state == STATE_MIGRATED:
                summary["original_bytes"] += outcome["original_bytes"]
                summary["compact_bytes"] += outcome["compact_bytes"]
                summary["artifact_bytes"] += outcome["artifact_bytes"]
            if state == STATE_FAILED:
                summary["failures"].append(
                    {"run_id": outcome["run_id"], "detail": outcome["detail"]}
                )
        summary["reclaimed_bytes"] = (
            summary["original_bytes"] - summary["compact_bytes"]
        )
        return summary
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite rows. Without this the database is opened read-only.",
    )
    parser.add_argument("--minimum-bytes", type=int, default=64 * 1024)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Write evidence artifacts under this directory instead of each "
        "run's own directory. Use for isolated rehearsal against a copied "
        "database so live run directories are not modified.",
    )
    args = parser.parse_args(argv)

    summary = run_backfill(
        args.database,
        apply_changes=args.apply,
        minimum_bytes=args.minimum_bytes,
        limit=args.limit,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary["failures"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
