from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

from .config import ExternalFixturesConfig


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VALIDATION_TYPES = frozenset({"none", "json", "py_compile", "bash_n"})


@dataclass(frozen=True)
class FixtureDownload:
    path: Path
    source_url: str
    sha256: str
    size_bytes: int


def validate_fixture_request(
    config: ExternalFixturesConfig,
    url: str,
    expected_sha256: str,
    validation: str,
) -> urllib.parse.ParseResult:
    if not config.enabled:
        raise ValueError("External fixture validation is disabled")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("External fixture URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("External fixture URL must not contain credentials")
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed = {item.lower().rstrip(".") for item in config.allowed_hosts}
    if not host or host not in allowed:
        raise ValueError(
            f"External fixture host is not allowlisted: {host or '<missing>'}"
        )
    if parsed.query:
        raise ValueError("External fixture URL must not contain a query string")
    if parsed.fragment:
        raise ValueError("External fixture URL must not contain a fragment")
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise ValueError(
            "expected_sha256 must contain exactly 64 hexadecimal characters"
        )
    if validation not in _VALIDATION_TYPES:
        raise ValueError(f"Unsupported external fixture validation: {validation}")
    return parsed


def _safe_filename(parsed: urllib.parse.ParseResult) -> str:
    candidate = Path(urllib.parse.unquote(parsed.path)).name or "fixture.bin"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", candidate)
    return safe[:120] or "fixture.bin"


def _open_url(request: urllib.request.Request, timeout: int):
    return urllib.request.urlopen(request, timeout=timeout)


def download_fixture(
    config: ExternalFixturesConfig,
    *,
    url: str,
    expected_sha256: str,
    validation: str,
    run_dir: Path,
    opener: Callable[[urllib.request.Request, int], BinaryIO] = _open_url,
) -> FixtureDownload:
    parsed = validate_fixture_request(config, url, expected_sha256, validation)
    fixture_root = (run_dir / "external_fixture").resolve()
    fixture_root.mkdir(parents=True, exist_ok=True)
    target = (fixture_root / _safe_filename(parsed)).resolve()
    target.relative_to(fixture_root)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CodexBridge/ExternalFixture"},
        method="GET",
    )
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with opener(request, config.timeout_seconds) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > config.max_bytes:
                raise ValueError("External fixture exceeds configured size limit")
            with target.open("wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > config.max_bytes:
                        raise ValueError(
                            "External fixture exceeds configured size limit"
                        )
                    digest.update(chunk)
                    handle.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    actual_sha256 = digest.hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        target.unlink(missing_ok=True)
        raise ValueError(
            "External fixture SHA-256 mismatch: "
            f"expected {expected_sha256.lower()}, got {actual_sha256}"
        )
    return FixtureDownload(
        path=target,
        source_url=url,
        sha256=actual_sha256,
        size_bytes=size_bytes,
    )


def validate_fixture_file(path: Path, validation: str) -> dict:
    if validation == "none":
        return {"ok": True, "validation": validation, "exit_code": 0, "output": ""}
    if validation == "json":
        json.loads(path.read_text(encoding="utf-8"))
        return {
            "ok": True,
            "validation": validation,
            "exit_code": 0,
            "output": "valid JSON",
        }
    if validation == "py_compile":
        argv = [sys.executable, "-m", "py_compile", str(path)]
    elif validation == "bash_n":
        argv = ["bash", "-n", str(path)]
    else:
        raise ValueError(f"Unsupported external fixture validation: {validation}")
    completed = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
        shell=False,
    )
    return {
        "ok": completed.returncode == 0,
        "validation": validation,
        "argv": argv,
        "exit_code": completed.returncode,
        "output": (completed.stdout or completed.stderr)[-10000:],
    }


def fetch_validate_and_discard(
    config: ExternalFixturesConfig,
    *,
    url: str,
    expected_sha256: str,
    validation: str,
    run_dir: Path,
    opener: Callable[[urllib.request.Request, int], BinaryIO] = _open_url,
) -> dict:
    fixture = download_fixture(
        config,
        url=url,
        expected_sha256=expected_sha256,
        validation=validation,
        run_dir=run_dir,
        opener=opener,
    )
    try:
        validation_result = validate_fixture_file(fixture.path, validation)
        return {
            "ok": bool(validation_result.get("ok")),
            "source_url": fixture.source_url,
            "sha256": fixture.sha256,
            "size_bytes": fixture.size_bytes,
            "validation": validation_result,
            "discarded": True,
            "error": "" if validation_result.get("ok") else "Fixture validation failed",
        }
    finally:
        fixture.path.unlink(missing_ok=True)
        if fixture.path.exists():
            raise RuntimeError("External fixture could not be discarded")
