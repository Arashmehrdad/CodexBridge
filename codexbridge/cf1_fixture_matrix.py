from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any, Final

CF1_FIXTURE_MATRIX_VERSION: Final[str] = "cf1.0.fixture-matrix.v1"

class FixtureClass(str, Enum):
    RUN_OUTCOME = "run_outcome"
    EXECUTOR = "executor"
    REPOSITORY = "repository"
    ORCHESTRATION = "orchestration"
    DOMAIN = "domain"

@dataclass(frozen=True)
class CF1FixtureSpec:
    name: str
    fixture_class: FixtureClass
    lifecycle_status: str
    outcome: str
    tool: str
    required_public_fields: tuple[str, ...]
    evidence_kinds: tuple[str, ...]
    notes: str = ""

    def canonical_payload(self) -> dict[str, Any]:
        return {"version": CF1_FIXTURE_MATRIX_VERSION, "name": self.name, "fixture_class": self.fixture_class.value, "lifecycle_status": self.lifecycle_status, "outcome": self.outcome, "tool": self.tool, "required_public_fields": list(self.required_public_fields), "evidence_kinds": list(self.evidence_kinds), "notes": self.notes}

    @property
    def identity_sha256(self) -> str:
        payload = json.dumps(self.canonical_payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return sha256(payload).hexdigest()

_COMMON_FIELDS: Final[tuple[str, ...]] = ("lifecycle_status", "outcome", "current_phase", "action_required", "validation_state", "cancellation_state", "cleanup_state", "reconciliation_required", "safety_failure", "state_version")

CF1_FIXTURE_MATRIX: Final[tuple[CF1FixtureSpec, ...]] = (
    CF1FixtureSpec("successful_run", FixtureClass.RUN_OUTCOME, "completed", "success", "project_command", _COMMON_FIELDS, ("result", "stdout", "stderr")),
    CF1FixtureSpec("failed_run", FixtureClass.RUN_OUTCOME, "failed", "execution_failure", "project_command", _COMMON_FIELDS, ("result", "stdout", "stderr")),
    CF1FixtureSpec("active_run", FixtureClass.RUN_OUTCOME, "running", "in_progress", "executable_profile", _COMMON_FIELDS, ("events", "stdout", "stderr")),
    CF1FixtureSpec("cancelled_run", FixtureClass.RUN_OUTCOME, "cancelled", "cancelled", "project_command", _COMMON_FIELDS, ("result", "events")),
    CF1FixtureSpec("partial_completion", FixtureClass.RUN_OUTCOME, "completed", "partial", "workflow", _COMMON_FIELDS, ("result", "events", "artifacts")),
    CF1FixtureSpec("ambiguous_side_effect", FixtureClass.RUN_OUTCOME, "uncertain", "ambiguous_side_effect", "ssh", _COMMON_FIELDS, ("result", "events", "reconciliation")),
    CF1FixtureSpec("hermes_call", FixtureClass.EXECUTOR, "completed", "success", "hermes_companion", _COMMON_FIELDS, ("result", "provider_identity")),
    CF1FixtureSpec("executable_profile", FixtureClass.EXECUTOR, "completed", "success", "executable_profile", _COMMON_FIELDS, ("result", "stdout", "stderr", "executable_identity")),
    CF1FixtureSpec("repository_read", FixtureClass.REPOSITORY, "completed", "success", "repo_query", _COMMON_FIELDS, ("content", "content_sha256")),
    CF1FixtureSpec("repository_search", FixtureClass.REPOSITORY, "completed", "success", "repo_search", _COMMON_FIELDS, ("matches", "snapshot_identity")),
    CF1FixtureSpec("large_diff", FixtureClass.REPOSITORY, "completed", "success", "repo_diff", _COMMON_FIELDS, ("diff_stats", "hunks", "frozen_diff")),
    CF1FixtureSpec("parallel_group", FixtureClass.ORCHESTRATION, "completed", "partial", "powershell_group", _COMMON_FIELDS, ("children", "result", "events")),
    CF1FixtureSpec("ssh_operation", FixtureClass.EXECUTOR, "completed", "success", "ssh", _COMMON_FIELDS, ("result", "stdout", "stderr", "remote_identity")),
    CF1FixtureSpec("workflow", FixtureClass.ORCHESTRATION, "completed", "success", "workflow", _COMMON_FIELDS, ("steps", "result", "events")),
    CF1FixtureSpec("supervisor", FixtureClass.ORCHESTRATION, "awaiting_chatgpt", "needs_input", "supervisor", _COMMON_FIELDS, ("result", "events", "resume_prompt")),
    CF1FixtureSpec("trading_lab", FixtureClass.DOMAIN, "completed", "success", "trading_lab", _COMMON_FIELDS, ("result", "journal")),
    CF1FixtureSpec("docker", FixtureClass.DOMAIN, "completed", "success", "docker", _COMMON_FIELDS, ("result", "stdout", "stderr")),
    CF1FixtureSpec("cloudflare", FixtureClass.DOMAIN, "completed", "success", "cloudflare", _COMMON_FIELDS, ("result", "provider_response")),
    CF1FixtureSpec("knowledge", FixtureClass.DOMAIN, "completed", "success", "knowledge", _COMMON_FIELDS, ("result", "sources")),
)

def fixture_matrix_by_name() -> dict[str, CF1FixtureSpec]:
    return {fixture.name: fixture for fixture in CF1_FIXTURE_MATRIX}

def validate_fixture_matrix(fixtures: tuple[CF1FixtureSpec, ...] = CF1_FIXTURE_MATRIX) -> None:
    names = [fixture.name for fixture in fixtures]
    if len(names) != len(set(names)):
        raise ValueError("CF1 fixture names must be unique")
    for fixture in fixtures:
        if not fixture.name or not fixture.tool:
            raise ValueError("CF1 fixtures require names and tools")
        if not fixture.required_public_fields:
            raise ValueError(f"CF1 fixture {fixture.name!r} has no public fields")
        if not fixture.evidence_kinds:
            raise ValueError(f"CF1 fixture {fixture.name!r} has no evidence kinds")
        if tuple(dict.fromkeys(fixture.required_public_fields)) != fixture.required_public_fields:
            raise ValueError(f"CF1 fixture {fixture.name!r} repeats public fields")
        if tuple(dict.fromkeys(fixture.evidence_kinds)) != fixture.evidence_kinds:
            raise ValueError(f"CF1 fixture {fixture.name!r} repeats evidence kinds")