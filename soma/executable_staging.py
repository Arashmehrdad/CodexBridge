from __future__ import annotations

from base64 import b64decode
from hashlib import sha256
from pathlib import Path, PurePosixPath


def _sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def build_executable_staging_manifest(
    input_data: dict[str, object],
    *,
    run_id: str,
    lease_generation: int,
) -> dict[str, object]:
    stdin_mode = str(input_data.get("stdin_mode", "none"))
    if stdin_mode == "text":
        payload = str(input_data.get("stdin_text") or "").encode("utf-8")
    elif stdin_mode == "bytes":
        try:
            payload = b64decode(str(input_data.get("stdin_base64") or ""), validate=True)
        except Exception as exc:
            raise ValueError("Executable binary stdin is invalid") from exc
    elif stdin_mode == "none":
        payload = b""
    else:
        raise ValueError(f"Unsupported executable stdin mode: {stdin_mode}")

    preserve = bool(input_data.get("preserve_protected_artifacts", True))
    outputs: list[dict[str, object]] = []
    for stream in ("stdout", "stderr"):
        mode = str(input_data.get(f"{stream}_mode", "protected_artifact"))
        classification = (
            "protected_evidence"
            if preserve and mode == "protected_artifact"
            else "staged_output"
        )
        outputs.append(
            {
                "stream": stream,
                "relative_path": f"{stream}.bin",
                "classification": classification,
            }
        )

    return {
        "version": 1,
        "invoking_run_id": run_id,
        "lease_generation": int(lease_generation),
        "input": {
            "mode": stdin_mode,
            "relative_path": "inputs/stdin.bin" if stdin_mode != "none" else "",
            "size_bytes": len(payload),
            "sha256": _sha256_bytes(payload),
            "classification": "staged_input",
        },
        "outputs": outputs,
    }


def stage_executable_input(
    run_dir: Path,
    input_data: dict[str, object],
    manifest: dict[str, object],
) -> None:
    input_entry = manifest.get("input")
    if not isinstance(input_entry, dict):
        raise ValueError("Executable staging manifest input is invalid")
    relative_path = str(input_entry.get("relative_path") or "")
    if not relative_path:
        return
    mode = str(input_entry.get("mode") or "")
    if mode == "text":
        payload = str(input_data.get("stdin_text") or "").encode("utf-8")
    elif mode == "bytes":
        payload = b64decode(str(input_data.get("stdin_base64") or ""), validate=True)
    else:
        raise ValueError("Executable staged input mode is invalid")
    path = _resolve_run_relative_path(run_dir, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def validate_executable_staging_manifest(
    run_dir: Path,
    manifest: dict[str, object],
    *,
    run_id: str,
    lease_generation: int,
) -> tuple[bytes | None, dict[str, Path], list[dict[str, object]]]:
    if manifest.get("version") != 1:
        raise ValueError("Executable staging manifest version is unsupported")
    if manifest.get("invoking_run_id") != run_id:
        raise ValueError("Executable staging manifest run identity does not match")
    if int(manifest.get("lease_generation") or 0) != int(lease_generation):
        raise ValueError("Executable staging manifest lease generation does not match")

    input_entry = manifest.get("input")
    outputs = manifest.get("outputs")
    if not isinstance(input_entry, dict) or not isinstance(outputs, list):
        raise ValueError("Executable staging manifest entries are invalid")

    relative_input = str(input_entry.get("relative_path") or "")
    stdin_payload: bytes | None = None
    if relative_input:
        input_path = _resolve_run_relative_path(run_dir, relative_input)
        if not input_path.is_file() or input_path.is_symlink():
            raise ValueError("Executable staged input is missing or unsafe")
        stdin_payload = input_path.read_bytes()
        if len(stdin_payload) != int(input_entry.get("size_bytes") or 0):
            raise ValueError("Executable staged input size changed after acceptance")
        if _sha256_bytes(stdin_payload) != str(input_entry.get("sha256") or ""):
            raise ValueError("Executable staged input SHA-256 changed after acceptance")

    output_paths: dict[str, Path] = {}
    normalized_outputs: list[dict[str, object]] = []
    for raw in outputs:
        if not isinstance(raw, dict):
            raise ValueError("Executable staging output entry is invalid")
        stream = str(raw.get("stream") or "")
        if stream not in {"stdout", "stderr"} or stream in output_paths:
            raise ValueError("Executable staging output stream is invalid")
        classification = str(raw.get("classification") or "")
        if classification not in {"protected_evidence", "staged_output"}:
            raise ValueError("Executable staging output classification is invalid")
        relative_path = str(raw.get("relative_path") or "")
        output_paths[stream] = _resolve_run_relative_path(run_dir, relative_path)
        normalized_outputs.append(
            {
                "stream": stream,
                "relative_path": relative_path,
                "classification": classification,
            }
        )
    if set(output_paths) != {"stdout", "stderr"}:
        raise ValueError("Executable staging manifest must declare stdout and stderr")
    return stdin_payload, output_paths, normalized_outputs


def _resolve_run_relative_path(run_dir: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if not relative_path or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Executable staging path escapes the run directory")
    root = run_dir.resolve()
    candidate = (run_dir / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Executable staging path escapes the run directory") from exc
    return candidate
