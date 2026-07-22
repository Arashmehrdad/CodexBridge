from __future__ import annotations

import re


SENSITIVE_MARKERS = (
    "api key",
    "secret",
    "password",
    "token",
    "private key",
    "credential",
    "authorization header",
    "authorization:",
    "bearer token",
    "bearer ",
)


def detect_sensitivity(text: str) -> list[str]:
    lowered = text.lower()
    return [
        marker.upper().replace(" ", "_").replace(":", "")
        for marker in SENSITIVE_MARKERS
        if marker in lowered
    ]


def redact_sensitive_text(text: str) -> str:
    redacted = text
    patterns = [
        r"(?i)(api[_ -]?key\s*[:=]\s*)\S+",
        r"(?i)(secret\s*[:=]\s*)\S+",
        r"(?i)(password\s*[:=]\s*)\S+",
        r"(?i)(token\s*[:=]\s*)\S+",
        r"(?i)(authorization\s*[:=]\s*)[^\n]+",
        r"(?i)(bearer\s+)[A-Za-z0-9._\-]+",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    ]
    for pattern in patterns:
        redacted = re.sub(
            pattern,
            lambda match: match.group(1) + "[REDACTED]",
            redacted,
            flags=re.DOTALL,
        )
    return redacted
