"""The guard facade: identity, profile, health, allowlist, path validation.

Order matters and is not configurable. Identity is resolved and refused *before*
the provider is contacted; health is established before semantic retrieval is
permitted; every returned path is validated against the bound canonical root
before it reaches a caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from .binding import ProjectBindingResolver
from .fallback import literal_search, read_note, resolve_within_root
from .health import PROVIDER_MEMBERSHIP_AVAILABLE, build_coverage, disposition
from .models import (
    GuardResult,
    HealthDisposition,
    PathRefused,
    ProviderBinding,
    RefusalReason,
    RuntimeRefused,
)
from .profile import ProviderProfile
from .provider import BasicMemoryProvider
from .runtime import probe_runtime, verify_runtime


@dataclass(frozen=True)
class RebuildPlan:
    """A rebuild request handed to Soma's existing run authority.

    The guard deliberately does not execute long rebuilds itself and creates no
    task, lease, cancellation or recovery plane of its own.
    """

    project_id: str
    provider_project: str
    argv: tuple[str, ...]
    env: dict[str, str]
    working_directory: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "provider_project": self.provider_project,
            "argv": list(self.argv),
            "env": dict(self.env),
            "working_directory": self.working_directory,
        }


class BasicMemoryGuard:
    """Soma-owned binding and health boundary over a replaceable provider."""

    def __init__(
        self,
        resolver: ProjectBindingResolver,
        profile: ProviderProfile,
        provider: BasicMemoryProvider,
        *,
        enforce_runtime: bool = True,
        expected_executable_sha256: str = "",
        membership_supported: bool = PROVIDER_MEMBERSHIP_AVAILABLE,
    ) -> None:
        self._resolver = resolver
        self._profile = profile
        self._provider = provider
        self._enforce_runtime = enforce_runtime
        self._expected_executable_sha256 = expected_executable_sha256
        # Whether the bound provider release enumerates its indexed set. False
        # for Basic Memory 0.22.1 by measurement, which is why semantic
        # retrieval stays blocked. A release that does enumerate flips this one
        # flag and the existing reconciliation applies unchanged.
        self._membership_supported = membership_supported
        self._runtime_mismatch: str | None = None

    # ------------------------------------------------------------------
    def runtime_mismatch(self) -> str:
        """Empty when the live stack is the frozen one; the reason otherwise.

        Measured once per guard instance: a provider cannot change underneath a
        single request, and re-probing on every call would add a subprocess to
        every read.
        """
        if not self._enforce_runtime:
            return ""
        if self._runtime_mismatch is None:
            try:
                identity = probe_runtime(self._profile, self._provider)
                verify_runtime(
                    identity,
                    expected_executable_sha256=self._expected_executable_sha256,
                )
                self._runtime_mismatch = ""
            except RuntimeRefused as exc:
                self._runtime_mismatch = str(exc)
        return self._runtime_mismatch

    # ------------------------------------------------------------------
    def bind(
        self, project_id: str | None, *, claimed_project_id: str | None = None
    ) -> ProviderBinding:
        binding = self._resolver.resolve(project_id)
        self._resolver.require_match(binding, claimed_project_id)
        return binding

    def health(self, project_id: str | None) -> HealthDisposition:
        binding = self.bind(project_id)
        return self._health_for(binding)

    def _health_for(self, binding: ProviderBinding) -> HealthDisposition:
        env = binding.process_env()
        info = self._provider.call(
            "project_info",
            "--json",
            provider_project=binding.provider_project,
            process_env=env,
        )
        status = self._provider.call(
            "status",
            "--json",
            provider_project=binding.provider_project,
            process_env=env,
        )
        coverage = build_coverage(
            binding,
            info_call=info,
            status_call=status,
            # No membership call is made. `MEMORY-INTEGRATION-FOUNDATION-1`
            # step 2 measured every accepted operation against a 34-file corpus
            # and none enumerates the indexed set: `project info` carries only a
            # ten-row recency feed, `status` reports pending deltas, and search
            # is threshold-gated. Passing `info` here would look like membership
            # on a small corpus and silently degrade on a real one, so the guard
            # records membership as unproven -- which blocks semantic retrieval.
            membership_call=(info if self._membership_supported else None),
        )
        return disposition(coverage, runtime_mismatch=self.runtime_mismatch())

    # ------------------------------------------------------------------
    def search(
        self,
        project_id: str | None,
        query: str,
        *,
        claimed_project_id: str | None = None,
        semantic: bool = True,
        page_size: int = 10,
        allow_fallback: bool = True,
    ) -> GuardResult:
        """Search within exactly one bound project.

        Semantic retrieval runs only when coverage is proven complete. Otherwise
        the guard falls back to bounded literal Markdown access and says so.
        """
        binding = self.bind(project_id, claimed_project_id=claimed_project_id)
        health = self._health_for(binding)

        if semantic and not health.semantic_permitted:
            if not allow_fallback:
                return GuardResult(
                    project_id=binding.project_id,
                    provider_project=binding.provider_project,
                    operation="search",
                    used_fallback=False,
                    health=health,
                    items=(),
                )
            items = literal_search(binding.canonical_root, query, max_results=page_size)
            return GuardResult(
                project_id=binding.project_id,
                provider_project=binding.provider_project,
                operation="search",
                used_fallback=True,
                health=health,
                items=tuple(items),
            )

        args = [query, "--page-size", str(page_size)]
        if semantic:
            args.append("--vector")
        call = self._provider.call(
            "search",
            *args,
            provider_project=binding.provider_project,
            process_env=binding.process_env(),
        )
        parsed = BasicMemoryProvider.parse_results(call)
        if parsed is None:
            # Unparsed is unproven, never "no matches".
            if not allow_fallback:
                raise PathRefused(
                    "provider response could not be parsed and fallback is disabled"
                )
            items = literal_search(binding.canonical_root, query, max_results=page_size)
            return GuardResult(
                project_id=binding.project_id,
                provider_project=binding.provider_project,
                operation="search",
                used_fallback=True,
                health=health,
                items=tuple(items),
            )

        validated = tuple(self._validate_items(binding, parsed))
        return GuardResult(
            project_id=binding.project_id,
            provider_project=binding.provider_project,
            operation="search",
            used_fallback=False,
            health=health,
            items=validated,
        )

    def read(
        self,
        project_id: str | None,
        relative_path: str,
        *,
        claimed_project_id: str | None = None,
    ) -> GuardResult:
        """Read one canonical note, always from the bound root."""
        binding = self.bind(project_id, claimed_project_id=claimed_project_id)
        health = self._health_for(binding)
        item = read_note(binding.canonical_root, relative_path)
        return GuardResult(
            project_id=binding.project_id,
            provider_project=binding.provider_project,
            operation="read",
            used_fallback=True,
            health=health,
            items=(item,),
        )

    # ------------------------------------------------------------------
    def rebuild_plan(
        self, project_id: str | None, *, full: bool = True
    ) -> RebuildPlan:
        """Describe a rebuild for Soma's run authority. Never executed here."""
        binding = self.bind(project_id)
        argv = ["reindex"]
        if full:
            argv.append("--full")
        argv += ["--project", binding.provider_project]
        env = self._profile.env(binding.process_env())
        return RebuildPlan(
            project_id=binding.project_id,
            provider_project=binding.provider_project,
            argv=tuple(argv),
            env=env,
            working_directory=binding.canonical_root,
        )

    # ------------------------------------------------------------------
    def _validate_items(
        self, binding: ProviderBinding, items: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Drop nothing silently: any path outside the bound root is a refusal."""
        out: list[dict[str, object]] = []
        for item in items:
            raw = item.get("file_path") or item.get("path") or ""
            if not raw:
                permalink = str(item.get("permalink") or "")
                if permalink and not permalink.startswith(
                    binding.provider_project + "/"
                ):
                    raise PathRefused(
                        f"result permalink {permalink!r} is outside provider project "
                        f"{binding.provider_project!r} "
                        f"({RefusalReason.PATH_OUTSIDE_ROOT.value})"
                    )
                out.append(item)
                continue
            # Raises PathRefused when the path escapes the bound canonical root.
            resolve_within_root(binding.canonical_root, str(raw))
            permalink = str(item.get("permalink") or "")
            if permalink and not permalink.startswith(binding.provider_project + "/"):
                raise PathRefused(
                    f"result permalink {permalink!r} belongs to another provider "
                    f"project ({RefusalReason.PATH_OUTSIDE_ROOT.value})"
                )
            out.append(item)
        return out
