"""Read-only aggregate evidence for the managed patch-repair lifecycle.

Gate 7 deliberately derives bounded telemetry from managed patch manifests
instead of introducing another durable counter store. The summary never reads
payload/chunk/repair files, never returns patch IDs or source bodies, and never
changes resolution/apply authority.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Final

from . import repo_writer as rw


PATCH_EVIDENCE_SUMMARY_SCHEMA_VERSION: Final[str] = "repo_patch_evidence_summary.v1"
MAX_EVIDENCE_MANIFEST_BYTES: Final[int] = 2 * 1024 * 1024
DEFAULT_EVIDENCE_MANIFEST_SCAN: Final[int] = 512
MAX_EVIDENCE_MANIFEST_SCAN: Final[int] = 4096

_ELAPSED_BUCKETS: Final[tuple[tuple[str, float], ...]] = (
    ("lt_1_ms", 1.0),
    ("1_to_lt_5_ms", 5.0),
    ("5_to_lt_25_ms", 25.0),
    ("25_to_lt_100_ms", 100.0),
)
_SIZE_BUCKETS: Final[tuple[tuple[str, int], ...]] = (
    ("lt_1_kib", 1 * 1024),
    ("1_to_lt_16_kib", 16 * 1024),
    ("16_to_lt_64_kib", 64 * 1024),
    ("64_to_lt_256_kib", 256 * 1024),
    ("256_to_lt_512_kib", 512 * 1024),
)


def _empty_elapsed_buckets() -> dict[str, int]:
    return {
        "lt_1_ms": 0,
        "1_to_lt_5_ms": 0,
        "5_to_lt_25_ms": 0,
        "25_to_lt_100_ms": 0,
        "gte_100_ms": 0,
        "invalid_or_missing": 0,
    }


def _empty_size_buckets() -> dict[str, int]:
    return {
        "lt_1_kib": 0,
        "1_to_lt_16_kib": 0,
        "16_to_lt_64_kib": 0,
        "64_to_lt_256_kib": 0,
        "256_to_lt_512_kib": 0,
        "gte_512_kib": 0,
        "invalid_or_missing": 0,
    }


def _bucket_elapsed(value: object, buckets: dict[str, int]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        buckets["invalid_or_missing"] += 1
        return
    elapsed = float(value)
    if not math.isfinite(elapsed) or elapsed < 0:
        buckets["invalid_or_missing"] += 1
        return
    for name, upper in _ELAPSED_BUCKETS:
        if elapsed < upper:
            buckets[name] += 1
            return
    buckets["gte_100_ms"] += 1


def _bucket_size(value: object, buckets: dict[str, int]) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        buckets["invalid_or_missing"] += 1
        return
    for name, upper in _SIZE_BUCKETS:
        if value < upper:
            buckets[name] += 1
            return
    buckets["gte_512_kib"] += 1


def _read_manifest(manifest_path: Path) -> dict[str, Any] | None:
    if (
        not manifest_path.exists()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
    ):
        return None
    try:
        size = manifest_path.stat().st_size
    except OSError:
        return None
    if size < 0 or size > MAX_EVIDENCE_MANIFEST_BYTES:
        return None
    try:
        raw = manifest_path.read_bytes()
        decoded = raw.decode("utf-8", errors="strict")
        value = json.loads(decoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def summarize_patch_evidence(
    repo_root: Path,
    runs_dir: Path,
    *,
    max_manifests: int = DEFAULT_EVIDENCE_MANIFEST_SCAN,
) -> dict[str, Any]:
    """Derive aggregate patch evidence without opening managed payload bodies.

    Only source-role manifests contribute candidate-validation, repair-proposal,
    and decision counts. Resolution child manifests intentionally do not, which
    prevents durable source evidence from being counted twice.

    ``currently_unresolved_resolution_required_sources`` is a mechanical state
    count. It must not be interpreted as proof that a controller intentionally
    abandoned those previews.
    """

    if (
        not isinstance(max_manifests, int)
        or isinstance(max_manifests, bool)
        or max_manifests < 1
        or max_manifests > MAX_EVIDENCE_MANIFEST_SCAN
    ):
        raise ValueError(
            f"max_manifests must be between 1 and {MAX_EVIDENCE_MANIFEST_SCAN}"
        )

    repo_fingerprint = rw._repo_fingerprint(repo_root)
    managed_root = runs_dir / rw.MANAGED_PATCHES_DIR

    validation_dispositions: Counter[str] = Counter()
    validation_languages: Counter[str] = Counter()
    proposal_rules: Counter[str] = Counter()
    resolution_decisions: Counter[str] = Counter()
    elapsed_buckets = _empty_elapsed_buckets()
    size_buckets = _empty_size_buckets()

    patches_examined = 0
    source_manifests = 0
    child_manifests_ignored = 0
    foreign_or_unbound_manifests_skipped = 0
    manifest_read_errors = 0
    malformed_validation_records = 0
    candidate_validations_attempted = 0
    currently_unresolved = 0
    accept_original_after_repair_review_signals = 0

    matching_patch_directories_discovered = 0
    scan_truncated = False
    if managed_root.exists():
        if managed_root.is_symlink() or not managed_root.is_dir():
            raise ValueError("managed patch evidence root must be a regular directory")
        patch_dirs = sorted(
            (
                item
                for item in managed_root.iterdir()
                if rw._PATCH_ID_RE.fullmatch(item.name)
            ),
            key=lambda item: item.name,
            reverse=True,
        )
        matching_patch_directories_discovered = len(patch_dirs)
        scan_truncated = len(patch_dirs) > max_manifests
        for patch_dir in patch_dirs[:max_manifests]:
            if patch_dir.is_symlink() or not patch_dir.is_dir():
                manifest_read_errors += 1
                continue
            patches_examined += 1
            manifest = _read_manifest(patch_dir / "manifest.json")
            if manifest is None or manifest.get("patch_id") != patch_dir.name:
                manifest_read_errors += 1
                continue
            if manifest.get("repo_fingerprint") != repo_fingerprint:
                foreign_or_unbound_manifests_skipped += 1
                continue

            if str(manifest.get("resolution_role", "source")) == "child":
                child_manifests_ignored += 1
                continue
            source_manifests += 1

            if manifest.get("status") == "preview_resolution_required":
                currently_unresolved += 1

            operations = manifest.get("operations")
            if isinstance(operations, list):
                for operation in operations:
                    if not isinstance(operation, dict):
                        continue
                    validation = operation.get("candidate_validation")
                    if validation is None:
                        continue
                    if not isinstance(validation, dict):
                        malformed_validation_records += 1
                        continue
                    disposition = validation.get("candidate_disposition")
                    language = validation.get("language")
                    if not isinstance(disposition, str) or not disposition:
                        malformed_validation_records += 1
                        continue
                    candidate_validations_attempted += 1
                    validation_dispositions[disposition] += 1
                    if isinstance(language, str) and language:
                        validation_languages[language] += 1
                    else:
                        validation_languages["unknown"] += 1
                    _bucket_elapsed(validation.get("elapsed_ms"), elapsed_buckets)
                    _bucket_size(
                        validation.get("candidate_size_bytes"),
                        size_buckets,
                    )

            repair_proposal = manifest.get("repair_proposal")
            repair_available = isinstance(repair_proposal, dict)
            if repair_available:
                rule_id = repair_proposal.get("rule_id")
                proposal_rules[
                    rule_id if isinstance(rule_id, str) and rule_id else "unknown"
                ] += 1

            resolution = manifest.get("resolution")
            if isinstance(resolution, dict):
                decision = resolution.get("decision")
                if decision in {"accept_repair", "accept_original"}:
                    resolution_decisions[str(decision)] += 1
                    if decision == "accept_original" and repair_available:
                        accept_original_after_repair_review_signals += 1

    return {
        "schema_version": PATCH_EVIDENCE_SUMMARY_SCHEMA_VERSION,
        "source": "managed_patch_manifests",
        "scan_order": "newest_patch_id_first",
        "manifest_scan_limit": max_manifests,
        "matching_patch_directories_discovered": matching_patch_directories_discovered,
        "scan_truncated": scan_truncated,
        "patches_examined": patches_examined,
        "source_manifests": source_manifests,
        "child_manifests_ignored": child_manifests_ignored,
        "foreign_or_unbound_manifests_skipped": foreign_or_unbound_manifests_skipped,
        "manifest_read_errors": manifest_read_errors,
        "candidate_validations_attempted": candidate_validations_attempted,
        "candidate_validation_dispositions": dict(
            sorted(validation_dispositions.items())
        ),
        "candidate_validation_languages": dict(sorted(validation_languages.items())),
        "repair_proposals_by_rule_id": dict(sorted(proposal_rules.items())),
        "resolution_decisions": {
            "accept_repair": resolution_decisions.get("accept_repair", 0),
            "accept_original": resolution_decisions.get("accept_original", 0),
        },
        "accept_original_after_repair_proposal_review_signals": (
            accept_original_after_repair_review_signals
        ),
        "currently_unresolved_resolution_required_sources": currently_unresolved,
        "validation_elapsed_ms_buckets": elapsed_buckets,
        "candidate_size_bytes_buckets": size_buckets,
        "malformed_validation_records": malformed_validation_records,
        "unavailable_metrics": {
            "resolution_conflicts_or_stale_failures": (
                "not_available_from_managed_patch_manifests"
            ),
            "intentional_abandonment": "not_inferred_from_unresolved_state",
        },
        "privacy": {
            "payload_files_read": False,
            "patch_ids_emitted": False,
            "source_bodies_emitted": False,
        },
        "authority": {
            "writes_state": False,
            "silent_auto_resolution_authorized": False,
        },
    }
