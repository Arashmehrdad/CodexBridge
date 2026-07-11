from __future__ import annotations

import signal
from types import SimpleNamespace

import codexbridge.process_control as process_control


def test_process_group_popen_kwargs_are_platform_specific(monkeypatch) -> None:
    monkeypatch.setattr(process_control, "_is_windows", lambda: False)
    assert process_control.process_group_popen_kwargs() == {"start_new_session": True}

    monkeypatch.setattr(process_control, "_is_windows", lambda: True)
    monkeypatch.setattr(
        process_control.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False
    )
    assert process_control.process_group_popen_kwargs() == {"creationflags": 512}


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
