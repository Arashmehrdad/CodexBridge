"""Bounded stand-in launch with persist-before-attach.

This module starts a *stand-in* process tree. It does not launch Claude Code or
Codex, and it holds no provider credential. Its job is to prove the ownership
boundary that a real provider launch will later reuse.

The ordering rule is the whole point: a process identity that exists but is not
yet recorded is an orphan waiting to happen, so nothing may report attachment
ready until the provider-root observation is durable. When identity capture
fails *after* process creation, the tree is contained and the binding is marked
unverified -- Soma never leaves a process it cannot name.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from ..process_control import (
    list_descendants,
    process_group_popen_kwargs,
    process_identity,
    process_is_running,
)
from ..worker_substrate import ProviderChildRole, SessionBindingDisposition
from .cancellation import contain_tree
from .environment import EnvironmentEvidence, build_child_environment
from .executable import ExecutableIdentity, require_unchanged, verify_executable


class AttachmentDisposition(str, Enum):
    """Outcome of one launch-and-attach attempt.

    Not a lifecycle. ``RunStore`` still owns whether the run is running; this
    says only whether Soma can name what it started.
    """

    ATTACHED = "attached"
    LAUNCH_FAILED = "launch_failed"
    CONTAINED_UNVERIFIED = "contained_unverified"


@dataclass(frozen=True)
class AttachmentResult:
    disposition: AttachmentDisposition
    root_pid: int = 0
    root_identity: str = ""
    descendant_count: int = 0
    environment_evidence: EnvironmentEvidence | None = None
    executable_identity: ExecutableIdentity | None = None
    containment: Mapping[str, Any] | None = None
    detail: str = ""

    @property
    def attached(self) -> bool:
        return self.disposition is AttachmentDisposition.ATTACHED

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "root_pid": self.root_pid,
            "root_identity": self.root_identity,
            "descendant_count": self.descendant_count,
            "environment_evidence": (
                None
                if self.environment_evidence is None
                else self.environment_evidence.to_dict()
            ),
            "executable_identity": (
                None
                if self.executable_identity is None
                else self.executable_identity.to_dict()
            ),
            "containment": dict(self.containment or {}) or None,
            "detail": self.detail,
        }


@dataclass
class StandInLaunchRequest:
    """Everything needed to start one bounded stand-in tree."""

    session_binding_id: str
    task_id: str
    run_id: str
    executable_path: str
    argv: Sequence[str]
    stdin_text: str | None = None
    working_directory: str = ""
    declared_removals: tuple[str, ...] = ()
    allowlist_extra: tuple[str, ...] = ()
    environment_additions: Mapping[str, str] = field(default_factory=dict)
    descendant_settle_seconds: float = 1.0


def launch_stand_in(
    store,
    request: StandInLaunchRequest,
    *,
    popen=subprocess.Popen,
) -> AttachmentResult:
    """Start one stand-in tree and record its identity before reporting ready.

    ``store`` is a :class:`~soma.worker_substrate.WorkerSubstrateStore`. It is
    passed in rather than constructed here so this module owns no persistence
    and cannot become a second authority.
    """
    # 1. Verify the executable and sanitise the environment before anything
    #    exists to clean up.
    identity = verify_executable(request.executable_path)
    sanitised = build_child_environment(
        declared_removals=request.declared_removals,
        allowlist_extra=request.allowlist_extra,
        additions=request.environment_additions,
    )

    # 2. Re-verify at the last possible moment. A path swapped after the first
    #    check is the case this closes.
    identity = require_unchanged(identity)

    # 3. Create the process in its own group so the whole tree is terminable.
    try:
        process = popen(
            [identity.path, *request.argv],
            cwd=request.working_directory or None,
            env=dict(sanitised.environment),
            stdin=subprocess.PIPE if request.stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **process_group_popen_kwargs(),
        )
    except OSError as exc:
        # Nothing was created, so there is nothing to contain. The canonical run
        # plane decides what a failed launch means; this reports it honestly.
        return AttachmentResult(
            disposition=AttachmentDisposition.LAUNCH_FAILED,
            environment_evidence=sanitised.evidence,
            executable_identity=identity,
            detail=f"process creation failed: {exc}",
        )

    root_pid = int(getattr(process, "pid", 0) or 0)
    if request.stdin_text is not None and getattr(process, "stdin", None) is not None:
        try:
            process.stdin.write(request.stdin_text.encode("utf-8"))
            process.stdin.close()
        except OSError:
            pass

    # 4. Capture the start identity. From here on a failure means a live process
    #    exists, so every exit path below contains the tree.
    root_identity = process_identity(root_pid)
    if not root_identity:
        containment = contain_tree(
            root_pid=root_pid,
            root_identity="",
            recorded=(),
            reason="provider root start identity could not be captured",
        )
        _mark_unverified(
            store,
            request.session_binding_id,
            "root start identity unavailable after process creation",
        )
        return AttachmentResult(
            disposition=AttachmentDisposition.CONTAINED_UNVERIFIED,
            root_pid=root_pid,
            environment_evidence=sanitised.evidence,
            executable_identity=identity,
            containment=containment,
            detail="root start identity unavailable; tree contained",
        )

    # 5. Persist the root BEFORE anything may report attachment ready.
    try:
        store.record_child_process(
            session_binding_id=request.session_binding_id,
            task_id=request.task_id,
            run_id=request.run_id,
            role=ProviderChildRole.PROVIDER_ROOT,
            pid=root_pid,
            process_start_identity=root_identity,
            image_name=identity.path,
            observation_source="stand_in_launch",
        )
    except Exception as exc:
        containment = contain_tree(
            root_pid=root_pid,
            root_identity=root_identity,
            recorded=(),
            reason="provider root observation could not be persisted",
        )
        _mark_unverified(
            store,
            request.session_binding_id,
            f"root observation not persisted: {exc}",
        )
        return AttachmentResult(
            disposition=AttachmentDisposition.CONTAINED_UNVERIFIED,
            root_pid=root_pid,
            root_identity=root_identity,
            environment_evidence=sanitised.evidence,
            executable_identity=identity,
            containment=containment,
            detail=f"root observation not persisted: {exc}",
        )

    # 6. Let the tree establish itself, then record the descendants that exist.
    #    Descendants discovered later are still terminated at cancellation: this
    #    snapshot is evidence, not the authoritative owned set.
    if request.descendant_settle_seconds > 0:
        time.sleep(request.descendant_settle_seconds)
    descendants = record_descendants(
        store,
        session_binding_id=request.session_binding_id,
        task_id=request.task_id,
        run_id=request.run_id,
        root_pid=root_pid,
    )

    return AttachmentResult(
        disposition=AttachmentDisposition.ATTACHED,
        root_pid=root_pid,
        root_identity=root_identity,
        descendant_count=len(descendants),
        environment_evidence=sanitised.evidence,
        executable_identity=identity,
    )


def record_descendants(
    store,
    *,
    session_binding_id: str,
    task_id: str,
    run_id: str,
    root_pid: int,
) -> list[tuple[int, str]]:
    """Persist every live descendant of the root with its own start identity."""
    recorded: list[tuple[int, str]] = []
    for pid in list_descendants(root_pid):
        if not process_is_running(pid):
            continue
        child_identity = process_identity(pid)
        if not child_identity:
            # A descendant that vanished between enumeration and identity
            # capture is not recorded: an identity-less row cannot be verified
            # later and would weaken the zero-descendant proof.
            continue
        store.record_child_process(
            session_binding_id=session_binding_id,
            task_id=task_id,
            run_id=run_id,
            role=ProviderChildRole.OWNED_DESCENDANT,
            pid=pid,
            process_start_identity=child_identity,
            observation_source="descendant_discovery",
        )
        recorded.append((pid, child_identity))
    return recorded


def _mark_unverified(store, session_binding_id: str, reason: str) -> None:
    try:
        store.set_binding_disposition(
            session_binding_id,
            disposition=SessionBindingDisposition.UNVERIFIED,
            reason=reason,
        )
    except Exception:
        # Disposition is evidence, not control flow. Failing to record it must
        # not mask the containment result the caller needs to see.
        pass
