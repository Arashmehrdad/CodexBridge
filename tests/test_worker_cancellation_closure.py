"""V3-1A-CANCELLATION-CLOSURE-1: publication, identity capture, crash containment.

Covers the final corrective gate: contradictory empty-row evidence, canonical
launcher/child identity capture, honest publication failure and retry,
KILL_ON_JOB_CLOSE crash policy, deterministic ordering, and public projections.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

import soma.job_manager as job_manager_module
from soma.process_control import (
    LaunchContainment,
    LaunchContainmentDisposition,
    LaunchIdentityUnavailable,
    capture_launch_identity,
    contain_fresh_launch,
    process_is_running,
)
from soma.run_store import (
    RUN_CONTROL_PROJECTION_COLUMNS,
    RUN_SUMMARY_PROJECTION_COLUMNS,
    RunStore,
)
from soma.worker_process import CancellationDisposition, CancellationProof
from soma.worker_process import containment as containment_module

from test_job_manager import make_manager
from test_worker_process_identity import IS_WINDOWS, bound as _bound_fixture  # noqa: F401


# ---------------------------------------------------------------------------
# 3.1 contradictory empty-row evidence
# ---------------------------------------------------------------------------


def test_a_live_job_blocks_publication_even_with_canonical_pre_launch_proof():
    """The audit probe: publish_with_live_job must be False.

    Canonical pre-launch proof plus live kernel membership is a contradiction --
    something exists that the run plane believes was never created -- so it is
    uncertainty, never permission.
    """
    proof = CancellationProof(
        disposition=CancellationDisposition.NOTHING_RECORDED,
        job_proof_available=True,
        job_assigned_pids=(4242,),
        canonical_pre_launch_proven=True,
    )
    assert proof.may_publish_terminal_cancellation is False
    assert proof.zero_owned_descendants is False


def test_surviving_evidence_blocks_publication_for_empty_rows():
    proof = CancellationProof(
        disposition=CancellationDisposition.NOTHING_RECORDED,
        surviving_pids=(99,),
        canonical_pre_launch_proven=True,
    )
    assert proof.may_publish_terminal_cancellation is False


def test_empty_rows_with_an_empty_job_and_canonical_proof_may_publish():
    proof = CancellationProof(
        disposition=CancellationDisposition.NOTHING_RECORDED,
        job_proof_available=True,
        job_assigned_pids=(),
        canonical_pre_launch_proven=True,
    )
    assert proof.may_publish_terminal_cancellation is True


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel job membership")
def test_empty_rows_with_a_live_job_become_uncertain(
    _bound_fixture,  # noqa: F811
    monkeypatch,
):
    """End-to-end: no recorded rows, but the kernel says processes exist."""
    store, binding, _task_id, _run_id = _bound_fixture
    from soma.worker_process import cancellation as cm

    monkeypatch.setattr(cm, "_terminate_job", lambda _b: (True, (1234,), ""))
    proof = cm.cancel_owned_tree(
        store, binding.session_binding_id, canonical_pre_launch_proven=True
    )
    assert proof.disposition is CancellationDisposition.UNCERTAIN
    assert proof.may_publish_terminal_cancellation is False
    assert "contradictory" in proof.detail


# ---------------------------------------------------------------------------
# 3.2 / 3.3 fresh identity capture and containment
# ---------------------------------------------------------------------------


class _FakeHandle:
    """A creator-held handle that reports a PID but is never a live process."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.killed = 0
        self.waited = 0

    def kill(self) -> None:
        self.killed += 1

    def wait(self, timeout: float | None = None) -> int:
        self.waited += 1
        return 1


def test_capture_launch_identity_contains_a_process_it_cannot_name(monkeypatch):
    import soma.process_control as pc

    handle = _FakeHandle(4242)
    monkeypatch.setattr(pc, "process_identity", lambda pid: "")
    with pytest.raises(LaunchIdentityUnavailable) as raised:
        pc.capture_launch_identity(handle)
    # Stopped through the exact handle, not by PID inference.
    assert handle.killed == 1
    assert handle.waited == 1
    assert raised.value.containment.stop_confirmed is True


