"""
Tests for soma/command_profiles.py.
Covers blocked-pattern rejection, unknown IDs, built-in profiles,
repo-level overrides, repository virtual environments, and shell=False execution.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import soma.command_profiles as cp
from soma.command_profiles import (
    BASH_N_PATH_COMMAND_ID,
    BUILTIN_PROFILES,
    GIT_READONLY_COMMAND_ID,
    JSON_VALIDATE_PATH_COMMAND_ID,
    PYTEST_PATH_COMMAND_ID,
    PY_COMPILE_PATH_COMMAND_ID,
    CommandProfileSpec,
    build_bash_n_path_profile,
    build_git_readonly_profile,
    build_json_validate_path_profile,
    build_py_compile_path_profile,
    build_pytest_path_profile,
    find_repo_python,
    resolve_command_profile,
    run_command_profile,
    validate_repo_relative_command_path,
    validate_and_normalize_pytest_target,
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


def test_git_status_is_read_only() -> None:
    status = resolve_command_profile("git_status")

    assert status.argv == ["git", "status", "--short", "--branch"]
    assert status.timeout_seconds == 30
    assert status.description == "Read repository branch and working-tree status"
    assert status.writes_files is False


def test_existing_builtin_profile_ids_remain_unchanged() -> None:
    assert set(BUILTIN_PROFILES) == {
        "pytest",
        "pip_check",
        "git_status",
        "git_readonly",
    }


def test_build_pytest_path_profile_for_directory(tmp_path: Path) -> None:
    target_dir = tmp_path / "tests" / "unit"
    target_dir.mkdir(parents=True)

    profile = build_pytest_path_profile(tmp_path, "tests/unit")

    assert profile.command_id == PYTEST_PATH_COMMAND_ID
    assert profile.argv == ["python", "-m", "pytest", "-q", "tests/unit"]
    assert profile.timeout_seconds == 600
    assert profile.async_only is True
    assert profile.writes_files is False


def test_build_pytest_path_profile_for_python_file(tmp_path: Path) -> None:
    target_file = tmp_path / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    profile = build_pytest_path_profile(tmp_path, "tests/test_api.py")

    assert profile.argv == ["python", "-m", "pytest", "-q", "tests/test_api.py"]


def test_build_py_compile_path_profile(tmp_path: Path) -> None:
    target_file = tmp_path / "pkg" / "module.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("x = 1\n", encoding="utf-8")

    profile = build_py_compile_path_profile(tmp_path, "pkg/module.py")

    assert profile.command_id == PY_COMPILE_PATH_COMMAND_ID
    assert profile.argv == ["python", "-m", "py_compile", "pkg/module.py"]


def test_build_bash_n_path_profile(tmp_path: Path) -> None:
    target_file = tmp_path / "scripts" / "check.sh"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("echo ok\n", encoding="utf-8")

    profile = build_bash_n_path_profile(tmp_path, "scripts/check.sh")

    assert profile.command_id == BASH_N_PATH_COMMAND_ID
    assert profile.argv == ["bash", "-n", "scripts/check.sh"]


def test_build_json_validate_path_profile(tmp_path: Path) -> None:
    target_file = tmp_path / "data" / "config.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text('{"ok": true}\n', encoding="utf-8")

    profile = build_json_validate_path_profile(tmp_path, "data/config.json")

    assert profile.command_id == JSON_VALIDATE_PATH_COMMAND_ID
    assert profile.argv == ["python", "-m", "json.tool", "data/config.json"]


def test_build_git_readonly_profile_uses_fixed_enum() -> None:
    profile = build_git_readonly_profile("ls_files")
    assert profile.command_id == GIT_READONLY_COMMAND_ID
    assert profile.argv == [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
    ]


def test_pytest_target_normalizes_node_selector_and_windows_separators(
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    normalized = validate_and_normalize_pytest_target(
        tmp_path, r"tests\test_api.py::TestThing::test_ok"
    )

    assert normalized == "tests/test_api.py::TestThing::test_ok"


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("", "must not be empty"),
        ("   ", "must not be empty"),
        ("../tests/test_api.py", "must not contain traversal segments"),
        ("tests/../test_api.py", "must not contain traversal segments"),
        ("/tmp/test_api.py", "must be repository-relative"),
        (r"C:\repo\tests\test_api.py", "must not include a drive prefix"),
        (r"\\server\share\tests\test_api.py", "must be repository-relative"),
        ("tests/*.py", "must not contain wildcards"),
        ("-k smoke", "must not start with an option"),
        ("missing/test_api.py", "does not exist"),
        ("docs/readme.md", "must be a .py file"),
        ("tests/test_api.py\x00", "contains control characters"),
    ],
)
def test_pytest_target_rejects_invalid_inputs(
    tmp_path: Path, target: str, error: str
) -> None:
    target_file = tmp_path / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    docs_file = tmp_path / "docs" / "readme.md"
    docs_file.parent.mkdir(parents=True)
    docs_file.write_text("# hi\n", encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        validate_and_normalize_pytest_target(tmp_path, target)


def test_validate_repo_relative_command_path_rejects_wrong_suffix(
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "docs" / "readme.md"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("# hi\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must use one of"):
        validate_repo_relative_command_path(
            tmp_path, "docs/readme.md", allowed_suffixes={".json"}
        )


def test_pytest_target_rejects_non_file_non_directory(tmp_path: Path) -> None:
    special_path = tmp_path / "tests" / "special"
    special_path.parent.mkdir(parents=True)
    special_path.write_text("", encoding="utf-8")

    original_exists = Path.exists
    original_is_dir = Path.is_dir
    original_is_file = Path.is_file

    def fake_exists(self: Path) -> bool:
        if self == special_path:
            return True
        return original_exists(self)

    def fake_is_dir(self: Path) -> bool:
        if self == special_path:
            return False
        return original_is_dir(self)

    def fake_is_file(self: Path) -> bool:
        if self == special_path:
            return False
        return original_is_file(self)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    monkeypatch.setattr(Path, "is_file", fake_is_file)
    try:
        with pytest.raises(ValueError, match="must be a file or directory"):
            validate_and_normalize_pytest_target(tmp_path, "tests/special")
    finally:
        monkeypatch.undo()


def test_pytest_target_rejects_symlink_when_supported(tmp_path: Path) -> None:
    target_file = tmp_path / "tests" / "test_api.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    link_path = tmp_path / "tests" / "linked_test.py"
    try:
        link_path.symlink_to(target_file)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is not supported in this environment")

    with pytest.raises(
        ValueError, match="must not traverse symlinks or reparse points"
    ):
        validate_and_normalize_pytest_target(tmp_path, "tests/linked_test.py")


def test_resolve_unknown_id_raises() -> None:
    with pytest.raises(ValueError, match="Unknown command_id"):
        resolve_command_profile("nonexistent_command")


@pytest.mark.parametrize(
    "command_id",
    ["ruff_check", "ruff_format_check", "ruff_format", "mypy", "git_diff_check"],
)
def test_removed_arbitrary_filtering_builtins_are_rejected(command_id: str) -> None:
    with pytest.raises(ValueError, match="Unknown command_id"):
        resolve_command_profile(command_id)


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


def test_find_repo_python_accepts_active_virtual_env_inside_repo(
    tmp_path: Path, monkeypatch
) -> None:
    expected_python, expected_venv = _create_repo_python(tmp_path)
    monkeypatch.setenv("VIRTUAL_ENV", str(expected_venv))

    python_executable, virtual_env = find_repo_python(tmp_path)

    assert python_executable == expected_python
    assert virtual_env == expected_venv


def test_find_repo_python_ignores_active_virtual_env_outside_repo(
    tmp_path: Path, monkeypatch
) -> None:
    outside_env = tmp_path.parent / "external-env"
    if os.name == "nt":
        interpreter = outside_env / "Scripts" / "python.exe"
    else:
        interpreter = outside_env / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("", encoding="utf-8")
    expected_python, expected_venv = _create_repo_python(tmp_path)
    monkeypatch.setenv("VIRTUAL_ENV", str(outside_env))

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
