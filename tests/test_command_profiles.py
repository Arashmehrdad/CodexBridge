"""
Tests for codexbridge/command_profiles.py.
Covers blocked-pattern rejection, unknown IDs, built-in profiles,
repo-level overrides, and shell=False execution.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.command_profiles import (
    BUILTIN_PROFILES,
    CommandProfileSpec,
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

@pytest.mark.parametrize("argv", [
    ["pip install requests"],          # single-element pip install
    ["npm install express"],            # single-element npm install
    ["cmd.exe", "/c", "dir"],
    ["powershell", "-Command", "Get-Process"],
    ["Invoke-Expression", "something"],
    ["rm -rf /"],                       # single-element rm -rf
    ["ssh", "user@host"],
    ["curl", "https://example.com"],
    ["wget", "https://example.com/file"],
    ["echo", "a; rm -rf /"],
    ["echo", "a && b"],
    ["echo", "a || b"],
    ["echo", "a | b"],
    ["echo", "`rm -rf /`"],
    ["echo", "$(whoami)"],
])
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
    spec.validate()  # should not raise


# ---------------------------------------------------------------------------
# Built-in profiles self-validate
# ---------------------------------------------------------------------------

def test_all_builtin_profiles_validate() -> None:
    for name, spec in BUILTIN_PROFILES.items():
        spec.validate()  # should not raise
        assert spec.command_id == name


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
    import codexbridge.command_profiles as cp
    monkeypatch.setattr(cp, "MAX_OUTPUT_BYTES", 10)
    spec = CommandProfileSpec(
        command_id="big_output",
        argv=["python", "-c", "print('x' * 100)"],
        timeout_seconds=10,
    )
    result = run_command_profile(spec, tmp_path)
    assert result["output_truncated"] is True
