from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domain.evaluation import (
    EvaluationCacheKey,
    JobEvaluation,
    NativeDimension,
)
from src.domain.job import ApplyType, JobDetailCapture
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def cache_key(snapshot_hash: str) -> EvaluationCacheKey:
    return EvaluationCacheKey(
        snapshot_hash=snapshot_hash,
        profile_hash="a" * 64,
        profile_bundle_hash="d" * 64,
        profile_projection_version="career-ops-profile-bundle.v1",
        engine_commit="b" * 40,
        contract_version="career-ops-native-af.v1",
    )


def evaluation(snapshot_id: str) -> JobEvaluation:
    return JobEvaluation(
        id=f"evaluation-{snapshot_id}",
        job_snapshot_id=snapshot_id,
        profile_version=1,
        profile_hash="a" * 64,
        snapshot_hash="c" * 64,
        engine_version="career-ops@01bf8b4",
        engine_commit="b" * 40,
        prompt_version="career-ops-native-af.v1",
        overall_score=4.2,
        dimensions=[
            NativeDimension(
                code=code,
                title=f"Block {code}",
                score=4.0,
                findings=["Synthetic finding"],
                evidence=["JD: synthetic evidence"],
            )
            for code in "ABCDEF"
        ],
        recommendation="strong_apply",
        strengths=["Relevant architecture experience"],
        gaps=["Synthetic gap"],
        risks=["Synthetic risk"],
        evidence=["JD: synthetic evidence"],
        created_at=NOW,
    )


def repository(tmp_path: Path) -> tuple[EvaluationRepository, str, str]:
    database = Database(str(tmp_path / "jobs.db"))
    capture = JobDetailCapture(
        jobsdb_job_id="job-1",
        canonical_url="https://hk.jobsdb.com/job/job-1",
        title="AI Architect",
        company="Synthetic Ltd",
        location="Hong Kong",
        jd_text="First synthetic JD",
        apply_type=ApplyType.QUICK_APPLY,
    )
    database.save_discovered_job(capture, captured_at=NOW)
    first = database.get_current_job_snapshot_record("job-1")
    assert first is not None
    capture.jd_text = "Changed synthetic JD"
    database.save_discovered_job(capture, captured_at=NOW)
    second = database.get_current_job_snapshot_record("job-1")
    assert second is not None
    return EvaluationRepository(database), first.snapshot_id, second.snapshot_id


def test_exact_cache_key_reuses_immutable_evaluation(tmp_path: Path) -> None:
    repo, first_snapshot_id, _second_snapshot_id = repository(tmp_path)
    key = cache_key("1" * 64)
    expected = evaluation(first_snapshot_id)

    repo.save(expected, key)

    assert repo.find_by_cache_key(key) == expected
    with pytest.raises(ValueError, match="evaluation cache key already exists"):
        repo.save(evaluation(first_snapshot_id), key)


def test_changed_snapshot_has_cache_miss(tmp_path: Path) -> None:
    repo, first_snapshot_id, _second_snapshot_id = repository(tmp_path)
    repo.save(evaluation(first_snapshot_id), cache_key("1" * 64))

    assert repo.find_by_cache_key(cache_key("2" * 64)) is None


def test_list_current_returns_only_current_profile_and_snapshot(
    tmp_path: Path,
) -> None:
    repo, first_snapshot_id, second_snapshot_id = repository(tmp_path)
    repo.save(evaluation(first_snapshot_id), cache_key("1" * 64))
    current = evaluation(second_snapshot_id)
    repo.save(current, cache_key("2" * 64))

    assert repo.list_current(profile_version=1) == [current]
    assert repo.list_current(profile_version=2) == []
