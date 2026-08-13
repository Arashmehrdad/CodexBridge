"""Generic repository evidence mapping with a mechanical Soma boundary.

The reasoning worker owns semantic analysis and chooses source locations. Soma
only verifies that each chosen path/range exists in the frozen source snapshot,
materializes exact evidence, and preserves it for later Sol adjudication.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.company_kernel.models import validate_opaque, validate_sha256
from soma.worker_evidence.models import (
    EvidenceAssignmentV1,
    EvidenceBlockerV1,
    EvidenceByteAccountingV1,
    EvidenceClaimV1,
    EvidenceHashedReferenceV1,
    EvidenceProducerV1,
    EvidenceRecordV1,
    EvidenceSubmissionV1,
    EvidenceUncertaintyV1,
    EvidenceUsageV1,
    EvidenceWorkIdentityV1,
    MAX_EVIDENCE_EXCERPT_CHARACTERS,
    MAX_EVIDENCE_RECORDS,
)


REPOSITORY_REASONING_SEMANTIC_VERSION: Final[str] = "repository_reasoning.semantic.v1"
REPOSITORY_REASONING_ADAPTER_ID: Final[str] = "soma.reasoning.repository.v1"


class RepositoryEvidenceError(ValueError):
    """Worker evidence cannot be mapped mechanically to the frozen source."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RepositorySourceLocatorV1(_FrozenModel):
    source_path: str = Field(min_length=1, max_length=2048)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_locator(self):
        if self.end_line < self.start_line:
            raise ValueError("source locator end_line must be >= start_line")
        _normalize_path(self.source_path)
        return self


class RepositoryReasoningClaimV1(_FrozenModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_class: Literal[
        "observation", "inference", "recommendation", "negative_finding"
    ]
    subject_key: str | None = Field(default=None, max_length=256)
    statement: str = Field(min_length=1, max_length=4096)
    evidence_locations: tuple[RepositorySourceLocatorV1, ...] = Field(
        default=(), max_length=24
    )
    uncertainty_ids: tuple[str, ...] = Field(default=(), max_length=12)


class RepositoryReasoningUncertaintyV1(_FrozenModel):
    uncertainty_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)
    related_claim_ids: tuple[str, ...] = Field(default=(), max_length=12)
    required_resolution: str | None = Field(default=None, max_length=2048)


class RepositoryReasoningBlockerV1(_FrozenModel):
    blocker_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2048)


