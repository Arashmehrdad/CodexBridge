"""Soma-side PulseSender return-loop contract helpers."""

from .atomic_writer import atomic_write_json, atomic_write_text
from .models import (
    AtomicWriteResult,
    PulseSenderContract,
    ReportManifest,
    ReportReadinessResult,
    ResumePrompt,
    ReturnLoopArtifact,
    ReturnLoopStatus,
)
from .pulse_contract import (
    build_job_report_manifest,
    check_report_readiness,
    discover_ready_reports,
    mark_sent_by_external_pulsesender,
)

__all__ = [
    "AtomicWriteResult",
    "PulseSenderContract",
    "ReportManifest",
    "ReportReadinessResult",
    "ResumePrompt",
    "ReturnLoopArtifact",
    "ReturnLoopStatus",
    "atomic_write_json",
    "atomic_write_text",
    "build_job_report_manifest",
    "check_report_readiness",
    "discover_ready_reports",
    "mark_sent_by_external_pulsesender",
]
