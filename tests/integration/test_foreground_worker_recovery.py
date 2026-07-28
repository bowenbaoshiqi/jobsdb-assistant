from datetime import UTC, datetime
from pathlib import Path

from src.application.foreground_worker import ForegroundWorker
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


class NoMaterials:
    async def run_next(self) -> bool:
        return False


class RepositoryApplicationRunner:
    def __init__(self, repository: ApplicationExecutionRepository) -> None:
        self.repository = repository

    async def run_next(self) -> bool:
        execution = self.repository.next_runnable()
        if execution is None:
            return False
        if execution.status is ApplicationExecutionStatus.QUEUED:
            self.repository.transition(
                execution.id,
                ApplicationExecutionStatus.PREPARING_RESUME,
                at=NOW,
            )
            return True
        if execution.status is ApplicationExecutionStatus.PREPARING_RESUME:
            self.repository.transition(
                execution.id,
                ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION,
                at=NOW,
            )
            return True
        return False


def _repository(path: Path) -> ApplicationExecutionRepository:
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
    return ApplicationExecutionRepository(database)


def _execution() -> ApplicationExecution:
    return ApplicationExecution(
        id="execution-1",
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
        created_at=NOW,
        updated_at=NOW,
    )


async def test_worker_restart_resumes_durable_preparation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.db"
    first_repository = _repository(path)
    first_repository.create(_execution())
    first_runner = RepositoryApplicationRunner(first_repository)
    assert await first_runner.run_next()
    assert first_repository.get("execution-1").status is (
        ApplicationExecutionStatus.PREPARING_RESUME
    )

    restored_repository = ApplicationExecutionRepository(Database(str(path)))
    worker = ForegroundWorker(
        material_runner=NoMaterials(),
        application_runner=RepositoryApplicationRunner(restored_repository),
    )
    await worker.run_until_idle()

    assert restored_repository.get("execution-1").status is (
        ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
