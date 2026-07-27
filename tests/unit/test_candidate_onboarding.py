from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.adapters.candidate_profile import CandidateProfileAdapter
from src.adapters.checkpoint_io import CheckpointStore
from src.application.candidate_onboarding import (
    CandidateOnboarding,
    OnboardingStatus,
)
from src.domain.candidate import CandidateProfileProposal, FactEvidence
from src.domain.candidate_interview import (
    REQUIRED_INTERVIEW_DIMENSIONS,
    InterviewDimension,
)
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def service(tmp_path: Path) -> CandidateOnboarding:
    database = Database(str(tmp_path / "jobs.db"))
    return CandidateOnboarding(
        profiles=CandidateRepository(database),
        adapter=CandidateProfileAdapter(
            "a" * 40,
            "candidate-profile.v2",
        ),
        checkpoints=CheckpointStore(tmp_path / "workspace" / "ai-tasks"),
    )


def proposal_payload(task_id: str, proposal_id: str = "proposal-1") -> dict:
    answers = complete_answers_payload()
    return {
        "kind": "proposal",
        "task_id": task_id,
        "canonical_cv": {
            "full_name": {
                "value": "Synthetic Candidate",
                "evidence": [{"source": "cv.md", "locator": "name"}],
            }
        },
        "intent_syntheses": [
            {
                "dimension": dimension.value,
                "answer_hash": sha256(
                    (
                        answer["value"]
                        if answer["status"] == "answered"
                        else answer["status"]
                    ).encode()
                ).hexdigest(),
                "summary": (
                    f"Synthesis for {dimension.value}"
                    if answer["status"] == "answered"
                    else None
                ),
                "target_field": dimension.value,
            }
            for dimension in REQUIRED_INTERVIEW_DIMENSIONS
            for answer in [answers[dimension.value]]
        ],
        "profile": {
            "id": proposal_id,
            "verified_facts": {"skills": ["Python"]},
            "fact_evidence": {
                "Python": [{"source": "cv.md", "locator": "skills"}]
            },
            "target_roles": ["AI Architect"],
            "created_at": NOW.isoformat(),
        },
    }


def questions_payload(task_id: str) -> dict:
    optional = {
        InterviewDimension.SALARY_EXPECTATIONS,
        InterviewDimension.REFERENCES,
    }
    return {
        "kind": "questions",
        "task_id": task_id,
        "questions": [
            {
                "dimension": dimension.value,
                "prompt": f"Question for {dimension.value}?",
                "optional": dimension in optional,
            }
            for dimension in REQUIRED_INTERVIEW_DIMENSIONS
        ],
    }


def complete_answers_payload() -> dict:
    return {
        dimension.value: (
            {"status": "not_provided"}
            if dimension is InterviewDimension.SALARY_EXPECTATIONS
            else {"status": "no_preference"}
            if dimension is InterviewDimension.REFERENCES
            else {
                "status": "answered",
                "value": f"Answer for {dimension.value}",
            }
        )
        for dimension in REQUIRED_INTERVIEW_DIMENSIONS
    }


def confirmed_proposal(proposal_id: str) -> CandidateProfileProposal:
    return CandidateProfileProposal(
        id=proposal_id,
        verified_facts={"skills": ["Python"]},
        fact_evidence={
            "Python": [FactEvidence(source="cv.md", locator="skills")]
        },
        target_roles=["AI Architect"],
        created_at=NOW,
    )


def test_first_cv_run_rejects_proposal_before_interview(
    tmp_path: Path,
) -> None:
    onboarding = service(tmp_path)

    outcome = onboarding.ensure_profile(
        run_id="run-1",
        source_documents=["workspace/candidate/cv.md"],
    )
    assert outcome.status is OnboardingStatus.WAITING_FOR_AGENT

    with pytest.raises(
        ValidationError,
        match="interview must be completed before proposal",
    ):
        onboarding.submit_result(
            run_id="run-1",
            task_id=outcome.task_id,
            payload=proposal_payload(outcome.task_id),
        )

    assert onboarding.profiles.get_active() is None
    result_path = (
        tmp_path
        / "workspace"
        / "ai-tasks"
        / outcome.task_id
        / "result.json"
    )
    assert not result_path.exists()