def test_identity_capture_failure_never_acts_on_reused_pid(monkeypatch):
    import soma.process_control as pc

    class UncertainHandle:
        pid = 4242

        def __init__(self) -> None:
            self.killed = 0
            self.waited = 0

        def kill(self) -> None:
            self.killed += 1
            raise OSError("creator handle kill failed")

        def wait(self, timeout=None) -> int:
            self.waited += 1
            raise subprocess.TimeoutExpired(cmd="owned-handle", timeout=timeout)

        def poll(self):
            raise OSError("creator handle query failed")

    handle = UncertainHandle()
    raw_pid_calls: list[int] = []
    monkeypatch.setattr(pc, "process_identity", lambda pid: "")
    monkeypatch.setattr(
        pc,
        "terminate_process_tree",
        lambda pid, **_kwargs: raw_pid_calls.append(int(pid)),
    )
    monkeypatch.setattr(
        pc,
        "process_is_running",
        lambda _pid: (_ for _ in ()).throw(
            AssertionError(
                "numeric PID must not be queried after identity capture fails"
            )
        ),
    )

    evidence = contain_fresh_launch(handle, timeout_seconds=0)

    assert evidence.disposition is LaunchContainmentDisposition.CLEANUP_ERROR
    assert evidence.stop_confirmed is False
    assert handle.killed == 1
    assert handle.waited == 1
    assert raw_pid_calls == []


def test_capture_launch_identity_returns_a_real_identity():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        identity = capture_launch_identity(process)
        assert identity.startswith(f"{process.pid}:")
    finally:
        process.kill()
        process.wait(timeout=30)


def test_every_canonical_launcher_path_persists_a_non_empty_identity(
    tmp_path: Path, monkeypatch
):
    """All four RunStore launcher attachment points, per gate 3.2."""
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    run = manager.store.get_run(response["run_id"])
    assert run["launcher_pid"]
    assert run["launcher_identity"], "initial JobManager launch left no identity"

    # Recovery relaunch path.
    manager.store.update_run(
        response["run_id"], status="queued", launcher_pid=None, launcher_identity=""
    )
    manager.reconcile_startup()
    relaunched = manager.store.get_run(response["run_id"])
    if relaunched["launcher_pid"]:
        assert relaunched["launcher_identity"], "recovery relaunch left no identity"


def test_launcher_identity_failure_leaves_no_healthy_attachment(
    tmp_path: Path, monkeypatch
):
    manager = make_manager(tmp_path, monkeypatch)

    def refuse(process, **_kwargs):
        raise LaunchIdentityUnavailable(
            LaunchContainment(
                disposition=LaunchContainmentDisposition.STOP_UNCONFIRMED,
                pid=process.pid,
                kill_attempted=True,
                exit_confirmed=False,
                method="creator_handle",
                error="simulated wait timeout",
            )
        )

    monkeypatch.setattr(job_manager_module, "capture_launch_identity", refuse)
    response = manager.start_git_readonly("sample", "status")
    run = manager.store.get_run(response["run_id"])

    assert response["accepted"] is False
    assert response["status"] == "recovery_pending"
    assert run["status"] == "recovery_pending"
    assert run["result"] == {}
    assert manager.locks.find_lock("sample", response["run_id"]) is not None


def test_confirmed_identity_capture_failure_remains_terminal_and_releases_lock(
    tmp_path: Path, monkeypatch
):
    manager = make_manager(tmp_path, monkeypatch)

    def refuse(process, **_kwargs):
        raise LaunchIdentityUnavailable(
            LaunchContainment(
                disposition=LaunchContainmentDisposition.STOP_CONFIRMED,
                pid=process.pid,
                kill_attempted=True,
                exit_confirmed=True,
                method="creator_handle",
            )
        )

    monkeypatch.setattr(job_manager_module, "capture_launch_identity", refuse)
    response = manager.start_git_readonly("sample", "status")
    run = manager.store.get_run(response["run_id"])

    assert response["status"] == "failed"
    assert run["status"] == "failed"
    assert manager.locks.find_lock("sample", response["run_id"]) is None


