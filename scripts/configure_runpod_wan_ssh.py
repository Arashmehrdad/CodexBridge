"""Configure the managed OpenSSH alias used for the RunPod Wan2GP pod."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import re
import subprocess
import tempfile

DEFAULT_RUNPOD_HOSTNAME = "ssh.runpod.io"
DEFAULT_RUNPOD_USER = "fhxnfase3ezwmn-644113c6"
DEFAULT_RUNPOD_PORT = 22
START_MARKER = "# BEGIN CODEXBRIDGE RUNPOD WAN"
END_MARKER = "# END CODEXBRIDGE RUNPOD WAN"


class ConfigurationError(RuntimeError):
    """Raised when the managed SSH alias cannot be configured safely."""


def _managed_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"(?ms)^{re.escape(START_MARKER)}\r?\n.*?^{re.escape(END_MARKER)}\r?\n?"
    )


def _run_windows_command(argv: list[str], label: str) -> str:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConfigurationError(f"Unable to run {label}: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ConfigurationError(
            f"{label} failed with exit code {completed.returncode}: {message}"
        )
    return completed.stdout


def _current_windows_user_sid() -> str:
    output = _run_windows_command(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        "whoami",
    )
    rows = list(csv.reader(output.splitlines()))
    if len(rows) != 1 or len(rows[0]) < 2:
        raise ConfigurationError("Unable to parse the current Windows user SID")
    sid = rows[0][1].strip()
    if not re.fullmatch(r"S-[0-9-]+", sid):
        raise ConfigurationError(f"Invalid current Windows user SID: {sid!r}")
    return sid


def harden_windows_acl(path: Path) -> None:
    if os.name != "nt":
        return
    sid = _current_windows_user_sid()
    target = str(path.resolve())
    _run_windows_command(["icacls.exe", target, "/reset"], "icacls reset")
    _run_windows_command(
        ["icacls.exe", target, "/inheritance:r"],
        "icacls inheritance removal",
    )
    _run_windows_command(
        [
            "icacls.exe",
            target,
            "/grant:r",
            f"*{sid}:(F)",
            "*S-1-5-18:(F)",
            "*S-1-5-32-544:(F)",
        ],
        "icacls grant",
    )
    _run_windows_command(
        ["icacls.exe", target, "/setowner", f"*{sid}"],
        "icacls owner update",
    )


def render_managed_block(
    hostname: str,
    runpod_user: str,
    port: int,
    identity_file: Path,
) -> str:
    normalized_hostname = hostname.strip()
    normalized_user = runpod_user.strip()
    if not normalized_hostname or not re.fullmatch(r"[A-Za-z0-9.-]+", normalized_hostname):
        raise ConfigurationError("RunPod hostname contains invalid characters")
    if not normalized_user or not re.fullmatch(r"[A-Za-z0-9._-]+", normalized_user):
        raise ConfigurationError("RunPod user contains invalid characters")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ConfigurationError("RunPod port must be between 1 and 65535")
    normalized_identity = identity_file.resolve().as_posix()
    return (
        f"{START_MARKER}\n"
        "Host runpod-wan\n"
        f"    HostName {normalized_hostname}\n"
        f"    User {normalized_user}\n"
        f"    Port {port}\n"
        f"    IdentityFile {normalized_identity}\n"
        "    IdentitiesOnly yes\n"
        "    ServerAliveInterval 30\n"
        "    ServerAliveCountMax 3\n"
        f"{END_MARKER}\n"
    )


def update_ssh_config(
    config_path: Path,
    identity_file: Path,
    runpod_user: str = DEFAULT_RUNPOD_USER,
    hostname: str = DEFAULT_RUNPOD_HOSTNAME,
    port: int = DEFAULT_RUNPOD_PORT,
) -> Path:
    config = config_path.expanduser().resolve()
    identity = identity_file.expanduser().resolve()
    if not identity.is_file():
        raise ConfigurationError(f"SSH private key was not found: {identity}")
    if config.exists() and (not config.is_file() or config.is_symlink()):
        raise ConfigurationError(f"SSH config must be a regular file: {config}")
    config.parent.mkdir(parents=True, exist_ok=True)

    try:
        existing = config.read_text(encoding="utf-8") if config.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigurationError(f"Unable to read SSH config {config}: {exc}") from exc

    cleaned = _managed_pattern().sub("", existing).rstrip()
    block = render_managed_block(hostname, runpod_user, port, identity).rstrip()
    new_content = f"{block}\n" if not cleaned else f"{cleaned}\n\n{block}\n"

    temporary_path: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{config.name}.codexbridge-",
            dir=config.parent,
        )
        temporary_path = Path(raw_temporary)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new_content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, config)
        temporary_path = None
        harden_windows_acl(config)
        harden_windows_acl(identity)
    except OSError as exc:
        raise ConfigurationError(f"Unable to write SSH config {config}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", default=DEFAULT_RUNPOD_HOSTNAME)
    parser.add_argument("--runpod-user", default=DEFAULT_RUNPOD_USER)
    parser.add_argument("--port", type=int, default=DEFAULT_RUNPOD_PORT)
    parser.add_argument(
        "--identity-file",
        default=str(Path.home() / ".ssh" / "runpod_wan22"),
    )
    parser.add_argument(
        "--config-path",
        default=str(Path.home() / ".ssh" / "config"),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        config = update_ssh_config(
            Path(args.config_path),
            Path(args.identity_file),
            args.runpod_user,
            args.hostname,
            args.port,
        )
    except ConfigurationError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Configured SSH alias 'runpod-wan' in {config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
