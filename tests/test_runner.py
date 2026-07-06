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


def make_runner(
    tmp_path: Path,
    executable: str = "codex",
    model: str = "",
    windows_sandbox: str = "",
    sandbox_private_desktop: bool | None = None,
) -> CodexRunner:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        codex=CodexConfig(
            executable=executable,
            model=model,
            windows_sandbox=windows_sandbox,
            sandbox_private_desktop=sandbox_private_desktop,
            default_timeout_seconds=1,
        ),
        config_dir=tmp_path,
    )
    return CodexRunner(config)


def test_configured_executable_path_is_preferred(tmp_path: Path) -> None:
    exe = tmp_path / "codex.exe"
    exe.write_text("", encoding="utf-8")
    runner = make_runner(tmp_path, executable=str(exe))
    assert runner._resolve_codex_executable() == str(exe)


def test_stale_configured_path_falls_back_to_path(monkeypatch, tmp_path: Path) -> None:
    stale = tmp_path / "old" / "codex.exe"
    fallback = tmp_path / "bin" / "codex.cmd"
    fallback.parent.mkdir()
    fallback.write_text("stub\n", encoding="utf-8")
    monkeypatch.setattr(
        "codexbridge.runner._codex_executable_candidates",
        lambda executable: [str(stale), str(fallback)],
    )
    runner = make_runner(tmp_path, executable=str(stale))
    assert runner._resolve_codex_executable() == str(fallback)


def test_missing_explicit_path_reports_checked_fallbacks(
    monkeypatch, tmp_path: Path
) -> None:
    stale = tmp_path / "old" / "codex.exe"
    monkeypatch.setattr(
        "codexbridge.runner._codex_executable_candidates",
        lambda executable: [str(stale)],
    )
    runner = make_runner(tmp_path, executable=str(stale))
    with pytest.raises(FileNotFoundError, match="No launchable fallback") as exc_info:
        runner._resolve_codex_executable()
    assert str(stale) in str(exc_info.value)


def test_windowsapps_codex_executable_is_rejected(monkeypatch, tmp_path: Path) -> None:
    windowsapps = "C:/Program Files/WindowsApps/OpenAI.Codex/codex.exe"
    monkeypatch.setattr(
        "codexbridge.runner._codex_executable_candidates",
        lambda executable: [windowsapps],
    )
    runner = make_runner(tmp_path)
    with pytest.raises(PermissionError, match="WindowsApps"):
        runner._resolve_codex_executable()


def test_model_flag_is_included_only_when_configured(tmp_path: Path) -> None:
    prompt = "plan"
    help_text = "--sandbox"
    with_model = make_runner(tmp_path, model="gpt-5.4")
    without_model = make_runner(tmp_path)
    assert "-m" in with_model._codex_exec_args(
        "codex.exe", "read-only", help_text, prompt
    )
    assert "-m" not in without_model._codex_exec_args(
        "codex.exe", "read-only", help_text, prompt
    )


def test_unsupported_approval_flag_is_omitted(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, model="gpt-5.4")
    args = runner._codex_exec_args("codex.exe", "read-only", "--sandbox", "plan")
    assert "--approval-policy" not in args
    assert "--ask-for-approval" not in args


def test_supported_approval_flag_is_included(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    args = runner._codex_exec_args(
        "codex.exe", "read-only", "--sandbox\n--approval-policy", "plan"
    )
    assert "--approval-policy" in args
    assert "never" in args


def test_windows_sandbox_override_is_included_when_configured(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, windows_sandbox="unelevated")
    args = runner._codex_exec_args(
        "codex.exe", "workspace-write", "--sandbox", "implement"
    )
    assert "-c" in args
    assert 'windows.sandbox="unelevated"' in args


def test_workspace_write_adds_allowed_directories(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    writable_dirs = [tmp_path / "docs", tmp_path / "src"]

    args = runner._codex_exec_args(
        "codex.exe",
        "workspace-write",
        "--sandbox\n--add-dir",
        "implement",
        writable_dirs=writable_dirs,
    )

    assert args.count("--add-dir") == 2
    assert str(writable_dirs[0]) in args
    assert str(writable_dirs[1]) in args


def test_workspace_write_requires_add_dir_support(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)

    with pytest.raises(ValueError, match="--add-dir"):
        runner._codex_exec_args(
            "codex.exe",
            "workspace-write",
            "--sandbox",
            "implement",
            writable_dirs=[tmp_path / "docs"],
        )


def test_private_desktop_override_is_included_when_configured(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, sandbox_private_desktop=False)
    args = runner._codex_exec_args(
        "codex.exe", "workspace-write", "--sandbox", "implement"
    )
    assert "windows.sandbox_private_desktop=false" in args


def test_safe_command_args_redacts_prompt(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    args = runner._codex_exec_args(
        "codex.exe", "workspace-write", "--sandbox", "secret prompt"
    )
    from codexbridge.runner import _safe_command_args

    assert _safe_command_args(args)[-1] == "<prompt>"


def test_launch_diagnostics_include_executable_and_cwd(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    diagnostics = runner._subprocess_diagnostics(
        ["codex", "exec"], tmp_path, PermissionError("denied")
    )
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


def test_subprocess_env_isolates_unrelated_connector_variables(
    monkeypatch, tmp_path: Path
) -> None:
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr("codexbridge.runner.subprocess.run", fake_run)
    monkeypatch.setenv("MCP_FAKE_CONNECTOR", "1")
    runner = make_runner(tmp_path)
    runner._run_subprocess(["codex", "exec"], tmp_path)

    assert "MCP_FAKE_CONNECTOR" not in captured["env"]
    assert captured["env"]["CODEXBRIDGE_CONNECTOR_ISOLATION"] == "enabled"
