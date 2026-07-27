"""Evidence-backed CV and interview synthesis contracts."""

from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from src.domain.candidate_interview import (
    InterviewAnswer,
    InterviewAnswerStatus,
    InterviewDimension,
)


class FactEvidence(BaseModel):
    """Source locator supporting one candidate value."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    locator: str = Field(min_length=1)


class SourcedText(BaseModel):
    """One non-empty candidate value with direct source evidence."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)
    evidence: tuple[FactEvidence, ...] = Field(min_length=1)


class CandidateExperience(BaseModel):
    """One ordered evidence-backed employment entry."""

    model_config = ConfigDict(frozen=True)

    role: SourcedText
    company: SourcedText
    period: SourcedText
    location: SourcedText | None = None
    bullets: tuple[SourcedText, ...] = ()


class CandidateEducation(BaseModel):
    """One ordered evidence-backed education entry."""

    model_config = ConfigDict(frozen=True)

    degree: SourcedText
    institution: SourcedText
    period: SourcedText | None = None
    topics: tuple[SourcedText, ...] = ()


class CandidateCv(BaseModel):
    """Canonical CV data from candidate-owned evidence."""

    model_config = ConfigDict(frozen=True)

    full_name: SourcedText | None = None
    email: SourcedText | None = None
    phone: SourcedText | None = None
    location: SourcedText | None = None
    linkedin: SourcedText | None = None
    github: SourcedText | None = None
    headline: SourcedText | None = None
    summary: SourcedText | None = None
    experience: tuple[CandidateExperience, ...] = ()
    education: tuple[CandidateEducation, ...] = ()
    skills: dict[str, tuple[SourcedText, ...]] = Field(
        default_factory=dict
    )
    projects: tuple[SourcedText, ...] = ()
    certifications: tuple[SourcedText, ...] = ()
    publications: tuple[SourcedText, ...] = ()
    awards: tuple[SourcedText, ...] = ()
    languages: tuple[SourcedText, ...] = ()
    proof_points: tuple[SourcedText, ...] = ()


class IntentTargetField(StrEnum):
    """Canonical destination for one interview dimension."""

    BEHAVIORAL_STYLE = "behavioral_style"
    CAREER_GOALS = "career_goals"
    NEXT_ROLE_MOTIVATORS = "next_role_motivators"
    MUST_HAVES = "must_haves"
    DEAL_BREAKERS = "deal_breakers"
    SALARY_EXPECTATIONS = "salary_expectations"
    REFERENCES = "references"


class IntentSynthesis(BaseModel):
    """Agent synthesis tied to one exact Python-owned answer."""

    model_config = ConfigDict(frozen=True)

    dimension: InterviewDimension
    answer_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str | None = None
    target_field: IntentTargetField
    target_roles: tuple[str, ...] = ()
    role_archetypes: tuple[str, ...] = ()
    culture_requirements: tuple[str, ...] = ()
    compensation_target: str | None = None
    compensation_minimum: str | None = None
    compensation_currency: str | None = None


def interview_answer_hash(answer: InterviewAnswer) -> str:
    """Hash the exact answer value or explicit skip status."""

    payload = (
        answer.value
        if answer.status is InterviewAnswerStatus.ANSWERED
        else answer.status.value
    )
    if payload is None:
        raise ValueError("answered interview value is missing")
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_intent_syntheses(
    answers: dict[InterviewDimension, InterviewAnswer],
    syntheses: tuple[IntentSynthesis, ...],
) -> tuple[IntentSynthesis, ...]:
    """Require one correctly bound synthesis per persisted answer."""

    dimensions = [item.dimension for item in syntheses]
    if len(dimensions) != len(answers) or set(dimensions) != set(answers):
        raise ValueError("intent synthesis coverage mismatch")
    for synthesis in syntheses:
        answer = answers[synthesis.dimension]
        if synthesis.answer_hash != interview_answer_hash(answer):
            raise ValueError(
                f"answer hash mismatch: {synthesis.dimension.value}"
            )
        if synthesis.target_field.value != synthesis.dimension.value:
            raise ValueError(
                f"intent target mismatch: {synthesis.dimension.value}"
            )
        if (
            answer.status is InterviewAnswerStatus.ANSWERED
            and (
                synthesis.summary is None
                or not synthesis.summary.strip()
            )
        ):
            raise ValueError(
                f"answered intent requires synthesis: "
                f"{synthesis.dimension.value}"
            )
    return syntheses
