"""Kernel-backed owned-process containment.

Parent-link enumeration cannot prove zero owned descendants: a root can exit
before a late descendant is observed, the descendant is reparented, and a
root-based sweep then finds nothing while the work continues. That is the exact
hole the acceptance audit reproduced.

A Windows Job Object closes it. Membership is kernel-maintained, survives
reparenting and root exit, and can be *queried* after termination, so
"zero owned processes" becomes an assertion about kernel state rather than an
inference from a process table.

Two design points worth stating:

- The root is created suspended and assigned to the job **before** its first
  instruction runs, so there is no window in which it can spawn an uncontained
  child. If assignment or resume fails, the process is killed rather than
  released.
- ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` is set before the suspended root is
  resumed. This is the owner-approved crash policy: if Soma dies, the last job
  handle closes and the kernel stops the whole worker tree. Company, task, run,
  session and interaction state are durable, worker processes are disposable,
  and exact provider-native session resume is the recovery mechanism. An
  uncontrolled orphan mutating a workspace with no controller is the outcome
  this forbids.

A consequence worth stating plainly: **closing the job handle kills the tree.**
``release_job`` is therefore a termination, not a cleanup.

Restart adoption of a still-running local worker is deliberately out of scope.
A named job also cannot be reopened once its last handle closes -- measured,
returning ``ERROR_FILE_NOT_FOUND`` -- so naming buys no restart survival either
way. The handle is held in a process-local registry for the session's lifetime.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Final

from ..process_control import windows_hidden_console_popen_kwargs


IS_WINDOWS: Final[bool] = os.name == "nt"

JOB_OBJECT_ALL_ACCESS: Final[int] = 0x1F001F
JOB_OBJECT_BASIC_PROCESS_ID_LIST: Final[int] = 3
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: Final[int] = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Final[int] = 0x00002000
PROCESS_SET_QUOTA: Final[int] = 0x0100
PROCESS_TERMINATE: Final[int] = 0x0001
CREATE_SUSPENDED: Final[int] = 0x00000004
CREATE_NEW_CONSOLE: Final[int] = 0x00000010
THREAD_SUSPEND_RESUME: Final[int] = 0x0002
TH32CS_SNAPTHREAD: Final[int] = 0x00000004
MAX_TRACKED_PROCESSES: Final[int] = 1024


class ContainmentUnavailable(RuntimeError):
    """Kernel containment could not be established. Callers must fail closed."""


if IS_WINDOWS:  # pragma: no branch - platform guard

    class _JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * MAX_TRACKED_PROCESSES),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", ctypes.c_long),
            ("tpDeltaPri", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
        ]


def _kernel32():
    if not IS_WINDOWS:
        raise ContainmentUnavailable("Job Object containment requires Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _resume_process_threads(pid: int) -> int:
    """Resume every thread of a suspended process. Returns the count resumed."""
    kernel32 = _kernel32()
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snapshot == -1 or snapshot == 0:
        raise ContainmentUnavailable("could not snapshot threads to resume the root")
    resumed = 0
    try:
        entry = _THREADENTRY32()
        entry.dwSize = ctypes.sizeof(_THREADENTRY32)
        if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
            raise ContainmentUnavailable("thread enumeration returned nothing")
        while True:
            if entry.th32OwnerProcessID == pid:
                handle = kernel32.OpenThread(
                    THREAD_SUSPEND_RESUME, False, entry.th32ThreadID
                )
                if handle:
                    try:
                        if kernel32.ResumeThread(handle) != 0xFFFFFFFF:
                            resumed += 1
                    finally:
                        kernel32.CloseHandle(handle)
            if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    if resumed == 0:
        raise ContainmentUnavailable(f"no thread of pid {pid} could be resumed")
    return resumed


@dataclass
class JobContainment:
    """A named kernel job that owns one process tree."""

    name: str
    _handle: int = 0
    _closed: bool = False

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def create(cls, name: str) -> "JobContainment":
        kernel32 = _kernel32()
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        handle = kernel32.CreateJobObjectW(None, name)
        if not handle:
            raise ContainmentUnavailable(
                f"CreateJobObject failed: {ctypes.get_last_error()}"
            )
        job = cls(name=name, _handle=int(handle))
        job.set_kill_on_close()
        return job

    def set_kill_on_close(self) -> None:
        """Make a lost controller fatal to the worker tree, not to correctness.

        Applied at creation, before the suspended root is resumed, so there is
        no interval in which a crash could strand a running descendant.
        """
        kernel32 = _kernel32()
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            wintypes.HANDLE(self._handle),
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            raise ContainmentUnavailable(
                "could not set KILL_ON_JOB_CLOSE: "
                f"{ctypes.get_last_error()}"
            )

    @classmethod
    def open_existing(cls, name: str) -> "JobContainment":
        """Open a still-existing named job while another handle keeps it alive.

        This does not provide restart adoption after the last handle closes;
        KILL_ON_JOB_CLOSE deliberately terminates the owned tree at that point.
        """
        kernel32 = _kernel32()
        kernel32.OpenJobObjectW.restype = wintypes.HANDLE
        handle = kernel32.OpenJobObjectW(JOB_OBJECT_ALL_ACCESS, False, name)
        if not handle:
            raise ContainmentUnavailable(
                f"job {name!r} could not be reopened: {ctypes.get_last_error()}"
            )
        return cls(name=name, _handle=int(handle))

    def close(self) -> None:
        if self._handle and not self._closed:
            _kernel32().CloseHandle(wintypes.HANDLE(self._handle))
            self._closed = True

    def __enter__(self) -> "JobContainment":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # -- membership ----------------------------------------------------------

    def assign_pid(self, pid: int) -> None:
        kernel32 = _kernel32()
        handle = kernel32.OpenProcess(
            PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid)
        )
        if not handle:
            raise ContainmentUnavailable(
                f"could not open pid {pid} for assignment: {ctypes.get_last_error()}"
            )
        try:
            if not kernel32.AssignProcessToJobObject(
                wintypes.HANDLE(self._handle), handle
            ):
                raise ContainmentUnavailable(
                    f"AssignProcessToJobObject failed for pid {pid}: "
                    f"{ctypes.get_last_error()}"
                )
        finally:
            kernel32.CloseHandle(handle)

    def assigned_pids(self) -> tuple[int, ...]:
        """Query kernel membership. This is the zero-descendant proof."""
        kernel32 = _kernel32()
        payload = _JOBOBJECT_BASIC_PROCESS_ID_LIST()
        payload.NumberOfAssignedProcesses = MAX_TRACKED_PROCESSES
        returned = wintypes.DWORD(0)
        ok = kernel32.QueryInformationJobObject(
            wintypes.HANDLE(self._handle),
            JOB_OBJECT_BASIC_PROCESS_ID_LIST,
            ctypes.byref(payload),
            ctypes.sizeof(payload),
            ctypes.byref(returned),
        )
        if not ok:
            # ERROR_MORE_DATA (234) means the list was truncated, which is still
            # a non-empty answer; anything else is an unusable query.
            if ctypes.get_last_error() != 234:
                raise ContainmentUnavailable(
                    f"QueryInformationJobObject failed: {ctypes.get_last_error()}"
                )
        count = int(payload.NumberOfProcessIdsInList)
        return tuple(int(payload.ProcessIdList[i]) for i in range(count))

    def is_empty(self) -> bool:
        return not self.assigned_pids()

    def terminate(self, exit_code: int = 1) -> None:
        kernel32 = _kernel32()
        if not kernel32.TerminateJobObject(wintypes.HANDLE(self._handle), exit_code):
            raise ContainmentUnavailable(
                f"TerminateJobObject failed: {ctypes.get_last_error()}"
            )


#: Live job handles, keyed by job name. The handle must stay open for the job to
#: remain openable at all, so ownership of it lives here rather than with the
#: caller. A Soma restart empties this, which is exactly the reduced-proof case
#: cancellation reports.
_ACTIVE_JOBS: dict[str, JobContainment] = {}


def register_job(job: JobContainment) -> None:
    previous = _ACTIVE_JOBS.get(job.name)
    if previous is not None and previous is not job:
        previous.close()
    _ACTIVE_JOBS[job.name] = job


def active_job(name: str) -> JobContainment | None:
    return _ACTIVE_JOBS.get(name)


def release_job(name: str) -> None:
    job = _ACTIVE_JOBS.pop(name, None)
    if job is not None:
        job.close()


def launch_contained(
    argv: list[str],
    *,
    job_name: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    stdin: Any = subprocess.DEVNULL,
    stdout: Any = subprocess.DEVNULL,
    stderr: Any = subprocess.DEVNULL,
    popen=subprocess.Popen,
) -> tuple[subprocess.Popen, JobContainment]:
    """Create a process already inside its job, with no uncontained window.

    The root is started suspended, assigned, then resumed. If assignment or
    resume fails the process is killed: releasing an unassignable process would
    hand back exactly the uncontained tree this exists to prevent.
    """
    job = JobContainment.create(job_name)
    try:
        process = popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            **windows_hidden_console_popen_kwargs(
                extra_creationflags=CREATE_SUSPENDED
            ),
        )
    except BaseException:
        job.close()
        raise

    try:
        job.assign_pid(process.pid)
        _resume_process_threads(process.pid)
    except BaseException:
        try:
            process.kill()
        except OSError:
            pass
        try:
            job.terminate()
        except ContainmentUnavailable:
            pass
        job.close()
        raise
    return process, job
