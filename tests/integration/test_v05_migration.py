import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.domain.job import ApplyType, JobDetailCapture
from src.storage.database import Database
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def test_database_upgrades_v04_state_to_v05_without_data_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.db"
    database = Database(str(path))
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
    SelectionRepository(database).select("job-1", selected_at=NOW)

    Database(str(path))

    with sqlite3.connect(path) as conn:
        versions = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        selected = conn.execute(
            "SELECT job_id, status FROM job_selections"
        ).fetchall()
        job = conn.execute(
            "SELECT id, title FROM jobs WHERE id = 'job-1'"
        ).fetchone()

    assert versions[-1] == (7,)
    assert versions.count((5,)) == 1
    assert selected == [("job-1", "waiting_for_materials")]
    assert job == ("job-1", "Head of AI")
