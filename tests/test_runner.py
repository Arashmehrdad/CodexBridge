from __future__ import annotations

import json
from pathlib import Path

from codexbridge.config import AppConfig, CodexConfig, RepoConfig
from codexbridge.runner import CodexRunner


def test_runner_creates_run_artifact_structure(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        codex=CodexConfig(executable="codex", default_timeout_seconds=1),
        config_dir=tmp_path,
    )
    runner = CodexRunner(config)
    run_dir = runner.create_run_dir("unit")
    result = runner._base_result(run_dir, "unit", "sample", "start", 0)
    runner._write_artifacts(
        run_dir,
        input_data={"x": 1},
        prompt="prompt",
        stdout="out",
        stderr="err",
        result=result,
    )
    assert (run_dir / "input.json").exists()
    assert (run_dir / "prompt.txt").read_text(encoding="utf-8") == "prompt"
    saved = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert saved["tool"] == "unit"
    assert "changed_files" in saved

