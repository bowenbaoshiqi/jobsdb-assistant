from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.dashboard.application_service import (
    DashboardApplicationService,
    DirectApplyRequest,
    NotQuickApplyError,
)
from src.domain.job import ApplyType, JobDetailCapture
from src.storage.dashboard_application_repository import (
    DashboardApplicationStatus,
)
from src.storage.database import Database
from src.storage.models import ApplyResult, ApplyStatus
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
DEFAULT_REQUEST = DirectApplyRequest(
    resume_mode="jobsdb_default",
    cover_letter_mode="none",
)


def _save_job(
    database: Database,
    job_id: str,
    apply_type: ApplyType,
) -> None:
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
            title=f"Role {job_id}",
            company="Example Corporation",
            location="Hong Kong",
            jd_text=f"JD for {job_id}",
            apply_type=apply_type,
        ),
        captured_at=NOW,
    )


def _service(
    runner: AsyncMock,
) -> tuple[DashboardApplicationService, Database]:
    database = Database(":memory:")
    _save_job(database, "quick-1", ApplyType.QUICK_APPLY)
    _save_job(database, "apply-1", ApplyType.APPLY)
    _save_job(database, "already-submitted", ApplyType.QUICK_APPLY)
    return (
        DashboardApplicationService(
            database,
            runner=runner,
            now=lambda: NOW,
        ),
        database,
    )


@pytest.mark.asyncio
async def test_rejects_apply_job_without_calling_runner() -> None:
    runner = AsyncMock()
    service, _database = _service(runner)

    with pytest.raises(NotQuickApplyError):
        await service.start("apply-1", DEFAULT_REQUEST)

    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_submitted_history_is_idempotent() -> None:
    runner = AsyncMock()
    service, database = _service(runner)
    database.record_application(
        ApplyResult(
            status=ApplyStatus.SUBMITTED,
            job_id="already-submitted",
        ),
        "existing-session",
    )

    first = await service.start("already-submitted", DEFAULT_REQUEST)
    second = await service.start("already-submitted", DEFAULT_REQUEST)

    assert (
        first.status
        is DashboardApplicationStatus.SKIPPED_ALREADY_APPLIED
    )
    assert second.id == first.id
    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_executes_existing_runner_and_persists_submitted() -> None:
    runner = AsyncMock(
        return_value={
            "session_id": "session-1",
            "total": 1,
            "success": 1,
            "failed": 0,
            "skipped": 0,
        }
    )
    service, _database = _service(runner)

    task = await service.start("quick-1", DEFAULT_REQUEST)
    await service.execute(task.id)

    restored = service.get(task.id)
    assert restored is not None
    assert restored.status is DashboardApplicationStatus.SUBMITTED
    assert restored.session_id == "session-1"
    runner.assert_awaited_once_with("quick-1")


@pytest.mark.asyncio
async def test_does_not_create_material_selection() -> None:
    runner = AsyncMock(return_value={"success": 1, "session_id": "session-1"})
    service, database = _service(runner)

    task = await service.start("quick-1", DEFAULT_REQUEST)
    await service.execute(task.id)

    assert "quick-1" not in SelectionRepository(database).list_selected()


@pytest.mark.asyncio
async def test_repeated_start_returns_same_active_task() -> None:
    runner = AsyncMock()
    service, _database = _service(runner)

    first = await service.start("quick-1", DEFAULT_REQUEST)
    second = await service.start("quick-1", DEFAULT_REQUEST)

    assert second == first


@pytest.mark.asyncio
async def test_captcha_result_requires_attention() -> None:
    runner = AsyncMock(
        return_value={"error": "captcha: manual resolution needed"}
    )
    service, _database = _service(runner)
    task = await service.start("quick-1", DEFAULT_REQUEST)

    await service.execute(task.id)

    restored = service.get(task.id)
    assert restored is not None
    assert restored.status is DashboardApplicationStatus.NEEDS_ATTENTION
    assert restored.error_message == "captcha"
