from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .events import redact_and_truncate


def sanitize_notification(
    notification: dict[str, Any], max_payload_chars: int = 4000
) -> dict[str, Any]:
    return redact_and_truncate(notification, limit=max_payload_chars)


class FileNotificationSink:
    def __init__(
        self, path: str | Path, *, enabled: bool = False, max_payload_chars: int = 4000
    ):
        self.path = Path(path) if path else None
        self.enabled = enabled
        self.max_payload_chars = max_payload_chars

    def send(self, notification: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"sent": False, "status": "disabled", "error": ""}
        if self.path is None:
            return {
                "sent": False,
                "status": "failed",
                "error": "file sink path is required",
            }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = sanitize_notification(notification, self.max_payload_chars)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return {"sent": True, "status": "delivered", "error": ""}


class WebhookNotificationSink:
    def __init__(
        self,
        *,
        enabled: bool = False,
        url_env: str = "",
        timeout_seconds: int = 5,
        transport: Callable[..., Any] | None = None,
        max_payload_chars: int = 4000,
    ):
        self.enabled = enabled
        self.url_env = url_env
        self.timeout_seconds = timeout_seconds
        self.transport = transport or urllib.request.urlopen
        self.max_payload_chars = max_payload_chars

    def send(self, notification: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"sent": False, "status": "disabled", "error": ""}
        if not self.url_env:
            return {
                "sent": False,
                "status": "failed",
                "error": "webhook url_env is required",
            }
        url = os.environ.get(self.url_env)
        if not url:
            return {
                "sent": False,
                "status": "failed",
                "error": "webhook URL environment variable is not set",
            }
        body = json.dumps(
            sanitize_notification(notification, self.max_payload_chars)
        ).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST", headers={"Content-Type": "application/json"}
        )
        with self.transport(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
        if int(status) >= 400:
            return {
                "sent": False,
                "status": "failed",
                "error": f"webhook returned HTTP {status}",
            }
        return {"sent": True, "status": "delivered", "error": ""}


class WindowsToastNotificationSink:
    def __init__(self, *, enabled: bool = False, max_payload_chars: int = 4000):
        self.enabled = enabled
        self.max_payload_chars = max_payload_chars

    def send(self, notification: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"sent": False, "status": "disabled", "error": ""}
        safe = sanitize_notification(notification, self.max_payload_chars)
        title = str(safe.get("title", "Soma")).replace("'", "''")
        message = str(safe.get("message", "")).replace("'", "''")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            f"[void](New-BurntToastNotification -Text '{title}', '{message}')"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                text=True,
                capture_output=True,
                timeout=5,
            )
        except Exception as exc:
            return {"sent": False, "status": "failed", "error": str(exc)}
        if completed.returncode != 0:
            return {
                "sent": False,
                "status": "failed",
                "error": (completed.stderr or completed.stdout).strip(),
            }
        return {"sent": True, "status": "delivered", "error": ""}


class NotificationDispatcher:
    def __init__(self, store, sinks: list[Any] | None = None):
        self.store = store
        self.sinks = sinks or []

    def deliver(self, notification: dict[str, Any]) -> dict[str, Any]:
        if not self.sinks:
            return self.store.update_notification_delivery(
                notification["id"],
                delivery_status="pending",
                last_error="",
                increment_attempts=False,
            )
        errors: list[str] = []
        delivered = False
        for sink in self.sinks:
            try:
                result = sink.send(notification)
                delivered = delivered or bool(result.get("sent"))
                if result.get("status") == "failed" and result.get("error"):
                    errors.append(str(result["error"]))
            except Exception as exc:
                errors.append(str(exc))
        if delivered:
            return self.store.update_notification_delivery(
                notification["id"], delivery_status="delivered", last_error=""
            )
        status = "failed" if errors else "pending"
        return self.store.update_notification_delivery(
            notification["id"], delivery_status=status, last_error="; ".join(errors)
        )
