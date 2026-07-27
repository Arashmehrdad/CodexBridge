"""Golden question set with expected answers, frozen before measurement.

Question text is deliberately written in vocabulary the notes do not use where
the class calls for it. Nothing in this module is indexed; the runner asserts
that no question string appears verbatim in any note body before it will record
a measured result.

The paraphrase questions are not tuned to be answerable. If the lexical
baseline cannot bridge them, that is the measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from .contract import CONFUSION_PROJECT_ID, SOMA_PROJECT_ID

S = SOMA_PROJECT_ID
C = CONFUSION_PROJECT_ID


@dataclass(frozen=True)
class Question:
    qid: str
    cls: str
    mode: str
    text: str
    project_id: str | None
    expected: frozenset[str] = frozenset()
    #: Claim lookups only.
    claim_key: str = ""
    #: Relation walks only.
    anchor: str = ""
    relation_type: str = ""
    depth: int = 1
    #: Structural probes only.
    probe: str = ""
    note: str = ""


def _q(*args, **kwargs) -> Question:
    return Question(*args, **kwargs)


QUESTIONS: Final[tuple[Question, ...]] = (
    # -- exact recall ------------------------------------------------------
    _q("ex-01", "exact_recall", "retrieval",
       "loopback HTTP listener port and the MCP route path", S,
       frozenset({"soma-runtime-port"})),
    _q("ex-02", "exact_recall", "retrieval",
       "powershell executable profile pinned interpreter digest", S,
       frozenset({"soma-executable-profile"})),
    _q("ex-03", "exact_recall", "retrieval",
       "write-ahead logging journal mode for the durable store", S,
       frozenset({"soma-journal-mode"})),
    _q("ex-04", "exact_recall", "retrieval",
       "additive sidecar rather than rewriting incumbent authorities", S,
       frozenset({"soma-decision-scope-sidecar"})),
    _q("ex-05", "exact_recall", "retrieval",
       "backup interface inside a read transaction before trusting a restore point", S,
       frozenset({"soma-procedure-backup"})),

    # -- multi-hop full supersession A <- B <- C ---------------------------
    _q("ms-01", "multi_hop_full_supersession", "claim_current",
       "current on-disk size of the durable store", S,
       frozenset({"soma-store-size-v3"}), claim_key="store_size",
       note="three-note chain; only the newest survives"),
    _q("ms-02", "multi_hop_full_supersession", "claim_superseded",
       "store size values that are no longer current", S,
       frozenset({"soma-store-size-v1", "soma-store-size-v2"}),
       claim_key="store_size"),
    _q("ms-03", "multi_hop_full_supersession", "claim_current",
       "current public tunnel hostname", S,
       frozenset({"soma-tunnel-endpoint-current", "soma-tunnel-duplicate"}),
       claim_key="tunnel_host",
       note="the duplicate restates the same current value and is not superseded"),

    # -- partial claim-level supersession ----------------------------------
    _q("pc-01", "partial_claim_supersession", "claim_current",
       "current worker lease duration", S,
       frozenset({"soma-worker-profile-v2"}), claim_key="lease_seconds"),
    _q("pc-02", "partial_claim_supersession", "claim_current",
       "current worker retry limit", S,
       frozenset({"soma-worker-profile-v1"}), claim_key="retry_limit",
       note="the amending note replaced only the lease; this claim stays current"),
    _q("pc-03", "partial_claim_supersession", "claim_superseded",
       "worker lease values that were replaced", S,
       frozenset({"soma-worker-profile-v1"}), claim_key="lease_seconds"),

    # -- contradiction and current-fact precision --------------------------
    _q("cf-01", "contradiction_and_current_fact_precision", "claim_current",
       "current default executable profile", S,
       frozenset({"soma-executable-profile"}), claim_key="default_profile"),
    _q("cf-02", "contradiction_and_current_fact_precision", "claim_superseded",
       "retired tunnel hostname", S,
       frozenset({"soma-tunnel-endpoint-old"}), claim_key="tunnel_host"),
    _q("cf-03", "contradiction_and_current_fact_precision", "claim_current",
       "current mismatch behaviour", S,
       frozenset({"soma-decision-fail-closed"}), claim_key="mismatch_behaviour"),

    # -- semantic paraphrase -----------------------------------------------
    _q("sp-01", "semantic_paraphrase", "retrieval",
       "how many jobs may execute at the same moment before the machine is overloaded",
       S, frozenset({"soma-paraphrase-throttle"})),
    _q("sp-02", "semantic_paraphrase", "retrieval",
       "are saved logs immutable once a job finishes", S,
       frozenset({"soma-paraphrase-evidence"})),
    _q("sp-03", "semantic_paraphrase", "retrieval",
       "why is hiding skipped items from a reviewer dangerous", S,
       frozenset({"soma-paraphrase-quiet-failure"})),
    _q("sp-04", "semantic_paraphrase", "retrieval",
       "which socket number does the service accept connections on", S,
       frozenset({"soma-runtime-port"})),
    _q("sp-05", "semantic_paraphrase", "retrieval",
       "can a query stall the process that is saving data", S,
       frozenset({"soma-journal-mode"})),
    _q("sp-06", "semantic_paraphrase", "retrieval",
       "what occurs when a caller names the wrong owner on a request", S,
       frozenset({"soma-decision-fail-closed"})),

    # -- one-hop and multi-hop relations -----------------------------------
    _q("rl-01", "one_and_multi_hop_relations", "relation",
       "what does the cutover gate directly depend on", S,
       frozenset({"soma-relation-gate-b"}),
       anchor="soma-relation-gate-c", relation_type="depends_on", depth=1),
    _q("rl-02", "one_and_multi_hop_relations", "relation",
       "every gate the cutover transitively depends on", S,
       frozenset({"soma-relation-gate-a", "soma-relation-gate-b"}),
       anchor="soma-relation-gate-c", relation_type="depends_on", depth=3),
    _q("rl-03", "one_and_multi_hop_relations", "relation",
       "which record the activation procedure depends on", S,
       frozenset({"soma-procedure-backup"}),
       anchor="soma-procedure-activation", relation_type="depends_on", depth=1),
    _q("rl-04", "one_and_multi_hop_relations", "referrers",
       "which records point at the removal target", S,
       frozenset({"soma-deletion-referrer"}), anchor="soma-deletion-target"),

    # -- source and frontmatter drift --------------------------------------
    _q("dr-01", "source_and_frontmatter_drift", "structural",
       "records whose source no longer resolves", S,
       frozenset({"soma-drift-moved-source", "soma-drift-deleted-source"}),
       probe="unresolved_sources"),
    _q("dr-02", "source_and_frontmatter_drift", "structural",
       "records carrying no source at all", S,
       frozenset({"soma-drift-empty-source"}), probe="missing_sources"),
    _q("dr-03", "source_and_frontmatter_drift", "structural",
       "records whose metadata block does not parse", S,
       frozenset({"soma-drift-malformed"}), probe="malformed_frontmatter"),

    # -- deletion and dangling links ---------------------------------------
    _q("dl-01", "deletion_and_dangling_links", "structural",
       "references that point at an absent target before any deletion", S,
       frozenset({"soma-dangling-reference"}), probe="dangling_sources"),
    _q("dl-02", "deletion_and_dangling_links", "structural_post_delete",
       "references left dangling after the removal", S,
       frozenset({"soma-dangling-reference", "soma-deletion-referrer"}),
       probe="dangling_sources"),
    _q("dl-03", "deletion_and_dangling_links", "structural_post_delete",
       "the removed record is absent from the rebuilt index", S,
       frozenset(), probe="deleted_note_present"),

    # -- project isolation and unscoped rejection --------------------------
    # The same query text is asked of both projects on purpose: identical
    # wording against near-identical corpora is what makes leakage detectable.
    # The wording avoids reusing a note title verbatim so that the query
    # carries no oracle, only shared vocabulary.
    _q("pi-01", "project_isolation_and_unscoped_rejection", "retrieval",
       "which port number is bound for incoming connections", S,
       frozenset({"soma-runtime-port"})),
    _q("pi-02", "project_isolation_and_unscoped_rejection", "retrieval",
       "which port number is bound for incoming connections", C,
       frozenset({"lab-runtime-port"})),
    _q("pi-03", "project_isolation_and_unscoped_rejection", "retrieval",
       "how long is a lease held and how many retries are permitted", C,
       frozenset({"lab-worker-profile-v1"})),
    _q("pi-04", "project_isolation_and_unscoped_rejection", "unscoped",
       "which port number is bound for incoming connections", None, frozenset()),
)


def questions_for_class(cls: str) -> tuple[Question, ...]:
    return tuple(q for q in QUESTIONS if q.cls == cls)


def question_texts() -> tuple[str, ...]:
    return tuple(q.text for q in QUESTIONS)
