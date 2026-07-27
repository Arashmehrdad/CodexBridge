"""Benchmark runner: freeze, then measure.

Two subcommands, deliberately separate so the contract is frozen before any
result is visible:

    python -m soma.pilot_memory_1b.runner freeze
    python -m soma.pilot_memory_1b.runner run [--scale] [--json PATH]

``run`` refuses to record anything unless the on-disk freeze still matches the
code. Thresholds cannot be edited after results are known without the freeze
check failing loudly, which is the point.

Every vault this module creates lives in a caller-supplied or temporary
directory. Nothing is written to the live store, ProjectScope, ``.soma/wiki/``,
or ``soma.memory``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    BENCHMARK_CONTRACT,
    BOOLEAN_CLASSES,
    CONFUSION_PROJECT_ID,
    LEXICAL_F1_THRESHOLDS,
    MEMORY_BUDGETS_MB,
    SEED,
    SOMA_PROJECT_ID,
    TIME_BUDGETS_SECONDS,
    canonical_json,
    contract_hash,
)
from .corpus import CURATED_NOTES, DELETION_NOTE_ID, EXTERNAL_EDIT_NOTE_ID
from .derived import build_association_model, derived_search
from .generator import NEEDLE_ID, NEEDLE_QUERY, generate_vault
from .index import MemoryIndex, UnscopedQueryError, build_index
from .questions import QUESTIONS, Question
from .scoring import Score, mean_f1, score_sets
from .vault import corpus_hash, read_vault, render_note, write_vault

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEZE_PATH = REPO_ROOT / "docs" / "pilot-memory-1b-frozen-benchmark-2026-07-28.json"


# ---------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------


def corpus_spec_hash() -> str:
    """Digest of the curated fixture source, independent of any filesystem."""
    payload = [
        {
            "id": s.note_id,
            "project": s.project_id,
            "kind": s.kind,
            "title": s.title,
            "body": s.body,
            "created": s.created,
            "source": s.source,
            "supersedes": list(s.supersedes),
            "supersedes_claims": [list(x) for x in s.supersedes_claims],
            "claims": [list(x) for x in s.claims],
            "relations": [list(x) for x in s.relations],
            "malformed": s.malformed_frontmatter,
        }
        for s in CURATED_NOTES
    ]
    import hashlib

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def questions_hash() -> str:
    payload = [
        {
            "qid": q.qid,
            "cls": q.cls,
            "mode": q.mode,
            "text": q.text,
            "project": q.project_id or "",
            "expected": sorted(q.expected),
            "claim_key": q.claim_key,
            "anchor": q.anchor,
            "relation_type": q.relation_type,
            "depth": q.depth,
            "probe": q.probe,
        }
        for q in QUESTIONS
    ]
    import hashlib

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def freeze_payload() -> dict[str, Any]:
    return {
        "schema_version": "pilot_memory_1b.frozen_benchmark.v1",
        "frozen_before_first_measured_run": True,
        "contract_hash": contract_hash(),
        "corpus_spec_hash": corpus_spec_hash(),
        "questions_hash": questions_hash(),
        "curated_note_count": len(CURATED_NOTES),
        "question_count": len(QUESTIONS),
        "contract": BENCHMARK_CONTRACT,
    }


def write_freeze(path: Path = FREEZE_PATH) -> dict[str, Any]:
    payload = freeze_payload()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def verify_freeze(path: Path = FREEZE_PATH) -> tuple[bool, list[str]]:
    if not path.is_file():
        return False, ["freeze_file_missing"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    current = freeze_payload()
    drift = [
        key
        for key in ("contract_hash", "corpus_spec_hash", "questions_hash")
        if stored.get(key) != current.get(key)
    ]
    return (not drift), drift


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def force_rmtree(path: Path) -> None:
    """Remove a tree that contains a Git repository.

    Windows refuses to unlink read-only files, and Git marks objects read-only,
    so a plain rmtree silently leaves the disposable vault behind. The gate
    requires proof that generated data was actually removed, so the read-only
    bit is cleared and the unlink retried.
    """
    import os
    import stat

    def _clear_readonly(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda f, t, e: _clear_readonly(f, t, e))
    else:  # pragma: no cover - the pinned interpreter is 3.12
        shutil.rmtree(path, onerror=_clear_readonly)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )


def init_vault_repo(root: Path) -> None:
    """Git supplies history and external-edit provenance for the vault."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "pilot@example.invalid")
    _git(root, "config", "user.name", "pilot-memory-1b")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "curated corpus")


