from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.domain.job import ApplyType, JobDetailCapture
from src.storage.dashboard_application_repository import (
    ApplicationBusyError,
    DashboardApplicationRepository,
    DashboardApplicationStatus,
)
from src.storage.database import Database

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
AFTER = LATER + timedelta(minutes=5)


def _save_job(database: Database, job_id: str) -> None:
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
            title=f"Role {job_id}",
            company="Example Corporation",
            location="Hong Kong",
            jd_text=f"Description for {job_id}",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )


def _database_with_two_jobs(path: str = ":memory:") -> Database:
    database = Database(path)
    _save_job(database, "quick-1")
    _save_job(database, "quick-2")
    return database


def test_only_one_application_task_can_be_active() -> None:
    repository = DashboardApplicationRepository(_database_with_two_jobs())
    repository.create("quick-1", now=NOW)

    with pytest.raises(ApplicationBusyError):
        repository.create("quick-2", now=LATER)


def test_terminal_task_releases_single_execution_lock() -> None:
    repository = DashboardApplicationRepository(_database_with_two_jobs())
    first = repository.create("quick-1", now=NOW)
    finished = repository.finish(
        first.id,
        DashboardApplicationStatus.SUBMITTED,
        now=LATER,
        session_id="session-1",
    )

    second = repository.create("quick-2", now=AFTER)

    assert finished.status is DashboardApplicationStatus.SUBMITTED
    assert finished.session_id == "session-1"
    assert second.status is DashboardApplicationStatus.APPLYING


def test_latest_task_survives_repository_recreation(tmp_path: Path) -> None:
    database_path = tmp_path / "jobs.db"
    database = _database_with_two_jobs(str(database_path))
    task = DashboardApplicationRepository(database).create(
        "quick-1",
        now=NOW,
    )

    restored = DashboardApplicationRepository(
        Database(str(database_path))
    ).get(task.id)

    assert restored == task


def test_create_rejects_unknown_job() -> None:
    with pytest.raises(KeyError, match="missing"):
        DashboardApplicationRepository(Database(":memory:")).create(
            "missing",
            now=NOW,
        )


def test_only_active_task_can_finish() -> None:
    repository = DashboardApplicationRepository(_database_with_two_jobs())
    task = repository.create("quick-1", now=NOW)
    repository.finish(
        task.id,
        DashboardApplicationStatus.FAILED,
        now=LATER,
        error_message="synthetic failure",
    )

    with pytest.raises(ValueError, match="not applying"):
        repository.finish(
            task.id,
            DashboardApplicationStatus.SUBMITTED,
            now=AFTER,
        )


def test_latest_for_jobs_returns_only_latest_task() -> None:
    repository = DashboardApplicationRepository(_database_with_two_jobs())
    first = repository.create("quick-1", now=NOW)
    repository.finish(
        first.id,
        DashboardApplicationStatus.FAILED,
        now=LATER,
    )
    latest = repository.create("quick-1", now=AFTER)

    assert repository.latest_for_jobs(["quick-1", "quick-2"]) == {
        "quick-1": latest,
    }
