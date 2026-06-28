from __future__ import annotations

import json
from pathlib import Path

from codexbridge.supervisor_notifications import (
    FileNotificationSink,
    NotificationDispatcher,
    WebhookNotificationSink,
    WindowsToastNotificationSink,
    sanitize_notification,
)
from codexbridge.supervisor_store import SupervisorStore


SUPERVISOR_ID = "20260428T120000Z_supervisor_abcdef12"


def notification() -> dict:
    return {
        "id": 1,
        "supervisor_id": SUPERVISOR_ID,
        "title": "Done",
        "message": "API_KEY=abc123",
        "payload": {"token": "token: secret-value", "large": "x" * 100},
    }


def test_sanitize_notification_redacts_and_truncates() -> None:
    safe = sanitize_notification(notification(), max_payload_chars=20)
    assert "abc123" not in safe["message"]
    assert "secret-value" not in str(safe["payload"])
    assert "[truncated" in safe["payload"]["large"]


def test_file_sink_disabled_by_default(tmp_path: Path) -> None:
    sink = FileNotificationSink(tmp_path / "notifications.jsonl")
    result = sink.send(notification())
    assert result["status"] == "disabled"
    assert not (tmp_path / "notifications.jsonl").exists()


def test_file_sink_writes_sanitized_jsonl_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "notifications.jsonl"
    sink = FileNotificationSink(path, enabled=True)
    result = sink.send(notification())
    assert result["status"] == "delivered"
    saved = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert "abc123" not in saved["message"]


def test_webhook_sink_disabled_by_default(monkeypatch) -> None:
    calls = []
    sink = WebhookNotificationSink(transport=lambda *args, **kwargs: calls.append(args))
    result = sink.send(notification())
    assert result["status"] == "disabled"
    assert calls == []


def test_webhook_sink_uses_env_url_and_stubbed_transport(monkeypatch) -> None:
    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    captured = {}

    def transport(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("CODEXBRIDGE_WEBHOOK_URL", "https://example.invalid/hook")
    sink = WebhookNotificationSink(
        enabled=True, url_env="CODEXBRIDGE_WEBHOOK_URL", transport=transport
    )
    result = sink.send(notification())
    assert result["status"] == "delivered"
    assert captured["url"] == "https://example.invalid/hook"
    assert "secret-value" not in captured["body"]


def test_windows_toast_disabled_by_default(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "codexbridge.supervisor_notifications.subprocess.run",
        lambda *args, **kwargs: calls.append(args),
    )
    result = WindowsToastNotificationSink().send(notification())
    assert result["status"] == "disabled"
    assert calls == []


def test_windows_toast_wrapper_handles_unavailable_toast(monkeypatch) -> None:
    class Result:
        returncode = 1
        stderr = "unavailable"
        stdout = ""

    monkeypatch.setattr(
        "codexbridge.supervisor_notifications.subprocess.run",
        lambda *args, **kwargs: Result(),
    )
    result = WindowsToastNotificationSink(enabled=True).send(notification())
    assert result["status"] == "failed"
    assert "unavailable" in result["error"]


def test_dispatcher_updates_delivery_state_without_raising(tmp_path: Path) -> None:
    store = SupervisorStore(tmp_path / "runs")
    store.create_supervisor(
        supervisor_id=SUPERVISOR_ID, repo_name="codexbridge", objective="notify"
    )
    stored = store.create_notification(
        SUPERVISOR_ID,
        event_stage="completed",
        event_level="info",
        kind="completed",
        title="Done",
        message="Done",
        payload={},
        dedupe_key="completed",
    )

    class FailingSink:
        def send(self, notification):
            raise RuntimeError("sink failed")

    updated = NotificationDispatcher(store, [FailingSink()]).deliver(stored)
    assert updated["delivery_status"] == "failed"
    assert updated["delivery_attempts"] == 1
    assert "sink failed" in updated["last_error"]
