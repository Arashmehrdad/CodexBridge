from __future__ import annotations

from pathlib import Path

from soma.config import (
    AppConfig,
    RepoConfig,
    SupervisorNotificationsConfig,
    SupervisorWebhookNotificationSinkConfig,
    SupervisorsConfig,
)
from soma.self_check import _start_server_probe, run_self_check


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

    monkeypatch.setattr("soma.self_check._run", fake_run)
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

    monkeypatch.setattr("soma.self_check._run", fake_run)
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
    assert "operation_locks" in supervisor_store["required_tables"]
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

    monkeypatch.setattr("soma.self_check._run", fake_run)
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
    monkeypatch.setattr("soma.self_check._run", fake_run)
    monkeypatch.setattr(
        "soma.self_check._start_server_probe", fake_start_server_probe
    )
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    result = run_self_check(
        config=config, config_path=config_file, live_path="/mcp", run_tests=False
    )
    assert result["checks"]["transport"]["transport_ready"] is True
    assert result["checks"]["transport"]["endpoint"]["url"].endswith("/mcp")


def test_self_check_uses_isolated_pytest_basetemp(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], cwd: Path, timeout: int = 120) -> dict:
        if "pytest" in command:
            captured["command"] = command
            captured["timeout"] = timeout
        return {
            "command": command,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    monkeypatch.setattr("soma.self_check._run", fake_run)
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )

    result = run_self_check(
        config=config, config_path=None, run_live_server=False, run_tests=True
    )

    command = captured["command"]
    assert isinstance(command, list)
    basetemp_index = command.index("--basetemp") + 1
    basetemp = Path(command[basetemp_index])
    assert basetemp.parent == config.resolve_runs_dir() / "self-check"
    assert captured["timeout"] == 600
    assert result["checks"]["pytest"]["basetemp"] == str(basetemp)


def test_server_probe_uses_extended_readiness_window(
    monkeypatch, tmp_path: Path
) -> None:
    observed: dict[str, float] = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> int | None:
            return 0 if self.terminated else None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: int) -> int:
            return 0

        def kill(self) -> None:
            self.terminated = True

    monkeypatch.setattr(
        "soma.self_check.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )

    def fake_wait_for_endpoint(url: str, timeout_seconds: float = 10.0) -> dict:
        observed["timeout_seconds"] = timeout_seconds
        return {"url": url, "status": 406, "ok": True}

    monkeypatch.setattr(
        "soma.self_check._wait_for_endpoint", fake_wait_for_endpoint
    )

    result = _start_server_probe(
        tmp_path / "config.yaml", "127.0.0.1", 8765, "/mcp", tmp_path
    )

    assert observed["timeout_seconds"] == 60.0
    assert result["ok"] is True
