from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


def _is_windows() -> bool:
    return os.name == "nt"


def process_group_popen_kwargs() -> dict[str, Any]:
    """Return platform-specific Popen options for an independently terminable tree."""
    if _is_windows():
        return {
            "creationflags": int(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        }
    return {"start_new_session": True}


def process_is_running(pid: int | None) -> bool:
    if pid is None or int(pid) <= 0:
        return False
    pid = int(pid)
    if _is_windows():
        try:
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, pid
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                ):
                    return False
                return int(exit_code.value) == still_active
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return False


def process_identity(pid: int | None) -> str:
    """Return a stable process-start identity for PID reuse protection."""
    normalized_pid = int(pid or 0)
    if normalized_pid <= 0 or not process_is_running(normalized_pid):
        return ""
    if _is_windows():
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, normalized_pid
            )
            if not handle:
                return ""
            try:
                creation = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel = wintypes.FILETIME()
                user = wintypes.FILETIME()
                if not ctypes.windll.kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                ):
                    return ""
                marker = (int(creation.dwHighDateTime) << 32) | int(
                    creation.dwLowDateTime
                )
                return f"{normalized_pid}:windows:{marker}"
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return ""
    try:
        stat_text = Path(f"/proc/{normalized_pid}/stat").read_text(encoding="utf-8")
        fields_after_comm = stat_text.rsplit(") ", 1)[1].split()
        start_ticks = fields_after_comm[19]
        return f"{normalized_pid}:proc:{start_ticks}"
    except Exception:
        return ""


def process_matches_identity(pid: int | None, expected_identity: str | None) -> bool:
    expected = str(expected_identity or "")
    return bool(expected and process_identity(pid) == expected)


def recorded_process_is_absent(pid: int | None, expected_identity: str) -> bool:
    """True when the exact recorded process is provably gone.

    A PID that is running again under a *different* start identity is a
    different process, so the recorded one is absent. This is the check that
    makes zero-descendant proof meaningful under PID reuse: presence of the
    number is not presence of the process.
    """
    normalized = int(pid or 0)
    if normalized <= 0:
        return True
    if not process_is_running(normalized):
        return True
    if not expected_identity:
        # Without a recorded identity nothing can be proven either way, so the
        # conservative answer is "not provably absent".
        return False
    return process_identity(normalized) != expected_identity


def _windows_parent_table() -> dict[int, int]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId | "
            "ConvertTo-Csv -NoTypeInformation",
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError(
            f"process enumeration failed: {(completed.stderr or '').strip()[:200]}"
        )
    table: dict[int, int] = {}
    for line in (completed.stdout or "").splitlines()[1:]:
        parts = [item.strip().strip('"') for item in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            table[int(parts[0])] = int(parts[1])
        except ValueError:
            continue
    return table


def _posix_parent_table() -> dict[int, int]:
    table: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat_text = (entry / "stat").read_text(encoding="utf-8")
            fields = stat_text.rsplit(") ", 1)[1].split()
            table[int(entry.name)] = int(fields[1])
        except Exception:
            continue
    return table


def process_parent_table() -> dict[int, int]:
    """Return a ``{pid: parent_pid}`` snapshot of every visible process."""
    if _is_windows():
        return _windows_parent_table()
    return _posix_parent_table()


def list_descendants(
    root_pid: int | None, *, parent_table: dict[int, int] | None = None
) -> list[int]:
    """Return every live descendant of ``root_pid``, nearest first.

    The snapshot is taken from one parent table so the walk cannot see a tree
    mutating underneath it. A cycle in reported parentage -- which a PID-reuse
    race can produce -- is broken by the visited set rather than hanging.
    """
    root = int(root_pid or 0)
    if root <= 0:
        return []
    table = process_parent_table() if parent_table is None else parent_table
    children: dict[int, list[int]] = {}
    for pid, parent in table.items():
        if pid != parent:
            children.setdefault(parent, []).append(pid)
    ordered: list[int] = []
    visited: set[int] = {root}
    frontier = [root]
    while frontier:
        nxt: list[int] = []
        for pid in frontier:
            for child in sorted(children.get(pid, ())):
                if child in visited:
                    continue
                visited.add(child)
                ordered.append(child)
                nxt.append(child)
        frontier = nxt
    return ordered


def _wait_until_stopped(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while process_is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not process_is_running(pid)


def _terminate_windows(pid: int, grace_seconds: float) -> dict[str, Any]:
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        text=True,
        capture_output=True,
        timeout=max(5.0, grace_seconds + 2.0),
        check=False,
    )
    stopped = _wait_until_stopped(pid, grace_seconds)
    error = ""
    if not stopped:
        detail = (result.stderr or result.stdout or "taskkill did not stop the process").strip()
        error = detail[-1000:]
    return {
        "pid": pid,
        "method": "taskkill_tree",
        "termination_attempted": True,
        "forced": True,
        "exit_code": int(result.returncode),
        "terminated": stopped,
        "error": error,
    }


def _terminate_posix(pid: int, grace_seconds: float) -> dict[str, Any]:
    current_group = os.getpgrp()
    process_group = os.getpgid(pid)
    use_group = process_group > 0 and process_group != current_group
    method = "process_group" if use_group else "process"
    terminate = (
        (lambda sig: os.killpg(process_group, sig))
        if use_group
        else (lambda sig: os.kill(pid, sig))
    )
    terminate(signal.SIGTERM)
    stopped = _wait_until_stopped(pid, grace_seconds)
    forced = False
    if not stopped:
        forced = True
        terminate(signal.SIGKILL)
        stopped = _wait_until_stopped(pid, max(1.0, grace_seconds))
    return {
        "pid": pid,
        "method": method,
        "termination_attempted": True,
        "forced": forced,
        "exit_code": 0 if stopped else 1,
        "terminated": stopped,
        "error": "" if stopped else "Process remained active after termination attempts",
    }


def terminate_process_tree(
    pid: int | None, *, grace_seconds: float = 3.0
) -> dict[str, Any]:
    """Terminate one process tree and confirm that the root PID stopped."""
    normalized_pid = int(pid or 0)
    if normalized_pid <= 0:
        return {
            "pid": normalized_pid,
            "method": "none",
            "termination_attempted": False,
            "forced": False,
            "exit_code": 0,
            "terminated": True,
            "error": "",
        }
    if not process_is_running(normalized_pid):
        return {
            "pid": normalized_pid,
            "method": "already_stopped",
            "termination_attempted": False,
            "forced": False,
            "exit_code": 0,
            "terminated": True,
            "error": "",
        }
    try:
        if _is_windows():
            return _terminate_windows(normalized_pid, grace_seconds)
        return _terminate_posix(normalized_pid, grace_seconds)
    except Exception as exc:
        return {
            "pid": normalized_pid,
            "method": "taskkill_tree" if _is_windows() else "process_group",
            "termination_attempted": True,
            "forced": False,
            "exit_code": 1,
            "terminated": not process_is_running(normalized_pid),
            "error": str(exc),
        }
