from __future__ import annotations

from pathlib import Path

from codexbridge.config import (
    AppConfig,
    RepoConfig,
    SupervisorNotificationsConfig,
    SupervisorWebhookNotificationSinkConfig,
    SupervisorsConfig,
)
from codexbridge.self_check import run_self_check


def test_self_check_result_structure_without_live_server(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_run(command: list[str], cwd: Path, timeout: int = 120) -> dict:
        return {
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    monkeypatch.setattr("codexbridge.self_check._run", fake_run)
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    result = run_self_check(
        config=config, config_path=None, run_live_server=False, run_tests=True
    )
    assert result["ok"] is True
    assert "imports" in result["checks"]
    assert "pytest" in result["checks"]
    assert "supervisor_store" in result["checks"]
    assert "supervisor_config" in result["checks"]
    assert "supervisor_resume_prompts" in result["checks"]
    assert result["checks"]["transport"]["skipped"] is True


def test_self_check_reports_supervisor_readiness(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], cwd: Path, timeout: int = 120) -> dict:
        return {
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    monkeypatch.setattr("codexbridge.self_check._run", fake_run)
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    result = run_self_check(
        config=config, config_path=None, run_live_server=False, run_tests=False
    )

    supervisor_store = result["checks"]["supervisor_store"]
    assert supervisor_store["ok"] is True
    assert supervisor_store["journal_mode"] == "wal"
    assert supervisor_store["missing_tables"] == []
    assert "supervisors" in supervisor_store["required_tables"]
    assert "supervisor_notifications" in supervisor_store["required_tables"]

    supervisor_config = result["checks"]["supervisor_config"]
    assert supervisor_config["ok"] is True
    assert supervisor_config["default_autonomy_profile"] == "permissive"
    assert supervisor_config["available_profiles"] == [
        "balanced",
        "conservative",
        "permissive",
    ]
    assert supervisor_config["notification_sinks"] == {
        "file_enabled": False,
        "webhook_enabled": False,
        "windows_toast_enabled": False,
    }

    resume_prompts = result["checks"]["supervisor_resume_prompts"]
    assert resume_prompts["ok"] is True
    assert resume_prompts["pattern"].endswith(
        "runs\\supervisors\\<supervisor_id>\\resume_prompt.txt"
    ) or resume_prompts["pattern"].endswith(
        "runs/supervisors/<supervisor_id>/resume_prompt.txt"
    )


def test_self_check_does_not_expose_webhook_url_values(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_run(command: list[str], cwd: Path, timeout: int = 120) -> dict:
        return {
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    monkeypatch.setattr("codexbridge.self_check._run", fake_run)
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
        supervisors=SupervisorsConfig(
            notifications=SupervisorNotificationsConfig(
                webhook=SupervisorWebhookNotificationSinkConfig(
                    enabled=True, url_env="SECRET_WEBHOOK_URL"
                )
            )
        ),
    )
    result = run_self_check(
        config=config, config_path=None, run_live_server=False, run_tests=False
    )

    serialized = str(result)
    assert (
        result["checks"]["supervisor_config"]["notification_sinks"]["webhook_enabled"]
        is True
    )
    assert "SECRET_WEBHOOK_URL" not in serialized


def test_self_check_reports_transport_readiness(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], cwd: Path, timeout: int = 120) -> dict:
        return {
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    def fake_start_server_probe(
        config_path: Path, host: str, port: int, path: str, cwd: Path
    ) -> dict:
        return {
            "command": ["server"],
            "process_started": True,
            "endpoint": {
                "url": f"http://{host}:{port}{path}",
                "status": 200,
                "ok": True,
            },
            "transport_ready": True,
            "ok": True,
        }

    config_file = tmp_path / "config.yaml"
    config_file.write_text("repos: {}\n", encoding="utf-8")
    monkeypatch.setattr("codexbridge.self_check._run", fake_run)
    monkeypatch.setattr(
        "codexbridge.self_check._start_server_probe", fake_start_server_probe
    )
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    result = run_self_check(
        config=config, config_path=config_file, live_path="/mcp", run_tests=False
    )
    assert result["checks"]["transport"]["transport_ready"] is True
    assert result["checks"]["transport"]["endpoint"]["url"].endswith("/mcp")
