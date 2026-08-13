"""Scripted production repository backend tests with no provider execution."""

import json
import subprocess
from pathlib import Path

from soma.reasoning.codex_app_server import CodexTurnEvidence
from soma.reasoning.codex_repository_backend import CodexRepositoryReasoningBackend
from soma.reasoning.codex_repository_contract import (
    CODEX_REPOSITORY_MODEL,
    CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256,
    make_repository_reasoning_spec,
)
from soma.reasoning.repository_assignment import (
    RepositoryReasoningAssignmentStore,
    RepositoryReasoningAssignmentV1,
)
from soma.reasoning.repository_evidence import REPOSITORY_REASONING_SEMANTIC_VERSION
from soma.reasoning.store import ReasoningBackendStore


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = "soma/tasks/models.py"


def _head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().lower()


def _semantic(end_line: int = 1) -> str:
    return json.dumps({
        "schema_version": REPOSITORY_REASONING_SEMANTIC_VERSION,
        "submission_disposition": "complete",
        "executive_summary": "Scripted worker result.",
        "claims": [{
            "claim_id": "c1",
            "claim_class": "observation",
            "subject_key": "fixture.value",
            "statement": "A worker-selected conclusion.",
            "evidence_locations": [{
                "source_path": SOURCE_PATH,
                "start_line": 1,
                "end_line": end_line,
            }],
            "uncertainty_ids": [],
        }],
        "uncertainties": [],
        "blockers": [],
    }, separators=(",", ":"))


class ScriptedClient:
    def __init__(self, message: str) -> None:
        self.message = message
        self.server_requests: list[dict] = []
        self.prompt = ""
        self.closed = False

    def start_thread(self, *, working_directory: str, model: str = "") -> dict:
        assert Path(working_directory) == REPO_ROOT
        assert model == CODEX_REPOSITORY_MODEL
        return {"thread": {"id": "thread_repo"}}

    def begin_turn(self, **kwargs) -> int:
        self.prompt = kwargs["prompt"]
        assert kwargs["output_schema"]["additionalProperties"] is False
        return 1

    def wait_for_turn_started(self, **kwargs) -> str:
        return "turn_repo"

    def wait_for_turn_completed(self, **kwargs) -> CodexTurnEvidence:
        return CodexTurnEvidence(
            thread_id="thread_repo",
            turn_id="turn_repo",
            status="completed",
            events=({"method": "turn/completed", "params": {"threadId": "thread_repo"}},),
            agent_message=self.message,
            token_usage_events=({
                "tokenUsage": {"total": {
                    "inputTokens": 100,
                    "outputTokens": 20,
                    "totalTokens": 120,
                }}
            },),
        )

    def interrupt_turn(self, **kwargs) -> dict:
        return {}

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> dict:
        return {"thread": {"id": thread_id, "turns": []}}

    def close(self) -> None:
        self.closed = True


def _backend(tmp_path: Path, client: ScriptedClient):
    runs = tmp_path / "runs"
    assignments = RepositoryReasoningAssignmentStore(runs)
    assignment = RepositoryReasoningAssignmentV1(
        repo_name="Soma",
        source_commit=_head(),
        objective="Inspect canonical Task ownership.",
    )
    ref, digest, _created = assignments.write(assignment)
    backend = CodexRepositoryReasoningBackend(
        ReasoningBackendStore(runs),
        assignment_resolver=assignments.read,
        repository_root_resolver=lambda _name: REPO_ROOT,
        task_id_resolver=lambda _ref: "task_repository",
        client_factory=lambda: client,
        preflight=lambda: {
            "auth_type": "chatgpt",
            "protocol_manifest_sha256": CODEX_REPOSITORY_PROTOCOL_MANIFEST_SHA256,
            "models": [CODEX_REPOSITORY_MODEL],
            "model_available": True,
        },
    )
    spec = make_repository_reasoning_spec(assignment_ref=ref, assignment_hash=digest)
    return backend, spec, assignment.source_commit


def test_backend_publishes_mechanically_bound_worker_evidence(tmp_path: Path) -> None:
    client = ScriptedClient(_semantic())
    backend, spec, commit = _backend(tmp_path, client)
    observation = backend.start(spec, backend.reserve())
    submission = backend.load_evidence_submission(observation.backend_ref)

    assert observation.output_contract_disposition == "valid"
    assert submission is not None
    assert submission.evidence[0].source_ref == f"git:{commit}:{SOURCE_PATH}"
    assert submission.claims[0].opposes_evidence_ids == ()
    assert "reason about the code yourself" in client.prompt
    assert "Soma will not judge whether the evidence proves your claim" in client.prompt
    assert client.closed is True


def test_invalid_line_range_fails_mechanically_not_semantically(tmp_path: Path) -> None:
    backend, spec, _commit = _backend(tmp_path, ScriptedClient(_semantic(999999)))
    observation = backend.start(spec, backend.reserve())
    assert observation.provider_terminal_claim == "success"
    assert observation.output_contract_disposition == "invalid"
    assert observation.error_code == "invalid_repository_output"
