from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from soma.skills import SkillLibrary, SkillNotFound, SkillQueryService


def _skill_md(name: str, description: str, body: str = "# Instructions\nDo the thing.\n") -> bytes:
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    ).encode("utf-8")


def _library(tmp_path: Path) -> tuple[SkillLibrary, SkillQueryService]:
    library = SkillLibrary(tmp_path / "skills")
    return library, SkillQueryService(library)


def _import(
    library: SkillLibrary,
    *,
    name: str,
    description: str,
    request_id: str,
    body: str = "# Instructions\nDo the thing.\n",
    extra: dict[str, bytes] | None = None,
    make_current: bool = True,
    expected_state_version: int | None = None,
    source_kind: str = "owner_local_import",
    source_ref: str = "",
) -> dict:
    files = {"SKILL.md": _skill_md(name, description, body)}
    files.update(extra or {})
    return library.import_revision(
        files,
        controller_request_id=request_id,
        source_kind=source_kind,
        source_ref=source_ref,
        make_current=make_current,
        expected_state_version=expected_state_version,
    )


def test_list_returns_current_enabled_metadata_only(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    first = _import(
        library,
        name="alpha-skill",
        description="Alpha workflow",
        request_id="alpha-v1",
    )
    _import(
        library,
        name="alpha-skill",
        description="Alpha workflow revised",
        request_id="alpha-v2",
        body="# Instructions\nRevised.\n",
        expected_state_version=first["state_version"],
    )
    beta = _import(
        library,
        name="beta-skill",
        description="Beta workflow",
        request_id="beta-v1",
    )
    library.set_enabled(
        "beta-skill",
        False,
        expected_state_version=beta["state_version"],
        controller_request_id="disable-beta",
    )

    result = service.list_skills()
    assert result["scope"] == "current_enabled_only"
    assert [item["name"] for item in result["items"]] == ["alpha-skill"]
    item = result["items"][0]
    assert item["current"] is True
    assert item["historical"] is False
    assert item["enabled"] is True
    assert "skill_md" not in item
    assert "package_root" not in item


def test_list_and_search_use_bound_checksum_cursors(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    for index, name in enumerate(("alpha-skill", "beta-skill", "gamma-skill"), 1):
        _import(
            library,
            name=name,
            description=f"Shared workflow {index}",
            request_id=f"import-{index}",
        )

    first = service.list_skills(limit=1)
    assert first["has_more"] is True
    second = service.list_skills(limit=1, cursor=first["next_cursor"])
    third = service.list_skills(limit=1, cursor=second["next_cursor"])
    assert [first["items"][0]["name"], second["items"][0]["name"], third["items"][0]["name"]] == [
        "alpha-skill",
        "beta-skill",
        "gamma-skill",
    ]

    search_first = service.search("workflow", limit=1)
    search_second = service.search(
        "workflow", limit=1, cursor=search_first["next_cursor"]
    )
    assert search_first["items"][0]["name"] != search_second["items"][0]["name"]
    with pytest.raises(ValueError, match="query mismatch"):
        service.search("alpha", limit=1, cursor=search_first["next_cursor"])


def test_search_ranking_is_deterministic_and_metadata_only(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    _import(
        library,
        name="research",
        description="General research workflow",
        request_id="research",
    )
    _import(
        library,
        name="research-audit",
        description="Audit workflow",
        request_id="research-audit",
    )
    _import(
        library,
        name="deep-research",
        description="Deep evidence workflow",
        request_id="deep-research",
    )
    _import(
        library,
        name="evidence-review",
        description="Research synthesis workflow",
        request_id="evidence-review",
    )

    result = service.search("research")
    assert [item["name"] for item in result["items"]] == [
        "research",
        "research-audit",
        "deep-research",
        "evidence-review",
    ]
    assert result["ranking"] == "deterministic_name_description_v1"
    assert all("skill_md" not in item for item in result["items"])


def test_get_name_resolves_only_current_enabled_revision(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    revision = _import(
        library,
        name="alpha-skill",
        description="Alpha workflow",
        request_id="alpha-v1",
        extra={"references/guide.md": b"guide"},
    )
    result = service.get(name="alpha-skill")
    assert result["skill_ref"] == revision["skill_ref"]
    assert result["skill_md_complete"] is True
    assert "Alpha workflow" in result["skill_md"]
    assert result["manifest_count"] == 2
    assert result["locator_is_execution_authority"] is False

    library.set_enabled(
        "alpha-skill",
        False,
        expected_state_version=revision["state_version"],
        controller_request_id="disable-alpha",
    )
    with pytest.raises(SkillNotFound):
        service.get(name="alpha-skill")
    exact = service.get(skill_ref=revision["skill_ref"])
    assert exact["skill_ref"] == revision["skill_ref"]
    assert exact["enabled"] is False


def test_get_manifest_and_provenance_projection_are_byte_bounded(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    extra = {
        f"references/item-{index:03d}-{'x' * 50}.txt": f"item-{index}".encode()
        for index in range(120)
    }
    files = {
        "SKILL.md": _skill_md("bounded-skill", "Bounded projection workflow"),
        **extra,
    }
    revision = library.import_revision(
        files,
        controller_request_id="bounded-v1",
        source_kind="owner_local_import",
        source_ref="owner",
        make_current=True,
    )
    library.import_revision(
        files,
        controller_request_id="bounded-source-2",
        source_kind="imported_source",
        source_ref="s" * 32_768,
        make_current=False,
    )
    library.import_revision(
        files,
        controller_request_id="bounded-source-3",
        source_kind="native_exported_copy",
        source_ref="native-copy",
        make_current=False,
    )

    result = service.get(skill_ref=revision["skill_ref"])
    assert result["manifest_count"] == 121
    assert result["manifest_truncated"] is True
    assert result["manifest_projection_bytes"] <= result["manifest_projection_max_bytes"]
    assert result["manifest_projection_max_bytes"] == 16 * 1024
    assert set(result["provenance"]) == {"source_count", "source_kinds"}
    assert result["provenance"]["source_count"] == 3
    assert result["provenance"]["source_kinds"] == [
        "imported_source",
        "native_exported_copy",
        "owner_local_import",
    ]
    assert "source_ref" not in json.dumps(result["provenance"], sort_keys=True)
    assert len(json.dumps(result, ensure_ascii=True).encode("utf-8")) < 384 * 1024


def test_name_lookup_does_not_guess_from_multiple_historical_revisions(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    first = _import(
        library,
        name="ambiguous-skill",
        description="First source",
        request_id="ambiguous-1",
        make_current=False,
        source_kind="owner_local_import",
        source_ref="owner-a",
    )
    second = _import(
        library,
        name="ambiguous-skill",
        description="Second source",
        request_id="ambiguous-2",
        body="# Instructions\nDifferent.\n",
        make_current=False,
        source_kind="imported_source",
        source_ref="source-b",
    )
    assert first["skill_ref"] != second["skill_ref"]
    with pytest.raises(SkillNotFound):
        service.get(name="ambiguous-skill")
    assert service.get(skill_ref=first["skill_ref"])["description"] == "First source"
    assert service.get(skill_ref=second["skill_ref"])["description"] == "Second source"


def test_history_pages_exact_immutable_revisions(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    state_version = None
    refs: list[str] = []
    for index in range(3):
        result = _import(
            library,
            name="history-skill",
            description=f"Revision {index}",
            request_id=f"history-{index}",
            body=f"# Instructions\nRevision {index}.\n",
            expected_state_version=state_version,
        )
        state_version = result["state_version"]
        refs.append(result["skill_ref"])

    first = service.history("history-skill", limit=2)
    second = service.history(
        "history-skill", limit=2, cursor=first["next_cursor"]
    )
    observed = [item["skill_ref"] for item in first["items"] + second["items"]]
    assert observed == refs
    assert sum(1 for item in first["items"] + second["items"] if item["current"]) == 1


def test_resource_returns_text_without_execution_and_rejects_escape(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    sentinel = tmp_path / "must-not-exist.txt"
    script = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n".encode()
    revision = _import(
        library,
        name="script-skill",
        description="Script resource workflow",
        request_id="script-v1",
        extra={"scripts/do_work.py": script},
    )

    result = service.resource(revision["skill_ref"], "scripts/do_work.py")
    assert result["encoding"] == "utf-8"
    assert "write_text" in result["content_text"]
    assert result["executes_resource"] is False
    assert result["locator_is_execution_authority"] is False
    assert not sentinel.exists()
    with pytest.raises(ValueError):
        service.resource(revision["skill_ref"], "../outside.txt")


def test_large_binary_resource_uses_cursor_chunks(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    payload = bytes(range(256)) * 900
    revision = _import(
        library,
        name="binary-skill",
        description="Binary resource workflow",
        request_id="binary-v1",
        extra={"assets/blob.bin": payload},
    )

    chunks = []
    cursor = ""
    while True:
        page = service.resource(
            revision["skill_ref"],
            "assets/blob.bin",
            max_bytes=32_000,
            cursor=cursor,
        )
        if page["encoding"] == "base64":
            chunks.append(base64.b64decode(page["content_base64"]))
        else:
            chunks.append(page["content_text"].encode("utf-8"))
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    assert b"".join(chunks) == payload
    assert page["complete"] is True


def test_resource_cursor_is_bound_to_revision_and_path(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    revision = _import(
        library,
        name="cursor-skill",
        description="Cursor workflow",
        request_id="cursor-v1",
        extra={"references/a.txt": b"a" * 100, "references/b.txt": b"b" * 100},
    )
    first = service.resource(
        revision["skill_ref"], "references/a.txt", max_bytes=10
    )
    with pytest.raises(ValueError, match="path mismatch"):
        service.resource(
            revision["skill_ref"],
            "references/b.txt",
            max_bytes=10,
            cursor=first["next_cursor"],
        )


def test_exact_ref_can_be_refetched_after_prior_context_is_gone(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    revision = _import(
        library,
        name="refetch-skill",
        description="Refetch workflow",
        request_id="refetch-v1",
    )
    first = service.get(skill_ref=revision["skill_ref"])
    fresh_service = SkillQueryService(SkillLibrary(library.root))
    second = fresh_service.get(skill_ref=revision["skill_ref"])
    assert second["skill_ref"] == first["skill_ref"]
    assert second["skill_md"] == first["skill_md"]
    assert second["package_hash"] == first["package_hash"]


def test_query_refuses_out_of_band_revision_drift(tmp_path: Path) -> None:
    library, service = _library(tmp_path)
    revision = _import(
        library,
        name="drift-skill",
        description="Drift workflow",
        request_id="drift-v1",
    )
    package_root = Path(revision["package_root"])
    (package_root / "SKILL.md").write_text(
        "---\nname: drift-skill\ndescription: changed\n---\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="package_integrity_mismatch"):
        service.get(skill_ref=revision["skill_ref"])
    with pytest.raises(ValueError, match="package_integrity_mismatch"):
        service.list_skills()