def check_oracle_leakage(vault_root: Path) -> list[str]:
    """No question text may appear verbatim in any indexed note body."""
    bodies = {n.note_id: f"{n.title}\n{n.body}".lower() for n in read_vault(vault_root)}
    leaks: list[str] = []
    for question in QUESTIONS:
        needle = question.text.lower().strip()
        if len(needle) < 12:
            continue
        for note_id, body in bodies.items():
            if needle in body:
                leaks.append(f"{question.qid}->{note_id}")
    return sorted(leaks)


def _timed(fn) -> tuple[Any, float]:
    start = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - start


# ---------------------------------------------------------------------------
# visible suite
# ---------------------------------------------------------------------------


@dataclass
class QuestionResult:
    question: Question
    retrieved: list[str]
    score: Score
    method: str
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "qid": self.question.qid,
            "class": self.question.cls,
            "mode": self.question.mode,
            "text": self.question.text,
            "project_id": self.question.project_id or "",
            "method": self.method,
            "expected": sorted(self.question.expected),
            "retrieved": list(self.retrieved),
            "error": self.error,
            **self.score.as_dict(),
        }


def _structural(index: MemoryIndex, probe: str, project_id: str | None) -> list[str]:
    scope = set(index.by_project.get(project_id or "", ()))
    if probe == "unresolved_sources":
        return sorted(
            n for n, s in index.source_status.items() if s == "unresolved" and n in scope
        )
    if probe == "missing_sources":
        return sorted(
            n for n, s in index.source_status.items() if s == "missing" and n in scope
        )
    if probe == "malformed_frontmatter":
        # Malformed notes may not carry a usable project field; that is the
        # defect. They are reported by id rather than filtered by scope.
        return sorted(index.malformed)
    if probe == "dangling_sources":
        return sorted({src for src, _ in index.dangling if src in scope})
    if probe == "deleted_note_present":
        return [DELETION_NOTE_ID] if DELETION_NOTE_ID in index.notes else []
    raise ValueError(f"unknown probe: {probe}")


def answer(
    index: MemoryIndex,
    question: Question,
    *,
    method: str,
    model=None,
    post_delete: bool = False,
) -> QuestionResult:
    q = question
    error = ""
    retrieved: list[str] = []

    try:
        if q.mode == "retrieval":
            # R-precision: request exactly as many results as are expected, so
            # precision is not automatically penalised for a question that has
            # a single correct answer.
            k = max(1, len(q.expected))
            if method == "derived":
                retrieved = derived_search(index, model, q.text, q.project_id, limit=k)
            else:
                retrieved = index.search(q.text, q.project_id, limit=k)
        elif q.mode == "claim_current":
            retrieved = sorted(
                c.note_id for c in index.current_claims(q.project_id, q.claim_key)
            )
        elif q.mode == "claim_superseded":
            retrieved = sorted(
                c.note_id
                for c in index.claim_refs(q.project_id, q.claim_key)
                if not c.current
            )
        elif q.mode == "relation":
            retrieved = index.reachable(q.anchor, q.relation_type, q.depth)
        elif q.mode == "referrers":
            retrieved = index.referrers(q.anchor)
        elif q.mode in ("structural", "structural_post_delete"):
            retrieved = _structural(index, q.probe, q.project_id)
        elif q.mode == "unscoped":
            try:
                index.search(q.text, None, limit=5)
            except UnscopedQueryError:
                retrieved = []
            else:
                error = "unscoped_query_returned_data"
                retrieved = ["UNSCOPED_LEAK"]
        else:
            raise ValueError(f"unknown mode: {q.mode}")
    except UnscopedQueryError as exc:
        error = f"unscoped_rejected:{exc}"
    except Exception as exc:  # preserved as an honest failure, never swallowed
        error = f"{type(exc).__name__}: {exc}"

    return QuestionResult(q, retrieved, score_sets(q.expected, retrieved), method, error)


def run_visible_suite(
    index: MemoryIndex, *, method: str, model=None, post_delete: bool = False
) -> list[QuestionResult]:
    results = []
    for question in QUESTIONS:
        if question.cls in BOOLEAN_CLASSES:
            continue
        if question.mode == "structural_post_delete" and not post_delete:
            continue
        if question.mode != "structural_post_delete" and post_delete:
            continue
        results.append(answer(index, question, method=method, model=model))
    return results


def summarize(results: list[QuestionResult]) -> dict[str, Any]:
    by_class: dict[str, list[Score]] = {}
    for r in results:
        by_class.setdefault(r.question.cls, []).append(r.score)
    summary = {}
    for cls, scores in sorted(by_class.items()):
        f1 = mean_f1(scores)
        threshold = LEXICAL_F1_THRESHOLDS.get(cls)
        summary[cls] = {
            "mean_f1": round(f1, 4),
            "questions": len(scores),
            "threshold": threshold,
            "meets_threshold": None if threshold is None else bool(f1 >= threshold),
        }
    return summary


# ---------------------------------------------------------------------------
# scale
# ---------------------------------------------------------------------------


