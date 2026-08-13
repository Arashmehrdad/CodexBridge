"""Read-only mechanical source loader for one immutable Git commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

from soma.company_kernel.models import validate_opaque
from soma.reasoning.repository_evidence import RepositoryEvidenceError


class GitCommitSourceLoader:
    """Load exact repository file bytes from one resolved immutable commit."""

    def __init__(self, repository_root: Path, source_revision: str = "HEAD") -> None:
        root = Path(repository_root).resolve()
        if not root.is_dir():
            raise RepositoryEvidenceError(
                "repository_root must be an existing directory"
            )
        validate_opaque(source_revision, "source_revision", max_length=256)
        self.repository_root = root
        self.source_commit = self._resolve_commit(source_revision)

    @property
    def source_revision_ref(self) -> str:
        return f"git:{self.source_commit}"

    def _git(self, *args: str) -> bytes:
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.repository_root), *args],
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryEvidenceError(f"Git source lookup failed: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RepositoryEvidenceError(detail[-1000:] or "Git source lookup failed")
        return bytes(completed.stdout)

    def _resolve_commit(self, source_revision: str) -> str:
        raw = self._git("rev-parse", "--verify", f"{source_revision}^{{commit}}")
        try:
            commit = raw.decode("ascii").strip().lower()
        except UnicodeDecodeError as exc:
            raise RepositoryEvidenceError("Git commit identity is not ASCII") from exc
        if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
            raise RepositoryEvidenceError(
                "source_revision did not resolve to one exact Git commit"
            )
        return commit

    def load(self, source_path: str) -> bytes:
        if not source_path or "\x00" in source_path:
            raise RepositoryEvidenceError("source_path must be non-empty")
        return self._git("show", f"{self.source_commit}:{source_path}")
