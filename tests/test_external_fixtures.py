from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from codexbridge.config import ExternalFixturesConfig
from codexbridge.external_fixtures import (
    fetch_validate_and_discard,
    validate_fixture_request,
)


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, announced_size: int | None = None):
        super().__init__(payload)
        self.headers = {"Content-Length": str(announced_size or len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


def fixture_config(**changes) -> ExternalFixturesConfig:
    values = {
        "enabled": True,
        "allowed_hosts": ["fixtures.example.com"],
        "max_bytes": 1024,
        "timeout_seconds": 5,
    }
    values.update(changes)
    return ExternalFixturesConfig(**values)


def test_fixture_policy_requires_enabled_https_allowlist() -> None:
    digest = "a" * 64
    with pytest.raises(ValueError, match="disabled"):
        validate_fixture_request(
            ExternalFixturesConfig(),
            "https://fixtures.example.com/data.json",
            digest,
            "json",
        )
    with pytest.raises(ValueError, match="HTTPS"):
        validate_fixture_request(
            fixture_config(),
            "http://fixtures.example.com/data.json",
            digest,
            "json",
        )
    with pytest.raises(ValueError, match="not allowlisted"):
        validate_fixture_request(
            fixture_config(),
            "https://other.example.com/data.json",
            digest,
            "json",
        )


def test_fixture_json_is_hash_verified_and_discarded(tmp_path: Path) -> None:
    payload = b'{"ok": true}\n'
    digest = hashlib.sha256(payload).hexdigest()
    result = fetch_validate_and_discard(
        fixture_config(),
        url="https://fixtures.example.com/data.json",
        expected_sha256=digest,
        validation="json",
        run_dir=tmp_path,
        opener=lambda _request, _timeout: FakeResponse(payload),
    )
    assert result["ok"] is True
    assert result["sha256"] == digest
    assert result["discarded"] is True
    assert list((tmp_path / "external_fixture").glob("*")) == []


def test_fixture_hash_mismatch_and_size_failure_leave_no_file(tmp_path: Path) -> None:
    payload = b"payload"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        fetch_validate_and_discard(
            fixture_config(),
            url="https://fixtures.example.com/data.bin",
            expected_sha256="0" * 64,
            validation="none",
            run_dir=tmp_path,
            opener=lambda _request, _timeout: FakeResponse(payload),
        )
    digest = hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError, match="size limit"):
        fetch_validate_and_discard(
            fixture_config(max_bytes=4),
            url="https://fixtures.example.com/data.bin",
            expected_sha256=digest,
            validation="none",
            run_dir=tmp_path,
            opener=lambda _request, _timeout: FakeResponse(payload),
        )
    assert list((tmp_path / "external_fixture").glob("*")) == []
