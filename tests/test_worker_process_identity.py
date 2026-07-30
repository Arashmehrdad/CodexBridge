"""V3-1A-PROCESS-IDENTITY-1: sanitised launch and owned-tree cancellation.

No provider is launched. The stand-in trees are the current virtual-environment
Python running trivial sleep programs, which reproduces the ownership shape the
pilot measured (root -> child -> grandchild) without any provider account.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from soma.process_control import (
    list_descendants,
    process_identity,
    process_is_running,
    process_parent_table,
    recorded_process_is_absent,
)
from soma.project_scope.store import ProjectScopeStore
from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore
from soma.worker_adapters import get_adapter
from soma.worker_process import (
    AttachmentDisposition,
    CancellationDisposition,
    ExecutableRejected,
    RemovalReason,
    StandInLaunchRequest,
    build_child_environment,
    cancel_owned_tree,
    find_secret_shaped_names,
    launch_stand_in,
    require_unchanged,
    verify_executable,
)
from soma.worker_process import cancellation as cancellation_module
from soma.worker_substrate import ProviderChildRole, WorkerSubstrateStore


PROJECT_ID = "proj_11111111-1111-1111-1111-111111111111"
RESOURCE_ID = "res_22222222-2222-2222-2222-222222222222"
IS_WINDOWS = os.name == "nt"


# ---------------------------------------------------------------------------
# canonical fixture
# ---------------------------------------------------------------------------


def _canonical_task(runs_dir: Path, *, controller_request_id: str) -> tuple[str, str]:
    task_id = make_task_id()
    run_id = (
        "20260730T101010Z_worker_"
        + hashlib.sha256(controller_request_id.encode("utf-8")).hexdigest()[:8]
    )
    normalized = normalize_durable_command_request(
        repo_name="soma", profile_id="pytest", argv=["python", "-m", "pytest", "-q"]
    )
    RunStore(runs_dir).create_run(
        run_id=run_id,
        repo_name="soma",
        tool="executable_profile",
        run_dir=runs_dir / run_id,
        input_data=normalized,
    )
    TaskStore(runs_dir).reserve_task(
        task_id=task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id=controller_request_id,
        request_hash=normalized_request_hash(normalized),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref=run_id,
        backend_identity={"run_id": run_id},
    )
    scope = ProjectScopeStore(runs_dir)
    scope.init_db()
    now = "2026-07-30T00:00:00+00:00"
    with scope.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, project_key, lifecycle_state,"
            " scope_generation, created_at, updated_at)"
            " VALUES (?, 'soma-test', 'active', 1, ?, ?)",
            (PROJECT_ID, now, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_resources (resource_id, resource_kind,"
            " opaque_ref, identity_hash, created_at)"
            " VALUES (?, 'repository', 'd:/github/soma', 'soma-test-resource', ?)",
            (RESOURCE_ID, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_resource_bindings (project_id, resource_id,"
            " access_mode, created_at) VALUES (?, ?, 'exclusive', ?)",
            (PROJECT_ID, RESOURCE_ID, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_repository_bindings (project_id,"
            " resource_id, repo_name, repository_root, identity_hash, created_at)"
            " VALUES (?, ?, 'soma', 'd:/github/soma', 'soma-test-resource', ?)",
            (PROJECT_ID, RESOURCE_ID, now),
        )
        conn.execute(
            "INSERT INTO project_task_reservations (task_id, project_id,"
            " scope_generation, status, created_at, updated_at)"
            " VALUES (?, ?, 1, 'attached', ?, ?)",
            (task_id, PROJECT_ID, now, now),
        )
        conn.execute(
            "INSERT INTO project_run_attempts (run_id, project_id, task_id,"
            " resource_id, scope_generation, status, recovery_reason, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, 1, 'attached', '', ?, ?)",
            (run_id, PROJECT_ID, task_id, RESOURCE_ID, now, now),
        )
    return task_id, run_id


@pytest.fixture()
def bound(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    store = WorkerSubstrateStore(runs_dir)
    task_id, run_id = _canonical_task(runs_dir, controller_request_id="req-proc-1")
    adapter = get_adapter("claude_code")
    binding, _ = store.bind_provider_session(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=task_id,
        run_id=run_id,
        provider=adapter.identity.provider,
        native_session_id="91f5d23f-2c4a-4d1e-9b8f-5a7c3e1d0b62",
        adapter_id=adapter.identity.adapter_id,
        adapter_version=adapter.identity.adapter_version,
        protocol_id=adapter.identity.protocol_id,
        protocol_version=adapter.identity.protocol_version,
    )
    return store, binding, task_id, run_id


# ---------------------------------------------------------------------------
# 3.1 sanitised environment
# ---------------------------------------------------------------------------


PARENT_ENV = {
    "PATH": "C:/Windows/System32",
    "SystemRoot": "C:/Windows",
    "CLAUDECODE": "1",
    "CLAUDE_CODE_ENTRYPOINT": "cli",
    "CODEX_HOME": "C:/Users/x/.codex",
    "SOMA_MCP_URL": "https://mcp.example.win",
    "MCP_SERVER_TOKEN": "should-never-appear",
    "ANTHROPIC_API_KEY": "sk-live-should-never-appear",
    "AWS_SECRET_ACCESS_KEY": "should-never-appear",
    "GITHUB_TOKEN": "should-never-appear",
    "MY_HARMLESS_SETTING": "1",
}


def _claude_removals() -> tuple[str, ...]:
    return get_adapter("claude_code").build_start_spec(
        executable_path=r"C:\opt\claude.exe",
        prompt_payload_ref="worker_payload:" + "a" * 64,
    ).environment_remove


def test_child_environment_is_built_from_an_allowlist_not_inherited():
    result = build_child_environment(
        parent_environment=PARENT_ENV, declared_removals=_claude_removals()
    )
    assert set(result.environment) == {"PATH", "SystemRoot"}
    # Everything else is withheld, including a variable nobody thought to ban.
    assert "MY_HARMLESS_SETTING" not in result.environment


def test_provider_recursion_markers_are_removed_and_classified():
    result = build_child_environment(
        parent_environment=PARENT_ENV, declared_removals=_claude_removals()
    )
    for name in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_HOME"):
        assert name not in result.environment
        assert result.evidence.reason_for(name) is (
            RemovalReason.PROVIDER_RECURSION_MARKER
        )
    assert "CLAUDECODE" in result.evidence.declared_removals_honoured


def test_soma_and_mcp_configuration_never_reaches_the_child():
    result = build_child_environment(
        parent_environment=PARENT_ENV, declared_removals=_claude_removals()
    )
    assert "SOMA_MCP_URL" not in result.environment
    assert result.evidence.reason_for("SOMA_MCP_URL") is (
        RemovalReason.SOMA_OR_MCP_CONFIGURATION
    )


def test_credential_shaped_variables_are_removed():
    result = build_child_environment(
        parent_environment=PARENT_ENV, declared_removals=_claude_removals()
    )
    for name in ("ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"):
        assert name not in result.environment
    assert find_secret_shaped_names(result.environment) == ()


def test_environment_evidence_never_contains_a_value():
    result = build_child_environment(
        parent_environment=PARENT_ENV, declared_removals=_claude_removals()
    )
    rendered = repr(result.evidence.to_dict())
    for secret in PARENT_ENV.values():
        if secret in {"C:/Windows/System32", "C:/Windows", "1", "cli"}:
            continue
        assert secret not in rendered
    assert "should-never-appear" not in rendered
    assert "sk-live" not in rendered


def test_a_declared_recursion_marker_cannot_be_allowlisted_back_in():
    """Finding 8 makes this a launch failure, not an operator preference."""
    result = build_child_environment(
        parent_environment=PARENT_ENV,
        declared_removals=_claude_removals(),
        allowlist_extra=("CLAUDECODE", "MY_HARMLESS_SETTING"),
    )
    assert "CLAUDECODE" not in result.environment
    assert "CLAUDECODE" not in result.evidence.allowlist_extra
    # An ordinary extra is still honoured, so this is a targeted refusal.
    assert result.environment["MY_HARMLESS_SETTING"] == "1"


def test_deliberate_additions_are_kept_and_not_treated_as_inherited():
    result = build_child_environment(
        parent_environment=PARENT_ENV,
        declared_removals=_claude_removals(),
        additions={"SOMA_WORKER_WORKSPACE": "C:/wt/a"},
    )
    assert result.environment["SOMA_WORKER_WORKSPACE"] == "C:/wt/a"


# ---------------------------------------------------------------------------
# 3.2 exact executable identity
# ---------------------------------------------------------------------------


def test_executable_identity_is_captured_for_a_real_file(tmp_path: Path):
    identity = verify_executable(sys.executable)
    assert Path(identity.path).is_absolute()
    assert identity.size_bytes > 0
    assert len(identity.content_sha256) == 64
    assert require_unchanged(identity) == identity


@pytest.mark.parametrize(
    "candidate", ["", "   ", "python", "python.exe", "./python", "bin/python"]
)
def test_path_lookup_and_relative_paths_are_refused(candidate):
    with pytest.raises(ExecutableRejected):
        verify_executable(candidate)


def test_traversal_is_refused(tmp_path: Path):
    with pytest.raises(ExecutableRejected, match="traversal"):
        verify_executable(str(tmp_path / ".." / "python.exe"))


def test_missing_and_directory_targets_are_refused(tmp_path: Path):
    with pytest.raises(ExecutableRejected, match="does not exist"):
        verify_executable(str(tmp_path / "absent.exe"))
    with pytest.raises(ExecutableRejected, match="directory"):
        verify_executable(str(tmp_path))


def test_replacement_between_verification_and_launch_is_detected(tmp_path: Path):
    target = tmp_path / "tool.exe"
    target.write_bytes(b"original-payload")
    if not IS_WINDOWS:
        target.chmod(0o755)
    identity = verify_executable(str(target))

    target.write_bytes(b"substituted-payload!")
    with pytest.raises(ExecutableRejected, match="identity changed"):
        require_unchanged(identity)


def test_same_size_replacement_is_still_detected(tmp_path: Path):
    """Size and mtime can collide; the content hash is what actually protects."""
    target = tmp_path / "tool.exe"
    target.write_bytes(b"AAAAAAAAAAAAAAAA")
    if not IS_WINDOWS:
        target.chmod(0o755)
    identity = verify_executable(str(target))
    target.write_bytes(b"BBBBBBBBBBBBBBBB")
    os.utime(target, ns=(identity.mtime_ns, identity.mtime_ns))

    with pytest.raises(ExecutableRejected, match="content_sha256"):
        require_unchanged(identity)


# ---------------------------------------------------------------------------
# process enumeration primitives
# ---------------------------------------------------------------------------


def test_parent_table_includes_this_process():
    table = process_parent_table()
    assert os.getpid() in table


def test_recorded_absence_distinguishes_pid_reuse():
    pid = os.getpid()
    identity = process_identity(pid)
    assert identity
    assert recorded_process_is_absent(pid, identity) is False
    # Same PID, different start identity: a different process, so ours is gone.
    assert recorded_process_is_absent(pid, identity + "-other") is True
    # No recorded identity means nothing can be proven, so not provably absent.
    assert recorded_process_is_absent(pid, "") is False
    assert recorded_process_is_absent(0, "") is True


# ---------------------------------------------------------------------------
# 3.3 / 3.4 real stand-in process tree
# ---------------------------------------------------------------------------


def _write_stand_in_tree(directory: Path) -> Path:
    """Write a root -> child -> grandchild sleeper tree as real files.

    Separate files rather than nested ``-c`` sources: quoting a script inside a
    script inside a dedent silently produced a root that died on an
    IndentationError, which made the tree look terminated before cancellation
    ever ran.
    """
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
    root = directory / "root.py"
    root.write_text(
        "import subprocess, sys, time, pathlib\n"
        "here = pathlib.Path(__file__).parent\n"
        "subprocess.Popen([sys.executable, str(here / 'child.py')])\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    return root


def _spawn_stand_in_tree(directory: Path) -> subprocess.Popen:
    from soma.process_control import process_group_popen_kwargs

    root_script = _write_stand_in_tree(directory)
    process = subprocess.Popen(
        [sys.executable, str(root_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **process_group_popen_kwargs(),
    )
    # Fail loudly if the stand-in itself is broken: a root that exited would
    # make every cancellation assertion below vacuously true.
    time.sleep(0.5)
    assert process.poll() is None, "stand-in root exited immediately"
    return process


def _wait_for_descendants(root_pid: int, minimum: int, timeout: float = 20.0) -> list[int]:
    deadline = time.monotonic() + timeout
    found: list[int] = []
    while time.monotonic() < deadline:
        found = list_descendants(root_pid)
        if len(found) >= minimum:
            return found
        time.sleep(0.25)
    return found


@pytest.mark.skipif(not IS_WINDOWS, reason="real Windows process-tree proof")
def test_real_tree_launch_records_root_and_descendants_then_cancels(bound, tmp_path):
    store, binding, task_id, run_id = bound
    process = _spawn_stand_in_tree(tmp_path / "tree_a")
    root_pid = process.pid
    try:
        descendants = _wait_for_descendants(root_pid, 2)
        assert len(descendants) >= 2, (
            f"stand-in tree did not reach root/child/grandchild: {descendants}"
        )
        root_identity = process_identity(root_pid)
        assert root_identity

        store.record_child_process(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=run_id,
            role=ProviderChildRole.PROVIDER_ROOT,
            pid=root_pid,
            process_start_identity=root_identity,
            observation_source="test_launch",
        )
        from soma.worker_process import record_descendants

        recorded = record_descendants(
            store,
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=run_id,
            root_pid=root_pid,
        )
        assert len(recorded) >= 2

        proof = cancel_owned_tree(store, binding.session_binding_id)

        assert proof.disposition is CancellationDisposition.CONFIRMED, proof.detail
        assert proof.zero_owned_descendants is True
        assert proof.may_publish_terminal_cancellation is True
        # Every recorded process is genuinely gone, checked against the OS.
        for record in proof.records:
            assert record.absent_after is True
        for pid, _identity in recorded:
            assert not process_is_running(pid)
        assert not process_is_running(root_pid)
    finally:
        if process.poll() is None:
            process.kill()


@pytest.mark.skipif(not IS_WINDOWS, reason="real Windows process-tree proof")
def test_cancellation_is_idempotent_when_replayed(bound, tmp_path):
    store, binding, task_id, run_id = bound
    process = _spawn_stand_in_tree(tmp_path / "tree_b")
    try:
        _wait_for_descendants(process.pid, 1)
        store.record_child_process(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=run_id,
            role=ProviderChildRole.PROVIDER_ROOT,
            pid=process.pid,
            process_start_identity=process_identity(process.pid),
            observation_source="test_launch",
        )
        first = cancel_owned_tree(store, binding.session_binding_id)
        second = cancel_owned_tree(store, binding.session_binding_id)
        assert first.disposition is CancellationDisposition.CONFIRMED
        assert second.disposition is CancellationDisposition.CONFIRMED
        assert second.may_publish_terminal_cancellation is True
    finally:
        if process.poll() is None:
            process.kill()


def test_nothing_recorded_is_not_a_cancellation_claim(bound):
    store, binding, _task_id, _run_id = bound
    proof = cancel_owned_tree(store, binding.session_binding_id)
    assert proof.disposition is CancellationDisposition.NOTHING_RECORDED
    # Nothing owned means nothing can be running, so publication is allowed.
    assert proof.may_publish_terminal_cancellation is True
    assert proof.records == ()


def test_a_surviving_descendant_disproves_a_successful_termination_report(
    bound, monkeypatch
):
    """taskkill claiming success must not outrank the absence check."""
    store, binding, task_id, run_id = bound
    identity = process_identity(os.getpid())
    store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=os.getpid(),
        process_start_identity=identity,
        observation_source="test",
    )
    monkeypatch.setattr(
        cancellation_module,
        "terminate_process_tree",
        lambda pid, grace_seconds=3.0: {
            "pid": pid,
            "method": "simulated",
            "terminated": True,
            "error": "",
        },
    )
    monkeypatch.setattr(cancellation_module, "list_descendants", lambda pid: [])

    proof = cancel_owned_tree(store, binding.session_binding_id)

    # The process really is still alive, so the cheerful report is overruled.
    assert proof.disposition is CancellationDisposition.UNCERTAIN
    assert os.getpid() in proof.surviving_pids
    assert proof.zero_owned_descendants is False
    assert proof.may_publish_terminal_cancellation is False


def test_pid_reuse_refuses_to_terminate_a_stranger(bound, monkeypatch):
    """The exact defect found in the legacy cancellation path."""
    store, binding, task_id, run_id = bound
    live_pid = os.getpid()
    store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=live_pid,
        # A recorded identity that cannot match the live process.
        process_start_identity=f"{live_pid}:windows:1",
        observation_source="test",
    )
    killed: list[int] = []
    monkeypatch.setattr(
        cancellation_module,
        "terminate_process_tree",
        lambda pid, grace_seconds=3.0: killed.append(pid),
    )
    monkeypatch.setattr(cancellation_module, "list_descendants", lambda pid: [])

    proof = cancel_owned_tree(store, binding.session_binding_id)

    assert killed == [], "Soma terminated a process it could not prove it owned"
    (record,) = proof.records
    assert record.identity_mismatch is True
    assert record.method == "refused_pid_reuse"
    # Our process is gone; the stranger occupying the number is not our problem.
    assert record.absent_after is True
    assert proof.disposition is CancellationDisposition.CONFIRMED


def test_a_process_control_error_becomes_uncertainty_not_success(bound, monkeypatch):
    store, binding, task_id, run_id = bound
    store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=os.getpid(),
        process_start_identity=process_identity(os.getpid()),
        observation_source="test",
    )

    def boom(pid, grace_seconds=3.0):
        raise OSError("process control unavailable")

    monkeypatch.setattr(cancellation_module, "terminate_process_tree", boom)
    monkeypatch.setattr(cancellation_module, "list_descendants", lambda pid: [])

    proof = cancel_owned_tree(store, binding.session_binding_id)
    assert proof.disposition is CancellationDisposition.UNCERTAIN
    assert proof.may_publish_terminal_cancellation is False


def test_enumeration_failure_before_termination_is_uncertainty(bound, monkeypatch):
    store, binding, task_id, run_id = bound
    store.record_child_process(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=run_id,
        role=ProviderChildRole.PROVIDER_ROOT,
        pid=os.getpid(),
        process_start_identity=process_identity(os.getpid()),
        observation_source="test",
    )

    def boom(pid):
        raise OSError("enumeration failed")

    monkeypatch.setattr(cancellation_module, "list_descendants", boom)
    proof = cancel_owned_tree(store, binding.session_binding_id)
    assert proof.disposition is CancellationDisposition.UNCERTAIN
    assert "enumerated" in proof.detail


# ---------------------------------------------------------------------------
# launch crash windows
# ---------------------------------------------------------------------------


def test_process_creation_failure_after_intent_reports_launch_failed(bound):
    store, binding, task_id, run_id = bound

    def failing_popen(*args, **kwargs):
        raise OSError("CreateProcess failed")

    result = launch_stand_in(
        store,
        StandInLaunchRequest(
            session_binding_id=binding.session_binding_id,
            task_id=task_id,
            run_id=run_id,
            executable_path=sys.executable,
            argv=["-c", "pass"],
            descendant_settle_seconds=0,
        ),
        popen=failing_popen,
    )
    assert result.disposition is AttachmentDisposition.LAUNCH_FAILED
    assert result.root_pid == 0
    # Nothing was created, so nothing was recorded.
    assert store.list_child_processes(binding.session_binding_id) == []


def test_identity_capture_failure_contains_the_tree(bound, monkeypatch):
    """A live process Soma cannot name must never be left running."""
    store, binding, task_id, run_id = bound
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        monkeypatch.setattr(
            "soma.worker_process.launch.process_identity", lambda pid: ""
        )
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
            popen=lambda *a, **k: process,
        )
        assert result.disposition is AttachmentDisposition.CONTAINED_UNVERIFIED
        assert result.containment is not None
        assert store.list_child_processes(binding.session_binding_id) == []
        # The binding is marked unverified rather than left looking healthy.
        assert store.get_binding(binding.session_binding_id).disposition.value == (
            "unverified"
        )
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        assert process.poll() is not None, "contained process is still running"
    finally:
        if process.poll() is None:
            process.kill()


def test_launch_records_the_root_before_reporting_attached(bound):
    store, binding, task_id, run_id = bound
    observed: list[int] = []
    real_record = store.record_child_process

    def spy(**kwargs):
        observed.append(len(store.list_child_processes(binding.session_binding_id)))
        return real_record(**kwargs)

    store.record_child_process = spy  # type: ignore[method-assign]
    try:
        result = launch_stand_in(
            store,
            StandInLaunchRequest(
                session_binding_id=binding.session_binding_id,
                task_id=task_id,
                run_id=run_id,
                executable_path=sys.executable,
                argv=["-c", "import time; time.sleep(5)"],
                descendant_settle_seconds=0,
            ),
        )
    finally:
        del store.record_child_process
    assert result.disposition is AttachmentDisposition.ATTACHED
    assert result.root_identity
    rows = store.list_child_processes(binding.session_binding_id)
    assert rows[0].role is ProviderChildRole.PROVIDER_ROOT
    assert rows[0].pid == result.root_pid
    # The first persistence call happened with nothing yet recorded, proving the
    # root row precedes any attachment-ready claim.
    assert observed[0] == 0
    cancel_owned_tree(store, binding.session_binding_id)


def test_launch_sanitises_the_environment_of_the_real_child(bound, tmp_path: Path):
    """Read the child's own view of its environment rather than trusting ours."""
    store, binding, task_id, run_id = bound
    marker = tmp_path / "env.txt"
    script = (
        "import os, sys;"
        "open(sys.argv[1], 'w', encoding='utf-8')"
        ".write('\\n'.join(sorted(os.environ)))"
    )
    os.environ["CLAUDECODE"] = "1"
    os.environ["SOMA_TEST_SECRET_TOKEN"] = "should-never-appear"
    try:
        result = launch_stand_in(
            store,
            StandInLaunchRequest(
                session_binding_id=binding.session_binding_id,
                task_id=task_id,
                run_id=run_id,
                executable_path=sys.executable,
                argv=["-c", script, str(marker)],
                declared_removals=_claude_removals(),
                descendant_settle_seconds=0,
            ),
        )
        assert result.disposition is AttachmentDisposition.ATTACHED
        deadline = time.monotonic() + 20
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert marker.exists(), "stand-in child did not report its environment"
        names = set(marker.read_text(encoding="utf-8").split())
        assert "CLAUDECODE" not in names
        assert "SOMA_TEST_SECRET_TOKEN" not in names
        assert "PATH" in names
    finally:
        os.environ.pop("CLAUDECODE", None)
        os.environ.pop("SOMA_TEST_SECRET_TOKEN", None)
        cancel_owned_tree(store, binding.session_binding_id)


