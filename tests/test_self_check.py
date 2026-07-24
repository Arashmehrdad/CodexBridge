from __future__ import annotations

from pathlib import Path

from soma.config import (
    AppConfig,
    RepoConfig,
    SupervisorNotificationsConfig,
    SupervisorWebhookNotificationSinkConfig,
    SupervisorsConfig,
)
from soma.self_check import run_self_check


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
    )


def test_self_check_is_lightweight_and_structured(tmp_path: Path) -> None:
    result = run_self_check(config=make_config(tmp_path), config_path=None)
    assert result["ok"] is True
    assert result["mode"] == "lightweight"
    assert result["duration_seconds"] < 1.0
    assert {
        "imports", "packages", "trading_lab", "config", "run_store",
        "supervisor_store", "supervisor_config", "service_identity",
        "comprehensive_validation",
    } <= set(result["checks"])
    assert "pytest" not in result["checks"]
    assert "pip_check" not in result["checks"]
    assert "transport" not in result["checks"]
    assert result["checks"]["comprehensive_validation"]["script"] == (
        "scripts/comprehensive_self_check.ps1"
    )


def test_self_check_reports_supervisor_readiness(tmp_path: Path) -> None:
    result = run_self_check(config=make_config(tmp_path), config_path=None)
    store = result["checks"]["supervisor_store"]
    assert store["ok"] is True
    assert store["journal_mode"] == "wal"
    assert store["missing_tables"] == []
    assert "operation_locks" in store["required_tables"]
    config = result["checks"]["supervisor_config"]
    assert config["ok"] is True
    assert config["default_autonomy_profile"] == "permissive"


def test_self_check_does_not_expose_webhook_reference(tmp_path: Path) -> None:
    config = AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        runs_dir=str(tmp_path / "runs"),
        config_dir=tmp_path,
        supervisors=SupervisorsConfig(
            notifications=SupervisorNotificationsConfig(
                webhook=SupervisorWebhookNotificationSinkConfig(
                    enabled=True, url_env="SECRET_WEBHOOK_URL"
                )
            )
        ),
    )
    result = run_self_check(config=config, config_path=None)
    assert result["checks"]["supervisor_config"]["notification_sinks"][
        "webhook_enabled"
    ] is True
    assert "SECRET_WEBHOOK_URL" not in str(result)


def test_comprehensive_self_check_handles_http_errors_under_strict_mode() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "comprehensive_self_check.ps1"
    ).read_text(encoding="utf-8")
    assert "-SkipHttpErrorCheck" in source
    assert "$Response.StatusCode" in source
    assert ".AddSeconds(90)" in source
    assert "$_.Exception.Response" not in source
    assert 'PSObject.Properties["Response"]' not in source


def test_self_check_has_no_subprocess_or_network_probe_dependencies() -> None:
    import soma.self_check as self_check

    assert not hasattr(self_check, "subprocess")
    assert not hasattr(self_check, "Popen")
    assert not hasattr(self_check, "urlopen")
    assert not hasattr(self_check, "_start_server_probe")
    assert not hasattr(self_check, "_wait_for_endpoint")
