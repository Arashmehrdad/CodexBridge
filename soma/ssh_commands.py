from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path, PureWindowsPath

from .config import AppConfig, SSHCommandProfileConfig, SSHConfig, SSHHostConfig
from .ssh_credentials import resolve_ssh_credential_binding

MAX_SSH_OUTPUT_BYTES = 100_000
MAX_REMOTE_ARGV_ITEMS = 64
MAX_REMOTE_ARG_BYTES = 512
MAX_REMOTE_COMMAND_BYTES = 4096
MAX_INTERNAL_CONTROLLER_COMMAND_BYTES = 16_384

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ALIAS_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_USER_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_CONNECTION_COMMAND_RE = re.compile(
    r"^ssh\s+(?P<user>[A-Za-z0-9._-]+)@(?P<hostname>[A-Za-z0-9.-]+)\s+"
    r"-p\s+(?P<port>[0-9]{1,5})\s+-i\s+(?P<identity>.+)$"
)
_CONTROL_OR_SHELL_META_RE = re.compile(r"[\x00-\x1f\x7f]")
_PTY_EXIT_MARKER = "__SOMA_REMOTE_EXIT__="
_PTY_EXIT_RE = re.compile(r"[\r\n]+__SOMA_REMOTE_EXIT__=(?P<code>[0-9]+)[\r\n]+")
_ROOT_EUID_MARKER = "__SOMA_ROOT_EUID__=0"
_PAYLOAD_DELIMITER = "__SOMA_PAYLOAD__"
_PAYLOAD_INTERPRETERS = frozenset({"bash", "sh", "python3", "pwsh"})
_ROOT_PAYLOAD_REMOTE_COMMAND = (
    'if [ "$(id -u)" -ne 0 ]; then '
    "printf '%s\\n' 'Soma root shell requires effective UID 0' >&2; "
    "exit 126; fi; "
    f"printf '%s\\n' '{_ROOT_EUID_MARKER}' >&2; "
    "exec bash -s --"
)
_FIXED_PAYLOAD_REMOTE_PREFIXES = (
    ("exec", "bash", "-s", "--"),
    ("exec", "sh", "-s", "--"),
    ("exec", "python3", "-"),
    ("exec", "pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-File", "-"),
)
_BLOCKED_REMOTE_LAUNCHERS = {
    "bash",
    "cmd",
    "cmd.exe",
    "dash",
    "fish",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "sh",
    "zsh",
}
_BLOCKED_SHELL_TOKENS = ("&&", "||", ";", "|", "`", "$(", "<", ">")


@dataclass(frozen=True)
class SSHConnection:
    destination: str
    mode: str
    identity_file: str = ""
    port: int = 22
    expected_host_key: str = ""
    source_id: str = ""
    host_key_policy: str = ""


def validate_ssh_host_id(host_id: str) -> str:
    value = str(host_id).strip()
    if not value or not _ID_RE.fullmatch(value):
        raise ValueError(f"Invalid SSH host_id: {host_id!r}")
    return value


def validate_ssh_alias(ssh_alias: str) -> str:
    value = str(ssh_alias).strip()
    if not value or not _ALIAS_RE.fullmatch(value):
        raise ValueError(
            "SSH alias must contain only letters, numbers, dots, underscores, or hyphens"
        )
    return value


def validate_ssh_hostname(hostname: str) -> str:
    value = str(hostname).strip()
    if not value or not _HOSTNAME_RE.fullmatch(value):
        raise ValueError(
            "SSH hostname must contain only letters, numbers, dots, or hyphens"
        )
    return value


def validate_ssh_user(user: str) -> str:
    value = str(user).strip()
    if not value or not _USER_RE.fullmatch(value):
        raise ValueError(
            "SSH user must contain only letters, numbers, dots, underscores, or hyphens"
        )
    return value


def _resolve_identity_path(configured: str) -> str:
    value = str(configured).strip()
    if not value:
        raise ValueError("Explicit SSH endpoint requires identity_file")
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    if not value or _CONTROL_OR_SHELL_META_RE.search(value):
        raise ValueError("SSH identity_file contains blocked characters")
    candidate = Path(value).expanduser()
    if not (candidate.is_absolute() or PureWindowsPath(value).is_absolute()):
        raise ValueError("SSH identity_file must be an absolute path")
    if not candidate.is_file():
        raise ValueError(f"SSH identity_file does not exist: {value}")
    return str(candidate)


