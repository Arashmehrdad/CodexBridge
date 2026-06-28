from __future__ import annotations

from pathlib import Path


def test_readme_documents_actual_server_command() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert (
        "python -m codexbridge.server --config config.yaml --transport http --host 127.0.0.1 --port 8000 --path /mcp"
        in readme
    )


def test_readme_tunnel_urls_end_in_mcp() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "https://example-tunnel.trycloudflare.com/mcp" in readme
    assert "https://example.ngrok-free.app/mcp" in readme


def test_readme_sets_human_involvement_policy() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "The human is not expected to run setup" in readme
    assert "Codex runs these checks and reports the results" in readme


def test_readme_documents_supervisor_workflow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "start_supervised_recovery_task" in readme
    assert (
        "resume_supervisor(supervisor_id)` to advance exactly one safe step" in readme
    )
    assert (
        "pause_supervisor(supervisor_id)` only when the supervisor is `queued` or `needs_input`"
        in readme
    )
    assert "runs/supervisors/<supervisor_id>/resume_prompt.txt" in readme
    assert "There is no background scheduler yet" in readme
    assert "There is no approve-plan MCP tool yet" in readme
    assert "Notification sinks are disabled by default" in readme
