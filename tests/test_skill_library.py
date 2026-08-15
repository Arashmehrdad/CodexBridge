from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from soma.config import SkillLibraryConfig
from soma.skills import (
    PackageIntegrityMismatch,
    SkillLibrary,
    SkillPackageInvalid,
    SkillRequestConflict,
    StaleSkillState,
    build_manifest,
)


def _skill_md(name: str = "research-helper", description: str = "Reusable research workflow") -> bytes:
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"# {name}\n\nFollow the reusable workflow.\n"
    ).encode("utf-8")


def _package(name: str = "research-helper", *, extra: bytes = b"v1") -> dict[str, bytes]:
    return {
        "SKILL.md": _skill_md(name),
        "scripts/run.py": b"print('mechanical resource only')\n",
        "references/guide.md": b"reference\n",
        "assets/data.bin": extra,
        "custom/other.txt": b"other package file\n",
    }


def _library(tmp_path: Path, **kwargs) -> SkillLibrary:
    return SkillLibrary(tmp_path / "Skill Library", **kwargs)


def test_skill_library_config_marks_runs_location_as_development_fallback(tmp_path: Path) -> None:
    config = SkillLibraryConfig()
    assert config.skill_library_kind == "runs_internal_development"
    assert config.resolve_library_root(tmp_path / "runs") == (tmp_path / "runs" / "skills").resolve()


def test_skill_library_config_uses_absolute_external_private_root(tmp_path: Path) -> None:
    external = tmp_path / "Owner Skills"
    config = SkillLibraryConfig(
        skill_library_root=str(external),
        skill_library_kind="external_private_library",
    )
    assert config.resolve_library_root(tmp_path / "runs") == external.resolve()


def test_skill_library_config_refuses_relative_or_missing_external_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute path"):
        SkillLibraryConfig(skill_library_root="relative/skills").resolve_library_root(tmp_path)
    with pytest.raises(ValueError, match="requires an absolute"):
        SkillLibraryConfig(skill_library_kind="external_private_library").resolve_library_root(tmp_path)


def test_minimal_skill_import_materializes_standard_parent_directory(tmp_path: Path) -> None:
    library = _library(tmp_path)
    result = library.import_revision(
        {"SKILL.md": _skill_md()},
        controller_request_id="s1-minimal",
        make_current=True,
    )

    package_root = Path(str(result["package_root"]))
    assert package_root == library.root / "revisions" / result["package_hash"] / "research-helper"
    assert package_root.name == "research-helper"
    assert (package_root / "SKILL.md").read_bytes() == _skill_md()
    assert library.get_state("research-helper")["current_skill_ref"] == result["skill_ref"]
    assert library.db_path.parent == library.root


def test_whole_package_manifest_includes_every_regular_file_and_any_change_revises_hash(tmp_path: Path) -> None:
    files = _package()
    manifest, first_hash = build_manifest(files)
    assert [entry["path"] for entry in manifest] == sorted(files)
    assert {entry["path"] for entry in manifest} == {
        "SKILL.md",
        "scripts/run.py",
        "references/guide.md",
        "assets/data.bin",
        "custom/other.txt",
    }

    for changed_path in files:
        changed = dict(files)
        changed[changed_path] = changed[changed_path] + b"changed"
        _manifest, changed_hash = build_manifest(changed)
        assert changed_hash != first_hash, changed_path


def test_manifest_is_stable_and_does_not_depend_on_mapping_order() -> None:
    files = _package()
    reversed_files = dict(reversed(list(files.items())))
    assert build_manifest(files) == build_manifest(reversed_files)


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.txt",
        "nested/../escape.txt",
        "/absolute.txt",
        "nested\\windows.txt",
        "nested//double.txt",
        "C:/drive.txt",
    ],
)
def test_direct_package_ingestion_rejects_path_traversal_and_nonportable_paths(
    tmp_path: Path, bad_path: str
) -> None:
    library = _library(tmp_path)
    files = {"SKILL.md": _skill_md(), bad_path: b"x"}
    with pytest.raises(SkillPackageInvalid):
        library.import_revision(files, controller_request_id=f"bad-{bad_path}")


def test_direct_package_ingestion_rejects_case_colliding_paths(tmp_path: Path) -> None:
    library = _library(tmp_path)
    with pytest.raises(SkillPackageInvalid, match="case-colliding"):
        library.import_revision(
            {
                "SKILL.md": _skill_md(),
                "references/A.md": b"one",
                "references/a.md": b"two",
            },
            controller_request_id="case-collision",
        )


def test_package_requires_standard_name_and_description_metadata(tmp_path: Path) -> None:
    library = _library(tmp_path)
    invalid = (
        b"# no frontmatter\n",
        b"---\ndescription: x\n---\n",
        b"---\nname: Research_Helper\ndescription: x\n---\n",
        b"---\nname: research-helper\ndescription: ''\n---\n",
    )
    for index, skill_md in enumerate(invalid):
        with pytest.raises(SkillPackageInvalid):
            library.import_revision(
                {"SKILL.md": skill_md},
                controller_request_id=f"metadata-{index}",
            )


