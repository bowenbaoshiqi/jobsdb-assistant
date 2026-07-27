"""Guarded reuse of the existing single-job Quick Apply workflow."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.domain.job import ApplyType
from src.storage.dashboard_application_repository import (
    DashboardApplicationRepository,
    DashboardApplicationStatus,
    DashboardApplicationTask,
)
from src.storage.database import Database

QuickApplyRunner = Callable[[str], Awaitable[dict]]


class NotQuickApplyError(ValueError):
    """The requested job requires the manual Apply path."""


class DirectApplyRequest(BaseModel):
    """The only material modes permitted by the direct path."""

    model_config = ConfigDict(frozen=True)

    resume_mode: Literal["jobsdb_default"]
    cover_letter_mode: Literal["none"]


class DashboardApplicationService:
    """Validate, persist, and execute one direct Quick Apply task."""

    def __init__(
        self,
        database: Database,
        *,
        runner: QuickApplyRunner,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.runner = runner
        self.now = now or (lambda: datetime.now(UTC))
        self.tasks = DashboardApplicationRepository(database)

    async def start(
        self,
        job_id: str,
        request: DirectApplyRequest,
    ) -> DashboardApplicationTask:
        del request
        snapshot = self.database.get_current_job_snapshot_record(job_id)
        if snapshot is None:
            raise KeyError(job_id)
        if snapshot.apply_type is not ApplyType.QUICK_APPLY:
            raise NotQuickApplyError(job_id)

        latest = self.tasks.latest_for_jobs([job_id]).get(job_id)
        if latest is not None and latest.status in {
            DashboardApplicationStatus.APPLYING,
            DashboardApplicationStatus.SUBMITTED,
            DashboardApplicationStatus.NEEDS_ATTENTION,
            DashboardApplicationStatus.SKIPPED_ALREADY_APPLIED,
        }:
            return latest

        task = self.tasks.create(job_id, now=self.now())
        if job_id in self.database.get_applied_job_ids():
            return self.tasks.finish(
                task.id,
                DashboardApplicationStatus.SKIPPED_ALREADY_APPLIED,
                now=self.now(),
                error_message="already_applied",
            )
        return task

    async def execute(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status is not DashboardApplicationStatus.APPLYING:
            return
        try:
            result = await self.runner(task.job_id)
        except Exception:
            self.tasks.finish(
                task.id,
                DashboardApplicationStatus.FAILED,
                now=self.now(),
                error_message="quick_apply_runner_failed",
            )
            return

        status, error_message = self._classify(result)
        self.tasks.finish(
            task.id,
            status,
            now=self.now(),
            session_id=result.get("session_id"),
            error_message=error_message,
            screenshot_path=result.get("screenshot_path"),
        )

    def get(self, task_id: str) -> DashboardApplicationTask | None:
        return self.tasks.get(task_id)

    @staticmethod
    def _classify(
        result: dict,
    ) -> tuple[DashboardApplicationStatus, str | None]:
        error = str(result.get("error", "")).casefold()
        if error:
            if "captcha" in error:
                return (
                    DashboardApplicationStatus.NEEDS_ATTENTION,
                    "captcha",
                )
            if "session_expired" in error or "login" in error:
                return (
                    DashboardApplicationStatus.NEEDS_ATTENTION,
                    "login_required",
                )
            if "complex_form" in error:
                return (
                    DashboardApplicationStatus.NEEDS_ATTENTION,
                    "complex_form",
                )
            return DashboardApplicationStatus.FAILED, "quick_apply_failed"
        if int(result.get("success", 0)) > 0:
            return DashboardApplicationStatus.SUBMITTED, None
        if int(result.get("skipped", 0)) > 0:
            return DashboardApplicationStatus.FAILED, "quick_apply_skipped"
        return DashboardApplicationStatus.FAILED, "no_submission_recorded"
