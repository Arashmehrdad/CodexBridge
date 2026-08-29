"""V3-1A-CANCELLATION-AUTHORITY-1: identity-proven cancellation and containment.

These cover the acceptance-audit blockers: raw-PID termination, root-identity
verification before enumeration, kernel-backed zero-descendant proof, and the
rule that empty subordinate evidence is not proof of anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soma.process_control import (
    identity_scoped_termination,
    list_descendants,
    process_identity,
    process_is_running,
    terminate_process_tree,
)
from soma.worker_process import (
    AttachmentDisposition,
    CancellationDisposition,
    ContainmentUnavailable,
    JobContainment,
    StandInLaunchRequest,
    cancel_owned_tree,
    launch_contained,
    launch_stand_in,
)
from soma.worker_process import cancellation as cancellation_module
from soma.worker_process import containment as containment_module
from soma.worker_substrate import ProviderChildRole

from test_worker_process_identity import IS_WINDOWS, bound  # noqa: F401


def _spy():
    calls: list[int] = []

    def terminate(pid):
        calls.append(pid)
        return {"terminated": True, "method": "spy", "error": ""}

    return calls, terminate


def _dead_pid() -> int:
    """A PID that really existed and really exited, so absence is not a guess."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=60)
    return process.pid


# ---------------------------------------------------------------------------
# 4.2 identity-first termination
# ---------------------------------------------------------------------------


def test_no_recorded_identity_means_no_termination():
    """The owner-approved rule, unit-tested at the canonical primitive."""
    calls, terminate = _spy()
    report = identity_scoped_termination(os.getpid(), "", terminate=terminate)
    assert calls == []
    assert report["method"] == "refused_no_recorded_identity"
    assert report["ownership_proven"] is False
    # Not terminated: the caller must keep the run pending and hold its lock.
    assert report["terminated"] is False


def test_pid_reuse_means_no_termination_but_the_recorded_process_is_absent():
    calls, terminate = _spy()
    report = identity_scoped_termination(os.getpid(), "1:windows:1", terminate=terminate)
    assert calls == []
    assert report["identity_mismatch"] is True
    assert report["terminated"] is True


def test_unreadable_live_identity_means_no_termination(monkeypatch):
    import soma.process_control as pc

    calls, terminate = _spy()
    monkeypatch.setattr(pc, "process_identity", lambda pid: "")
    report = identity_scoped_termination(
        os.getpid(), "some-recorded-identity", terminate=terminate
    )
    assert calls == []
    assert report["method"] == "refused_unreadable_identity"
    assert report["terminated"] is False


def test_a_proven_match_may_be_terminated_but_absence_still_decides():
    calls, terminate = _spy()
    identity = process_identity(os.getpid())
    report = identity_scoped_termination(os.getpid(), identity, terminate=terminate)
    assert calls == [os.getpid()]
    assert report["ownership_proven"] is True
    # This process is obviously still alive, so the spy's claim is overruled.
    assert report["terminated"] is False


def test_a_dead_pid_needs_no_identity_and_no_termination():
    calls, terminate = _spy()
    report = identity_scoped_termination(_dead_pid(), "", terminate=terminate)
    assert calls == []
    assert report["method"] == "already_stopped"
    assert report["terminated"] is True


def test_root_identity_is_verified_before_any_enumeration(bound, monkeypatch):
    """A mismatched root must never have its tree walked, let alone targeted."""
    store, binding, task_id, run_id = bound
    store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=os.getpid(),
        process_start_identity=f"{os.getpid()}:windows:1",
        observation_source="test",
    )
    enumerated: list[int] = []
    monkeypatch.setattr(
        cancellation_module,
        "list_descendants",
        lambda pid: enumerated.append(pid) or [],
    )
    proof = cancel_owned_tree(store, binding.session_binding_id)
    assert enumerated == [], "an unproven tree was enumerated"
    assert proof.records[0].identity_mismatch is True


