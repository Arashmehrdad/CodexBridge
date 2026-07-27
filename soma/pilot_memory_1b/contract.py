"""Frozen benchmark contract.

Everything the gate requires to be fixed *before the first measured run* lives
here: the seed, the exact project identities, scoring rules, operational time
budgets, and failure thresholds. The runner refuses to record a measured result
unless the on-disk freeze file still matches this module.

Thresholds are deliberately declared without knowing the outcome. Some are
expected to fail. A failing threshold is the product of this lane, not a defect
to be tuned away afterwards.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

CONTRACT_VERSION: Final[str] = "pilot_memory_1b.contract.v1"

#: Exact opaque project identities. Never inferred from folder names, note
#: paths, repository names, or human-readable project labels.
SOMA_PROJECT_ID: Final[str] = "proj_a144f759-1619-4276-9292-28704b6611f4"
CONFUSION_PROJECT_ID: Final[str] = "proj_0cf013d0-191b-57f4-a84b-7a43819a1578"

#: Single deterministic seed for every generated artifact in this lane.
SEED: Final[int] = 20260727

QUESTION_CLASSES: Final[tuple[str, ...]] = (
    "exact_recall",
    "multi_hop_full_supersession",
    "partial_claim_supersession",
    "contradiction_and_current_fact_precision",
    "semantic_paraphrase",
    "one_and_multi_hop_relations",
    "source_and_frontmatter_drift",
    "external_edit_attribution",
    "deletion_and_dangling_links",
    "deterministic_rebuild",
    "project_isolation_and_unscoped_rejection",
    "scale_and_resource_measurement",
)

#: Per-class minimum F1 for the lexical baseline. Predeclared blind.
#: semantic_paraphrase is set at 0.60 because a purely lexical index has no
#: principled way to bridge vocabulary it never sees; if the baseline clears it
#: anyway the questions were too easy, and that is also a reportable finding.
LEXICAL_F1_THRESHOLDS: Final[dict[str, float]] = {
    "exact_recall": 0.95,
    "multi_hop_full_supersession": 0.90,
    "partial_claim_supersession": 0.90,
    "contradiction_and_current_fact_precision": 0.90,
    "semantic_paraphrase": 0.60,
    "one_and_multi_hop_relations": 0.85,
    "source_and_frontmatter_drift": 0.95,
    "deletion_and_dangling_links": 0.95,
    "project_isolation_and_unscoped_rejection": 1.00,
}

#: Classes evaluated as a strict boolean rather than by retrieval overlap.
BOOLEAN_CLASSES: Final[tuple[str, ...]] = (
    "external_edit_attribution",
    "deterministic_rebuild",
)

#: Operational budgets, declared before measurement. Wall-clock seconds.
TIME_BUDGETS_SECONDS: Final[dict[str, float]] = {
    "cold_rebuild_100": 2.0,
    "cold_rebuild_1000": 15.0,
    "cold_rebuild_10000": 150.0,
    "warm_query_p95_100": 0.05,
    "warm_query_p95_1000": 0.25,
    "warm_query_p95_10000": 2.50,
}

#: Peak Python allocation during index construction, megabytes, measured with
#: tracemalloc. Deliberately not RSS: RSS is dominated by interpreter and
#: allocator behaviour and would not be reproducible across hosts.
MEMORY_BUDGETS_MB: Final[dict[str, float]] = {
    "index_peak_alloc_100": 25.0,
    "index_peak_alloc_1000": 250.0,
    "index_peak_alloc_10000": 1500.0,
}

SCORING_RULES: Final[dict[str, Any]] = {
    "retrieval_metric": "set_f1_over_expected_note_ids",
    # R-precision: ask for exactly as many results as the question expects.
    # The first frozen revision used a fixed cutoff of 5, which capped F1 at
    # 0.333 for any single-answer question and so sat below its own 0.95
    # threshold no matter how good retrieval was. That was an internally
    # inconsistent contract, corrected once under the gate's bounded-correction
    # allowance. No threshold was altered, and the pre-correction measurement
    # is preserved as evidence.
    "ranked_cutoff_k": "r_precision: k = max(1, len(expected))",
    "ranked_cutoff_k_first_revision": 5,
    "precision": "true_positives / retrieved",
    "recall": "true_positives / expected",
    "f1": "harmonic_mean(precision, recall); 1.0 when both expected and retrieved are empty",
    "class_score": "unweighted_mean_of_question_f1_within_class",
    "boolean_classes_scored": "all_or_nothing",
    "unscoped_query": "must_raise; a returned result is an automatic class failure",
    "oracle_leakage": "verbatim question text in any note body fails the whole run",
}

CORPUS_RULES: Final[dict[str, Any]] = {
    "curated_min": 50,
    "curated_max": 100,
    "projects": [SOMA_PROJECT_ID, CONFUSION_PROJECT_ID],
    "canonical_format": "markdown_with_yaml_frontmatter",
    "history": "git",
    "index_is_derived_and_disposable": True,
    "scale_note_counts": [1000, 10000],
    "scale_corpora_committed": False,
    "scale_corpora_location": "outside_tracked_repository_paths",
}

BENCHMARK_CONTRACT: Final[dict[str, Any]] = {
    "contract_version": CONTRACT_VERSION,
    "seed": SEED,
    "project_ids": {
        "soma": SOMA_PROJECT_ID,
        "confusion_sibling": CONFUSION_PROJECT_ID,
    },
    "identity_inference_allowed": False,
    "unscoped_retrieval_allowed": False,
    "question_classes": list(QUESTION_CLASSES),
    "boolean_classes": list(BOOLEAN_CLASSES),
    "lexical_f1_thresholds": dict(LEXICAL_F1_THRESHOLDS),
    "time_budgets_seconds": dict(TIME_BUDGETS_SECONDS),
    "memory_budgets_mb": dict(MEMORY_BUDGETS_MB),
    "scoring_rules": dict(SCORING_RULES),
    "corpus_rules": dict(CORPUS_RULES),
    "network_dependency_allowed": False,
    "local_derived_method_reported_separately": True,
}


def canonical_json(payload: Any) -> str:
    """Stable JSON encoding used for every hash in this lane."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def contract_hash() -> str:
    """SHA-256 of the frozen contract as defined by this module."""
    return hashlib.sha256(canonical_json(BENCHMARK_CONTRACT).encode("utf-8")).hexdigest()
