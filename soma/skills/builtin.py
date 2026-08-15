"""Reviewed repo-owned Agent Skill seed packages.

Built-in seeds are inert source packages.  They are never synchronized into an
owner Skill library automatically; callers must explicitly import a named seed
through the normal immutable SkillLibrary lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from .library import SkillLibrary, SkillNotFound


BUILTIN_SKILL_SEED_NAMES: Final[tuple[str, ...]] = ("soma-engineering",)
BUILTIN_SKILL_SEED_SOURCE_PREFIX: Final[str] = "soma-builtin://"


def builtin_skill_seed_path(name: str) -> Path:
    """Return the standards-valid package root for one reviewed built-in seed."""
    seed_name = str(name or "").strip()
    if seed_name not in BUILTIN_SKILL_SEED_NAMES:
        raise SkillNotFound(seed_name)
    package_root = Path(__file__).resolve().parent / "seed_packages" / seed_name
    if package_root.name != seed_name or not (package_root / "SKILL.md").is_file():
        raise SkillNotFound(seed_name)
    return package_root


def import_builtin_skill_seed(
    library: SkillLibrary,
    name: str,
    *,
    controller_request_id: str,
    make_current: bool = False,
    expected_state_version: int | None = None,
) -> dict[str, object]:
    """Explicitly import one reviewed seed through normal library semantics.

    ``make_current`` deliberately defaults to false.  Repo-owned source never
    becomes owner-library current state merely because Soma ships a newer seed.
    """
    seed_name = str(name or "").strip()
    package_root = builtin_skill_seed_path(seed_name)
    return library.import_directory(
        package_root,
        controller_request_id=controller_request_id,
        source_kind="repo_builtin_seed",
        source_ref=f"{BUILTIN_SKILL_SEED_SOURCE_PREFIX}{seed_name}",
        make_current=make_current,
        expected_state_version=expected_state_version,
    )
