from __future__ import annotations

from dataclasses import replace

import pytest

from soma.cf1_fixture_matrix import (
    CF1_FIXTURE_MATRIX,
    CF1_FIXTURE_MATRIX_VERSION,
    FixtureClass,
    fixture_matrix_by_name,
    validate_fixture_matrix,
)

_REQUIRED_FIXTURES = {
    "successful_run", "failed_run", "active_run", "cancelled_run",
    "partial_completion", "ambiguous_side_effect", "hermes_call",
    "executable_profile", "repository_read", "repository_search",
    "large_diff", "parallel_group", "ssh_operation", "workflow",
    "supervisor", "trading_lab", "docker", "cloudflare", "knowledge",
}


def test_cf1_fixture_matrix_covers_authoritative_roadmap_cases() -> None:
    validate_fixture_matrix()
    fixtures = fixture_matrix_by_name()
    assert set(fixtures) == _REQUIRED_FIXTURES
    assert {fixture.fixture_class for fixture in CF1_FIXTURE_MATRIX} == set(FixtureClass)
    assert fixtures["partial_completion"].outcome == "partial"
    assert fixtures["ambiguous_side_effect"].lifecycle_status == "uncertain"
    assert fixtures["supervisor"].outcome == "needs_input"


def test_cf1_fixture_identities_are_stable_and_versioned() -> None:
    first = fixture_matrix_by_name()
    second = fixture_matrix_by_name()
    assert CF1_FIXTURE_MATRIX_VERSION == "cf1.0.fixture-matrix.v1"
    assert {name: fixture.identity_sha256 for name, fixture in first.items()} == {
        name: fixture.identity_sha256 for name, fixture in second.items()
    }
    assert all(len(fixture.identity_sha256) == 64 for fixture in first.values())
    assert len({fixture.identity_sha256 for fixture in first.values()}) == len(first)


def test_cf1_fixture_matrix_rejects_duplicate_names_and_evidence() -> None:
    fixture = CF1_FIXTURE_MATRIX[0]
    with pytest.raises(ValueError, match="names must be unique"):
        validate_fixture_matrix((fixture, fixture))
    duplicate_evidence = replace(
        fixture, name="duplicate_evidence", evidence_kinds=("result", "result")
    )
    with pytest.raises(ValueError, match="repeats evidence kinds"):
        validate_fixture_matrix((duplicate_evidence,))
