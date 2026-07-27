"""Candidate profile contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from src.domain.candidate_cv import (
    CandidateCv,
    FactEvidence,
    IntentSynthesis,
)
from src.domain.candidate_interview import (
    InterviewAnswer,
    InterviewDimension,
)


class CandidateProfileProposal(BaseModel):
    """Unconfirmed AI output awaiting explicit user approval."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    verified_facts: dict[str, list[str]] = Field(default_factory=dict)
    fact_evidence: dict[str, list[FactEvidence]] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list)
    preferences: dict[str, str | int | float | bool] = Field(
        default_factory=dict
    )
    exclusions: list[str] = Field(default_factory=list)
    writing_style: dict[str, str] = Field(default_factory=dict)
    source_documents: list[str] = Field(default_factory=list)
    star_examples: list[str] = Field(default_factory=list)
    canonical_cv: CandidateCv | None = None
    interview_answers: dict[
        InterviewDimension,
        InterviewAnswer,
    ] = Field(default_factory=dict)
    intent_syntheses: tuple[IntentSynthesis, ...] = ()
    created_at: datetime


class CandidateProfile(BaseModel):
    """Confirmed immutable candidate profile version."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    version: PositiveInt
    verified_facts: dict[str, list[str]] = Field(default_factory=dict)
    fact_evidence: dict[str, list[FactEvidence]] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list)
    preferences: dict[str, str | int | float | bool] = Field(
        default_factory=dict
    )
    exclusions: list[str] = Field(default_factory=list)
    writing_style: dict[str, str] = Field(default_factory=dict)
    source_documents: list[str] = Field(default_factory=list)
    star_examples: list[str] = Field(default_factory=list)
    canonical_cv: CandidateCv | None = None
    interview_answers: dict[
        InterviewDimension,
        InterviewAnswer,
    ] = Field(default_factory=dict)
    intent_syntheses: tuple[IntentSynthesis, ...] = ()
    created_at: datetime
    confirmed_at: datetime | None = None
    content_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
