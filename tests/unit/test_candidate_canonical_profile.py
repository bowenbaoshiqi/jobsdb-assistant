from datetime import UTC, datetime
from hashlib import sha256

import pytest
from pydantic import ValidationError

from src.domain.candidate import CandidateProfile
from src.domain.candidate_cv import (
    CandidateCv,
    CandidateExperience,
    FactEvidence,
    IntentSynthesis,
    IntentTargetField,
    SourcedText,
    validate_intent_syntheses,
)
from src.domain.candidate_interview import (
    InterviewAnswer,
    InterviewAnswerStatus,
    InterviewDimension,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def evidence(locator: str = "page 1") -> tuple[FactEvidence, ...]:
    return (
        FactEvidence(source="candidate/resume.pdf", locator=locator),
    )


def sourced(value: str, locator: str = "page 1") -> SourcedText:
    return SourcedText(value=value, evidence=evidence(locator))


def answer_hash(answer: InterviewAnswer) -> str:
    payload = (
        answer.value
        if answer.status is InterviewAnswerStatus.ANSWERED
        else answer.status.value
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def test_sourced_text_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        SourcedText(value="Built an AI platform", evidence=())


def test_candidate_cv_keeps_ordered_evidence_backed_experience() -> None:
    cv = CandidateCv(
        full_name=sourced("Synthetic Candidate", "header"),
        headline=sourced("AI Architect", "summary"),
        experience=(
            CandidateExperience(
                role=sourced("AI Architect", "experience 1"),
                company=sourced("Example Corp", "experience 1"),
                period=sourced("2025-present", "experience 1"),
                bullets=(
                    sourced("Built an enterprise AI platform", "bullet 1"),
                ),
            ),
        ),
    )

    assert cv.experience[0].company.value == "Example Corp"
    assert cv.experience[0].bullets[0].evidence[0].locator == "bullet 1"


def test_answered_intent_requires_matching_hash() -> None:
    answer = InterviewAnswer(
        status=InterviewAnswerStatus.ANSWERED,
        value="Large companies",
    )
    synthesis = IntentSynthesis(
        dimension=InterviewDimension.MUST_HAVES,
        answer_hash="0" * 64,
        summary="Prefers mature large organizations.",
        target_field=IntentTargetField.MUST_HAVES,
    )

    with pytest.raises(ValueError, match="answer hash mismatch"):
        validate_intent_syntheses(
            {InterviewDimension.MUST_HAVES: answer},
            (synthesis,),
        )


def test_answered_intent_requires_non_empty_synthesis() -> None:
    answer = InterviewAnswer(
        status=InterviewAnswerStatus.ANSWERED,
        value="Large companies",
    )
    synthesis = IntentSynthesis(
        dimension=InterviewDimension.MUST_HAVES,
        answer_hash=answer_hash(answer),
        summary=None,
        target_field=IntentTargetField.MUST_HAVES,
    )

    with pytest.raises(ValueError, match="answered intent requires synthesis"):
        validate_intent_syntheses(
            {InterviewDimension.MUST_HAVES: answer},
            (synthesis,),
        )


def test_intent_synthesis_requires_exact_dimension_coverage() -> None:
    answers = {
        InterviewDimension.MUST_HAVES: InterviewAnswer(
            status=InterviewAnswerStatus.ANSWERED,
            value="Large companies",
        ),
        InterviewDimension.REFERENCES: InterviewAnswer(
            status=InterviewAnswerStatus.NOT_PROVIDED,
        ),
    }
    synthesis = IntentSynthesis(
        dimension=InterviewDimension.MUST_HAVES,
        answer_hash=answer_hash(answers[InterviewDimension.MUST_HAVES]),
        summary="Prefers mature large organizations.",
        target_field=IntentTargetField.MUST_HAVES,
    )

    with pytest.raises(ValueError, match="intent synthesis coverage"):
        validate_intent_syntheses(answers, (synthesis,))


def test_explicit_skip_status_is_preserved_without_summary() -> None:
    answer = InterviewAnswer(
        status=InterviewAnswerStatus.NOT_PROVIDED,
    )
    synthesis = IntentSynthesis(
        dimension=InterviewDimension.SALARY_EXPECTATIONS,
        answer_hash=answer_hash(answer),
        summary=None,
        target_field=IntentTargetField.SALARY_EXPECTATIONS,
    )

    validated = validate_intent_syntheses(
        {InterviewDimension.SALARY_EXPECTATIONS: answer},
        (synthesis,),
    )

    assert validated[0].summary is None


def test_legacy_profile_json_remains_readable() -> None:
    profile = CandidateProfile.model_validate({
        "id": "profile-1",
        "version": 1,
        "verified_facts": {"skills": ["Python"]},
        "fact_evidence": {
            "Python": [
                {"source": "candidate/resume.pdf", "locator": "skills"}
            ]
        },
        "target_roles": ["AI Architect"],
        "created_at": NOW.isoformat(),
        "confirmed_at": NOW.isoformat(),
        "content_hash": "a" * 64,
    })

    assert profile.canonical_cv is None
    assert profile.interview_answers == {}
    assert profile.intent_syntheses == ()
