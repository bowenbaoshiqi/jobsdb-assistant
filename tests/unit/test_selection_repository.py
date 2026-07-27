from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.domain.job import ApplyType, JobDetailCapture
from src.storage.database import Database
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def _save_current_job(database: Database, job_id: str = "quick-1") -> None:
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
            title="Head of AI",
            company="Example Corporation",
            location="Hong Kong",
            jd_text="Lead an enterprise AI platform team.",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )


def test_select_is_durable_and_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "jobs.db"
    database = Database(str(database_path))
    _save_current_job(database)
    repository = SelectionRepository(database)

    first = repository.select("quick-1", selected_at=NOW)
    second = repository.select("quick-1", selected_at=LATER)

    assert first.selected_at == NOW
    assert second.selected_at == NOW
    assert second.updated_at == LATER
    restored = SelectionRepository(Database(str(database_path))).list_selected()
    assert restored["quick-1"].status == "waiting_for_materials"


def test_select_rejects_unknown_job() -> None:
    with pytest.raises(KeyError, match="missing"):
        SelectionRepository(Database(":memory:")).select(
            "missing",
            selected_at=NOW,
        )


def test_deselect_removes_current_state() -> None:
    database = Database(":memory:")
    _save_current_job(database)
    repository = SelectionRepository(database)
    repository.select("quick-1", selected_at=NOW)

    assert repository.deselect("quick-1") is True
    assert repository.deselect("quick-1") is False
    assert repository.list_selected() == {}