def test_directory_import_requires_frontmatter_name_to_match_immediate_parent(tmp_path: Path) -> None:
    library = _library(tmp_path)
    package_root = tmp_path / "wrong-directory"
    package_root.mkdir()
    (package_root / "SKILL.md").write_bytes(_skill_md("research-helper"))
    with pytest.raises(SkillPackageInvalid, match="immediate package-root directory"):
        library.import_directory(package_root, controller_request_id="parent-mismatch")


def test_directory_import_rejects_any_symlink(tmp_path: Path, monkeypatch) -> None:
    library = _library(tmp_path)
    package_root = tmp_path / "research-helper"
    package_root.mkdir()
    (package_root / "SKILL.md").write_bytes(_skill_md())
    link = package_root / "link.txt"
    target = package_root / "target.txt"
    target.write_text("target", encoding="utf-8")
    try:
        os.symlink(target, link)
    except OSError:
        link.write_text("synthetic link", encoding="utf-8")
        original = Path.is_symlink

        def synthetic_is_symlink(path: Path) -> bool:
            if path == link:
                return True
            return original(path)

        monkeypatch.setattr(Path, "is_symlink", synthetic_is_symlink)
    with pytest.raises(SkillPackageInvalid, match="symlinks"):
        library.import_directory(package_root, controller_request_id="symlink")


def test_package_bounds_cover_file_count_single_file_and_total_bytes(tmp_path: Path) -> None:
    with pytest.raises(SkillPackageInvalid, match="max_files"):
        _library(tmp_path / "a", max_files=1).import_revision(
            {"SKILL.md": _skill_md(), "a.txt": b"a"},
            controller_request_id="too-many",
        )
    with pytest.raises(SkillPackageInvalid, match="max_file_bytes"):
        _library(tmp_path / "b", max_file_bytes=10).import_revision(
            {"SKILL.md": _skill_md()},
            controller_request_id="file-too-large",
        )
    skill_md = _skill_md()
    with pytest.raises(SkillPackageInvalid, match="max_total_bytes"):
        _library(tmp_path / "c", max_total_bytes=len(skill_md) + 2).import_revision(
            {"SKILL.md": skill_md, "a.txt": b"123"},
            controller_request_id="total-too-large",
        )