class RepositoryReasoningPayloadV1(_FrozenModel):
    schema_version: Literal[REPOSITORY_REASONING_SEMANTIC_VERSION] = (
        REPOSITORY_REASONING_SEMANTIC_VERSION
    )
    submission_disposition: Literal["complete", "partial", "blocked", "uncertain"]
    executive_summary: str = Field(max_length=1024)
    claims: tuple[RepositoryReasoningClaimV1, ...] = Field(default=(), max_length=12)
    uncertainties: tuple[RepositoryReasoningUncertaintyV1, ...] = Field(
        default=(), max_length=12
    )
    blockers: tuple[RepositoryReasoningBlockerV1, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def _validate_refs(self):
        claim_ids = [item.claim_id for item in self.claims]
        uncertainty_ids = [item.uncertainty_id for item in self.uncertainties]
        blocker_ids = [item.blocker_id for item in self.blockers]
        for label, values in (
            ("claim", claim_ids),
            ("uncertainty", uncertainty_ids),
            ("blocker", blocker_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")
        known_uncertainties = set(uncertainty_ids)
        known_claims = set(claim_ids)
        for claim in self.claims:
            missing = set(claim.uncertainty_ids) - known_uncertainties
            if missing:
                raise ValueError(
                    f"claim {claim.claim_id} references unknown uncertainty IDs: {sorted(missing)}"
                )
        for item in self.uncertainties:
            missing = set(item.related_claim_ids) - known_claims
            if missing:
                raise ValueError(
                    f"uncertainty {item.uncertainty_id} references unknown claims: {sorted(missing)}"
                )
        return self


class FrozenSourceLoader(Protocol):
    """Mechanical loader already bound to one immutable repository snapshot."""

    def load(self, source_path: str) -> bytes: ...


def _normalize_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RepositoryEvidenceError(
            "source_path must be a normalized repository-relative path"
        )
    return path.as_posix()


def semantic_output_schema() -> dict[str, Any]:
    """Strict provider shape; semantic truth is deliberately not encoded."""
    schema = RepositoryReasoningPayloadV1.model_json_schema()

    def strict(value: Any) -> Any:
        if isinstance(value, list):
            return [strict(item) for item in value]
        if not isinstance(value, dict):
            return value
        normalized = {
            key: strict(item) for key, item in value.items() if key != "default"
        }
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized["additionalProperties"] = False
            normalized["required"] = list(properties)
        return normalized

    return strict(schema)


def parse_semantic_output(text: str) -> RepositoryReasoningPayloadV1:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RepositoryEvidenceError(
            f"provider final message is not exact JSON: {exc}"
        ) from exc
    try:
        return RepositoryReasoningPayloadV1.model_validate(value)
    except ValueError as exc:
        raise RepositoryEvidenceError(str(exc)) from exc


def resolve_source_locator(
    loader: FrozenSourceLoader, locator: RepositorySourceLocatorV1
) -> tuple[str, str, str]:
    """Return normalized path, source SHA-256, and exact selected text."""
    path = _normalize_path(locator.source_path)
    body = loader.load(path)
    digest = hashlib.sha256(body).hexdigest()
    try:
        lines = body.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RepositoryEvidenceError(f"source {path!r} is not UTF-8 text") from exc
    if locator.end_line > len(lines):
        raise RepositoryEvidenceError(
            f"source locator exceeds line count: {path!r} has {len(lines)} lines"
        )
    selected = "\n".join(lines[locator.start_line - 1 : locator.end_line])
    return path, digest, selected


def validate_semantic_mechanics(
    payload: RepositoryReasoningPayloadV1, loader: FrozenSourceLoader
) -> None:
    """Validate source membership/ranges only; never whether evidence proves a claim."""
    for claim in payload.claims:
        for locator in claim.evidence_locations:
            resolve_source_locator(loader, locator)


def _selected_locations(
    payload: RepositoryReasoningPayloadV1,
) -> dict[str, tuple[RepositorySourceLocatorV1, ...]]:
    buckets: list[tuple[str, tuple[RepositorySourceLocatorV1, ...]]] = []
    for claim in payload.claims:
        unique: list[RepositorySourceLocatorV1] = []
        seen: set[tuple[str, int, int]] = set()
        for locator in claim.evidence_locations:
            key = (_normalize_path(locator.source_path), locator.start_line, locator.end_line)
            if key not in seen:
                seen.add(key)
                unique.append(locator)
        if unique:
            buckets.append((claim.claim_id, tuple(unique)))
    if len(buckets) > MAX_EVIDENCE_RECORDS:
        raise RepositoryEvidenceError("claims with evidence exceed EvidenceSubmission cap")
    selected = {claim_id: [items[0]] for claim_id, items in buckets}
    remaining = MAX_EVIDENCE_RECORDS - len(selected)
    depth = 1
    while remaining > 0:
        progressed = False
        for claim_id, items in buckets:
            if depth < len(items):
                selected[claim_id].append(items[depth])
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
        if not progressed:
            break
        depth += 1
    return {key: tuple(value) for key, value in selected.items()}


def build_evidence_submission(
    *,
    payload: RepositoryReasoningPayloadV1,
    loader: FrozenSourceLoader,
    source_revision_ref: str,
    work_identity: EvidenceWorkIdentityV1,
    assignment_ref: str,
    assignment_hash: str,
    backend_kind: str,
    provider: str | None,
    model_or_profile: str | None,
    native_session_ref: str | None = None,
    wall_time_seconds: float = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: Decimal = Decimal("0"),
    provenance_refs: tuple[tuple[str, str], ...] = (),
) -> EvidenceSubmissionV1:
    """Wrap worker semantics in mechanically verified immutable source evidence."""
    validate_sha256(assignment_hash, "assignment_hash")
    validate_opaque(source_revision_ref, "source_revision_ref", max_length=256)
    validate_semantic_mechanics(payload, loader)
    selected = _selected_locations(payload)
    records: list[EvidenceRecordV1] = []
    evidence_ids: dict[tuple[str, str, int, int], str] = {}
    referenced_bytes = 0
    for claim in payload.claims:
        for locator in selected.get(claim.claim_id, ()):
            path, source_hash, selected_text = resolve_source_locator(loader, locator)
            excerpt = selected_text[:MAX_EVIDENCE_EXCERPT_CHARACTERS]
            referenced_bytes += len(excerpt.encode("utf-8"))
            key = (claim.claim_id, path, locator.start_line, locator.end_line)
            evidence_id = "repo_evidence_" + hashlib.sha256(
                "\0".join(map(str, key)).encode("utf-8")
            ).hexdigest()[:24]
            evidence_ids[key] = evidence_id
            records.append(
                EvidenceRecordV1(
                    evidence_id=evidence_id,
                    source_kind="frozen_repository_source",
                    source_ref=f"{source_revision_ref}:{path}",
                    source_hash=source_hash,
                    locator=f"lines:{locator.start_line}-{locator.end_line}",
                    content_type="text/plain",
                    excerpt=excerpt,
                    fact_key=claim.subject_key,
                    fact_value=claim.statement,
                )
            )
    provenance = tuple(
        EvidenceHashedReferenceV1(ref=ref, hash=digest)
        for ref, digest in provenance_refs
    )
    payload_hash = hashlib.sha256(
        json.dumps(
            payload.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    submission_seed = (
        f"{work_identity.task_id}\0{work_identity.backend_ref or ''}\0{payload_hash}"
    )
    return EvidenceSubmissionV1(
        submission_id="repo_submission_"
        + hashlib.sha256(submission_seed.encode("utf-8")).hexdigest()[:24],
        work_identity=work_identity,
        assignment=EvidenceAssignmentV1(
            contract_ref=assignment_ref,
            contract_hash=assignment_hash,
        ),
        producer=EvidenceProducerV1(
            backend_kind=backend_kind,
            provider=provider,
            model_or_profile=model_or_profile,
            adapter_id=REPOSITORY_REASONING_ADAPTER_ID,
            native_session_ref=native_session_ref,
        ),
        submission_disposition=payload.submission_disposition,
        executive_summary=payload.executive_summary,
        claims=tuple(
            EvidenceClaimV1(
                claim_id=claim.claim_id,
                claim_class=claim.claim_class,
                subject_key=claim.subject_key,
                statement=claim.statement,
                supports_evidence_ids=tuple(
                    evidence_ids[
                        (
                            claim.claim_id,
                            _normalize_path(locator.source_path),
                            locator.start_line,
                            locator.end_line,
                        )
                    ]
                    for locator in selected.get(claim.claim_id, ())
                ),
                opposes_evidence_ids=(),
                uncertainty_ids=claim.uncertainty_ids,
            )
            for claim in payload.claims
        ),
        evidence=tuple(records),
        uncertainties=tuple(
            EvidenceUncertaintyV1(
                uncertainty_id=item.uncertainty_id,
                kind=item.kind,
                statement=item.statement,
                related_claim_ids=item.related_claim_ids,
                required_resolution=item.required_resolution,
            )
            for item in payload.uncertainties
        ),
        blockers=tuple(
            EvidenceBlockerV1(
                blocker_id=item.blocker_id,
                kind=item.kind,
                statement=item.statement,
            )
            for item in payload.blockers
        ),
        usage=EvidenceUsageV1(
            wall_time_seconds=wall_time_seconds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        ),
        provenance=provenance,
        byte_accounting=EvidenceByteAccountingV1(
            referenced_body_bytes=referenced_bytes,
            omitted_body_bytes=0,
        ),
    )
