from datetime import UTC, datetime
from hashlib import sha256

import pytest
from pydantic import ValidationError

from src.adapters.candidate_profile import (
    CandidateProfileAdapter,
    ProfileProposalResult,
    ProfileQuestions,
)
from src.domain.candidate_interview import (
    REQUIRED_INTERVIEW_DIMENSIONS,
    InterviewDimension,
)

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def adapter() -> CandidateProfileAdapter:
    return CandidateProfileAdapter("a" * 40, "candidate-profile.v2")


def complete_questions() -> list[dict[str, object]]:
    optional = {
        InterviewDimension.SALARY_EXPECTATIONS,
        InterviewDimension.REFERENCES,
    }
    return [
        {
            "dimension": dimension.value,
            "prompt": f"Question for {dimension.value}?",
            "optional": dimension in optional,
        }
        for dimension in REQUIRED_INTERVIEW_DIMENSIONS
    ]


def complete_answers() -> dict[str, dict[str, str]]:
    return {
        dimension.value: {
            "status": (
                "not_provided"
                if dimension is InterviewDimension.SALARY_EXPECTATIONS
                else "no_preference"
                if dimension is InterviewDimension.REFERENCES
                else "answered"
            ),
            **(
                {"value": f"Answer for {dimension.value}"}
                if dimension
                not in {
                    InterviewDimension.SALARY_EXPECTATIONS,
                    InterviewDimension.REFERENCES,
                }
                else {}
            ),
        }
        for dimension in REQUIRED_INTERVIEW_DIMENSIONS
    }


def proposal_payload(task_id: str) -> dict:
    answers = complete_answers()
    return {
        "kind": "proposal",
        "task_id": task_id,
        "canonical_cv": {
            "full_name": {
                "value": "Synthetic Candidate",
                "evidence": [
                    {"source": "cv.pdf", "locator": "page 1"}
                ],
            },
            "experience": [
                {
                    "role": {
                        "value": "AI Architect",
                        "evidence": [
                            {"source": "cv.pdf", "locator": "experience"}
                        ],
                    },
                    "company": {
                        "value": "Example Group",
                        "evidence": [
                            {"source": "cv.pdf", "locator": "experience"}
                        ],
                    },
                    "period": {
                        "value": "2022-present",
                        "evidence": [
                            {"source": "cv.pdf", "locator": "experience"}
                        ],
                    },
                }
            ],
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
            "id": "proposal-1",
            "verified_facts": {"skills": ["Python"]},
            "fact_evidence": {
                "Python": [{"source": "cv.md", "locator": "skills"}]
            },
            "target_roles": ["AI Architect"],
            "created_at": NOW.isoformat(),
        },
    }


