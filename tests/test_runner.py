from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def make_runner(tmp_path: Path, executable: str = "codex", model: str = "") -> CodexRunner:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        codex=CodexConfig(executable=executable, model=model, default_timeout_seconds=1),
        config_dir=tmp_path,
    )
    return CodexRunner(config)


def test_configured_executable_path_is_preferred(tmp_path: Path) -> None:
    exe = tmp_path / "codex.exe"
    exe.write_text("", encoding="utf-8")
    runner = make_runner(tmp_path, executable=str(exe))
    assert runner._resolve_codex_executable() == str(exe)


def test_windowsapps_codex_executable_is_rejected(monkeypatch, tmp_path: Path) -> None:
    windowsapps = r"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe"
    monkeypatch.setattr("codexbridge.runner.shutil.which", lambda name: windowsapps)
    runner = make_runner(tmp_path)
    with pytest.raises(PermissionError, match="WindowsApps"):
        runner._resolve_codex_executable()


def test_model_flag_is_included_only_when_configured(tmp_path: Path) -> None:
    prompt = "plan"
    help_text = "--sandbox"
    with_model = make_runner(tmp_path, model="gpt-5.4")
    without_model = make_runner(tmp_path)
    assert "-m" in with_model._codex_exec_args("codex.exe", "read-only", help_text, prompt)
    assert "-m" not in without_model._codex_exec_args("codex.exe", "read-only", help_text, prompt)


def test_unsupported_approval_flag_is_omitted(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, model="gpt-5.4")
    args = runner._codex_exec_args("codex.exe", "read-only", "--sandbox", "plan")
    assert "--approval-policy" not in args
    assert "--ask-for-approval" not in args


def test_supported_approval_flag_is_included(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    args = runner._codex_exec_args("codex.exe", "read-only", "--sandbox\n--approval-policy", "plan")
    assert "--approval-policy" in args
    assert "never" in args


def test_launch_diagnostics_include_executable_and_cwd(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    diagnostics = runner._subprocess_diagnostics(["codex", "exec"], tmp_path, PermissionError("denied"))
    data = json.loads(diagnostics)
    assert data["executable_attempted"] == "codex"
    assert data["cwd"] == str(tmp_path)
    assert "original_exception" in data


def test_subprocess_capture_uses_utf8_replace(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr("codexbridge.runner.subprocess.run", fake_run)
    runner = make_runner(tmp_path)
    runner._run_subprocess(["codex", "exec"], tmp_path)
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
