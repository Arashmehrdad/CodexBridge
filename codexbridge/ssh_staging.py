from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath


def _sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def build_ssh_staging_manifest(
    *,
    tool: str,
    run_id: str,
    lease_generation: int,
    script: str | None = None,
) -> dict[str, object]:
    if tool not in {"ssh_reviewed_script", "ssh_monitored_command"}:
        raise ValueError(f"Unsupported SSH staging tool: {tool}")
    inputs: list[dict[str, object]] = []
    if tool == "ssh_reviewed_script":
        payload = (script or "").encode("utf-8")
        inputs.append(
            {
                "name": "script",
                "relative_path": "inputs/reviewed-script.bin",
                "size_bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "classification": "protected_input",
            }
        )
    return {
        "version": 1,
        "tool": tool,
        "invoking_run_id": run_id,
        "lease_generation": int(lease_generation),
        "inputs": inputs,
        "outputs": [
            {
                "stream": stream,
                "relative_path": f"{stream}.txt",
                "classification": "protected_evidence",
            }
            for stream in ("stdout", "stderr")
        ],
    }


def stage_ssh_inputs(
    run_dir: Path,
    *,
    script: str | None,
    manifest: dict[str, object],
) -> None:
    for raw in manifest.get("inputs", []):
        if not isinstance(raw, dict):
            raise ValueError("SSH staging input entry is invalid")
        if raw.get("name") != "script":
            raise ValueError("SSH staging input name is invalid")
        path = _resolve_run_relative_path(run_dir, str(raw.get("relative_path") or ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((script or "").encode("utf-8"))


def validate_ssh_staging_manifest(
    run_dir: Path,
    manifest: dict[str, object],
    *,
    tool: str,
    run_id: str,
    lease_generation: int,
) -> tuple[str | None, dict[str, Path], list[dict[str, object]]]:
    if manifest.get("version") != 1 or manifest.get("tool") != tool:
        raise ValueError("SSH staging manifest identity is invalid")
    if manifest.get("invoking_run_id") != run_id:
        raise ValueError("SSH staging manifest run identity does not match")
    if int(manifest.get("lease_generation") or 0) != int(lease_generation):
        raise ValueError("SSH staging manifest lease generation does not match")
    raw_inputs = manifest.get("inputs")
    raw_outputs = manifest.get("outputs")
    if not isinstance(raw_inputs, list) or not isinstance(raw_outputs, list):
        raise ValueError("SSH staging manifest entries are invalid")

    script: str | None = None
    if tool == "ssh_reviewed_script":
        if len(raw_inputs) != 1 or not isinstance(raw_inputs[0], dict):
            raise ValueError("Reviewed-script staging input is invalid")
        entry = raw_inputs[0]
        if entry.get("name") != "script" or entry.get("classification") != "protected_input":
            raise ValueError("Reviewed-script staging classification is invalid")
        path = _resolve_run_relative_path(run_dir, str(entry.get("relative_path") or ""))
        if not path.is_file() or path.is_symlink():
            raise ValueError("Reviewed-script staged input is missing or unsafe")
        payload = path.read_bytes()
        if len(payload) != int(entry.get("size_bytes") or 0):
            raise ValueError("Reviewed-script staged input size changed after acceptance")
        if _sha256_bytes(payload) != str(entry.get("sha256") or ""):
            raise ValueError("Reviewed-script staged input SHA-256 changed after acceptance")
        try:
            script = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Reviewed-script staged input is not valid UTF-8") from exc
    elif raw_inputs:
        raise ValueError("Remote-controller staging must not declare local inputs")

    output_paths: dict[str, Path] = {}
    normalized: list[dict[str, object]] = []
    for raw in raw_outputs:
        if not isinstance(raw, dict):
            raise ValueError("SSH staging output entry is invalid")
        stream = str(raw.get("stream") or "")
        if stream not in {"stdout", "stderr"} or stream in output_paths:
            raise ValueError("SSH staging output stream is invalid")
        if raw.get("classification") != "protected_evidence":
            raise ValueError("SSH staging output classification is invalid")
        relative_path = str(raw.get("relative_path") or "")
        output_paths[stream] = _resolve_run_relative_path(run_dir, relative_path)
        normalized.append(
            {
                "stream": stream,
                "relative_path": relative_path,
                "classification": "protected_evidence",
            }
        )
    if set(output_paths) != {"stdout", "stderr"}:
        raise ValueError("SSH staging manifest must declare stdout and stderr")
    return script, output_paths, normalized


def _resolve_run_relative_path(run_dir: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if not relative_path or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("SSH staging path escapes the run directory")
    root = run_dir.resolve()
    candidate = (run_dir / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("SSH staging path escapes the run directory") from exc
    return candidate
