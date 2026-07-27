from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain.material import (
    ApplicationPackage,
    MaterialArtifact,
    MaterialCheck,
    MaterialReviewAction,
    MaterialReviewEvent,
    MaterialReviewStatus,
    MaterialTaskStatus,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def artifact(name: str = "cv.pdf") -> MaterialArtifact:
    return MaterialArtifact(
        path=f"workspace/materials/job-1/v1/{name}",
        sha256="a" * 64,
    )


def package(**updates) -> ApplicationPackage:
    values = {
        "id": "material-job-1-v1",
        "job_id": "job-1",
        "evaluation_id": "evaluation-1",
        "profile_version": 2,
        "version": 1,
        "resume": artifact(),
        "cover_letter": artifact("cover-letter.txt"),
        "cover_letter_word_count": 180,
        "created_at": NOW,
    }
    values.update(updates)
    return ApplicationPackage(**values)


def test_material_status_values_are_stable() -> None:
    assert [status.value for status in MaterialTaskStatus] == [
        "waiting_for_agent",
        "generating",
        "generated",
        "failed",
    ]
    assert [status.value for status in MaterialReviewStatus] == [
        "pending_review",
        "pending_review_with_fact_warning",
        "approved",
        "approved_with_fact_override",
        "rejected",
        "superseded",
    ]


@pytest.mark.parametrize("word_count", [100, 300])
def test_cover_letter_accepts_inclusive_word_boundaries(
    word_count: int,
) -> None:
    assert package(cover_letter_word_count=word_count).cover_letter_word_count == (
        word_count
    )


@pytest.mark.parametrize("word_count", [99, 301])
def test_cover_letter_rejects_out_of_range_word_count(
    word_count: int,
) -> None:
    with pytest.raises(ValidationError):
        package(cover_letter_word_count=word_count)


def test_fact_findings_default_package_to_warning_review() -> None:
    result = package(
        facts=MaterialCheck(
            passed=False,
            findings=["Team size claim is not supported by the source CV."],
        )
    )

    assert (
        result.review_status
        is MaterialReviewStatus.PENDING_REVIEW_WITH_FACT_WARNING
    )
    assert result.facts.findings


def test_clean_package_defaults_to_pending_review() -> None:
    assert package().review_status is MaterialReviewStatus.PENDING_REVIEW


def test_material_artifact_requires_lowercase_sha256() -> None:
    with pytest.raises(ValidationError):
        MaterialArtifact(path="cv.pdf", sha256="A" * 64)


def test_fact_override_event_requires_explicit_override_state() -> None:
    event = MaterialReviewEvent(
        id="review-1",
        package_id="material-job-1-v1",
        action=MaterialReviewAction.APPROVE,
        resulting_status=MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE,
        fact_warning_overridden=True,
        created_at=NOW,
    )

    assert event.fact_warning_overridden is True

    with pytest.raises(ValidationError, match="fact warning override"):
        MaterialReviewEvent(
            id="review-2",
            package_id="material-job-1-v1",
            action=MaterialReviewAction.APPROVE,
            resulting_status=MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE,
            fact_warning_overridden=False,
            created_at=NOW,
        )
