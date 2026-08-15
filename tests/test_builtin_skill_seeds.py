from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import soma.skills.builtin as builtin_module
from soma.skills import (
    BUILTIN_SKILL_SEED_NAMES,
    BUILTIN_SKILL_SEED_SOURCE_PREFIX,
    SkillLibrary,
    SkillNotFound,
    builtin_skill_seed_path,
    import_builtin_skill_seed,
    parse_skill_metadata,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _library(tmp_path: Path) -> SkillLibrary:
    return SkillLibrary(tmp_path / "owner-skill-library")


def _owner_revision(seed_root: Path) -> dict[str, bytes]:
    return {
        "SKILL.md": seed_root.joinpath("SKILL.md").read_bytes()
        + b"\n\n## Owner revision\n\nOwner-specific workflow guidance.\n"
    }


def _newer_seed(tmp_path: Path, seed_root: Path) -> Path:
    package_root = tmp_path / "newer-repo-seed" / "soma-engineering"
    package_root.mkdir(parents=True)
    package_root.joinpath("SKILL.md").write_bytes(
        seed_root.joinpath("SKILL.md").read_bytes()
        + b"\n\n## Reviewed seed revision\n\nLater repo-owned guidance.\n"
    )
    return package_root


def test_soma_engineering_builtin_seed_is_agent_skills_valid() -> None:
    assert BUILTIN_SKILL_SEED_NAMES == ("soma-engineering",)
    package_root = builtin_skill_seed_path("soma-engineering")
    skill_md = package_root / "SKILL.md"

    assert package_root.name == "soma-engineering"
    assert skill_md.is_file()
    metadata = parse_skill_metadata(skill_md.read_bytes())
    assert metadata["name"] == package_root.name
    assert metadata["description"]
    assert package_root.as_posix().endswith(
        "soma/skills/seed_packages/soma-engineering"
    )


def test_builtin_seed_lookup_is_allowlisted_not_path_driven() -> None:
    for unknown in ("", "../soma-engineering", "owner-skill", "SOMA-ENGINEERING"):
        with pytest.raises(SkillNotFound):
            builtin_skill_seed_path(unknown)


def test_builtin_seed_is_declared_as_distribution_package_data() -> None:
    config = tomllib.loads(REPOSITORY_ROOT.joinpath("pyproject.toml").read_text("utf-8"))
    package_data = config["tool"]["setuptools"]["package-data"]
    assert "skills/seed_packages/*/SKILL.md" in package_data["soma"]


def test_builtin_seed_imports_into_fresh_library_with_explicit_provenance(
    tmp_path: Path,
) -> None:
    library = _library(tmp_path)
    result = import_builtin_skill_seed(
        library,
        "soma-engineering",
        controller_request_id="s4-seed-first-import",
        make_current=True,
    )

    assert result["name"] == "soma-engineering"
    assert result["created"] is True
    assert result["current"] is True
    assert result["state_version"] == 1
    revision = library.get_revision(str(result["skill_ref"]))
    assert revision["package_root"].endswith(
        f"/{result['package_hash']}/soma-engineering"
    ) or revision["package_root"].endswith(
        f"\\{result['package_hash']}\\soma-engineering"
    )
    assert {
        (source["source_kind"], source["source_ref"])
        for source in revision["sources"]
    } == {
        ("repo_builtin_seed", f"{BUILTIN_SKILL_SEED_SOURCE_PREFIX}soma-engineering")
    }


def test_builtin_import_defaults_to_history_only_not_current_state(tmp_path: Path) -> None:
    library = _library(tmp_path)
    result = import_builtin_skill_seed(
        library,
        "soma-engineering",
        controller_request_id="s4-seed-default-import",
    )

    assert result["created"] is True
    assert result["current"] is False
    state = library.get_state("soma-engineering")
    assert state["current_skill_ref"] == ""
    assert state["state_version"] == 0


def test_owner_revision_is_normal_immutable_history_and_newer_seed_does_not_replace_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library(tmp_path)
    seed_root = builtin_skill_seed_path("soma-engineering")
    original_seed = import_builtin_skill_seed(
        library,
        "soma-engineering",
        controller_request_id="s4-seed-current",
        make_current=True,
    )
    owner = library.import_revision(
        _owner_revision(seed_root),
        controller_request_id="s4-owner-revision",
        source_kind="owner_local_import",
        source_ref="owner://soma-engineering",
        make_current=True,
        expected_state_version=1,
    )

    assert owner["skill_ref"] != original_seed["skill_ref"]
    assert owner["state_version"] == 2
    owner_revision = library.get_revision(str(owner["skill_ref"]))
    assert owner_revision["parent_skill_ref"] == original_seed["skill_ref"]
    assert any(
        source["source_kind"] == "owner_local_import"
        for source in owner_revision["sources"]
    )

    newer_seed_root = _newer_seed(tmp_path, seed_root)
    monkeypatch.setattr(
        builtin_module,
        "builtin_skill_seed_path",
        lambda name: newer_seed_root if name == "soma-engineering" else seed_root,
    )
    newer_seed = builtin_module.import_builtin_skill_seed(
        library,
        "soma-engineering",
        controller_request_id="s4-newer-seed-history",
    )

    assert newer_seed["created"] is True
    assert newer_seed["current"] is False
    assert newer_seed["skill_ref"] not in {
        original_seed["skill_ref"],
        owner["skill_ref"],
    }
    state = library.get_state("soma-engineering")
    assert state["current_skill_ref"] == owner["skill_ref"]
    assert state["state_version"] == 2
    history = library.history("soma-engineering")
    assert {entry["skill_ref"] for entry in history} == {
        original_seed["skill_ref"],
        owner["skill_ref"],
        newer_seed["skill_ref"],
    }
