from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.safety import (
    is_secret_like_file,
    redact_secret_values,
    reject_destructive_command,
    reject_secret_like_file,
    validate_repo_relative_path,
)


def test_absolute_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_repo_relative_path(tmp_path, str(tmp_path / "file.txt"))


def test_parent_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_repo_relative_path(tmp_path, "../outside.txt")


def test_windows_drive_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_repo_relative_path(tmp_path, "C:\\Users\\me\\secret.txt")


def test_unc_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_repo_relative_path(tmp_path, "\\\\server\\share\\file.txt")


def test_wildcard_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_repo_relative_path(tmp_path, "*.py")


def test_outside_repo_symlink_escape_rejected_where_practical(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    with pytest.raises(ValueError):
        validate_repo_relative_path(tmp_path, "link.txt")


@pytest.mark.parametrize(
    "command",
    [
        "docker system prune",
        "docker volume rm data",
        "docker compose down -v",
        "Remove-Item -Recurse -Force .",
        "rm -rf /tmp/x",
        "del /s *.txt",
        "rmdir /s build",
        "format C:",
        ".venv\\Scripts\\python.exe -m ruff format .",
        "diskpart",
    ],
)
def test_destructive_command_patterns_rejected(command: str) -> None:
    with pytest.raises(ValueError):
        reject_destructive_command(command)


def test_ruff_format_check_is_allowed() -> None:
    reject_destructive_command(".venv\\Scripts\\python.exe -m ruff format --check .")


def test_secret_like_files_rejected_for_gemini() -> None:
    assert is_secret_like_file(".env")
    with pytest.raises(ValueError):
        reject_secret_like_file("config/credentials.json")


def test_secret_values_redacted() -> None:
    redacted = redact_secret_values("API_KEY=abc123 token: xyz")
    assert "abc123" not in redacted
    assert "xyz" not in redacted
