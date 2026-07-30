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
from . import containment
from .cancellation import contain_tree, job_name_for_binding
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
    job_name: str = ""
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
            "job_name": self.job_name,
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

    # 3. Create the process already inside a kernel job. It is started
    #    suspended and assigned before its first instruction, so there is no
    #    window in which it can spawn a child outside containment.
    job = None
    try:
        if containment.IS_WINDOWS:
            process, job = containment.launch_contained(
                [identity.path, *request.argv],
                job_name=job_name_for_binding(request.session_binding_id),
                cwd=request.working_directory or None,
                env=dict(sanitised.environment),
                stdin=(
                    subprocess.PIPE
                    if request.stdin_text is not None
                    else subprocess.DEVNULL
                ),
                popen=popen,
            )
        else:
            process = popen(
                [identity.path, *request.argv],
                cwd=request.working_directory or None,
                env=dict(sanitised.environment),
                stdin=(
                    subprocess.PIPE
                    if request.stdin_text is not None
                    else subprocess.DEVNULL
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **process_group_popen_kwargs(),
            )
    except containment.ContainmentUnavailable as exc:
        # Fail closed: launch_contained already killed anything it created.
        return AttachmentResult(
            disposition=AttachmentDisposition.LAUNCH_FAILED,
            environment_evidence=sanitised.evidence,
            executable_identity=identity,
            detail=f"kernel containment unavailable: {exc}",
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
        contained = _contain(job, root_pid, "",
            "provider root start identity could not be captured")
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
            containment=contained,
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
            observation_source=(
                f"stand_in_launch:job={job_name_for_binding(request.session_binding_id)}"
                if job is not None
                else "stand_in_launch"
            ),
        )
    except Exception as exc:
        contained = _contain(job, root_pid, root_identity,
            "provider root observation could not be persisted")
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
            containment=contained,
            detail=f"root observation not persisted: {exc}",
        )

    # 6. Let the tree establish itself, then record the descendants that exist.
    #    Descendants discovered later are still terminated at cancellation: this
    #    snapshot is evidence, not the authoritative owned set.
    if request.descendant_settle_seconds > 0:
        time.sleep(request.descendant_settle_seconds)
    try:
        descendants = record_descendants(
            store,
            session_binding_id=request.session_binding_id,
            task_id=request.task_id,
            run_id=request.run_id,
            root_pid=root_pid,
        )
    except Exception as exc:
        # Enumeration, identity capture, or persistence failed after the root
        # was recorded. Attachment must not report healthy while a tree Soma
        # cannot fully name is still running.
        contained = _contain(
            job, root_pid, root_identity, f"descendant attachment failed: {exc}"
        )
        _mark_unverified(
            store, request.session_binding_id, f"descendant attachment failed: {exc}"
        )
        if job is not None:
            job.close()
        return AttachmentResult(
            disposition=AttachmentDisposition.CONTAINED_UNVERIFIED,
            root_pid=root_pid,
            root_identity=root_identity,
            environment_evidence=sanitised.evidence,
            executable_identity=identity,
            containment=contained,
            detail=f"descendant attachment failed: {exc}",
        )

    if job is not None:
        # Hold the handle: a named job stops being openable the moment its last
        # handle closes, so releasing it here would discard containment.
        containment.register_job(job)
    return AttachmentResult(
        disposition=AttachmentDisposition.ATTACHED,
        root_pid=root_pid,
        root_identity=root_identity,
        descendant_count=len(descendants),
        environment_evidence=sanitised.evidence,
        executable_identity=identity,
        job_name=job_name_for_binding(request.session_binding_id) if job else "",
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


def _contain(job, root_pid: int, root_identity: str, reason: str) -> dict:
    """Contain everything created, preferring the kernel job over PID walking."""
    result: dict = {"reason": reason}
    if job is not None:
        try:
            job.terminate()
            remaining = job.assigned_pids()
            result.update(
                {
                    "mechanism": "job_object",
                    "contained": not remaining,
                    "job_assigned_pids": list(remaining),
                }
            )
        except containment.ContainmentUnavailable as exc:
            result.update({"mechanism": "job_object", "contained": False,
                           "error": str(exc)})
        finally:
            job.close()
        if result.get("contained"):
            return result
    fallback = contain_tree(
        root_pid=root_pid, root_identity=root_identity, recorded=(), reason=reason
    )
    fallback["mechanism"] = "process_tree_fallback"
    fallback["job"] = result
    return fallback


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
