from __future__ import annotations

import threading
from pathlib import Path

from soma.run_store import RunStore, TERMINAL_STATUSES, utc_now


def test_concurrent_status_and_result_polling_never_observes_terminal_without_result(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "runs")
    run_id = "20260711T180000Z_project_command_deadbeef"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    store.create_run(
        run_id=run_id,
        repo_name="sample",
        tool="project_command",
        run_dir=run_dir,
        input_data={"repo_name": "sample", "command_id": "pytest"},
    )
    store.update_run(run_id, status="running", started_at=utc_now())
    start = threading.Barrier(5)
    finished = threading.Event()
    violations: list[dict] = []

    def poll() -> None:
        start.wait()
        while not finished.is_set():
            observed = store.get_run(run_id)
            if observed["status"] in TERMINAL_STATUSES and not observed["result"]:
                violations.append(observed)
                finished.set()

    readers = [threading.Thread(target=poll) for _ in range(4)]
    for reader in readers:
        reader.start()
    start.wait()
    result = {
        "run_id": run_id,
        "status": "completed",
        "classification": "success",
        "process_success": True,
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "error": "",
    }
    store.update_run(
        run_id,
        status="completed",
        ended_at=utc_now(),
        exit_code=0,
        result_json=result,
    )
    observed = store.get_run(run_id)
    assert observed["status"] == "completed"
    assert observed["result"] == result
    finished.set()
    for reader in readers:
        reader.join(timeout=5)
        assert not reader.is_alive()
    assert violations == []
