"""Inspect the active Windows OpenSSH configuration for the Andiya alias.

The script intentionally emits structural booleans only. It never prints SSH
usernames, identity-file paths, key contents, or the SSH config contents.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any

ALIAS = "andia-server"
EXPECTED_HOSTNAME = "85.9.106.91"


def _split_config_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if " " in stripped or "\t" in stripped:
        parts = stripped.split(None, 1)
        return parts[0].lower(), parts[1].strip()
    if "=" in stripped:
        key, value = stripped.split("=", 1)
        return key.strip().lower(), value.strip()
    return stripped.lower(), ""


def _clean_value(value: str) -> str:
    try:
        tokens = shlex.split(value, posix=False)
    except ValueError:
        tokens = [value]
    return tokens[0].strip('"\'') if tokens else ""


def _identity_exists(raw_value: str) -> bool:
    value = _clean_value(raw_value)
    if not value:
        return False
    expanded = os.path.expandvars(os.path.expanduser(value))
    return Path(expanded).is_file()


def _parse_main_config(config_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "config_exists": config_path.is_file(),
        "include_directive_present": False,
        "direct_alias_block_found": False,
        "direct_alias_hostname_matches_expected": False,
        "direct_alias_has_user": False,
        "direct_alias_has_identity_file": False,
        "direct_alias_identity_file_exists": False,
        "matching_ip_block_found": False,
        "matching_ip_block_count": 0,
    }
    if not config_path.is_file():
        return result

    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        result["config_readable"] = False
        return result

    result["config_readable"] = True
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        parsed = _split_config_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key == "include":
            result["include_directive_present"] = True
            continue
        if key == "match":
            current = None
            continue
        if key == "host":
            patterns = [token.strip('"\'') for token in value.split()]
            current = {"patterns": patterns, "options": {}}
            blocks.append(current)
            continue
        if current is not None:
            current["options"].setdefault(key, value)

    matching_ip_count = 0
    for block in blocks:
        patterns = block["patterns"]
        options = block["options"]
        hostname = _clean_value(options.get("hostname", ""))
        if hostname == EXPECTED_HOSTNAME:
            matching_ip_count += 1
        if ALIAS not in patterns:
            continue
        result["direct_alias_block_found"] = True
        result["direct_alias_hostname_matches_expected"] = hostname == EXPECTED_HOSTNAME
        result["direct_alias_has_user"] = bool(_clean_value(options.get("user", "")))
        identity_value = options.get("identityfile", "")
        result["direct_alias_has_identity_file"] = bool(_clean_value(identity_value))
        result["direct_alias_identity_file_exists"] = _identity_exists(identity_value)

    result["matching_ip_block_count"] = matching_ip_count
    result["matching_ip_block_found"] = matching_ip_count > 0
    return result


def _effective_config() -> dict[str, Any]:
    executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
    ssh_path = str(executable) if executable.is_file() else shutil.which("ssh")
    if not ssh_path:
        return {"ssh_executable_found": False}

    try:
        completed = subprocess.run(
            [ssh_path, "-G", "-o", "BatchMode=yes", ALIAS],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ssh_executable_found": True, "ssh_g_completed": False}

    effective: dict[str, list[str]] = {}
    for line in completed.stdout.splitlines():
        if not line.strip() or " " not in line:
            continue
        key, value = line.split(None, 1)
        effective.setdefault(key.lower(), []).append(value.strip())

    hostnames = effective.get("hostname", [])
    identity_values = effective.get("identityfile", [])
    identity_exists = any(_identity_exists(value) for value in identity_values)
    ports = effective.get("port", [])
    port = ports[0] if ports and ports[0].isdigit() else None

    return {
        "ssh_executable_found": True,
        "ssh_g_completed": completed.returncode == 0,
        "effective_hostname_matches_expected": bool(hostnames and hostnames[0] == EXPECTED_HOSTNAME),
        "effective_hostname_is_unresolved_alias": bool(hostnames and hostnames[0] == ALIAS),
        "effective_identity_candidate_count": len(identity_values),
        "effective_identity_file_exists": identity_exists,
        "effective_port": int(port) if port is not None else None,
    }


def main() -> int:
    user_profile = os.environ.get("USERPROFILE")
    config_path = Path(user_profile) / ".ssh" / "config" if user_profile else Path.home() / ".ssh" / "config"
    report = {
        "alias": ALIAS,
        "expected_hostname": EXPECTED_HOSTNAME,
        "main_config": _parse_main_config(config_path),
        "effective_config": _effective_config(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
