"""Restore the managed Andiya SSH alias without exposing credential details."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ALIAS = "andia-server"
HOSTNAME = "100.94.44.95"
USER = "root"
START_MARKER = "# BEGIN CODEXBRIDGE ANDIYA"
END_MARKER = "# END CODEXBRIDGE ANDIYA"


class RepairError(RuntimeError):
    """Raised when the alias cannot be restored and validated safely."""


def _ssh_executable() -> Path:
    candidate = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
    if not candidate.is_file():
        raise RepairError("Windows OpenSSH executable is unavailable")
    return candidate


def _private_key_candidates(ssh_dir: Path) -> list[Path]:
    excluded = {"config", "known_hosts", "known_hosts.old", "authorized_keys"}
    candidates: list[Path] = []
    if not ssh_dir.is_dir():
        return candidates
    for path in ssh_dir.iterdir():
        name = path.name.lower()
        if (
            not path.is_file()
            or path.is_symlink()
            or name in excluded
            or name.endswith(".pub")
            or not ("andia" in name or "clinic" in name)
        ):
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)


def _classify_failure(stderr: str) -> str:
    lowered = stderr.lower()
    if "host key verification failed" in lowered:
        return "host_key_verification_failed"
    if "permission denied" in lowered:
        return "authentication_failed"
    if "timed out" in lowered:
        return "connection_timed_out"
    if "no route to host" in lowered or "network is unreachable" in lowered:
        return "network_unreachable"
    if "connection refused" in lowered:
        return "connection_refused"
    return "connection_failed"


def _test_key(ssh: Path, key_path: Path) -> tuple[bool, str]:
    argv = [
        str(ssh),
        "-F",
        "NUL",
        "-n",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "ConnectTimeout=12",
        "-i",
        str(key_path),
        f"{USER}@{HOSTNAME}",
        "true",
    ]
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False, "connection_timed_out"
    except OSError:
        return False, "ssh_execution_failed"
    if completed.returncode == 0:
        return True, "ok"
    return False, _classify_failure(completed.stderr)


def _managed_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"(?ms)^{re.escape(START_MARKER)}\r?\n.*?^{re.escape(END_MARKER)}\r?\n?"
    )


def _render_block(identity_file: Path) -> str:
    identity = identity_file.resolve().as_posix()
    return (
        f"{START_MARKER}\n"
        f"Host {ALIAS}\n"
        f"    HostName {HOSTNAME}\n"
        f"    User {USER}\n"
        f"    IdentityFile {identity}\n"
        "    IdentitiesOnly yes\n"
        "    ServerAliveInterval 30\n"
        "    ServerAliveCountMax 3\n"
        f"{END_MARKER}\n"
    )


def _write_atomic(config_path: Path, content: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{config_path.name}.codexbridge-",
            dir=config_path.parent,
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, config_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_alias(ssh: Path) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [
                str(ssh),
                "-n",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "KbdInteractiveAuthentication=no",
                "-o",
                "ForwardAgent=no",
                "-o",
                "ClearAllForwardings=yes",
                "-o",
                "ConnectTimeout=12",
                ALIAS,
                "true",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False, "connection_timed_out"
    except OSError:
        return False, "ssh_execution_failed"
    if completed.returncode == 0:
        return True, "ok"
    return False, _classify_failure(completed.stderr)


def main() -> int:
    report: dict[str, object] = {
        "alias": ALIAS,
        "target_is_tailscale": True,
        "candidate_keys_found": 0,
        "candidate_keys_tested": 0,
        "working_key_found": False,
        "alias_written": False,
        "alias_validation_succeeded": False,
        "rollback_performed": False,
        "failure_category": "",
    }
    try:
        ssh = _ssh_executable()
        user_profile = os.environ.get("USERPROFILE")
        ssh_dir = Path(user_profile) / ".ssh" if user_profile else Path.home() / ".ssh"
        config_path = ssh_dir / "config"
        candidates = _private_key_candidates(ssh_dir)
        report["candidate_keys_found"] = len(candidates)

        selected: Path | None = None
        last_failure = "no_candidate_key"
        for candidate in candidates:
            report["candidate_keys_tested"] = int(report["candidate_keys_tested"]) + 1
            ok, category = _test_key(ssh, candidate)
            last_failure = category
            if ok:
                selected = candidate
                break
        if selected is None:
            raise RepairError(last_failure)
        report["working_key_found"] = True

        existed = config_path.is_file()
        original = config_path.read_text(encoding="utf-8") if existed else ""
        cleaned = _managed_pattern().sub("", original).rstrip()
        block = _render_block(selected).rstrip()
        updated = f"{block}\n" if not cleaned else f"{cleaned}\n\n{block}\n"
        _write_atomic(config_path, updated)
        report["alias_written"] = True

        valid, category = _validate_alias(ssh)
        if not valid:
            if existed:
                _write_atomic(config_path, original)
            else:
                config_path.unlink(missing_ok=True)
            report["rollback_performed"] = True
            raise RepairError(category)
        report["alias_validation_succeeded"] = True
    except (OSError, UnicodeDecodeError, RepairError) as exc:
        report["failure_category"] = str(exc)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
