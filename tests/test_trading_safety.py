from __future__ import annotations

from pathlib import Path

import pytest

from soma.trading.safety import (
    SafetyLimits,
    TradingSafetyController,
    redact_health,
)

from tests.trading_lab_fixtures import demo_health


def test_kill_switch_is_durable_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "safety.sqlite3"
    controller = TradingSafetyController(path)
    assert controller.kill_switch().active is False
    controller.activate_kill_switch("incident")

    # A fresh controller over the same durable state still sees the switch.
    reopened = TradingSafetyController(path)
    state = reopened.kill_switch()
    assert state.active is True
    assert state.reason == "incident"
    reopened.release_kill_switch("resolved")
    assert TradingSafetyController(path).kill_switch().active is False


def test_health_redaction_hides_the_login(tmp_path: Path) -> None:
    redacted = redact_health(demo_health())
    assert redacted["login"] == "[redacted]"
    assert redacted["server"] == "Alpari-MT5-Demo"
    assert redacted["account_environment"] == "demo"
    assert "123" not in str(redacted)


def test_limits_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        SafetyLimits(maximum_daily_loss_usd=0)
    with pytest.raises(ValueError, match="must not be empty"):
        SafetyLimits(allowed_symbols=())


def test_disallowed_symbol_is_a_violation(tmp_path: Path) -> None:
    controller = TradingSafetyController(tmp_path / "s.sqlite3")
    violations = controller.violations(
        symbol="EURUSD_i",
        spread_usd=1.0,
        tick_age_seconds=1.0,
        requested_volume_lots=0.01,
        open_volume_lots=0.0,
        daily_loss_usd=0.0,
    )
    assert any("not in the allowed set" in item for item in violations)
