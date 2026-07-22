from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from .events import redact_and_truncate


_OUTPUT_STREAMS = {"stdout", "stderr"}
_OUTPUT_CLASSIFICATIONS = {"protected_evidence", "staged_output"}


@dataclass(frozen=True)
class ResolvedRunArtifact:
    stream: str
    path: Path
    classification: str
    manifest_source: str
    manifest_generation: str


def resolve_output_artifacts(
    run: dict[str, Any], runs_root: Path
) -> dict[str, ResolvedRunArtifact]:
    run_id = str(run.get("run_id") or "")
    raw_run_dir = Path(str(run.get("run_dir") or ""))
    if raw_run_dir.is_symlink():
        raise ValueError("Run directory must not be a symlink")
    run_dir = raw_run_dir.resolve()
    run_dir.relative_to(runs_root.resolve())

    input_data = run.get("input")
    manifest = (
        input_data.get("staging_manifest") if isinstance(input_data, dict) else None
    )
    if manifest is None:
        manifest_source = "legacy_output_adapter_v1"
        outputs = [
            {
                "stream": stream,
                "relative_path": f"{stream}.txt",
                "classification": "protected_evidence",
            }
            for stream in ("stdout", "stderr")
        ]
        manifest_generation = _manifest_generation(
            {"version": 1, "run_id": run_id, "outputs": outputs}
        )
    else:
        if not isinstance(manifest, dict):
            raise ValueError("Run staging manifest is invalid")
        if str(manifest.get("invoking_run_id") or "") != run_id:
            raise ValueError("Run staging manifest identity does not match")
        outputs = manifest.get("outputs")
        if not isinstance(outputs, list):
            raise ValueError("Run staging manifest outputs are invalid")
        manifest_source = "staging_manifest"
        manifest_generation = _manifest_generation(manifest)

    resolved: dict[str, ResolvedRunArtifact] = {}
    for raw in outputs:
        if not isinstance(raw, dict):
            raise ValueError("Run staging output entry is invalid")
        stream = str(raw.get("stream") or "")
        if stream not in _OUTPUT_STREAMS or stream in resolved:
            raise ValueError("Run staging output stream is invalid")
        classification = str(raw.get("classification") or "")
        if classification not in _OUTPUT_CLASSIFICATIONS:
            raise ValueError("Run staging output classification is invalid")
        relative_path = str(raw.get("relative_path") or "")
        path = _resolve_manifest_path(run_dir, relative_path)
        resolved[stream] = ResolvedRunArtifact(
            stream=stream,
            path=path,
            classification=classification,
            manifest_source=manifest_source,
            manifest_generation=manifest_generation,
        )
    if set(resolved) != _OUTPUT_STREAMS:
        raise ValueError("Run output manifest must declare stdout and stderr")
    return resolved


def read_redacted_output_tail(
    artifact: ResolvedRunArtifact,
    *,
    run_id: str,
    tail_bytes: int,
) -> dict[str, Any]:
    path = artifact.path
    if not path.exists():
        return {
            "text": "",
            "size_bytes": 0,
            "truncated": False,
            "available": False,
            "artifact": _artifact_metadata(artifact, run_id=run_id),
        }
    if not path.is_file() or path.is_symlink():
        raise ValueError("Run output is not a regular file")

    size = path.stat().st_size
    source_sha256 = _sha256_file(path)
    artifact_id = _artifact_id(
        run_id=run_id,
        artifact=artifact,
        size_bytes=size,
        source_sha256=source_sha256,
    )
    offset = max(0, size - tail_bytes)
    with path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read(tail_bytes)
    text = redact_and_truncate(payload.decode("utf-8", errors="replace"), tail_bytes)
    return {
        "text": text,
        "size_bytes": size,
        "truncated": offset > 0,
        "available": True,
        "artifact": _artifact_metadata(
            artifact,
            run_id=run_id,
            artifact_id=artifact_id,
            size_bytes=size,
            source_sha256=source_sha256,
        ),
    }


def _resolve_manifest_path(run_dir: Path, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if not normalized or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Run staging path escapes the run directory")
    unresolved = run_dir.joinpath(*relative.parts)
    current = run_dir
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Run staging path must not contain symlinks")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(run_dir)
    except ValueError as exc:
        raise ValueError("Run staging path escapes the run directory") from exc
    return candidate


def _manifest_generation(manifest: dict[str, Any]) -> str:
    payload = json.dumps(
        manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_id(
    *,
    run_id: str,
    artifact: ResolvedRunArtifact,
    size_bytes: int,
    source_sha256: str,
) -> str:
    binding = {
        "classification": artifact.classification,
        "manifest_generation": artifact.manifest_generation,
        "run_id": run_id,
        "size_bytes": size_bytes,
        "source_sha256": source_sha256,
        "stream": artifact.stream,
    }
    return "artifact_" + _manifest_generation(binding)


def _artifact_metadata(
    artifact: ResolvedRunArtifact,
    *,
    run_id: str,
    artifact_id: str = "",
    size_bytes: int = 0,
    source_sha256: str = "",
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "stream": artifact.stream,
        "classification": artifact.classification,
        "manifest_source": artifact.manifest_source,
        "manifest_generation": artifact.manifest_generation,
        "size_bytes": size_bytes,
        "source_sha256": source_sha256,
        "encoding": "binary" if artifact.path.suffix.lower() == ".bin" else "utf-8",
        "public_representation": "redacted_text_tail",
        "evidence": {
            "operation": "output",
            "run_id": run_id,
            "stream": artifact.stream,
        },
    }