def resolve_ssh_identity_file(host: SSHHostConfig) -> str:
    return _resolve_identity_path(host.identity_file)


def _resolve_connection_file(configured: str) -> SSHConnection:
    path = Path(str(configured).strip()).expanduser()
    if not (path.is_absolute() or PureWindowsPath(str(configured)).is_absolute()):
        raise ValueError("SSH connection_file must be an absolute path")
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"SSH connection_file is missing or not a regular file: {configured}"
        )
    if path.stat().st_size > 4096:
        raise ValueError("SSH connection_file is too large")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"Unable to read SSH connection_file {configured}: {exc}"
        ) from exc
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError(
            "SSH connection_file must contain exactly one non-empty command line"
        )
    line = lines[0]
    if _CONTROL_OR_SHELL_META_RE.search(line):
        raise ValueError("SSH connection_file contains blocked shell syntax")
    blocked_token = next(
        (token for token in _BLOCKED_SHELL_TOKENS if token in line),
        None,
    )
    if blocked_token is not None:
        raise ValueError(
            f"SSH connection_file contains blocked shell syntax: {blocked_token}"
        )
    match = _CONNECTION_COMMAND_RE.fullmatch(line)
    if match is None:
        raise ValueError(
            "SSH connection_file must use: ssh user@host -p PORT -i IDENTITY_FILE"
        )
    port = int(match.group("port"))
    if not 1 <= port <= 65535:
        raise ValueError("SSH connection_file port must be between 1 and 65535")
    user = validate_ssh_user(match.group("user"))
    hostname = validate_ssh_hostname(match.group("hostname"))
    identity_file = _resolve_identity_path(match.group("identity"))
    return SSHConnection(
        destination=f"{user}@{hostname}",
        mode="connection_file",
        identity_file=identity_file,
        port=port,
    )


def resolve_ssh_connection(
    host: SSHHostConfig,
    ssh_config: SSHConfig | None = None,
) -> SSHConnection:
    if host.credential_binding is not None:
        if ssh_config is None:
            raise ValueError(
                "SSH credential_binding resolution requires the global SSH configuration"
            )
        resolved = resolve_ssh_credential_binding(
            ssh_config.credential_sources,
            host.credential_binding,
        )
        return SSHConnection(
            destination=resolved.destination,
            mode="credential_binding",
            identity_file=resolved.identity_file,
            port=resolved.port,
            expected_host_key=resolved.expected_host_key,
            source_id=resolved.source_id,
            host_key_policy=resolved.host_key_policy,
        )
    if host.ssh_alias:
        return SSHConnection(
            destination=validate_ssh_alias(host.ssh_alias),
            mode="alias",
        )
    if host.connection_file:
        return _resolve_connection_file(host.connection_file)
    return SSHConnection(
        destination=(
            f"{validate_ssh_user(host.user)}@{validate_ssh_hostname(host.hostname)}"
        ),
        mode="explicit",
        identity_file=resolve_ssh_identity_file(host),
        port=host.port,
    )


def build_ssh_destination(
    host: SSHHostConfig,
    ssh_config: SSHConfig | None = None,
) -> str:
    return resolve_ssh_connection(host, ssh_config).destination


def build_ssh_connection_options(
    host: SSHHostConfig,
    *,
    scp: bool = False,
    connection: SSHConnection | None = None,
    ssh_config: SSHConfig | None = None,
) -> list[str]:
    resolved = connection or resolve_ssh_connection(host, ssh_config)
    if resolved.mode == "alias":
        return []
    options = ["-i", resolved.identity_file]
    if resolved.port != 22:
        options.extend(["-P" if scp else "-p", str(resolved.port)])
    return options


