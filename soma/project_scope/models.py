"""Typed project-scope identities and controller-neutral state vocabulary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Final


PROJECT_SCOPE_SCHEMA_COMPONENT: Final[str] = "project_scope"
PROJECT_SCOPE_SCHEMA_VERSION: Final[int] = 2
PROJECT_SCOPE_MODEL_VERSION: Final[str] = "project_scope.v1"
SCOPED_REQUEST_HASH_DOMAIN: Final[str] = "soma.project_scope.task_request.v1"
ADJUDICATION_ID_DOMAIN: Final[str] = "soma.project_scope.quarantine_adjudication.v1"
ADJUDICATION_REQUEST_DOMAIN: Final[str] = (
    "soma.project_scope.quarantine_adjudication_request.v1"
)


class ProjectLifecycle(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class ResourceAccessMode(str, Enum):
    EXCLUSIVE = "exclusive"
    SHARED = "shared"


class TaskBindingStatus(str, Enum):
    RESERVED = "reserved"
    ATTACHED = "attached"
    QUARANTINED = "quarantined"


class AttemptBindingStatus(str, Enum):
    RESERVED = "reserved"
    ATTACHED = "attached"
    RECOVERY_PENDING = "recovery_pending"
    QUARANTINED = "quarantined"


class QuarantineRecordKind(str, Enum):
    TASK_RESERVATION = "task_reservation"
    RUN_ATTEMPT = "run_attempt"


class QuarantineDisposition(str, Enum):
    """Owner adjudication outcomes. Neither returns a record to an active state."""

    ACKNOWLEDGED = "acknowledged"
    SUPERSEDED = "superseded"


class ProjectScopeError(ValueError):
    """The requested operation cannot establish authoritative project scope."""


class ProjectScopeMismatch(ProjectScopeError):
    """An exact task, run, or resource belongs to another project."""


@dataclass(frozen=True)
class RepositoryBinding:
    project_id: str
    project_key: str
    resource_id: str
    repo_name: str
    repository_root: str
    identity_hash: str
    scope_generation: int
    access_mode: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "project_key": self.project_key,
            "resource_id": self.resource_id,
            "repo_name": self.repo_name,
            "repository_root": self.repository_root,
            "identity_hash": self.identity_hash,
            "scope_generation": self.scope_generation,
            "access_mode": self.access_mode,
        }


@dataclass(frozen=True)
class ScopeProjection:
    binding_status: str
    project_id: str = ""
    resource_id: str = ""
    scope_generation: int = 0
    attempt_status: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "project_binding_status": self.binding_status,
        }
        if self.project_id:
            payload.update(
                {
                    "project_id": self.project_id,
                    "project_resource_id": self.resource_id,
                    "scope_generation": self.scope_generation,
                }
            )
        if self.attempt_status:
            payload["project_attempt_status"] = self.attempt_status
        return payload


def validate_opaque_id(value: str, field_name: str) -> str:
    """Validate shape without normalising opaque identity."""
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ProjectScopeError(f"{field_name} must be a non-empty opaque string")
    if "\x00" in value:
        raise ProjectScopeError(f"{field_name} contains an embedded NUL")
    return value


def canonical_repository_root(value: str | Path) -> str:
    """Return the stable locator used only to hash an explicit repository root."""
    path = Path(value).expanduser().resolve()
    normalized = os.path.normcase(str(path))
    return normalized.replace("\\", "/")


def repository_identity_hash(value: str | Path) -> str:
    identity = canonical_repository_root(value)
    return sha256(identity.encode("utf-8")).hexdigest()


def path_is_within_repository(
    working_directory: str | Path, repository_root: str | Path
) -> bool:
    candidate = Path(working_directory).expanduser().resolve()
    root = Path(repository_root).expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True
