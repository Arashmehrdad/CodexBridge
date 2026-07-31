from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from soma.config import AppConfig, ExecutableProfileConfig, RepoConfig
from soma.executable_profiles import build_local_executable_run_request
from soma.job_worker import JobWorker
from soma.process_control import ProcessContainmentUncertain
from soma.run_store import RunStore, utc_now


def _write_config(config_path: Path, repo: Path, runs_dir: Path) -> None:
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
                f'    executable_path: "{Path(sys.executable).as_posix()}"',
                "    target: local",
                "    autonomy_profile: permissive",
                "    working_directory_policy: arbitrary",
                "    environment_policy: arbitrary",
                "    stdin_mode: bytes",
                "    stdout_mode: protected_artifact",
                "    stderr_mode: protected_artifact",
                "    unrestricted_argv: true",
                "    allow_no_timeout: true",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _make_worker(
    tmp_path: Path,
    *,
    argv: list[str],
    stdin_bytes: bytes | None = None,
    timeout_seconds: int | None = 30,
) -> tuple[JobWorker, RunStore, dict, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, repo, runs_dir)
    profile = ExecutableProfileConfig(
        profile_id="powershell",
        enabled=True,
        executable_path=str(Path(sys.executable).resolve()),
        target="local",
        autonomy_profile="permissive",
        working_directory_policy="arbitrary",
        environment_policy="arbitrary",
        stdin_mode="bytes",
        stdout_mode="protected_artifact",
        stderr_mode="protected_artifact",
        unrestricted_argv=True,
        allow_no_timeout=True,
    )
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        executable_profiles={"powershell": profile},
        runs_dir=str(runs_dir),
        config_dir=tmp_path,
    )
    input_data = build_local_executable_run_request(
        config,
        "powershell",
        argv,
        working_directory=str(repo),
        environment={},
        stdin_bytes=stdin_bytes,
        timeout_seconds=timeout_seconds,
    )
    run_id = "20260716T000000Z_executable_profile_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data=input_data,
    )
    worker = JobWorker(config_path, run_id)
    worker.event = lambda *args, **kwargs: True
    return worker, store, input_data, run_dir


def test_executable_worker_preserves_quoting_and_binary_streams(
    monkeypatch, tmp_path: Path
) -> None:
    payload = b"\x00\xffbinary\r\ntext"
    sensitive_args = ["a b", "", 'a"b', "'quoted'", "trailing\\"]
    script = (
        "import json,sys; "
        "sys.stdout.buffer.write(sys.stdin.buffer.read()); "
        "sys.stderr.buffer.write(json.dumps(sys.argv[1:]).encode('utf-8'))"
    )
    worker, _store, input_data, run_dir = _make_worker(
        tmp_path,
        argv=["-c", script, *sensitive_args],
        stdin_bytes=payload,
    )
    monkeypatch.setattr(worker.store, "attach_child_pid", lambda *args, **kwargs: True)

    result = worker._execute_executable_profile(utc_now(), input_data)

    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert result["argv"] == ["-c", script, *sensitive_args]
    assert (run_dir / "stdout.bin").read_bytes() == payload
    assert (
        json.loads((run_dir / "stderr.bin").read_text(encoding="utf-8"))
        == sensitive_args
    )
    assert result["stdout_bytes"] == len(payload)
    assert result["stderr_bytes"] == len((run_dir / "stderr.bin").read_bytes())
    assert result["output_truncated"] is False


def test_executable_worker_rejects_identity_change_before_launch(
    monkeypatch, tmp_path: Path
) -> None:
    worker, _store, input_data, _run_dir = _make_worker(
        tmp_path,
        argv=["-c", "print('unused')"],
    )
    changed_identity = dict(input_data["executable_identity"])
    changed_identity["observed_sha256"] = "0" * 64
    input_data["executable_identity"] = changed_identity
    launched = False

    def unexpected_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("process launch must not occur")

    monkeypatch.setattr("soma.job_worker.subprocess.Popen", unexpected_launch)

    with pytest.raises(ValueError, match="identity does not match"):
        worker._execute_executable_profile(utc_now(), input_data)
    assert launched is False


@pytest.fixture(autouse=True)
def _synthetic_child_identity(monkeypatch):
    """Deterministic identity for the synthetic child handles in this module.

    These fakes are not live processes, so a real capture correctly refuses to
    attach them. Real handles keep the real path.
    """
    monkeypatch.setattr(
        "soma.job_worker.capture_launch_identity",
        lambda process, **_kwargs: f"{process.pid}:synthetic:1",
    )


