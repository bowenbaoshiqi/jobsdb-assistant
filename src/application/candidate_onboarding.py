"""First-run and explicit-update candidate profile flow."""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256

from src.adapters.candidate_profile import (
    CandidateProfileAdapter,
    ProfileProposalResult,
    ProfileQuestions,
)
from src.adapters.checkpoint_io import CheckpointStore
from src.domain.candidate import CandidateProfile
from src.domain.candidate_interview import (
    InterviewAnswer,
    InterviewDimension,
    InterviewQuestion,
)
from src.storage.candidate_repository import CandidateRepository


class OnboardingStatus(str, Enum):
    READY = "ready"
    WAITING_FOR_AGENT = "waiting_for_agent"
    NEEDS_ANSWERS = "needs_answers"
    WAITING_FOR_USER = "waiting_for_user"


@dataclass(frozen=True)
class OnboardingOutcome:
    status: OnboardingStatus
    profile_version: int | None = None
    task_id: str | None = None
    proposal_id: str | None = None
    questions: tuple[InterviewQuestion, ...] = ()


class CandidateOnboarding:
    def __init__(
        self,
        profiles: CandidateRepository,
        adapter: CandidateProfileAdapter,
        checkpoints: CheckpointStore,
    ) -> None:
        self.profiles = profiles
        self.adapter = adapter
        self.checkpoints = checkpoints

    @staticmethod
    def _task_id(run_id: str, suffix: str = "") -> str:
        digest = sha256(run_id.encode("utf-8")).hexdigest()[:12]
        return f"profile-{digest}{suffix}"

    def ensure_profile(
        self,
        run_id: str,
        source_documents: list[str],
        *,
        update: bool = False,
    ) -> OnboardingOutcome:
        active = self.profiles.get_active()
        if active is not None and not update:
            return OnboardingOutcome(
                status=OnboardingStatus.READY,
                profile_version=active.version,
            )
        return self._create_task(
            run_id,
            source_documents,
            answers={},
        )

    def _create_task(
        self,
        run_id: str,
        source_documents: list[str],
        answers: dict[InterviewDimension, InterviewAnswer],
    ) -> OnboardingOutcome:
        suffix = "-answers" if answers else ""
        task = self.adapter.build_task(
            self._task_id(run_id, suffix),
            source_documents,
            answers,
        )
        self.checkpoints.write_task(
            task.task_id,
            task.model_dump(mode="json"),
        )
        return OnboardingOutcome(
            status=OnboardingStatus.WAITING_FOR_AGENT,
            task_id=task.task_id,
        )

    def submit_result(
        self,
        run_id: str,
        task_id: str,
        payload: dict,
    ) -> OnboardingOutcome:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        task = self.adapter.validate_task(
            self.checkpoints.read_task(task_id)
        )
        result = self.adapter.validate_result(payload, task=task)
        self.checkpoints.submit_result(task_id, encoded)
        if isinstance(result, ProfileQuestions):
            return OnboardingOutcome(
                status=OnboardingStatus.NEEDS_ANSWERS,
                task_id=task_id,
                questions=tuple(result.questions),
            )
        if not isinstance(result, ProfileProposalResult):
            raise TypeError("unsupported profile checkpoint result")
        self.profiles.create_proposal(run_id, result.profile)
        return OnboardingOutcome(
            status=OnboardingStatus.WAITING_FOR_USER,
            task_id=task_id,
            proposal_id=result.profile.id,
        )

    def submit_answers(
        self,
        run_id: str,
        source_documents: list[str],
        answers: dict,
    ) -> OnboardingOutcome:
        validated = self.adapter.validate_answers(answers)
        return self._create_task(
            run_id,
            source_documents,
            validated,
        )

    def confirm(
        self,
        proposal_id: str,
        *,
        confirmed_at: datetime,
    ) -> CandidateProfile:
        return self.profiles.confirm(
            proposal_id,
            confirmed_at=confirmed_at,
        )