def test_a_root_without_a_recorded_identity_is_uncertainty(bound, monkeypatch):
    store, binding, task_id, run_id = bound
    # The store refuses an empty identity, so simulate a legacy row directly.
    monkeypatch.setattr(
        cancellation_module,
        "list_descendants",
        lambda pid: pytest.fail("enumeration must not happen"),
    )

    class _Row:
        role = ProviderChildRole.PROVIDER_ROOT
        pid = os.getpid()
        process_start_identity = ""
        observation_source = ""

    monkeypatch.setattr(store, "list_child_processes", lambda _b: [_Row()])
    proof = cancel_owned_tree(store, binding.session_binding_id)
    assert proof.disposition is CancellationDisposition.UNCERTAIN
    assert proof.may_publish_terminal_cancellation is False


# ---------------------------------------------------------------------------
# 4.3 kernel-backed containment
# ---------------------------------------------------------------------------


def _write_tree(directory: Path, *, root_exits: bool) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "grandchild.py").write_text(
        "import time\ntime.sleep(120)\n", encoding="utf-8"
    )
    (directory / "child.py").write_text(
        "import subprocess, sys, time, pathlib\n"
        "here = pathlib.Path(__file__).parent\n"
        "subprocess.Popen([sys.executable, str(here / 'grandchild.py')])\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    tail = "time.sleep(1)\nraise SystemExit(0)\n" if root_exits else "time.sleep(120)\n"
    root = directory / "root.py"
    root.write_text(
        "import subprocess, sys, time, pathlib\n"
        "here = pathlib.Path(__file__).parent\n"
        "subprocess.Popen([sys.executable, str(here / 'child.py')])\n" + tail,
        encoding="utf-8",
    )
    return root


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel Job Object proof")
def test_job_still_owns_descendants_after_the_root_exits(tmp_path: Path):
    """The audit blocker: a sweep from a dead root finds nothing at all."""
    root = _write_tree(tmp_path / "exiting", root_exits=True)
    process, job = launch_contained(
        [sys.executable, str(root)], job_name="Local\\soma-test-root-exit"
    )
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        assert process.poll() is not None, "root did not exit"

        # Parent-table enumeration from the dead root is incomplete. A hidden
        # console host may remain linked to the exited root, but the actual
        # worker descendants have already escaped that parent walk.
        enumerated = set(list_descendants(process.pid))
        assigned = set(job.assigned_pids())
        assert len(assigned) >= 2, f"job lost the orphaned descendants: {assigned}"
        assert enumerated < assigned, (
            "parent enumeration unexpectedly matched the kernel-owned tree: "
            f"enumerated={enumerated}, assigned={assigned}"
        )

        job.terminate()
        deadline = time.monotonic() + 30
        while job.assigned_pids() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert job.is_empty(), f"job still owns {job.assigned_pids()}"
    finally:
        try:
            job.terminate()
        except ContainmentUnavailable:
            pass
        job.close()


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel Job Object proof")
def test_a_late_descendant_spawned_after_launch_is_still_contained(tmp_path: Path):
    directory = tmp_path / "late"
    directory.mkdir()
    (directory / "late.py").write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    root = directory / "root.py"
    root.write_text(
        "import subprocess, sys, time, pathlib\n"
        "here = pathlib.Path(__file__).parent\n"
        "time.sleep(1.5)\n"
        "subprocess.Popen([sys.executable, str(here / 'late.py')])\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    process, job = launch_contained(
        [sys.executable, str(root)], job_name="Local\\soma-test-late"
    )
    try:
        deadline = time.monotonic() + 30
        while len(job.assigned_pids()) < 2 and time.monotonic() < deadline:
            time.sleep(0.2)
        assert len(job.assigned_pids()) >= 2, "late descendant was not contained"
        job.terminate()
        deadline = time.monotonic() + 30
        while job.assigned_pids() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert job.is_empty()
    finally:
        try:
            job.terminate()
        except ContainmentUnavailable:
            pass
        job.close()


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel Job Object proof")
def test_a_named_job_cannot_be_reopened_after_its_handle_closes():
    """Measured limitation, pinned so the design cannot silently regress.

    Naming does not buy restart survival, which is why the handle is held in a
    process-local registry and why cancellation reports reduced proof once the
    job is gone.
    """
    name = "Local\\soma-test-reopen-probe"
    process, job = launch_contained(
        [sys.executable, "-c", "import time; time.sleep(60)"], job_name=name
    )
    try:
        assert job.assigned_pids()
        job.close()
        with pytest.raises(ContainmentUnavailable):
            JobContainment.open_existing(name)
    finally:
        if process.poll() is None:
            process.kill()


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel Job Object proof")
def test_launch_registers_a_job_and_cancellation_proves_it_empty(bound):
    store, binding, task_id, run_id = bound
    result = launch_stand_in(
        store,
        StandInLaunchRequest(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=run_id,
            executable_path=sys.executable,
            argv=["-c", "import time; time.sleep(60)"],
            descendant_settle_seconds=0,
        ),
    )
    assert result.disposition is AttachmentDisposition.ATTACHED
    assert result.job_name

    proof = cancel_owned_tree(store, binding.session_binding_id)
    assert proof.job_proof_available is True
    assert proof.job_assigned_pids == ()
    assert proof.disposition is CancellationDisposition.CONFIRMED
    assert proof.may_publish_terminal_cancellation is True
    assert not process_is_running(result.root_pid)


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel Job Object proof")
def test_lost_containment_downgrades_to_uncertainty(bound):
    """After a Soma restart the job is gone; parent-table evidence is not proof."""
    store, binding, task_id, run_id = bound
    result = launch_stand_in(
        store,
        StandInLaunchRequest(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=run_id,
            executable_path=sys.executable,
            argv=["-c", "import time; time.sleep(60)"],
            descendant_settle_seconds=0,
        ),
    )
    assert result.disposition is AttachmentDisposition.ATTACHED
    try:
        containment_module.release_job(result.job_name)
        proof = cancel_owned_tree(store, binding.session_binding_id)
        assert proof.job_proof_available is False
        assert proof.disposition is CancellationDisposition.UNCERTAIN
        assert proof.may_publish_terminal_cancellation is False
        assert "no longer reachable" in proof.detail
    finally:
        terminate_process_tree(result.root_pid)


@pytest.mark.skipif(not IS_WINDOWS, reason="kernel Job Object proof")
def test_containment_failure_at_launch_leaves_nothing_running(monkeypatch, tmp_path):
    """If a process cannot be assigned, it is killed rather than released."""
    started: list[int] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        started.append(process.pid)
        return process

    monkeypatch.setattr(
        containment_module.JobContainment,
        "assign_pid",
        lambda self, pid: (_ for _ in ()).throw(
            ContainmentUnavailable("assignment refused")
        ),
    )
    with pytest.raises(ContainmentUnavailable):
        launch_contained(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            job_name="Local\\soma-test-assign-fail",
            popen=recording_popen,
        )
    assert started, "no process was created, so the test proved nothing"
    deadline = time.monotonic() + 20
    while process_is_running(started[0]) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not process_is_running(started[0]), "unassignable process was released"


def test_contained_launch_uses_hidden_inherited_console(monkeypatch):
    """Contained Windows roots hide a console descendants can safely inherit."""
    captured: dict[str, object] = {}

    class FakeJob:
        def assign_pid(self, pid):
            captured["assigned_pid"] = pid

        def close(self):
            captured["closed"] = True

        def terminate(self, exit_code=1):
            captured["terminated"] = exit_code

    class FakeProcess:
        pid = 4242

        def kill(self):
            captured["killed"] = True

    monkeypatch.setattr(
        containment_module.JobContainment,
        "create",
        classmethod(lambda cls, name: FakeJob()),
    )
    monkeypatch.setattr(
        containment_module,
        "_resume_process_threads",
        lambda pid: captured.__setitem__("resumed_pid", pid),
    )

    def fake_popen(*args, **kwargs):
        captured["creationflags"] = kwargs["creationflags"]
        captured["startupinfo"] = kwargs["startupinfo"]
        return FakeProcess()

    process, _job = containment_module.launch_contained(
        ["powershell.exe", "-NoProfile"],
        job_name="Local\\soma-background-test",
        popen=fake_popen,
    )

    assert process.pid == 4242
    assert captured["assigned_pid"] == 4242
    assert captured["resumed_pid"] == 4242
    assert captured["creationflags"] == (
        containment_module.CREATE_SUSPENDED | containment_module.CREATE_NEW_CONSOLE
    )
    startupinfo = captured["startupinfo"]
    assert startupinfo.dwFlags & int(getattr(subprocess, "STARTF_USESHOWWINDOW", 1))
    assert startupinfo.wShowWindow == int(getattr(subprocess, "SW_HIDE", 0))
