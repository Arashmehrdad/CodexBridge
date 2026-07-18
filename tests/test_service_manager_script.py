import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts" / "manage_codexbridge_service.ps1"
LAUNCHER = ROOT / "codexbridge-service.cmd"
README = ROOT / "README.md"
WINDOWS = sys.platform == "win32"
POWERSHELL_5 = shutil.which("powershell.exe")
POWERSHELL_7 = shutil.which("pwsh")
POWERSHELL_ENGINES = tuple(
    dict.fromkeys(engine for engine in (POWERSHELL_5, POWERSHELL_7) if engine)
)
LOCAL_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CMD = shutil.which("cmd.exe")


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _write_isolated_config(root: Path) -> Path:
    config = root / "config.yaml"
    config.write_text(
        f'''repos:
  codexbridge:
    path: "{ROOT.as_posix()}"
runs_dir: "{(root / "runs").as_posix()}"
supervisors:
  default_autonomy_profile: "permissive"
  autonomy_profiles:
    permissive:
      stop_on_requires_human: true
      max_plan_tier: 3
      max_implementation_tier: 3
      require_tests_for_non_docs_changes: false
''',
        encoding="utf-8",
    )
    return config


def _manager_argv(
    engine: str,
    action: str,
    project_root: Path,
    config: Path,
    port: int,
) -> list[str]:
    return [
        engine,
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(MANAGER),
        "-Action",
        action,
        "-ProjectRoot",
        str(project_root),
        "-Config",
        str(config),
        "-PythonExecutable",
        str(LOCAL_PYTHON),
        "-HostName",
        "127.0.0.1",
        "-Port",
        str(port),
        "-McpPath",
        "/mcp",
        "-TunnelConfig",
        str(project_root / "unused-tunnel.yml"),
        "-StartupTimeoutSeconds",
        "30",
    ]


def _run_manager(
    engine: str,
    action: str,
    project_root: Path,
    config: Path,
    port: int,
    *,
    timeout: int = 90,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    argv = _manager_argv(engine, action, project_root, config, port)
    if capture_output:
        return subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="") as output:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        output.flush()
        output.seek(0)
        text = output.read()
    return subprocess.CompletedProcess(completed.args, completed.returncode, text, "")


def test_service_manager_and_launcher_exist() -> None:
    assert MANAGER.is_file()
    assert LAUNCHER.is_file()


def test_launcher_forwards_all_arguments_to_manager() -> None:
    text = LAUNCHER.read_text(encoding="utf-8").lower()
    assert "manage_codexbridge_service.ps1" in text
    assert "%*" in text
    assert "powershell.exe" in text


def test_manager_exposes_complete_action_surface() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    actions = {
        "start",
        "stop",
        "restart",
        "status",
        "logs",
        "follow-logs",
        "open-logs",
        "validate-config",
        "diagnostics",
        "profiles",
        "profile-status",
        "profile-set",
        "tunnel-start",
        "tunnel-stop",
        "tunnel-restart",
        "tunnel-status",
        "start-all",
        "stop-all",
    }
    for action in actions:
        assert f'"{action}"' in text


def test_manager_represents_hidden_lifecycle_and_stable_logs() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    assert "-WindowStyle Hidden" in text
    assert "-RedirectStandardOutput" in text
    assert "-RedirectStandardError" in text
    assert "runs\\service_logs" in text
    assert "codexbridge-server.pid" in text
    assert "codexbridge-mcp-tunnel.pid" in text


def test_manager_verifies_identity_and_protects_unrelated_port_owner() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    assert "Test-ServerProcessIdentity" in text
    assert "Test-TunnelProcessIdentity" in text
    assert "Get-NetTCPConnection" in text
    assert "unrelated process" in text
    assert "will not be killed" in text


def test_manager_supports_bounded_uac_and_route_readiness() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    assert "-Verb RunAs" in text
    assert "ExpectedProcessId" in text
    assert "elevated-stop-server" in text
    assert "elevated-stop-tunnel" in text
    assert "406" in text
    assert "not a full MCP handshake" in text
    assert "Get-HttpStatusCodeFromException" in text
    assert '$Exception.PSObject.Properties["Response"]' in text
    assert "$_.Exception.Response" not in text
    assert "the Cloudflare tunnel will remain unchanged" in text


@pytest.mark.skipif(not WINDOWS, reason="Windows service lifecycle is Windows-only")
@pytest.mark.parametrize("engine", POWERSHELL_ENGINES)
def test_status_handles_connection_refused_in_each_powershell_engine(
    tmp_path: Path,
    engine: str,
) -> None:
    config = _write_isolated_config(tmp_path)
    result = _run_manager(engine, "status", tmp_path, config, _unused_local_port())
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "Ready:     False (HTTP 0" in output
    assert "property 'Response' cannot be found" not in output


