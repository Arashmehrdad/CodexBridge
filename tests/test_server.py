from __future__ import annotations

from codexbridge.server import parse_args


def test_server_cli_defaults_to_http_mcp_path() -> None:
    args = parse_args([])
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_server_cli_supports_explicit_mcp_command() -> None:
    args = parse_args(
        [
            "--config",
            "config.yaml",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--path",
            "/mcp",
        ]
    )
    assert args.config == "config.yaml"
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_server_cli_preserves_stdio_mode() -> None:
    args = parse_args(["--transport", "stdio"])
    assert args.transport == "stdio"

