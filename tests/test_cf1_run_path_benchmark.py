from __future__ import annotations

from pathlib import Path

import soma.run_store as run_store_module
from soma.cf1_run_path_benchmark import (
    CF1_RUN_PATH_BENCHMARK_VERSION,
    measure_run_path,
)
from soma.config import AppConfig, CodexConfig, RepoConfig
from soma.job_manager import JobManager


def _make_manager(tmp_path: Path) -> JobManager:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        codex=CodexConfig(enabled=False),
        config_dir=tmp_path,
    )
    return JobManager(config, config_path)


def _seed_runs(manager: JobManager) -> str:
    selected_run_id = ""
    detail = "x" * 4096
    for index in range(20):
        run_id = f"20260721T0100{index:02d}Z_project_command_{index:08x}"
        run_dir = manager.config.resolve_runs_dir() / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "stdout.txt").write_text(f"stdout-{index}\n{detail}", encoding="utf-8")
        (run_dir / "stderr.txt").write_text(f"stderr-{index}\n", encoding="utf-8")
        manager.store.create_run(
            run_id=run_id,
            repo_name="sample",
            tool="project_command",
            run_dir=run_dir,
            input_data={"command_id": "pytest", "detail": detail},
            status="completed",
        )
        manager.store.update_run(
            run_id,
            status="completed",
            current_phase="result",
            ended_at="2026-07-21T01:10:00+00:00",
            duration_seconds=float(index + 1),
            exit_code=0,
            summary=f"completed-{index}",
            result_json={
                "run_id": run_id,
                "repo_name": "sample",
                "tool": "project_command",
                "status": "completed",
                "classification": "success",
                "summary": f"completed-{index}",
                "detail": detail,
                "error": "",
                "safety_failure": False,
            },
        )
        manager.store.append_event(
            run_id,
            level="info",
            stage="result",
            message=f"event-{index}",
            data={"detail": detail[:128]},
            update_run_metadata=False,
        )
        selected_run_id = run_id
    return selected_run_id


def test_cf1_benchmarks_each_current_run_path_independently(
    tmp_path: Path, monkeypatch
) -> None:
    manager = _make_manager(tmp_path)
    run_id = _seed_runs(manager)
    authoritative = manager.store.get_run(run_id)

    decode_count = 0
    original_loads = run_store_module.loads

    def counted_loads(value):
        nonlocal decode_count
        decode_count += 1
        return original_loads(value)

    monkeypatch.setattr(run_store_module, "loads", counted_loads)

    operations = {
        "list": lambda: manager.list_runs("sample", "completed", 20),
        "status": lambda: manager.get_status(run_id),
        "control": lambda: manager.get_control_status(run_id),
        "events": lambda: manager.get_events(run_id, 50),
        "output": lambda: manager.get_output(run_id, "combined", 20_000),
        "result": lambda: manager.get_result(run_id),
    }

    measurements = {
        name: measure_run_path(
            name=name,
            operation=operation,
            authoritative_record=authoritative,
            iterations=3,
            json_decode_counter=lambda: decode_count,
        )
        for name, operation in operations.items()
    }

    assert tuple(measurements) == (
        "list",
        "status",
        "control",
        "events",
        "output",
        "result",
    )
    assert all(
        item.version == CF1_RUN_PATH_BENCHMARK_VERSION
        for item in measurements.values()
    )
    assert all(item.serialized_bytes > 0 for item in measurements.values())
    assert all(item.result_sha256 for item in measurements.values())
    assert all(item.authoritative_sha256 for item in measurements.values())
    assert measurements["control"].json_decode_calls == 0
    assert all(
        measurements[name].json_decode_calls > 0
        for name in ("list", "status", "events", "output", "result")
    )
    assert measurements["list"].serialized_bytes > measurements["status"].serialized_bytes
    assert measurements["output"].serialized_bytes > measurements["control"].serialized_bytes


def test_cf1_run_path_measurement_records_latency_allocations_and_hashes() -> None:
    counter = 0

    def operation() -> dict:
        nonlocal counter
        counter += 1
        return {"status": "completed", "summary": "stable"}

    measurement = measure_run_path(
        name="stable",
        operation=operation,
        authoritative_record={"full": "record"},
        iterations=5,
    )

    assert measurement.version == "cf1.0.run-path.v1"
    assert measurement.iterations == 5
    assert counter == 5
    assert measurement.serialized_bytes > 0
    assert len(measurement.result_sha256) == 64
    assert len(measurement.authoritative_sha256) == 64
    assert measurement.p50_latency_ms >= 0
    assert measurement.p95_latency_ms >= measurement.p50_latency_ms
    assert measurement.peak_python_alloc_bytes > 0
    assert measurement.json_decode_calls == 0


def test_cf1_run_path_measurement_rejects_non_deterministic_payloads() -> None:
    counter = 0

    def operation() -> dict:
        nonlocal counter
        counter += 1
        return {"counter": counter}

    try:
        measure_run_path(
            name="unstable",
            operation=operation,
            authoritative_record={},
            iterations=2,
            require_deterministic_payload=True,
        )
    except ValueError as exc:
        assert "non-deterministic payload" in str(exc)
    else:
        raise AssertionError("Expected non-deterministic measurement to fail")
