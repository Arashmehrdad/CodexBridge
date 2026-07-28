"""Runtime enforcement of the frozen, evidence-bound provider stack.

`FROZEN_EVIDENCE_STACK` and `PILOT_SIMILARITY_THRESHOLD` record the exact stack
`PILOT-BASIC-MEMORY-2` and `BASIC-MEMORY-GUARD-1` measured. Before this module
existed they were documentation only: nothing read them, so a provider upgraded
underneath Soma would silently inherit a health verdict that was never measured
for it.

The check is deliberately fail-closed. An unreadable executable, an unparsable
version, a missing embedding-model setting or a changed threshold all refuse --
absence of contrary evidence is not evidence of the accepted stack.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .models import (
    FROZEN_EVIDENCE_STACK,
    RefusalReason,
    RuntimeIdentity,
    RuntimeRefused,
)
from .profile import ProviderProfile
from .provider import BasicMemoryProvider


#: Config keys the provider may use for the local embedding model.
_MODEL_KEYS: tuple[str, ...] = (
    "embedding_model",
    "embedding_model_name",
    "local_embedding_model",
)

#: Config keys the provider may use for the similarity threshold.
_THRESHOLD_KEYS: tuple[str, ...] = (
    "similarity_threshold",
    "search_similarity_threshold",
    "semantic_similarity_threshold",
)

_VERSION = re.compile(r"(\d+\.\d+\.\d+(?:[.\-+][0-9A-Za-z.\-]+)?)")


def file_sha256(path: str | Path) -> str:
    """Hash a file in bounded chunks, or refuse when it cannot be read."""
    target = Path(path).expanduser()
    try:
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise RuntimeRefused(
            f"provider executable {str(target)!r} could not be read for hashing: "
            f"{exc} ({RefusalReason.RUNTIME_MISMATCH.value})"
        ) from exc


def _setting(config: dict[str, object], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        if key in config:
            return config[key]
    return None


def parse_version(text: str) -> str | None:
    """Extract a version from `bm --version` output, or None when absent."""
    match = _VERSION.search(text or "")
    return match.group(1) if match else None


def probe_runtime(
    profile: ProviderProfile, provider: BasicMemoryProvider
) -> RuntimeIdentity:
    """Measure the live provider stack. Raises rather than guessing."""
    call = provider.call("version")
    if not call.ok:
        raise RuntimeRefused(
            "provider version probe did not exit successfully "
            f"(exit={call.exit_code}): {(call.stderr or call.stdout or '').strip()[:200]} "
            f"({RefusalReason.PROVIDER_EXIT_FAILURE.value})"
        )
    version = parse_version(call.stdout) or parse_version(call.stderr)
    if version is None:
        raise RuntimeRefused(
            "provider did not report a parsable version; the frozen stack cannot "
            f"be verified ({RefusalReason.RUNTIME_MISMATCH.value})"
        )

    model = _setting(profile.config, _MODEL_KEYS)
    if not isinstance(model, str) or not model.strip():
        raise RuntimeRefused(
            "provider config declares no embedding model, so the accepted "
            f"multilingual model cannot be confirmed; the provider default is "
            f"English-only ({RefusalReason.RUNTIME_MISMATCH.value})"
        )

    raw_threshold = _setting(profile.config, _THRESHOLD_KEYS)
    threshold: float | None
    if raw_threshold is None:
        threshold = None
    elif isinstance(raw_threshold, (int, float)) and not isinstance(
        raw_threshold, bool
    ):
        threshold = float(raw_threshold)
    else:
        raise RuntimeRefused(
            f"provider similarity threshold {raw_threshold!r} is not numeric "
            f"({RefusalReason.RUNTIME_MISMATCH.value})"
        )

    executable = str(profile.executable or "")
    if not executable:
        raise RuntimeRefused(
            "the guard was given no provider executable to verify, so the frozen "
            f"stack cannot be enforced ({RefusalReason.RUNTIME_MISMATCH.value})"
        )

    return RuntimeIdentity(
        executable=executable,
        executable_sha256=file_sha256(executable),
        provider_version=version,
        embedding_model=model.strip(),
        similarity_threshold=threshold,
        config_sha256=config_sha256(profile.config),
    )


def config_sha256(config: dict[str, object]) -> str:
    """Stable hash of the accepted configuration."""
    payload = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_runtime(
    identity: RuntimeIdentity,
    *,
    expected_executable_sha256: str = "",
) -> None:
    """Refuse any runtime that is not the frozen evidence stack."""
    problems = list(identity.mismatches())
    if (
        expected_executable_sha256
        and identity.executable_sha256 != expected_executable_sha256
    ):
        problems.append(
            f"provider executable hash {identity.executable_sha256[:16]}... is not "
            f"the pinned {expected_executable_sha256[:16]}..."
        )
    if problems:
        raise RuntimeRefused(
            "provider runtime does not match the accepted evidence stack "
            f"{FROZEN_EVIDENCE_STACK['basic_memory']}: "
            + "; ".join(problems)
            + f" ({RefusalReason.RUNTIME_MISMATCH.value})"
        )
