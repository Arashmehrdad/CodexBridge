from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from .models import ProjectManifest

MANIFEST_FILENAME = "soma.project.json"
MAX_MANIFEST_BYTES = 1_048_576


class ManifestState(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class ManifestLoadResult:
    state: ManifestState
    manifest: ProjectManifest | None = None
    error_code: str = ""

    @property
    def valid(self) -> bool:
        return self.state is ManifestState.VALID and self.manifest is not None


def load_project_manifest(repository_root: str | Path) -> ManifestLoadResult:
    """Load the tracked portable manifest without mutating repository state."""
    root = Path(repository_root)
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return ManifestLoadResult(state=ManifestState.MISSING)
    if not manifest_path.is_file():
        return ManifestLoadResult(
            state=ManifestState.MALFORMED,
            error_code="manifest_not_file",
        )

    try:
        size = manifest_path.stat().st_size
        if size > MAX_MANIFEST_BYTES:
            return ManifestLoadResult(
                state=ManifestState.MALFORMED,
                error_code="manifest_too_large",
            )
        raw = manifest_path.read_bytes()
        payload = json.loads(raw.decode("utf-8", errors="strict"))
        manifest = ProjectManifest.model_validate(payload)
    except UnicodeDecodeError:
        return ManifestLoadResult(
            state=ManifestState.MALFORMED,
            error_code="manifest_not_utf8",
        )
    except json.JSONDecodeError:
        return ManifestLoadResult(
            state=ManifestState.MALFORMED,
            error_code="manifest_invalid_json",
        )
    except ValidationError:
        return ManifestLoadResult(
            state=ManifestState.MALFORMED,
            error_code="manifest_schema_invalid",
        )
    except OSError:
        return ManifestLoadResult(
            state=ManifestState.MALFORMED,
            error_code="manifest_read_error",
        )

    return ManifestLoadResult(state=ManifestState.VALID, manifest=manifest)
