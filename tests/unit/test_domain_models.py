from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain import (
    ApplicationPackage,
    ApplicationStatus,
    ApplyType,
    CandidateProfile,
    FactEvidence,
    Job,
    JobEvaluation,
    JobSnapshot,
    MaterialArtifact,
    NativeDimension,
)

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def test_candidate_profile_preserves_verified_fact_sources() -> None:
    profile = CandidateProfile(
        version=1,
        verified_facts={"python": ["cv:skills"]},
        target_roles=["Backend Engineer"],
        created_at=NOW,
    )

    assert profile.version == 1
    assert profile.verified_facts["python"] == ["cv:skills"]


def test_job_keeps_apply_type_separate_from_execution_status() -> None:
    job = Job(
        jobsdb_job_id="123",
        canonical_url="https://hk.jobsdb.com/job/123",
        title="Backend Engineer",
        company="Synthetic Ltd",
        apply_type=ApplyType.APPLY,
        first_seen=NOW,
        last_seen=NOW,
    )

    assert job.apply_type is ApplyType.APPLY
    assert ApplicationStatus.MANUAL_APPLY_READY.value == "manual_apply_ready"


def test_snapshot_requires_sha256_content_hash() -> None:
    with pytest.raises(ValidationError):
        JobSnapshot(
            job_id="123",
            jd_text="Synthetic JD",
            content_hash="short",
            captured_at=NOW,
        )


def test_evaluation_score_is_bounded() -> None:
    with pytest.raises(ValidationError):
        JobEvaluation(
            job_snapshot_id="snapshot-1",
            profile_version=1,
            engine_version="career-ops@pinned",
            prompt_version="evaluation@1",
            overall_score=5.1,
            recommendation="apply",
        )


def test_confirmed_profile_is_frozen_and_preserves_evidence() -> None:
    profile = CandidateProfile(
        id="profile-1",
        version=1,
        verified_facts={"skills": ["Python"]},
        fact_evidence={
            "Python": [FactEvidence(source="cv.md", locator="skills")]
        },
        target_roles=["AI Architect"],
        created_at=NOW,
        confirmed_at=NOW,
        content_hash="a" * 64,
    )

    assert profile.fact_evidence["Python"][0].source == "cv.md"
    with pytest.raises(ValidationError):
        profile.target_roles = ["Other"]


def test_native_evaluation_requires_ordered_a_through_f_once() -> None:
    dimensions = [
        NativeDimension(
            code=code,
            title=f"Block {code}",
            score=4.0,
            findings=["Synthetic fit"],
            evidence=["JD: synthetic requirement"],
        )
        for code in "ABCDEF"
    ]

    evaluation = JobEvaluation(
        id="evaluation-1",
        job_snapshot_id="snapshot-1",
        profile_version=1,
        profile_hash="a" * 64,
        snapshot_hash="b" * 64,
        engine_version="career-ops@01bf8b4",
        engine_commit="c" * 40,
        prompt_version="career-ops-native-af.v1",
        overall_score=4.2,
        dimensions=dimensions,
        recommendation="strong_apply",
        created_at=NOW,
    )

    assert [dimension.code for dimension in evaluation.dimensions] == list(
        "ABCDEF"
    )

    with pytest.raises(ValidationError, match="A through F"):
        evaluation.model_copy(
            update={"dimensions": dimensions[:-1]},
        ).model_validate(
            {
                **evaluation.model_dump(),
                "dimensions": [
                    dimension.model_dump() for dimension in dimensions[:-1]
                ],
            }
        )

    with pytest.raises(ValidationError, match="A through F"):
        JobEvaluation(
            **{
                **evaluation.model_dump(),
                "dimensions": [],
            }
        )


def test_application_package_requires_english_cover_letter_word_range() -> None:
    resume = MaterialArtifact(
        path="workspace/applications/123/v1/resume.pdf",
        sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        ApplicationPackage(
            job_id="123",
            evaluation_id="evaluation-1",
            profile_version=1,
            version=1,
            resume=resume,
            cover_letter=resume,
            cover_letter_word_count=99,
        )