def validate_ssh_command_profile(
    profile: SSHCommandProfileConfig,
    *,
    max_total_bytes: int = MAX_REMOTE_COMMAND_BYTES,
) -> SSHCommandProfileConfig:
    command_id = str(profile.command_id).strip()
    if not command_id or not _ID_RE.fullmatch(command_id):
        raise ValueError(f"Invalid SSH command_id: {profile.command_id!r}")
    argv = [str(item) for item in profile.argv]
    if not argv:
        raise ValueError(
            f"SSH command profile '{command_id}' must have a non-empty argv"
        )
    if len(argv) > MAX_REMOTE_ARGV_ITEMS:
        raise ValueError(f"SSH command profile '{command_id}' has too many argv items")
    launcher = Path(argv[0]).name.lower()
    if launcher in _BLOCKED_REMOTE_LAUNCHERS:
        raise ValueError(
            f"SSH command profile '{command_id}' may not launch a remote shell wrapper: {launcher}"
        )
    total_bytes = 0
    for item in argv:
        if not item:
            raise ValueError(
                f"SSH command profile '{command_id}' contains an empty argv item"
            )
        encoded_size = len(item.encode("utf-8"))
        total_bytes += encoded_size
        if encoded_size > MAX_REMOTE_ARG_BYTES:
            raise ValueError(
                f"SSH command profile '{command_id}' contains an oversized argv item"
            )
        blocked_token = next(
            (token for token in _BLOCKED_SHELL_TOKENS if token in item),
            None,
        )
        if blocked_token is not None:
            raise ValueError(
                f"SSH command profile '{command_id}' contains blocked shell token: {blocked_token}"
            )
        if _CONTROL_OR_SHELL_META_RE.search(item):
            raise ValueError(
                f"SSH command profile '{command_id}' contains control characters"
            )
    if total_bytes > int(max_total_bytes):
        raise ValueError(f"SSH command profile '{command_id}' is too large")
    return profile


def resolve_ssh_host(config: AppConfig, host_id: str) -> SSHHostConfig:
    if not config.ssh.enabled:
        raise ValueError("SSH capability is disabled in config.yaml")
    normalized_host_id = validate_ssh_host_id(host_id)
    host = config.ssh.hosts.get(normalized_host_id)
    if host is None:
        raise ValueError(f"Unknown SSH host_id: {normalized_host_id}")
    resolve_ssh_connection(host, config.ssh)
    seen: set[str] = set()
    for profile in host.command_profiles:
        validate_ssh_command_profile(profile)
        if profile.command_id in seen:
            raise ValueError(
                f"Duplicate SSH command_id for host '{normalized_host_id}': "
                f"{profile.command_id}"
            )
        seen.add(profile.command_id)
    return host


def resolve_ssh_command_profile(
    config: AppConfig, host_id: str, command_id: str
) -> tuple[SSHHostConfig, SSHCommandProfileConfig]:
    host = resolve_ssh_host(config, host_id)
    normalized_command_id = str(command_id).strip()
    if not normalized_command_id or not _ID_RE.fullmatch(normalized_command_id):
        raise ValueError(f"Invalid SSH command_id: {command_id!r}")
    for profile in host.command_profiles:
        if profile.command_id == normalized_command_id:
            return host, validate_ssh_command_profile(profile)
    allowed = sorted(profile.command_id for profile in host.command_profiles)
    raise ValueError(
        f"Unknown SSH command_id for host '{host_id}': {normalized_command_id}. "
        f"Allowed: {allowed}"
    )


def resolve_ssh_executable(config: AppConfig) -> str:
    configured = str(config.ssh.executable).strip()
    if not configured:
        raise ValueError("SSH executable must not be empty")
    candidate = Path(configured)
    if candidate.is_absolute():
        if not candidate.is_file():
            raise ValueError(f"SSH executable does not exist: {configured}")
        return str(candidate)
    resolved = shutil.which(configured)
    if not resolved:
        raise ValueError(f"SSH executable was not found on PATH: {configured}")
    return resolved


