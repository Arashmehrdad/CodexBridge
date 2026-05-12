from __future__ import annotations

import json
from pathlib import Path

import pytest

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.dashboard.app import create_dashboard_app


pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_app(tmp_path: Path):
    config = AppConfig(repos={"repo": RepoConfig(path=str(tmp_path))}, runs_dir=str(tmp_path / "runs"), config_dir=tmp_path)
    write_json(tmp_path / "runs" / "local_agent" / "commands" / "cmd1" / "result.json", {"run_id": "cmd1", "command_id": "git_status", "status": "success"})
    return create_dashboard_app(config)


def test_dashboard_health_root_and_api_summary_routes(tmp_path: Path) -> None:
    client = TestClient(make_app(tmp_path))

    health = client.get("/health")
    root = client.get("/")
    summary = client.get("/api/summary")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert root.status_code == 200
    assert "Overall health" in root.text
    assert "Recent command runs" in root.text
    assert "PulseSender readiness" in root.text
    assert summary.status_code == 200
    assert summary.json()["commands"][0]["id"] == "cmd1"


def test_dashboard_api_routes_are_read_only(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    client = TestClient(app)

    for path in [
        "/api/runs",
        "/api/jobs",
        "/api/supervisors",
        "/api/approvals",
        "/api/codex-escalations",
        "/api/return-loop",
        "/api/local-coding",
        "/api/memory",
    ]:
        assert client.get(path).status_code == 200
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    for route in app.routes:
        assert not (getattr(route, "methods", set()) & mutating_methods)


def test_dashboard_package_introduces_no_pulsesender_browser_codex_or_subprocess_calls() -> None:
    package = Path("codexbridge/dashboard")
    text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "import PulseSender" not in text
    assert "from PulseSender" not in text
    assert "playwright" not in text
    assert "selenium" not in text
    assert "subprocess" not in text
    assert "CodexEscalationRouter" not in text
