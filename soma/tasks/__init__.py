"""Canonical task plane.

One controller-neutral public task identity above Soma's existing durable
execution engine. The task plane owns canonical task identity, typed links,
version-guarded commands, checkpoints, and task events. It does not own
worker, lease, lock, evidence, or result authority: those remain with the
existing durable run engine, which the task plane references.
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
