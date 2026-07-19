from __future__ import annotations

import json

import pytest

from scripts.hermes_mcp_fixture import (
    apply_reversible_fixture,
    reconcile_reversible_fixture,
    revert_reversible_fixture,
)


def test_reversible_fixture_applies_once_reconciles_and_reverts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    first = apply_reversible_fixture("fixture-key", "value")
    replay = apply_reversible_fixture("fixture-key", "value")
    reconciled = reconcile_reversible_fixture("fixture-key")
    reverted = revert_reversible_fixture("fixture-key")
    missing = reconcile_reversible_fixture("fixture-key")

    assert first["applied"] is True
    assert replay["applied"] is False
    assert first["outcome"] == replay["outcome"] == {
        "value": "value",
        "application_count": 1,
    }
    assert reconciled == {
        "idempotency_key": "fixture-key",
        "exists": True,
        "outcome": first["outcome"],
    }
    assert reverted["reverted"] is True
    assert missing["exists"] is False


def test_ambiguous_response_reconciles_without_duplicate_mutation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    with pytest.raises(RuntimeError, match="ambiguous response"):
        apply_reversible_fixture(
            "ambiguous-key",
            "committed-value",
            simulate_ambiguous_response=True,
        )

    reconciled = reconcile_reversible_fixture("ambiguous-key")
    replay = apply_reversible_fixture("ambiguous-key", "committed-value")
    state = json.loads(
        (tmp_path / "codexbridge-side-effect-fixture.json").read_text(encoding="utf-8")
    )

    assert reconciled["exists"] is True
    assert reconciled["outcome"]["application_count"] == 1
    assert replay["applied"] is False
    assert state["mutations"] == {
        "ambiguous-key": {
            "value": "committed-value",
            "application_count": 1,
        }
    }


def test_idempotency_key_rejects_argument_drift(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    apply_reversible_fixture("stable-key", "first")

    with pytest.raises(ValueError, match="different arguments"):
        apply_reversible_fixture("stable-key", "second")
