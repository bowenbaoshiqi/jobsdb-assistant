from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.adapters.candidate_profile import (
    CandidateProfileAdapter,
    ProfileProposalResult,
    ProfileQuestions,
)

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def test_candidate_task_uses_only_pinned_onboarding_capabilities() -> None:
    adapter = CandidateProfileAdapter(
        integration_commit="a" * 40,
        contract_version="candidate-profile.v1",
    )

    task = adapter.build_task(
        task_id="profile-run-1",
        source_documents=["workspace/candidate/cv.md"],
        answers={},
    )

    assert task.capability_paths == [
        ".claude/commands/setup.md",
        (
            ".claude/skills/job-application-assistant/"
            "01-candidate-profile.md"
        ),
        (
            ".claude/skills/job-application-assistant/"
            "02-behavioral-profile.md"
        ),
    ]
    assert "job-evaluation" not in " ".join(task.capability_paths)


def test_candidate_result_supports_questions_or_proposal() -> None:
    adapter = CandidateProfileAdapter("a" * 40, "candidate-profile.v1")

    questions = adapter.validate_result({
        "kind": "questions",
        "task_id": "profile-run-1",
        "questions": ["What role are you targeting?"],
    })
    assert isinstance(questions, ProfileQuestions)

    proposal = adapter.validate_result({
        "kind": "proposal",
        "task_id": "profile-run-1",
        "profile": {
            "id": "proposal-1",
            "verified_facts": {"skills": ["Python"]},
            "fact_evidence": {
                "Python": [{"source": "cv.md", "locator": "skills"}]
            },
            "target_roles": ["AI Architect"],
            "created_at": NOW.isoformat(),
        },
    })
    assert isinstance(proposal, ProfileProposalResult)


def test_candidate_adapter_rejects_fact_without_evidence() -> None:
    adapter = CandidateProfileAdapter("a" * 40, "candidate-profile.v1")

    with pytest.raises(ValidationError, match="verified fact lacks evidence"):
        adapter.validate_result({
            "kind": "proposal",
            "task_id": "profile-run-1",
            "profile": {
                "id": "proposal-1",
                "verified_facts": {"skills": ["Python"]},
                "fact_evidence": {},
                "created_at": NOW.isoformat(),
            },
        })
