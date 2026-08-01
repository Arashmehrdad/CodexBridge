from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from soma import reconciliation_status
from soma.reconciliation_status import (
    PATH_JOB_RUNS,
    PATH_TASKS,
    PATH_SUPERVISORS,
    PATH_WORKFLOWS,
    PATH_SSH_ACTIVATION,
    STARTUP_PATHS,
    STATE_FAILED,
    STATE_OK,
    STATE_RUNNING,
    ReconciliationRecorder,
    claim,
    read_status,
    resolve,
)


def _all_paths_ok(runs_dir: Path) -> None:
    for path in STARTUP_PATHS:
        resolve(runs_dir, path, ok=True)


def test_never_recorded_is_healthy_but_explicitly_labelled(tmp_path: Path) -> None:
    # Nothing has started, so no recovery information has been lost. A check
    # that is red on every fresh install is a check operators stop reading.
    status = read_status(tmp_path / "runs")

    assert status["ok"] is True
    assert status["available"] is False
    assert status["state"] == "never_recorded"
    assert status["paths"] == {}


def test_partial_record_is_unhealthy(tmp_path: Path) -> None:
    # Once anything reports, a path that should have run and did not is a
    # missing recovery decision, not an absence of work.
    runs_dir = tmp_path / "runs"
    resolve(runs_dir, PATH_JOB_RUNS, ok=True)

    status = read_status(runs_dir)

    assert status["ok"] is False
    assert status["state"] == "recorded"
    assert PATH_TASKS in status["missing"]
    assert PATH_SUPERVISORS in status["missing"]
    assert PATH_WORKFLOWS in status["missing"]


def test_all_paths_succeeding_is_healthy(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _all_paths_ok(runs_dir)

    status = read_status(runs_dir)

    assert status["ok"] is True
    assert status["failed"] == []
    assert status["incomplete"] == []
    assert status["missing"] == []
    assert status["paths"][PATH_TASKS]["state"] == STATE_OK


def test_one_failed_path_makes_the_whole_status_unhealthy(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _all_paths_ok(runs_dir)
    resolve(
        runs_dir,
        PATH_WORKFLOWS,
        ok=False,
        detail="RuntimeError: store unavailable",
        exception_type="RuntimeError",
    )

    status = read_status(runs_dir)

    assert status["ok"] is False
    assert status["failed"] == [PATH_WORKFLOWS]
    assert status["paths"][PATH_WORKFLOWS]["exception_type"] == "RuntimeError"
    assert "store unavailable" in status["paths"][PATH_WORKFLOWS]["detail"]


def test_interrupted_reconciliation_stays_visible(tmp_path: Path) -> None:
    """A process that dies mid-reconciliation must not look like a clean start."""
    runs_dir = tmp_path / "runs"
    _all_paths_ok(runs_dir)
    claim(runs_dir, PATH_JOB_RUNS)  # claimed, never resolved

    status = read_status(runs_dir)

    assert status["ok"] is False
    assert status["incomplete"] == [PATH_JOB_RUNS]
    assert status["paths"][PATH_JOB_RUNS]["state"] == STATE_RUNNING


def test_recorder_publishes_failure_and_suppresses_by_default(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _all_paths_ok(runs_dir)

    with ReconciliationRecorder(runs_dir, PATH_TASKS) as recorder:
        raise RuntimeError("reconciliation exploded")

    assert recorder.failed is True
    status = read_status(runs_dir)
    assert status["ok"] is False
    assert status["failed"] == [PATH_TASKS]
    assert status["paths"][PATH_TASKS]["exception_type"] == "RuntimeError"
    assert "reconciliation exploded" in status["paths"][PATH_TASKS]["detail"]


def test_recorder_can_re_raise_when_suppression_is_disabled(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    with pytest.raises(RuntimeError):
        with ReconciliationRecorder(runs_dir, PATH_TASKS, suppress=False):
            raise RuntimeError("must propagate")

    assert read_status(runs_dir)["failed"] == [PATH_TASKS]


def test_recorder_success_clears_a_previous_failure(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _all_paths_ok(runs_dir)
    resolve(runs_dir, PATH_SSH_ACTIVATION, ok=False, detail="earlier failure")
    assert read_status(runs_dir)["ok"] is False

    with ReconciliationRecorder(runs_dir, PATH_SSH_ACTIVATION):
        pass

    status = read_status(runs_dir)
    assert status["ok"] is True
    assert status["paths"][PATH_SSH_ACTIVATION]["state"] == STATE_OK


def test_bookkeeping_failure_never_blocks_reconciliation(
    tmp_path: Path, monkeypatch
) -> None:
    """Recording is best-effort; it must not stop the work it observes."""
    runs_dir = tmp_path / "runs"

    def explode(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(reconciliation_status, "claim", explode)
    monkeypatch.setattr(reconciliation_status, "resolve", explode)

    performed = False
    with ReconciliationRecorder(runs_dir, PATH_TASKS):
        performed = True

    assert performed is True


def test_self_check_reports_reconciliation_and_fails_readiness(tmp_path) -> None:
    from soma.config import load_config
    from soma.self_check import run_self_check

    runs_dir = tmp_path / "runs"
    _all_paths_ok(runs_dir)
    resolve(runs_dir, PATH_JOB_RUNS, ok=False, detail="lost recovery information")

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "repos:\n"
        "  sample:\n"
        f'    path: "{repo.as_posix()}"\n'
        f'runs_dir: "{runs_dir.as_posix()}"\n',
        encoding="utf-8",
    )

    result = run_self_check(config=load_config(config_path), config_path=config_path)

    assert result["checks"]["startup_reconciliation"]["ok"] is False
    assert result["checks"]["startup_reconciliation"]["failed"] == [PATH_JOB_RUNS]
    # Readiness is the aggregate of every check, so this must fail it.
    assert result["ok"] is False
