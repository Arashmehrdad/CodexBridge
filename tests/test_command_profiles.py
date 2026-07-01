"""
Tests for codexbridge/command_profiles.py.
Covers blocked-pattern rejection, unknown IDs, built-in profiles,
repo-level overrides, repository virtual environments, and shell=False execution.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import codexbridge.command_profiles as cp
from codexbridge.command_profiles import (
    BUILTIN_PROFILES,
    CommandProfileSpec,
    find_repo_python,
    resolve_command_profile,
    run_command_profile,
)


# ---------------------------------------------------------------------------
# resolve_command_profile
# ---------------------------------------------------------------------------


def test_resolve_known_builtin() -> None:
    spec = resolve_command_profile("pytest")
    assert spec.command_id == "pytest"
    assert "pytest" in spec.argv
    assert spec.async_only is True
    assert spec.timeout_seconds == 600


def test_ruff_format_has_matching_write_profile() -> None:
    check = resolve_command_profile("ruff_format_check")
    formatter = resolve_command_profile("ruff_format")

    assert check.argv == ["python", "-m", "ruff", "format", "--check", "."]
    assert check.writes_files is False
    assert formatter.argv == ["python", "-m", "ruff", "format", "."]
    assert formatter.writes_files is True


def test_git_status_is_read_only() -> None:
    status = resolve_command_profile("git_status")

    assert status.argv == ["git", "status", "--short", "--branch"]
    assert status.timeout_seconds == 30
    assert status.description == "Read repository branch and working-tree status"
    assert status.writes_files is False


def test_existing_builtin_profile_ids_remain_unchanged() -> None:
    assert set(BUILTIN_PROFILES) == {
        "pytest",
        "ruff_check",
        "ruff_format_check",
        "ruff_format",
        "mypy",
        "pip_check",
        "git_status",
        "git_diff_check",
    }


def test_resolve_unknown_id_raises() -> None:
    with pytest.raises(ValueError, match="Unknown command_id"):
        resolve_command_profile("nonexistent_command")


def test_resolve_invalid_id_raises() -> None:
    with pytest.raises(ValueError, match="Invalid command_id"):
        resolve_command_profile("bad id with spaces")


def test_repo_override_shadows_builtin() -> None:
    repo_profiles = [
        {"command_id": "pytest", "argv": ["python", "-m", "pytest", "-x", "-q"]},
    ]
    spec = resolve_command_profile("pytest", repo_profiles)
    assert "-x" in spec.argv


def test_repo_pytest_override_inherits_async_only_default() -> None:
    repo_profiles = [
        {
            "command_id": "pytest",
            "argv": ["python", "-m", "pytest", "tests/unit", "-q"],
        },
    ]

    spec = resolve_command_profile("pytest", repo_profiles)

    assert spec.async_only is True
    assert spec.timeout_seconds == 600
    assert spec.description == "Run pytest in quiet mode as a durable async command"


def test_repo_override_unknown_id_falls_through_to_builtin() -> None:
    repo_profiles = [
        {"command_id": "custom_tool", "argv": ["echo", "hello"]},
    ]
    # pytest is a builtin, not in repo_profiles, so it should still resolve
    spec = resolve_command_profile("pytest", repo_profiles)
    assert spec.command_id == "pytest"


# ---------------------------------------------------------------------------
# CommandProfileSpec.validate – blocked patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["pip install requests"],
        ["npm install express"],
        ["cmd.exe", "/c", "dir"],
        ["powershell", "-Command", "Get-Process"],
        ["Invoke-Expression", "something"],
        ["rm -rf /"],
        ["ssh", "user@host"],
        ["curl", "https://example.com"],
        ["wget", "https://example.com/file"],
        ["echo", "a; rm -rf /"],
        ["echo", "a && b"],
        ["echo", "a || b"],
        ["echo", "a | b"],
        ["echo", "`rm -rf /`"],
        ["echo", "$(whoami)"],
    ],
)
def test_blocked_argv_patterns(argv: list[str]) -> None:
    spec = CommandProfileSpec(command_id="test_cmd", argv=argv)
    with pytest.raises(ValueError, match="Blocked pattern"):
        spec.validate()


def test_empty_argv_raises() -> None:
    spec = CommandProfileSpec(command_id="test_cmd", argv=[])
    with pytest.raises(ValueError, match="argv must not be empty"):
        spec.validate()


def test_valid_custom_profile() -> None:
    spec = CommandProfileSpec(
        command_id="custom_check",
        argv=["python", "-m", "mypy", "src/"],
        timeout_seconds=30,
    )
    spec.validate()


# ---------------------------------------------------------------------------
# Built-in profiles self-validate
# ---------------------------------------------------------------------------


def test_all_builtin_profiles_validate() -> None:
    for name, spec in BUILTIN_PROFILES.items():
        spec.validate()
        assert spec.command_id == name


# ---------------------------------------------------------------------------
# Repository virtual-environment resolution
# ---------------------------------------------------------------------------


def _create_repo_python(repo_root: Path) -> tuple[Path, Path]:
    relative = (
        Path(".venv/Scripts/python.exe")
        if os.name == "nt"
        else Path(".venv/bin/python")
    )
    python_executable = repo_root / relative
    python_executable.parent.mkdir(parents=True)
    python_executable.write_text("", encoding="utf-8")
    return python_executable.absolute(), python_executable.parent.parent.absolute()


def test_find_repo_python_prefers_local_virtualenv(tmp_path: Path) -> None:
    expected_python, expected_venv = _create_repo_python(tmp_path)

    python_executable, virtual_env = find_repo_python(tmp_path)

    assert python_executable == expected_python
    assert virtual_env == expected_venv


def test_run_command_uses_repo_virtualenv(tmp_path: Path, monkeypatch) -> None:
    expected_python, expected_venv = _create_repo_python(tmp_path)
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    monkeypatch.setattr(cp.subprocess, "run", fake_run)
    spec = CommandProfileSpec(
        command_id="ruff_check",
        argv=["python", "-m", "ruff", "check", "."],
        timeout_seconds=10,
    )

    result = run_command_profile(spec, tmp_path)

    assert captured["argv"][0] == str(expected_python)
    assert captured["kwargs"]["cwd"] == tmp_path
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["env"]["VIRTUAL_ENV"] == str(expected_venv)
    assert captured["kwargs"]["env"]["PATH"].split(os.pathsep)[0] == str(
        expected_python.parent
    )
    assert result["argv"][0] == str(expected_python)
    assert set(result) == {
        "ok",
        "command_id",
        "argv",
        "exit_code",
        "timed_out",
        "duration_seconds",
        "stdout",
        "stderr",
        "output_truncated",
        "error",
    }


def test_run_command_merges_explicit_environment(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["env"] = kwargs["env"]
        return SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    monkeypatch.setattr(cp.subprocess, "run", fake_run)
    spec = CommandProfileSpec(
        command_id="env_check",
        argv=["python", "-c", "print('ok')"],
        timeout_seconds=10,
    )

    result = run_command_profile(
        spec, tmp_path, extra_env={"TMP": "isolated", "CUSTOM_FLAG": "yes"}
    )

    assert result["ok"] is True
    assert captured["env"]["TMP"] == "isolated"
    assert captured["env"]["CUSTOM_FLAG"] == "yes"


def test_repo_virtualenv_path_supports_bare_tools(tmp_path: Path, monkeypatch) -> None:
    expected_python, _ = _create_repo_python(tmp_path)
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(cp.subprocess, "run", fake_run)
    spec = CommandProfileSpec(
        command_id="ruff_direct",
        argv=["ruff", "check", "."],
        timeout_seconds=10,
    )

    result = run_command_profile(spec, tmp_path)

    assert captured["argv"] == spec.argv
    assert captured["env"]["PATH"].split(os.pathsep)[0] == str(expected_python.parent)
    assert result["argv"] == spec.argv


# ---------------------------------------------------------------------------
# run_command_profile – shell=False execution
# ---------------------------------------------------------------------------


def test_run_command_success(tmp_path: Path) -> None:
    spec = CommandProfileSpec(
        command_id="echo_test",
        argv=["python", "-c", "print('hello')"],
        timeout_seconds=10,
    )
    result = run_command_profile(spec, tmp_path)
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]
    assert result["timed_out"] is False
    assert result["command_id"] == "echo_test"


def test_run_command_failure(tmp_path: Path) -> None:
    spec = CommandProfileSpec(
        command_id="fail_test",
        argv=["python", "-c", "import sys; sys.exit(1)"],
        timeout_seconds=10,
    )
    result = run_command_profile(spec, tmp_path)
    assert result["ok"] is False
    assert result["exit_code"] == 1


def test_run_command_timeout(tmp_path: Path) -> None:
    spec = CommandProfileSpec(
        command_id="timeout_test",
        argv=["python", "-c", "import time; time.sleep(5)"],
        timeout_seconds=1,
    )
    result = run_command_profile(spec, tmp_path)
    assert result["ok"] is False
    assert result["timed_out"] is True
    assert result["exit_code"] == 124


def test_run_command_invalid_binary(tmp_path: Path) -> None:
    spec = CommandProfileSpec(
        command_id="missing_test",
        argv=["this_binary_does_not_exist_12345"],
        timeout_seconds=5,
    )
    result = run_command_profile(spec, tmp_path)
    assert result["ok"] is False
    assert result["exit_code"] == 1


def test_run_command_output_truncation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cp, "MAX_OUTPUT_BYTES", 10)
    spec = CommandProfileSpec(
        command_id="big_output",
        argv=["python", "-c", "print('x' * 100)"],
        timeout_seconds=10,
    )
    result = run_command_profile(spec, tmp_path)
    assert result["output_truncated"] is True