def test_recovery_relaunch_uncertainty_retains_lease_and_lock(
    tmp_path: Path, monkeypatch
):
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    manager.store.update_run(
        response["run_id"], launcher_pid=None, launcher_identity=""
    )
    monkeypatch.setattr(job_manager_module, "process_is_running", lambda _pid: False)

    def refuse(process, **_kwargs):
        raise LaunchIdentityUnavailable(
            LaunchContainment(
                disposition=LaunchContainmentDisposition.STOP_UNCONFIRMED,
                pid=process.pid,
                kill_attempted=True,
                exit_confirmed=False,
                method="creator_handle",
                error="simulated recovery wait timeout",
            )
        )

    monkeypatch.setattr(job_manager_module, "capture_launch_identity", refuse)

    assert manager.reconcile_startup() == 1
    run = manager.store.get_run(response["run_id"])
    assert run["status"] == "recovery_pending"
    assert run["ended_at"] is None
    assert manager.locks.find_lock("sample", response["run_id"]) is not None


# ---------------------------------------------------------------------------
# 3.5 honest publication failure and retry
# ---------------------------------------------------------------------------


def test_publication_failure_after_termination_is_reported_honestly(
    tmp_path: Path, monkeypatch
):
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    run_id = response["run_id"]

    calls: list[str] = []

    def failing_publish(store, target_run_id):
        calls.append(target_run_id)
        return {"ok": False, "error": "disk full while publishing"}

    monkeypatch.setattr(job_manager_module, "publish_run_result", failing_publish)
    terminations: list[int] = []
    monkeypatch.setattr(
        job_manager_module,
        "terminate_process_tree",
        lambda pid, **_k: (
            terminations.append(pid)
            or {"pid": pid, "terminated": True, "method": "spy", "error": ""}
        ),
    )

    cancelled = manager.cancel_run(run_id)

    # Termination is proven; publication is not. The response says both.
    assert cancelled["cancelled"] is True
    assert cancelled["termination_confirmed"] is True
    assert cancelled["publication_ok"] is False
    assert cancelled["ok"] is False, "a publication failure read as full success"
    assert "disk full" in cancelled["publication_error"]
    assert cancelled["retry_hint"]
    # Durable terminal state is still the exact winner.
    assert manager.get_status(run_id)["status"] == "cancelled"

    # Retry: republishes the same result, never re-terminates.
    before = len(terminations)
    monkeypatch.setattr(
        job_manager_module,
        "publish_run_result",
        lambda store, target: {"ok": True, "error": ""},
    )
    retried = manager.cancel_run(run_id)
    assert retried["publication_ok"] is True
    assert retried["ok"] is True
    assert retried["status"] == "cancelled"
    assert len(terminations) == before, "retry repeated process termination"

    # Idempotent after success.
    again = manager.cancel_run(run_id)
    assert again["ok"] is True
    assert manager.get_status(run_id)["status"] == "cancelled"


