from __future__ import annotations

from codexbridge.server import parse_args
import codexbridge.server as server


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


class FakeSupervisorService:
    def start_supervised_recovery_task(self, *args):
        return {"tool": "start", "args": args}

    def get_status(self, supervisor_id):
        return {"tool": "status", "supervisor_id": supervisor_id}

    def get_events(self, supervisor_id, limit):
        return [{"tool": "events", "limit": limit}]

    def get_result(self, supervisor_id):
        return {"tool": "result"}

    def resume(self, supervisor_id):
        return {"tool": "resume"}

    def pause(self, supervisor_id):
        return {"tool": "pause"}

    def cancel(self, supervisor_id):
        return {"tool": "cancel"}

    def get_notifications(self, supervisor_id, delivery_status, limit):
        return [{"tool": "notifications", "delivery_status": delivery_status, "limit": limit}]

    def get_resume_prompt(self, supervisor_id):
        return {"tool": "prompt"}


def test_server_supervisor_tool_functions_delegate(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_supervisor_service", lambda: FakeSupervisorService())
    supervisor_id = "20260428T120000Z_supervisor_abcdef12"
    assert server.start_supervised_recovery_task("repo", "objective", "task")["tool"] == "start"
    assert server.get_supervisor_status(supervisor_id)["tool"] == "status"
    assert server.get_supervisor_events(supervisor_id, 5)[0]["limit"] == 5
    assert server.get_supervisor_result(supervisor_id)["tool"] == "result"
    assert server.resume_supervisor(supervisor_id)["tool"] == "resume"
    assert server.pause_supervisor(supervisor_id)["tool"] == "pause"
    assert server.cancel_supervisor(supervisor_id)["tool"] == "cancel"
    assert server.get_supervisor_notifications(supervisor_id, "pending", 3)[0]["delivery_status"] == "pending"
    assert server.get_supervisor_resume_prompt(supervisor_id)["tool"] == "prompt"
