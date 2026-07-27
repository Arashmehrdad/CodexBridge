"""Curated 60-record corpus, written as a reviewable deterministic fixture.

Two deliberately similar projects share vocabulary ("runtime port", "store
size", "worker lease") so that accidental cross-project leakage is plausible
rather than theoretical. Values always differ between the projects, so a leak
is detectable rather than merely suspected.

Nothing here contains question text or an answer marker. The bodies state
facts the way a note would; the questions live in ``questions.py`` and are
checked for verbatim leakage before any measured run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from .contract import CONFUSION_PROJECT_ID, SOMA_PROJECT_ID


@dataclass(frozen=True)
class NoteSpec:
    note_id: str
    project_id: str
    kind: str
    title: str
    body: str
    created: str
    source: str = ""
    supersedes: tuple[str, ...] = ()
    #: (predecessor_note_id, claim_key) - this note replaces only that claim.
    supersedes_claims: tuple[tuple[str, str], ...] = ()
    claims: tuple[tuple[str, str], ...] = ()
    #: (relation_type, target_note_id) - rendered as a typed wikilink.
    relations: tuple[tuple[str, str], ...] = field(default=())
    #: Emits deliberately broken YAML to exercise malformed-metadata handling.
    malformed_frontmatter: bool = False


S = SOMA_PROJECT_ID
C = CONFUSION_PROJECT_ID


_SOMA_NOTES: tuple[NoteSpec, ...] = (
    # --- exact recall anchors -------------------------------------------
    NoteSpec(
        "soma-runtime-port", S, "fact", "Runtime listener port",
        "The control plane binds its HTTP listener on port 8000 at the loopback "
        "address. The MCP route is served under the /mcp path.",
        "2026-01-04", source="soma/server.py",
        claims=(("http_port", "8000"), ("mcp_path", "/mcp")),
    ),
    NoteSpec(
        "soma-executable-profile", S, "fact", "Executable profile identity",
        "Durable commands run through the powershell executable profile. The "
        "profile pins the interpreter path and records an observed digest.",
        "2026-01-06", source="soma/executable_profiles.py",
        claims=(("default_profile", "powershell"),),
    ),
    NoteSpec(
        "soma-journal-mode", S, "fact", "Store journal mode",
        "The durable store runs in write-ahead logging mode so readers do not "
        "block the worker during a long publication.",
        "2026-01-09", source="soma/run_store.py",
        claims=(("journal_mode", "wal"),),
    ),

    # --- multi-hop full supersession A <- B <- C -------------------------
    NoteSpec(
        "soma-store-size-v1", S, "fact", "Durable store size, first survey",
        "A first survey of the durable store recorded a total on-disk size of "
        "96 MB across all published runs.",
        "2026-01-11", source="runs/soma.sqlite3",
        claims=(("store_size", "96 MB"),),
    ),
    NoteSpec(
        "soma-store-size-v2", S, "fact", "Durable store size, second survey",
        "A later survey of the durable store recorded a total on-disk size of "
        "118 MB after several weeks of ordinary run traffic.",
        "2026-03-02", source="runs/soma.sqlite3",
        supersedes=("soma-store-size-v1",),
        claims=(("store_size", "118 MB"),),
        relations=(("supersedes", "soma-store-size-v1"),),
    ),
    NoteSpec(
        "soma-store-size-v3", S, "fact", "Durable store size, current survey",
        "The durable store now measures 131 MB on disk. Growth is dominated by "
        "protected evidence artifacts rather than row count.",
        "2026-07-01", source="runs/soma.sqlite3",
        supersedes=("soma-store-size-v2",),
        claims=(("store_size", "131 MB"),),
        relations=(("supersedes", "soma-store-size-v2"),),
    ),

    # --- partial claim-level supersession --------------------------------
    NoteSpec(
        "soma-worker-profile-v1", S, "fact", "Worker lease and retry profile",
        "The worker claims a run under a lease held for 30 seconds. A failed "
        "launch is retried at most 3 times before the run is marked uncertain.",
        "2026-02-01", source="soma/job_worker.py",
        claims=(("lease_seconds", "30"), ("retry_limit", "3")),
    ),
    NoteSpec(
        "soma-worker-profile-v2", S, "fact", "Worker lease extended",
        "The worker lease was extended to 45 seconds after slow filesystem "
        "staging was observed on large artifact writes. Only the lease duration "
        "changed.",
        "2026-05-14", source="soma/job_worker.py",
        supersedes_claims=(("soma-worker-profile-v1", "lease_seconds"),),
        claims=(("lease_seconds", "45"),),
        relations=(("amends", "soma-worker-profile-v1"),),
    ),

    # --- contradiction / duplicate / current-fact precision --------------
    NoteSpec(
        "soma-tunnel-endpoint-old", S, "fact", "Public tunnel endpoint, retired",
        "The public tunnel endpoint was reachable at the retired hostname "
        "mcp-legacy.example.invalid during the early bridge period.",
        "2026-01-20", source="scripts/manage_soma_service.ps1",
        claims=(("tunnel_host", "mcp-legacy.example.invalid"),),
    ),
    NoteSpec(
        "soma-tunnel-endpoint-current", S, "fact", "Public tunnel endpoint",
        "The public tunnel endpoint is served from the current hostname "
        "mcp.example.invalid through a named Cloudflare tunnel.",
        "2026-04-18", source="scripts/manage_soma_service.ps1",
        supersedes=("soma-tunnel-endpoint-old",),
        claims=(("tunnel_host", "mcp.example.invalid"),),
        relations=(("supersedes", "soma-tunnel-endpoint-old"),),
    ),
    NoteSpec(
        "soma-tunnel-duplicate", S, "fact", "Tunnel endpoint restated",
        "A duplicate record restating the tunnel hostname. It repeats the same "
        "current hostname mcp.example.invalid without adding anything new.",
        "2026-04-19", source="scripts/manage_soma_service.ps1",
        claims=(("tunnel_host", "mcp.example.invalid"),),
        relations=(("duplicates", "soma-tunnel-endpoint-current"),),
    ),

    # --- decisions --------------------------------------------------------
    NoteSpec(
        "soma-decision-scope-sidecar", S, "decision", "Scope as a sidecar",
        "Project identity was added as an additive sidecar rather than by "
        "rewriting the incumbent run and task authorities. The incumbent tables "
        "keep ownership of process lifecycle, result, and evidence.",
        "2026-06-02", source="docs/SCOPE_FOUNDATION_1_PRODUCTION_LANE_PROPOSAL_2026-07-27.md",
        claims=(("scope_strategy", "additive sidecar"),),
        relations=(("motivated_by", "soma-lesson-dual-authority"),),
    ),
    NoteSpec(
        "soma-decision-fail-closed", S, "decision", "Fail closed on scope mismatch",
        "A request naming the wrong project is rejected before any backend "
        "query, signal, result, event, link, or artifact read occurs. Rejection "
        "discloses no state.",
        "2026-06-05", source="soma/tasks/manager.py",
        claims=(("mismatch_behaviour", "reject before backend access"),),
        relations=(("implements", "soma-decision-scope-sidecar"),),
    ),
    NoteSpec(
        "soma-decision-markdown-canonical", S, "decision", "Markdown stays canonical",
        "Canonical content remains ordinary files with history in version "
        "control. Any generated structure is treated as disposable so that "
        "deleting it can never lose information.",
        "2026-07-03", source="docs/pilot-memory-1-shadow-baseline-2026-07-27.md",
        claims=(("canonical_format", "markdown"),),
    ),

    # --- lessons ----------------------------------------------------------
    NoteSpec(
        "soma-lesson-dual-authority", S, "lesson", "Two definitions always drift",
        "The same classification was defined in two modules and the copies "
        "diverged, so scratch output was excluded from one consumer and indexed "
        "by the other. One definition, imported by both, prevents recurrence.",
        "2026-05-20", source="soma/tool_owned_paths.py",
        claims=(("root_cause", "duplicated definition"),),
    ),
    NoteSpec(
        "soma-lesson-preparation-counts", S, "lesson", "Stale baselines mislead",
        "Counts captured during preparation were stale by the time approval "
        "arrived. Every activation now takes its own snapshot immediately "
        "before mutating anything.",
        "2026-07-05", source="docs/pilot-evidence.md",
        claims=(("baseline_policy", "resnapshot before mutation"),),
        relations=(("informs", "soma-procedure-activation"),),
    ),
    NoteSpec(
        "soma-lesson-implicit-index", S, "lesson", "Implicit indexes surprise diffs",
        "A raw schema comparison reported extra objects that were really the "
        "unavoidable consequence of declared uniqueness constraints. Matching "
        "each one back to its constraint removed the false alarm.",
        "2026-07-12", source="docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_2026-07-27.md",
        claims=(("false_alarm_source", "constraint backed indexes"),),
    ),

    # --- procedures / skills ---------------------------------------------
    NoteSpec(
        "soma-procedure-activation", S, "procedure", "Live activation sequence",
        "Stop writers, take a verified backup, rehearse the change on a copy of "
        "that backup, apply once, verify, restart, then record evidence. The "
        "rehearsal must reproduce the reviewed object digests exactly.",
        "2026-06-28", source="docs/SCOPE_FOUNDATION_1_PROJECT_SCOPE_V2_ACTIVATION_2026-07-27.md",
        claims=(("step_count", "7"),),
        relations=(("depends_on", "soma-procedure-backup"),),
    ),
    NoteSpec(
        "soma-procedure-backup", S, "procedure", "Backup before mutation",
        "Create the copy through the database backup interface inside a read "
        "transaction, then verify the copy matches the closed original before "
        "trusting it as a restore point.",
        "2026-06-27", source="scripts/comprehensive_self_check.ps1",
        claims=(("backup_method", "online backup interface"),),
    ),
    NoteSpec(
        "soma-procedure-rebuild-index", S, "procedure", "Rebuild a derived index",
        "Delete the generated structure entirely and regenerate it from the "
        "canonical files. A rebuild that cannot be reproduced from files alone "
        "means the files were not actually canonical.",
        "2026-07-08", source="docs/pilot-memory-1-shadow-baseline-2026-07-27.md",
        claims=(("rebuild_input", "canonical files only"),),
    ),

    # --- source references ------------------------------------------------
    NoteSpec(
        "soma-source-plans", S, "source_ref", "Plan of record",
        "The plan of record enumerates active lanes, their status, and the "
        "boundaries that each lane may not cross.",
        "2026-07-20", source="PLANS.md",
    ),
    NoteSpec(
        "soma-source-agents", S, "source_ref", "Operating instructions",
        "The operating instructions describe routing, safety rules, and the "
        "handoff packet for external coding work.",
        "2026-07-21", source="AGENTS.md",
    ),

    # --- relation chains for one-hop and multi-hop questions --------------
    NoteSpec(
        "soma-relation-gate-a", S, "decision", "Gate A foundation",
        "The first gate established the additive identity foundation without "
        "enabling any enforcement.",
        "2026-06-10", source="PLANS.md",
        claims=(("gate", "A"),),
    ),
    NoteSpec(
        "soma-relation-gate-b", S, "decision", "Gate B schema activation",
        "The second gate installed the identity schema on the live store while "
        "leaving enforcement switched off.",
        "2026-06-18", source="PLANS.md",
        supersedes=(),
        claims=(("gate", "B"),),
        relations=(("depends_on", "soma-relation-gate-a"),),
    ),
    NoteSpec(
        "soma-relation-gate-c", S, "decision", "Gate C cutover",
        "The third gate bootstrapped the reviewed identity and turned on scoped "
        "writes, making enforcement active for new work.",
        "2026-07-27", source="PLANS.md",
        claims=(("gate", "C"),),
        relations=(("depends_on", "soma-relation-gate-b"),),
    ),

    # --- source and frontmatter drift -------------------------------------
    NoteSpec(
        "soma-drift-moved-source", S, "fact", "Reference to a relocated file",
        "This record points at a path that no longer exists because the module "
        "was relocated during a refactor.",
        "2026-02-14", source="soma/old_location/moved_module.py",
        claims=(("drift_kind", "moved"),),
    ),
    NoteSpec(
        "soma-drift-deleted-source", S, "fact", "Reference to a deleted file",
        "This record points at a file that was deleted outright and never "
        "replaced.",
        "2026-02-16", source="soma/deleted_helper.py",
        claims=(("drift_kind", "deleted"),),
    ),
    NoteSpec(
        "soma-drift-empty-source", S, "fact", "Record with no source at all",
        "This record carries no source reference, which is itself a metadata "
        "defect worth surfacing during review.",
        "2026-02-18", source="",
        claims=(("drift_kind", "missing"),),
    ),
    NoteSpec(
        "soma-drift-malformed", S, "fact", "Record with broken metadata",
        "The metadata block on this record does not parse. A reader must "
        "surface it rather than silently skipping the content.",
        "2026-02-20", source="soma/server.py",
        claims=(("drift_kind", "malformed"),),
        malformed_frontmatter=True,
    ),

    # --- dangling link + deletion target ----------------------------------
    NoteSpec(
        "soma-dangling-reference", S, "fact", "Record pointing at nothing",
        "This record references a target that is not present in the corpus, "
        "which should be reported rather than ignored.",
        "2026-03-11", source="PLANS.md",
        relations=(("references", "soma-absent-target"),),
    ),
    NoteSpec(
        "soma-deletion-target", S, "fact", "Record scheduled for removal",
        "This record exists so that its removal can be observed, together with "
        "the references that point at it afterwards.",
        "2026-03-12", source="PLANS.md",
        claims=(("removal", "scheduled"),),
    ),
    NoteSpec(
        "soma-deletion-referrer", S, "fact", "Record referring to the removed one",
        "This record refers to a neighbour that is removed partway through the "
        "benchmark run.",
        "2026-03-13", source="PLANS.md",
        relations=(("references", "soma-deletion-target"),),
    ),

    # --- external edit target ---------------------------------------------
    NoteSpec(
        "soma-external-edit", S, "fact", "Record edited outside the tool",
        "This record is modified directly on disk during the run so that the "
        "change can be attributed through version control rather than through "
        "the benchmark's own bookkeeping.",
        "2026-03-15", source="PLANS.md",
        claims=(("edit_channel", "out of band"),),
    ),

    # --- paraphrase targets (deliberately distinctive vocabulary) ---------
    NoteSpec(
        "soma-paraphrase-throttle", S, "fact", "Concurrency ceiling",
        "Simultaneous durable executions are capped so that the host is never "
        "saturated. The ceiling is derived from available processors minus a "
        "reserved margin.",
        "2026-04-02", source="soma/job_manager.py",
        claims=(("concurrency_rule", "processors minus margin"),),
    ),
    NoteSpec(
        "soma-paraphrase-evidence", S, "fact", "Immutable artifact retention",
        "Captured output streams are written once, digested, and never altered "
        "afterwards, so a later reader can confirm nothing was rewritten.",
        "2026-04-04", source="soma/executable_staging.py",
        claims=(("artifact_policy", "write once"),),
    ),
    NoteSpec(
        "soma-paraphrase-quiet-failure", S, "lesson", "Silent truncation reads as success",
        "When a bounded listing dropped entries without saying so, reviewers "
        "believed coverage was complete. Any boundary must announce what it "
        "left out.",
        "2026-04-07", source="AGENTS.md",
        claims=(("reporting_rule", "announce omissions"),),
    ),
)


def _sibling(
    note_id: str,
    kind: str,
    title: str,
    body: str,
    created: str,
    source: str = "",
    claims: tuple[tuple[str, str], ...] = (),
    supersedes: tuple[str, ...] = (),
    supersedes_claims: tuple[tuple[str, str], ...] = (),
    relations: tuple[tuple[str, str], ...] = (),
) -> NoteSpec:
    return NoteSpec(
        note_id, C, kind, title, body, created,
        source=source, claims=claims, supersedes=supersedes,
        supersedes_claims=supersedes_claims, relations=relations,
    )


#: The confusion sibling reuses the Soma vocabulary almost word for word while
#: every value differs. Any retrieval that leaks across projects will surface
#: as a wrong value, not merely as an extra hit.
_SIBLING_NOTES: tuple[NoteSpec, ...] = (
    _sibling(
        "lab-runtime-port", "fact", "Runtime listener port",
        "The lab control plane binds its HTTP listener on port 9400 at the "
        "loopback address. The MCP route is served under the /mcp path.",
        "2026-01-05", "lab/server.py", (("http_port", "9400"),),
    ),
    _sibling(
        "lab-executable-profile", "fact", "Executable profile identity",
        "Durable commands run through the bash executable profile. The profile "
        "pins the interpreter path and records an observed digest.",
        "2026-01-07", "lab/profiles.py", (("default_profile", "bash"),),
    ),
    _sibling(
        "lab-journal-mode", "fact", "Store journal mode",
        "The lab store runs in rollback journal mode, which is simpler but lets "
        "a reader block the writer.",
        "2026-01-10", "lab/store.py", (("journal_mode", "delete"),),
    ),
    _sibling(
        "lab-store-size-v1", "fact", "Durable store size, first survey",
        "A first survey of the lab store recorded a total on-disk size of 12 MB "
        "across all published runs.",
        "2026-01-12", "lab/lab.sqlite3", (("store_size", "12 MB"),),
    ),
    _sibling(
        "lab-store-size-v2", "fact", "Durable store size, current survey",
        "The lab store now measures 19 MB on disk after routine traffic.",
        "2026-03-04", "lab/lab.sqlite3", (("store_size", "19 MB"),),
        supersedes=("lab-store-size-v1",),
        relations=(("supersedes", "lab-store-size-v1"),),
    ),
    _sibling(
        "lab-worker-profile-v1", "fact", "Worker lease and retry profile",
        "The lab worker claims a run under a lease held for 15 seconds. A "
        "failed launch is retried at most 5 times before the run is abandoned.",
        "2026-02-02", "lab/worker.py",
        (("lease_seconds", "15"), ("retry_limit", "5")),
    ),
    _sibling(
        "lab-worker-profile-v2", "fact", "Worker lease shortened",
        "The lab worker lease was shortened to 10 seconds. Only the lease "
        "duration changed.",
        "2026-05-16", "lab/worker.py", (("lease_seconds", "10"),),
        supersedes_claims=(("lab-worker-profile-v1", "lease_seconds"),),
        relations=(("amends", "lab-worker-profile-v1"),),
    ),
    _sibling(
        "lab-tunnel-endpoint-current", "fact", "Public tunnel endpoint",
        "The lab tunnel endpoint is served from the hostname "
        "lab.example.invalid through a named tunnel.",
        "2026-04-20", "lab/service.ps1", (("tunnel_host", "lab.example.invalid"),),
    ),
    _sibling(
        "lab-decision-scope-sidecar", "decision", "Scope as a sidecar",
        "The lab added project identity by rewriting its run table directly, "
        "accepting a migration rather than keeping a sidecar.",
        "2026-06-03", "lab/notes.md", (("scope_strategy", "table rewrite"),),
    ),
    _sibling(
        "lab-decision-fail-open", "decision", "Fail open on scope mismatch",
        "A lab request naming an unknown project is answered with an empty "
        "result instead of a rejection.",
        "2026-06-06", "lab/notes.md",
        (("mismatch_behaviour", "empty result"),),
    ),
    _sibling(
        "lab-lesson-dual-authority", "lesson", "Two definitions always drift",
        "The lab kept the same list in two files and they diverged during a "
        "rename.",
        "2026-05-21", "lab/notes.md", (("root_cause", "duplicated definition"),),
    ),
    _sibling(
        "lab-procedure-activation", "procedure", "Live activation sequence",
        "The lab applies changes directly and relies on a nightly copy rather "
        "than a pre-change backup.",
        "2026-06-29", "lab/runbook.md", (("step_count", "3"),),
    ),
    _sibling(
        "lab-procedure-backup", "procedure", "Backup before mutation",
        "The lab copies the database file with an ordinary filesystem copy "
        "while the writer may still be attached.",
        "2026-06-30", "lab/runbook.md", (("backup_method", "file copy"),),
    ),
    _sibling(
        "lab-paraphrase-throttle", "fact", "Concurrency ceiling",
        "Simultaneous lab executions are capped at a fixed count of four "
        "regardless of the host size.",
        "2026-04-03", "lab/worker.py", (("concurrency_rule", "fixed four"),),
    ),
    _sibling(
        "lab-paraphrase-evidence", "fact", "Artifact retention",
        "Lab output streams are overwritten on rerun, so an earlier capture is "
        "not recoverable.",
        "2026-04-05", "lab/worker.py", (("artifact_policy", "overwrite"),),
    ),
    _sibling(
        "lab-source-plans", "source_ref", "Plan of record",
        "The lab plan lists its experiments and their current status.",
        "2026-07-22", "lab/PLAN.md",
    ),
    _sibling(
        "lab-relation-stage-one", "decision", "Stage one",
        "The lab first stage introduced an identity column with no constraint.",
        "2026-06-11", "lab/PLAN.md", (("gate", "one"),),
    ),
    _sibling(
        "lab-relation-stage-two", "decision", "Stage two",
        "The lab second stage added a uniqueness constraint to the identity "
        "column.",
        "2026-06-19", "lab/PLAN.md", (("gate", "two"),),
        relations=(("depends_on", "lab-relation-stage-one"),),
    ),
    _sibling(
        "lab-drift-moved-source", "fact", "Reference to a relocated file",
        "This lab record points at a path that no longer exists.",
        "2026-02-15", "lab/old/moved.py", (("drift_kind", "moved"),),
    ),
    _sibling(
        "lab-drift-empty-source", "fact", "Record with no source at all",
        "This lab record carries no source reference.",
        "2026-02-19", "", (("drift_kind", "missing"),),
    ),
    _sibling(
        "lab-dangling-reference", "fact", "Record pointing at nothing",
        "This lab record references a target that is not present.",
        "2026-03-16", "lab/PLAN.md",
        relations=(("references", "lab-absent-target"),),
    ),
    _sibling(
        "lab-lesson-quiet-failure", "lesson", "Silent truncation reads as success",
        "A lab listing dropped entries without saying so and reviewers assumed "
        "full coverage.",
        "2026-04-08", "lab/notes.md", (("reporting_rule", "announce omissions"),),
    ),
    _sibling(
        "lab-external-edit", "fact", "Record edited outside the tool",
        "This lab record is not modified during the run and exists as a control "
        "for the edit-attribution check.",
        "2026-03-17", "lab/PLAN.md", (("edit_channel", "none"),),
    ),
    _sibling(
        "lab-gate-terminology", "fact", "Gate terminology",
        "The lab calls its checkpoints stages rather than gates, though the "
        "surrounding wording is otherwise similar.",
        "2026-06-21", "lab/PLAN.md", (("checkpoint_word", "stage"),),
    ),
    _sibling(
        "lab-store-journal-note", "fact", "Store maintenance note",
        "The lab store is compacted by hand each month.",
        "2026-05-02", "lab/runbook.md", (("maintenance", "manual compaction"),),
    ),
    _sibling(
        "lab-source-runbook", "source_ref", "Operating runbook",
        "The lab runbook describes how experiments are started and stopped.",
        "2026-07-23", "lab/runbook.md",
    ),
)

CURATED_NOTES: Final[tuple[NoteSpec, ...]] = _SOMA_NOTES + _SIBLING_NOTES

#: Notes removed partway through the run to exercise deletion detection.
DELETION_NOTE_ID: Final[str] = "soma-deletion-target"
#: Note edited directly on disk to exercise external-edit attribution.
EXTERNAL_EDIT_NOTE_ID: Final[str] = "soma-external-edit"
