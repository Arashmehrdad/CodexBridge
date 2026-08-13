"""Lazy Codex App Server client/preflight factories for repository reasoning."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .codex_app_server import (
    CodexAppServerClient,
    StdioCodexTransport,
    canonical_schema_manifest_hash,
    resolve_codex_executable,
)
from .codex_repository_backend_support import ClientFactory, Preflight
from .codex_repository_contract import CODEX_REPOSITORY_MODEL


def default_codex_repository_client_factory(
    working_directory: Path,
) -> ClientFactory:
    cwd = Path(working_directory).resolve()

    def create() -> CodexAppServerClient:
        executable = resolve_codex_executable()
        transport = StdioCodexTransport(
            codex_executable=executable,
            working_directory=str(cwd),
        )
        client = CodexAppServerClient(transport)
        client.initialize()
        return client

    return create


def _codex_command(executable: str, *arguments: str) -> list[str]:
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
        return [comspec, "/d", "/s", "/c", executable, *arguments]
    return [executable, *arguments]


def default_codex_repository_preflight(
    working_directory: Path,
    *,
    model: str = CODEX_REPOSITORY_MODEL,
) -> Preflight:
    """Return a lazy drift/auth/model preflight; no check runs at construction."""
    cwd = Path(working_directory).resolve()

    def check() -> Mapping[str, Any]:
        executable = resolve_codex_executable()
        with tempfile.TemporaryDirectory(prefix="soma-codex-repository-schema-") as temp:
            completed = subprocess.run(
                _codex_command(
                    executable,
                    "app-server",
                    "generate-json-schema",
                    "--out",
                    temp,
                ),
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "Codex App Server schema generation failed: "
                    + completed.stderr[-1000:]
                )
            protocol_hash, schema_count = canonical_schema_manifest_hash(Path(temp))

        client = default_codex_repository_client_factory(cwd)()
        try:
            account = client.account_read()
            models_result = client.model_list(include_hidden=False)
        finally:
            client.close()
        account_value = account.get("account") or account.get("data") or account
        auth_type = ""
        if isinstance(account_value, Mapping):
            auth_type = str(
                account_value.get("type")
                or account_value.get("authType")
                or account_value.get("auth_type")
                or ""
            ).lower()
        models_raw = models_result.get("data") or models_result.get("models") or []
        models: list[str] = []
        if isinstance(models_raw, list):
            for item in models_raw:
                if isinstance(item, Mapping):
                    candidate = item.get("model") or item.get("id") or item.get("slug")
                    if isinstance(candidate, str) and candidate:
                        models.append(candidate)
        return {
            "auth_type": auth_type,
            "protocol_manifest_sha256": protocol_hash,
            "schema_count": schema_count,
            "models": models,
            "model_available": model in set(models),
        }

    return check
