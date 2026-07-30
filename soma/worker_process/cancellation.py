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
from typing import Any, Iterable, Sequence

from ..process_control import (
    list_descendants,
    process_identity,
    process_is_running,
    recorded_process_is_absent,
    terminate_process_tree,
)


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

    @property
    def zero_owned_descendants(self) -> bool:
        """True only when every recorded process is provably gone."""
        return (
            self.disposition is not CancellationDisposition.UNCERTAIN
            and not self.surviving_pids
            and not self.late_descendant_pids
        )

    @property
    def may_publish_terminal_cancellation(self) -> bool:
        """The single question a caller should ask before a terminal transition."""
        return (
            self.disposition
            in {
                CancellationDisposition.CONFIRMED,
                CancellationDisposition.NOTHING_RECORDED,
            }
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

    live_identity = process_identity(pid)
    if recorded_identity and live_identity and live_identity != recorded_identity:
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


def cancel_owned_tree(
    store,
    session_binding_id: str,
    *,
    grace_seconds: float = 3.0,
) -> CancellationProof:
    """Terminate one provider session's recorded tree and prove it is gone.

    Replay after a successful cancellation is safe and returns ``CONFIRMED``
    again: the recorded observations are immutable evidence, and re-verifying
    absence is idempotent.
    """
    recorded = list(store.list_child_processes(session_binding_id))
    if not recorded:
        return CancellationProof(
            disposition=CancellationDisposition.NOTHING_RECORDED,
            detail="no provider process was ever recorded for this binding",
        )

    roots = [item for item in recorded if item.role.value == "provider_root"]
    descendants = [item for item in recorded if item.role.value != "provider_root"]

    # Prove the owned set *before* terminating. A descendant spawned since
    # attachment is still ours, so live enumeration is unioned with the
    # recorded rows rather than trusted alone or ignored.
    live_before: list[int] = []
    for root in roots:
        if process_is_running(root.pid):
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

    # Final sweep: a descendant that appeared during termination, or one the
    # tree kill missed, must disprove the claim even if every record looks good.
    late: list[int] = []
    for root in roots:
        if not process_is_running(root.pid):
            continue
        try:
            late.extend(list_descendants(root.pid))
        except OSError:
            late.append(root.pid)

    if surviving or late:
        return CancellationProof(
            disposition=CancellationDisposition.UNCERTAIN,
            records=records,
            surviving_pids=surviving,
            late_descendant_pids=tuple(sorted(set(late))),
            detail=(
                "cancellation is unproven: recorded or descendant processes "
                "remain after termination"
            ),
        )

    return CancellationProof(
        disposition=CancellationDisposition.CONFIRMED,
        records=records,
        detail="every recorded process is provably absent",
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
