from __future__ import annotations

from codexbridge.memory.redaction import detect_sensitivity, redact_sensitive_text


def detect_sensitive_text(text: str) -> list[str]:
    return detect_sensitivity(text)


def redact_for_codex(text: str) -> str:
    return redact_sensitive_text(text)
