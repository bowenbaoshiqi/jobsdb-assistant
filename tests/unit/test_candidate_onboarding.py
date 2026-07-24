from datetime import UTC, datetime
from pathlib import Path

from src.adapters.candidate_profile import CandidateProfileAdapter
from src.adapters.checkpoint_io import CheckpointStore
from src.application.candidate_onboarding import (
    CandidateOnboarding,
    OnboardingStatus,
)
from src.domain.candidate import CandidateProfileProposal, FactEvidence
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def service(tmp_path: Path) -> CandidateOnboarding:
    database = Database(str(tmp_path / "jobs.db"))
    return CandidateOnboarding(
        profiles=CandidateRepository(database),
        adapter=CandidateProfileAdapter(
            "a" * 40,
            "candidate-profile.v1",
        ),
        checkpoints=CheckpointStore(tmp_path / "workspace" / "ai-tasks"),
    )


def proposal_payload(task_id: str, proposal_id: str = "proposal-1") -> dict:
    return {
        "kind": "proposal",
        "task_id": task_id,
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


def test_first_run_creates_task_then_waits_for_confirmation(
    tmp_path: Path,
) -> None:
    onboarding = service(tmp_path)

    outcome = onboarding.ensure_profile(
        run_id="run-1",
        source_documents=["workspace/candidate/cv.md"],
    )
    assert outcome.status is OnboardingStatus.WAITING_FOR_AGENT

    review = onboarding.submit_result(
        run_id="run-1",
        task_id=outcome.task_id,
        payload=proposal_payload(outcome.task_id),
    )
    assert review.status is OnboardingStatus.WAITING_FOR_USER
    assert onboarding.profiles.get_active() is None

    profile = onboarding.confirm("proposal-1", confirmed_at=NOW)
    assert profile.version == 1


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
        payload=proposal_payload(outcome.task_id, "proposal-2"),
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
        payload={
            "kind": "questions",
            "task_id": outcome.task_id,
            "questions": ["Which roles do you want?"],
        },
    )

    assert questions.status is OnboardingStatus.NEEDS_ANSWERS
    next_task = onboarding.submit_answers(
        run_id="run-1",
        source_documents=[],
        answers={"Which roles do you want?": "AI Architect"},
    )
    assert next_task.status is OnboardingStatus.WAITING_FOR_AGENT
