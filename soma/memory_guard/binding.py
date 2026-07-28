"""Exact project identity resolution. Refuses before any provider call.

Nothing here infers identity. Provider defaults, the current working directory,
an active Obsidian vault and any previously selected Basic Memory project are all
non-signals by construction: the only input is an explicit `project_id`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from ..project_scope.models import (
    ProjectLifecycle,
    canonical_repository_root,
    repository_identity_hash,
    validate_opaque_id,
)
from .models import IdentityRefused, ProviderBinding, RefusalReason


class BindingSource(Protocol):
    """Supplies the approved project_id -> provider project + root mapping."""

    def lookup(self, project_id: str) -> tuple[str, str] | None:
        """Return (provider_project, canonical_root) or None when unbound."""


class StaticBindingSource:
    """An explicit, owner-declared binding table.

    A mapping is authority, not a hint. An absent entry is a refusal, never a
    reason to fall back to a default project.
    """

    def __init__(self, bindings: dict[str, tuple[str, str]]) -> None:
        self._bindings = dict(bindings)
        seen_projects: dict[str, str] = {}
        seen_roots: dict[str, str] = {}
        for project_id, (provider_project, root) in self._bindings.items():
            if provider_project in seen_projects:
                raise IdentityRefused(
                    f"provider project {provider_project!r} is bound to both "
                    f"{seen_projects[provider_project]!r} and {project_id!r}; "
                    "one provider project may serve exactly one Soma project"
                )
            seen_projects[provider_project] = project_id
            identity = repository_identity_hash(root)
            if identity in seen_roots:
                raise IdentityRefused(
                    f"canonical root {root!r} is bound to both "
                    f"{seen_roots[identity]!r} and {project_id!r}; "
                    "one Markdown root may serve exactly one Soma project"
                )
            seen_roots[identity] = project_id

    def lookup(self, project_id: str) -> tuple[str, str] | None:
        return self._bindings.get(project_id)


class ProjectBindingResolver:
    """Resolves and validates identity, or refuses.

    `scope_store` is optional. When supplied, the project must exist in
    ProjectScope and be `active`; a suspended or archived project is refused even
    if a binding exists for it.
    """

    def __init__(
        self,
        source: BindingSource,
        *,
        scope_store: object | None = None,
    ) -> None:
        self._source = source
        self._scope_store = scope_store

    def resolve(self, project_id: str | None) -> ProviderBinding:
        if project_id is None or not str(project_id).strip():
            raise IdentityRefused(
                "project_id is required; the guard never infers project identity "
                f"({RefusalReason.PROJECT_OMITTED.value})"
            )
        project_id = validate_opaque_id(str(project_id), "project_id")

        lifecycle, scope_generation = self._lifecycle(project_id)
        if lifecycle is None:
            raise IdentityRefused(
                f"project {project_id!r} is not present in ProjectScope "
                f"({RefusalReason.PROJECT_UNKNOWN.value})"
            )
        if lifecycle is not ProjectLifecycle.ACTIVE:
            raise IdentityRefused(
                f"project {project_id!r} is {lifecycle.value}, not active "
                f"({RefusalReason.PROJECT_INACTIVE.value})"
            )

        bound = self._source.lookup(project_id)
        if bound is None:
            raise IdentityRefused(
                f"project {project_id!r} has no approved provider binding "
                f"({RefusalReason.NO_BINDING.value})"
            )
        provider_project, root = bound
        if not provider_project or not str(provider_project).strip():
            raise IdentityRefused(
                f"project {project_id!r} has an empty provider project name "
                f"({RefusalReason.NO_BINDING.value})"
            )

        resolved_root = Path(root).expanduser()
        if not resolved_root.is_absolute():
            raise IdentityRefused(
                f"canonical root for {project_id!r} must be absolute, got {root!r}"
            )
        canonical = canonical_repository_root(resolved_root)

        return ProviderBinding(
            project_id=project_id,
            provider_project=str(provider_project),
            canonical_root=canonical,
            root_identity_hash=repository_identity_hash(resolved_root),
            scope_generation=scope_generation,
        )

    def require_match(
        self, binding: ProviderBinding, claimed_project_id: str | None
    ) -> None:
        """Refuse a request whose claimed identity is not the bound one."""
        if claimed_project_id is None:
            return
        if str(claimed_project_id) != binding.project_id:
            raise IdentityRefused(
                f"request claims project {claimed_project_id!r} but the resolved "
                f"binding is {binding.project_id!r} "
                f"({RefusalReason.PROJECT_MISMATCH.value})"
            )

    # ------------------------------------------------------------------
    def _lifecycle(self, project_id: str) -> tuple[ProjectLifecycle | None, int]:
        """Read lifecycle from ProjectScope, or refuse.

        An absent scope store previously returned ACTIVE -- a fail-open default
        inside a fail-closed guard, and the one branch the suite never covered
        because every test injects a store. Unverifiable lifecycle is now a
        refusal: the guard cannot prove the project is active, so it does not
        proceed as though it had.
        """
        if self._scope_store is None:
            raise IdentityRefused(
                f"no ProjectScope store is configured, so the lifecycle of "
                f"{project_id!r} cannot be established "
                f"({RefusalReason.PROJECT_UNKNOWN.value})"
            )
        connect = getattr(self._scope_store, "connect", None)
        if connect is None:
            raise IdentityRefused("scope_store does not expose connect()")
        conn: sqlite3.Connection = connect()
        try:
            row = conn.execute(
                "SELECT lifecycle_state, scope_generation FROM projects "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None, 0
        return ProjectLifecycle(row[0]), int(row[1])
