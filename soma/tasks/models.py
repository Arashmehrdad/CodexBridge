"""Typed canonical task models and the controller-neutral state vocabulary.

Nothing here encodes a controller vendor, an approval concept, or a permission
tier. A canonical task records *which* execution backend owns the work and
*where* the authoritative evidence lives; it never copies that evidence.
"""

from __future__ import annotations

import json
import re
from base64 import b64decode
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Final
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


TASK_SCHEMA_COMPONENT: Final[str] = "canonical_task_plane"
TASK_SCHEMA_VERSION: Final[int] = 2
TASK_MODEL_VERSION: Final[str] = "task.v1"

TASK_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^task_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)
COMMAND_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^taskcmd_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)
CHECKPOINT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^taskckpt_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{12}$"
)


class TaskState(str, Enum):
    """Complete controller-neutral task state vocabulary.

    There is deliberately no approval state and no controller-specific state.
    """

    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_CONTROLLER = "awaiting_controller"
    PAUSED = "paused"
    CANCELLATION_PENDING = "cancellation_pending"
    RECOVERY_PENDING = "recovery_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNCERTAIN = "uncertain"


TERMINAL_TASK_STATES: Final[frozenset[TaskState]] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
)


class TaskPhase(str, Enum):
    """Coarse progress marker inside a state; never a permission concept."""

    NONE = ""
    ACCEPTED = "accepted"
    BACKEND_RESERVED = "backend_reserved"
    BACKEND_LAUNCHING = "backend_launching"
    BACKEND_RUNNING = "backend_running"
    AWAITING_CONTROLLER = "awaiting_controller"
    BACKEND_TERMINAL = "backend_terminal"
    CANCELLATION_REQUESTED = "cancellation_requested"
    RECOVERY = "recovery"
    RESULT_PUBLISHED = "result_published"


class TaskKind(str, Enum):
    DURABLE_COMMAND = "durable_command"


class BackendKind(str, Enum):
    """Selected execution backend. The existing durable engine is the default."""

    SOMA_DURABLE_RUN = "soma_durable_run"


class TaskLinkType(str, Enum):
    PARENT = "parent"
    CHILD = "child"
    BACKEND_RUN = "backend_run"
    RELATED = "related"
    SUPERSEDES = "supersedes"


class TaskLinkTargetKind(str, Enum):
    TASK = "task"
    DURABLE_RUN = "durable_run"


class TaskCommandKind(str, Enum):
    CANCEL = "cancel"
    STEER = "steer"
    SUPPLY_INPUT = "supply_input"


class TaskCommandStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED_STALE_VERSION = "rejected_stale_version"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCheckpointStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class TaskRecoveryState(str, Enum):
    NONE = "none"
    PENDING = "pending"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class TaskEventLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opaque_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:12]}"


def make_task_id() -> str:
    return _opaque_id("task")


def make_command_id() -> str:
    return _opaque_id("taskcmd")


def make_checkpoint_id() -> str:
    return _opaque_id("taskckpt")


