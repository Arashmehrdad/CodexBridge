"""Sanitised child environment construction.

The environment is built from an explicit allowlist, not by copying the
controller's environment and deleting known-bad names. A denylist fails open:
every new credential variable a developer adds would reach the worker until
someone remembers to ban it. An allowlist fails closed, which is the only safe
default when the child is a coding agent with a shell.

Evidence records variable *names* and a classification. Values never appear in
evidence, logs, argv, or test output -- not even hashed, since a hashed secret
with a known candidate set is not a protected secret.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping


class RemovalReason(str, Enum):
    """Why a variable was withheld. Ordered most-specific first when reported."""

    PROVIDER_RECURSION_MARKER = "provider_recursion_marker"
    SOMA_OR_MCP_CONFIGURATION = "soma_or_mcp_configuration"
    SECRET_SHAPED_NAME = "secret_shaped_name"
    NOT_ALLOWLISTED = "not_allowlisted"


#: Variables an ordinary Windows or POSIX process needs to run at all. Nothing
#: here identifies a user account, a credential, or a tool configuration.
BASE_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        # Windows
        "SystemRoot",
        "SystemDrive",
        "windir",
        "COMSPEC",
        "PATHEXT",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "OS",
        "TEMP",
        "TMP",
        # POSIX
        "HOME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        # both
        "PATH",
    }
)

#: Names that look like a credential regardless of who set them.
SECRET_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|SESSION|COOKIE|SIGNATURE"
    r"|PRIVATE|LICEN[CS]E|ACCESS_ID|SUBSCRIPTION)",
    re.IGNORECASE,
)

#: Names that would hand a worker Soma's own control plane or connector wiring.
SOMA_CONFIGURATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(SOMA_|MCP_|HERMES_|CLOUDFLARE_|TRADING_|OBSIDIAN_|BASIC_MEMORY_)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EnvironmentEvidence:
    """Names and classifications only. No values, ever."""

    allowed_names: tuple[str, ...]
    removed: tuple[tuple[str, RemovalReason], ...]
    declared_removals_honoured: tuple[str, ...]
    allowlist_extra: tuple[str, ...] = ()

    def removed_names(self) -> tuple[str, ...]:
        return tuple(name for name, _reason in self.removed)

    def reason_for(self, name: str) -> RemovalReason | None:
        for candidate, reason in self.removed:
            if candidate == name:
                return reason
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed_names": list(self.allowed_names),
            "removed": [
                {"name": name, "reason": reason.value} for name, reason in self.removed
            ],
            "declared_removals_honoured": list(self.declared_removals_honoured),
            "allowlist_extra": list(self.allowlist_extra),
        }


@dataclass(frozen=True)
class SanitisedEnvironment:
    environment: Mapping[str, str] = field(default_factory=dict)
    evidence: EnvironmentEvidence = field(
        default_factory=lambda: EnvironmentEvidence((), (), ())
    )


def classify_removal(
    name: str, *, declared_removals: frozenset[str]
) -> RemovalReason:
    upper = name.upper()
    if upper in declared_removals:
        return RemovalReason.PROVIDER_RECURSION_MARKER
    if SOMA_CONFIGURATION_PATTERN.search(name):
        return RemovalReason.SOMA_OR_MCP_CONFIGURATION
    if SECRET_NAME_PATTERN.search(name):
        return RemovalReason.SECRET_SHAPED_NAME
    return RemovalReason.NOT_ALLOWLISTED


def build_child_environment(
    *,
    parent_environment: Mapping[str, str] | None = None,
    declared_removals: tuple[str, ...] = (),
    allowlist_extra: tuple[str, ...] = (),
    additions: Mapping[str, str] | None = None,
) -> SanitisedEnvironment:
    """Build a child environment from an allowlist and report what was withheld.

    ``declared_removals`` comes from the accepted adapter contract's
    ``environment_remove``. Those names are refused even if an operator puts
    them in ``allowlist_extra``: pilot Finding 8 measured that Claude Code
    refuses to start inside another Claude Code session, so a recursion marker
    reaching the child is a launch failure, not a preference.

    ``additions`` are values Soma sets deliberately. They are not read from the
    parent and are never classified as inherited.
    """
    source = dict(os.environ if parent_environment is None else parent_environment)
    declared = frozenset(name.upper() for name in declared_removals)
    extra = tuple(dict.fromkeys(allowlist_extra))

    # A declared recursion marker can never be allowlisted back in.
    effective_extra = tuple(name for name in extra if name.upper() not in declared)
    allowed_names = BASE_ALLOWLIST | set(effective_extra)

    environment: dict[str, str] = {}
    removed: list[tuple[str, RemovalReason]] = []
    for name in sorted(source):
        if name.upper() in declared:
            removed.append((name, RemovalReason.PROVIDER_RECURSION_MARKER))
            continue
        if name in allowed_names:
            environment[name] = source[name]
            continue
        removed.append((name, classify_removal(name, declared_removals=declared)))

    for name, value in (additions or {}).items():
        environment[name] = value

    honoured = tuple(
        name for name in declared_removals if name.upper() in {
            candidate.upper() for candidate, _ in removed
        }
    )
    evidence = EnvironmentEvidence(
        allowed_names=tuple(sorted(environment)),
        removed=tuple(removed),
        declared_removals_honoured=honoured,
        allowlist_extra=effective_extra,
    )
    return SanitisedEnvironment(environment=environment, evidence=evidence)


def find_secret_shaped_names(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Return names in a built environment that still look credential-bearing.

    Used as an assertion in tests and as a pre-launch self-check: if an operator
    allowlists something that looks like a secret, that must be visible rather
    than silent.
    """
    return tuple(
        sorted(name for name in environment if SECRET_NAME_PATTERN.search(name))
    )
