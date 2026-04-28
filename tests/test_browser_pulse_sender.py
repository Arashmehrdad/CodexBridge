from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from codexbridge.supervisor_store import SupervisorStore


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "browser_pulse_sender.py"
LAUNCHER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "start_chrome_cdp.ps1"
SPEC = importlib.util.spec_from_file_location("browser_pulse_sender", SCRIPT_PATH)
assert SPEC and SPEC.loader
browser_pulse_sender = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser_pulse_sender)


def test_validate_chat_url_requires_real_chatgpt_conversation_url() -> None:
    assert browser_pulse_sender.validate_chat_url("https://chatgpt.com/c/abc123") == "https://chatgpt.com/c/abc123"
    with pytest.raises(ValueError):
        browser_pulse_sender.validate_chat_url("https://chatgpt.com/")
    with pytest.raises(ValueError):
        browser_pulse_sender.validate_chat_url("https://example.com/c/abc123")


def test_validate_cdp_url_is_local_only() -> None:
    assert browser_pulse_sender.validate_local_cdp_url("http://127.0.0.1:9222") == "http://127.0.0.1:9222"
    assert browser_pulse_sender.validate_local_cdp_url("http://localhost:9222") == "http://localhost:9222"
    with pytest.raises(ValueError):
        browser_pulse_sender.validate_local_cdp_url("https://127.0.0.1:9222")
    with pytest.raises(ValueError):
        browser_pulse_sender.validate_local_cdp_url("http://192.168.1.10:9222")


def test_build_prompt_uses_resume_prompt_and_redacts(tmp_path: Path) -> None:
    store = SupervisorStore(tmp_path)
    supervisor = store.create_supervisor(repo_name="sample", objective="Test", status="needs_input")
    prompt_path = tmp_path / "supervisors" / supervisor["supervisor_id"] / "resume_prompt.txt"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Use token=super-secret-value", encoding="utf-8")

    prompt = browser_pulse_sender.build_prompt(
        runs_dir=tmp_path,
        supervisor_id=supervisor["supervisor_id"],
        status="needs_input",
    )

    assert "super-secret-value" not in prompt
    assert "[REDACTED]" in prompt


def test_run_once_dry_run_logs_safe_fields_only(tmp_path: Path) -> None:
    store = SupervisorStore(tmp_path)
    supervisor = store.create_supervisor(repo_name="sample", objective="Test", status="completed")
    log_file = tmp_path / "pulse.jsonl"

    result = browser_pulse_sender.run_once(
        store=store,
        runs_dir=tmp_path,
        supervisor_id=supervisor["supervisor_id"],
        chat_url="https://chatgpt.com/c/abc123",
        dry_run=True,
        override_prompt="Browser pulse smoke test. Reply only: pulse received.",
        log_file=log_file,
    )

    assert result["success"] is True
    assert result["sent"] is False
    logged = log_file.read_text(encoding="utf-8")
    assert supervisor["supervisor_id"] in logged
    assert "completed" in logged
    assert "Browser pulse smoke test" not in logged


def test_run_once_refuses_non_handoff_status(tmp_path: Path) -> None:
    store = SupervisorStore(tmp_path)
    supervisor = store.create_supervisor(repo_name="sample", objective="Test", status="planning")

    result = browser_pulse_sender.run_once(
        store=store,
        runs_dir=tmp_path,
        supervisor_id=supervisor["supervisor_id"],
        chat_url="https://chatgpt.com/c/abc123",
        dry_run=True,
    )

    assert result["success"] is False
    assert result["sent"] is False
    assert result["reason"] == "status is not a handoff state"


def test_cdp_launcher_documents_verified_dedicated_profile_flow() -> None:
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "[string]$UserDataDir" in launcher
    assert "[switch]$KillExisting" in launcher
    assert "[int]$WaitSeconds = 20" in launcher
    assert "--remote-debugging-port=$Port" in launcher
    assert "--remote-debugging-address=127.0.0.1" in launcher
    assert "--no-first-run" in launcher
    assert "--new-window" in launcher
    assert "--user-data-dir=$UserDataDir" in launcher
    assert "http://127.0.0.1:$Port/json/version" in launcher
    assert "Modern Chrome/Edge builds may refuse remote debugging on the default profile" in launcher
    assert "RemoteDebuggingAllowed" in launcher
