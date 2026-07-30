"""Frozen protocol fixtures and their integrity contract.

A fixture is compatibility evidence, never canonical company or execution state.
Each one is pinned by content hash and carries its own expected parsed outcome,
hand-authored in ``fixtures/manifest.json``. The manifest is the oracle: it is
written independently of the parser, so a parser change that alters behaviour
fails the comparison instead of silently redefining what "correct" means.

``capture_kind`` is the honesty field. None of these fixtures is a byte capture
of a live provider stream -- no such capture survives in this repository -- so
each one states exactly what it is and where it came from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Final


FIXTURE_ROOT: Final[Path] = Path(__file__).parent / "fixtures"
MANIFEST_PATH: Final[Path] = FIXTURE_ROOT / "manifest.json"


class FixtureIntegrityError(RuntimeError):
    """A fixture's bytes no longer match the hash the manifest pinned."""


@dataclass(frozen=True)
class FixtureRecord:
    name: str
    path: str
    provider: str
    protocol_id: str
    protocol_version: str
    capture_kind: str
    provenance: str
    redaction_review: str
    sha256: str
    expected: dict[str, Any]

    @property
    def full_path(self) -> Path:
        return FIXTURE_ROOT / self.path


def load_manifest() -> dict[str, FixtureRecord]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records: dict[str, FixtureRecord] = {}
    for entry in payload["fixtures"]:
        record = FixtureRecord(
            name=entry["name"],
            path=entry["path"],
            provider=entry["provider"],
            protocol_id=entry["protocol_id"],
            protocol_version=entry["protocol_version"],
            capture_kind=entry["capture_kind"],
            provenance=entry["provenance"],
            redaction_review=entry["redaction_review"],
            sha256=entry["sha256"],
            expected=entry["expected"],
        )
        records[record.name] = record
    return records


def fixture_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def read_fixture_lines(record: FixtureRecord) -> list[str]:
    """Read a fixture after verifying its pinned hash.

    Verification happens on every read rather than once at import: a fixture that
    drifts on disk must fail the test that uses it, not a distant setup step.
    """
    path = record.full_path
    actual = fixture_hash(path)
    if actual != record.sha256:
        raise FixtureIntegrityError(
            f"fixture {record.name} hash mismatch: manifest pins {record.sha256}, "
            f"file is {actual}"
        )
    return path.read_text(encoding="utf-8").splitlines()


def fixtures_for(provider: str) -> list[FixtureRecord]:
    return [
        record
        for record in load_manifest().values()
        if record.provider == provider
    ]