def build_ssh_argv(
    config: AppConfig,
    host_id: str,
    profile: SSHCommandProfileConfig | None = None,
) -> list[str]:
    host = resolve_ssh_host(config, host_id)
    connection = resolve_ssh_connection(host, config.ssh)
    destination = connection.destination
    if profile is None:
        remote_command = "true"
    else:
        validate_ssh_command_profile(profile)
        remote_command = shlex.join([str(item) for item in profile.argv])
    executable = resolve_ssh_executable(config)
    strict_host_key_checking = (
        "accept-new" if connection.mode == "connection_file" else "yes"
    )
    force_pty = requires_forced_pty(host, connection.destination)
    return [
        executable,
        "-n",
        "-tt" if force_pty else "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        f"StrictHostKeyChecking={strict_host_key_checking}",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "-o",
        "ControlPersist=no",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        f"ConnectTimeout={host.connect_timeout_seconds}",
        *build_ssh_connection_options(host, connection=connection),
        destination,
        remote_command,
    ]


def requires_forced_pty(host: SSHHostConfig, destination: str) -> bool:
    return bool(getattr(host, "force_pty", False)) or destination.endswith(
        "@ssh.runpod.io"
    )


def prepare_ssh_execution(
    host: SSHHostConfig,
    argv: list[str],
) -> tuple[list[str], str | None, str]:
    if len(argv) < 4:
        raise ValueError("SSH argv is incomplete")
    destination = argv[-2]
    if not requires_forced_pty(host, destination):
        return argv, None, destination
    if argv[1] != "-n" or argv[2] != "-tt":
        raise ValueError("Forced-PTY SSH argv is malformed")
    remote_command = argv[-1]
    execution_argv = [argv[0], *argv[2:-1]]
    stdin_text = (
        "stty -echo 2>/dev/null || true\n"
        f"{remote_command}\n"
        "__soma_status=$?\n"
        f"printf '\\n{_PTY_EXIT_MARKER}%s\\n' \"$__soma_status\"\n"
        'exit "$__soma_status"\n'
    )
    return execution_argv, stdin_text, destination


def _truncate_output(stdout: str, stderr: str, limit: int) -> tuple[str, str, bool]:
    combined_size = len((stdout + stderr).encode("utf-8"))
    if combined_size <= limit:
        return stdout, stderr, False
    stdout_bytes = stdout.encode("utf-8")
    stderr_bytes = stderr.encode("utf-8")
    if len(stdout_bytes) >= limit:
        return stdout_bytes[:limit].decode("utf-8", errors="replace"), "", True
    remaining = limit - len(stdout_bytes)
    return (
        stdout,
        stderr_bytes[:remaining].decode("utf-8", errors="replace"),
        True,
    )


