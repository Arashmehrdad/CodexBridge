"""Canonical task plane.

One controller-neutral task identity above provider-neutral execution backends.
The task plane owns canonical task identity, typed links, version-guarded
commands, checkpoints, and task events. It does not copy backend/provider
lifecycle authority: durable-run and reasoning backends remain subordinate
evidence sources selected by the Task's persisted BackendKind.
"""

from .models import (
    TASK_SCHEMA_COMPONENT,
    TASK_SCHEMA_VERSION,
    BackendKind,
    TaskCommandKind,
    TaskCommandStatus,
    TaskEvent,
    TaskKind,
    TaskLink,
    TaskLinkType,
    TaskPhase,
    TaskRecord,
    TaskRecoveryState,
    TaskState,
    TERMINAL_TASK_STATES,
)
from .manager import TaskManager
from .store import TaskRequestConflict, TaskStore

__all__ = [
    "TASK_SCHEMA_COMPONENT",
    "TASK_SCHEMA_VERSION",
    "TERMINAL_TASK_STATES",
    "BackendKind",
    "TaskCommandKind",
    "TaskCommandStatus",
    "TaskEvent",
    "TaskKind",
    "TaskLink",
    "TaskLinkType",
    "TaskManager",
    "TaskPhase",
    "TaskRecord",
    "TaskRecoveryState",
    "TaskRequestConflict",
    "TaskState",
    "TaskStore",
]