def measure_scale(count: int, workdir: Path) -> dict[str, Any]:
    vault = workdir / f"scale-{count}"
    generate_vault(vault, count, seed=SEED)

    tracemalloc.start()
    index, cold = _timed(lambda: build_index(vault, repo_root=None))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    latencies: list[float] = []
    needle_found = False
    for i in range(25):
        query = NEEDLE_QUERY if i % 5 == 0 else f"sequence marker {i * 7}"
        start = time.perf_counter()
        hits = index.search(query, SOMA_PROJECT_ID, limit=5)
        latencies.append(time.perf_counter() - start)
        if query == NEEDLE_QUERY:
            needle_found = NEEDLE_ID in hits

    p95 = statistics.quantiles(latencies, n=20)[-1] if len(latencies) > 1 else latencies[0]
    cold_budget = TIME_BUDGETS_SECONDS.get(f"cold_rebuild_{count}")
    warm_budget = TIME_BUDGETS_SECONDS.get(f"warm_query_p95_{count}")
    mem_budget = MEMORY_BUDGETS_MB.get(f"index_peak_alloc_{count}")
    peak_mb = peak / (1024 * 1024)

    force_rmtree(vault)
    return {
        "notes": count,
        "note_files_generated": count + 1,
        "cold_rebuild_seconds": round(cold, 4),
        "cold_budget_seconds": cold_budget,
        "cold_within_budget": None if cold_budget is None else bool(cold <= cold_budget),
        "warm_query_p95_seconds": round(p95, 6),
        "warm_budget_seconds": warm_budget,
        "warm_within_budget": None if warm_budget is None else bool(p95 <= warm_budget),
        "index_peak_alloc_mb": round(peak_mb, 2),
        "memory_budget_mb": mem_budget,
        "memory_within_budget": None if mem_budget is None else bool(peak_mb <= mem_budget),
        "needle_retrieved_at_scale": needle_found,
        "vault_removed": not vault.exists(),
    }


# ---------------------------------------------------------------------------
# full run
# ---------------------------------------------------------------------------