def _decode_subprocess_stream(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _run_ssh_argv(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    output_limit: int,
    stdin_text: str | None = None,
    expect_exit_marker: bool | None = None,
) -> dict:
    started = time.monotonic()
    timed_out = False
    try:
        run_kwargs = {
            "cwd": cwd,
            "env": os.environ.copy(),
            "capture_output": True,
            "shell": False,
            "timeout": timeout_seconds,
        }
        if stdin_text is None:
            run_kwargs["text"] = True
            run_kwargs["encoding"] = "utf-8"
            run_kwargs["errors"] = "replace"
            run_kwargs["stdin"] = subprocess.DEVNULL
        else:
            run_kwargs["text"] = False
            run_kwargs["input"] = stdin_text.encode("utf-8")
        completed = subprocess.run(argv, **run_kwargs)
        stdout = _decode_subprocess_stream(completed.stdout)
        stderr = _decode_subprocess_stream(completed.stderr)
        exit_code = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_subprocess_stream(exc.stdout)
        stderr = _decode_subprocess_stream(exc.stderr)
        exit_code = 124
        timed_out = True
    except (OSError, PermissionError) as exc:
        stdout = ""
        stderr = str(exc)
        exit_code = 1
    if expect_exit_marker is None:
        expect_exit_marker = stdin_text is not None
    if expect_exit_marker and not timed_out:
        matches = list(_PTY_EXIT_RE.finditer(stdout))
        if matches:
            marker = matches[-1]
            exit_code = int(marker.group("code"))
            cleaned = stdout[: marker.start()] + stdout[marker.end() :]
            stdout = cleaned.rstrip("\r\n")
            if stdout:
                stdout += "\n"
        else:
            exit_code = 1
            missing = "Forced-PTY session ended without remote exit marker"
            stderr = f"{stderr.rstrip()}\n{missing}".strip()
    stdout, stderr, output_truncated = _truncate_output(stdout, stderr, output_limit)
    duration = round(time.monotonic() - started, 3)
    return {
        "ok": exit_code == 0 and not timed_out,
        "argv": argv,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": output_truncated,
        "error": (
            f"Timed out after {timeout_seconds}s"
            if timed_out
            else (
                (stderr.strip() or f"Remote command exited with code {exit_code}")[:300]
                if exit_code != 0
                else ""
            )
        ),
    }


def _is_fixed_payload_remote_command(remote_command: str) -> bool:
    if remote_command == _ROOT_PAYLOAD_REMOTE_COMMAND:
        return True
    try:
        tokens = shlex.split(remote_command, posix=True)
    except ValueError:
        return False
    for prefix in _FIXED_PAYLOAD_REMOTE_PREFIXES:
        if tuple(tokens[: len(prefix)]) != prefix:
            continue
        arguments = tokens[len(prefix) :]
        canonical = " ".join(prefix) + _quote_payload_arguments(arguments)
        return remote_command == canonical
    return False


def build_ssh_payload_argv(
    config: AppConfig,
    host_id: str,
    remote_command: str,
) -> list[str]:
    """Build hardened SSH argv for a fixed remote command that consumes stdin."""

    if not _is_fixed_payload_remote_command(remote_command):
        raise ValueError("SSH payload remote command is not a fixed launch envelope")
    host = resolve_ssh_host(config, host_id)
    connection = resolve_ssh_connection(host, config.ssh)
    executable = resolve_ssh_executable(config)
    strict_host_key_checking = (
        "accept-new" if connection.mode == "connection_file" else "yes"
    )
    force_pty = requires_forced_pty(host, connection.destination)
    return [
        executable,
        "-tt" if force_pty else "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        f"StrictHostKeyChecking={strict_host_key_checking}",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "-o",
        "ControlPersist=no",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        f"ConnectTimeout={host.connect_timeout_seconds}",
        *build_ssh_connection_options(host, connection=connection),
        connection.destination,
        remote_command,
    ]


def _quote_payload_arguments(arguments: list[str]) -> str:
    return "".join(f" {shlex.quote(argument)}" for argument in arguments)


def _payload_interpreter_commands(
    interpreter: str,
    arguments: list[str] | None = None,
) -> tuple[str, str]:
    if interpreter not in _PAYLOAD_INTERPRETERS:
        raise ValueError(f"Unsupported SSH payload interpreter: {interpreter!r}")
    argument_suffix = _quote_payload_arguments(list(arguments or []))
    if interpreter == "python3":
        return f"exec python3 -{argument_suffix}", f'python3 "$__soma_payload"{argument_suffix}'
    if interpreter == "pwsh":
        fixed = "pwsh -NoLogo -NoProfile -NonInteractive -File"
        return f"exec {fixed} -{argument_suffix}", f'{fixed} "$__soma_payload"{argument_suffix}'
    return f"exec {interpreter} -s --{argument_suffix}", f'{interpreter} "$__soma_payload"{argument_suffix}'


def _encoded_payload(payload: str) -> tuple[str, str]:
    encoded = b64encode(payload.encode("utf-8")).decode("ascii")
    wrapped = "\n".join(encoded[index : index + 76] for index in range(0, len(encoded), 76))
    return encoded, wrapped


def _forced_pty_payload_envelope(
    payload: str,
    interpreter: str,
    *,
    root_required: bool,
    arguments: list[str] | None = None,
) -> tuple[str, str, str]:
    encoded, wrapped = _encoded_payload(payload)
    _, file_command = _payload_interpreter_commands(interpreter, arguments)
    lines = ["stty -echo 2>/dev/null || exit 125"]
    if root_required:
        lines.extend(
            [
                'if [ "$(id -u)" -ne 0 ]; then',
                "  printf '%s\\n' 'Soma root shell requires effective UID 0' >&2",
                "  exit 126",
                "fi",
                f"printf '%s\\n' '{_ROOT_EUID_MARKER}' >&2",
            ]
        )
    lines.extend(
        [
            "__soma_payload=$(mktemp) || exit 125",
            "trap 'rm -f -- \"$__soma_payload\"' EXIT HUP INT TERM",
            f"if ! base64 -d > \"$__soma_payload\" <<'{_PAYLOAD_DELIMITER}'",
            wrapped,
            _PAYLOAD_DELIMITER,
            "then",
            "  exit 125",
            "fi",
            'chmod 600 "$__soma_payload"',
            file_command,
            "__soma_status=$?",
            'rm -f -- "$__soma_payload"',
            "trap - EXIT HUP INT TERM",
            f"printf '\\n{_PTY_EXIT_MARKER}%s\\n' \"$__soma_status\"",
            'exit "$__soma_status"',
        ]
    )
    return "\n".join(lines) + "\n", encoded, wrapped


def _redact_payload_echo(text: str, payload: str, encoded: str, wrapped: str) -> str:
    redacted = text
    candidates = {
        payload,
        payload.replace("\n", "\r\n"),
        encoded,
        wrapped,
        wrapped.replace("\n", "\r\n"),
    }
    for candidate in sorted((item for item in candidates if item), key=len, reverse=True):
        redacted = redacted.replace(candidate, "[REDACTED]")
    return redacted


def _strip_root_marker(text: str) -> tuple[str, bool]:
    verified = _ROOT_EUID_MARKER in text
    cleaned = text.replace(f"{_ROOT_EUID_MARKER}\r\n", "")
    cleaned = cleaned.replace(f"{_ROOT_EUID_MARKER}\n", "")
    cleaned = cleaned.replace(_ROOT_EUID_MARKER, "")
    return cleaned, verified


def run_ssh_payload(
    config: AppConfig,
    host_id: str,
    interpreter: str,
    payload: str,
    *,
    payload_sha256: str,
    timeout_seconds: int,
    writes_remote: bool,
    arguments: list[str] | None = None,
    root_required: bool = False,
) -> dict:
    """Execute an exact hash-pinned payload through SSH stdin."""

    payload_bytes = payload.encode("utf-8")
    if sha256(payload_bytes).hexdigest() != payload_sha256:
        raise ValueError("SSH payload SHA-256 does not match its content")
    host = resolve_ssh_host(config, host_id)
    validated_arguments = list(arguments or [])
    stdin_command, _ = _payload_interpreter_commands(interpreter, validated_arguments)
    if root_required:
        stdin_command = _ROOT_PAYLOAD_REMOTE_COMMAND
    built_argv = build_ssh_payload_argv(config, host_id, stdin_command)
    force_pty = requires_forced_pty(host, built_argv[-2])
    encoded, wrapped = _encoded_payload(payload)
    safe_label = (
        "<root shell via stdin>"
        if root_required
        else "<reviewed script via stdin>"
    )
    if force_pty:
        argv = built_argv[:-1]
        stdin_text, encoded, wrapped = _forced_pty_payload_envelope(
            payload,
            interpreter,
            root_required=root_required,
            arguments=validated_arguments,
        )
        expect_exit_marker = True
        safe_argv = [*argv, safe_label]
    else:
        argv = built_argv
        stdin_text = payload
        expect_exit_marker = False
        safe_argv = [*argv[:-1], safe_label]
    result = _run_ssh_argv(
        argv,
        cwd=config.config_dir,
        timeout_seconds=timeout_seconds,
        output_limit=config.ssh.max_output_bytes,
        stdin_text=stdin_text,
        expect_exit_marker=expect_exit_marker,
    )
    stdout = _redact_payload_echo(str(result.get("stdout", "")), payload, encoded, wrapped)
    stderr = _redact_payload_echo(str(result.get("stderr", "")), payload, encoded, wrapped)
    error = _redact_payload_echo(str(result.get("error", "")), payload, encoded, wrapped)
    stdout, root_stdout = _strip_root_marker(stdout)
    stderr, root_stderr = _strip_root_marker(stderr)
    error, _ = _strip_root_marker(error)
    root_identity_verified = root_stdout or root_stderr
    result["stdout"] = stdout
    result["stderr"] = stderr
    result["error"] = error.strip()
    if root_required and not root_identity_verified and result.get("ok"):
        result["ok"] = False
        result["exit_code"] = 1
        result["error"] = "Remote root identity could not be verified"
    elif not result.get("ok") and not result["error"]:
        result["error"] = (
            f"Timed out after {timeout_seconds}s"
            if result.get("timed_out")
            else f"Remote command exited with code {int(result.get('exit_code', 1))}"
        )
    result["argv"] = safe_argv
    result.update(
        {
            "host_id": validate_ssh_host_id(host_id),
            "ssh_alias": built_argv[-2],
            "interpreter": interpreter,
            "arguments": validated_arguments,
            "payload_sha256": payload_sha256,
            "writes_remote": bool(writes_remote),
            "remote_state_verified": False,
            "root_identity_verified": root_identity_verified,
        }
    )
    return result


def run_ssh_command(config: AppConfig, host_id: str, command_id: str) -> dict:
    host, profile = resolve_ssh_command_profile(config, host_id, command_id)
    built_argv = build_ssh_argv(config, host_id, profile)
    argv, stdin_text, destination = prepare_ssh_execution(host, built_argv)
    result = _run_ssh_argv(
        argv,
        cwd=config.config_dir,
        timeout_seconds=profile.timeout_seconds,
        output_limit=config.ssh.max_output_bytes,
        stdin_text=stdin_text,
    )
    result["argv"] = (
        [*argv[:-1], "<configured command>"]
        if stdin_text is None
        else [*argv, "<configured command via stdin>"]
    )
    result.update(
        {
            "host_id": validate_ssh_host_id(host_id),
            "ssh_alias": destination,
            "command_id": profile.command_id,
            "writes_remote": bool(profile.writes_remote),
            "remote_state_verified": False,
        }
    )
    return result


def ssh_host_health(config: AppConfig, host_id: str) -> dict:
    host = resolve_ssh_host(config, host_id)
    built_argv = build_ssh_argv(config, host_id)
    argv, stdin_text, destination = prepare_ssh_execution(host, built_argv)
    timeout = max(5, host.connect_timeout_seconds + 5)
    result = _run_ssh_argv(
        argv,
        cwd=config.config_dir,
        timeout_seconds=timeout,
        output_limit=config.ssh.max_output_bytes,
        stdin_text=stdin_text,
    )
    result["argv"] = (
        [*argv[:-1], "<health check>"]
        if stdin_text is None
        else [*argv, "<health check via stdin>"]
    )
    result.update(
        {
            "host_id": validate_ssh_host_id(host_id),
            "ssh_alias": destination,
            "status": "ok" if result["ok"] else "unavailable",
        }
    )
    return result


def list_ssh_capabilities(config: AppConfig) -> dict:
    hosts: list[dict] = []
    for host_id in sorted(config.ssh.hosts):
        host = config.ssh.hosts[host_id]
        validate_ssh_host_id(host_id)
        binding = host.credential_binding
        if binding is None:
            connection = resolve_ssh_connection(host, config.ssh)
            destination = connection.destination
            connection_mode = connection.mode
            credential_source_id = ""
        else:
            destination = f"<credential_binding:{binding.source_id}>"
            connection_mode = "credential_binding"
            credential_source_id = binding.source_id
        commands = []
        seen: set[str] = set()
        for profile in host.command_profiles:
            validate_ssh_command_profile(profile)
            if profile.command_id in seen:
                raise ValueError(
                    f"Duplicate SSH command_id for host '{host_id}': "
                    f"{profile.command_id}"
                )
            seen.add(profile.command_id)
            commands.append(
                {
                    "command_id": profile.command_id,
                    "description": profile.description,
                    "timeout_seconds": profile.timeout_seconds,
                    "writes_remote": profile.writes_remote,
                    "watchdog_eligible": bool(profile.watchdog_eligible),
                }
            )
        hosts.append(
            {
                "host_id": host_id,
                "ssh_alias": destination,
                "connection_mode": connection_mode,
                "credential_source_id": credential_source_id,
                "host_key_policy": (
                    binding.host_key_policy if binding is not None else "legacy"
                ),
                "force_pty": bool(getattr(host, "force_pty", False))
                or destination.endswith("@ssh.runpod.io"),
                "connect_timeout_seconds": host.connect_timeout_seconds,
                "commands": commands,
            }
        )
    return {
        "ok": True,
        "enabled": config.ssh.enabled,
        "hosts": hosts,
        "error": "",
    }
