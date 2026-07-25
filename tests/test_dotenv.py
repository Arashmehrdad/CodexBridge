from __future__ import annotations

from pathlib import Path

import pytest

from soma.dotenv import parse_dotenv_text, read_dotenv_file


def test_parse_dotenv_supports_bom_export_comments_and_whole_value_quotes() -> None:
    values = parse_dotenv_text(
        "\ufeff# comment\n"
        "export SSH_HOST=example.test\n"
        "SSH_USER='root user'\n"
        'SSH_KEY_PATH="C:\\\\Users\\\\owner\\\\.ssh\\\\id_ed25519"\n'
        "EMPTY=\n"
    )

    assert values == {
        "SSH_HOST": "example.test",
        "SSH_USER": "root user",
        "SSH_KEY_PATH": "C:\\\\Users\\\\owner\\\\.ssh\\\\id_ed25519",
        "EMPTY": "",
    }


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("A=1\nA=2\n", "duplicate variable"),
        ("1BAD=value\n", "invalid variable name"),
        ("MISSING_EQUALS\n", "not an assignment"),
        ("BROKEN='value\n", "unmatched quoting"),
        ("BROKEN=value'\n", "unmatched quoting"),
        ("CONTROL=hello\x07world\n", "control character"),
    ],
)
def test_parse_dotenv_fails_closed(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_dotenv_text(text)


def test_read_dotenv_file_requires_regular_bounded_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "credentials.env"
    path.write_text("SSH_HOST=example.test\n", encoding="utf-8")

    assert read_dotenv_file(path) == {"SSH_HOST": "example.test"}

    with pytest.raises(ValueError, match="exceeds"):
        read_dotenv_file(path, max_bytes=2)

    binary = tmp_path / "binary.env"
    binary.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        read_dotenv_file(binary)


def test_read_dotenv_file_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.env"
    target.write_text("SSH_HOST=example.test\n", encoding="utf-8")
    link = tmp_path / "link.env"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")

    with pytest.raises(ValueError, match="regular file"):
        read_dotenv_file(link)