@pytest.mark.skipif(
    not WINDOWS or not (POWERSHELL_7 or POWERSHELL_5) or not LOCAL_PYTHON.is_file(),
    reason="Local Windows PowerShell and repository Python are required",
)
def test_direct_server_start_restart_stop_on_isolated_port(tmp_path: Path) -> None:
    engine = str(POWERSHELL_7 or POWERSHELL_5)
    config = _write_isolated_config(tmp_path)
    port = _unused_local_port()
    pid_file = tmp_path / "runs" / "service_logs" / "codexbridge-server.pid"

    try:
        started = _run_manager(
            engine, "start", tmp_path, config, port, capture_output=False
        )
        assert started.returncode == 0, started.stdout + started.stderr
        first_pid = int(pid_file.read_text(encoding="ascii").strip())

        restarted = _run_manager(
            engine, "restart", tmp_path, config, port, capture_output=False
        )
        restart_output = restarted.stdout + restarted.stderr
        assert restarted.returncode == 0, restart_output
        assert "the Cloudflare tunnel will remain unchanged" in restart_output
        second_pid = int(pid_file.read_text(encoding="ascii").strip())
        assert second_pid != first_pid

        status = _run_manager(engine, "status", tmp_path, config, port)
        assert status.returncode == 0, status.stdout + status.stderr
        assert "Ready:     True (HTTP 406" in status.stdout
        assert "PID:       not found" not in status.stdout
        pid_line = next(
            line for line in status.stdout.splitlines() if line.strip().startswith("PID:")
        )
        reported_pid = int(pid_line.split(":", 1)[1].strip())
        assert reported_pid != first_pid
    finally:
        stopped = _run_manager(
            engine, "stop", tmp_path, config, port, capture_output=False
        )

    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert not pid_file.exists()
    final_status = _run_manager(engine, "status", tmp_path, config, port)
    assert final_status.returncode == 0, final_status.stdout + final_status.stderr
    assert "Ready:     False (HTTP 0" in final_status.stdout
    assert "PID:       not found" in final_status.stdout


@pytest.mark.skipif(
    not WINDOWS or not POWERSHELL_5 or not CMD or not LOCAL_PYTHON.is_file(),
    reason="Windows PowerShell, cmd.exe, and repository Python are required",
)
def test_tui_start_restart_stop_on_isolated_port(tmp_path: Path) -> None:
    config = _write_isolated_config(tmp_path)
    port = _unused_local_port()
    launcher_args = [
        str(LAUNCHER),
        "-ProjectRoot",
        str(tmp_path),
        "-Config",
        str(config),
        "-PythonExecutable",
        str(LOCAL_PYTHON),
        "-HostName",
        "127.0.0.1",
        "-Port",
        str(port),
        "-McpPath",
        "/mcp",
        "-TunnelConfig",
        str(tmp_path / "unused-tunnel.yml"),
        "-StartupTimeoutSeconds",
        "30",
    ]
    command_line = subprocess.list2cmdline(launcher_args)

    try:
        with tempfile.TemporaryFile(
            mode="w+", encoding="utf-8", newline=""
        ) as tui_output:
            completed = subprocess.run(
                [str(CMD), "/d", "/s", "/c", command_line],
                cwd=ROOT,
                input="1\n\n3\n\n2\n\n0\n",
                stdout=tui_output,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=150,
                check=False,
            )
            tui_output.flush()
            tui_output.seek(0)
            output = tui_output.read()
        result = subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            output,
            "",
        )
    finally:
        cleanup = _run_manager(
            str(POWERSHELL_5),
            "stop",
            tmp_path,
            config,
            port,
            capture_output=False,
        )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert output.count("CodexBridge started hidden") >= 2
    assert "the Cloudflare tunnel will remain unchanged" in output
    assert "Stopped verified process PID" in output
    assert cleanup.returncode == 0, cleanup.stdout + cleanup.stderr


def test_manager_tui_exposes_profile_selection_and_runtime_state() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    assert "Show-SupervisorProfileMenu" in text
    assert "Select supervisor profile" in text
    assert "AvailableProfiles" in text
    assert "[active]" in text
    assert "Profile: $($profileConfiguration.DefaultProfile)" in text
    assert "Server:  $serverState    Tunnel: $tunnelState" in text
    assert "Profile update was rolled back because validation failed" in text


POWERSHELL = POWERSHELL_5 or POWERSHELL_7


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")
def test_profile_status_and_set_actions_update_only_selected_config(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """repos: {}
supervisors:
  default_autonomy_profile: \"permissive\"
  autonomy_profiles:
    permissive:
      stop_on_requires_human: true
      max_plan_tier: 3
      max_implementation_tier: 3
      require_tests_for_non_docs_changes: false
    balanced:
      stop_on_requires_human: true
      max_plan_tier: 1
      max_implementation_tier: 2
      require_tests_for_non_docs_changes: false
""",
        encoding="utf-8",
    )

    common = [
        str(POWERSHELL),
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(MANAGER),
        "-Config",
        str(config),
    ]
    status = subprocess.run(
        [*common, "-Action", "profile-status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert status.returncode == 0, status.stderr or status.stdout
    assert "Current profile:    permissive" in status.stdout
    assert "permissive, balanced" in status.stdout

    changed = subprocess.run(
        [*common, "-Action", "profile-set", "-Profile", "balanced"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert changed.returncode == 0, changed.stderr or changed.stdout
    assert "Supervisor profile changed from 'permissive' to 'balanced'" in changed.stdout

    updated = config.read_text(encoding="utf-8")
    assert 'default_autonomy_profile: "balanced"' in updated
    assert updated.count("default_autonomy_profile:") == 1
    assert "    permissive:" in updated
    assert "    balanced:" in updated


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")
def test_interactive_menu_launches_and_displays_profile() -> None:
    result = subprocess.run(
        [
            str(POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MANAGER),
            "-Action",
            "menu",
            "-Config",
            str(ROOT / "config.yaml"),
        ],
        cwd=ROOT,
        input="0\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "CodexBridge Service Controller" in output
    assert "Profile:" in output
    assert "Select supervisor profile" in output


def test_readme_documents_controller_and_common_actions() -> None:
    text = README.read_text(encoding="utf-8")
    assert ".\\codexbridge-service.cmd" in text
    for action in (
        "start",
        "stop",
        "restart",
        "status",
        "logs",
        "diagnostics",
        "profile-status",
        "profile-set",
    ):
        assert f"codexbridge-service.cmd {action}" in text
    assert "Select supervisor profile" in text
    assert "runs\\service_logs" in text
    assert "UAC" in text
