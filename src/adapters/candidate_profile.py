"""Adapter contract for pinned ai-job-search onboarding guidance."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    model_validator,
)

from src.domain.candidate import CandidateProfileProposal

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
    answers: dict[str, str]


class ProfileQuestions(BaseModel):
    kind: Literal["questions"]
    task_id: str
    questions: list[str] = Field(min_length=1, max_length=12)


class ProfileProposalResult(BaseModel):
    kind: Literal["proposal"]
    task_id: str
    profile: CandidateProfileProposal

    @model_validator(mode="after")
    def require_fact_evidence(self) -> "ProfileProposalResult":
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
        answers: dict[str, str],
    ) -> CandidateProfileTask:
        return CandidateProfileTask(
            task_id=task_id,
            integration_commit=self.integration_commit,
            contract_version=self.contract_version,
            capability_paths=list(_CAPABILITIES),
            source_documents=source_documents,
            answers=answers,
        )

    def validate_result(
        self,
        payload: object,
    ) -> ProfileQuestions | ProfileProposalResult:
        return _RESULT_ADAPTER.validate_python(payload)
