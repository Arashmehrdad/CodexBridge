from __future__ import annotations

from pathlib import Path

from soma.return_loop.atomic_writer import atomic_write_json, atomic_write_text

from .models import CodexEscalationPacket, CodexInvocationResult, CodexPacketArtifact


def write_packet_artifacts(
    packet_dir: Path, packet: CodexEscalationPacket, prompt: str
) -> CodexPacketArtifact:
    target = packet_dir / packet.escalation_id
    target.mkdir(parents=True, exist_ok=True)
    packet_path = target / "packet.json"
    prompt_path = target / "prompt.txt"
    manifest_path = target / "context_manifest.json"
    policy_path = target / "policy_result.json"
    atomic_write_json(packet_path, packet.to_dict())
    atomic_write_text(prompt_path, prompt)
    atomic_write_json(
        manifest_path,
        {
            "escalation_id": packet.escalation_id,
            "relevant_files": [
                item.model_dump(mode="json") for item in packet.relevant_files
            ],
            "source_artifacts": [str(path) for path in packet.source_artifacts],
        },
    )
    atomic_write_json(policy_path, packet.policy_decision)
    atomic_write_text(target / "events.jsonl", "")
    return CodexPacketArtifact(
        escalation_id=packet.escalation_id,
        packet_dir=target,
        packet_json_path=packet_path,
        prompt_path=prompt_path,
        context_manifest_path=manifest_path,
        policy_result_path=policy_path,
    )


def write_invocation_artifacts(
    artifacts: CodexPacketArtifact, invocation: dict, result: CodexInvocationResult
) -> CodexPacketArtifact:
    invocation_path = artifacts.packet_dir / "codex_invocation.json"
    result_path = artifacts.packet_dir / "codex_result.json"
    atomic_write_json(invocation_path, invocation)
    atomic_write_json(result_path, result.model_dump(mode="json"))
    artifacts.codex_invocation_path = invocation_path
    artifacts.codex_result_path = result_path
    return artifacts