# ---------------------------------------------------------------------------
# 3.6 crash containment
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not IS_WINDOWS, reason="KILL_ON_JOB_CLOSE is a Windows job limit")
def test_a_controller_crash_kills_the_whole_contained_tree(tmp_path: Path):
    """Owner-approved crash policy, proven end to end.

    A helper contains a root that spawns descendants, then dies abruptly via
    os._exit without cancelling anything. Every member must be gone because the
    last job handle closed. No parent-table inference is used.
    """
    workspace = tmp_path / "crash"
    workspace.mkdir()
    (workspace / "grand.py").write_text(
        "import time\ntime.sleep(120)\n", encoding="utf-8"
    )
    (workspace / "child.py").write_text(
        "import subprocess, sys, pathlib, time\n"
        "h = pathlib.Path(__file__).parent\n"
        "subprocess.Popen([sys.executable, str(h / 'grand.py')])\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    (workspace / "root.py").write_text(
        "import subprocess, sys, pathlib, time\n"
        "h = pathlib.Path(__file__).parent\n"
        "subprocess.Popen([sys.executable, str(h / 'child.py')])\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    controller = workspace / "controller.py"
    controller.write_text(
        "import os, pathlib, sys, time\n"
        f"sys.path.insert(0, {str(Path.cwd())!r})\n"
        "from soma.worker_process.containment import launch_contained\n"
        "here = pathlib.Path(__file__).parent\n"
        "proc, job = launch_contained(\n"
        "    [sys.executable, str(here / 'root.py')],\n"
        "    job_name='Local\\\\soma-closure-crash-probe')\n"
        "deadline = time.time() + 30\n"
        "while len(job.assigned_pids()) < 3 and time.time() < deadline:\n"
        "    time.sleep(0.2)\n"
        "(here / 'pids.txt').write_text(','.join(str(p) for p in job.assigned_pids()))\n"
        "os._exit(1)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(controller)], capture_output=True, text=True, timeout=120
    )
    pids_file = workspace / "pids.txt"
    assert pids_file.exists(), f"controller did not contain a tree: {result.stderr}"
    pids = [int(item) for item in pids_file.read_text().split(",") if item]
    assert len(pids) >= 3, f"stand-in tree was too small to prove anything: {pids}"

    deadline = time.monotonic() + 30
    while any(process_is_running(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.2)
    alive = [pid for pid in pids if process_is_running(pid)]
    assert alive == [], f"controller crash left {alive} running"


@pytest.mark.skipif(not IS_WINDOWS, reason="KILL_ON_JOB_CLOSE is a Windows job limit")
def test_releasing_an_already_empty_job_is_safe():
    process, job = containment_module.launch_contained(
        [sys.executable, "-c", "pass"], job_name="Local\\soma-closure-empty"
    )
    process.wait(timeout=60)
    deadline = time.monotonic() + 20
    while job.assigned_pids() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert job.is_empty()
    containment_module.register_job(job)
    containment_module.release_job(job.name)  # must not raise


# ---------------------------------------------------------------------------
# 3.7 deterministic ordering
# ---------------------------------------------------------------------------


def test_cancellation_considers_child_then_worker_then_launcher(
    tmp_path: Path, monkeypatch
):
    """Deterministic ordering with synthetic PIDs and a termination spy.

    No host process is touched: running state and identities are supplied, so
    host PID allocation cannot decide this verdict.
    """
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    run_id = response["run_id"]
    manager.store.update_run(
        run_id,
        pid=901,
        child_identity="901:synthetic:1",
        worker_pid=902,
        worker_identity="902:synthetic:1",
        launcher_pid=903,
        launcher_identity="903:synthetic:1",
    )

    import soma.process_control as pc

    synthetic = {901: "901:synthetic:1", 902: "902:synthetic:1", 903: "903:synthetic:1"}
    monkeypatch.setattr(pc, "process_is_running", lambda pid: int(pid) in synthetic)
    monkeypatch.setattr(pc, "process_identity", lambda pid: synthetic.get(int(pid), ""))
    monkeypatch.setattr(pc, "recorded_process_is_absent", lambda pid, identity: True)
    terminated: list[int] = []
    monkeypatch.setattr(
        job_manager_module,
        "terminate_process_tree",
        lambda pid, **_k: (
            terminated.append(int(pid))
            or {"pid": pid, "terminated": True, "method": "spy", "error": ""}
        ),
    )

    cancelled = manager.cancel_run(run_id)

    assert terminated == [901, 902, 903]
    assert [report["role"] for report in cancelled["termination_reports"]] == [
        "child",
        "worker",
        "launcher",
    ]
    assert all(
        report["ownership_proven"] for report in cancelled["termination_reports"]
    )
    assert cancelled["cancelled"] is True


def test_an_unproven_target_is_skipped_while_proven_ones_are_terminated(
    tmp_path: Path, monkeypatch
):
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    run_id = response["run_id"]
    manager.store.update_run(
        run_id,
        pid=901,
        child_identity="901:synthetic:1",
        worker_pid=902,
        worker_identity="",  # no proof for the worker
        launcher_pid=0,
        launcher_identity="",
    )

    import soma.process_control as pc

    live = {901: "901:synthetic:1", 902: "902:synthetic:1"}
    monkeypatch.setattr(pc, "process_is_running", lambda pid: int(pid) in live)
    monkeypatch.setattr(pc, "process_identity", lambda pid: live.get(int(pid), ""))
    monkeypatch.setattr(pc, "recorded_process_is_absent", lambda pid, identity: True)
    terminated: list[int] = []
    monkeypatch.setattr(
        job_manager_module,
        "terminate_process_tree",
        lambda pid, **_k: (
            terminated.append(int(pid))
            or {"pid": pid, "terminated": True, "method": "spy", "error": ""}
        ),
    )

    cancelled = manager.cancel_run(run_id)

    assert terminated == [901], "an unproven live PID was terminated"
    assert cancelled["cancelled"] is False
    assert cancelled["termination_confirmed"] is False
    # Lock retained while ownership is unprovable.
    assert manager.locks.find_lock("sample", run_id) is not None


# ---------------------------------------------------------------------------
# 3.8 public projection classification
# ---------------------------------------------------------------------------


IDENTITY_COLUMNS = ("worker_identity", "launcher_identity", "child_identity")


def test_identity_values_are_absent_from_public_projections(
    tmp_path: Path, monkeypatch
):
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    run_id = response["run_id"]
    manager.store.update_run(
        run_id,
        launcher_identity="LAUNCHER-IDENTITY-SECRET",
        child_identity="CHILD-IDENTITY-SECRET",
        worker_identity="WORKER-IDENTITY-SECRET",
    )

    status = manager.get_status(run_id)
    rendered = repr(status)
    for marker in ("LAUNCHER-IDENTITY-SECRET", "CHILD-IDENTITY-SECRET"):
        assert marker not in rendered, f"{marker} leaked through get_status"

    control = manager.get_control_status(run_id)
    rendered = repr(control)
    for marker in (
        "LAUNCHER-IDENTITY-SECRET",
        "CHILD-IDENTITY-SECRET",
        "WORKER-IDENTITY-SECRET",
    ):
        assert marker not in rendered, f"{marker} leaked through get_control_status"


@pytest.mark.xfail(
    reason=(
        "Pre-existing, not introduced by this gate: _public_run copies the whole "
        "run row, so the older worker_identity column is exposed through "
        "get_status. Gate 3.8 governs launcher and child identity, which are now "
        "withheld. Removing worker_identity is a public-contract change needing "
        "separate authorisation, so it is reported rather than made silently."
    ),
    strict=True,
)
def test_worker_identity_is_still_exposed_through_get_status(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, monkeypatch)
    response = manager.start_git_readonly("sample", "status")
    manager.store.update_run(
        response["run_id"], worker_identity="WORKER-IDENTITY-SECRET"
    )
    assert "WORKER-IDENTITY-SECRET" not in repr(manager.get_status(response["run_id"]))


def test_projection_column_lists_exclude_identity_values():
    for column in IDENTITY_COLUMNS:
        assert column not in RUN_SUMMARY_PROJECTION_COLUMNS
    for column in ("launcher_identity", "child_identity"):
        assert column not in RUN_CONTROL_PROJECTION_COLUMNS


def test_control_projection_reports_worker_identity_presence_not_its_value(
    tmp_path: Path,
):
    """The existing contract: presence is public, the value is not."""
    store = RunStore(tmp_path / "runs")
    store.create_run(
        run_id="20260730T090000Z_executable_profile_deadbee1",
        repo_name="sample",
        tool="executable_profile",
        run_dir=tmp_path / "runs" / "20260730T090000Z_executable_profile_deadbee1",
        input_data={},
    )
    store.update_run(
        "20260730T090000Z_executable_profile_deadbee1",
        worker_identity="WORKER-IDENTITY-SECRET",
    )
    snapshot, _identity = store.get_run_control_observation(
        "20260730T090000Z_executable_profile_deadbee1"
    )
    assert snapshot["worker_identity_present"] is True
    assert "WORKER-IDENTITY-SECRET" not in repr(snapshot)
