"""Bind approved packages to resumable Quick Apply and manual handoff."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from src.domain.application_execution import (
    ApplicationExecution,
    ApplicationExecutionStatus,
    ApplicationIdentity,
)
from src.domain.job import ApplyType
from src.domain.material import (
    ApplicationPackage,
    MaterialReviewStatus,
)
from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.resumes import (
    HumanInterventionRequiredError,
    RemoteResumeManager,
)
from src.materials.artifacts import hash_file
from src.storage.application_execution_repository import (
    ApplicationExecutionRepository,
)
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository
from src.storage.models import ApplyResult, ApplyStatus


class MaterialWizard(Protocol):
    async def prepare(
        self,
        context: ApplicationMaterialContext,
    ) -> ApplyResult: ...

    async def submit(
        self,
        context: ApplicationMaterialContext,
    ) -> ApplyResult: ...


class ResumeReplacer(Protocol):
    async def replace_all_with(
        self,
        pdf_path: Path,
        remote_name: str,
    ): ...


@dataclass(frozen=True)
class ManualApplicationHandoff:
    execution_id: str
    job_url: str
    resume_path: Path
    cover_letter_text: str


class ApplicationExecutionService:
    def __init__(
        self,
        *,
        database: Database,
        materials: MaterialRepository,
        executions: ApplicationExecutionRepository,
        resume_manager: RemoteResumeManager | ResumeReplacer,
        wizard: MaterialWizard,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.materials = materials
        self.executions = executions
        self.resume_manager = resume_manager
        self.wizard = wizard
        self.now = now or (lambda: datetime.now(UTC))

    def queue(
        self,
        job_id: str,
        *,
        account_alias: str,
    ) -> ApplicationExecution:
        snapshot = self._snapshot(job_id)
        if snapshot.apply_type is not ApplyType.QUICK_APPLY:
            raise ValueError("only Quick Apply can enter automatic queue")
        if self.executions.has_submitted_job(job_id, account_alias):
            raise ValueError("job was already submitted")
        package = self._approved_package(job_id)
        return self.executions.create(
            self._execution(snapshot, package, account_alias)
        )

    def confirm_submission(
        self,
        execution_id: str,
    ) -> ApplicationExecution:
        execution = self.executions.get(execution_id)
        if execution is None:
            raise KeyError(execution_id)
        if (
            execution.status
            is not ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION
        ):
            raise ValueError("application is not waiting for confirmation")
        self._context(execution)
        return self.executions.transition(
            execution.id,
            ApplicationExecutionStatus.SUBMITTING,
            at=self.now(),
        )

    def get(self, execution_id: str) -> ApplicationExecution | None:
        return self.executions.get(execution_id)

    async def run_next(self) -> bool:
        execution = self.executions.next_runnable()
        if execution is None:
            return False
        if execution.status is ApplicationExecutionStatus.QUEUED:
            self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.PREPARING_RESUME,
                at=self.now(),
            )
            return True
        if execution.status is ApplicationExecutionStatus.PREPARING_RESUME:
            await self._prepare(execution)
            return True
        if execution.status is ApplicationExecutionStatus.SUBMITTING:
            await self._submit(execution)
            return True
        return False

    def manual_handoff(
        self,
        job_id: str,
        *,
        account_alias: str,
    ) -> ManualApplicationHandoff:
        snapshot = self._snapshot(job_id)
        if snapshot.apply_type is not ApplyType.APPLY:
            raise ValueError("manual handoff requires an Apply role")
        package = self._approved_package(job_id)
        execution = self.executions.create(
            self._execution(snapshot, package, account_alias)
        )
        if execution.status is ApplicationExecutionStatus.QUEUED:
            execution = self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.MANUAL_HANDOFF,
                at=self.now(),
            )
        _resume, cover = self._verified_artifacts(package)
        return ManualApplicationHandoff(
            execution_id=execution.id,
            job_url=snapshot.canonical_url,
            resume_path=Path(package.resume.path),
            cover_letter_text=cover.read_text(encoding="utf-8"),
        )

    async def _prepare(self, execution: ApplicationExecution) -> None:
        try:
            context, resume = self._context(execution)
            await self.resume_manager.replace_all_with(
                resume,
                context.resume_filename,
            )
            result = await self.wizard.prepare(context)
            if result.status is not ApplyStatus.READY_FOR_REVIEW:
                raise HumanInterventionRequiredError(
                    result.error_message or "application review not reached"
                )
            self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION,
                at=self.now(),
            )
        except HumanInterventionRequiredError as exc:
            self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.WAITING_FOR_HUMAN,
                at=self.now(),
                error_code="human_intervention_required",
                error_message=str(exc),
            )
        except Exception as exc:
            self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.FAILED,
                at=self.now(),
                error_code="application_preparation_failed",
                error_message=str(exc),
            )

    async def _submit(self, execution: ApplicationExecution) -> None:
        try:
            context, _resume = self._context(execution)
            result = await self.wizard.submit(context)
        except Exception as exc:
            self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.SUBMISSION_UNCERTAIN,
                at=self.now(),
                error_code="submit_result_unknown",
                error_message=str(exc),
            )
            return
        if result.status is ApplyStatus.SUBMITTED:
            self.executions.transition(
                execution.id,
                ApplicationExecutionStatus.SUBMITTED,
                at=self.now(),
            )
            return
        self.executions.transition(
            execution.id,
            ApplicationExecutionStatus.SUBMISSION_UNCERTAIN,
            at=self.now(),
            error_code="submit_result_unknown",
            error_message=result.error_message,
        )

    def _context(
        self,
        execution: ApplicationExecution,
    ) -> tuple[ApplicationMaterialContext, Path]:
        package = self._approved_package(execution.identity.job_id)
        if (
            package.id != execution.identity.package_id
            or package.version != execution.identity.material_version
            or package.resume.sha256 != execution.identity.resume_sha256
            or package.cover_letter.sha256
            != execution.identity.cover_letter_sha256
        ):
            raise ValueError("application package is no longer current approved")
        resume, cover = self._verified_artifacts(package)
        cover_text = cover.read_text(encoding="utf-8")
        return (
            ApplicationMaterialContext(
                job_id=execution.identity.job_id,
                package_id=package.id,
                resume_filename=execution.remote_resume_filename,
                resume_sha256=package.resume.sha256,
                cover_letter_text=cover_text,
                cover_letter_sha256=package.cover_letter.sha256,
            ),
            resume,
        )

    def _approved_package(self, job_id: str) -> ApplicationPackage:
        package = self.materials.current_approved_for_job(job_id)
        if package is None or package.review_status not in {
            MaterialReviewStatus.APPROVED,
            MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE,
        }:
            raise ValueError("current approved package is required")
        if not package.layout.passed or package.layout.findings:
            raise ValueError("approved package failed layout integrity")
        return package

    @staticmethod
    def _verified_artifacts(
        package: ApplicationPackage,
    ) -> tuple[Path, Path]:
        resume = Path(package.resume.path).resolve()
        cover = Path(package.cover_letter.path).resolve()
        if not resume.is_file() or hash_file(resume) != package.resume.sha256:
            raise ValueError("approved resume hash mismatch")
        if (
            not cover.is_file()
            or hash_file(cover) != package.cover_letter.sha256
        ):
            raise ValueError("approved cover letter hash mismatch")
        return resume, cover

    def _snapshot(self, job_id: str):
        snapshot = self.database.get_current_job_snapshot_record(job_id)
        if snapshot is None:
            raise KeyError(job_id)
        return snapshot

    def _execution(
        self,
        snapshot,
        package: ApplicationPackage,
        account_alias: str,
    ) -> ApplicationExecution:
        created = self.now()
        filename = (
            f"JBA_{snapshot.job_id}_v{package.version}_"
            f"{package.resume.sha256[:8]}.pdf"
        )
        return ApplicationExecution(
            id=f"application-{uuid.uuid4().hex}",
            identity=ApplicationIdentity(
                job_id=snapshot.job_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_hash=snapshot.content_hash,
                account_alias=account_alias,
                package_id=package.id,
                material_version=package.version,
                resume_sha256=package.resume.sha256,
                cover_letter_sha256=package.cover_letter.sha256,
                apply_type=snapshot.apply_type,
            ),
            status=ApplicationExecutionStatus.QUEUED,
            remote_resume_filename=filename,
            created_at=created,
            updated_at=created,
        )