def test_duplicate_same_bytes_converges_and_records_multiple_provenance_sources(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(
        _package(),
        controller_request_id="source-one",
        source_kind="owner_local_import",
        source_ref="owner://draft",
        make_current=True,
    )
    second = library.import_revision(
        _package(),
        controller_request_id="source-two",
        source_kind="imported_source",
        source_ref="archive://copy",
    )

    assert second["skill_ref"] == first["skill_ref"]
    assert second["created"] is False
    revision = library.get_revision(str(first["skill_ref"]))
    assert {(source["source_kind"], source["source_ref"]) for source in revision["sources"]} == {
        ("owner_local_import", "owner://draft"),
        ("imported_source", "archive://copy"),
    }
    assert library.get_state("research-helper")["current_skill_ref"] == first["skill_ref"]


def test_same_name_conflicting_source_revision_does_not_silently_replace_current(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(
        _package(extra=b"v1"),
        controller_request_id="current-v1",
        source_kind="owner_local_import",
        source_ref="owner://one",
        make_current=True,
    )
    second = library.import_revision(
        _package(extra=b"v2"),
        controller_request_id="other-source-v2",
        source_kind="imported_source",
        source_ref="repo://untrusted-copy",
    )

    assert first["skill_ref"] != second["skill_ref"]
    state = library.get_state("research-helper")
    assert state["current_skill_ref"] == first["skill_ref"]
    assert state["state_version"] == 1
    assert len(library.history("research-helper")) == 2


def test_import_request_replay_is_stable_and_conflicting_reuse_is_rejected(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(_package(), controller_request_id="stable-import")
    replay = library.import_revision(_package(), controller_request_id="stable-import")
    assert replay["skill_ref"] == first["skill_ref"]
    assert replay["replayed"] is True

    with pytest.raises(SkillRequestConflict):
        library.import_revision(
            _package(extra=b"different"),
            controller_request_id="stable-import",
        )


def test_out_of_band_revision_edit_is_detected_not_rehashed_in_place(tmp_path: Path) -> None:
    library = _library(tmp_path)
    imported = library.import_revision(_package(), controller_request_id="drift")
    package_root = Path(str(imported["package_root"]))
    (package_root / "references" / "guide.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(PackageIntegrityMismatch, match="package_integrity_mismatch"):
        library.get_revision(str(imported["skill_ref"]))


def test_historical_revision_remains_exact_after_current_pointer_moves(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(
        _package(extra=b"v1"),
        controller_request_id="hist-v1",
        make_current=True,
    )
    second = library.import_revision(
        _package(extra=b"v2"),
        controller_request_id="hist-v2",
    )
    moved = library.set_current(
        str(second["skill_ref"]),
        expected_state_version=1,
        controller_request_id="move-current",
    )

    assert moved["state_version"] == 2
    assert library.get_state("research-helper")["current_skill_ref"] == second["skill_ref"]
    old = library.get_revision(str(first["skill_ref"]))
    assert (Path(str(old["package_root"])) / "assets" / "data.bin").read_bytes() == b"v1"
    new = library.get_revision(str(second["skill_ref"]))
    assert (Path(str(new["package_root"])) / "assets" / "data.bin").read_bytes() == b"v2"


def test_set_current_uses_compare_and_set_under_concurrency(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(
        _package(extra=b"v1"), controller_request_id="cas-v1", make_current=True
    )
    second = library.import_revision(_package(extra=b"v2"), controller_request_id="cas-v2")
    third = library.import_revision(_package(extra=b"v3"), controller_request_id="cas-v3")
    assert first["state_version"] == 1

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def move(skill_ref: str, request_id: str) -> None:
        barrier.wait()
        try:
            library.set_current(
                skill_ref,
                expected_state_version=1,
                controller_request_id=request_id,
            )
            outcome = "won"
        except StaleSkillState:
            outcome = "stale"
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=move, args=(str(second["skill_ref"]), "cas-move-2")),
        threading.Thread(target=move, args=(str(third["skill_ref"]), "cas-move-3")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ["stale", "won"]
    assert library.get_state("research-helper")["state_version"] == 2


def test_current_and_enabled_mutation_replay_is_stable(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(
        _package(extra=b"v1"), controller_request_id="state-v1", make_current=True
    )
    second = library.import_revision(_package(extra=b"v2"), controller_request_id="state-v2")
    moved = library.set_current(
        str(second["skill_ref"]),
        expected_state_version=1,
        controller_request_id="state-move",
    )
    replay = library.set_current(
        str(second["skill_ref"]),
        expected_state_version=1,
        controller_request_id="state-move",
    )
    assert replay["state_version"] == moved["state_version"] == 2
    assert replay["replayed"] is True

    disabled = library.set_enabled(
        "research-helper",
        False,
        expected_state_version=2,
        controller_request_id="state-disable",
    )
    disabled_replay = library.set_enabled(
        "research-helper",
        False,
        expected_state_version=2,
        controller_request_id="state-disable",
    )
    assert disabled["state_version"] == disabled_replay["state_version"] == 3
    assert disabled_replay["replayed"] is True
    assert library.get_state("research-helper")["enabled"] is False
    assert first["skill_ref"] != second["skill_ref"]


def test_concurrent_duplicate_imports_converge_to_one_revision(tmp_path: Path) -> None:
    library = _library(tmp_path)
    barrier = threading.Barrier(4)
    refs: list[str] = []
    lock = threading.Lock()

    def do_import(index: int) -> None:
        barrier.wait()
        result = library.import_revision(
            _package(), controller_request_id=f"concurrent-import-{index}"
        )
        with lock:
            refs.append(str(result["skill_ref"]))

    threads = [threading.Thread(target=do_import, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(refs) == 4
    assert len(set(refs)) == 1
    assert len(library.history("research-helper")) == 1


def test_tampered_revision_cannot_be_promoted_to_current(tmp_path: Path) -> None:
    library = _library(tmp_path)
    first = library.import_revision(
        _package(extra=b"v1"), controller_request_id="promote-v1", make_current=True
    )
    second = library.import_revision(
        _package(extra=b"v2"), controller_request_id="promote-v2"
    )
    package_root = Path(str(second["package_root"]))
    (package_root / "assets" / "data.bin").write_bytes(b"tampered")

    with pytest.raises(PackageIntegrityMismatch, match="package_integrity_mismatch"):
        library.set_current(
            str(second["skill_ref"]),
            expected_state_version=1,
            controller_request_id="promote-tampered",
        )
    assert library.get_state("research-helper")["current_skill_ref"] == first["skill_ref"]


def test_import_never_executes_bundled_script(tmp_path: Path) -> None:
    library = _library(tmp_path)
    marker = tmp_path / "executed.txt"
    script = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n".encode()
    files = _package()
    files["scripts/run.py"] = script
    library.import_revision(files, controller_request_id="no-exec")
    assert not marker.exists()


def test_orphaned_immutable_materialization_is_safe_to_retry(tmp_path: Path, monkeypatch) -> None:
    library = _library(tmp_path)
    original = library._record_request

    def fail_before_commit(*args, **kwargs):
        raise RuntimeError("simulated registry failure")

    monkeypatch.setattr(library, "_record_request", fail_before_commit)
    with pytest.raises(RuntimeError, match="simulated registry failure"):
        library.import_revision(_package(), controller_request_id="orphan-safe")

    revision_dirs = list((library.root / "revisions").glob("*/research-helper"))
    assert len(revision_dirs) == 1
    assert library.history("research-helper") == []

    monkeypatch.setattr(library, "_record_request", original)
    recovered = library.import_revision(_package(), controller_request_id="orphan-safe")
    assert recovered["created"] is True
    assert len(library.history("research-helper")) == 1
    assert library.get_revision(str(recovered["skill_ref"]))["package_hash"] == recovered["package_hash"]
