"""Bounded adapter over the official Basic Memory CLI.

Exact allowlist, no arbitrary invocation. Two operations are refused outright
because the pilot measured them as unsafe controls:

* ``bm status --wait`` livelocks -- each poll restarts a full scan that never
  applies, so it is not an accepted synchronization or readiness mechanism;
* ``bm doctor`` is not a project-completeness oracle -- it passed while both
  pilot projects held a partial 6-of-14 index, because it validates the
  write/sync/search mechanism using its own scratch project.

Synchronization and recovery use ``bm reindex``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Sequence

from .models import RefusalReason, ToolRefused
from .profile import ProviderProfile, validate_env


#: The only provider operations the guard will ever invoke, and the exact
#: argv prefix each is permitted to use.
ALLOWED_OPERATIONS: dict[str, tuple[str, ...]] = {
    "search": ("tool", "search-notes"),
    "read_note": ("tool", "read-note"),
    "status": ("status",),
    "project_info": ("project", "info"),
    "reindex": ("reindex",),
}

#: Argument fragments that are never forwarded, whatever the operation.
FORBIDDEN_ARGS: tuple[str, ...] = (
    "--wait",       # livelocks; see module docstring
    "--cloud",      # cloud routing
    "--project-id",  # UUID routing bypasses the guard's name binding
)

#: Subcommands the guard will never invoke.
FORBIDDEN_OPERATIONS: tuple[str, ...] = (
    "cloud",
    "doctor",
    "import",
    "ci",
    "workspace",
    "mcp",
    "reset",
    "delete-note",
    "write-note",
    "edit-note",
)


#: Executes argv with an environment and returns (exit_code, stdout, stderr).
Runner = Callable[[Sequence[str], dict[str, str], int], tuple[int | None, str, str]]


@dataclass(frozen=True)
class ProviderCall:
    operation: str
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class BasicMemoryProvider:
    """Invokes the provider through a narrow, validated surface."""

    def __init__(
        self,
        profile: ProviderProfile,
        runner: Runner,
        *,
        default_timeout: int = 300,
    ) -> None:
        self._profile = profile
        self._runner = runner
        self._default_timeout = default_timeout

    def call(
        self,
        operation: str,
        *args: str,
        provider_project: str,
        process_env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> ProviderCall:
        prefix = ALLOWED_OPERATIONS.get(operation)
        if prefix is None:
            raise ToolRefused(
                f"operation {operation!r} is not in the guard allowlist "
                f"({RefusalReason.TOOL_NOT_ALLOWED.value}); allowed: "
                f"{sorted(ALLOWED_OPERATIONS)}"
            )
        for arg in args:
            text = str(arg)
            for bad in FORBIDDEN_ARGS:
                if text == bad or text.startswith(bad + "="):
                    raise ToolRefused(
                        f"argument {text!r} is refused "
                        f"({RefusalReason.FORBIDDEN_SYNC_PATH.value})"
                    )
            if text in FORBIDDEN_OPERATIONS:
                raise ToolRefused(f"subcommand {text!r} is refused")

        if not provider_project:
            raise ToolRefused("provider_project is required for every call")

        # Identity is always explicit and always the guard's, never the caller's.
        # `project info` takes the project as a POSITIONAL argument and rejects
        # `--project`; every other allowed operation takes the flag. Getting this
        # wrong silently breaks coverage reconciliation, so it is encoded here
        # rather than left to callers.
        if operation == "project_info":
            argv = [*prefix, provider_project, *[str(a) for a in args]]
        else:
            argv = [*prefix, *[str(a) for a in args], "--project", provider_project]

        env = self._profile.env(process_env)
        validate_env(env)

        code, out, err = self._runner(
            argv, env, timeout if timeout is not None else self._default_timeout
        )
        return ProviderCall(
            operation=operation, argv=tuple(argv),
            exit_code=code, stdout=out, stderr=err,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def parse_json(call: ProviderCall) -> dict | None:
        """Parse a JSON payload, tolerating the CLI's decorative output."""
        text = (call.stdout or "").strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                value = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def parse_results(call: ProviderCall) -> list[dict[str, object]] | None:
        """Extract search results, or None when the shape is not understood.

        None means unproven, never empty. A caller must not read an unparsed
        response as "no matches".
        """
        payload = BasicMemoryProvider.parse_json(call)
        if payload is None:
            return None
        results = payload.get("results")
        if not isinstance(results, list):
            return None
        out: list[dict[str, object]] = []
        for item in results:
            if isinstance(item, dict):
                out.append(item)
        return out