def test_candidate_task_uses_only_pinned_onboarding_capabilities() -> None:
    candidate_adapter = adapter()

    task = candidate_adapter.build_task(
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
    assert task.interview_complete is False


def test_first_task_requires_all_typed_interview_questions() -> None:
    candidate_adapter = adapter()
    task = candidate_adapter.build_task(
        "profile-run-1",
        ["workspace/candidate/cv.md"],
        {},
    )

    questions = candidate_adapter.validate_result(
        {
            "kind": "questions",
            "task_id": task.task_id,
            "questions": complete_questions(),
        },
        task=task,
    )

    assert isinstance(questions, ProfileQuestions)
    assert {item.dimension for item in questions.questions} == set(
        REQUIRED_INTERVIEW_DIMENSIONS
    )


def test_first_task_rejects_immediate_proposal() -> None:
    candidate_adapter = adapter()
    task = candidate_adapter.build_task("profile-run-1", ["cv.pdf"], {})

    with pytest.raises(
        ValidationError,
        match="interview must be completed before proposal",
    ):
        candidate_adapter.validate_result(
            proposal_payload(task.task_id),
            task=task,
        )


@pytest.mark.parametrize(
    "questions, error",
    [
        (
            complete_questions()[:-1],
            "questions must cover every required interview dimension",
        ),
        (
            complete_questions() + [complete_questions()[0]],
            "questions must cover every required interview dimension",
        ),
        (
            [
                *complete_questions()[:-1],
                {
                    "dimension": "favorite_colour",
                    "prompt": "What is your favorite colour?",
                    "optional": False,
                },
            ],
            "favorite_colour",
        ),
    ],
)
def test_first_task_rejects_invalid_question_coverage(
    questions: list[dict[str, object]],
    error: str,
) -> None:
    candidate_adapter = adapter()
    task = candidate_adapter.build_task("profile-run-1", ["cv.pdf"], {})

    with pytest.raises(ValidationError, match=error):
        candidate_adapter.validate_result(
            {
                "kind": "questions",
                "task_id": task.task_id,
                "questions": questions,
            },
            task=task,
        )


def test_answers_require_every_dimension() -> None:
    payload = complete_answers()
    payload.pop(InterviewDimension.REFERENCES.value)

    with pytest.raises(
        ValidationError,
        match="answers must cover every required interview dimension",
    ):
        adapter().validate_answers(payload)


def test_answered_status_requires_non_empty_value() -> None:
    payload = complete_answers()
    payload[InterviewDimension.CAREER_GOALS.value] = {
        "status": "answered",
        "value": " ",
    }

    with pytest.raises(
        ValidationError,
        match="answered interview value must not be empty",
    ):
        adapter().validate_answers(payload)


def test_explicit_skip_answers_complete_interview() -> None:
    candidate_adapter = adapter()
    answers = candidate_adapter.validate_answers(complete_answers())
    task = candidate_adapter.build_task(
        "profile-run-1-answers",
        ["cv.pdf"],
        answers,
    )

    assert task.interview_complete is True
    assert task.answers[
        InterviewDimension.SALARY_EXPECTATIONS
    ].status.value == "not_provided"
    assert task.answers[
        InterviewDimension.REFERENCES
    ].status.value == "no_preference"

    proposal = candidate_adapter.validate_result(
        proposal_payload(task.task_id),
        task=task,
    )
    assert isinstance(proposal, ProfileProposalResult)
    assert proposal.profile.canonical_cv is not None
    assert proposal.profile.interview_answers == task.answers
    assert len(proposal.profile.intent_syntheses) == len(
        REQUIRED_INTERVIEW_DIMENSIONS
    )


def test_agent_cannot_replace_raw_interview_answers() -> None:
    candidate_adapter = adapter()
    answers = candidate_adapter.validate_answers(complete_answers())
    task = candidate_adapter.build_task(
        "profile-run-raw-answers",
        ["cv.pdf"],
        answers,
    )
    payload = proposal_payload(task.task_id)
    payload["profile"]["interview_answers"] = {
        InterviewDimension.CAREER_GOALS.value: {
            "status": "answered",
            "value": "Agent replacement",
        }
    }

    proposal = candidate_adapter.validate_result(payload, task=task)

    assert isinstance(proposal, ProfileProposalResult)
    assert proposal.profile.interview_answers == task.answers
    assert (
        proposal.profile.interview_answers[
            InterviewDimension.CAREER_GOALS
        ].value
        == "Answer for career_goals"
    )


def test_proposal_rejects_missing_intent_synthesis() -> None:
    candidate_adapter = adapter()
    task = candidate_adapter.build_task(
        "profile-run-incomplete-synthesis",
        ["cv.pdf"],
        candidate_adapter.validate_answers(complete_answers()),
    )
    payload = proposal_payload(task.task_id)
    payload["intent_syntheses"].pop()

    with pytest.raises(ValueError, match="intent synthesis coverage"):
        candidate_adapter.validate_result(payload, task=task)


def test_candidate_adapter_rejects_fact_without_evidence() -> None:
    candidate_adapter = adapter()
    task = candidate_adapter.build_task(
        "profile-run-1-answers",
        ["cv.pdf"],
        candidate_adapter.validate_answers(complete_answers()),
    )

    with pytest.raises(ValidationError, match="verified fact lacks evidence"):
        candidate_adapter.validate_result(
            {
                "kind": "proposal",
                "task_id": task.task_id,
                "canonical_cv": proposal_payload(task.task_id)[
                    "canonical_cv"
                ],
                "intent_syntheses": proposal_payload(task.task_id)[
                    "intent_syntheses"
                ],
                "profile": {
                    "id": "proposal-1",
                    "verified_facts": {"skills": ["Python"]},
                    "fact_evidence": {},
                    "created_at": NOW.isoformat(),
                },
            },
            task=task,
        )
