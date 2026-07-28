from datetime import UTC, datetime, timedelta

import pytest

from src.domain.job import ApplyType, JobDetailCapture
from src.storage.database import Database
from src.storage.job_batch_repository import (
    ActiveDiscoveryError,
    JobBatchRepository,
)

NOW = datetime(2026, 7, 28, 6, 0, tzinfo=UTC)


def _job(database: Database, job_id: str) -> None:
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
            title=f"Role {job_id}",
            company="Example",
            location="Hong Kong",
            jd_text=f"JD {job_id}",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )


def test_archive_and_start_next_is_immediate_and_ordered(tmp_path) -> None:
    database = Database(str(tmp_path / "jobs.db"))
    for job_id in ("1", "2", "3"):
        _job(database, job_id)
    repository = JobBatchRepository(database)
    first = repository.create("AI Lead", now=NOW)
    repository.add_jobs(first.id, ["1", "2"], now=NOW)
    repository.mark_ready(first.id)

    second = repository.archive_and_create(
        "AI Lead",
        now=NOW + timedelta(minutes=1),
    )
    repository.add_jobs(second.id, ["3"], now=NOW)

    assert repository.current().id == second.id
    assert repository.current_job_ids() == ["3"]
    assert repository.historical_job_ids() == {"1", "2", "3"}
    assert repository.get(first.id).status == "archived"


def test_cannot_archive_again_while_discovery_is_running(tmp_path) -> None:
    repository = JobBatchRepository(
        Database(str(tmp_path / "jobs.db"))
    )
    repository.create("AI Lead", now=NOW)

    with pytest.raises(ActiveDiscoveryError):
        repository.archive_and_create("AI Lead", now=NOW)


def test_purge_expired_batch_removes_all_job_data(tmp_path) -> None:
    database = Database(str(tmp_path / "jobs.db"))
    _job(database, "old")
    repository = JobBatchRepository(database)
    batch = repository.create("AI Lead", now=NOW - timedelta(days=40))
    repository.add_jobs(
        batch.id,
        ["old"],
        now=NOW - timedelta(days=40),
    )
    repository.mark_ready(batch.id)
    repository.archive_and_create(
        "new",
        now=NOW - timedelta(days=35),
    )

    removed = repository.purge_expired(
        cutoff=NOW - timedelta(days=30),
    )

    assert removed == {"old"}
    assert database.get_job("old") is None
    assert repository.get(batch.id) is None
