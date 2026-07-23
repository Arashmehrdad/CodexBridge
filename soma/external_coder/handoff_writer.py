from __future__ import annotations

from pathlib import Path

from soma.return_loop.atomic_writer import atomic_write_json, atomic_write_text

from .models import ExternalCoderHandoff, ExternalCoderHandoffArtifact


def write_handoff_artifacts(
    handoff_dir: Path, handoff: ExternalCoderHandoff, prompt: str
) -> ExternalCoderHandoffArtifact:
    target = handoff_dir / handoff.handoff_id
    target.mkdir(parents=True, exist_ok=True)
    handoff_path = target / "handoff.json"
    prompt_path = target / "prompt.txt"
    manifest_path = target / "context_manifest.json"
    policy_path = target / "policy_result.json"
    atomic_write_json(handoff_path, handoff.to_dict())
    atomic_write_text(prompt_path, prompt)
    atomic_write_json(
        manifest_path,
        {
            "handoff_id": handoff.handoff_id,
            "relevant_files": [
                item.model_dump(mode="json") for item in handoff.relevant_files
            ],
            "source_artifacts": [str(path) for path in handoff.source_artifacts],
        },
    )
    atomic_write_json(policy_path, handoff.policy_decision)
    atomic_write_text(target / "events.jsonl", "")
    return ExternalCoderHandoffArtifact(
        handoff_id=handoff.handoff_id,
        handoff_dir=target,
        handoff_json_path=handoff_path,
        prompt_path=prompt_path,
        context_manifest_path=manifest_path,
        policy_result_path=policy_path,
    )