def test_complete_interview_then_proposal_can_be_confirmed(
    tmp_path: Path,
) -> None:
    onboarding = service(tmp_path)
    first = onboarding.ensure_profile("run-1", ["cv.pdf"])

    questions = onboarding.submit_result(
        "run-1",
        first.task_id,
        questions_payload(first.task_id),
    )
    assert questions.status is OnboardingStatus.NEEDS_ANSWERS
    assert len(questions.questions) == len(
        REQUIRED_INTERVIEW_DIMENSIONS
    )

    follow_up = onboarding.submit_answers(
        "run-1",
        ["cv.pdf"],
        complete_answers_payload(),
    )
    follow_up_task = onboarding.checkpoints.read_task(follow_up.task_id)
    assert follow_up_task["interview_complete"] is True
    assert follow_up_task["answers"]["salary_expectations"] == {
        "status": "not_provided",
        "value": None,
    }

    review = onboarding.submit_result(
        "run-1",
        follow_up.task_id,
        proposal_payload(follow_up.task_id),
    )
    assert review.status is OnboardingStatus.WAITING_FOR_USER
    profile = onboarding.confirm("proposal-1", confirmed_at=NOW)
    assert profile.version == 1
    assert profile.canonical_cv is not None
    assert profile.canonical_cv.full_name is not None
    assert profile.canonical_cv.full_name.value == "Synthetic Candidate"
    assert profile.interview_answers[
        InterviewDimension.CAREER_GOALS
    ].value == "Answer for career_goals"


def test_later_run_reuses_active_profile_without_new_task(
    tmp_path: Path,
) -> None:
    onboarding = service(tmp_path)
    onboarding.profiles.create_proposal(
        "run-1",
        confirmed_proposal("proposal-1"),
    )
    onboarding.profiles.confirm("proposal-1", confirmed_at=NOW)

    outcome = onboarding.ensure_profile(
        run_id="run-2",
        source_documents=[],
    )

    assert outcome.status is OnboardingStatus.READY
    assert outcome.profile_version == 1
    assert outcome.task_id is None


def test_explicit_update_creates_new_task_and_v2(tmp_path: Path) -> None:
    onboarding = service(tmp_path)
    onboarding.profiles.create_proposal(
        "run-1",
        confirmed_proposal("proposal-1"),
    )
    onboarding.profiles.confirm("proposal-1", confirmed_at=NOW)

    outcome = onboarding.ensure_profile(
        run_id="run-2",
        source_documents=["workspace/candidate/new-cv.md"],
        update=True,
    )
    onboarding.submit_result(
        run_id="run-2",
        task_id=outcome.task_id,
        payload=questions_payload(outcome.task_id),
    )
    follow_up = onboarding.submit_answers(
        "run-2",
        ["workspace/candidate/new-cv.md"],
        complete_answers_payload(),
    )
    onboarding.submit_result(
        run_id="run-2",
        task_id=follow_up.task_id,
        payload=proposal_payload(follow_up.task_id, "proposal-2"),
    )
    profile = onboarding.confirm("proposal-2", confirmed_at=NOW)

    assert profile.version == 2
    assert len(onboarding.profiles.versions()) == 2


def test_questions_remain_an_agent_checkpoint(tmp_path: Path) -> None:
    onboarding = service(tmp_path)
    outcome = onboarding.ensure_profile("run-1", [])

    questions = onboarding.submit_result(
        run_id="run-1",
        task_id=outcome.task_id,
        payload=questions_payload(outcome.task_id),
    )

    assert questions.status is OnboardingStatus.NEEDS_ANSWERS
    next_task = onboarding.submit_answers(
        run_id="run-1",
        source_documents=[],
        answers=complete_answers_payload(),
    )
    assert next_task.status is OnboardingStatus.WAITING_FOR_AGENT
