from __future__ import annotations

from dataclasses import dataclass
from typing import Final


CF1_RUN_STORE_BASELINE_VERSION: Final[str] = "cf1.2.run-store.v3"

RUN_SCALAR_SUMMARY_COLUMNS: Final[tuple[str, ...]] = (
    "run_id",
    "repo_name",
    "tool",
    "status",
    "risk_level",
    "requires_human",
    "created_at",
    "started_at",
    "ended_at",
    "duration_seconds",
    "pid",
    "launcher_pid",
    "worker_pid",
    "lease_generation",
    "state_version",
    "worker_identity",
    # V3-1A-CANCELLATION-AUTHORITY-1. Classified beside worker_identity: these
    # are process-start identities used to prove ownership before termination,
    # never controller-facing summary fields.
    "launcher_identity",
    "child_identity",
    "worker_claimed_at",
    "launch_attempts",
    "recovery_reason",
    "exit_code",
    "summary",
    "error",
    "safety_failure",
    "current_phase",
    "elapsed_seconds",
    "heartbeat_at",
    "last_output_at",
    "cancellation_requested_at",
    "result_publication_status",
    "result_published_hash",
    "result_published_at",
    "result_publication_error",
    "public_result_schema_version",
    "public_result_source_sha256",
    "public_result_status",
    "public_result_error",
)

RUN_JSON_BLOB_COLUMNS: Final[tuple[str, ...]] = (
    "input_json",
    "progress_json",
    "result_json",
    "public_result_json",
)

RUN_INTERNAL_ONLY_COLUMNS: Final[tuple[str, ...]] = (
    "worker_lease_token",
    "run_dir",
)


@dataclass(frozen=True)
class RunStoreIndexProposal:
    name: str
    columns: tuple[str, ...]
    status: str
    rationale: str


RUN_STORE_INDEX_PROPOSALS: Final[tuple[RunStoreIndexProposal, ...]] = (
    RunStoreIndexProposal(
        name="idx_runs_created_at",
        columns=("created_at",),
        status="existing",
        rationale="supports current newest-first scans but not a stable run_id tie-break",
    ),
    RunStoreIndexProposal(
        name="idx_runs_repo_status",
        columns=("repo_name", "status"),
        status="existing",
        rationale="supports current repository and status filtering",
    ),
    RunStoreIndexProposal(
        name="idx_runs_created_run_id_desc",
        columns=("created_at", "run_id"),
        status="measurement_accepted",
        rationale=(
            "accepted after the 3,245-row run database removed the temporary "
            "ORDER BY B-tree and improved measured unfiltered p95 from 3.82 ms "
            "to 0.10 ms"
        ),
    ),
    RunStoreIndexProposal(
        name="idx_runs_repo_status_created_run_id_desc",
        columns=("repo_name", "status", "created_at", "run_id"),
        status="measurement_rejected",
        rationale=(
            "lower(repo_name) prevents direct use and the accepted ordering index "
            "already improved every representative filtered p95 by at least 92 percent"
        ),
    ),
)
