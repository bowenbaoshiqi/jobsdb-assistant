"""Adapter contract for pinned ai-job-search onboarding guidance."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationInfo,
    model_validator,
)

from src.domain.candidate import CandidateProfileProposal
from src.domain.candidate_interview import (
    REQUIRED_INTERVIEW_DIMENSIONS,
    InterviewAnswer,
    InterviewAnswers,
    InterviewDimension,
    InterviewQuestion,
)

_CAPABILITIES = [
    ".claude/commands/setup.md",
    ".claude/skills/job-application-assistant/01-candidate-profile.md",
    ".claude/skills/job-application-assistant/02-behavioral-profile.md",
]


class CandidateProfileTask(BaseModel):
    task_id: str
    integration_id: Literal["candidate-profile"] = "candidate-profile"
    integration_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    contract_version: str
    capability_paths: list[str]
    source_documents: list[str]
    answers: dict[InterviewDimension, InterviewAnswer]
    interview_complete: bool

    @model_validator(mode="after")
    def require_python_derived_completion(self) -> "CandidateProfileTask":
        complete = set(self.answers) == set(
            REQUIRED_INTERVIEW_DIMENSIONS
        )
        if self.interview_complete is not complete:
            raise ValueError(
                "interview_complete does not match validated answers"
            )
        return self


class ProfileQuestions(BaseModel):
    kind: Literal["questions"]
    task_id: str
    questions: list[InterviewQuestion] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def require_complete_coverage(self) -> "ProfileQuestions":
        dimensions = [item.dimension for item in self.questions]
        if (
            len(dimensions) != len(REQUIRED_INTERVIEW_DIMENSIONS)
            or set(dimensions) != set(REQUIRED_INTERVIEW_DIMENSIONS)
        ):
            raise ValueError(
                "questions must cover every required interview dimension"
            )
        return self


class ProfileProposalResult(BaseModel):
    kind: Literal["proposal"]
    task_id: str
    profile: CandidateProfileProposal

    @model_validator(mode="after")
    def require_legal_proposal(
        self,
        info: ValidationInfo,
    ) -> "ProfileProposalResult":
        task = (info.context or {}).get("task")
        if task is None or not task.interview_complete:
            raise ValueError(
                "interview must be completed before proposal"
            )
        for facts in self.profile.verified_facts.values():
            for fact in facts:
                if not self.profile.fact_evidence.get(fact):
                    raise ValueError(
                        f"verified fact lacks evidence: {fact}"
                    )
        return self


ProfileCheckpointResult = Annotated[
    ProfileQuestions | ProfileProposalResult,
    Field(discriminator="kind"),
]
_RESULT_ADAPTER = TypeAdapter(ProfileCheckpointResult)


class CandidateProfileAdapter:
    def __init__(
        self,
        integration_commit: str,
        contract_version: str,
    ) -> None:
        self.integration_commit = integration_commit
        self.contract_version = contract_version

    def build_task(
        self,
        task_id: str,
        source_documents: list[str],
        answers: dict[InterviewDimension, InterviewAnswer],
    ) -> CandidateProfileTask:
        interview_complete = set(answers) == set(
            REQUIRED_INTERVIEW_DIMENSIONS
        )
        return CandidateProfileTask(
            task_id=task_id,
            integration_commit=self.integration_commit,
            contract_version=self.contract_version,
            capability_paths=list(_CAPABILITIES),
            source_documents=source_documents,
            answers=answers,
            interview_complete=interview_complete,
        )

    @staticmethod
    def validate_task(payload: object) -> CandidateProfileTask:
        return CandidateProfileTask.model_validate(payload)

    @staticmethod
    def validate_answers(
        payload: object,
    ) -> dict[InterviewDimension, InterviewAnswer]:
        return InterviewAnswers.model_validate(payload).root

    def validate_result(
        self,
        payload: object,
        *,
        task: CandidateProfileTask,
    ) -> ProfileQuestions | ProfileProposalResult:
        result = _RESULT_ADAPTER.validate_python(
            payload,
            context={"task": task},
        )
        if result.task_id != task.task_id:
            raise ValueError("task id mismatch")
        return result
