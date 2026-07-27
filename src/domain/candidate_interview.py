"""Typed candidate interview dimensions, questions, and answers."""

from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    model_validator,
)


class InterviewDimension(StrEnum):
    """Stable identifiers for first-run candidate interview coverage."""

    BEHAVIORAL_STYLE = "behavioral_style"
    CAREER_GOALS = "career_goals"
    NEXT_ROLE_MOTIVATORS = "next_role_motivators"
    MUST_HAVES = "must_haves"
    DEAL_BREAKERS = "deal_breakers"
    SALARY_EXPECTATIONS = "salary_expectations"
    REFERENCES = "references"


REQUIRED_INTERVIEW_DIMENSIONS = tuple(InterviewDimension)
OPTIONAL_INTERVIEW_DIMENSIONS = frozenset({
    InterviewDimension.SALARY_EXPECTATIONS,
    InterviewDimension.REFERENCES,
})


class InterviewAnswerStatus(StrEnum):
    """How a user completed one interview dimension."""

    ANSWERED = "answered"
    NOT_PROVIDED = "not_provided"
    NO_PREFERENCE = "no_preference"


class InterviewQuestion(BaseModel):
    """One agent-written prompt attached to a Python-owned dimension."""

    model_config = ConfigDict(frozen=True)

    dimension: InterviewDimension
    prompt: str = Field(min_length=1)
    optional: bool = False

    @model_validator(mode="after")
    def require_python_defined_optionality(self) -> "InterviewQuestion":
        expected = self.dimension in OPTIONAL_INTERVIEW_DIMENSIONS
        if self.optional is not expected:
            raise ValueError(
                "question optional flag does not match interview dimension"
            )
        return self


class InterviewAnswer(BaseModel):
    """One explicit answer or user-selected skip."""

    model_config = ConfigDict(frozen=True)

    status: InterviewAnswerStatus
    value: str | None = None

    @model_validator(mode="after")
    def require_value_when_answered(self) -> "InterviewAnswer":
        if (
            self.status is InterviewAnswerStatus.ANSWERED
            and (self.value is None or not self.value.strip())
        ):
            raise ValueError(
                "answered interview value must not be empty"
            )
        return self


class InterviewAnswers(
    RootModel[dict[InterviewDimension, InterviewAnswer]]
):
    """Complete dimension-keyed answer set."""

    @model_validator(mode="after")
    def require_complete_coverage(self) -> "InterviewAnswers":
        if set(self.root) != set(REQUIRED_INTERVIEW_DIMENSIONS):
            raise ValueError(
                "answers must cover every required interview dimension"
            )
        return self
