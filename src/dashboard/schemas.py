"""Validated read models and requests for the local Dashboard."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.job import ApplyType
from src.domain.material import MaterialReviewStatus, MaterialTaskStatus
from src.storage.dashboard_application_repository import (
    DashboardApplicationTask,
)


class DashboardMaterialSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_id: str | None = None
    version: int | None = None
    review_status: MaterialReviewStatus | None = None
    task_status: MaterialTaskStatus | None = None


class DashboardFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    show: Literal["evaluated", "all"] = "evaluated"
    score_min: float | None = Field(default=None, ge=1.0, le=5.0)
    apply_type: ApplyType | None = None
    selected: bool | None = None
    query: str | None = None


class DashboardDimension(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal["A", "B", "C", "D", "E", "F"]
    title: str
    score: float | None
    findings: list[str]
    evidence: list[str]


class EvaluationProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    evaluation_created_at: datetime | None
    profile_version: int
    profile_hash: str | None
    snapshot_id: str
    snapshot_hash: str | None
    engine_version: str
    engine_commit: str | None
    prompt_version: str
    cache_status: Literal["persisted"] = "persisted"


class CandidateProfileSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str
    profile_version: int
    target_roles: list[str]
    preferences: dict[str, str | int | float | bool]
    exclusions: list[str]
    writing_style: dict[str, str]


class DashboardJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    snapshot_id: str
    title: str
    company: str
    location: str | None
    canonical_url: str
    apply_type: ApplyType
    jd_text: str
    evaluation_status: Literal["evaluated", "pending"]
    overall_score: float | None = None
    dimensions: list[DashboardDimension] = Field(default_factory=list)
    recommendation: str | None = None
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    provenance: EvaluationProvenance | None = None
    profile_summary: CandidateProfileSummary | None = None
    profile_requirement_verdicts: None = None
    selected: bool = False
    selection_status: Literal["waiting_for_materials"] | None = None
    application_task: DashboardApplicationTask | None = None
    material: DashboardMaterialSummary | None = None


class DashboardSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    evaluated: int
    pending: int
    selected: int
    score_buckets: dict[str, int]


class DashboardPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    jobs: list[DashboardJob]
    summary: DashboardSummary
