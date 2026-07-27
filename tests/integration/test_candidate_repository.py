from datetime import UTC, datetime
from pathlib import Path

from src.domain.candidate import CandidateProfileProposal, FactEvidence
from src.domain.candidate_cv import (
    CandidateCv,
    IntentSynthesis,
    IntentTargetField,
    SourcedText,
    interview_answer_hash,
)
from src.domain.candidate_interview import (
    InterviewAnswer,
    InterviewAnswerStatus,
    InterviewDimension,
)
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def proposal(proposal_id: str, skill: str) -> CandidateProfileProposal:
    return CandidateProfileProposal(
        id=proposal_id,
        verified_facts={"skills": [skill]},
        fact_evidence={
            skill: [FactEvidence(source="synthetic-cv.md", locator="skills")]
        },
        target_roles=["AI Architect"],
        created_at=NOW,
    )


def complete_proposal() -> CandidateProfileProposal:
    evidence = (FactEvidence(source="synthetic-cv.md", locator="work"),)
    answer = InterviewAnswer(
        status=InterviewAnswerStatus.ANSWERED,
        value="I want an AI Architect role in a mature large organization.",
    )
    synthesis = IntentSynthesis(
        dimension=InterviewDimension.CAREER_GOALS,
        answer_hash=interview_answer_hash(answer),
        summary="Target AI architecture roles at mature large organizations.",
        target_field=IntentTargetField.CAREER_GOALS,
        target_roles=("AI Architect",),
        culture_requirements=("Mature large organization",),
    )
    return CandidateProfileProposal(
        id="proposal-complete",
        canonical_cv=CandidateCv(
            full_name=SourcedText(
                value="Synthetic Candidate",
                evidence=evidence,
            ),
            experience=(
                {
                    "role": {
                        "value": "AI Architect",
                        "evidence": evidence,
                    },
                    "company": {
                        "value": "Example Group",
                        "evidence": evidence,
                    },
                    "period": {
                        "value": "2022-present",
                        "evidence": evidence,
                    },
                },
            ),
        ),
        interview_answers={
            InterviewDimension.CAREER_GOALS: answer,
        },
        intent_syntheses=(synthesis,),
        created_at=NOW,
    )


def repository(tmp_path: Path) -> CandidateRepository:
    database = Database(str(tmp_path / "jobs.db"))
    with database._connect() as conn:
        conn.execute(
            "INSERT INTO workflow_runs "
            "(id, keyword, stage, condition, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "AI Architect",
                "profile_task_ready",
                "waiting_for_user",
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    return CandidateRepository(database)


def test_confirm_creates_next_version_without_overwriting_v1(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)

    first_proposal = repo.create_proposal("run-1", proposal("proposal-1", "Python"))
    first = repo.confirm(first_proposal.id, confirmed_at=NOW)
    second_proposal = repo.create_proposal("run-1", proposal("proposal-2", "Go"))
    second = repo.confirm(second_proposal.id, confirmed_at=NOW)

    assert (first.version, second.version) == (1, 2)
    assert repo.versions()[0].verified_facts["skills"] == ["Python"]
    assert repo.get_active().version == 2


def test_unconfirmed_proposal_never_becomes_active(tmp_path: Path) -> None:
    repo = repository(tmp_path)

    repo.create_proposal("run-1", proposal("proposal-1", "Python"))

    assert repo.get_active() is None


def test_confirm_preserves_canonical_cv_and_exact_interview_answers(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    pending = repo.create_proposal("run-1", complete_proposal())

    repo.confirm(pending.id, confirmed_at=NOW)
    active = repo.get_active()

    assert active is not None
    assert active.canonical_cv is not None
    assert active.canonical_cv.experience[0].company.value == "Example Group"
    assert (
        active.interview_answers[
            InterviewDimension.CAREER_GOALS
        ].value
        == "I want an AI Architect role in a mature large organization."
    )
    assert active.intent_syntheses[0].target_roles == ("AI Architect",)