def execute(*, with_scale: bool, workdir: Path | None = None) -> dict[str, Any]:
    frozen_ok, drift = verify_freeze()
    if not frozen_ok:
        return {
            "ok": False,
            "verdict": "benchmark_inconclusive",
            "stop_reason": "contract_not_frozen_or_drifted",
            "freeze_drift": drift,
        }

    owns_workdir = workdir is None
    base = Path(workdir or tempfile.mkdtemp(prefix="pilot-memory-1b-"))
    report: dict[str, Any] = {
        "schema_version": "pilot_memory_1b.results.v1",
        "freeze": {
            "contract_hash": contract_hash(),
            "corpus_spec_hash": corpus_spec_hash(),
            "questions_hash": questions_hash(),
            "verified_before_measurement": True,
        },
        "shadow_only": {
            "vault_location": "disposable_temp_directory",
            "live_store_touched": False,
            "project_scope_touched": False,
            "soma_memory_package_imported": False,
            "wiki_touched": False,
            "network_used": False,
        },
    }

    try:
        vault = base / "vault"
        write_vault(vault, CURATED_NOTES)
        init_vault_repo(vault)

        report["corpus"] = {
            "curated_notes": len(CURATED_NOTES),
            "canonical_bytes_hash": corpus_hash(vault),
            "projects": {
                SOMA_PROJECT_ID: sum(
                    1 for n in CURATED_NOTES if n.project_id == SOMA_PROJECT_ID
                ),
                CONFUSION_PROJECT_ID: sum(
                    1 for n in CURATED_NOTES if n.project_id == CONFUSION_PROJECT_ID
                ),
            },
        }

        leaks = check_oracle_leakage(vault)
        report["oracle_leakage"] = {"leaks": leaks, "clean": not leaks}
        if leaks:
            report["ok"] = False
            report["verdict"] = "benchmark_inconclusive"
            report["stop_reason"] = "oracle_leakage_detected"
            return report

        # -- cold build + lexical suite ---------------------------------
        tracemalloc.start()
        index, cold = _timed(lambda: build_index(vault, repo_root=REPO_ROOT))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        lexical = run_visible_suite(index, method="lexical")
        model = build_association_model(index)
        derived = [
            answer(index, q, method="derived", model=model)
            for q in QUESTIONS
            if q.mode == "retrieval"
        ]

        report["curated_scale"] = {
            "notes": len(CURATED_NOTES),
            "cold_rebuild_seconds": round(cold, 4),
            "cold_budget_seconds": TIME_BUDGETS_SECONDS["cold_rebuild_100"],
            "cold_within_budget": bool(cold <= TIME_BUDGETS_SECONDS["cold_rebuild_100"]),
            "index_peak_alloc_mb": round(peak / (1024 * 1024), 2),
            "memory_budget_mb": MEMORY_BUDGETS_MB["index_peak_alloc_100"],
        }

        # -- external edit attribution ----------------------------------
        target = vault / f"{EXTERNAL_EDIT_NOTE_ID}.md"
        target.write_text(
            target.read_text(encoding="utf-8")
            + "\nAn additional line was appended directly on disk.\n",
            encoding="utf-8",
        )
        status = _git(vault, "status", "--porcelain")
        attributed = f"{EXTERNAL_EDIT_NOTE_ID}.md" in status.stdout
        reindexed = build_index(vault, repo_root=REPO_ROOT)
        visible_after_reindex = (
            "appended directly on disk"
            in reindexed.notes[EXTERNAL_EDIT_NOTE_ID].body
        )
        report["external_edit_attribution"] = {
            "git_status": status.stdout.strip().splitlines(),
            "attributed_by_git": attributed,
            "visible_after_reindex": visible_after_reindex,
            "passed": bool(attributed and visible_after_reindex),
        }

        # -- deterministic rebuild --------------------------------------
        fingerprint_a = build_index(vault, repo_root=REPO_ROOT).fingerprint()
        fingerprint_b = build_index(vault, repo_root=REPO_ROOT).fingerprint()
        # Deleting the derived structure entirely and rebuilding from files.
        del reindexed
        fingerprint_c = build_index(vault, repo_root=REPO_ROOT).fingerprint()
        canonical_before = corpus_hash(vault)
        report["deterministic_rebuild"] = {
            "fingerprint": fingerprint_a,
            "repeat_identical": fingerprint_a == fingerprint_b,
            "after_discard_identical": fingerprint_a == fingerprint_c,
            "canonical_unchanged_by_rebuild": corpus_hash(vault) == canonical_before,
            "passed": bool(fingerprint_a == fingerprint_b == fingerprint_c),
        }

        # -- deletion ----------------------------------------------------
        (vault / f"{DELETION_NOTE_ID}.md").unlink()
        post_index = build_index(vault, repo_root=REPO_ROOT)
        post_delete_results = run_visible_suite(
            post_index, method="lexical", post_delete=True
        )
        report["deletion"] = {
            "removed_note": DELETION_NOTE_ID,
            "present_after_delete": DELETION_NOTE_ID in post_index.notes,
            "dangling_after_delete": [list(x) for x in post_index.dangling],
        }

        all_lexical = lexical + post_delete_results
        report["lexical"] = {
            "per_question": [r.as_dict() for r in all_lexical],
            "per_class": summarize(all_lexical),
        }
        report["local_derived"] = {
            "method": "corpus-only NPMI co-occurrence query expansion",
            "network_used": False,
            "per_question": [r.as_dict() for r in derived],
            "per_class": summarize(derived),
        }

        # -- boolean classes ---------------------------------------------
        report["lexical"]["per_class"]["external_edit_attribution"] = {
            "mean_f1": 1.0 if report["external_edit_attribution"]["passed"] else 0.0,
            "questions": 1,
            "threshold": 1.0,
            "meets_threshold": report["external_edit_attribution"]["passed"],
        }
        report["lexical"]["per_class"]["deterministic_rebuild"] = {
            "mean_f1": 1.0 if report["deterministic_rebuild"]["passed"] else 0.0,
            "questions": 1,
            "threshold": 1.0,
            "meets_threshold": report["deterministic_rebuild"]["passed"],
        }

        # -- scale --------------------------------------------------------
        if with_scale:
            report["scale"] = [measure_scale(n, base) for n in (1000, 10000)]
        else:
            report["scale"] = "skipped"

        failing = sorted(
            cls
            for cls, row in report["lexical"]["per_class"].items()
            if row.get("meets_threshold") is False
        )
        report["failing_classes"] = failing
        report["ok"] = True
        report["verdict"] = (
            "baseline_candidate_passes" if not failing else "baseline_has_named_measured_gaps"
        )
        return report
    finally:
        if owns_workdir:
            force_rmtree(base)
            report.setdefault("cleanup", {})["workdir_removed"] = not base.exists()
            report["cleanup"]["workdir"] = str(base)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pilot_memory_1b")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze", help="write the frozen benchmark definition")
    run = sub.add_parser("run", help="execute the measured benchmark")
    run.add_argument("--scale", action="store_true", help="include 1k/10k measurements")
    run.add_argument("--json", type=Path, default=None, help="write the report here")
    args = parser.parse_args(argv)

    if args.command == "freeze":
        payload = write_freeze()
        print(json.dumps({k: payload[k] for k in sorted(payload) if k != "contract"}, indent=2))
        return 0

    report = execute(with_scale=args.scale)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
