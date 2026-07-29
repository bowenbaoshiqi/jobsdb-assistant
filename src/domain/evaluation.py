"""Native career-ops job evaluation contracts."""

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    model_validator,
)


class NativeDimension(BaseModel):
    """One native career-ops A-F evaluation block."""

    model_config = ConfigDict(frozen=True)

    code: Literal["A", "B", "C", "D", "E", "F"]
    title: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=1.0, le=5.0)
    findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class JobEvaluation(BaseModel):
    """Immutable, schema-validated native career-ops result."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    job_snapshot_id: str
    profile_version: PositiveInt
    profile_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    snapshot_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    engine_version: str
    engine_commit: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{40}$",
    )
    prompt_version: str
    jd_summary_zh_cn: str | None = Field(default=None, min_length=1)
    overall_score: float = Field(ge=1.0, le=5.0)
    dimensions: list[NativeDimension] = Field(default_factory=list)
    recommendation: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_native_dimensions(self) -> "JobEvaluation":
        codes = [dimension.code for dimension in self.dimensions]
        if codes != list("ABCDEF"):
            raise ValueError(
                "native dimensions must contain ordered A through F"
            )
        return self


class EvaluationCacheKey(BaseModel):
    """Exact identity for safely reusing one evaluation."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str | None = None
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_projection_version: str = Field(min_length=1)
    engine_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    contract_version: str = Field(min_length=1)

    def digest(self) -> str:
        payload = self.model_dump_json().encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
