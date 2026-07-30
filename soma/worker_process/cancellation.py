"""Owned-tree cancellation with zero-descendant proof.

The pilot measured the failure this closes: killing the agent root left 5 of 6
Claude processes and 2 of 5 Codex processes alive, including the child doing the
work. A worker that keeps mutating a workspace after Soma reports the task
cancelled is the worst outcome in the lane, so the verdict here is deliberately
*not* derived from the return code of the killing tool.

The rule: **cancellation is confirmed by verified absence, never by a successful
terminate call.** ``taskkill`` reporting success while a grandchild survives is
exactly the case that must fail, and it is tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Iterable, Sequence

from ..process_control import (
    list_descendants,
    process_identity,
    process_is_running,
    recorded_process_is_absent,
    terminate_process_tree,
)
from . import containment


class CancellationDisposition(str, Enum):
    """What Soma can prove about one cancellation attempt.

    Not a run state. ``RunStore``/``JobManager`` still decide whether the run
    becomes ``cancelled``; this only reports whether it is *safe* to.
    """

    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    NOTHING_RECORDED = "nothing_recorded"


@dataclass(frozen=True)
class TerminationRecord:
    pid: int
    recorded_identity: str
    role: str
    was_running: bool
    identity_mismatch: bool
    termination_attempted: bool
    method: str
    absent_after: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "role": self.role,
            "was_running": self.was_running,
            "identity_mismatch": self.identity_mismatch,
            "termination_attempted": self.termination_attempted,
            "method": self.method,
            "absent_after": self.absent_after,
            "error": self.error,
        }


@dataclass(frozen=True)
class CancellationProof:
    disposition: CancellationDisposition
    records: tuple[TerminationRecord, ...] = ()
    surviving_pids: tuple[int, ...] = ()
    late_descendant_pids: tuple[int, ...] = ()
    detail: str = ""
    #: Kernel job membership after termination. ``None`` means no job was
    #: available, which is weaker evidence and is reported as such.
    job_assigned_pids: tuple[int, ...] | None = None
    job_proof_available: bool = False
    #: Set only when the canonical run plane proved no process could have been
    #: created. An empty subordinate table can never establish this by itself.
    canonical_pre_launch_proven: bool = False

    @property
    def zero_owned_descendants(self) -> bool:
        """True only when every recorded process is provably gone."""
        if self.disposition is CancellationDisposition.UNCERTAIN:
            return False
        if self.job_proof_available and self.job_assigned_pids:
            return False
        return not self.surviving_pids and not self.late_descendant_pids

    @property
    def may_publish_terminal_cancellation(self) -> bool:
        """The single question a caller asks before a terminal transition.

        ``NOTHING_RECORDED`` no longer authorises publication on its own. An
        empty subordinate table can mean no process existed -- or that launch
        crossed a crash window and left one Soma never recorded. Only the
        canonical run plane can tell those apart, so it must say so explicitly.
        """
        if self.disposition is CancellationDisposition.NOTHING_RECORDED:
            return self.canonical_pre_launch_proven
        return (
            self.disposition is CancellationDisposition.CONFIRMED
            and self.zero_owned_descendants
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "zero_owned_descendants": self.zero_owned_descendants,
            "may_publish_terminal_cancellation": (
                self.may_publish_terminal_cancellation
            ),
            "records": [record.to_dict() for record in self.records],
            "surviving_pids": list(self.surviving_pids),
            "late_descendant_pids": list(self.late_descendant_pids),
            "detail": self.detail,
        }


def _terminate_one(
    pid: int, recorded_identity: str, role: str, grace_seconds: float
) -> TerminationRecord:
    running = process_is_running(pid)
    if not running:
        return TerminationRecord(
            pid=pid,
            recorded_identity=recorded_identity,
            role=role,
            was_running=False,
            identity_mismatch=False,
            termination_attempted=False,
            method="already_stopped",
            absent_after=True,
        )

    if not recorded_identity:
        # Owner-approved contract, 2026-07-30: a live PID without an exact
        # matching recorded start identity is never terminated. Soma cannot
        # prove it owns this process, so the run stays pending and the lock
        # stays held rather than Soma killing something that may not be its own.
        return TerminationRecord(
            pid=pid,
            recorded_identity=recorded_identity,
            role=role,
            was_running=True,
            identity_mismatch=False,
            termination_attempted=False,
            method="refused_no_recorded_identity",
            absent_after=False,
            error="live pid has no recorded start identity; ownership unproven",
        )

    live_identity = process_identity(pid)
    if not live_identity:
        # The process is alive but its identity cannot be read, so ownership is
        # unverifiable in the direction that matters. Refuse and stay uncertain.
        return TerminationRecord(
            pid=pid,
            recorded_identity=recorded_identity,
            role=role,
            was_running=True,
            identity_mismatch=False,
            termination_attempted=False,
            method="refused_unreadable_identity",
            absent_after=False,
            error="live start identity could not be read; ownership unproven",
        )

    if live_identity != recorded_identity:
        # PID reuse. The number is alive but the *process* Soma recorded is
        # gone, and the current occupant belongs to someone else. Terminating it
        # would be Soma killing a stranger, so this fails closed by refusing to
        # act while still counting the recorded process as absent.
        return TerminationRecord(
            pid=pid,
            recorded_identity=recorded_identity,
            role=role,
            was_running=True,
            identity_mismatch=True,
            termination_attempted=False,
            method="refused_pid_reuse",
            absent_after=True,
            error="live start identity differs from the recorded identity",
        )

    try:
        report = terminate_process_tree(pid, grace_seconds=grace_seconds)
        method = str(report.get("method") or "")
        error = str(report.get("error") or "")
    except Exception as exc:
        # A process-control error becomes uncertainty, never apparent success.
        method = "error"
        error = str(exc)

    return TerminationRecord(
        pid=pid,
        recorded_identity=recorded_identity,
        role=role,
        was_running=True,
        identity_mismatch=False,
        termination_attempted=True,
        method=method,
        # The verdict ignores the tool's own claim and re-checks reality.
        absent_after=recorded_process_is_absent(pid, recorded_identity),
        error=error[:500],
    )


#: Marker written into ``observation_source`` when a launch established kernel
#: containment, so cancellation knows whether to expect a job at all.
JOB_MARKER: Final[str] = "job=" 


def job_name_for_binding(session_binding_id: str) -> str:
    """Deterministic job name, so containment survives a Soma restart.

    Derived from the binding rather than stored in a new column: the name must
    be recoverable by a process that has lost every handle, and the binding id
    is already durable.
    """
    return f"Local\\soma-worker-{session_binding_id}"


def _terminate_job(session_binding_id: str) -> tuple[bool, tuple[int, ...] | None, str]:
    """Terminate the kernel job for a binding and query what remains.

    Returns ``(proof_available, assigned_pids_after, detail)``. A job that
    cannot be opened is not a failure: it means no contained launch happened,
    or the job was already destroyed because every member exited.
    """
    if not containment.IS_WINDOWS:
        return False, None, "kernel containment is unavailable off Windows"
    name = job_name_for_binding(session_binding_id)
    # A named job cannot be reopened after its last handle closes, so the live
    # handle in the process-local registry is the only way to reach it.
    job = containment.active_job(name)
    if job is None:
        return False, None, "no live kernel job handle for this binding"
    try:
        job.terminate()
    except containment.ContainmentUnavailable as exc:
        return False, None, f"job termination failed: {exc}"
    try:
        remaining = job.assigned_pids()
    except containment.ContainmentUnavailable as exc:
        return False, None, f"job membership query failed: {exc}"
    return True, remaining, ""


def cancel_owned_tree(
    store,
    session_binding_id: str,
    *,
    grace_seconds: float = 3.0,
    canonical_pre_launch_proven: bool = False,
) -> CancellationProof:
    """Terminate one provider session's recorded tree and prove it is gone.

    Replay after a successful cancellation is safe and returns ``CONFIRMED``
    again: the recorded observations are immutable evidence, and re-verifying
    absence is idempotent.
    """
    recorded = list(store.list_child_processes(session_binding_id))
    if not recorded:
        # Terminate the job anyway: an empty table with a live job is exactly
        # the crash window where a process was created but never recorded.
        job_available, job_remaining, _detail = _terminate_job(session_binding_id)
        return CancellationProof(
            disposition=CancellationDisposition.NOTHING_RECORDED,
            detail=(
                "no provider process was recorded; publication requires "
                "canonical pre-launch proof"
            ),
            job_assigned_pids=job_remaining,
            job_proof_available=job_available,
            canonical_pre_launch_proven=canonical_pre_launch_proven,
        )

    roots = [item for item in recorded if item.role.value == "provider_root"]
    # A launch that established kernel containment says so in its observation
    # source. If containment was expected but is no longer reachable -- a Soma
    # restart -- parent-table evidence alone may not confirm cancellation.
    job_was_expected = any(
        JOB_MARKER in (item.observation_source or "") for item in recorded
    )
    descendants = [item for item in recorded if item.role.value != "provider_root"]

    # Prove the ROOT IDENTITY before looking at the tree at all. Enumerating
    # descendants of a live PID whose identity has not been matched can inspect
    # -- and then target -- an unrelated process tree under PID reuse.
    live_before: list[int] = []
    for root in roots:
        if not process_is_running(root.pid):
            continue
        if not root.process_start_identity:
            return CancellationProof(
                disposition=CancellationDisposition.UNCERTAIN,
                detail=(
                    "recorded provider root has no start identity; refusing to "
                    "enumerate or terminate an unproven tree"
                ),
            )
        live_root_identity = process_identity(root.pid)
        if not live_root_identity:
            return CancellationProof(
                disposition=CancellationDisposition.UNCERTAIN,
                detail="live root start identity could not be read",
            )
        if live_root_identity != root.process_start_identity:
            # The recorded root is provably absent. The current occupant of the
            # number belongs to someone else, so its tree is not enumerated.
            continue
        try:
            live_before.extend(list_descendants(root.pid))
        except OSError:
            # Enumeration failure is uncertainty, not an empty owned set.
            return CancellationProof(
                disposition=CancellationDisposition.UNCERTAIN,
                detail=(
                    "owned descendant set could not be enumerated before "
                    "termination"
                ),
            )

    ordered: list[tuple[int, str, str]] = []
    seen: set[int] = set()
    # Deepest first: killing a parent first can reparent a grandchild and hide
    # it from the post-termination sweep.
    for item in reversed(descendants):
        if item.pid not in seen:
            seen.add(item.pid)
            ordered.append((item.pid, item.process_start_identity, item.role.value))
    for pid in live_before:
        if pid not in seen:
            seen.add(pid)
            ordered.append((pid, process_identity(pid), "late_descendant"))
    for item in roots:
        if item.pid not in seen:
            seen.add(item.pid)
            ordered.append((item.pid, item.process_start_identity, item.role.value))

    records = tuple(
        _terminate_one(pid, identity, role, grace_seconds)
        for pid, identity, role in ordered
    )

    surviving = tuple(
        record.pid for record in records if not record.absent_after
    )

    # Kernel-backed proof. Job membership survives reparenting and root exit,
    # so it answers the question a parent-table sweep cannot: is anything Soma
    # started still alive, wherever it has been reparented to?
    job_available, job_remaining, job_detail = _terminate_job(session_binding_id)

    # Parent-link sweep is retained as supporting evidence only. It is skipped
    # for a root whose identity did not match, since that tree is not ours.
    late: list[int] = []
    for root in roots:
        if not process_is_running(root.pid):
            continue
        if process_identity(root.pid) != root.process_start_identity:
            continue
        try:
            late.extend(list_descendants(root.pid))
        except OSError:
            late.append(root.pid)

    if job_was_expected and not job_available:
        return CancellationProof(
            disposition=CancellationDisposition.UNCERTAIN,
            records=records,
            surviving_pids=surviving,
            late_descendant_pids=tuple(sorted(set(late))),
            job_proof_available=False,
            detail=(
                "kernel containment was established at launch but is no longer "
                f"reachable ({job_detail}); parent-table evidence alone cannot "
                "prove zero owned descendants"
            ),
        )

    if surviving or late or (job_available and job_remaining):
        return CancellationProof(
            disposition=CancellationDisposition.UNCERTAIN,
            records=records,
            surviving_pids=surviving,
            late_descendant_pids=tuple(sorted(set(late))),
            job_assigned_pids=job_remaining,
            job_proof_available=job_available,
            detail=(
                "cancellation is unproven: recorded, descendant, or "
                "kernel-owned processes remain after termination"
            ),
        )

    return CancellationProof(
        disposition=CancellationDisposition.CONFIRMED,
        records=records,
        job_assigned_pids=job_remaining,
        job_proof_available=job_available,
        detail=(
            "kernel job is empty and every recorded process is absent"
            if job_available
            else f"every recorded process is absent ({job_detail})"
        ),
    )


def contain_tree(
    *,
    root_pid: int,
    root_identity: str,
    recorded: Iterable[tuple[int, str]] | Sequence[tuple[int, str]] = (),
    reason: str,
    grace_seconds: float = 3.0,
) -> dict[str, Any]:
    """Best-effort containment when a tree exists but cannot be attached.

    Used only on the launch path, where the alternative is a live process Soma
    cannot name. Containment is reported honestly: if it fails, the caller must
    surface uncertainty rather than treating the launch as cleanly aborted.
    """
    targets: list[tuple[int, str, str]] = [
        (pid, identity, "recorded") for pid, identity in recorded
    ]
    if process_is_running(root_pid):
        try:
            targets.extend(
                (pid, process_identity(pid), "descendant")
                for pid in list_descendants(root_pid)
            )
        except OSError:
            pass
    targets.append((root_pid, root_identity, "provider_root"))

    records = [
        _terminate_one(pid, identity, role, grace_seconds).to_dict()
        for pid, identity, role in targets
        if pid > 0
    ]
    contained = all(bool(record["absent_after"]) for record in records)
    return {
        "reason": reason,
        "contained": contained,
        "records": records,
    }
