import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts" / "manage_codexbridge_service.ps1"
LAUNCHER = ROOT / "codexbridge-service.cmd"
README = ROOT / "README.md"


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


def test_manager_tui_exposes_profile_selection_and_runtime_state() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    assert "Show-SupervisorProfileMenu" in text
    assert "Select supervisor profile" in text
    assert "AvailableProfiles" in text
    assert "[active]" in text
    assert "Profile: $($profileConfiguration.DefaultProfile)" in text
    assert "Server:  $serverState    Tunnel: $tunnelState" in text
    assert "Profile update was rolled back because validation failed" in text


POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


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
