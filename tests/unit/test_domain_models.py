from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain import (
    ApplicationPackage,
    ApplicationStatus,
    ApplyType,
    CandidateProfile,
    Job,
    JobEvaluation,
    JobSnapshot,
    MaterialArtifact,
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
