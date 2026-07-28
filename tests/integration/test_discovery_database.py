import sqlite3
from datetime import UTC, datetime, timedelta

from src.domain.job import (
    ApplyType,
    DiscoveryPersistenceState,
    JobDetailCapture,
)
from src.storage.database import Database
from src.storage.models import JobListing


def capture(
    *,
    jd_text: str = "Original JD",
    title: str = "Product Manager",
    apply_type: ApplyType = ApplyType.QUICK_APPLY,
) -> JobDetailCapture:
    return JobDetailCapture(
        jobsdb_job_id="123",
        canonical_url="https://hk.jobsdb.com/job/123",
        title=title,
        company="Synthetic Ltd",
        location="Hong Kong",
        jd_text=jd_text,
        apply_type=apply_type,
    )


def test_new_unchanged_and_changed_jd_snapshots(tmp_path) -> None:
    db = Database(str(tmp_path / "jobs.db"))

    assert (
        db.save_discovered_job(capture())
        is DiscoveryPersistenceState.NEW
    )
    assert (
        db.save_discovered_job(capture())
        is DiscoveryPersistenceState.UNCHANGED
    )
    assert (
        db.save_discovered_job(capture(jd_text="Changed JD"))
        is DiscoveryPersistenceState.CHANGED
    )

    assert db.get_job_snapshot_count("123") == 2
    current = db.get_current_job_snapshot("123")
    assert current is not None
    assert current.jd_text == "Changed JD"
    assert len(current.content_hash) == 64


def test_metadata_change_does_not_create_snapshot(tmp_path) -> None:
    db = Database(str(tmp_path / "jobs.db"))
    db.save_discovered_job(capture())

    state = db.save_discovered_job(
        capture(title="Senior Product Manager", apply_type=ApplyType.APPLY)
    )

    assert state is DiscoveryPersistenceState.UNCHANGED
    assert db.get_job_snapshot_count("123") == 1
    job = db.get_job("123")
    assert job is not None
    assert job.title == "Senior Product Manager"


def test_unchanged_capture_updates_last_seen(tmp_path) -> None:
    db = Database(str(tmp_path / "jobs.db"))
    first_seen = datetime(2026, 7, 24, 1, tzinfo=UTC)
    later = first_seen + timedelta(hours=1)

    db.save_discovered_job(capture(), captured_at=first_seen)
    db.save_discovered_job(capture(), captured_at=later)

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT first_seen, last_seen FROM jobs WHERE id = '123'"
        ).fetchone()
    assert row == (first_seen.isoformat(), later.isoformat())


def test_mark_inactive_preserves_snapshots(tmp_path) -> None:
    db = Database(str(tmp_path / "jobs.db"))
    db.save_discovered_job(capture())

    db.mark_job_inactive("123", "expired")

    assert db.get_job_snapshot_count("123") == 1
    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT is_active, inactive_reason FROM jobs WHERE id = '123'"
        ).fetchone()
    assert row == (0, "expired")


def test_discovery_migration_is_applied_once(tmp_path) -> None:
    db_path = tmp_path / "jobs.db"
    Database(str(db_path))
    Database(str(db_path))

    with sqlite3.connect(db_path) as conn:
        versions = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }

    assert versions == [(1,), (2,), (3,), (4,), (5,), (6,), (7,)]
    assert {
        "apply_type",
        "first_seen",
        "last_seen",
        "current_snapshot_id",
        "is_active",
        "inactive_reason",
    } <= columns


def test_legacy_save_job_preserves_discovery_snapshot(tmp_path) -> None:
    db = Database(str(tmp_path / "jobs.db"))
    db.save_discovered_job(capture())

    db.save_job(
        JobListing(
            id="123",
            title="Updated listing title",
            company="Synthetic Ltd",
            url="https://hk.jobsdb.com/job/123",
        )
    )

    assert db.get_job_snapshot_count("123") == 1
    assert db.get_current_job_snapshot("123") is not None


def test_list_current_snapshot_records_returns_active_evaluation_inputs(
    tmp_path,
) -> None:
    db = Database(str(tmp_path / "jobs.db"))
    db.save_discovered_job(capture())

    records = db.list_current_snapshot_records()

    assert len(records) == 1
    assert records[0].job_id == "123"
    assert records[0].title == "Product Manager"
    assert records[0].jd_text == "Original JD"
