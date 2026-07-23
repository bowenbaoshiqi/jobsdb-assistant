"""Job evaluation contracts."""

from pydantic import BaseModel, Field, PositiveInt


class JobEvaluation(BaseModel):
    job_snapshot_id: str
    profile_version: PositiveInt
    engine_version: str
    prompt_version: str
    overall_score: float = Field(ge=1.0, le=5.0)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    recommendation: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
