from datetime import UTC, datetime
from pathlib import Path

from src.domain.candidate import CandidateProfileProposal, FactEvidence
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
