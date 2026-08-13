"""Immutable assignment artifacts for repository reasoning workers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import validate_opaque


REPOSITORY_ASSIGNMENT_SCHEMA_VERSION: Final[str] = "repository_reasoning.assignment.v1"
REPOSITORY_ASSIGNMENT_REF_PREFIX: Final[str] = "reasoning_assignment:"


class RepositoryAssignmentError(ValueError):
    """An assignment artifact is invalid, missing, or conflicts with its hash."""


class RepositoryReasoningAssignmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[REPOSITORY_ASSIGNMENT_SCHEMA_VERSION] = (
        REPOSITORY_ASSIGNMENT_SCHEMA_VERSION
    )
    repo_name: str = Field(min_length=1, max_length=128)
    source_commit: str = Field(min_length=40, max_length=40, pattern=r"^[a-f0-9]{40}$")
    objective: str = Field(min_length=1, max_length=16_384)
    instructions: str = Field(default="", max_length=16_384)

    @model_validator(mode="after")
    def _validate_assignment(self):
        validate_opaque(self.repo_name, "repo_name", max_length=128)
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @property
    def assignment_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def assignment_ref(self) -> str:
        return REPOSITORY_ASSIGNMENT_REF_PREFIX + self.assignment_hash


class RepositoryReasoningAssignmentStore:
    """Content-addressed assignment store; identical writes replay exactly."""

    def __init__(self, runs_dir: Path) -> None:
        self.root = Path(runs_dir).resolve() / "reasoning_assignments"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _digest_from_ref(assignment_ref: str) -> str:
        if not assignment_ref.startswith(REPOSITORY_ASSIGNMENT_REF_PREFIX):
            raise RepositoryAssignmentError("unsupported reasoning assignment reference")
        digest = assignment_ref[len(REPOSITORY_ASSIGNMENT_REF_PREFIX) :]
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RepositoryAssignmentError("assignment reference has invalid SHA-256")
        return digest

    def _path(self, digest: str) -> Path:
        return self.root / f"{digest}.json"

    def write(self, assignment: RepositoryReasoningAssignmentV1) -> tuple[str, str, bool]:
        body = assignment.canonical_bytes()
        digest = hashlib.sha256(body).hexdigest()
        path = self._path(digest)
        if path.exists():
            durable = path.read_bytes()
            if durable != body:
                raise RepositoryAssignmentError(
                    "assignment hash path contains different durable bytes"
                )
            return assignment.assignment_ref, digest, False

        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{digest}.", suffix=".tmp", dir=self.root
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temporary, path)
            except OSError:
                if not path.exists() or path.read_bytes() != body:
                    raise
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return assignment.assignment_ref, digest, True

    def read(self, assignment_ref: str) -> RepositoryReasoningAssignmentV1:
        digest = self._digest_from_ref(assignment_ref)
        path = self._path(digest)
        if not path.is_file():
            raise RepositoryAssignmentError("reasoning assignment artifact is missing")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise RepositoryAssignmentError("reasoning assignment artifact hash mismatch")
        try:
            value = json.loads(body.decode("utf-8"))
            assignment = RepositoryReasoningAssignmentV1.model_validate(value)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise RepositoryAssignmentError("reasoning assignment artifact is invalid") from exc
        if assignment.canonical_bytes() != body:
            raise RepositoryAssignmentError("reasoning assignment bytes are not canonical")
        return assignment
