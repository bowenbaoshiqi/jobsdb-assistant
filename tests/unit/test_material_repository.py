from datetime import UTC, datetime, timedelta

import pytest

from src.domain.job import ApplyType, JobDetailCapture
from src.domain.material import (
    ApplicationPackage,
    MaterialArtifact,
    MaterialCheck,
    MaterialReviewAction,
    MaterialReviewStatus,
    MaterialTaskStatus,
)
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository

NOW = datetime(2026, 7, 27, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


def _repository() -> tuple[MaterialRepository, int]:
    database = Database(":memory:")
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id="job-1",
            canonical_url="https://hk.jobsdb.com/job/job-1",
            title="Head of AI",
            company="Example Corporation",
            location="Hong Kong",
            jd_text="Lead enterprise AI.",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )
    snapshot = database.get_current_job_snapshot_record("job-1")
    assert snapshot is not None
    return MaterialRepository(database), int(snapshot.snapshot_id)


def _package(version: int, *, facts_passed: bool = True) -> ApplicationPackage:
    return ApplicationPackage(
        id=f"package-{version}",
        job_id="job-1",
        evaluation_id="evaluation-1",
        profile_version=1,
        version=version,
        resume=MaterialArtifact(path=f"cv-v{version}.pdf", sha256=HASH_A),
        cover_letter=MaterialArtifact(
            path=f"cover-v{version}.txt",
            sha256=HASH_B,
        ),
        cover_letter_word_count=120,
        reviewer=MaterialCheck(),
        ats=MaterialCheck(passed=False, findings=["Add one keyword"]),
        facts=MaterialCheck(
            passed=facts_passed,
            findings=[] if facts_passed else ["Unsupported team size"],
        ),
        created_at=NOW,
    )


def test_tasks_are_idempotent_and_fail_independently() -> None:
    repository, snapshot_id = _repository()
    first = repository.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=snapshot_id,
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={"job_id": "job-1"},
        created_at=NOW,
    )
    repeated = repository.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=snapshot_id,
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={"job_id": "job-1"},
        created_at=NOW,
    )

    assert repeated == first
    assert repository.start_task("task-1", started_at=NOW).status is (
        MaterialTaskStatus.GENERATING
    )
    failed = repository.fail_task(
        "task-1",
        error_message="invalid result",
        completed_at=NOW + timedelta(seconds=1),
    )
    assert failed.status is MaterialTaskStatus.FAILED
    assert failed.error_message == "invalid result"
    assert [task.id for task in repository.list_batch("batch-1")] == ["task-1"]


def test_packages_are_immutable_versioned_and_only_one_is_current() -> None:
    repository, snapshot_id = _repository()
    for version in (1, 2):
        repository.create_task(
            task_id=f"task-{version}",
            batch_id="batch-1",
            job_id="job-1",
            snapshot_id=snapshot_id,
            profile_version=1,
            evaluation_id="evaluation-1",
            target_version=version,
            payload={"version": version},
            created_at=NOW,
        )
        repository.save_package(
            task_id=f"task-{version}",
            package=_package(version),
            saved_at=NOW,
        )

    assert [item.version for item in repository.list_versions("job-1")] == [2, 1]
    assert repository.latest_for_job("job-1").version == 2
    with pytest.raises(ValueError, match="immutable"):
        repository.save_package(
            task_id="task-1",
            package=_package(1),
            saved_at=NOW,
        )

    repository.record_review(
        "package-1",
        MaterialReviewAction.APPROVE,
        reviewed_at=NOW,
    )
    repository.record_review(
        "package-2",
        MaterialReviewAction.APPROVE,
        reviewed_at=NOW + timedelta(seconds=1),
    )
    assert repository.current_approved_for_job("job-1").id == "package-2"
    assert repository.get_package("package-1").review_status is (
        MaterialReviewStatus.APPROVED
    )


def test_fact_warning_requires_explicit_override_and_review_is_audited() -> None:
    repository, snapshot_id = _repository()
    repository.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=snapshot_id,
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={},
        created_at=NOW,
    )
    repository.save_package(
        task_id="task-1",
        package=_package(1, facts_passed=False),
        saved_at=NOW,
    )

    with pytest.raises(ValueError, match="override"):
        repository.record_review(
            "package-1",
            MaterialReviewAction.APPROVE,
            reviewed_at=NOW,
        )
    event = repository.record_review(
        "package-1",
        MaterialReviewAction.APPROVE,
        fact_warning_overridden=True,
        feedback="Confirmed from source CV",
        reviewed_at=NOW,
    )

    assert event.resulting_status is (
        MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE
    )
    assert event.fact_warning_overridden is True
    assert repository.list_review_events("package-1") == [event]


def test_reject_and_regenerate_preserve_old_package() -> None:
    repository, snapshot_id = _repository()
    repository.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=snapshot_id,
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={},
        created_at=NOW,
    )
    repository.save_package(
        task_id="task-1",
        package=_package(1),
        saved_at=NOW,
    )
    repository.record_review(
        "package-1",
        MaterialReviewAction.REJECT,
        feedback="Too generic",
        reviewed_at=NOW,
    )

    assert repository.get_package("package-1").review_status is (
        MaterialReviewStatus.REJECTED
    )
    event = repository.record_review(
        "package-1",
        MaterialReviewAction.REGENERATE,
        feedback="Emphasise platform leadership",
        reviewed_at=NOW,
    )
    assert event.resulting_status is MaterialReviewStatus.SUPERSEDED
    assert repository.get_package("package-1").review_status is (
        MaterialReviewStatus.SUPERSEDED
    )
