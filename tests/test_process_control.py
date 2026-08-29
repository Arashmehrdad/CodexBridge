from __future__ import annotations

import json
import os
import signal
import sys
from types import SimpleNamespace

import pytest

import soma.process_control as process_control


def test_process_group_popen_kwargs_are_platform_specific(monkeypatch) -> None:
    monkeypatch.setattr(process_control, "_is_windows", lambda: False)
    assert process_control.process_group_popen_kwargs() == {"start_new_session": True}

    monkeypatch.setattr(process_control, "_is_windows", lambda: True)
    result = process_control.process_group_popen_kwargs()
    assert result["creationflags"] == int(
        getattr(process_control.subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    )
    assert result["startupinfo"].dwFlags & int(
        getattr(process_control.subprocess, "STARTF_USESHOWWINDOW", 1)
    )
    assert result["startupinfo"].wShowWindow == int(
        getattr(process_control.subprocess, "SW_HIDE", 0)
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows console inheritance contract")
def test_hidden_console_is_inherited_by_console_descendant() -> None:
    child_code = (
        "import ctypes; "
        "print(int(ctypes.windll.kernel32.GetConsoleWindow()))"
    )
    root_code = (
        "import ctypes,json,subprocess,sys; "
        "root=int(ctypes.windll.kernel32.GetConsoleWindow()); "
        f"child=int(subprocess.check_output([sys.executable,'-c',{child_code!r}], "
        "text=True).strip()); "
        "print(json.dumps({'root':root,'child':child}))"
    )
    completed = process_control.subprocess.run(
        [sys.executable, "-c", root_code],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
        **process_control.process_group_popen_kwargs(),
    )
    handles = json.loads(completed.stdout.strip())
    assert handles["root"] != 0
    assert handles["child"] == handles["root"]


def test_process_identity_matching_is_exact(monkeypatch) -> None:
    monkeypatch.setattr(
        process_control, "process_identity", lambda pid: f"{pid}:test:1"
    )

    assert process_control.process_matches_identity(123, "123:test:1") is True
    assert process_control.process_matches_identity(123, "123:test:2") is False
    assert process_control.process_matches_identity(123, "") is False


def test_current_process_identity_is_stable_when_supported() -> None:
    identity = process_control.process_identity(os.getpid())
    if not identity:
        pytest.skip("Process-start identity is unavailable on this platform")

    assert process_control.process_matches_identity(os.getpid(), identity) is True
    assert process_control.process_matches_identity(os.getpid(), identity + "x") is False


def test_terminate_process_tree_returns_already_stopped(monkeypatch) -> None:
    monkeypatch.setattr(process_control, "process_is_running", lambda _pid: False)

    result = process_control.terminate_process_tree(123)

    assert result["terminated"] is True
    assert result["termination_attempted"] is False
    assert result["method"] == "already_stopped"


def test_windows_termination_uses_taskkill_tree_and_confirms_exit(monkeypatch) -> None:
    states = iter([True, False, False])
    captured: dict[str, object] = {}
    monkeypatch.setattr(process_control, "_is_windows", lambda: True)
    monkeypatch.setattr(
        process_control,
        "process_is_running",
        lambda _pid: next(states, False),
    )

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="SUCCESS", stderr="")

    monkeypatch.setattr(process_control.subprocess, "run", fake_run)

    result = process_control.terminate_process_tree(321, grace_seconds=0.1)

    assert captured["argv"] == ["taskkill", "/PID", "321", "/T", "/F"]
    assert result["terminated"] is True
    assert result["forced"] is True
    assert result["method"] == "taskkill_tree"


def test_posix_termination_targets_independent_process_group(monkeypatch) -> None:
    states = iter([True, True, False, False])
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(process_control, "_is_windows", lambda: False)
    monkeypatch.setattr(
        process_control,
        "process_is_running",
        lambda _pid: next(states, False),
    )
    monkeypatch.setattr(process_control.os, "getpgrp", lambda: 10, raising=False)
    monkeypatch.setattr(
        process_control.os, "getpgid", lambda _pid: 777, raising=False
    )
    monkeypatch.setattr(
        process_control.os,
        "killpg",
        lambda group, sig: signals.append((group, sig)),
        raising=False,
    )
    monkeypatch.setattr(process_control.time, "sleep", lambda _seconds: None)

    result = process_control.terminate_process_tree(777, grace_seconds=0.1)

    assert signals == [(777, signal.SIGTERM)]
    assert result["terminated"] is True
    assert result["forced"] is False
    assert result["method"] == "process_group"
