from __future__ import annotations

import re
from pathlib import Path

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_MAX_DOTENV_BYTES = 65_536
DEFAULT_MAX_DOTENV_VARIABLES = 512
DEFAULT_MAX_DOTENV_VALUE_BYTES = 16_384


def parse_dotenv_text(
    text: str,
    *,
    label: str = "dotenv file",
    max_variables: int = DEFAULT_MAX_DOTENV_VARIABLES,
    max_value_bytes: int = DEFAULT_MAX_DOTENV_VALUE_BYTES,
) -> dict[str, str]:
    """Parse one bounded dotenv document without interpolation or command expansion.

    The parser deliberately supports only plain ``NAME=value`` assignments,
    optional ``export`` prefixes, whole-value single or double quotes, comments,
    and blank lines. Duplicate variables and malformed quoting fail closed.
    """

    if text.startswith("\ufeff"):
        text = text[1:]
    if "\x00" in text:
        raise ValueError(f"{label} contains a NUL byte")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{label} line {line_number} is not an assignment")

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not ENV_NAME_RE.fullmatch(key):
            raise ValueError(f"{label} line {line_number} has an invalid variable name")
        if key in values:
            raise ValueError(f"{label} contains duplicate variable {key!r}")

        value = raw_value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            if len(value) < 2 or not value.endswith(quote):
                raise ValueError(f"{label} line {line_number} has unmatched quoting")
            value = value[1:-1]
        elif value.endswith(("'", '"')):
            raise ValueError(f"{label} line {line_number} has unmatched quoting")

        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(f"{label} line {line_number} contains a control character")
        if len(value.encode("utf-8")) > max_value_bytes:
            raise ValueError(f"{label} variable {key!r} exceeds the value-size limit")

        values[key] = value
        if len(values) > max_variables:
            raise ValueError(f"{label} exceeds the variable-count limit")
    return values


def read_dotenv_file(
    path: Path,
    *,
    label: str = "dotenv file",
    max_bytes: int = DEFAULT_MAX_DOTENV_BYTES,
    max_variables: int = DEFAULT_MAX_DOTENV_VARIABLES,
    max_value_bytes: int = DEFAULT_MAX_DOTENV_VALUE_BYTES,
) -> dict[str, str]:
    """Read and parse one regular UTF-8 dotenv file with bounded size."""

    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or not a regular file")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"{label} metadata could not be read") from exc
    if size > max_bytes:
        raise ValueError(f"{label} exceeds {max_bytes} bytes")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{label} could not be read as UTF-8") from exc
    return parse_dotenv_text(
        text,
        label=label,
        max_variables=max_variables,
        max_value_bytes=max_value_bytes,
    )
