from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from codexbridge.config import load_config
from codexbridge.job_manager import JobManager
from codexbridge.parallel_groups import ParallelGroupStore


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell acceptance")


def _pwsh_path() -> Path:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "PowerShell"
        / "7"
        / "pwsh.exe",
        Path(os.environ.get("ProgramW6432", r"C:\Program Files"))
        / "PowerShell"
        / "7"
        / "pwsh.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    pytest.skip("PowerShell 7 executable is not installed at a configured absolute path")


def _manager(tmp_path: Path, *, max_concurrent: int | None = 2) -> JobManager:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "executable_profiles:",
                "  powershell:",
                "    profile_id: powershell",
                "    enabled: true",
                f'    executable_path: "{_pwsh_path().as_posix()}"',
                "    target: local",
                "    autonomy_profile: permissive",
                "    working_directory_policy: arbitrary",
                "    environment_policy: arbitrary",
                "    stdin_mode: bytes",
                "    stdout_mode: protected_artifact",
                "    stderr_mode: protected_artifact",
                "    unrestricted_argv: true",
                "    allow_no_timeout: true",
                "parallel_execution:",
                "  enabled: true",
                "  autonomy_profile: permissive",
                "  max_concurrent_powershell: "
                + ("null" if max_concurrent is None else str(max_concurrent)),
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return JobManager(load_config(config_path), config_path)


def _children(marker_dir: Path, count: int) -> list[dict]:
    children = []
    for index in range(count):
        marker = marker_dir / f"child-{index}.txt"
        script = (
            "Start-Sleep -Milliseconds 700; "
            "Set-Content -LiteralPath $env:CB_MARKER -Value $env:CB_VALUE -NoNewline; "
            "[Console]::Out.Write($env:CB_VALUE)"
        )
        children.append(
            {
                "idempotency_key": f"child-{index}",
                "argv": ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
                "environment": {"CB_MARKER": str(marker), "CB_VALUE": f"done-{index}"},
                "working_directory": str(marker_dir.parent),
                "timeout_seconds": 30,
            }
        )
    return children


def _wait_for_group(manager: JobManager, group_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last = manager.get_powershell_group(group_id)
    while time.monotonic() < deadline:
        last = manager.get_powershell_group(group_id)
        if last["status"] in {"completed", "failed", "cancelled", "partial"}:
            return last
        time.sleep(0.05)
    pytest.fail(f"PowerShell group did not finish: {last}")


def test_live_capped_fanout_refills_pending_children(tmp_path: Path) -> None:
    manager = _manager(tmp_path, max_concurrent=2)
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()

    started = manager.start_powershell_group("sample", _children(marker_dir, 3))

    assert len(started["launched_run_ids"]) == 2
    assert len(started["pending_run_ids"]) == 1
    pending_id = started["pending_run_ids"][0]
    store = ParallelGroupStore(manager.config.resolve_runs_dir())
    assert store.store.get_run(pending_id)["status"] == "pending"

    completed = _wait_for_group(manager, started["group_id"])

    assert completed["status"] == "completed"
    assert completed["result"]["status_counts"] == {"completed": 3}
    for index in range(3):
        assert (marker_dir / f"child-{index}.txt").read_text(encoding="utf-8") == f"done-{index}"


def test_live_uncapped_group_continues_successful_siblings_after_failure(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path, max_concurrent=None)
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    children = _children(marker_dir, 3)
    children[1]["argv"] = [
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "[Console]::Error.Write('expected failure'); exit 7",
    ]

    started = manager.start_powershell_group("sample", children)

    assert len(started["launched_run_ids"]) == 3
    assert started["pending_run_ids"] == []
    completed = _wait_for_group(manager, started["group_id"])
    assert completed["status"] == "failed"
    assert completed["result"]["status_counts"] == {"completed": 2, "failed": 1}
    assert (marker_dir / "child-0.txt").read_text(encoding="utf-8") == "done-0"
    assert not (marker_dir / "child-1.txt").exists()
    assert (marker_dir / "child-2.txt").read_text(encoding="utf-8") == "done-2"


def test_restart_reconciliation_adopts_active_child_without_duplicate_launch(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path, max_concurrent=1)
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    started = manager.start_powershell_group("sample", _children(marker_dir, 2))
    active_id = started["launched_run_ids"][0]
    pending_id = started["pending_run_ids"][0]
    store = ParallelGroupStore(manager.config.resolve_runs_dir())

    deadline = time.monotonic() + 10
    active_before = store.store.get_run(active_id)
    while time.monotonic() < deadline and active_before["status"] != "running":
        time.sleep(0.05)
        active_before = store.store.get_run(active_id)
    assert active_before["status"] == "running"
    assert active_before["worker_pid"]
    launch_attempts = active_before["launch_attempts"]
    worker_pid = active_before["worker_pid"]

    restarted = JobManager(load_config(manager.config_path), manager.config_path)
    restarted.reconcile_startup()

    active_after = store.store.get_run(active_id)
    assert active_after["worker_pid"] == worker_pid
    assert active_after["launch_attempts"] == launch_attempts
    assert store.store.get_run(pending_id)["status"] == "pending"

    completed = _wait_for_group(restarted, started["group_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["status_counts"] == {"completed": 2}