def checkpoint_id_for_request(task_id: str, idempotency_key: str) -> str:
    """Derive one opaque checkpoint identity for one exact wait request."""
    validate_task_id(task_id)
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key must be non-empty")
    stamp = task_id.removeprefix("task_").split("_", 1)[0]
    digest = sha256(
        f"soma.task_checkpoint.wait.v1\0{task_id}\0{idempotency_key}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    return f"taskckpt_{stamp}_{digest}"


def validate_task_id(task_id: str) -> None:
    if not TASK_ID_PATTERN.match(task_id):
        raise ValueError(f"Invalid task_id: {task_id}")


DURABLE_RUN_EXECUTOR: Final[str] = "executable_profile"

# Reference schemes point at evidence that already exists in the durable run
# store. The task plane never becomes a second copy of that evidence.
RUN_INPUT_REFERENCE_PREFIX: Final[str] = "run_input:"
RUN_TERMINAL_REFERENCE_PREFIX: Final[str] = "run_terminal:"


def run_input_reference(run_id: str) -> str:
    return f"{RUN_INPUT_REFERENCE_PREFIX}{run_id}"


def run_terminal_reference(run_id: str) -> str:
    return f"{RUN_TERMINAL_REFERENCE_PREFIX}{run_id}"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _stdin_descriptor(
    stdin_text: str | None, stdin_base64: str | None
) -> dict[str, Any]:
    """Describe stdin by content identity so equivalent forms hash identically.

    The descriptor never carries the value itself, so a normalized request hash
    can be stored in the canonical task row without storing the payload.
    """
    if stdin_text is not None and stdin_base64 is not None:
        raise ValueError("Specify either stdin_text or stdin_base64, not both")
    if stdin_text is not None:
        payload = stdin_text.encode("utf-8")
    elif stdin_base64 is not None:
        payload = b64decode(stdin_base64, validate=True)
    else:
        return {"present": False, "bytes": 0, "sha256": ""}
    return {
        "present": True,
        "bytes": len(payload),
        "sha256": sha256(payload).hexdigest(),
    }


def normalize_durable_command_request(
    *,
    repo_name: str,
    profile_id: str,
    argv: list[str],
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_text: str | None = None,
    stdin_base64: str | None = None,
    timeout_seconds: int | None = None,
    parent_task_id: str = "",
) -> dict[str, Any]:
    """Return the deterministic normalized form used for request hashing.

    The controller request ID is deliberately excluded: the hash answers
    "is this the same request?", not "who asked?".
    """
    return {
        "task_kind": TaskKind.DURABLE_COMMAND.value,
        "backend_kind": BackendKind.SOMA_DURABLE_RUN.value,
        "backend_executor": DURABLE_RUN_EXECUTOR,
        "repo_name": repo_name,
        "profile_id": profile_id,
        "argv": list(argv),
        "working_directory": working_directory,
        "environment": {
            str(key): str(value) for key, value in sorted((environment or {}).items())
        },
        "stdin": _stdin_descriptor(stdin_text, stdin_base64),
        "timeout_seconds": timeout_seconds,
        "parent_task_id": parent_task_id,
    }


def normalize_scoped_durable_command_request(
    *,
    project_id: str,
    resource_id: str,
    repo_name: str,
    profile_id: str,
    argv: list[str],
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_text: str | None = None,
    stdin_base64: str | None = None,
    timeout_seconds: int | None = None,
    parent_task_id: str = "",
) -> dict[str, Any]:
    """Return a versioned scoped hash domain without changing legacy hashes."""
    legacy = normalize_durable_command_request(
        repo_name=repo_name,
        profile_id=profile_id,
        argv=argv,
        working_directory=working_directory,
        environment=environment,
        stdin_text=stdin_text,
        stdin_base64=stdin_base64,
        timeout_seconds=timeout_seconds,
        parent_task_id=parent_task_id,
    )
    return {
        "hash_domain": "soma.project_scope.task_request.v1",
        "project_id": project_id,
        "resource_id": resource_id,
        "request": legacy,
    }


def normalized_request_hash(normalized: dict[str, Any]) -> str:
    return sha256(canonical_json(normalized).encode("utf-8")).hexdigest()


class TaskRecord(BaseModel):
    """Canonical public task identity."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    parent_task_id: str = ""
    task_kind: TaskKind
    controller_request_id: str
    request_hash: str
    objective_ref: str = ""
    constraints_ref: str = ""
    backend_kind: BackendKind
    backend_executor: str = ""
    backend_ref: str = ""
    backend_identity: dict[str, Any] = Field(default_factory=dict)
    workspace_kind: str = ""
    workspace_ref: str = ""
    state: TaskState
    phase: TaskPhase = TaskPhase.NONE
    state_version: int = 0
    checkpoint_ref: str = ""
    result_ref: str = ""
    result_hash: str = ""
    evidence_ref: str = ""
    recovery_state: TaskRecoveryState = TaskRecoveryState.NONE
    recovery_reason: str = ""
    reconciled_at: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    ended_at: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_TASK_STATES

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TaskLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = 0
    task_id: str
    link_type: TaskLinkType
    target_kind: TaskLinkTargetKind
    target_id: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TaskCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    task_id: str
    command_kind: TaskCommandKind
    controller_request_id: str = ""
    requested_state_version: int
    observed_state_version: int
    status: TaskCommandStatus
    reason: str = ""
    created_at: str
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TaskCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str
    task_id: str
    kind: str
    prompt: str = ""
    expected_input_schema: dict[str, Any] = Field(default_factory=dict)
    context_ref: str = ""
    evidence_ref: str = ""
    required_state_version: int
    status: TaskCheckpointStatus = TaskCheckpointStatus.OPEN
    created_at: str
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = 0
    task_id: str
    timestamp: str
    level: TaskEventLevel
    stage: str
    message: str
    state: str = ""
    state_version: int = 0
    data: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# Durable run status -> canonical task state. The mapping is intentionally
# conservative: an unknown backend status becomes ``uncertain`` rather than an
# invented success.
BACKEND_RUN_STATE_MAP: Final[dict[str, TaskState]] = {
    "launch_pending": TaskState.QUEUED,
    "queued": TaskState.QUEUED,
    "running": TaskState.RUNNING,
    "cancellation_pending": TaskState.CANCELLATION_PENDING,
    "recovery_pending": TaskState.RECOVERY_PENDING,
    "completed": TaskState.COMPLETED,
    # A degraded-but-finished durable run is finished. The canonical task does
    # not claim success on its own: the authoritative outcome stays in the run
    # result the task references.
    "partial": TaskState.COMPLETED,
    "timed_out": TaskState.FAILED,
    "failed": TaskState.FAILED,
    "cancelled": TaskState.CANCELLED,
    "needs_input": TaskState.AWAITING_CONTROLLER,
}

BACKEND_RUN_PHASE_MAP: Final[dict[str, TaskPhase]] = {
    "launch_pending": TaskPhase.BACKEND_LAUNCHING,
    "queued": TaskPhase.BACKEND_LAUNCHING,
    "running": TaskPhase.BACKEND_RUNNING,
    "cancellation_pending": TaskPhase.CANCELLATION_REQUESTED,
    "recovery_pending": TaskPhase.RECOVERY,
}


def map_backend_status(status: str) -> tuple[TaskState, TaskPhase]:
    state = BACKEND_RUN_STATE_MAP.get(status)
    if state is None:
        return TaskState.UNCERTAIN, TaskPhase.RECOVERY
    phase = BACKEND_RUN_PHASE_MAP.get(status)
    if phase is None:
        phase = (
            TaskPhase.BACKEND_TERMINAL
            if state in TERMINAL_TASK_STATES or state is TaskState.AWAITING_CONTROLLER
            else TaskPhase.NONE
        )
    return state, phase
