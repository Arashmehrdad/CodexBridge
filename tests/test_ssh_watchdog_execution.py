from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codexbridge.remote_controller_state import build_remote_controller_state_contract
from codexbridge.remote_resource_enforcement import RemoteMemoryPolicy
from codexbridge.ssh_watchdog import _start_controller_source

pytestmark = pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups and /proc")


def _run_controller(
    tmp_path: Path,
    *,
    child_source: str,
    policy: RemoteMemoryPolicy,
    force_identity_mismatch: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object], dict[str, object]]:
    contract = build_remote_controller_state_contract(
        run_id="execution-test",
        host_id="local-posix",
        command_id="python-child",
        lease_generation=1,
        remote_argv=[sys.executable, "-c", child_source],
        timeout_seconds=30,
        memory_policy=policy,
    )
    state_dir = tmp_path / "remote-state"
    contract["remote"] = dict(contract["remote"])
    contract["remote"].update(
        {
            "state_dir": str(state_dir),
            "state_path": str(state_dir / "state.json"),
            "input_path": str(state_dir / "input.json"),
            "stdout_path": str(state_dir / "stdout.bin"),
            "stderr_path": str(state_dir / "stderr.bin"),
            "result_path": str(state_dir / "result.json"),
        }
    )
    source = _start_controller_source(
        contract["remote_argv"] if "remote_argv" in contract else [sys.executable, "-c", child_source],
        "START=",
        "EXIT=",
        contract,
    )
    memory_sample_path = tmp_path / "memory.current"
    memory_sample_path.write_text("1\n", encoding="utf-8")
    source = source.replace(
        '"/sys/fs/cgroup/memory.current"', repr(str(memory_sample_path))
    )
    source = source.replace(
        '"/sys/fs/cgroup/memory/memory.usage_in_bytes"',
        repr(str(memory_sample_path)),
    )
    source = source.replace(
        "next_heartbeat=time.monotonic()+5.0",
        "next_heartbeat=time.monotonic()+.1",
    )
    source = source.replace("next_heartbeat=now_mono+5.0", "next_heartbeat=now_mono+.05")
    source = source.replace("deadline=time.monotonic()+5", "deadline=time.monotonic()+.25")
    source = source.replace("deadline=time.monotonic()+2", "deadline=time.monotonic()+.25")
    if force_identity_mismatch:
        source = source.replace(
            "def identity_matches():\n try:\n  value=ident(meta[\"pid\"])",
            "def identity_matches():\n return False\n try:\n  value=ident(meta[\"pid\"])",
        )
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    result = json.loads((state_dir / "result.json").read_text(encoding="utf-8"))
    return completed, state, result


def test_generated_controller_gracefully_terminates_process_group(tmp_path: Path) -> None:
    completed, state, result = _run_controller(
        tmp_path,
        child_source="import signal,sys,time; signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); time.sleep(30)",
        policy=RemoteMemoryPolicy(conservative_bytes=None, graceful_bytes=1, hard_bytes=None),
    )

    evidence = result["resource_enforcement"]
    assert completed.returncode != 0
    assert evidence["decision"]["action"] == "graceful_terminate"
    assert evidence["identity_verified"] is True
    assert evidence["term_sent"] is True
    assert evidence["kill_sent"] is False
    assert evidence["terminated"] is True
    assert evidence["outcome"] == "terminated"
    assert state["execution"]["resource_enforcement"] == evidence


def test_generated_controller_escalates_when_sigterm_is_ignored(tmp_path: Path) -> None:
    _, _, result = _run_controller(
        tmp_path,
        child_source="import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        policy=RemoteMemoryPolicy(conservative_bytes=None, graceful_bytes=1, hard_bytes=None),
    )

    evidence = result["resource_enforcement"]
    assert evidence["decision"]["action"] == "graceful_terminate"
    assert evidence["term_sent"] is True
    assert evidence["kill_sent"] is True
    assert evidence["terminated"] is True


def test_generated_controller_hard_terminates_without_sigterm(tmp_path: Path) -> None:
    _, _, result = _run_controller(
        tmp_path,
        child_source="import time; time.sleep(30)",
        policy=RemoteMemoryPolicy(conservative_bytes=None, graceful_bytes=None, hard_bytes=1),
    )

    evidence = result["resource_enforcement"]
    assert evidence["decision"]["action"] == "hard_terminate"
    assert evidence["term_sent"] is False
    assert evidence["kill_sent"] is True
    assert evidence["terminated"] is True


def test_generated_controller_refuses_identity_mismatch(tmp_path: Path) -> None:
    completed, state, result = _run_controller(
        tmp_path,
        child_source="import time; time.sleep(.2)",
        policy=RemoteMemoryPolicy(conservative_bytes=None, graceful_bytes=1, hard_bytes=None),
        force_identity_mismatch=True,
    )

    evidence = result["resource_enforcement"]
    assert completed.returncode != 0
    assert evidence["identity_verified"] is False
    assert evidence["term_sent"] is False
    assert evidence["kill_sent"] is False
    assert evidence["terminated"] is False
    assert evidence["outcome"] == "termination_unconfirmed"
    assert evidence["error"] == "remote process identity changed before resource enforcement"
    assert state["execution"]["resource_enforcement"] == evidence
