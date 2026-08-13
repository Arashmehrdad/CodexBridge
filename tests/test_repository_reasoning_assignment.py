from __future__ import annotations

import hashlib

import pytest

from soma.reasoning.repository_assignment import (
    RepositoryAssignmentError,
    RepositoryReasoningAssignmentStore,
    RepositoryReasoningAssignmentV1,
)


def _assignment() -> RepositoryReasoningAssignmentV1:
    return RepositoryReasoningAssignmentV1(
        repo_name="Soma",
        source_commit="0123456789abcdef0123456789abcdef01234567",
        objective="Inspect the durable task path.",
        instructions="Return evidence locations for relevant claims.",
    )


def test_assignment_identity_is_content_addressed_and_replay_safe(tmp_path) -> None:
    assignment = _assignment()
    store = RepositoryReasoningAssignmentStore(tmp_path)

    ref, digest, created = store.write(assignment)
    replay_ref, replay_digest, replay_created = store.write(assignment)

    assert created is True
    assert replay_created is False
    assert ref == replay_ref == assignment.assignment_ref
    assert digest == replay_digest == assignment.assignment_hash
    assert digest == hashlib.sha256(assignment.canonical_bytes()).hexdigest()
    assert store.read(ref) == assignment


def test_assignment_hash_changes_with_objective() -> None:
    first = _assignment()
    second = first.model_copy(update={"objective": "A different objective."})
    assert first.assignment_hash != second.assignment_hash
    assert first.assignment_ref != second.assignment_ref


def test_assignment_store_fails_closed_for_missing_or_corrupt_artifact(tmp_path) -> None:
    store = RepositoryReasoningAssignmentStore(tmp_path)
    assignment = _assignment()
    ref, digest, _created = store.write(assignment)
    path = store.root / f"{digest}.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(RepositoryAssignmentError, match="hash mismatch"):
        store.read(ref)
    with pytest.raises(RepositoryAssignmentError, match="missing"):
        store.read("reasoning_assignment:" + "a" * 64)
