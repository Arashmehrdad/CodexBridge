"""Provider-neutral canonical Task route contracts for Company WorkPackageAttempts.

Company owns the route-independent WorkPackage/outcome identity. A concrete
WorkPackageAttempt carries one exact canonical Task request chosen by Sol/Work.
Reasoning is one optional Task route; it is never a prerequisite for Company.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soma.reasoning.models import ReasoningSpecV1


class _FrozenTaskRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DurableCommandTaskRequestV1(_FrozenTaskRouteModel):
    """One canonical durable-command Task request selected by the executive."""

    task_kind: Literal["durable_command"] = "durable_command"
    backend_kind: Literal["soma_durable_run"] = "soma_durable_run"
    profile_id: str = Field(default="powershell", min_length=1, max_length=128)
    argv: tuple[str, ...] = Field(default=(), max_length=10_000)
    working_directory: str = Field(default="", max_length=32_768)
    environment: dict[str, str] = Field(default_factory=dict, max_length=10_000)
    stdin_text: str | None = Field(default=None, max_length=2_000_000)
    stdin_base64: str | None = Field(default=None, max_length=2_700_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604_800)
    parent_task_id: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def _validate_stdin(self):
        if self.stdin_text is not None and self.stdin_base64 is not None:
            raise ValueError("Specify either stdin_text or stdin_base64, not both")
        return self


class ReasoningTaskRequestV1(_FrozenTaskRouteModel):
    """Optional specialist reasoning Task request selected by Sol/Work."""

    task_kind: Literal["reasoning"] = "reasoning"
    backend_kind: Literal["soma_reasoning"] = "soma_reasoning"
    reasoning_spec: ReasoningSpecV1
    parent_task_id: str = Field(default="", max_length=128)


CompanyTaskRequestV1 = Annotated[
    DurableCommandTaskRequestV1 | ReasoningTaskRequestV1,
    Field(discriminator="task_kind"),
]
