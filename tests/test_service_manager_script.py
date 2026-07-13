from pathlib import Path


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


def test_readme_documents_controller_and_common_actions() -> None:
    text = README.read_text(encoding="utf-8")
    assert ".\\codexbridge-service.cmd" in text
    for action in ("start", "stop", "restart", "status", "logs", "diagnostics"):
        assert f"codexbridge-service.cmd {action}" in text
    assert "runs\\service_logs" in text
    assert "UAC" in text
