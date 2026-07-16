from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from codexbridge.config import AppConfig, ExecutableProfileConfig, RepoConfig
from codexbridge.executable_profiles import build_local_executable_run_request
from codexbridge.job_worker import JobWorker
from codexbridge.run_store import RunStore, utc_now


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell acceptance")


def _pwsh_path() -> Path:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "PowerShell"
        / "7"
        / "pwsh.exe",
        Path(os.environ.get("ProgramW6432", r"C:\Program Files"))
        / "PowerShell"
        / "7"
        / "pwsh.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    pytest.skip("PowerShell 7 executable is not installed at a configured absolute path")


def _make_worker(
    tmp_path: Path,
    *,
    argv: list[str],
    stdin_bytes: bytes | None = None,
    environment: dict[str, str] | None = None,
    working_directory: Path | None = None,
    timeout_seconds: int | None = 30,
) -> tuple[JobWorker, dict, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    pwsh = _pwsh_path()
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "executable_profiles:",
                "  powershell:",
                "    profile_id: powershell",
                "    enabled: true",
                f'    executable_path: "{pwsh.as_posix()}"',
                "    target: local",
                "    autonomy_profile: permissive",
                "    working_directory_policy: arbitrary",
                "    environment_policy: arbitrary",
                "    stdin_mode: bytes",
                "    stdout_mode: protected_artifact",
                "    stderr_mode: protected_artifact",
                "    unrestricted_argv: true",
                "    allow_no_timeout: true",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    profile = ExecutableProfileConfig(
        profile_id="powershell",
        enabled=True,
        executable_path=str(pwsh),
        target="local",
        autonomy_profile="permissive",
        working_directory_policy="arbitrary",
        environment_policy="arbitrary",
        stdin_mode="bytes",
        stdout_mode="protected_artifact",
        stderr_mode="protected_artifact",
        unrestricted_argv=True,
        allow_no_timeout=True,
    )
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(repo))},
        executable_profiles={"powershell": profile},
        runs_dir=str(runs_dir),
        config_dir=tmp_path,
    )
    input_data = build_local_executable_run_request(
        config,
        "powershell",
        argv,
        working_directory=str(working_directory or repo),
        environment=environment or {},
        stdin_bytes=stdin_bytes,
        timeout_seconds=timeout_seconds,
    )
    run_id = f"20260716T000000Z_executable_profile_{len(list(runs_dir.glob('*'))):08x}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    RunStore(runs_dir).create_run(
        run_id=run_id,
        repo_name="sample",
        tool="executable_profile",
        run_dir=run_dir,
        input_data=input_data,
    )
    worker = JobWorker(config_path, run_id)
    worker.event = lambda *args, **kwargs: True
    worker.store.attach_child_pid = lambda *args, **kwargs: True
    return worker, input_data, run_dir


def _execute(worker: JobWorker, input_data: dict, run_dir: Path) -> bytes:
    result = worker._execute_executable_profile(utc_now(), input_data)
    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert (run_dir / "stderr.bin").read_bytes() == b""
    return (run_dir / "stdout.bin").read_bytes()


def test_powershell_command_file_encoded_and_stdin_modes(tmp_path: Path) -> None:
    command_worker, command_input, command_dir = _make_worker(
        tmp_path / "command",
        argv=[
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::Out.Write('command:' + $args[0])",
            "a b",
        ],
    )
    assert _execute(command_worker, command_input, command_dir) == b"command:a b"

    file_root = tmp_path / "file"
    file_root.mkdir()
    script_path = file_root / "quoted script.ps1"
    script_path.write_text(
        "param([string]$Value) [Console]::Out.Write('file:' + $Value)",
        encoding="utf-8",
    )
    file_worker, file_input, file_dir = _make_worker(
        file_root / "case",
        argv=[
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script_path),
            "quoted value",
        ],
    )
    assert _execute(file_worker, file_input, file_dir) == b"file:quoted value"

    encoded_script = "[Console]::Out.Write('encoded:' + [char]0x2713)"
    encoded = base64.b64encode(encoded_script.encode("utf-16-le")).decode("ascii")
    encoded_worker, encoded_input, encoded_dir = _make_worker(
        tmp_path / "encoded",
        argv=["-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
    )
    assert _execute(encoded_worker, encoded_input, encoded_dir).decode("utf-8") == "encoded:✓"

    stdin_script = b"[Console]::Out.Write('stdin:' + $env:CB_STDIN_VALUE)\n"
    stdin_worker, stdin_input, stdin_dir = _make_worker(
        tmp_path / "stdin",
        argv=["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "-"],
        stdin_bytes=stdin_script,
        environment={"CB_STDIN_VALUE": "script value"},
    )
    assert _execute(stdin_worker, stdin_input, stdin_dir) == b"stdin:script value"


def test_powershell_native_child_arbitrary_path_and_environment(tmp_path: Path) -> None:
    case_root = tmp_path / "native child case"
    working_directory = case_root / "working directory with spaces"
    working_directory.mkdir(parents=True)
    marker_path = working_directory / "child marker.txt"
    script = (
        "$child = & $env:COMSPEC /d /c echo native-child; "
        "Set-Content -LiteralPath $env:CB_MARKER -Value $env:CB_VALUE -NoNewline; "
        "$payload = [ordered]@{child=$child.Trim(); cwd=(Get-Location).Path; "
        "value=$env:CB_VALUE; marker=(Get-Content -LiteralPath $env:CB_MARKER -Raw)}; "
        "[Console]::Out.Write(($payload | ConvertTo-Json -Compress))"
    )
    worker, input_data, run_dir = _make_worker(
        case_root / "worker",
        argv=["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        environment={
            "CB_VALUE": "value with spaces = and ; symbols",
            "CB_MARKER": str(marker_path),
        },
        working_directory=working_directory,
    )

    payload = json.loads(_execute(worker, input_data, run_dir).decode("utf-8"))
    assert payload["child"] == "native-child"
    assert Path(payload["cwd"]).resolve() == working_directory.resolve()
    assert payload["value"] == "value with spaces = and ; symbols"
    assert payload["marker"] == "value with spaces = and ; symbols"
    assert marker_path.read_text(encoding="utf-8") == "value with spaces = and ; symbols"


def test_powershell_loopback_network_round_trip(tmp_path: Path) -> None:
    script = (
        "$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); "
        "$listener.Start(); "
        "$port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port; "
        "$accept = $listener.AcceptTcpClientAsync(); "
        "$client = [System.Net.Sockets.TcpClient]::new(); "
        "$client.Connect([System.Net.IPAddress]::Loopback, $port); "
        "$server = $accept.GetAwaiter().GetResult(); "
        "$send = [Text.Encoding]::UTF8.GetBytes('loopback-ok'); "
        "$client.GetStream().Write($send, 0, $send.Length); "
        "$buffer = [byte[]]::new(64); "
        "$count = $server.GetStream().Read($buffer, 0, $buffer.Length); "
        "[Console]::Out.Write([Text.Encoding]::UTF8.GetString($buffer, 0, $count)); "
        "$server.Dispose(); $client.Dispose(); $listener.Stop()"
    )
    worker, input_data, run_dir = _make_worker(
        tmp_path,
        argv=["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
    )

    assert _execute(worker, input_data, run_dir) == b"loopback-ok"