# ---------------------------------------------------------------------------
# authority audit
# ---------------------------------------------------------------------------


MODULES = (
    "soma/worker_process/environment.py",
    "soma/worker_process/executable.py",
    "soma/worker_process/launch.py",
    "soma/worker_process/cancellation.py",
    "soma/worker_process/__init__.py",
)


def _identifiers(relative: str) -> set[str]:
    import io
    import tokenize

    source = Path(relative).read_text(encoding="utf-8")
    return {
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.NAME
    }


def test_boundary_never_owns_canonical_lifecycle():
    for relative in MODULES:
        identifiers = _identifiers(relative)
        for banned in (
            "RunStore",
            "JobManager",
            "TaskStore",
            "TaskManager",
            "TaskState",
            "OperationLockStore",
            "publish_run_result",
        ):
            assert banned not in identifiers, f"{relative} references {banned}"


def test_boundary_registers_no_gateway_and_is_not_imported_by_the_server():
    server_source = Path("soma/server.py").read_text(encoding="utf-8")
    assert "worker_process" not in server_source
    for relative in MODULES:
        identifiers = _identifiers(relative)
        assert "FastMCP" not in identifiers
        assert "mcp" not in identifiers


def test_cancellation_verdict_cannot_come_from_a_termination_report():
    """The absence check must be the only source of a confirmed verdict."""
    source = Path("soma/worker_process/cancellation.py").read_text(encoding="utf-8")
    assert "recorded_process_is_absent" in source
    # The verdict is computed from absent_after, never from report["terminated"].
    assert 'report.get("terminated")' not in source
