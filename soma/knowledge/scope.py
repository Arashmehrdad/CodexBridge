"""Discriminated memory scope resolution.

SOMA-SHARED-MEMORY-ARCH-1: project memory resolves through ProjectScope;
personal memory is a *sibling* authority resolved through owner identity, not a
synthetic repository project. Representing a person as a repository would mean
either fabricating a repository root or bypassing
`ProjectScopeStore.resolve_repository` -- and bypassing it is exactly the hole
the guard exists to close.

Only the project kind is active in `MEMORY-INTEGRATION-FOUNDATION-1`. The
personal kind is modelled here so the discriminator exists from the start, and
refuses until the owner authorises activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class ScopeRefused(ValueError):
    """The request did not establish an authoritative memory scope."""


ScopeKind = Literal["project", "personal"]


@dataclass(frozen=True)
class MemoryScope:
    """An exactly-resolved scope. There is no default and no inference path."""

    kind: ScopeKind
    project_id: str = ""
    repo_name: str = ""
    owner_id: str = ""

    @property
    def scope_key(self) -> str:
        """Stable identity used for vault roots and provider binding."""
        if self.kind == "project":
            return self.project_id
        return f"personal-{self.owner_id}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        if self.kind == "project":
            payload["project_id"] = self.project_id
            payload["repo_name"] = self.repo_name
        else:
            payload["owner_id"] = self.owner_id
        return payload


def resolve_project_scope(
    scope_store: Any,
    *,
    project_id: str,
    repo_name: str,
    repository_root: str,
) -> MemoryScope:
    """Resolve a project scope through ProjectScope, or refuse.

    Delegates to the live authority rather than re-implementing it: an omitted,
    unknown, inactive or mismatched project raises out of `resolve_repository`
    before anything reads or writes memory.
    """
    if not project_id or not str(project_id).strip():
        raise ScopeRefused("project_id is required; memory scope is never inferred")
    if not repo_name or not str(repo_name).strip():
        raise ScopeRefused("repo_name is required to bind a project memory scope")
    binding = scope_store.resolve_repository(
        project_id=project_id,
        repo_name=repo_name,
        repository_root=repository_root,
    )
    return MemoryScope(
        kind="project",
        project_id=binding.project_id,
        repo_name=binding.repo_name,
    )


def resolve_personal_scope(owner_id: str) -> MemoryScope:
    """Refuse: personal memory is excluded from this lane by the decision."""
    raise ScopeRefused(
        "personal memory scope is not activated; owner identity, storage root, "
        "sharing policy and authorization boundary are explicit exclusions of "
        "MEMORY-INTEGRATION-FOUNDATION-1"
    )


def resolve_scope(scope_store: Any, request: dict[str, Any], *, repository_root: str = "") -> MemoryScope:
    """Resolve a controller-supplied scope object exactly."""
    if not isinstance(request, dict):
        raise ScopeRefused("scope must be an object naming its kind")
    kind = request.get("kind")
    if kind == "project":
        return resolve_project_scope(
            scope_store,
            project_id=str(request.get("project_id") or ""),
            repo_name=str(request.get("repo_name") or ""),
            repository_root=repository_root,
        )
    if kind == "personal":
        return resolve_personal_scope(str(request.get("owner_id") or ""))
    raise ScopeRefused(
        f"scope kind {kind!r} is not recognised; expected 'project' or 'personal'"
    )
