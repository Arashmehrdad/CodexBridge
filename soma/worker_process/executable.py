"""Exact executable identity, verified before process creation.

Pilot Finding 10 recorded that the Claude Code npm package ships a native
``bin/claude.exe`` which ``subprocess`` cannot resolve from a bare name on
Windows, so a full resolved path is required anyway. This module makes that
requirement a check rather than a convention, and adds the part the pilot did
not need: proof that the file at the path is still the file that was verified.

PATH lookup is refused outright. Resolving a bare name means whatever the
environment says today, which is exactly the substitution this check exists to
prevent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Final


#: Executables are read fully to hash them. This bound stops a mistaken path to
#: a huge file from stalling a launch; anything larger is refused rather than
#: partially hashed, because a partial hash proves nothing.
MAX_HASHED_BYTES: Final[int] = 256 * 1024 * 1024


class ExecutableRejected(ValueError):
    """The requested executable cannot be used as a launch target."""


@dataclass(frozen=True)
class ExecutableIdentity:
    """A file identity strong enough to detect replacement between checks.

    ``content_sha256`` is the real protection: device/inode and mtime can be
    reproduced by an attacker who controls the filesystem, and mtime alone is
    famously forgeable. Size and the filesystem index are kept because they
    make the common accidental case -- a rebuilt or re-installed binary --
    obvious in evidence.
    """

    path: str
    size_bytes: int
    device: int
    index: int
    mtime_ns: int
    content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "device": self.device,
            "index": self.index,
            "mtime_ns": self.mtime_ns,
            "content_sha256": self.content_sha256,
        }


def _hash_file(path: Path, size_bytes: int) -> str:
    if size_bytes > MAX_HASHED_BYTES:
        raise ExecutableRejected(
            f"executable is {size_bytes} bytes, above the {MAX_HASHED_BYTES} byte "
            "hashing bound; refusing to launch an unverifiable target"
        )
    digest = sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_executable(executable_path: str) -> ExecutableIdentity:
    """Verify a launch target and capture its identity.

    Refuses, in order: empty, non-absolute, unresolved traversal, missing,
    directory, and (on POSIX) a file without an execute bit.
    """
    if not executable_path or not executable_path.strip():
        raise ExecutableRejected("executable_path is required")
    raw = Path(executable_path)
    if not raw.is_absolute():
        raise ExecutableRejected(
            f"executable_path must be absolute, refusing PATH lookup: "
            f"{executable_path!r}"
        )
    if ".." in raw.parts:
        raise ExecutableRejected(
            f"executable_path must not contain traversal segments: "
            f"{executable_path!r}"
        )

    # resolve() follows symlinks, so identity is captured for the file that
    # would actually execute rather than for the link that names it.
    resolved = raw.resolve()
    if not resolved.exists():
        raise ExecutableRejected(f"executable does not exist: {resolved}")
    if resolved.is_dir():
        raise ExecutableRejected(f"executable_path is a directory: {resolved}")
    if not resolved.is_file():
        raise ExecutableRejected(f"executable_path is not a regular file: {resolved}")
    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise ExecutableRejected(f"executable is not executable: {resolved}")

    stat = resolved.stat()
    return ExecutableIdentity(
        path=str(resolved),
        size_bytes=int(stat.st_size),
        device=int(getattr(stat, "st_dev", 0)),
        index=int(getattr(stat, "st_ino", 0)),
        mtime_ns=int(stat.st_mtime_ns),
        content_sha256=_hash_file(resolved, int(stat.st_size)),
    )


def require_unchanged(identity: ExecutableIdentity) -> ExecutableIdentity:
    """Re-verify immediately before process creation.

    The window between verification and launch is small but real, and it is the
    window a path-replacement attack aims at. Any difference is fatal: this
    never returns a "changed but probably fine" result.
    """
    current = verify_executable(identity.path)
    if current == identity:
        return current
    differing = sorted(
        field
        for field in ("size_bytes", "device", "index", "mtime_ns", "content_sha256")
        if getattr(current, field) != getattr(identity, field)
    )
    raise ExecutableRejected(
        f"executable identity changed between verification and launch for "
        f"{identity.path}: {differing}"
    )
