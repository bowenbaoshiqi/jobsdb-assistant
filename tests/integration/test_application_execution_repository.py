from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.domain.application_execution import (
    ApplicationExecution,
    ApplicationExecutionStatus,
    ApplicationIdentity,
)
from src.domain.job import ApplyType, JobDetailCapture
from src.storage.application_execution_repository import (
    ApplicationExecutionRepository,
)
from src.storage.database import Database

NOW = datetime(2026, 7, 28, tzinfo=UTC)


def _database(path: Path) -> Database:
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
    return database


def _execution(
    *,
    execution_id: str = "execution-1",
    created_at: datetime = NOW,
) -> ApplicationExecution:
    return ApplicationExecution(
        id=execution_id,
        identity=ApplicationIdentity(
            job_id="job-1",
            snapshot_id="1",
            snapshot_hash="a" * 64,
            account_alias="personal",
            package_id="package-1",
            material_version=1,
            resume_sha256="b" * 64,
            cover_letter_sha256="c" * 64,
            apply_type=ApplyType.QUICK_APPLY,
        ),
        status=ApplicationExecutionStatus.QUEUED,
        remote_resume_filename="JBA_job-1_v1_bbbbbbbb.pdf",
        created_at=created_at,
        updated_at=created_at,
    )


def test_application_execution_survives_repository_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.db"
    saved = ApplicationExecutionRepository(_database(path)).create(_execution())

    restored = ApplicationExecutionRepository(Database(str(path))).get(saved.id)

    assert restored == saved


def test_create_is_idempotent_for_same_identity(tmp_path: Path) -> None:
    repository = ApplicationExecutionRepository(
        _database(tmp_path / "jobs.db")
    )

    first = repository.create(_execution())
    second = repository.create(
        _execution(execution_id="different-execution-id")
    )

    assert second.id == first.id


def test_create_rejects_different_data_for_existing_execution_id(
    tmp_path: Path,
) -> None:
    repository = ApplicationExecutionRepository(
        _database(tmp_path / "jobs.db")
    )
    repository.create(_execution())
    changed = _execution().model_copy(
        update={"remote_resume_filename": "different.pdf"}
    )

    with pytest.raises(ValueError, match="different data"):
        repository.create(changed)


def test_next_runnable_is_oldest_non_terminal(tmp_path: Path) -> None:
    repository = ApplicationExecutionRepository(
        _database(tmp_path / "jobs.db")
    )
    older = repository.create(_execution())
    repository.create(
        _execution(
            execution_id="execution-2",
            created_at=NOW + timedelta(seconds=1),
        ).model_copy(
            update={
                "identity": _execution().identity.model_copy(
                    update={
                        "package_id": "package-2",
                        "material_version": 2,
                        "resume_sha256": "d" * 64,
                    }
                ),
                "remote_resume_filename": "JBA_job-1_v2_dddddddd.pdf",
            }
        )
    )

    assert repository.next_runnable().id == older.id


def test_transition_persists_event_and_submitted_job_guard(
    tmp_path: Path,
) -> None:
    repository = ApplicationExecutionRepository(
        _database(tmp_path / "jobs.db")
    )
    repository.create(_execution())
    repository.transition(
        "execution-1",
        ApplicationExecutionStatus.PREPARING_RESUME,
        at=NOW + timedelta(seconds=1),
    )
    repository.transition(
        "execution-1",
        ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION,
        at=NOW + timedelta(seconds=2),
    )
    repository.transition(
        "execution-1",
        ApplicationExecutionStatus.SUBMITTING,
        at=NOW + timedelta(seconds=3),
    )
    submitted = repository.transition(
        "execution-1",
        ApplicationExecutionStatus.SUBMITTED,
        at=NOW + timedelta(seconds=4),
    )

    assert submitted.status is ApplicationExecutionStatus.SUBMITTED
    assert repository.has_submitted_job("job-1", "personal")
    assert [event.to_status for event in repository.list_events("execution-1")] == [
        ApplicationExecutionStatus.PREPARING_RESUME,
        ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION,
        ApplicationExecutionStatus.SUBMITTING,
        ApplicationExecutionStatus.SUBMITTED,
    ]