def test_executable_worker_terminates_child_when_attachment_fails(
    monkeypatch, tmp_path: Path
) -> None:
    worker, _store, input_data, _run_dir = _make_worker(
        tmp_path,
        argv=["-c", "print('unused')"],
    )

    class FakeProcess:
        pid = 43210
        stdin = None
        stdout = None
        stderr = None

    terminated: list[int] = []
    monkeypatch.setattr(
        "soma.job_worker.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    monkeypatch.setattr(worker.store, "attach_child_pid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "soma.job_worker.require_identity_scoped_cleanup",
        lambda pid, identity, **_kwargs: (
            terminated.append(pid)
            or {
                "pid": pid,
                "terminated": True,
                "ownership_proven": bool(identity),
            }
        ),
    )

    with pytest.raises(RuntimeError, match="lease was lost"):
        worker._execute_executable_profile(utc_now(), input_data)
    assert terminated == [43210]


def test_executable_worker_cleans_up_after_attachment_exception(
    monkeypatch, tmp_path: Path
) -> None:
    worker, _store, input_data, _run_dir = _make_worker(
        tmp_path,
        argv=["-c", "print('unused')"],
    )

    class FakeProcess:
        pid = 43211
        stdin = None
        stdout = None
        stderr = None

    cleaned: list[tuple[int, str]] = []
    monkeypatch.setattr(
        "soma.job_worker.subprocess.Popen", lambda *args, **kwargs: FakeProcess()
    )
    monkeypatch.setattr(
        worker.store,
        "attach_child_pid",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("database unavailable")),
    )
    monkeypatch.setattr(
        "soma.job_worker.require_identity_scoped_cleanup",
        lambda pid, identity, **_kwargs: (
            cleaned.append((pid, identity)) or {"terminated": True}
        ),
    )

    with pytest.raises(OSError, match="database unavailable"):
        worker._execute_executable_profile(utc_now(), input_data)
    assert cleaned == [(43211, "43211:synthetic:1")]


def test_executable_worker_propagates_unconfirmed_attachment_cleanup(
    monkeypatch, tmp_path: Path
) -> None:
    worker, _store, input_data, _run_dir = _make_worker(
        tmp_path,
        argv=["-c", "print('unused')"],
    )

    class FakeProcess:
        pid = 43212
        stdin = None
        stdout = None
        stderr = None

    monkeypatch.setattr(
        "soma.job_worker.subprocess.Popen", lambda *args, **kwargs: FakeProcess()
    )
    monkeypatch.setattr(worker.store, "attach_child_pid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "soma.job_worker.require_identity_scoped_cleanup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProcessContainmentUncertain(
                {
                    "pid": 43212,
                    "method": "refused_unreadable_identity",
                    "terminated": False,
                    "error": "identity unreadable",
                }
            )
        ),
    )

    with pytest.raises(ProcessContainmentUncertain):
        worker._execute_executable_profile(utc_now(), input_data)


def test_executable_worker_marks_verified_timeout_termination(
    monkeypatch, tmp_path: Path
) -> None:
    worker, _store, input_data, run_dir = _make_worker(
        tmp_path,
        argv=["-c", "print('unused')"],
        timeout_seconds=1,
    )

    class FakePipe:
        def read(self, _size: int) -> bytes:
            return b""

        def close(self) -> None:
            return None

    class FakeProcess:
        pid = 54321
        stdin = None
        stdout = FakePipe()
        stderr = FakePipe()

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    monkeypatch.setattr(
        "soma.job_worker.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    monkeypatch.setattr(worker.store, "attach_child_pid", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "soma.job_worker.require_identity_scoped_cleanup",
        lambda pid, identity, **_kwargs: {
            "terminated": True,
            "pid": pid,
            "ownership_proven": bool(identity),
        },
    )

    result = worker._execute_executable_profile(utc_now(), input_data)

    assert result["status"] == "timed_out"
    assert result["exit_code"] == 124
    assert result["timed_out"] is True
    assert result["termination"] == {
        "terminated": True,
        "pid": 54321,
        "ownership_proven": True,
    }
    assert (run_dir / "stdout.bin").read_bytes() == b""
    assert (run_dir / "stderr.bin").read_bytes() == b""
